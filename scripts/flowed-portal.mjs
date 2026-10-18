#!/usr/bin/env bun
// Flowed portal — una sola adreça per a tots els alumnes (docs/ENCARREC-PORTAL.md).
//
// Cada perfil d'alumne és un servidor propi en un port propi (FLOWED_WEBS, amb
// basic auth). Aquest portal escolta en un sol port (FLOWED_PORTAL_PORT, 4000 per
// defecte), demana nom i contrasenya, i reenvia tota la navegació del perfil
// triat afegint la capçalera Authorization. El navegador no veu mai el diàleg de
// basic auth.
//
//   GET  /                 sense sessió: formulari d'entrada; amb sessió: el perfil
//   POST /login            usuari + contrasenya -> entra, o "Què vols fer?" si hi ha
//                          més d'un perfil amb aquelles credencials
//   GET  /switch           torna a "Què vols fer?" (si n'hi ha més d'un)
//   POST /choose           tria perfil (només entre els que han coincidit en entrar)
//   GET  /logout           esborra la sessió
//   GET  /portal/health    comprovació de vida
//   resta                  amb sessió: proxy cap al perfil (inclòs /api/event, SSE)
//
// Secrets: contrasenyes de cada perfil a <perfil>/.web-password; secret de signatura
// de les cookies a <FLOWED_HOME_DIR>/.portal-secret (mode 600). Mai es registren.

import { serve } from "bun"
import crypto from "node:crypto"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

const ROOT = path.resolve(path.join(import.meta.dir, ".."))

const COOKIE = "flowed_portal"
const SESSION_SECONDS = 30 * 24 * 3600 // 30 dies
const PENDING_SECONDS = 10 * 60 // temps per triar perfil després d'entrar
const MAX_FAILS = 5 // intents erronis...
const FAIL_WINDOW_MS = 5 * 60 * 1000 // ...en 5 minuts => espera
const PROXY_TIMEOUT_MS = 600000 // com flowed-web-proxy: POST (torn de model) fins a 10 min
const MAX_FORM_BYTES = 4096

// ---------------------------------------------------------------------------
// Configuració: .env (sense sobreescriure l'entorn), com scripts/lib-paths.sh
// ---------------------------------------------------------------------------

function loadEnvFile(file) {
  if (!file || !fs.existsSync(file)) return
  for (const raw of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const line = raw.replace(/#.*$/, "").trim() // com lib-paths.sh: tot el que va després de # és comentari
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(line)
    if (!m) continue
    let key = m[1]
    let val = m[2]
    if (val.endsWith('"')) val = val.slice(0, -1)
    if (val.startsWith('"')) val = val.slice(1)
    if (val.endsWith("'")) val = val.slice(0, -1)
    if (val.startsWith("'")) val = val.slice(1)
    if (key.startsWith("FLUENT_")) key = "FLOWED_" + key.slice("FLUENT_".length)
    if (!(key in process.env)) process.env[key] = val
  }
}

// FLOWED_ENV_FILE: el que han carregat els scripts (buit = cap). Sense ell, <arrel>/.env.
loadEnvFile("FLOWED_ENV_FILE" in process.env ? process.env.FLOWED_ENV_FILE : path.join(ROOT, ".env"))

const PORTAL_PORT = Number(process.env.FLOWED_PORTAL_PORT || 4000)

function expandHome(p) {
  return p.replace(/^~(?=$|\/)/, os.homedir())
}

// Mateixa regla que scripts/lib-paths.sh (flowed_home).
function flowedHome() {
  if (process.env.FLOWED_HOME) return path.resolve(expandHome(process.env.FLOWED_HOME))
  if (process.env.FLOWED_HOME_DIR) return path.resolve(expandHome(process.env.FLOWED_HOME_DIR))
  const home = os.homedir()
  if (fs.existsSync(path.join(home, ".flowed")) || !fs.existsSync(path.join(home, ".fluent"))) {
    return path.join(home, ".flowed")
  }
  return path.join(home, ".fluent")
}

const HOME_DIR = flowedHome()
const WEBS_SPEC = process.env.FLOWED_WEBS || ""
const SECRET_FILE = path.join(HOME_DIR, ".portal-secret")

// Dominis i escala de nivells: config/domain.json (la mateixa font que hooks/domain.py).
function loadLevelScales() {
  const fallback = { language: ["A1", "A2", "B1", "B2", "C1", "C2"], math: ["m1", "m2", "m3", "m4", "m5", "m6", "m7"] }
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "config", "domain.json"), "utf8"))
    const out = {}
    for (const [name, spec] of Object.entries(manifest.domains || {})) out[name] = spec.level_scale || []
    return { scales: out, default: manifest.default || "math" }
  } catch {
    return { scales: fallback, default: "math" }
  }
}
const DOMAINS = loadLevelScales()

const LANGUAGE_NAMES = {
  english: "Anglès",
  spanish: "Castellà",
  french: "Francès",
  german: "Alemany",
  italian: "Italià",
  catalan: "Català",
}

function domainOf(lp) {
  const explicit = String(lp?.domain || "").trim()
  if (explicit && DOMAINS.scales[explicit]) return explicit
  const learner = lp?.learner || {}
  for (const lv of [learner.current_level, learner.target_level]) {
    const s = String(lv || "").trim()
    if (!s) continue
    for (const [name, scale] of Object.entries(DOMAINS.scales)) if (scale.includes(s)) return name
  }
  return DOMAINS.default
}

// Perfils de FLOWED_WEBS ("id:port id:port"). Llegeix cada perfil en arrancar;
// el nom d'usuari i la contrasenya es miren a cada intent d'entrada.
function readProfiles() {
  const out = []
  for (const spec of WEBS_SPEC.split(/\s+/).filter(Boolean)) {
    const cut = spec.lastIndexOf(":")
    const id = spec.slice(0, cut)
    const port = Number(spec.slice(cut + 1))
    if (cut <= 0 || !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(id) || !Number.isInteger(port)) continue
    out.push({ id, port, dir: path.join(HOME_DIR, id) })
  }
  return out
}

// Dades del perfil que el portal necessita (nom d'usuari = el de flowed-web.sh / server).
function profileInfo(p) {
  let lp = null
  try {
    lp = JSON.parse(fs.readFileSync(path.join(p.dir, "learner-profile.json"), "utf8"))
  } catch {
    return null // sense perfil => no es pot entrar
  }
  const name = String(lp?.learner?.name ?? "").trim().toLowerCase()
  const level = String(lp?.learner?.current_level || "").trim()
  const domain = domainOf(lp)
  let label
  if (domain === "language") {
    const target = String(lp?.learner?.target_language || "").trim()
    label = `🌍 ${LANGUAGE_NAMES[target.toLowerCase()] || target || "Idiomes"}`
  } else {
    label = "🧮 Matemàtiques"
  }
  return { ...p, login: name || "opencode", label, level }
}

// Contrasenya del perfil: el mateix fitxer que llegeix flowed-web.sh (espais fora).
function readPassword(p) {
  try {
    return fs.readFileSync(path.join(p.dir, ".web-password"), "utf8").replace(/\s+/g, "")
  } catch {
    return null
  }
}

function activeProfiles() {
  return readProfiles().map(profileInfo).filter(Boolean)
}

// ---------------------------------------------------------------------------
// Secret i cookies signades (HMAC-SHA256, payload en base64url)
// ---------------------------------------------------------------------------

function loadSecret() {
  fs.mkdirSync(HOME_DIR, { recursive: true })
  try {
    fs.writeFileSync(SECRET_FILE, crypto.randomBytes(32).toString("hex") + "\n", { mode: 0o600, flag: "wx" })
  } catch (e) {
    if (e?.code !== "EEXIST") throw e
  }
  if ((fs.statSync(SECRET_FILE).mode & 0o777) !== 0o600) fs.chmodSync(SECRET_FILE, 0o600)
  return fs.readFileSync(SECRET_FILE, "utf8").trim()
}
const SECRET = loadSecret()

function mac(body) {
  return crypto.createHmac("sha256", SECRET).update(body).digest("base64url")
}

function sign(obj) {
  const body = Buffer.from(JSON.stringify(obj)).toString("base64url")
  return `${body}.${mac(body)}`
}

function unsign(token) {
  if (typeof token !== "string") return null
  const dot = token.lastIndexOf(".")
  if (dot <= 0) return null
  const body = token.slice(0, dot)
  const given = token.slice(dot + 1)
  const expect = mac(body)
  if (given.length !== expect.length) return null
  if (!crypto.timingSafeEqual(Buffer.from(given), Buffer.from(expect))) return null
  try {
    const obj = JSON.parse(Buffer.from(body, "base64url").toString("utf8"))
    if (typeof obj?.e !== "number" || obj.e * 1000 <= Date.now()) return null
    if (!Array.isArray(obj.c) || !obj.c.every((x) => typeof x === "string")) return null
    return obj
  } catch {
    return null
  }
}

function readCookie(req, name) {
  for (const part of (req.headers.get("cookie") || "").split(";")) {
    const i = part.indexOf("=")
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim()
  }
  return ""
}

// Sessió: {p: perfil triat, c: perfils que han coincidit en entrar, e: caducitat}.
// Pendent (abans de triar): {c, e}, sense p.
function getSession(req) {
  const st = unsign(readCookie(req, COOKIE))
  if (!st || typeof st.p !== "string" || !st.c.includes(st.p)) return null
  return st
}
function getPending(req) {
  const st = unsign(readCookie(req, COOKIE))
  if (!st || st.p !== undefined) return null
  return st
}

function cookieHeader(value, maxAge) {
  return `${COOKIE}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}`
}

// ---------------------------------------------------------------------------
// Limitació d'intents (per IP, en memòria)
// ---------------------------------------------------------------------------

const failures = new Map() // ip -> [timestamp ms]

function lockRemainingMs(ip, now) {
  const recent = (failures.get(ip) || []).filter((t) => now - t < FAIL_WINDOW_MS)
  failures.set(ip, recent)
  if (recent.length >= MAX_FAILS) return recent[0] + FAIL_WINDOW_MS - now
  return 0
}

// ---------------------------------------------------------------------------
// Pàgines (estil de web/style.css)
// ---------------------------------------------------------------------------

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])

function page(title, body) {
  return `<!doctype html>
<html lang="ca">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${esc(title)} · FlowEd</title>
<style>
:root {
  --bg: #faf7f2; --panel: #ffffff; --ink: #2b2620; --muted: #8a8177;
  --accent: #2f7d5d; --accent-ink: #ffffff; --border: #e6e0d6;
  --err: #b3402f; --chip: #efe9df;
}
* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; background: var(--bg); color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; font-size: 16px; line-height: 1.5; }
body { display: flex; align-items: center; justify-content: center; padding: 16px; min-height: 100vh; }
main { width: 100%; max-width: 380px; background: var(--panel); border: 1px solid var(--border);
  border-radius: 14px; padding: 24px; box-shadow: 0 1px 3px rgba(43,38,32,.06); }
h1 { margin: 0 0 4px; font-size: 1.5rem; }
.brand { color: var(--accent); font-weight: 700; letter-spacing: .02em; }
p { margin: 8px 0 16px; color: var(--muted); }
label { display: block; font-size: .9rem; color: var(--muted); margin: 12px 0 4px; }
input { width: 100%; font: inherit; font-size: 16px; padding: 10px 12px; border: 1px solid var(--border);
  border-radius: 10px; background: #fff; color: var(--ink); }
input:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
button, .btn { display: block; width: 100%; margin-top: 10px; font: inherit; font-size: 16px; font-weight: 600;
  padding: 11px 14px; border: 0; border-radius: 10px; background: var(--accent); color: var(--accent-ink);
  text-align: center; text-decoration: none; cursor: pointer; }
.btn.alt { background: var(--chip); color: var(--ink); }
.err { background: #fbeae6; color: var(--err); border-radius: 10px; padding: 10px 12px; margin: 0 0 12px; }
.small { font-size: .85rem; color: var(--muted); margin-top: 16px; }
form { margin: 0; }
</style>
</head>
<body>
<main>
${body}
</main>
</body>
</html>`
}

function html(status, title, body, headers = {}) {
  return new Response(page(title, body), {
    status,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", ...headers },
  })
}

function redirect(location, headers = {}) {
  return new Response(null, { status: 303, headers: { location, ...headers } })
}

function loginPage(error = "") {
  return html(
    error ? 401 : 200,
    "Entra",
    `<h1><span class="brand">FlowEd</span></h1>
<p>Entra amb el nom i la contrasenya que t'han donat.</p>
${error ? `<div class="err" role="alert">${esc(error)}</div>` : ""}
<form method="post" action="/login" autocomplete="on">
  <label for="user">Nom</label>
  <input id="user" name="user" type="text" autocomplete="username" autocapitalize="none" autocorrect="off" required autofocus>
  <label for="pass">Contrasenya</label>
  <input id="pass" name="pass" type="password" autocomplete="current-password" required>
  <button type="submit">Entra</button>
</form>
<p class="small">Si no saps la contrasenya, demana-la a qui et va donar accés.</p>`,
  )
}

function choicePage(profiles) {
  const buttons = profiles
    .map(
      (p) => `<form method="post" action="/choose">
  <input type="hidden" name="profile" value="${esc(p.id)}">
  <button type="submit">${esc(p.label)}${p.level ? ` · ${esc(p.level)}` : ""}</button>
</form>`,
    )
    .join("\n")
  return html(
    200,
    "Què vols fer?",
    `<h1>Què vols fer?</h1>
<p>Tens més d'un espai amb aquest nom i aquesta contrasenya.</p>
${buttons}
<a class="btn alt" href="/logout">Surt</a>`,
  )
}

function unavailablePage() {
  return html(
    503,
    "Ara no està disponible",
    `<h1>Ara no està disponible</h1>
<p>L'espai d'aquest alumne no respon. Torna-ho a provar en un moment.</p>
<a class="btn" href="/">Torna-ho a provar</a>
<a class="btn alt" href="/logout">Surt</a>`,
  )
}

// ---------------------------------------------------------------------------
// Entrada, sortida i selecció de perfil
// ---------------------------------------------------------------------------

async function readForm(req) {
  const len = Number(req.headers.get("content-length") || 0)
  if (len > MAX_FORM_BYTES) return new URLSearchParams()
  const text = (await req.text()).slice(0, MAX_FORM_BYTES)
  return new URLSearchParams(text)
}

function samePassword(given, expected) {
  // SHA-256 als dos costats: mateixa longitud, i timingSafeEqual.
  const a = crypto.createHash("sha256").update(String(given)).digest()
  const b = crypto.createHash("sha256").update(String(expected)).digest()
  return crypto.timingSafeEqual(a, b)
}

const DUMMY_PASSWORD = crypto.randomBytes(16).toString("hex")

async function handleLogin(req, ip) {
  const now = Date.now()
  const locked = lockRemainingMs(ip, now)
  if (locked > 0) {
    const mins = Math.ceil(locked / 60000)
    return html(
      429,
      "Massa intents",
      `<h1>Massa intents</h1>
<p>Has fet massa intents seguits. Torna-ho a provar d'aquí a ${mins} ${mins === 1 ? "minut" : "minuts"}.</p>`,
      { "retry-after": String(Math.ceil(locked / 1000)) },
    )
  }

  const form = await readForm(req)
  const user = String(form.get("user") || "").trim().toLowerCase()
  const pass = String(form.get("pass") || "").trim()

  // Es mira cada perfil, sense sortir abans: el temps no revela quin ha coincidit.
  const matches = []
  for (const p of activeProfiles()) {
    const stored = readPassword(p)
    const passOk = samePassword(pass, stored ?? DUMMY_PASSWORD) && stored !== null
    const nameOk = user.length > 0 && p.login === user
    if (nameOk && passOk) matches.push(p)
  }

  if (matches.length === 0) {
    failures.set(ip, [...(failures.get(ip) || []), now])
    return loginPage("Usuari o contrasenya incorrectes.")
  }
  failures.delete(ip)

  if (matches.length === 1) {
    const ids = [matches[0].id]
    const token = sign({ p: ids[0], c: ids, e: Math.floor(now / 1000) + SESSION_SECONDS })
    return redirect("/", { "set-cookie": cookieHeader(token, SESSION_SECONDS) })
  }

  const token = sign({ c: matches.map((p) => p.id), e: Math.floor(now / 1000) + PENDING_SECONDS })
  return redirect("/switch", { "set-cookie": cookieHeader(token, PENDING_SECONDS) })
}

function handleSwitch(req) {
  const st = getSession(req) || getPending(req)
  if (!st) return redirect("/")
  const profiles = activeProfiles().filter((p) => st.c.includes(p.id))
  if (profiles.length < 2) return redirect("/")
  return choicePage(profiles)
}

async function handleChoose(req) {
  const st = getSession(req) || getPending(req)
  if (!st) return redirect("/")
  const form = await readForm(req)
  const chosen = String(form.get("profile") || "")
  if (!st.c.includes(chosen) || !activeProfiles().some((p) => p.id === chosen)) return redirect("/")
  const exp = Math.floor(Date.now() / 1000) + SESSION_SECONDS
  const token = sign({ p: chosen, c: st.c, e: exp })
  return redirect("/", { "set-cookie": cookieHeader(token, SESSION_SECONDS) })
}

function handleLogout() {
  return redirect("/", { "set-cookie": cookieHeader("", 0) })
}

// ---------------------------------------------------------------------------
// Proxy cap al perfil
// ---------------------------------------------------------------------------

const HOP_BY_HOP = new Set([
  "host", "connection", "keep-alive", "proxy-connection", "transfer-encoding", "te", "upgrade",
  "content-length", "accept-encoding", "authorization",
])
const DROP_RESPONSE = new Set([
  "transfer-encoding", "content-encoding", "connection", "content-length", "www-authenticate",
])

function upstreamCookie(req) {
  const kept = (req.headers.get("cookie") || "")
    .split(";")
    .map((s) => s.trim())
    .filter((s) => s && !s.startsWith(`${COOKIE}=`))
  return kept.join("; ")
}

// La pàgina principal d'un perfil porta el marcador del portal (docs/ENCARREC-P4-FLASH-INICI.md §2): la web
// mostra el 🏠 només amb ell. multi = l'alumne té més d'un perfil a la sessió (anar a /switch, no a /logout).
function portalMarker(multi) {
  return `<script>window.__FLOWED_PORTAL={multi:${multi ? "true" : "false"}}</script>`
}

function isMainPage(req) {
  const p = new URL(req.url).pathname
  return req.method === "GET" && (p === "/" || p === "/index.html")
}

async function proxyTo(req, prof, api, multi) {
  const password = readPassword(prof)
  if (password === null) return api ? jsonErr(503, "perfil sense contrasenya") : unavailablePage()

  const url = new URL(req.url)
  const headers = new Headers()
  for (const [k, v] of req.headers) {
    const lk = k.toLowerCase()
    if (HOP_BY_HOP.has(lk) || lk === "cookie") continue
    headers.set(k, v)
  }
  const cookie = upstreamCookie(req)
  if (cookie) headers.set("cookie", cookie)
  // El perfil espera basic auth: l'afegeix el portal, mai el navegador.
  headers.set("authorization", "Basic " + Buffer.from(`${prof.login}:${password}`).toString("base64"))

  // Els cossos són petits (formularis, missatges): es llegeixen sencers, com
  // flowed-web-proxy, perquè el perfil rebi Content-Length.
  const hasBody = req.method !== "GET" && req.method !== "HEAD"
  const body = hasBody ? await req.arrayBuffer() : undefined
  let upstream
  try {
    upstream = await fetch(`http://127.0.0.1:${prof.port}${url.pathname}${url.search}`, {
      method: req.method,
      headers,
      body,
      redirect: "manual",
      ...(hasBody ? { signal: AbortSignal.timeout(PROXY_TIMEOUT_MS) } : {}),
    })
  } catch {
    return api ? jsonErr(502, "perfil no disponible") : unavailablePage()
  }

  const resHeaders = new Headers()
  for (const [k, v] of upstream.headers) {
    if (DROP_RESPONSE.has(k.toLowerCase())) continue
    resHeaders.append(k, v)
  }
  const type = upstream.headers.get("content-type") || ""
  if (isMainPage(req) && upstream.status === 200 && type.includes("text/html")) {
    // Només la pàgina principal: el marcador va just abans de </head>; res més canvia.
    const text = await upstream.text()
    return new Response(text.replace("</head>", portalMarker(multi) + "</head>"), { status: upstream.status, headers: resHeaders })
  }
  return new Response(upstream.body, { status: upstream.status, headers: resHeaders })
}

function jsonErr(status, msg) {
  return new Response(JSON.stringify({ error: msg }), {
    status,
    headers: { "content-type": "application/json" },
  })
}

// ---------------------------------------------------------------------------
// Servidor
// ---------------------------------------------------------------------------

const server = serve({
  port: PORTAL_PORT,
  hostname: "0.0.0.0",
  async fetch(req) {
    // Les respostes poden ser SSE o torns de model llargs: sense timeout d'inactivitat.
    server.timeout(req, 0)
    const url = new URL(req.url)
    const p = url.pathname
    const ip = server.requestIP(req)?.address || "unknown"
    const api = p.startsWith("/api/")

    try {
      if (p === "/portal/health") return new Response("ok\n", { headers: { "content-type": "text/plain" } })
      if (p === "/login") {
        if (req.method === "POST") return await handleLogin(req, ip)
        return redirect("/")
      }
      if (p === "/logout") return handleLogout()
      if (p === "/switch") return handleSwitch(req)
      if (p === "/choose") {
        if (req.method === "POST") return await handleChoose(req)
        return redirect("/")
      }

      const session = getSession(req)
      const prof = session ? activeProfiles().find((x) => x.id === session.p) : null
      if (prof) {
        const multi = activeProfiles().filter((x) => session.c.includes(x.id)).length > 1
        return await proxyTo(req, prof, api, multi)
      }

      if (api) return jsonErr(401, "sense sessió")
      if (getPending(req)) return redirect("/switch")
      return loginPage()
    } catch (e) {
      // Mai es registra el cos de la petició (pot dur contrasenya).
      console.error(`flowed-portal: error a ${req.method} ${p}: ${String(e?.message || e)}`)
      return html(500, "Error", `<h1>Alguna cosa ha fallat</h1><p>Torna-ho a provar.</p>`)
    }
  },
})

const listed = activeProfiles().map((p) => `${p.id}→:${p.port}`)
console.log(
  `flowed-portal :${PORTAL_PORT} · perfils: ${listed.length ? listed.join(" ") : "(cap; mira FLOWED_WEBS)"} · home: ${HOME_DIR}`,
)
