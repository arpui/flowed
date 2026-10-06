// Fluent server — entry point.
// Standalone server that replaces `opencode serve` + the proxy for the Fluent
// web UI. Speaks to the local OpenAI-compatible models directly and persists
// sessions into the per-profile sessions DB (schema-compatible, so the Fluent
// Python hooks keep working unchanged).

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { loadTtsConfig } from "./tts";
import { FluentDB } from "./db";
import { Agent } from "./agent";
import { makeSessionService } from "./session";
import { createHub, serve } from "./http";
import { buildStamp } from "./pacing";


/** What server/src looked like when THIS process started. Printed at startup
 *  and served at /api/global/health, so a test can say out loud whether it is
 *  judging the code that is on disk. */
const BUILD_STAMP = buildStamp(
  path.resolve(import.meta.dirname, "..", ".."),
  (f) => fs.readFileSync(f, "utf8"),
  (d) => fs.readdirSync(d)
);

const VERSION = "0.5.0";

function resolveRoot(): string {
  // Prefer the project root (contains AGENTS.md). When launched from the repo
  // root (`fluent_dev`), cwd is that; otherwise fall back to derivation.
  const cwd = process.cwd();
  if (fs.existsSync(path.join(cwd, "AGENTS.md"))) return cwd;
  return path.resolve(import.meta.dir, "..", "..");
}

function expand(p: string): string {
  return p.startsWith("~") ? path.join(os.homedir(), p.slice(1)) : p;
}

function resolveDataDir(root: string): { dir: string; from: string } {
  if (process.env.FLOWED_DATA_DIR) {
    return { dir: path.resolve(expand(process.env.FLOWED_DATA_DIR)), from: "env" };
  }
  const marker = path.join(root, ".flowed-active");
  try {
    const m = fs.readFileSync(marker, "utf8").trim();
    if (m) return { dir: path.resolve(expand(m)), from: "marker" };
  } catch {
    /* no marker */
  }
  return { dir: path.join(root, "data"), from: "repo-data" };
}

function resolvePassword(dataDir: string): string {
  if (process.env.FLOWED_WEB_PASSWORD) return process.env.FLOWED_WEB_PASSWORD;
  const file = path.join(dataDir, ".web-password");
  try {
    return fs.readFileSync(file, "utf8").trim();
  } catch {
    return "math"; // dev fallback; the launcher always writes a real password
  }
}

// Learner login name: first name lowercased (nes, alex, sam, test…).
// Falls back to "opencode" when the profile can't be read.
function resolveLoginName(dataDir: string): string {
  try {
    const profile = JSON.parse(fs.readFileSync(path.join(dataDir, "learner-profile.json"), "utf8"));
    const name = String(profile?.learner?.name ?? "").trim().toLowerCase();
    if (name) return name;
  } catch {
    /* fall through */
  }
  return "opencode";
}

function loadModels(root: string): AgentModels {
  const deepDefaults = {
    name: "deep",
    baseURL: "http://127.0.0.1:12322/v1",
    temperature: 0.7,
    maxTokens: 4096,
    topP: 0.95,
    timeoutMs: 600000,
  };
  const faceDefaults = {
    name: "face",
    baseURL: "http://127.0.0.1:12323/v1",
    temperature: 0.7,
    maxTokens: 4096,
    topP: 0.95,
    timeoutMs: 120000,
  };
  // Model endpoints: project-local config (later wins):
  //   code defaults <- config/fluent.json (the ONE source, P1-9)
  //                  <- $FLOWED_MODELS_FILE (explicit file override: an
  //                     experiment, e.g. scripts/flowed-sweep.py)
  //                  <- $FLOWED_DEEP_BASE_URL / $FLOWED_FACE_BASE_URL (top;
  //                     so .env drives the server too, not just the scripts)
  const layers: Array<Record<string, unknown>> = [];
  // Canonical project configuration (P1-9): where every model parameter lives.
  // Only an explicit $FLOWED_MODELS_FILE and the *_BASE_URL variables below are
  // allowed to sit on top of it.
  try {
    const canonical = JSON.parse(fs.readFileSync(path.join(root, "config", "fluent.json"), "utf8"));
    const models = (canonical?.models ?? {}) as Record<string, Record<string, unknown>>;
    const view = (m: Record<string, unknown> | undefined) => {
      if (!m) return {};
      const port = typeof m.port === "number" ? m.port : undefined;
      return {
        baseURL: (m.base_url as string) ?? (port ? `http://127.0.0.1:${port}/v1` : undefined),
        temperature: m.temperature,
        maxTokens: m.max_tokens ?? m.maxTokens,
        topP: m.top_p ?? m.topP,
        topK: m.top_k ?? m.topK,
        presencePenalty: m.presence_penalty ?? m.presencePenalty,
        frequencyPenalty: m.frequency_penalty ?? m.frequencyPenalty,
        repeatPenalty: m.repeat_penalty ?? m.repeatPenalty,
        repeatLastN: m.repeat_last_n ?? m.repeatLastN,
        timeout_ms: m.timeout_ms,
      };
    };
    layers.push({ deep: view(models.deep), face: view(models.face) });
  } catch {
    /* no canonical config — defaults and the legacy layers below cover it */
  }
  // config/fluent-models.json used to be a second layer here. It only repeated
  // fluent.json — except that it won over it, so an edit to `temperature` in
  // fluent.json did nothing and a sweep ran every setting at 0.2 without
  // saying so. It is gone (obsolet/config/): a value has one place.
  for (const p of process.env.FLOWED_MODELS_FILE ? [process.env.FLOWED_MODELS_FILE] : []) {
    try {
      const raw = JSON.parse(fs.readFileSync(p, "utf8"));
      if (raw && typeof raw === "object") layers.push(raw);
    } catch {
      /* missing layer — skip */
    }
  }
  const merge = (key: string, defaults: Record<string, unknown>) =>
    layers.reduce((acc, l) => ({ ...acc, ...((l[key] ?? {}) as Record<string, unknown>) }), { ...defaults });
  try {
    const d = merge("deep", deepDefaults as unknown as Record<string, unknown>);
    const f = merge("face", faceDefaults as unknown as Record<string, unknown>);
    const str = (v: unknown, fb: string) => (typeof v === "string" && v ? v : fb);
    const num = (v: unknown, fb: number) => (typeof v === "number" && Number.isFinite(v) ? v : fb);
    /** Only what is configured: an absent knob must stay absent from the
     *  request, so the backend's own default applies and nothing changes for a
     *  machine that has not set it. */
    const opt = (src: Record<string, unknown>, ...keys: string[]) => {
      const out: Record<string, number> = {};
      for (const k of keys) if (typeof src[k] === "number" && Number.isFinite(src[k])) out[k] = src[k] as number;
      return out;
    };
    const deepModel: ModelView = {
      name: str(d.name, deepDefaults.name),
      baseURL: str(d.baseURL, deepDefaults.baseURL),
      temperature: num(d.temperature, deepDefaults.temperature),
      maxTokens: num(d.maxTokens ?? d.max_tokens, deepDefaults.maxTokens),
      topP: num(d.topP, deepDefaults.topP),
      ...opt(d, "topK", "presencePenalty", "frequencyPenalty", "repeatPenalty", "repeatLastN"),
      timeoutMs: num(d.timeout_ms, deepDefaults.timeoutMs),
    };
    const faceModel: ModelView = {
      name: str(f.name, faceDefaults.name),
      baseURL: str(f.baseURL, faceDefaults.baseURL),
      temperature: num(f.temperature, faceDefaults.temperature),
      maxTokens: num(f.maxTokens ?? f.max_tokens, faceDefaults.maxTokens),
      topP: num(f.topP, faceDefaults.topP),
      ...opt(f, "topK", "presencePenalty", "frequencyPenalty", "repeatPenalty", "repeatLastN"),
      timeoutMs: num(f.timeout_ms, faceDefaults.timeoutMs),
    };
    // Explicit env wins over every file (lets .env drive the server too).
    if (process.env.FLOWED_DEEP_BASE_URL) deepModel.baseURL = process.env.FLOWED_DEEP_BASE_URL;
    if (process.env.FLOWED_FACE_BASE_URL) faceModel.baseURL = process.env.FLOWED_FACE_BASE_URL;
    // Token streaming: opt-in, off by default (FLOWED_STREAM=1).
    const stream = /^(1|true|yes|on)$/i.test(process.env.FLOWED_STREAM ?? "");
    deepModel.stream = stream;
    faceModel.stream = stream;
    return {
      deep: deepModel,
      face: faceModel,
      deepEval: { model: deepModel.name, baseURL: deepModel.baseURL, temperature: deepModel.temperature, maxTokens: deepModel.maxTokens, timeoutMs: deepModel.timeoutMs },
    };
  } catch {
    return { deep: deepDefaults, face: faceDefaults, deepEval: { model: deepDefaults.name, baseURL: deepDefaults.baseURL, temperature: deepDefaults.temperature, maxTokens: deepDefaults.maxTokens, timeoutMs: deepDefaults.timeoutMs } };
  }
}

interface AgentModels {
  deep: ModelView;
  face: ModelView;
  deepEval: EvalView;
}
interface ModelView {
  name: string;
  baseURL: string;
  temperature: number;
  maxTokens: number;
  topP: number;
  topK?: number;
  presencePenalty?: number;
  frequencyPenalty?: number;
  repeatPenalty?: number;
  repeatLastN?: number;
  timeoutMs: number;
  /** Token streaming, set from FLOWED_STREAM (off by default). */
  stream?: boolean;
}
interface EvalView {
  model: string;
  baseURL: string;
  temperature: number;
  maxTokens: number;
  timeoutMs: number;
}

// Session inactivity timeout (ms) — if a learner session has no activity for this
// long, we run the final persistence (Capa B) automatically.
// Increased to 30 minutes to allow for slow deep-model grading on large contexts.
// Where a profile's transcript lives. It used to be
// <profile>/.opencode/opencode/opencode.db — opencode's XDG shape, kept long
// after opencode stopped being the runtime. New profiles are born at
// <profile>/sessions/sessions.db; a profile that only has the old file keeps
// being read there (and the old build of the app keeps working on it) until
// scripts/migrate-sessions-db.py copies it over.
export function resolveSessionsDb(dataDir: string): { path: string; legacy: boolean } {
  const fromEnv = process.env.FLOWED_SESSIONS_DB;
  if (fromEnv) return { path: path.resolve(expand(fromEnv)), legacy: false };
  const current = path.join(dataDir, "sessions", "sessions.db");
  if (fs.existsSync(current)) return { path: current, legacy: false };
  const legacy = path.join(dataDir, ".opencode", "opencode", "opencode.db");
  if (fs.existsSync(legacy)) return { path: legacy, legacy: true };
  return { path: current, legacy: false };
}

const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
const SWEEPER_INTERVAL_MS = 60 * 1000; // 1 minute

function main() {
  const root = resolveRoot();
  const { dir: dataDir } = resolveDataDir(root);
  if (!fs.existsSync(path.join(dataDir, "learner-profile.json"))) {
    console.error(`[Fluent] ⚠ data dir has no learner-profile.json: ${dataDir}`);
    console.error(`       create the profile first, or set FLOWED_DATA_DIR.`);
    process.exit(1);
  }

  const password = resolvePassword(dataDir);
  const loginName = resolveLoginName(dataDir);
  const port = Number(process.env.PORT) || Number(process.env.FLOWED_PORT) || 4100;
  const models = loadModels(root);

  const sessionsDb = resolveSessionsDb(dataDir);
  fs.mkdirSync(path.dirname(sessionsDb.path), { recursive: true });
  const db = new FluentDB(sessionsDb.path);
  console.log(`[Fluent] sessions : ${sessionsDb.path}${sessionsDb.legacy ? "  (legacy path)" : ""}`);
  if (sessionsDb.legacy) {
    console.log(
      `[Fluent]            ↳ still on the old opencode layout. To move it (copies, never deletes):\n` +
        `[Fluent]              python3 scripts/migrate-sessions-db.py --dir ${dataDir}`
    );
  }
  const hub = createHub();
  const sessions = makeSessionService(db);

  const agent = new Agent({
    db,
    root,
    dataDir: () => dataDir,
    models: { deep: models.deep, face: models.face },
    deep: models.deepEval,
    emit: (e) => hub.broadcast(e),
  });

  console.log(`[Fluent] data dir : ${dataDir}`);
  console.log(`[Fluent] deep     : ${models.deep.baseURL}  (${models.deep.name})`);
  console.log(`[Fluent] face     : ${models.face.baseURL}  (${models.face.name})`);
  console.log(`[Fluent] streaming: ${models.deep.stream ? "on (FLOWED_STREAM)" : "off"}`);
  console.log(`[Fluent] serving  : http://127.0.0.1:${port}  (login: ${loginName} / ****)`);
  console.log(`[Fluent] build    : ${BUILD_STAMP}  (server/src as it was when this process started)`);

  // Background sweeper: checks for stale learner sessions and runs Capa B (final persistence)
  const sweeper = setInterval(async () => {
    try {
      const stale = db.getStaleSessions(SESSION_TIMEOUT_MS);
      for (const s of stale) {
        // Idempotency: has Capa B already run for THIS SQLite session?
        // The draft's own session_id is the logical "session-NNN" id, which can
        // never equal a "ses_…" id — capa_b_sid records the SQLite one.
        const draftPath = path.join(dataDir, "session-draft.json");
        let capaBDone = false;
        let draftSid = "";
        try {
          const draft = JSON.parse(fs.readFileSync(draftPath, "utf8"));
          draftSid = typeof draft.session_id === "string" ? draft.session_id : "";
          capaBDone =
            draft.capa_b_done === true &&
            (draft.capa_b_sid === s.id || draft.session_id === s.id);
        } catch {
          /* no draft or parse error */
        }
        // Fallback marker: this session's own results file already carries the
        // enriched Capa B fields. Scoped to the ACTIVE learner (loginName) and
        // to the draft's session id — a different, older session that was
        // enriched must never block this one.
        const resultsDir = path.join(dataDir, "results");
        let existingResults = false;
        if (draftSid && fs.existsSync(resultsDir)) {
          const files = fs
            .readdirSync(resultsDir)
            .filter((f) => f.startsWith(`${loginName}-`) && f.includes(draftSid) && f.endsWith(".md"));
          for (const f of files) {
            try {
              const content = fs.readFileSync(path.join(resultsDir, f), "utf8");
              // Check for enriched Capa B data markers
              if (content.includes("new_facts") || content.includes("new_vocabulary") || content.includes("review_results") || content.includes("milestones") || content.includes("focus_next_session")) {
                existingResults = true;
                break;
              }
            } catch { /* ignore */ }
          }
        }

        if (capaBDone || existingResults) {
          continue; // already finalized
        }

        console.log(`[Fluent] 🕐 Session ${s.id} stale (inactive >${SESSION_TIMEOUT_MS / 60000}min), running Capa B...`);
        // Run persist-session.py for this specific session (positional arg, not --session-id)
        const { spawnSync } = await import("node:child_process");
        const proc = spawnSync("python3", [
          path.join(root, "hooks", "persist-session.py"),
          s.id,
          "--dir", dataDir
        ], {
          cwd: root,
          stdio: "inherit",
        });
        if (proc.status === 0) {
          console.log(`[Fluent] ✅ Capa B completed for ${s.id}`);
          db.markFinalized(s.id);
          // Mark Capa B done in session-draft.json to prevent future re-runs
          try {
            const draft = JSON.parse(fs.readFileSync(draftPath, "utf8"));
            draft.capa_b_done = true;
            draft.capa_b_sid = s.id; // SQLite session id, not the "session-NNN" one
            fs.writeFileSync(draftPath, JSON.stringify(draft, null, 2));
          } catch { /* best-effort */ }
        } else {
          // Not marked: retried on the next tick, and the 24 h lookback in
          // getStaleSessions stops it from retrying forever.
          console.error(`[Fluent] ❌ Capa B failed for ${s.id} (exit ${proc.status})`);
        }
      }
    } catch (e) {
      console.error("[Fluent] ⚠ sweeper error:", e);
    }
  }, SWEEPER_INTERVAL_MS);

  // Cleanup on exit
  process.on("SIGINT", () => clearInterval(sweeper));
  process.on("SIGTERM", () => clearInterval(sweeper));

  serve(
    {
      root,
      webDir: path.join(root, "web"),
      dataDir: () => dataDir,
      password,
      loginName,
      port,
      agent,
      sessionService: sessions,
      version: VERSION,
      build: BUILD_STAMP,
      sampling: Object.fromEntries(
        Object.entries({
          temperature: models.deep.temperature,
          top_p: models.deep.topP,
          top_k: models.deep.topK,
          presence_penalty: models.deep.presencePenalty,
          frequency_penalty: models.deep.frequencyPenalty,
          repeat_penalty: models.deep.repeatPenalty,
          repeat_last_n: models.deep.repeatLastN,
        }).filter(([, v]) => typeof v === "number")
      ) as Record<string, number>,
      tts: loadTtsConfig(root, dataDir),
    },
    hub
  );
}

main();
