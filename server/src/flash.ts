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
  answer_kind?: AnswerKind; // math only (always sent for math)
  unit?: string; // math, unit kind: shown outside the box
  options?: string[]; // math, choice kind: the buttons
  form?: "value" | "simplest"; // math, fraction kind
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
        ? mathWords(raw).words.map(mathView)
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

/** A math word as the client gets it: the prompt is shown and answered as its own native line, and the
 *  answer kind decides the card (number by default). */
function mathView(w: MathWord): FlashWordView {
  const kind = w.answer_kind ?? "number";
  const v: FlashWordView = { id: w.id, target: w.target, native: [w.prompt], prompt: w.prompt, answer_kind: kind };
  if (w.unit) v.unit = w.unit;
  if (kind === "choice") v.options = w.options ?? [];
  if (kind === "fraction") v.form = w.form ?? "value";
  return v;
}

// ---- math lists (docs/ENCARREC-FLASH-MATH.md, docs/ENCARREC-M5-E1-FLASH.md) -----
// `generate` with no kind (or "op"): the server works out every operation and its result.
// `generate` with a kind (E1 §3): `count` words from a seeded generator, ids g1…gN.
// `items`: hand-written, each checked (its own sum, its answer kind); a wrong one is dropped.
// Every math word: target = the answer(s), native = [prompt], prompt = what the card shows,
// answer_kind = number | fraction | unit | choice, plus unit / options / form as the kind needs.
// hooks/curriculum.py flash_lists mirrors these rules: the same ids, the same drops.

export type MathOp = "+" | "−" | "×" | ":";
export type AnswerKind = "number" | "fraction" | "unit" | "choice";
const ANSWER_KINDS: readonly string[] = ["number", "fraction", "unit", "choice"];

const MATH_OP = new Map<string, MathOp>([
  ["+", "+"], ["−", "−"], ["-", "−"], ["×", "×"], ["x", "×"], ["*", "×"], [":", ":"], ["/", ":"],
]);
const MATH_OP_ID = new Map<MathOp, string>([["+", "p"], ["−", "m"], ["×", "x"], [":", "d"]]);
const MATH_RANGE_MAX = 1000; // a {from, to} range never holds more than this

export interface MathWord {
  id: string;
  prompt: string;
  target: string[];
  answer_kind?: AnswerKind; // absent = number
  unit?: string; // unit: the unit shown outside the box
  options?: string[]; // choice: the buttons
  form?: "value" | "simplest"; // fraction: equivalents count, or only the irreducible form
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

/** Every a op b of an op `generate` block, in order (a outer, b inner). Results that are not whole and ≥ 0
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

// ---- fractions (answer_kind fraction) -------------------------------------------

export interface Fraction {
  num: number;
  den: number; // > 0
}

const FRAC_PLAIN = /^(-?)(\d+)\s*\/\s*(\d+)$/;
const FRAC_MIXED = /^(-?)(\d+)\s+(\d+)\s*\/\s*(\d+)$/;
const FRAC_DEC = /^(-?)(\d+)[,.](\d+)$/;
const FRAC_INT = /^(-?)(\d+)$/;

/** A fraction written n/d, as a mixed number (1 1/2), a whole number or a decimal (0,25). Null when it is
 *  none of these, or the denominator is 0. */
export function parseFraction(s: unknown): Fraction | null {
  const t = String(s ?? "").trim();
  let m: RegExpExecArray | null;
  if ((m = FRAC_MIXED.exec(t))) {
    const den = Number(m[4]);
    if (den === 0) return null;
    const sign = m[1] ? -1 : 1;
    return { num: sign * (Number(m[2]) * den + Number(m[3])), den };
  }
  if ((m = FRAC_PLAIN.exec(t))) {
    const den = Number(m[3]);
    if (den === 0) return null;
    return { num: (m[1] ? -1 : 1) * Number(m[2]), den };
  }
  if ((m = FRAC_DEC.exec(t))) {
    const frac = m[3] ?? "";
    return { num: (m[1] ? -1 : 1) * Number(String(m[2]) + frac), den: 10 ** frac.length };
  }
  if ((m = FRAC_INT.exec(t))) return { num: (m[1] ? -1 : 1) * Number(m[2]), den: 1 };
  return null;
}

export function gcd(a: number, b: number): number {
  let x = Math.abs(a);
  let y = Math.abs(b);
  while (y) [x, y] = [y, x % y];
  return x;
}

/** The irreducible form as text: an integer when the value is whole, else n/d or a mixed number whose
 *  fraction part is reduced and proper. Decimals do not count. */
export function isSimplestText(s: unknown): boolean {
  const t = String(s ?? "").trim();
  const f = parseFraction(t);
  if (!f) return false;
  if (f.num % f.den === 0) return /^-?\d+$/.test(t);
  if (FRAC_DEC.test(t)) return false;
  const m = FRAC_MIXED.exec(t);
  if (m) {
    const r = Number(m[3]);
    const d = Number(m[4]);
    return r > 0 && r < d && gcd(r, d) === 1;
  }
  return gcd(f.num, f.den) === 1;
}

/** `n/d` as the lists write a fraction: a whole number when it divides, else `n/d` unsimplified. */
function fracText(num: number, den: number): string {
  return num % den === 0 ? String(num / den) : `${num}/${den}`;
}

// ---- generators (docs/ENCARREC-M5-E1-FLASH.md §3) ----------------------------------

type Rng = () => number;
type Params = JsonRecord;
interface GenItem {
  prompt: string;
  target: string[];
  answer_kind?: AnswerKind;
  unit?: string;
  options?: string[];
  form?: "value" | "simplest";
}
type Generator = (r: Rng, p: Params) => GenItem | null;

export const GEN_COUNT_DEFAULT = 12;
export const GEN_COUNT_MAX = 50;

/** FNV-1a, 32 bits, of the UTF-8 bytes of the text. */
export function fnv1a(text: string): number {
  let h = 0x811c9dc5;
  for (const b of new TextEncoder().encode(text)) h = Math.imul(h ^ b, 0x01000193) >>> 0;
  return h >>> 0;
}

/** mulberry32: a seeded stream of floats in [0, 1). Only chooses which numbers appear, never a result. */
export function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Whole numbers lo..hi, both ends included, from the stream. */
function int(r: Rng, lo: number, hi: number): number {
  return lo + Math.floor(r() * (hi - lo + 1));
}

function pick<T>(r: Rng, xs: readonly T[]): T {
  return xs[Math.floor(r() * xs.length)] as T;
}

/** An optional whole-number parameter in lo..hi, else the default. */
function paramInt(p: Params, key: string, def: number, lo: number, hi: number): number {
  const v = p[key];
  return Number.isInteger(v) && (v as number) >= lo && (v as number) <= hi ? (v as number) : def;
}

/** An optional list of whole numbers in lo..hi, else the default. */
function paramList(p: Params, key: string, def: number[], lo: number, hi: number): number[] {
  const v = p[key];
  if (!Array.isArray(v)) return def;
  const out = v.filter((x): x is number => Number.isInteger(x) && x >= lo && x <= hi);
  return out.length ? out : def;
}

/** 4735218 → "4.735.218" (screen only). */
function thousands(n: number): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** An integer scaled by 10^-decs, written with a comma and no trailing zeros: (235, 2) → "2,35", (940, 2) → "9,4". */
export function decComma(numer: number, decs: number): string {
  if (decs <= 0) return String(numer);
  const s = String(Math.abs(numer)).padStart(decs + 1, "0");
  const int_ = s.slice(0, -decs);
  const frac = s.slice(-decs).replace(/0+$/, "");
  return (numer < 0 ? "-" : "") + int_ + (frac ? `,${frac}` : "");
}

function fracItem(prompt: string, num: number, den: number, form: "value" | "simplest" = "value"): GenItem {
  return { prompt, target: [fracText(num, den)], answer_kind: "fraction", form };
}

const PLACES: ReadonlyArray<[number, string]> = [[10, "desena"], [100, "centena"], [1000, "unitat de miler"]];
const LADDERS: Record<string, Array<[string, number]>> = {
  length: [["km", 3], ["m", 0], ["dm", -1], ["cm", -2], ["mm", -3]],
  mass: [["kg", 3], ["g", 0], ["mg", -3]],
  capacity: [["kl", 3], ["l", 0], ["dl", -1], ["ml", -3]],
};
const PAIRS: ReadonlyArray<[string, string, number, number]> = [["m", "cm", 100, 99], ["kg", "g", 1000, 999], ["l", "ml", 1000, 999]];

const GENERATORS = new Map<string, Generator>([
  ["round", (r, p) => {
    const d = int(r, 4, paramInt(p, "digits", 7, 4, 7));
    const n = int(r, 10 ** (d - 1), 10 ** d - 1);
    const [place, name] = pick(r, PLACES);
    if (n % place === 0) return null;
    return { prompt: `Arrodoneix ${thousands(n)} a la ${name}`, target: [String(Math.floor((n + place / 2) / place) * place)] };
  }],
  ["digit_value", (r, p) => {
    const d = int(r, 5, paramInt(p, "digits", 7, 5, 7));
    const n = int(r, 10 ** (d - 1), 10 ** d - 1);
    const s = String(n);
    const i = int(r, 0, s.length - 1);
    const c = s[i] ?? "";
    if (c === "" || c === "0" || s.split(c).length !== 2) return null; // the digit must appear once, and not be a zero
    return { prompt: `Quin valor té el ${c} a ${thousands(n)}?`, target: [String(Number(c) * 10 ** (s.length - 1 - i))] };
  }],
  ["compare_numbers", (r, p) => {
    const d = int(r, 4, paramInt(p, "digits", 7, 4, 7));
    const lo = 10 ** (d - 1);
    const hi = 10 ** d - 1;
    const a = int(r, lo, hi);
    let b: number;
    if (r() < 0.1) b = a; // about one in ten is an equality
    else if (r() < 0.5) {
      b = a + int(r, -99999, 99999); // a close pair is the useful one
      if (b < lo || b > hi || b === a) return null;
    } else {
      b = int(r, lo, hi);
      if (b === a) return null;
    }
    const rel = a < b ? "<" : a > b ? ">" : "=";
    return { prompt: `${thousands(a)} ? ${thousands(b)}`, target: [rel], answer_kind: "choice", options: ["<", ">", "="] };
  }],
  ["frac_of", (r, p) => {
    const den = pick(r, paramList(p, "dens", [2, 3, 4, 5, 6, 8, 10], 2, 12));
    const num = int(r, 1, den - 1);
    const k = int(r, 2, 25);
    return { prompt: `${num}/${den} de ${den * k}`, target: [String(num * k)] };
  }],
  ["frac_equiv", (r, p) => {
    const den = pick(r, paramList(p, "dens", [2, 3, 4, 5, 6, 7, 8, 9, 10], 2, 12));
    const num = int(r, 1, den - 1);
    const m = int(r, 2, 6);
    return { prompt: `${num}/${den} = ?/${den * m}`, target: [String(num * m)] };
  }],
  ["frac_same_den", (r, p) => {
    const den = pick(r, paramList(p, "dens", [2, 3, 4, 5, 6, 7, 8, 9, 10, 12], 2, 12));
    const a = int(r, 1, den - 1);
    const b = int(r, 1, den - 1);
    if (r() < 0.5) return fracItem(`${a}/${den} + ${b}/${den}`, a + b, den);
    if (a === b) return null;
    return fracItem(`${Math.max(a, b)}/${den} − ${Math.min(a, b)}/${den}`, Math.max(a, b) - Math.min(a, b), den);
  }],
  ["frac_dec", (r) => {
    const k = int(r, 1, 3);
    const den = 10 ** k;
    const num = int(r, 1, den - 1);
    if (r() < 0.5) return { prompt: `${num}/${den} = ?`, target: [decComma(num, k)] };
    return { prompt: `${decComma(num, k)} = ?/${den}`, target: [String(num)] };
  }],
  ["dec_times_int", (r, p) => {
    const k = int(r, 1, paramInt(p, "decimals", 3, 1, 3));
    const m = int(r, 11, 999);
    if (m % 10 === 0) return null; // the last decimal is not a zero
    const f = int(r, 2, 9);
    return { prompt: `${decComma(m, k)} × ${f}`, target: [decComma(m * f, k)] };
  }],
  ["percent_of", (r, p) => {
    const pct = pick(r, paramList(p, "percents", [10, 25, 50, 75], 1, 99));
    const base = (100 / gcd(pct, 100)) * int(r, 2, 30); // the base makes the result whole
    return { prompt: `${pct} % de ${base}`, target: [String((pct * base) / 100)] };
  }],
  ["divisible", (r, p) => {
    const d = pick(r, paramList(p, "divisors", [2, 3, 5, 10], 2, 12));
    const yes = r() < 0.5;
    const n = int(r, 11, 999);
    if ((n % d === 0) !== yes) return null;
    return { prompt: `És ${n} divisible per ${d}?`, target: [yes ? "Sí" : "No"], answer_kind: "choice", options: ["Sí", "No"] };
  }],
  ["combined", (r) => {
    const a = int(r, 2, 20);
    const b = int(r, 2, 12);
    const c = int(r, 2, 9);
    const a2 = int(r, 2, 60);
    const q = int(r, 2, 9);
    const one = (prompt: string, v: number): GenItem => ({ prompt, target: [String(v)] });
    switch (int(r, 0, 9)) {
      case 0: return one(`${a} + ${b} × ${c}`, a + b * c);
      case 1: return one(`${a} × ${b} + ${c}`, a * b + c);
      case 2: return a >= b * c ? one(`${a} − ${b} × ${c}`, a - b * c) : null;
      case 3: return a * b >= c ? one(`${a} × ${b} − ${c}`, a * b - c) : null;
      case 4: return one(`(${a} + ${b}) × ${c}`, (a + b) * c);
      case 5: return a > b ? one(`(${a} − ${b}) × ${c}`, (a - b) * c) : null;
      case 6: return one(`${a} × (${b} + ${c})`, a * (b + c));
      case 7: return a2 >= c * q ? one(`${a2} − ${c * q} : ${c}`, a2 - q) : null;
      case 8: return one(`${a2} + ${c * q} : ${c}`, a2 + q);
      default: {
        const total = c * q;
        return b < total ? one(`(${total - b} + ${b}) : ${c}`, q) : null;
      }
    }
  }],
  ["unit_convert", (r) => {
    const ladder = LADDERS[pick(r, Object.keys(LADDERS))] ?? [];
    const i = int(r, 0, ladder.length - 1);
    let j = int(r, 0, ladder.length - 2);
    if (j >= i) j += 1;
    const [ua, ea] = ladder[i] ?? ["", 0];
    const [ub, eb] = ladder[j] ?? ["", 0];
    const k = int(r, 0, 2);
    const m = k === 0 ? int(r, 1, 99) : int(r, 11, 999);
    if (k > 0 && m % 10 === 0) return null;
    const e = ea - eb - k; // value in ub = m × 10^e
    if (e < -3) return null; // at most three decimals in the answer
    const target = e >= 0 ? decComma(m * 10 ** e, 0) : decComma(m, -e);
    return { prompt: `${decComma(m, k)} ${ua} = ? ${ub}`, target: [target], answer_kind: "unit", unit: ub };
  }],
  ["complex_to_simple", (r) => {
    const [big, small, f, max] = pick(r, PAIRS);
    const b = int(r, 1, 9);
    const s = int(r, 1, max);
    return { prompt: `${b} ${big} ${s} ${small} = ? ${small}`, target: [String(b * f + s)], answer_kind: "unit", unit: small };
  }],
  ["time_convert", (r) => {
    if (r() < 0.5) {
      const h = int(r, 1, 5);
      const mi = int(r, 1, 59);
      return { prompt: `${h} h ${mi} min = ? min`, target: [String(h * 60 + mi)], answer_kind: "unit", unit: "min" };
    }
    const mi = int(r, 1, 5);
    const s = int(r, 1, 59);
    return { prompt: `${mi} min ${s} s = ? s`, target: [String(mi * 60 + s)], answer_kind: "unit", unit: "s" };
  }],
  ["area_simple", (r) => {
    if (r() < 0.5) {
      const a = int(r, 2, 20);
      const b = int(r, 2, 20);
      return { prompt: `Rectangle de ${a} cm × ${b} cm. Àrea?`, target: [String(a * b)], answer_kind: "unit", unit: "cm²" };
    }
    const base = int(r, 2, 20);
    const h = 2 * int(r, 1, 10); // even, so base × height / 2 is whole
    return { prompt: `Triangle: base ${base} cm, altura ${h} cm. Àrea?`, target: [String((base * h) / 2)], answer_kind: "unit", unit: "cm²" };
  }],
  ["mean", (r, p) => {
    const count = int(r, 4, paramInt(p, "values", 6, 4, 6));
    const mu = int(r, 2, 20);
    const vals: number[] = [];
    for (let i = 0; i < count - 1; i++) vals.push(int(r, 1, 20));
    const last = count * mu - vals.reduce((x, y) => x + y, 0);
    if (last < 1 || last > 30) return null;
    vals.push(last);
    return { prompt: `Mitjana de ${vals.join(", ")}`, target: [String(mu)] };
  }],
  ["probability", (r) => {
    const t = int(r, 0, 2);
    if (t === 0) {
      const k = int(r, 2, 5);
      const j = int(r, 3, 5);
      const faces: Array<[string, number]> = [
        ["un nombre parell", 3],
        ["un nombre senar", 3],
        ["un múltiple de 3", 2],
        [`un nombre més gran que ${k}`, 6 - k],
        [`un nombre més petit que ${j}`, j - 1],
      ];
      const [text, fav] = pick(r, faces);
      return fracItem(`Dau de 6 cares: probabilitat de treure ${text}?`, fav, 6);
    }
    if (t === 1) return fracItem("Moneda: probabilitat de treure cara?", 1, 2);
    const red = int(r, 1, 9);
    const blue = int(r, 1, 9);
    return fracItem(`Bossa amb ${red} boles vermelles i ${blue} de blaves. Probabilitat de treure una vermella?`, red, red + blue);
  }],
  ["equation", (r) => {
    const x = int(r, 1, 20);
    const t = int(r, 0, 2);
    if (t === 0) {
      const a = int(r, 2, 9);
      const b = int(r, 1, 20);
      return { prompt: `${a}·x + ${b} = ${a * x + b}. x = ?`, target: [String(x)] };
    }
    if (t === 1) {
      const a = int(r, 2, 9);
      const b = int(r, 1, 20);
      if (a * x <= b) return null; // the right side stays positive
      return { prompt: `${a}·x − ${b} = ${a * x - b}. x = ?`, target: [String(x)] };
    }
    const b = int(r, 1, 20);
    return { prompt: `x + ${b} = ${x + b}. x = ?`, target: [String(x)] };
  }],
  ["sequence", (r) => {
    const t = int(r, 0, 2);
    const terms: number[] = [];
    if (t === 0) {
      const s = int(r, 1, 30);
      const d = int(r, 2, 12);
      for (let i = 0; i < 5; i++) terms.push(s + i * d);
    } else if (t === 1) {
      const s = int(r, 40, 99);
      const d = int(r, 2, 9);
      for (let i = 0; i < 5; i++) terms.push(s - i * d);
    } else {
      const s = int(r, 1, 5);
      const q = pick(r, [2, 3]);
      for (let i = 0; i < 5; i++) terms.push(s * q ** i);
    }
    return { prompt: `${terms.slice(0, 4).join(", ")}, ?`, target: [String(terms[4])] };
  }],
]);

/** The generator kinds a `generate` block may name (besides `op`). */
export const GEN_KINDS: readonly string[] = [...GENERATORS.keys()];

/** The count of a generated list: an integer from 1 to 50, default 12 when it is not a whole number. */
export function genCount(v: unknown): number {
  return Number.isInteger(v) ? Math.min(GEN_COUNT_MAX, Math.max(1, v as number)) : GEN_COUNT_DEFAULT;
}

/** The words of a generated list: `count` distinct prompts, ids g1…gN. Seeded by the list id, so the same
 *  list always gives the same words. Fewer than `count` only when the parameters leave too little room. */
export function generatedWords(listId: string, gen: JsonRecord): MathWord[] {
  const make = GENERATORS.get(String(gen.kind));
  if (!make) return [];
  const count = genCount(gen.count);
  const rng = mulberry32(fnv1a(listId));
  const params = asRecord(gen.params);
  const out: MathWord[] = [];
  const seen = new Set<string>();
  for (let tries = 0; out.length < count && tries < count * 200; tries++) {
    const item = make(rng, params);
    if (!item || seen.has(item.prompt)) continue;
    seen.add(item.prompt);
    out.push({ id: `g${out.length + 1}`, ...item });
  }
  return out;
}

/** The kind of a `generate` block: "op" when it is absent, null or "op"; else the kind as written. */
function generateKind(gen: JsonRecord): unknown {
  return gen.kind === undefined || gen.kind === null || gen.kind === "op" ? "op" : gen.kind;
}

/** The answer kind of an explicit item, or null when it names none that exists. */
function itemKind(item: JsonRecord): string | null {
  if (item.answer_kind === undefined) return "number";
  return typeof item.answer_kind === "string" && ANSWER_KINDS.includes(item.answer_kind) ? item.answer_kind : null;
}

/** Why an explicit item is wrong, or null when it is fine. A simple operation's answer must be its result. */
function itemProblem(item: JsonRecord): string | null {
  if (typeof item.id !== "string" || !item.id.trim()) return "sense id";
  if (typeof item.prompt !== "string" || !item.prompt.trim()) return "sense enunciat";
  const answer = strings(item.answer);
  if (!answer.length) return "sense resultat";
  const kind = itemKind(item);
  if (kind === null) return `answer_kind desconegut (${JSON.stringify(item.answer_kind)})`;
  if (kind === "choice") {
    const options = strings(item.options);
    if (options.length < 2) return "choice sense almenys dues opcions";
    if (!options.includes(answer[0] ?? "")) return `${answer[0]} no és una de les opcions`;
  }
  if (kind === "fraction") {
    if (!parseFraction(answer[0])) return `${answer[0]} no és una fracció`;
    if (item.form === "simplest" && !isSimplestText(answer[0])) return `${answer[0]} no és la fracció irreductible`;
  }
  if (kind === "unit" && (typeof item.unit !== "string" || !item.unit.trim())) return "unit sense text";
  if (kind === "number" || kind === "unit") {
    const sop = simpleOp(item.prompt);
    if (sop) {
      const r = opResult(sop.a, sop.op, sop.b);
      if (r === null) return `${item.prompt} no dona un resultat enter ≥ 0`;
      if (numericValue(answer[0]) !== r) return `${item.prompt} és ${r}, no ${answer[0]}`;
    }
  }
  return null;
}

/** An explicit item as a word (its kind's fields only). */
function itemWord(item: JsonRecord, id: string): MathWord {
  const kind = itemKind(item) ?? "number";
  const w: MathWord = { id, prompt: String(item.prompt).trim(), target: strings(item.answer), answer_kind: kind as AnswerKind };
  if (kind === "unit") w.unit = String(item.unit).trim();
  if (kind === "choice") w.options = strings(item.options);
  if (kind === "fraction") w.form = item.form === "simplest" ? "simplest" : "value";
  return w;
}

/** The words of a math list, and what was left out of it (for the test that checks the lists). */
export function mathWords(raw: JsonRecord): { words: MathWord[]; problems: string[] } {
  if ("generate" in raw) {
    const gen = asRecord(raw.generate);
    const kind = generateKind(gen);
    if (kind === "op") {
      const words = expandGenerate(raw.generate);
      const problems = normalizeOp(gen.op) ? [] : ["generate: op desconegut"];
      if (!words.length) problems.push("generate: no genera cap operació");
      return { words, problems };
    }
    if (typeof kind !== "string" || !GENERATORS.has(kind)) {
      return { words: [], problems: [`generate: kind desconegut (${JSON.stringify(kind)})`] };
    }
    const words = generatedWords(String(raw.id ?? ""), gen);
    return { words, problems: words.length ? [] : ["generate: no genera cap ítem"] };
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
    words.push(itemWord(item, id));
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
