// Fluent server — local text-to-speech.
//
// The one thing a written tutor cannot do is let you HEAR the sentence said
// properly, which is most of what you want when you are learning to speak a
// language. This is that, and deliberately nothing more: no model call, no
// tool, no prompt change, not one extra token of context per turn. The tutor
// does not know it exists. It is a presentation layer over text that is
// already on screen.
//
// Engine: piper (a static binary plus one ONNX voice per language). CPU only —
// it must never compete for the VRAM the deep model needs, which is the scarce
// resource on both machines.
//
// Kept free of Bun imports so server/test/*.test.ts can exercise it under node.

import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** Longest utterance we will synthesise. A whole feedback message is not a
 *  sentence to repeat, and a runaway string is a runaway subprocess. */
export const MAX_TTS_CHARS = 400;

export interface TtsConfig {
  enabled: boolean;
  /** piper binary — absolute path, or a name on PATH. */
  binary: string;
  /** Voice model (.onnx) per target language, keyed as the profile spells it. */
  voices: Record<string, string>;
  /** Disk budget for one profile's cache, in MB. */
  cacheMaxMb: number;
  /** Hard stop for one synthesis, in ms. */
  timeoutMs: number;
}

export const DEFAULT_TTS: TtsConfig = {
  enabled: false,
  binary: "piper",
  voices: {},
  cacheMaxMb: 200,
  timeoutMs: 20000,
};

export function resolveTtsConfig(raw: unknown): TtsConfig {
  const c = (raw ?? {}) as Record<string, unknown>;
  const voices: Record<string, string> = {};
  for (const [lang, model] of Object.entries((c.voices ?? {}) as Record<string, unknown>)) {
    if (typeof model === "string" && model.trim()) voices[lang.toLowerCase()] = model.trim();
  }
  const num = (v: unknown, fallback: number) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : fallback;
  };
  return {
    enabled: c.enabled === true,
    binary: typeof c.binary === "string" && c.binary.trim() ? c.binary.trim() : DEFAULT_TTS.binary,
    voices,
    cacheMaxMb: num(c.cache_max_mb ?? c.cacheMaxMb, DEFAULT_TTS.cacheMaxMb),
    timeoutMs: num(c.timeout_ms ?? c.timeoutMs, DEFAULT_TTS.timeoutMs),
  };
}

/** The voice for a language, or null when we have none — never a guess: an
 *  English voice reading Catalan teaches the wrong thing. */
export function voiceFor(config: TtsConfig, language: string | undefined): string | null {
  if (!language) return null;
  return config.voices[language.trim().toLowerCase()] ?? null;
}

/**
 * What actually gets spoken.
 *
 * The text comes from a rendered chat bubble, so it arrives carrying markdown,
 * emoji, scores and the tutor's parenthetical asides in the NATIVE language.
 * Reading those aloud with a target-language voice is worse than silence.
 */
export function speakableText(raw: string): string {
  let t = String(raw ?? "");
  t = t.replace(/```[\s\S]*?```/g, " ");          // code / machine blocks
  t = t.replace(/`([^`]*)`/g, "$1");
  t = t.replace(/!\[[^\]]*\]\([^)]*\)/g, " ");    // images
  t = t.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");  // links keep their label
  t = t.replace(/[*_~#>]/g, " ");                 // emphasis, headings, quotes
  t = t.replace(/\([^)]*\)/g, " ");               // asides: usually the native language
  t = t.replace(/\b\d+\s*\/\s*10\b/g, " ");       // "7/10"
  // Emoji and the pictographic ranges the tutor decorates with.
  t = t.replace(/[\u{1F000}-\u{1FAFF}\u{2190}-\u{27BF}\u{FE0F}\u{2B00}-\u{2BFF}]/gu, " ");
  t = t.replace(/\s+/g, " ").trim();
  return t.slice(0, MAX_TTS_CHARS);
}

/** Same sentence, same file. Exercises and corrections repeat constantly, so
 *  the cache is what makes this feel instant rather than "please wait". */
export function cacheKey(text: string, voice: string): string {
  return crypto.createHash("sha1").update(`${voice} ${text}`).digest("hex");
}

export interface TtsRequest {
  text: string;
  language?: string;
}

export type TtsOutcome =
  | { ok: true; file: string; cached: boolean }
  | { ok: false; status: number; error: string };

/**
 * The environment piper needs, derived from where its binary lives.
 *
 * The release tarball ships its own libespeak-ng and libonnxruntime next to the
 * executable, so piper only runs if the loader can find them. Fixing that in a
 * shell profile works right up until the server is started by something that
 * does not read one — systemd, cron, another machine — and then the speaker
 * buttons 503 with nothing in the log to explain it. Deriving it here makes the
 * feature independent of whoever launched the process.
 */
export function ttsEnv(binary: string, base: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  if (!binary.includes("/")) return { ...base }; // on PATH: packaged by the system
  const dir = path.dirname(path.resolve(binary));
  const existing = base.LD_LIBRARY_PATH;
  const parts = [dir, ...(existing ? existing.split(":") : [])].filter(Boolean);
  return { ...base, LD_LIBRARY_PATH: [...new Set(parts)].join(":"), ESPEAK_DATA_PATH: base.ESPEAK_DATA_PATH ?? path.join(dir, "espeak-ng-data") };
}

/** Reject before spawning anything: an empty or absurd request is a bug or an
 *  abuse, never a learner pressing the speaker button. */
export function validate(
  config: TtsConfig,
  req: TtsRequest
): { text: string; voice: string } | TtsOutcome {
  if (!config.enabled) return { ok: false, status: 503, error: "tts disabled" };
  const text = speakableText(req.text);
  if (!text) return { ok: false, status: 400, error: "nothing to say" };
  const voice = voiceFor(config, req.language);
  if (!voice) return { ok: false, status: 503, error: `no voice for ${req.language ?? "(no language)"}` };
  if (!fs.existsSync(voice)) return { ok: false, status: 503, error: `voice model not found: ${voice}` };
  return { text, voice };
}

/** Oldest-first eviction once the profile's cache passes its budget. Audio is
 *  regenerable; a disk that fills up is not. */
export function pruneCache(dir: string, maxMb: number): number {
  let removed = 0;
  try {
    const files = fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".wav"))
      .map((f) => {
        const full = path.join(dir, f);
        const st = fs.statSync(full);
        return { full, size: st.size, mtime: st.mtimeMs };
      })
      .sort((a, b) => a.mtime - b.mtime);
    let total = files.reduce((sum, f) => sum + f.size, 0);
    const budget = maxMb * 1024 * 1024;
    for (const f of files) {
      if (total <= budget) break;
      try {
        fs.unlinkSync(f.full);
        total -= f.size;
        removed += 1;
      } catch {
        /* someone else's file, or gone already */
      }
    }
  } catch {
    /* no cache dir yet */
  }
  return removed;
}

/**
 * Synthesise (or serve from cache) and return the path to a WAV.
 *
 * piper reads the line on stdin and writes the wav to the path given. It is
 * spawned with an argument array — never a shell string — so a learner's
 * sentence can never become a command.
 */
export async function synthesise(
  config: TtsConfig,
  cacheDir: string,
  req: TtsRequest
): Promise<TtsOutcome> {
  const checked = validate(config, req);
  if ("ok" in checked) return checked;
  const { text, voice } = checked;

  const file = path.join(cacheDir, `${cacheKey(text, voice)}.wav`);
  try {
    if (fs.statSync(file).size > 44) return { ok: true, file, cached: true };
  } catch {
    /* not cached yet */
  }

  try {
    fs.mkdirSync(cacheDir, { recursive: true });
  } catch (e) {
    return { ok: false, status: 500, error: `cache dir: ${e instanceof Error ? e.message : String(e)}` };
  }

  const { spawn } = await import("node:child_process");
  const tmp = `${file}.tmp-${process.pid}`;
  const code = await new Promise<number | string>((resolve) => {
    const proc = spawn(config.binary, ["--model", voice, "--output_file", tmp], {
      stdio: ["pipe", "ignore", "pipe"],
      env: ttsEnv(config.binary),
    });
    let stderr = "";
    let settled = false;
    const done = (v: number | string) => {
      if (!settled) {
        settled = true;
        resolve(v);
      }
    };
    const timer = setTimeout(() => {
      proc.kill("SIGKILL");
      done("timeout");
    }, config.timeoutMs);
    proc.stderr?.on("data", (d) => {
      stderr += String(d).slice(0, 500);
    });
    proc.on("error", (e) => {
      clearTimeout(timer);
      done(`spawn: ${e.message}`);
    });
    proc.on("close", (c) => {
      clearTimeout(timer);
      done(c === 0 ? 0 : `exit ${c}${stderr ? `: ${stderr.trim()}` : ""}`);
    });
    proc.stdin?.end(`${text}\n`);
  });

  if (code !== 0) {
    try {
      fs.unlinkSync(tmp);
    } catch {
      /* nothing to clean */
    }
    return { ok: false, status: 500, error: `piper failed (${code})` };
  }

  try {
    fs.renameSync(tmp, file);
  } catch (e) {
    return {
      ok: false,
      status: 500,
      error: `could not store audio: ${e instanceof Error ? e.message : String(e)}`,
    };
  }
  pruneCache(cacheDir, config.cacheMaxMb);
  return { ok: true, file, cached: false };
}

// ---- where this machine keeps piper -------------------------------------
// config/fluent.json travels between machines (rsync, git); piper and its voices
// do not — they live in `_tts/` next to the profiles. Absolute paths to them in
// the shared config broke audio twice on 2026-09-26: after `mv ~/.fluent
// ~/.flowed` (the paths pointed at the old folder) and on llvm after a rsync
// (railab's config replaced llvm's). So the machine's own install is found on
// disk, and config/fluent.json only says whether to use it.

const VOICE_LANGUAGE: Record<string, string> = {
  en: "English", de: "German", fr: "French", es: "Spanish",
  ca: "Catalan", it: "Italian", pt: "Portuguese", nl: "Dutch",
};

/** en_GB-alba-medium.onnx -> "English" (what learner-profile.json calls it). */
export function voiceLanguage(file: string): string | null {
  const m = path.basename(file).match(/^([a-z]{2})_[A-Z]{2}-/);
  return m?.[1] ? VOICE_LANGUAGE[m[1]] ?? null : null;
}

/** The `_tts` folder of this machine: $FLOWED_TTS_DIR, else the one next to
 *  the profile (its parent is the profiles folder), else the profiles folder by
 *  the same rule as hooks/main_paths.py. null when none exists. */
export function ttsDirFor(
  dataDir?: string,
  env: Record<string, string | undefined> = process.env,
  home: string = os.homedir(),
): string | null {
  const candidates: string[] = [];
  if (env.FLOWED_TTS_DIR) candidates.push(env.FLOWED_TTS_DIR);
  if (dataDir) candidates.push(path.join(path.dirname(path.resolve(dataDir)), "_tts"));
  const flowed = path.join(home, ".flowed");
  const fluent = path.join(home, ".fluent");
  const profiles = env.FLOWED_HOME
    ? env.FLOWED_HOME.replace(/^~/, home)
    : fs.existsSync(flowed) || !fs.existsSync(fluent) ? flowed : fluent;
  candidates.push(path.join(profiles, "_tts"));
  return candidates.find((d) => fs.existsSync(d)) ?? null;
}

/** What is installed in a `_tts` folder: piper/piper and voices/*.onnx (with
 *  their .onnx.json). One voice per language, the first by name. */
export function discoverTts(dir: string): { binary?: string; voices: Record<string, string> } {
  const binary = path.join(dir, "piper", "piper");
  const voices: Record<string, string> = {};
  try {
    for (const f of fs.readdirSync(path.join(dir, "voices")).sort()) {
      if (!f.endsWith(".onnx")) continue;
      const full = path.join(dir, "voices", f);
      const lang = voiceLanguage(f);
      if (!lang || !fs.existsSync(full + ".json")) continue;
      voices[lang.toLowerCase()] ??= full;
    }
  } catch {
    /* no voices folder */
  }
  return { binary: fs.existsSync(binary) ? binary : undefined, voices };
}

/** config/fluent.json's `tts` block (on/off and limits) over this machine's
 *  install. A binary or voice named in the config is used only if it exists
 *  here. Absent or malformed means off — audio is a bonus, never a reason the
 *  server fails to start. */
export function loadTtsConfig(root: string, dataDir?: string, ttsDir: string | null = ttsDirFor(dataDir)): TtsConfig {
  let raw: unknown;
  try {
    raw = JSON.parse(fs.readFileSync(path.join(root, "config", "fluent.json"), "utf8"))?.tts;
  } catch {
    return { ...DEFAULT_TTS };
  }
  const base = resolveTtsConfig(raw);
  const found = ttsDir ? discoverTts(ttsDir) : { voices: {} as Record<string, string> };
  const onDisk = (p: string) => !p.includes("/") || fs.existsSync(p);
  const explicitBinary = base.binary !== DEFAULT_TTS.binary && onDisk(base.binary);
  const voices = { ...found.voices };
  for (const [lang, file] of Object.entries(base.voices)) if (onDisk(file)) voices[lang] = file;
  return {
    ...base,
    binary: explicitBinary ? base.binary : found.binary ?? base.binary,
    voices,
    enabled: base.enabled && Object.keys(voices).length > 0,
  };
}
