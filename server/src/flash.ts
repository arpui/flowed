// Flash v0 — the server side of the vocabulary drill (docs/ENCARREC-FLASH-v0.md).
// No model here: the manifest switch (config/domain.json `flash`), the word
// lists under curriculum/flash/, resolved to the learner's native language.
// The drill itself is web/flash.js.

import fs from "node:fs";
import path from "node:path";

type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((v) => String(v ?? "").trim()).filter((v) => v.length > 0)
    : [];
}

export type NativeCode = "ca" | "es";

/** The learner's native language (free text in the profile) as a code the
 *  lists are written in. Anything not Spanish reads as Catalan. */
export function nativeCode(text: unknown): NativeCode {
  const t = String(text ?? "").trim().toLowerCase();
  if (t === "es") return "es";
  if (t === "ca") return "ca";
  if (t.includes("catal")) return "ca";
  if (/span|espa|castell/.test(t)) return "es";
  return "ca";
}

export interface FlashWordView {
  id: string;
  target: string[];
  native: string[];
}

export interface FlashListView {
  id: string;
  level: string;
  title: string;
  words: FlashWordView[];
}

/** Expands a path whose segments may hold a `*` (e.g. `curriculum/flash/en-*`)
 *  into the existing directories it matches, sorted by name. */
function expandDirGlob(root: string, pattern: string): string[] {
  let dirs = [root];
  for (const seg of pattern.split("/").filter((s) => s.length > 0)) {
    const next: string[] = [];
    for (const d of dirs) {
      if (!seg.includes("*")) {
        next.push(path.join(d, seg));
        continue;
      }
      const re = new RegExp("^" + seg.split("*").map((p) => p.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$");
      let names: string[] = [];
      try {
        names = fs.readdirSync(d).sort();
      } catch {
        continue;
      }
      for (const n of names) if (re.test(n)) next.push(path.join(d, n));
    }
    dirs = next;
  }
  return dirs.filter((d) => {
    try {
      return fs.statSync(d).isDirectory();
    } catch {
      return false;
    }
  });
}

/** Every list under the directories `dirGlob` matches, ordered by level and
 *  then file name. Each word carries its native forms in `code` only. */
export function loadFlashLists(root: string, dirGlob: string, code: NativeCode): FlashListView[] {
  const out: Array<{ file: string; list: FlashListView }> = [];
  for (const dir of expandDirGlob(root, dirGlob)) {
    let files: string[] = [];
    try {
      files = fs.readdirSync(dir).filter((f) => f.endsWith(".json")).sort();
    } catch {
      continue;
    }
    for (const file of files) {
      let raw: JsonRecord;
      try {
        raw = asRecord(JSON.parse(fs.readFileSync(path.join(dir, file), "utf8")));
      } catch {
        continue; // a broken list is skipped, the others still load
      }
      const title = asRecord(raw.title);
      const words: FlashWordView[] = (Array.isArray(raw.words) ? raw.words : []).map((w) => {
        const word = asRecord(w);
        return {
          id: String(word.id ?? ""),
          target: strings(word.target),
          native: strings(asRecord(word.native)[code]),
        };
      });
      out.push({
        file,
        list: {
          id: String(raw.id ?? ""),
          level: String(raw.level ?? ""),
          title: String(title[code] ?? title.en ?? ""),
          words,
        },
      });
    }
  }
  out.sort((a, b) => a.list.level.localeCompare(b.list.level) || a.file.localeCompare(b.file));
  return out.map((x) => x.list);
}

export interface FlashConfig {
  enabled: boolean;
  dir: string;
}

/** The manifest's `flash` block of one domain. Absent means off. */
export function flashConfig(manifest: unknown, domain: string): FlashConfig {
  const flash = asRecord(asRecord(asRecord(manifest).domains)[domain]).flash;
  const f = asRecord(flash);
  return { enabled: f.enabled === true, dir: typeof f.dir === "string" ? f.dir : "" };
}

/** The domain a profile is on (same rule as http.ts and hooks/domain.py:
 *  explicit field, else a CEFR level means language). */
export function profileDomain(profile: unknown): string {
  const prof = asRecord(profile);
  const explicit = String(prof.domain ?? "").trim().toLowerCase();
  if (explicit) return explicit;
  const learner = asRecord(prof.learner);
  const lv = String(learner.current_level ?? learner.target_level ?? "").trim().toUpperCase();
  return /^[A-C][12]$/.test(lv) ? "language" : "math";
}

function readJson(file: string): JsonRecord {
  try {
    return asRecord(JSON.parse(fs.readFileSync(file, "utf8")));
  } catch {
    return {};
  }
}

/** The body of GET /api/flash/lists. Disabled (or no profile to read) gives
 *  an empty list, so nothing of the drill reaches a domain it is not on. */
export function flashListsResponse(root: string, dataDir: string): JsonRecord {
  const profile = readJson(path.join(dataDir, "learner-profile.json"));
  const learner = asRecord(profile.learner);
  const native = String(learner.native_language ?? "").trim();
  const code = nativeCode(native);
  const target = String(learner.target_language ?? "").trim();
  const level = String(learner.current_level ?? "").trim().toUpperCase();
  const cfg = flashConfig(readJson(path.join(root, "config", "domain.json")), profileDomain(profile));
  if (!cfg.enabled || !cfg.dir) {
    return { ok: true, enabled: false, native, nativeCode: code, target, level, lists: [] };
  }
  return { ok: true, enabled: true, native, nativeCode: code, target, level, lists: loadFlashLists(root, cfg.dir, code) };
}
