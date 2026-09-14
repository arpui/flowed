#!/usr/bin/env bun
// Fluent web proxy — one public port serving the static UI and reverse-proxying
// the opencode serve API.
//
//   /            -> web/index.html
//   /app.js ...  -> static files from ../web/
//   /api/<path>  -> <FLUENT_INTERNAL_URL>/<path>  (opencode API, auth header passed through)
//
// Basic auth: the upstream opencode server enforces it (OPENCODE_SERVER_PASSWORD);
// 401 + WWW-Authenticate are passed through so the browser shows its prompt.

import { serve } from "bun"
import fs from "node:fs"
import path from "node:path"

const PUBLIC_PORT = Number(process.env.FLUENT_PUBLIC_PORT || 4100)
const INTERNAL = (process.env.FLUENT_INTERNAL_URL || "http://127.0.0.1:4199").replace(/\/+$/, "")
const WEB_DIR = path.resolve(path.join(import.meta.dir, "..", "web"))
const FLUENT_DATA_DIR = process.env.FLUENT_DATA_DIR || ""

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".webmanifest": "application/manifest+json",
}

function staticResponse(urlPath) {
  const rel = urlPath === "/" ? "index.html" : urlPath.replace(/^\/+/, "")
  const file = path.resolve(WEB_DIR, rel)
  if (!file.startsWith(WEB_DIR)) return new Response("forbidden", { status: 403 })
  try {
    if (!fs.statSync(file).isFile()) return null
  } catch {
    return null
  }
  return new Response(Bun.file(file), {
    headers: { "content-type": MIME[path.extname(file)] || "application/octet-stream" },
  })
}

const server = serve({
  port: PUBLIC_PORT,
  hostname: "0.0.0.0",
  async fetch(req) {
    const url = new URL(req.url)

    if (url.pathname.startsWith("/api/")) {
      // Proxied requests are long-lived: /api/event is an SSE stream (heartbeat
      // every ~10s) and message POSTs block for the whole turn (30s+ of prefill
      // with zero bytes written). Bun.serve's default 10s idle timeout kills both
      // mid-stream (ERR_INCOMPLETE_CHUNKED_ENCODING in the browser), so disable
      // the timeout for every proxied request.
      server.timeout(req, 0)
    }

    if (!url.pathname.startsWith("/api/")) {
      const staticRes = staticResponse(url.pathname)
      if (staticRes) return staticRes
      return new Response("not found", { status: 404 })
    }

    // Fluent-reserved API (not forwarded upstream): lets the web client know the
    // per-profile setup state so it can auto-start /fluent-setup for new users.
    if (url.pathname === "/api/fluent/setup-state") {
      let setupComplete = true
      if (FLUENT_DATA_DIR) {
        try {
          const lp = JSON.parse(
            fs.readFileSync(path.join(FLUENT_DATA_DIR, "learner-profile.json"), "utf8"),
          )
          const sc = lp?.preferences?.setup_complete
          setupComplete = sc === undefined ? true : sc === true
        } catch {
          setupComplete = true
        }
      }
      return new Response(JSON.stringify({ setup_complete: setupComplete }), {
        headers: { "content-type": "application/json" },
      })
    }

    const upstreamPath = url.pathname.slice("/api".length) + (url.search || "")
    const headers = new Headers()
    for (const [k, v] of req.headers) {
      const lk = k.toLowerCase()
      if (lk === "host" || lk === "content-length" || lk === "connection" || lk === "accept-encoding") continue
      headers.set(k, v)
    }
    const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer()

    // Non-GET proxied requests (message POSTs) block on the upstream for the
    // whole model turn — 30s+ with zero bytes on the deep model. Bun's
    // default 10s fetch timeout kills them mid-turn with a 502, so cap them
    // at 5 minutes instead. GETs (incl. the SSE event stream) keep the
    // default: bytes keep flowing via heartbeats, and long-lived streams
    // must not be aborted by a timer.
    let upstream
    try {
      upstream = await fetch(INTERNAL + upstreamPath, {
        method: req.method,
        headers,
        body,
        redirect: "manual",
        ...(req.method === "GET" ? {} : { signal: AbortSignal.timeout(600000) }),
      })
    } catch (e) {
      return new Response(JSON.stringify({ error: "upstream unavailable: " + String(e?.message || e) }), {
        status: 502,
        headers: { "content-type": "application/json" },
      })
    }

    const resHeaders = new Headers()
    for (const [k, v] of upstream.headers) {
      const lk = k.toLowerCase()
      if (["transfer-encoding", "content-encoding", "connection", "content-length"].includes(lk)) continue
      resHeaders.set(k, v)
    }
    resHeaders.delete("content-length")
    return new Response(upstream.body, { status: upstream.status, headers: resHeaders })
  },
})

console.log(`fluent-web proxy :${PUBLIC_PORT} -> ${INTERNAL} (static: ${WEB_DIR})`)
