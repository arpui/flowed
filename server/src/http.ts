// Fluent server — HTTP layer.
// Serves the static web/ UI, the /api/* contract the UI expects, and the SSE
// /api/event stream, protected by basic auth (per-profile .web-password).
// Replaces both `opencode serve` and the fluent-web-proxy.

import fs from "node:fs";
import path from "node:path";
import type { Agent } from "./agent";
import { resumeState, type SessionService } from "./session";
import { synthesise, voiceFor, DEFAULT_TTS, type TtsConfig } from "./tts";

export interface HttpConfig {
  root: string;
  webDir: string;
  dataDir: () => string;
  password: string;
  /** Stamp of server/src as this process loaded it. */
  build?: string;
  /** The sampling knobs actually in force, so a test can report them. */
  sampling?: Record<string, number>;
  /** learner login name (lowercased first name); "opencode" always accepted too */
  loginName: string;
  port: number;
  agent: Agent;
  sessionService: SessionService;
  version: string;
  /** Local text-to-speech. Off unless a voice is installed for this machine. */
  tts?: TtsConfig;
}

interface SSEClient {
  controller: ReadableStreamDefaultController;
  id: number;
}

/** Idle time after which a session is over, matching the sweeper's own
 *  timeout in index.ts: past it, Capa B has run (or is about to). */
const SESSION_IDLE_LIMIT_MS = 30 * 60 * 1000;

// When this server process started — see resumeState() in session.ts.
const BOOT_MS = Date.now();

type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function textOr(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim()) {
    const t = value.trim();
    if (/^\{.*\}$/.test(t)) return fallback; // unfilled template placeholder
    return t;
  }
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

function numberOr(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function percentOr(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const scaled = value <= 1 ? value * 100 : value;
  return Math.round(Math.max(0, Math.min(100, scaled)) * 10) / 10;
}

function firstPercent(source: JsonRecord, keys: string[]): number | null {
  for (const key of keys) {
    const pct = percentOr(source[key]);
    if (pct !== null) return pct;
  }
  return null;
}

function normalizeSkills(dbs: JsonRecord): Array<Record<string, unknown>> {
  const known = ["computation", "steps", "problems", "reasoning", "facts"];
  const mastery = asRecord(dbs.mastery_db);
  const progress = asRecord(dbs.progress_db);
  const profile = asRecord(dbs.learner_profile);
  const names = new Set<string>(known);
  for (const k of Object.keys(asRecord(mastery.skills))) names.add(k);
  for (const k of Object.keys(asRecord(progress.skill_progress))) names.add(k);
  for (const k of Object.keys(asRecord(profile.skills))) names.add(k);

  return [...names].map((name) => {
    const ms = asRecord(asRecord(mastery.skills)[name]);
    const ps = asRecord(asRecord(progress.skill_progress)[name]);
    const ls = asRecord(asRecord(profile.skills)[name]);
    const masteryLevel = Math.max(
      numberOr(ms.mastery_level, -1),
      numberOr(ms.level, -1),
      numberOr(ls.current_level, -1),
      0,
    );
    const accuracy =
      firstPercent(ps, ["accuracy", "avg_accuracy", "success_rate"]) ??
      firstPercent(ms, ["avg_accuracy", "confidence_score", "success_rate"]) ??
      firstPercent(ls, ["confidence", "confidence_score"]);
    return {
      name,
      mastery_level: masteryLevel,
      accuracy,
      sessions: numberOr(ps.sessions),
      exercises: Math.max(numberOr(ps.exercises_completed), numberOr(ms.practice_count)),
      last_practiced: textOr(ps.last_practiced ?? ms.last_practiced ?? ls.last_practiced, "—"),
    };
  });
}

function normalizeWeakPatterns(dbs: JsonRecord) {
  const mistakes = asRecord(dbs.mistakes_db);
  const patterns = asRecord(mistakes.error_patterns);
  const list = Object.entries(patterns)
    .map(([id, raw]) => {
      const p = asRecord(raw);
      return {
        id,
        category: textOr(p.category, "general"),
        subcategory: textOr(p.subcategory, ""),
        frequency: numberOr(p.frequency),
        mastery_level: numberOr(p.mastery_level),
        last_seen: textOr(p.last_occurred ?? p.last_seen, "—"),
      };
    })
    .sort((a, b) => (b.frequency - a.frequency) || (a.mastery_level - b.mastery_level));
  return { total: list.length, weak: list.slice(0, 5) };
}

function normalizeTrends(dbs: JsonRecord) {
  const progress = asRecord(dbs.progress_db);
  const accuracyTrend = asArray(progress.accuracy_trend).slice(-10).map((raw) => {
    const row = asRecord(raw);
    return {
      date: textOr(row.date, "—"),
      accuracy: percentOr(row.accuracy),
      exercises: numberOr(row.exercises),
    };
  });
  const weekly = asArray(progress.weekly_summary).slice(-6).map((raw) => {
    const row = asRecord(raw);
    return {
      week_start: textOr(row.week_start, "—"),
      sessions: numberOr(row.sessions),
      total_minutes: numberOr(row.total_minutes),
      accuracy: percentOr(row.accuracy),
    };
  });
  return { accuracy_trend: accuracyTrend, weekly };
}

function normalizeSessions(dbs: JsonRecord) {
  const log = asRecord(dbs.session_log);
  return asArray(log.sessions).slice(-8).reverse().map((raw) => {
    const s = asRecord(raw);
    const skills = Array.isArray(s.skills_practiced) ? s.skills_practiced.map(String).join(", ") : textOr(s.skill_practiced, "—");
    return {
      session_id: textOr(s.session_id, "—"),
      date: textOr(s.date, "—"),
      skills,
      exercises: numberOr(s.exercises_completed),
      accuracy: percentOr(s.accuracy),
      duration_minutes: numberOr(s.duration_minutes),
    };
  });
}

function normalizeMilestones(dbs: JsonRecord) {
  const log = asRecord(dbs.session_log);
  return asArray(log.milestones).slice(-5).reverse().map((raw) => {
    const m = asRecord(raw);
    return {
      date: textOr(m.date, "—"),
      milestone: textOr(m.milestone, ""),
      session_id: textOr(m.session_id, ""),
    };
  });
}

function normalizeAchievements(dbs: JsonRecord) {
  const profile = asRecord(dbs.learner_profile);
  return asArray(profile.achievements).slice(-8).reverse().map((raw) => {
    const a = asRecord(raw);
    return {
      id: textOr(a.id, ""),
      name: textOr(a.name, ""),
      earned_date: textOr(a.earned_date, "—"),
      description: textOr(a.description, ""),
    };
  });
}

function buildFluentProgress(dbs: JsonRecord, computed: JsonRecord, warnings: string[]) {
  const profile = asRecord(dbs.learner_profile);
  const progress = asRecord(dbs.progress_db);
  const sr = asRecord(dbs.spaced_repetition);
  const overall = asRecord(progress.overall_stats);

  return {
    warnings,
    learner: {
      name: textOr(asRecord(profile.learner).name, ""),
      target_language: textOr(asRecord(profile.learner).target_language, ""),
      native_language: textOr(asRecord(profile.learner).native_language, ""),
      current_level: textOr(asRecord(profile.learner).current_level, ""),
      target_level: textOr(asRecord(profile.learner).target_level, ""),
    },
    streak: {
      current_days: numberOr(profile.current_streak_days),
      active: Boolean(computed.streak_active),
      days_since_last_session: computed.days_since_last_session ?? null,
      last_updated: textOr(profile.last_updated, "—"),
    },
    overview: {
      total_sessions: numberOr(overall.total_sessions ?? profile.total_sessions),
      total_exercises: numberOr(overall.total_exercises),
      total_correct: numberOr(overall.total_correct),
      accuracy: percentOr(overall.accuracy_rate),
      total_study_minutes: numberOr(overall.total_study_minutes ?? profile.total_study_minutes),
      due_today: numberOr(computed.due_reviews_count),
      due_items: asArray(computed.due_review_items).map(String),
      total_review_items: Object.keys(asRecord(sr.items)).length,
      next_session_id: textOr(computed.next_session_id, ""),
    },
    skills: normalizeSkills(dbs),
    patterns: normalizeWeakPatterns(dbs),
    trends: normalizeTrends(dbs),
    // WP4.1: per-step precision + calculation fluency, computed by read-db.py
    // from the .records steps traces (null when the learner has no steps
    // records yet — the panel hides the section).
    steps_precision: computed.steps_precision ?? null,
    // WP5.2: the profile's domain (config/domain.json is the manifest;
    // hooks/domain.py resolves it). The web picks labels by it.
    domain: computed.domain ?? "math",
    recent_sessions: normalizeSessions(dbs),
    milestones: normalizeMilestones(dbs),
    achievements: normalizeAchievements(dbs),
  };
}

class SSEHub {
  private clients = new Set<SSEClient>();
  private nextId = 0;

  add(controller: ReadableStreamDefaultController): () => void {
    const c: SSEClient = { controller, id: this.nextId++ };
    this.clients.add(c);
    return () => {
      this.clients.delete(c);
    };
  }

  broadcast(event: { type: string; properties: Record<string, unknown> }) {
    const payload = `data: ${JSON.stringify({ type: event.type, properties: event.properties })}\n\n`;
    for (const c of this.clients) {
      try {
        c.controller.enqueue(payload);
      } catch {
        this.clients.delete(c);
      }
    }
  }
}

export function createHub() {
  return new SSEHub();
}

export function serve(opts: HttpConfig, hub: SSEHub): { stop: () => void } {
  const authorized = (req: Request): boolean => {
    const header = req.headers.get("authorization") ?? "";
    const match = /^Basic\s+(.+)$/i.exec(header);
    if (!match) return false;
    const decoded = Buffer.from(match[1]!, "base64").toString();
    // username = learner login name (or legacy "opencode"), password = per-profile .web-password
    const idx = decoded.indexOf(":");
    const user = (idx === -1 ? decoded : decoded.slice(0, idx)).trim().toLowerCase();
    const pass = idx === -1 ? "" : decoded.slice(idx + 1);
    if (user !== opts.loginName && user !== "opencode") return false;
    return pass === opts.password;
  };

  const unauth = () =>
    new Response("Unauthorized", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="FlowMath", charset="UTF-8"' },
    });

  const json = (data: unknown, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: { "content-type": "application/json" },
    });

  const readBody = async (req: Request): Promise<unknown> => {
    try {
      return await req.json();
    } catch {
      return null;
    }
  };

  const server = Bun.serve({
    port: opts.port,
    fetch: async (req) => {
      const url = new URL(req.url);
      const p = url.pathname;

      // SSE must be authorized too (the browser reuses basic-auth creds).
      if (p === "/api/event") {
        if (!authorized(req)) return unauth();
        let cleanup: (() => void) | null = null;
        const stream = new ReadableStream({
          start(controller) {
            cleanup = hub.add(controller);
            controller.enqueue(": connected\n\n");
          },
          cancel() {
            cleanup?.();
          },
        });
        return new Response(stream, {
          headers: {
            "content-type": "text/event-stream",
            "cache-control": "no-cache",
            connection: "keep-alive",
          },
        });
      }

      // ---- static assets ----------------------------------------------------
      if (!p.startsWith("/api")) {
        // never require auth for the static shell; API calls will 401.
        let rel = p === "/" ? "index.html" : p.replace(/^\/+/, "");
        let file = path.join(opts.webDir, rel);
        // Prevents path traversal.
        if (!file.startsWith(path.resolve(opts.webDir))) return new Response("Not found", { status: 404 });
        if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
          file = path.join(opts.webDir, "index.html");
        }
        if (!fs.existsSync(file)) return new Response("Not found", { status: 404 });
        const ext = path.extname(file).toLowerCase();
        const ct =
          {
            ".html": "text/html",
            ".js": "application/javascript",
            ".css": "text/css",
            ".svg": "image/svg+xml",
          }[ext] ?? "application/octet-stream";
        let body = fs.readFileSync(file);
        // WP5.2: the shell carries the profile's domain so the web can pick
        // its button bar (same rule as hooks/domain.py: explicit field, else
        // level scale).
        if (rel === "index.html") {
          let dom = "math";
          try {
            const prof = JSON.parse(fs.readFileSync(path.join(opts.dataDir(), "learner-profile.json"), "utf8"));
            const explicit = String(prof?.domain ?? "").trim().toLowerCase();
            if (explicit) dom = explicit;
            else {
              const lv = String(prof?.learner?.current_level ?? prof?.learner?.target_level ?? "").trim().toUpperCase();
              if (/^[A-C][12]$/.test(lv)) dom = "language";
            }
          } catch {
            /* no profile — math default */
          }
          const s = String(body);
          body = s.replace("</head>", `<script>window.__FLOWED_DOMAIN=${JSON.stringify(dom)};</script></head>`);
        }
        return new Response(body, {
          headers: { "content-type": ct, "cache-control": "no-cache" },
        });
      }

      // ---- API --------------------------------------------------------------
      // Long-lived: SSE event stream and message POSTs block for the whole
      // model turn (tens of seconds of prefill with zero bytes on deep). Bun's
      // default idle timeout would kill them mid-stream, so disable it.
      server.timeout(req, 0);
      if (!authorized(req)) return unauth();

      // health
      if (p === "/api/global/health") {
        return json({ ok: true, version: opts.version, service: "math-server",
                      build: opts.build ?? null, sampling: opts.sampling ?? null });
      }

      // agents list (UI requires the "learner" agent to exist)
      if (p === "/api/agent") {
        return json([{ name: "learner", title: "FlowMath learner" }]);
      }

      // setup-state (auto-start /math-setup for onboarding)
      if (p === "/api/math/setup-state") {
        return json({ setup_complete: readSetupState(opts.dataDir()) });
      }

      // visual progress dashboard: normalized view of the 6 learner DBs.
      if (p === "/api/math/progress") {
        const script = path.join(opts.root, "hooks", "read-db.py");
        if (!fs.existsSync(script)) {
          return json({ ok: false, exitCode: -1, error: `read-db.py no trobat: ${script}` }, 500);
        }
        const { spawnSync } = await import("node:child_process");
        const proc = spawnSync("python3", [script, "--full"], {
          cwd: opts.root,
          encoding: "utf8",
          env: { ...process.env, FLOWED_DATA_DIR: opts.dataDir() },
          timeout: 10000,
        }) as unknown as { status: number | null; stdout: string; stderr: string; error?: unknown };

        let payload: unknown = null;
        try {
          payload = JSON.parse(proc.stdout || "");
        } catch {
          payload = null;
        }
        if (!payload) {
          const detail = proc.error ? String(proc.error) : (proc.stderr || "read-db.py no ha produït JSON").slice(0, 800);
          return json({ ok: false, exitCode: proc.status ?? -1, error: detail }, 500);
        }

        const parsed = asRecord(payload);
        const warnings = asArray(parsed._warnings).map(String);
        return json({
          ok: proc.status === 0 || proc.status === 1,
          exitCode: proc.status ?? 0,
          data: buildFluentProgress(asRecord(parsed.databases), asRecord(parsed.computed), warnings),
        });
      }

      // the learner's path through the curriculum (bar, state per competence).
      // `available:false` when the profile's level has no curriculum: the UI
      // then shows nothing, never an error.
      if (p === "/api/math/path") {
        const script = path.join(opts.root, "hooks", "curriculum.py");
        if (!fs.existsSync(script)) return json({ ok: true, data: { available: false } });
        const { spawnSync } = await import("node:child_process");
        const proc = spawnSync("python3", [script, "json", "--auto", "--data", opts.dataDir()], {
          cwd: opts.root,
          encoding: "utf8",
          env: { ...process.env, FLOWED_DATA_DIR: opts.dataDir() },
          timeout: 10000,
        }) as unknown as { status: number | null; stdout: string; stderr: string; error?: unknown };
        let data: unknown = null;
        try {
          data = JSON.parse(proc.stdout || "");
        } catch {
          data = null;
        }
        if (!data) {
          const detail = proc.error ? String(proc.error) : (proc.stderr || "curriculum.py no ha produït JSON").slice(0, 800);
          return json({ ok: false, exitCode: proc.status ?? -1, error: detail }, 500);
        }
        return json({ ok: true, data });
      }

      // the learner has seen the "course completed" notice: it does not come back.
      if (p === "/api/math/path/seen" && req.method === "POST") {
        const script = path.join(opts.root, "hooks", "curriculum.py");
        if (fs.existsSync(script)) {
          const { spawnSync } = await import("node:child_process");
          spawnSync("python3", [script, "notice", "--data", opts.dataDir(), "--seen"], {
            cwd: opts.root, encoding: "utf8", timeout: 10000,
          });
        }
        return json({ ok: true });
      }

      // ---- audio: hear the sentence said properly ------------------------
      // A presentation layer, nothing more. The tutor knows nothing about it,
      // there is no tool and no extra context per turn. When no voice is
      // installed the UI is told so and simply shows no speaker buttons —
      // never a button that fails.
      // WP5.2: TTS follows the DOMAIN (config/domain.json `tts`), not the
      // machine config alone — a language profile hears voices even when the
      // fork's config/fluent.json keeps them off for math.
      const domOfProfile = (): string => {
        try {
          const prof = JSON.parse(fs.readFileSync(path.join(opts.dataDir(), "learner-profile.json"), "utf8"));
          const explicit = String(prof?.domain ?? "").trim().toLowerCase();
          if (explicit) return explicit;
          const lv = String(prof?.learner?.current_level ?? prof?.learner?.target_level ?? "").trim().toUpperCase();
          if (/^[A-C][12]$/.test(lv)) return "language";
        } catch { /* no profile — math default */ }
        return "math";
      };
      const ttsForDomain = (): TtsConfig => {
        const base = opts.tts ?? DEFAULT_TTS;
        try {
          const man = JSON.parse(fs.readFileSync(path.join(opts.root, "config", "domain.json"), "utf8"));
          const spec = (man.domains ?? {})[domOfProfile()] ?? {};
          if (spec.tts === true && base.binary) return { ...base, enabled: true };
        } catch { /* no manifest — machine config decides */ }
        return base;
      };
      if (p === "/api/math/tts-state") {
        const cfg = ttsForDomain();
        const language = readTargetLanguage(opts.dataDir());
        return json({
          enabled: cfg.enabled && !!voiceFor(cfg, language),
          language: language ?? null,
        });
      }

      if (p === "/api/math/say") {
        const cfg = ttsForDomain();
        const text = url.searchParams.get("text") ?? "";
        const language = url.searchParams.get("lang") || readTargetLanguage(opts.dataDir());
        const cacheDir = path.join(opts.dataDir(), ".audio");
        const outcome = await synthesise(cfg, cacheDir, { text, language });
        if (!outcome.ok) return json({ error: outcome.error }, outcome.status);
        const audio = fs.readFileSync(outcome.file);
        return new Response(new Uint8Array(audio), {
          headers: {
            "content-type": "audio/wav",
            "content-length": String(audio.length),
            // Same sentence, same bytes: let the browser keep it too.
            "cache-control": "private, max-age=86400",
            "x-math-cached": outcome.cached ? "1" : "0",
          },
        });
      }

      // Can the browser resume the session it has in localStorage?
      //
      // It used to just resume it, always. Closing the browser does nothing
      // server-side, so coming back hours later landed the learner back in a
      // session the sweeper had already finalized — its later work never got a
      // summary — and one that kept growing: a live profile reached 51,605
      // prompt tokens against a 32,768 context, which means llama.cpp had been
      // truncating from the left, where the system prompt lives. A session
      // that has been finalized, or left alone longer than the sweeper's
      // timeout, is over. Starting a fresh one costs nothing: streak and
      // progress live in the databases, not in the session.
      if (p === "/api/math/session-state") {
        const id = url.searchParams.get("session") ?? "";
        const row = id ? opts.sessionService.get(id) : null;
        if (!row) return json({ exists: false, resumable: false, reason: "unknown" });
        const st = resumeState(row, Date.now(), BOOT_MS, SESSION_IDLE_LIMIT_MS);
        return json({ exists: true, ...st });
      }

      // where the learner is in this session (the header indicator)
      if (p === "/api/math/session-progress") {
        const id = url.searchParams.get("session") ?? "";
        if (!id) return json({ error: "missing session" }, 400);
        return json({ sessionID: id, ...opts.agent.sessionProgress(id) });
      }

      // session summary (Capa A data for instant resume/summary)
      if (p === "/api/math/summary") {
        const dataDir = opts.dataDir();
        const draftPath = path.join(dataDir, "session-draft.json");
        let draft: Record<string, unknown> = {};
        try {
          draft = JSON.parse(fs.readFileSync(draftPath, "utf8"));
        } catch {
          /* no draft */
        }
        // Streak comes from the learner profile (authoritative). It used to be
        // derived by opening a second FluentDB handle per request (never closed)
        // and looking up a hardcoded learner slug.
        let streak = 0;
        try {
          const profile = JSON.parse(
            fs.readFileSync(path.join(dataDir, "learner-profile.json"), "utf8")
          );
          streak = Number(profile?.current_streak_days ?? 0) || 0;
        } catch {
          /* no profile → 0 */
        }

        const exercises = (draft.exercises as Array<Record<string, unknown>>) ?? [];
        const totalExercises = exercises.length;
        const correctCount = exercises.filter((e) => (e.score as number) >= 8).length;
        const accuracy = totalExercises > 0 ? (correctCount / totalExercises) * 100 : 0;
        const avgScore = totalExercises > 0
          ? exercises.reduce((s, e) => s + (e.score as number), 0) / totalExercises
          : 0;

        return json({
          session_id: (draft.session_id as string) ?? "unknown",
          date: (draft.date as string) ?? new Date().toISOString().slice(0, 10),
          duration_minutes: (draft.duration_minutes as number) ?? 0,
          total_exercises: totalExercises,
          correct_count: correctCount,
          accuracy,
          avg_score: avgScore,
          skill_scores: (draft.skill_scores as Record<string, unknown>) ?? {},
          skills_practiced: (draft.skills_practiced as string[]) ?? [],
          exercises,
          error_patterns: (draft.errors as Array<Record<string, unknown>>) ?? [],
          streak,
        });
      }

      // ---- sessions ---------------------------------------------------------
      const sessionMatch = /^\/api\/session\/([^/]+)(?:\/(message|command))?$/.exec(p);
      if (p === "/api/session" && req.method === "POST") {
        const body = (await readBody(req)) as { title?: string } | null;
        const s = opts.sessionService.create(body?.title ?? "Fluent");
        return json({ id: s.id, slug: s.slug, title: s.title });
      }
      if (sessionMatch) {
        const id = decodeURIComponent(sessionMatch[1]!);
        const sub = sessionMatch[2];
        const session = opts.sessionService.get(id);
        if (!session) return json({ error: "session not found" }, 404);

        if (!sub && req.method === "GET") {
          return json({ ...session });
        }
        if (sub === "message" && req.method === "GET") {
          const limit = Number(url.searchParams.get("limit")) || 200;
          return json(opts.sessionService.history(id, limit));
        }
        // A page left open across a restart: nothing is sent to the model, the
        // client starts a clean session (see BOOT_MS).
        if ((sub === "message" || sub === "command") && req.method === "POST" && resumeState(session, Date.now(), BOOT_MS, Infinity).restarted) {
          return json({ bounce: "restart" });
        }
        if (sub === "message" && req.method === "POST") {
          const body = (await readBody(req)) as {
            agent?: string;
            parts?: Array<{ type?: string; text?: string }>;
          } | null;
          const text = (body?.parts ?? [])
            .filter((p) => p?.type === "text")
            .map((p) => p?.text ?? "")
            .join("\n");
          const outcome = await opts.agent.runMessage(id, text, body?.agent ?? "learner");
          return json(outcome);
        }
        if (sub === "command" && req.method === "POST") {
          const body = (await readBody(req)) as { agent?: string; command?: string } | null;
          const outcome = await opts.agent.runCommand(id, body?.command ?? "", body?.agent ?? "learner");
          return json(outcome);
        }
      }
      return json({ error: "not found" }, 404);
    },
  });

  return { stop: () => server.stop(true) };
}

/** The language the learner is learning — the only one we ever read aloud. */
function readTargetLanguage(dataDir: string): string | undefined {
  try {
    const profile = JSON.parse(fs.readFileSync(path.join(dataDir, "learner-profile.json"), "utf8"));
    const lang = profile?.learner?.target_language;
    return typeof lang === "string" && lang.trim() ? lang.trim() : undefined;
  } catch {
    return undefined;
  }
}

function readSetupState(dataDir: string): boolean {
  try {
    const profile = JSON.parse(fs.readFileSync(path.join(dataDir, "learner-profile.json"), "utf8"));
    // Lives under preferences.setup_complete (matches flowed-web-proxy.mjs &
    // new-user.sh). Back-compat: missing flag → treated as completed.
    const sc = profile?.preferences?.setup_complete;
    return sc === undefined ? true : sc === true;
  } catch {
    return true;
  }
}
