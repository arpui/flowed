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
  prompt?: string; // math only: the operation shown on the card (native = [prompt])
}

export interface FlashListView {
  id: string;
  level: string;
  title: string;
  words: FlashWordView[];
  kind?: "math"; // absent for language lists
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
      // A math list has `generate` or `items` (docs/ENCARREC-FLASH-MATH.md §2); both at once is ambiguous: skipped.
      if ("generate" in raw && "items" in raw) continue;
      const math = "generate" in raw || "items" in raw;
      const words: FlashWordView[] = math
        ? mathWords(raw).words.map((w) => ({ id: w.id, target: w.target, native: [w.prompt], prompt: w.prompt }))
        : (Array.isArray(raw.words) ? raw.words : []).map((w) => {
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
          ...(math ? { kind: "math" as const } : {}),
        },
      });
    }
  }
  out.sort((a, b) => a.list.level.localeCompare(b.list.level) || a.file.localeCompare(b.file));
  return out.map((x) => x.list);
}

// ---- math lists (docs/ENCARREC-FLASH-MATH.md) ----------------------------------
// `generate`: the server works out every operation and its result (no result is
// written by hand). `items`: hand-written, each checked against its own sum, and
// an item whose result is wrong is dropped. Both give the same words as a
// language list: target = [result], native = [prompt], prompt = what the card shows.
// hooks/curriculum.py flash_lists mirrors these rules: the same ids, the same drops.

export type MathOp = "+" | "−" | "×" | ":";

const MATH_OP = new Map<string, MathOp>([
  ["+", "+"], ["−", "−"], ["-", "−"], ["×", "×"], ["x", "×"], ["*", "×"], [":", ":"], ["/", ":"],
]);
const MATH_OP_ID = new Map<MathOp, string>([["+", "p"], ["−", "m"], ["×", "x"], [":", "d"]]);
const MATH_RANGE_MAX = 1000; // a {from, to} range never holds more than this

export interface MathWord {
  id: string;
  prompt: string;
  target: string[];
}

/** The operator as the lists write it (`x`, `*`, `-`, `/` are synonyms), or null. */
export function normalizeOp(op: unknown): MathOp | null {
  return typeof op === "string" ? MATH_OP.get(op.trim()) ?? null : null;
}

/** A whole number from a JSON value (7 and 7.0 both), or null. */
function wholeNumber(v: unknown): number | null {
  return Number.isInteger(v) ? (v as number) : null;
}

/** The number an answer says (spaces out, comma or dot as decimal point), or null. */
export function numericValue(s: unknown): number | null {
  const t = String(s ?? "").replace(/\s+/g, "").replace(/,/g, ".");
  return /^-?[0-9]+(\.[0-9]+)?$/.test(t) ? Number(t) : null;
}

/** The result of `a op b` when it is a whole number ≥ 0 (no division with a rest, no negative), else null. */
export function opResult(a: number, op: MathOp, b: number): number | null {
  let r: number;
  switch (op) {
    case "+": r = a + b; break;
    case "−": r = a - b; break;
    case "×": r = a * b; break;
    case ":":
      if (b === 0 || a % b !== 0) return null;
      r = a / b;
      break;
  }
  return r < 0 ? null : r;
}

/** A simple operation written out (`23 × 4`, `81 : 9`, `5 - 2`), or null when the text is not one. */
export function simpleOp(prompt: string): { a: number; op: MathOp; b: number } | null {
  const m = /^\s*(-?[0-9]+)\s*([+\-−×x*:/])\s*(-?[0-9]+)\s*$/.exec(prompt);
  if (!m) return null;
  const op = normalizeOp(m[2]);
  return op ? { a: Number(m[1]), op, b: Number(m[3]) } : null;
}

function rangeOf(v: unknown): number[] {
  if (Array.isArray(v)) return v.map(wholeNumber).filter((n): n is number => n !== null);
  const r = asRecord(v);
  const lo = wholeNumber(r.from);
  const hi = wholeNumber(r.to);
  if (lo === null || hi === null || hi - lo > MATH_RANGE_MAX) return [];
  const out: number[] = [];
  for (let i = lo; i <= hi; i++) out.push(i);
  return out;
}

/** Every a op b of a `generate` block, in order (a outer, b inner). Results that are not whole and ≥ 0
 *  are dropped; a repeated id keeps the first. */
export function expandGenerate(gen: unknown): MathWord[] {
  const g = asRecord(gen);
  const op = normalizeOp(g.op);
  if (!op) return [];
  const out: MathWord[] = [];
  const seen = new Set<string>();
  for (const a of rangeOf(g.a)) {
    for (const b of rangeOf(g.b)) {
      const r = opResult(a, op, b);
      const id = `${a}${MATH_OP_ID.get(op)}${b}`;
      if (r === null || seen.has(id)) continue;
      seen.add(id);
      out.push({ id, prompt: `${a} ${op} ${b}`, target: [String(r)] });
    }
  }
  return out;
}

/** Why an explicit item is wrong, or null when it is fine. A simple operation's answer must be its result. */
function itemProblem(item: JsonRecord): string | null {
  if (typeof item.id !== "string" || !item.id.trim()) return "sense id";
  if (typeof item.prompt !== "string" || !item.prompt.trim()) return "sense enunciat";
  const answer = strings(item.answer);
  if (!answer.length) return "sense resultat";
  const sop = simpleOp(item.prompt);
  if (sop) {
    const r = opResult(sop.a, sop.op, sop.b);
    if (r === null) return `${item.prompt} no dona un resultat enter ≥ 0`;
    if (numericValue(answer[0]) !== r) return `${item.prompt} és ${r}, no ${answer[0]}`;
  }
  return null;
}

/** The words of a math list, and what was left out of it (for the test that checks the lists). */
export function mathWords(raw: JsonRecord): { words: MathWord[]; problems: string[] } {
  if ("generate" in raw) {
    const words = expandGenerate(raw.generate);
    const problems = normalizeOp(asRecord(raw.generate).op) ? [] : ["generate: op desconegut"];
    if (!words.length) problems.push("generate: no genera cap operació");
    return { words, problems };
  }
  const words: MathWord[] = [];
  const problems: string[] = [];
  const seen = new Set<string>();
  for (const it of Array.isArray(raw.items) ? raw.items : []) {
    const item = asRecord(it);
    const problem = itemProblem(item);
    if (problem) {
      problems.push(`ítem ${JSON.stringify(item.id ?? "?")}: ${problem}`);
      continue;
    }
    const id = String(item.id).trim();
    if (seen.has(id)) {
      problems.push(`ítem ${JSON.stringify(id)}: id repetit`);
      continue;
    }
    seen.add(id);
    words.push({ id, prompt: String(item.prompt).trim(), target: strings(item.answer) });
  }
  return { words, problems };
}

/** Every problem of one math list file (empty when it is a valid math list). */
export function mathListProblems(raw: JsonRecord): string[] {
  if ("generate" in raw && "items" in raw) return ["té generate i items: en cal un de sol"];
  if (!("generate" in raw) && !("items" in raw)) return ["no té ni generate ni items"];
  const { words, problems } = mathWords(raw);
  return words.length || problems.length ? problems : ["no té cap ítem"];
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

// ---- progress (docs/ENCARREC-FLASH-v1.md) -------------------------------------
// data/flash-db.json: the learner's Flash progress, on the server so the level
// test can read it (hooks/curriculum.py flash_progress reads the same file).
// Nothing else here writes to the learner's databases.

export const FLASH_DB_FILE = "flash-db.json";

export interface FlashWordState {
  box: number; // 0..2; 2 = known (sabuda)
  seen: number;
  first_try: number;
  misses: number;
  last: string | null;
}

export interface FlashListState {
  words: Record<string, FlashWordState>;
  closed_at: string | null;
}

export interface FlashState {
  version: 1;
  lists: Record<string, FlashListState>;
  rounds_by_day: Record<string, number>;
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

function count(value: unknown): number | null {
  return Number.isInteger(value) && (value as number) >= 0 ? (value as number) : null;
}

function day(value: unknown): string | null {
  return typeof value === "string" && DAY.test(value) ? value : null;
}

export function emptyFlashState(): FlashState {
  return { version: 1, lists: {}, rounds_by_day: {} };
}

/** Keeps what fits the shape and drops the rest: an unknown list id, a word
 *  whose box is outside 0..2, or any field of the wrong type. A body that is
 *  not a state at all gives an empty state. */
export function sanitizeFlashState(raw: unknown, knownListIds: ReadonlySet<string>): FlashState {
  const out = emptyFlashState();
  const body = asRecord(raw);
  if (body.version !== 1) return out;
  for (const [listId, entry] of Object.entries(asRecord(body.lists))) {
    if (!knownListIds.has(listId)) continue;
    const e = asRecord(entry);
    const words: Record<string, FlashWordState> = {};
    for (const [wordId, w] of Object.entries(asRecord(e.words))) {
      const r = asRecord(w);
      const box = Number.isInteger(r.box) && (r.box as number) >= 0 && (r.box as number) <= 2 ? (r.box as number) : null;
      const seen = count(r.seen);
      const firstTry = count(r.first_try);
      const misses = count(r.misses);
      const last = r.last === null ? null : day(r.last);
      if (box === null || seen === null || firstTry === null || misses === null || (r.last !== null && last === null)) continue;
      words[wordId] = { box, seen, first_try: firstTry, misses, last };
    }
    out.lists[listId] = { words, closed_at: day(e.closed_at) };
  }
  for (const [d, n] of Object.entries(asRecord(body.rounds_by_day))) {
    const c = count(n);
    if (day(d) && c !== null) out.rounds_by_day[d] = c;
  }
  return out;
}

/** The ids of the lists the profile's domain runs (none when Flash is off there). */
export function flashListIds(root: string, dataDir: string): Set<string> {
  const profile = readJson(path.join(dataDir, "learner-profile.json"));
  const cfg = flashConfig(readJson(path.join(root, "config", "domain.json")), profileDomain(profile));
  if (!cfg.enabled || !cfg.dir) return new Set();
  return new Set(loadFlashLists(root, cfg.dir, "ca").map((l) => l.id));
}

/** The stored progress, or an empty one when there is no file (or it does not read). */
export function readFlashState(root: string, dataDir: string): FlashState {
  let raw: unknown = null;
  try {
    raw = JSON.parse(fs.readFileSync(path.join(dataDir, FLASH_DB_FILE), "utf8"));
  } catch {
    raw = null;
  }
  return sanitizeFlashState(raw, flashListIds(root, dataDir));
}

/** Writes the whole state atomically: a temporary file, then rename. */
export function writeFlashState(dataDir: string, state: FlashState): void {
  fs.mkdirSync(dataDir, { recursive: true });
  const file = path.join(dataDir, FLASH_DB_FILE);
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(state, null, 1), "utf8");
  fs.renameSync(tmp, file);
}

/** GET /api/flash/state. Flash off for the profile gives an empty state. */
export function flashStateResponse(root: string, dataDir: string): JsonRecord {
  const profile = readJson(path.join(dataDir, "learner-profile.json"));
  const cfg = flashConfig(readJson(path.join(root, "config", "domain.json")), profileDomain(profile));
  if (!cfg.enabled || !cfg.dir) return { ok: true, enabled: false, state: emptyFlashState() };
  return { ok: true, enabled: true, state: readFlashState(root, dataDir) };
}

/** PUT /api/flash/state. Returns the status and the body to send. Refused (and
 *  nothing written) when Flash is off for the profile or the body is not an object. */
export function saveFlashState(root: string, dataDir: string, body: unknown): { status: number; body: JsonRecord } {
  const profile = readJson(path.join(dataDir, "learner-profile.json"));
  const cfg = flashConfig(readJson(path.join(root, "config", "domain.json")), profileDomain(profile));
  if (!cfg.enabled || !cfg.dir) return { status: 404, body: { ok: false, error: "Flash no està activat per a aquest perfil" } };
  if (!body || typeof body !== "object" || Array.isArray(body) || (body as JsonRecord).version !== 1) {
    return { status: 400, body: { ok: false, error: "cal un objecte JSON amb l'estat de Flash (versió 1)" } };
  }
  const state = sanitizeFlashState(body, flashListIds(root, dataDir));
  writeFlashState(dataDir, state);
  return { status: 200, body: { ok: true, state } };
}
