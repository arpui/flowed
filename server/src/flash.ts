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
  mode?: SexaMode; // math, sexagesimal kind: the notation of the answer (time or angle)
  figure?: Figure; // math: drawn as SVG above the prompt (docs/ENCARREC-M5-E3-FIGURES.md)
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
  if (w.figure) v.figure = w.figure;
  if (w.mode) v.mode = w.mode;
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
export type AnswerKind = "number" | "fraction" | "unit" | "choice" | "pair" | "factorization" | "algebraic" | "sexagesimal";
const ANSWER_KINDS: readonly string[] = ["number", "fraction", "unit", "choice", "pair", "factorization", "algebraic", "sexagesimal"];

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
  figure?: Figure; // a figure above the prompt (checked by checkFigure)
  mode?: SexaMode; // sexagesimal: time or angle
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
  const t = String(s ?? "").replace(/\s+/g, "").replace(/−/g, "-").replace(/,/g, ".");
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
  const t = String(s ?? "").trim().replace(/−/g, "-");
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
  const t = String(s ?? "").trim().replace(/−/g, "-");
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

// ---- answer kinds of m7 (docs/ENCARREC-M7-E5-FLASH.md §2) -------------------------
// factorization: the prime factors with multiplicity (2^3·3^2·5, 2·2·2·3·3·5; ·, *, x, × or a space between factors).
// algebraic: the rules of hooks/mathgrade.py parse_poly (_normalize_alg, _poly_eval): sums of monomials, integer or
// fraction coefficients, single-letter variables, powers ^n, ² ³ ⁴ (exponent 1..6), implicit product, · * /
// (division by a nonzero number only). Equal when the expanded forms are equal. Number notation is the common subset:
// no underscores, no exponent notation (1e5).
// sexagesimal: a time (h, min, s; h:mm, h:mm:ss) or an angle (°, ', ''; º and typographic quotes too), compared in
// seconds. Minutes and seconds must be below 60 (1 h 75 min is not normalized).

export type SexaMode = "time" | "angle";

const SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹";

/** Whether n is a prime number (n ≥ 2). */
function isPrime(n: number): boolean {
  if (!Number.isInteger(n) || n < 2) return false;
  for (let d = 2; d * d <= n; d++) if (n % d === 0) return false;
  return true;
}

/** The prime factors of a factorization as a map prime → count, or a problem (a factor that is not prime, or
 *  a text that is not a factorization). `1` is no factor. */
export function factorization(s: unknown): { factors: Map<number, number> } | { problem: string } {
  const t = String(s ?? "").trim();
  if (!t) return { problem: "buit" };
  const factors = new Map<number, number>();
  for (const tok of t.split(/\s*[·*x×]\s*|\s+/).filter((x) => x.length > 0)) {
    const m = /^(\d+)(?:\^(\d+)|([⁰¹²³⁴⁵⁶⁷⁸⁹]+))?$/.exec(tok);
    if (!m) return { problem: `${tok} no és un factor` };
    const p = Number(m[1]);
    if (!isPrime(p)) return { problem: `${p} no és primer` };
    let e = 1;
    if (m[2] !== undefined) e = Number(m[2]);
    else if (m[3] !== undefined) e = [...m[3]].reduce((acc, c) => acc * 10 + SUPERSCRIPT_DIGITS.indexOf(c), 0);
    if (e < 1) return { problem: `${tok}: l'exponent ha de ser ≥ 1` };
    factors.set(p, (factors.get(p) ?? 0) + e);
  }
  return { factors };
}

/** The canonical text of a factorization: [[2, 3], [3, 2], [5, 1]] → "2^3·3^2·5". */
export function factorText(f: Array<[number, number]>): string {
  return f.map(([p, e]) => (e > 1 ? `${p}^${e}` : `${p}`)).join("·");
}

/** The prime factors of n with multiplicity, as [prime, count] pairs in order. */
export function primeFactorList(n: number): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  let m = n;
  for (let p = 2; p * p <= m; p++) {
    let e = 0;
    while (m % p === 0) {
      m /= p;
      e++;
    }
    if (e > 0) out.push([p, e]);
  }
  if (m > 1) out.push([m, 1]);
  return out;
}

/** Two factorizations with the same primes and counts. */
export function sameFactors(a: Map<number, number>, b: Map<number, number>): boolean {
  if (a.size !== b.size) return false;
  for (const [p, e] of a) if (b.get(p) !== e) return false;
  return true;
}

class AlgebraError extends Error {}

/** A reduced rational with a positive denominator (bigint, so the expansion is exact). */
interface Rat {
  n: bigint;
  d: bigint;
}

function bigGcd(a: bigint, b: bigint): bigint {
  let x = a < 0n ? -a : a;
  let y = b < 0n ? -b : b;
  while (y) [x, y] = [y, x % y];
  return x;
}

function rat(n: bigint, d: bigint = 1n): Rat {
  if (d === 0n) throw new AlgebraError("division by zero");
  const sign = d < 0n ? -1n : 1n;
  const g = bigGcd(n, d) || 1n;
  return { n: (sign * n) / g, d: (sign * d) / g };
}

const ratAdd = (x: Rat, y: Rat): Rat => rat(x.n * y.d + y.n * x.d, x.d * y.d);
const ratMul = (x: Rat, y: Rat): Rat => rat(x.n * y.n, x.d * y.d);
const ratText = (x: Rat): string => (x.d === 1n ? String(x.n) : `${x.n}/${x.d}`);

/** A monomial: letters in alphabetical order with exponents ≥ 1 ([] is the constant 1). */
type Mono = Array<[string, number]>;
/** A polynomial: monomial key → term. The key is the letters and exponents ("x2y1"); "" is the constant. */
export type Poly = Map<string, { mono: Mono; c: Rat }>;

const monoKey = (m: Mono): string => m.map(([v, e]) => `${v}${e}`).join("");

function monoMul(a: Mono, b: Mono): Mono {
  const d = new Map<string, number>();
  for (const [v, e] of [...a, ...b]) d.set(v, (d.get(v) ?? 0) + e);
  return [...d.entries()].sort(([x], [y]) => (x < y ? -1 : x > y ? 1 : 0));
}

function polyConst(c: Rat): Poly {
  return c.n === 0n ? new Map() : new Map([["", { mono: [], c }]]);
}

function polyVar(v: string): Poly {
  return new Map([[monoKey([[v, 1]]), { mono: [[v, 1]], c: rat(1n) }]]);
}

function polyAdd(a: Poly, b: Poly, sign: 1n | -1n = 1n): Poly {
  const out: Poly = new Map(a);
  for (const [k, t] of b) {
    const cur = out.get(k);
    const c = ratAdd(cur ? cur.c : rat(0n), rat(sign * t.c.n, t.c.d));
    if (c.n === 0n) out.delete(k);
    else out.set(k, { mono: t.mono, c });
  }
  return out;
}

function polyMul(a: Poly, b: Poly): Poly {
  const out: Poly = new Map();
  for (const x of a.values()) {
    for (const y of b.values()) {
      const mono = monoMul(x.mono, y.mono);
      const k = monoKey(mono);
      const cur = out.get(k);
      const c = ratAdd(cur ? cur.c : rat(0n), ratMul(x.c, y.c));
      if (c.n === 0n) out.delete(k);
      else out.set(k, { mono, c });
    }
  }
  return out;
}

function polyScale(p: Poly, k: Rat): Poly {
  const out: Poly = new Map();
  for (const [key, t] of p) {
    const c = ratMul(t.c, k);
    if (c.n !== 0n) out.set(key, { mono: t.mono, c });
  }
  return out;
}

/** The value of a polynomial that is a nonzero constant, else null (a division or exponent needs one). */
function nonzeroConstant(p: Poly): Rat | null {
  if (p.size !== 1) return null;
  return p.get("")?.c ?? null;
}

/** The parse_poly normalization (hooks/mathgrade.py _normalize_alg): operator signs, superscripts, ^ as **, decimal
 *  comma, implicit product. A thousands separator is refused. */
function normalizeAlg(text: unknown): string {
  let s = String(text ?? "").trim();
  s = s.replace(/[×·∗⋅]/g, "*").replace(/[÷⁄]/g, "/").replace(/[−–—]/g, "-");
  s = s.replace(/²/g, "^2").replace(/³/g, "^3").replace(/⁴/g, "^4");
  s = s.replace(/\^/g, "**");
  s = s.replace(/(?<=\d),(?=\d)/g, ".");
  if (/\d{1,3}(?:\.\d{3}){2,}/.test(s)) throw new AlgebraError("thousand separators");
  s = s.replace(/(\d)\s*(?=[a-zA-Z(])/g, "$1*");
  s = s.replace(/([a-zA-Z)])\s*(?=\()/g, "$1*");
  s = s.replace(/([a-zA-Z)])\s*(?=[a-zA-Z(])/g, "$1*");
  return s.replace(/\s+/g, " ").trim();
}

type Tok = { t: "num"; v: Rat } | { t: "name"; v: string } | { t: "op"; v: string };

function decimalRat(text: string): Rat {
  const [whole = "", frac = ""] = text.split(".");
  return rat(BigInt((whole || "0") + frac), 10n ** BigInt(frac.length));
}

function tokenizeAlg(s: string): Tok[] {
  const out: Tok[] = [];
  let i = 0;
  while (i < s.length) {
    const ch = s[i] as string;
    if (ch === " ") {
      i++;
      continue;
    }
    const num = /^(\d+\.?\d*|\.\d+)/.exec(s.slice(i));
    if (num) {
      out.push({ t: "num", v: decimalRat(num[1] as string) });
      i += num[0].length;
    } else if (/^[a-zA-Z]$/.test(ch)) {
      out.push({ t: "name", v: ch });
      i++;
    } else if (s.startsWith("**", i)) {
      out.push({ t: "op", v: "**" });
      i += 2;
    } else if ("+-*/()".includes(ch)) {
      out.push({ t: "op", v: ch });
      i++;
    } else {
      throw new AlgebraError(`character ${ch}`);
    }
  }
  return out;
}

/** The expanded polynomial of an algebraic answer (parse_poly's rules), or null when it is not one. */
export function parsePoly(text: unknown): Poly | null {
  try {
    const s = normalizeAlg(text);
    if (!s) throw new AlgebraError("empty");
    const toks = tokenizeAlg(s);
    let pos = 0;
    const isOp = (v: string): boolean => {
      const t = toks[pos];
      return t !== undefined && t.t === "op" && t.v === v;
    };
    const expr = (): Poly => {
      let p = term();
      while (isOp("+") || isOp("-")) {
        const op = (toks[pos++] as { v: string }).v;
        p = polyAdd(p, term(), op === "+" ? 1n : -1n);
      }
      return p;
    };
    const term = (): Poly => {
      let p = factor();
      while (isOp("*") || isOp("/")) {
        const op = (toks[pos++] as { v: string }).v;
        const q = factor();
        if (op === "*") p = polyMul(p, q);
        else {
          const c = nonzeroConstant(q);
          if (c === null) throw new AlgebraError("divisor");
          p = polyScale(p, rat(c.d, c.n));
        }
      }
      return p;
    };
    const factor = (): Poly => {
      if (isOp("+") || isOp("-")) {
        const neg = (toks[pos++] as { v: string }).v === "-";
        const f = factor();
        return neg ? polyScale(f, rat(-1n)) : f;
      }
      return power();
    };
    const power = (): Poly => {
      const base = primary();
      if (!isOp("**")) return base;
      pos++;
      const e = nonzeroConstant(factor());
      if (e === null || e.d !== 1n || e.n < 1n || e.n > 6n) throw new AlgebraError("exponent");
      return polyPow(base, Number(e.n));
    };
    const primary = (): Poly => {
      const t = toks[pos++];
      if (!t) throw new AlgebraError("end");
      if (t.t === "num") return polyConst(t.v);
      if (t.t === "name") return polyVar(t.v);
      if (t.v !== "(") throw new AlgebraError("token");
      const p = expr();
      if (!isOp(")")) throw new AlgebraError("parenthesis");
      pos++;
      return p;
    };
    const result = expr();
    if (pos !== toks.length) throw new AlgebraError("trailing");
    return result;
  } catch (e) {
    if (e instanceof AlgebraError) return null;
    throw e;
  }
}

function polyPow(base: Poly, n: number): Poly {
  let out = polyConst(rat(1n));
  for (let i = 0; i < n; i++) out = polyMul(out, base);
  return out;
}

/** The canonical form of a polynomial: equal polynomials give equal keys. */
export function polyKey(p: Poly): string {
  return [...p.entries()]
    .map(([k, t]) => `${k}:${ratText(t.c)}`)
    .sort()
    .join("|");
}

/** Highest total degree of a polynomial (0 for a constant or 0). */
export function polyDegree(p: Poly): number {
  let d = 0;
  for (const t of p.values()) d = Math.max(d, t.mono.reduce((s, [, e]) => s + e, 0));
  return d;
}

/** Terms as parse_poly's report: monomial (x^2y, "" for the constant) → coefficient text. */
export function polyTerms(p: Poly): Record<string, string> {
  const out: Record<string, string> = {};
  for (const t of p.values()) {
    out[t.mono.map(([v, e]) => (e === 1 ? v : `${v}^${e}`)).join("")] = ratText(t.c);
  }
  return out;
}

/** The mode of a sexagesimal word: the one it names, else by its notation (° or ' means an angle). */
export function sexaMode(v: unknown, target: string): SexaMode {
  if (v === "time" || v === "angle") return v;
  return /[°']/.test(target) ? "angle" : "time";
}

/** A time or an angle written as the lists write it, as seconds. normalized is false when minutes or seconds
 *  are 60 or more. Null when the text is neither. */
export function parseSexa(s: unknown, mode: SexaMode): { seconds: number; normalized: boolean } | null {
  const t = String(s ?? "")
    .trim()
    .replace(/º/g, "°")
    .replace(/’’|′′|″|”|“/g, "''")
    .replace(/[′’‘]/g, "'")
    .replace(/\s+/g, " ");
  let m: RegExpExecArray | null;
  let a = 0;
  let b = 0;
  let c = 0;
  if (mode === "time") {
    if ((m = /^(\d+):(\d+)(?::(\d+))?$/.exec(t))) {
      a = Number(m[1]);
      b = Number(m[2]);
      c = m[3] === undefined ? 0 : Number(m[3]);
    } else if ((m = /^(?:(\d+) ?h)?(?: ?(\d+) ?min)?(?: ?(\d+) ?s)?$/i.exec(t)) && m.slice(1).some((x) => x !== undefined)) {
      a = Number(m[1] ?? 0);
      b = Number(m[2] ?? 0);
      c = Number(m[3] ?? 0);
    } else return null;
  } else {
    m = /^(\d+) ?°(?: ?(\d+) ?'(?: ?(\d+) ?'')?)?$/.exec(t);
    if (!m) return null;
    a = Number(m[1]);
    b = Number(m[2] ?? 0);
    c = Number(m[3] ?? 0);
  }
  return { seconds: a * 3600 + b * 60 + c, normalized: b < 60 && c < 60 };
}

// ---- figures (docs/ENCARREC-M5-E3-FIGURES.md §2–§4) ------------------------------
// A math word may carry a `figure`: the client draws it as inline SVG above the prompt, and nothing
// outside the list is needed. The server checks it (a bad one drops its word, as a bad item does) and
// returns the clean object with its defaults filled in. The drawing never shows the answer: an angle has
// no degrees unless `label`, and a circle's mark has no name on it.

export type CircleMark = "radius" | "diameter" | "chord" | "arc" | "center";
export type Figure =
  | { type: "angle"; deg: number; label: boolean }
  | { type: "triangle"; sides: number[]; labels: boolean; unit?: string }
  | { type: "polygon"; sides: number[]; regular: boolean; labels: boolean; unit?: string }
  | { type: "rect"; w: number; h: number; labels: boolean; unit?: string }
  | { type: "circle"; mark: CircleMark; rot: number }
  | { type: "bars"; labels: string[]; values: number[]; title?: string }
  | { type: "grid"; points: Array<[number, number]>; size?: number; min: number; max: number; line?: { m: number; n: number } }
  | { type: "parallels"; angle: number; known: number; ask: number }
  | { type: "right_triangle"; a: number; b: number; c: number; ask: "a" | "b" | "c"; unit?: string }
  | { type: "number_line"; min: number; max: number; point: number; label?: string };

export const CIRCLE_MARKS: readonly CircleMark[] = ["radius", "diameter", "chord", "arc", "center"];
export const CIRCLE_NAME: Record<CircleMark, string> = { radius: "radi", diameter: "diàmetre", chord: "corda", arc: "arc", center: "centre" };
export const ANGLE_NAMES: readonly string[] = ["agut", "recte", "obtús", "pla", "complet"];
export const TRIANGLE_NAMES: readonly string[] = ["equilàter", "isòsceles", "escalè"];
const FIGURE_TYPES: readonly string[] = ["angle", "triangle", "polygon", "rect", "circle", "bars", "grid", "parallels", "right_triangle", "number_line"];
const MAX_SIDE = 999;

/** An integer in lo..hi (7 and 7.0 both), or null. */
function intIn(v: unknown, lo: number, hi: number): number | null {
  const n = wholeNumber(v);
  return n !== null && n >= lo && n <= hi ? n : null;
}

/** Between lo and hi whole sides, each 1..999, or null. */
function sidesOf(v: unknown, lo: number, hi: number): number[] | null {
  if (!Array.isArray(v) || v.length < lo || v.length > hi) return null;
  const out: number[] = [];
  for (const x of v) {
    const n = intIn(x, 1, MAX_SIDE);
    if (n === null) return null;
    out.push(n);
  }
  return out;
}

/** Strict triangle inequality: the three sides close a triangle with an area. */
export function validTriangle(s: number[]): boolean {
  const [a = 0, b = 0, c = 0] = s;
  return a + b > c && a + c > b && b + c > a;
}

/** A triangle's name by its sides: all equal, two equal, or none. */
export function triangleKind(s: number[]): string {
  const distinct = new Set(s).size;
  return distinct === 1 ? "equilàter" : distinct === 2 ? "isòsceles" : "escalè";
}

/** The angle's name by its degrees (181..359 has none: it is not an option). */
export function angleName(deg: number): string | null {
  if (deg >= 1 && deg < 90) return "agut";
  if (deg === 90) return "recte";
  if (deg > 90 && deg < 180) return "obtús";
  if (deg === 180) return "pla";
  if (deg === 360) return "complet";
  return null;
}

/** An ordered pair written (3, 4), 3,4, 3 4 or (3 ; 4). Null when it is not one. Parentheses come in pairs. */
export function parsePair(s: unknown): [number, number] | null {
  const t = String(s ?? "").trim().replace(/−/g, "-");
  if (t.startsWith("(") !== t.endsWith(")")) return null;
  const m = /^\s*(-?[0-9]+)\s*(?:[,;]\s*|\s+)(-?[0-9]+)\s*$/.exec(t.startsWith("(") ? t.slice(1, -1) : t);
  return m ? [Number(m[1]), Number(m[2])] : null;
}

/** The figure as the client draws it, or why it is not one. */
export function checkFigure(raw: unknown): { figure: Figure } | { problem: string } {
  const f = asRecord(raw);
  const bad = (problem: string) => ({ problem });
  const unit = typeof f.unit === "string" && f.unit.trim() ? f.unit.trim() : null;
  const unitPart: { unit?: string } = unit === null ? {} : { unit };
  const labels = f.labels === true;
  const type = typeof f.type === "string" ? f.type : "";
  if (!FIGURE_TYPES.includes(type)) return bad(`tipus desconegut (${JSON.stringify(f.type)})`);
  switch (type) {
    case "angle": {
      const deg = intIn(f.deg, 1, 360);
      if (deg === null) return bad("angle: deg ha de ser un enter de 1 a 360");
      return { figure: { type: "angle", deg, label: f.label === true } };
    }
    case "triangle": {
      const sides = sidesOf(f.sides, 3, 3);
      if (!sides) return bad("triangle: cal 3 costats enters de 1 a 999");
      if (!validTriangle(sides)) return bad(`triangle: ${sides.join(", ")} no formen un triangle`);
      return { figure: { type: "triangle", sides, labels, ...unitPart } };
    }
    case "polygon": {
      const sides = sidesOf(f.sides, 3, 8);
      if (!sides) return bad("polygon: de 3 a 8 costats enters de 1 a 999");
      const regular = f.regular === true;
      if (regular && sides.some((x) => x !== sides[0])) return bad("polygon: regular però amb costats diferents");
      return { figure: { type: "polygon", sides, regular, labels, ...unitPart } };
    }
    case "rect": {
      const w = intIn(f.w, 1, MAX_SIDE);
      const h = intIn(f.h, 1, MAX_SIDE);
      if (w === null || h === null) return bad("rect: w i h han de ser enters de 1 a 999");
      return { figure: { type: "rect", w, h, labels, ...unitPart } };
    }
    case "circle": {
      const mark = CIRCLE_MARKS.find((m) => m === f.mark);
      if (!mark) return bad(`circle: mark desconegut (${JSON.stringify(f.mark)})`);
      const rot = f.rot === undefined ? 0 : intIn(f.rot, 0, 359);
      if (rot === null) return bad("circle: rot ha de ser un enter de 0 a 359");
      return { figure: { type: "circle", mark, rot } };
    }
    case "bars": {
      if (!Array.isArray(f.labels) || f.labels.length < 1 || f.labels.length > 8) return bad("bars: de 1 a 8 barres");
      const names = f.labels.map((x) => (typeof x === "string" ? x.trim() : ""));
      if (names.some((x) => !x)) return bad("bars: cada barra necessita una etiqueta");
      if (!Array.isArray(f.values) || f.values.length !== names.length) return bad("bars: values ha de tenir una xifra per barra");
      const values: number[] = [];
      for (const v of f.values) {
        const n = intIn(v, 0, MAX_SIDE);
        if (n === null) return bad("bars: values ha de ser enters ≥ 0");
        values.push(n);
      }
      const title = typeof f.title === "string" && f.title.trim() ? f.title.trim() : null;
      return { figure: { type: "bars", labels: names, values, ...(title === null ? {} : { title }) } };
    }
    case "parallels": {
      // E5 §3: the angle of the known place (20..160) and the places 1..8 of the known and the asked angle
      const angle = intIn(f.angle, 20, 160);
      const known = intIn(f.known, 1, 8);
      const ask = intIn(f.ask, 1, 8);
      if (angle === null || known === null || ask === null || known === ask) {
        return bad("parallels: angle de 20 a 160, known i ask diferents de 1 a 8");
      }
      return { figure: { type: "parallels", angle, known, ask } };
    }
    case "right_triangle": {
      const a = intIn(f.a, 1, MAX_SIDE);
      const b = intIn(f.b, 1, MAX_SIDE);
      const c = intIn(f.c, 1, MAX_SIDE);
      if (a === null || b === null || c === null) return bad("right_triangle: a, b i c han de ser enters de 1 a 999");
      if (a * a + b * b !== c * c) return bad(`right_triangle: ${a}, ${b}, ${c} no són un triangle rectangle`);
      if (f.ask !== "a" && f.ask !== "b" && f.ask !== "c") return bad("right_triangle: ask ha de ser a, b o c");
      return { figure: { type: "right_triangle", a, b, c, ask: f.ask, ...unitPart } };
    }
    case "number_line": {
      const min = intIn(f.min, -100, 100);
      const max = intIn(f.max, -100, 100);
      if (min === null || max === null || max <= min || max - min > 40) return bad("number_line: min < max, com a molt 40 unitats d'obertura");
      const point = intIn(f.point, min, max);
      if (point === null) return bad("number_line: point ha d'estar entre min i max");
      const label = typeof f.label === "string" && f.label.trim() ? f.label.trim().slice(0, 12) : null;
      return { figure: { type: "number_line", min, max, point, ...(label === null ? {} : { label }) } };
    }
    case "grid": {
      // E5 §3: the square from min to max (min ≤ 0 ≤ max, axes at 0; by default 0..10). A line y = m·x + n.
      const size = f.size === undefined ? null : intIn(f.size, 1, 10);
      if (f.size !== undefined && size === null) return bad("grid: size ha de ser un enter de 1 a 10");
      const min = f.min === undefined ? 0 : intIn(f.min, -10, 0);
      const max = f.max === undefined ? (size ?? 10) : intIn(f.max, 1, 10);
      if (min === null || max === null) return bad("grid: min de -10 a 0, max de 1 a 10");
      let line: { m: number; n: number } | undefined;
      if (f.line !== undefined) {
        const l = asRecord(f.line);
        const m = intIn(l.m, -9, 9);
        const n = intIn(l.n, min, max);
        if (m === null || n === null) return bad("grid: line ha de tenir m de -9 a 9 i n dins la graella");
        line = { m, n };
      }
      if (!Array.isArray(f.points) || f.points.length > 12 || (f.points.length < 1 && line === undefined)) {
        return bad("grid: de 1 a 12 punts (o una recta)");
      }
      const points: Array<[number, number]> = [];
      for (const p of f.points) {
        if (!Array.isArray(p) || p.length !== 2) return bad("grid: cada punt és [x, y]");
        const x = intIn(p[0], min, max);
        const y = intIn(p[1], min, max);
        if (x === null || y === null) return bad(`grid: el punt ha d'estar entre ${min} i ${max}`);
        points.push([x, y]);
      }
      // size is the old name of max for a grid from 0 (kept for it); a grid from below 0 has min and max only,
      // so the figure it gives is a figure its input would take again
      return { figure: { type: "grid", points, ...(min === 0 ? { size: max } : {}), min, max, ...(line === undefined ? {} : { line }) } };
    }
    default:
      return bad("tipus de figura no suportat");
  }
}

/** The places of a `parallels` figure where the angle equals the secant's own angle: 1 and 4 at the upper parallel,
 *  5 and 8 at the lower one (upper left and lower right). The others are its supplement. */
const PARALLEL_SAME: readonly number[] = [1, 4, 5, 8];

/** The degrees at place `ask`, when the place `known` has `angle` (corresponding angles are equal). */
export function parallelValue(angle: number, known: number, ask: number): number {
  const alpha = PARALLEL_SAME.includes(known) ? angle : 180 - angle;
  return PARALLEL_SAME.includes(ask) ? alpha : 180 - alpha;
}

/** Where a figure settles the answer, the answer must agree with it (E3 §4). Null when it agrees or the
 *  figure cannot tell (a question the figure does not settle). */
export function figureAnswerProblem(fig: Figure, prompt: string, kind: AnswerKind, answer: string[]): string | null {
  const a = answer[0] ?? "";
  if (fig.type === "angle" && kind === "choice" && ANGLE_NAMES.includes(a)) {
    const want = angleName(fig.deg);
    return want === a ? null : `la figura té ${fig.deg}°, no és ${a}`;
  }
  if (fig.type === "triangle" && kind === "choice" && TRIANGLE_NAMES.includes(a)) {
    const want = triangleKind(fig.sides);
    return want === a ? null : `els costats donen ${want}, no ${a}`;
  }
  if (fig.type === "circle" && kind === "choice" && Object.values(CIRCLE_NAME).includes(a)) {
    const want = CIRCLE_NAME[fig.mark];
    return want === a ? null : `la marca és ${want}, no ${a}`;
  }
  if (fig.type === "grid" && kind === "pair" && fig.points.length === 1) {
    const q = fig.points[0] ?? [0, 0];
    const p = parsePair(a);
    return p && p[0] === q[0] && p[1] === q[1] ? null : `el punt és (${q[0]}, ${q[1]})`;
  }
  const n = numericValue(a);
  if (n !== null && (kind === "number" || kind === "unit")) {
    if (fig.type === "rect" && /[àa]rea/i.test(prompt) && fig.w * fig.h !== n) return `l'àrea és ${fig.w * fig.h}`;
    if (/per[ií]metre/i.test(prompt)) {
      const per =
        fig.type === "rect" ? 2 * (fig.w + fig.h)
        : fig.type === "triangle" || fig.type === "polygon" ? fig.sides.reduce((x, y) => x + y, 0)
        : null;
      if (per !== null && per !== n) return `el perímetre és ${per}`;
    }
    if (fig.type === "parallels") {
      const want = parallelValue(fig.angle, fig.known, fig.ask);
      return want === n ? null : `l'angle val ${want}°`;
    }
    if (fig.type === "right_triangle") {
      // the question says what it asks: a perimeter, an area, or else the side marked with ?
      let want: number;
      let why: string;
      if (/per[ií]metre/i.test(prompt)) {
        want = fig.a + fig.b + fig.c;
        why = "el perímetre és";
      } else if (/[àa]rea/i.test(prompt)) {
        want = (fig.a * fig.b) / 2;
        why = "l'àrea és";
      } else {
        want = fig[fig.ask];
        why = `el costat ${fig.ask} mesura`;
      }
      return want === n ? null : `${why} ${want}`;
    }
    // Only a card that asks for the marked point is answered by it; a change card (int_number_line)
    // marks the START, so the result is never on screen before the attempt.
    if (fig.type === "number_line" && kind === "number" && /punt/i.test(prompt)) return n === fig.point ? null : `el punt és ${fig.point}`;
    if (fig.type === "grid" && fig.line !== undefined && kind === "number") {
      if (/pendent/i.test(prompt)) return n === fig.line.m ? null : `el pendent és ${fig.line.m}`;
      if (/ordenada/i.test(prompt)) return n === fig.line.n ? null : `l'ordenada a l'origen és ${fig.line.n}`;
    }
  }
  return null;
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
  figure?: Figure;
  key?: string; // two items with the same key are the same exercise (mult: a×b and b×a)
  mode?: SexaMode; // sexagesimal
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

const COLOURS = ["vermell", "blau", "verd", "groc", "taronja"];

/** n items of xs, chosen from the stream (a shuffle, then the first n). */
function subset<T>(r: Rng, xs: readonly T[], n: number): T[] {
  const a = xs.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [a[i], a[j]] = [a[j] as T, a[i] as T];
  }
  return a.slice(0, n);
}

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
  ["angle_type", (r, p) => {
    const cats = p.full === true ? ANGLE_NAMES : ANGLE_NAMES.slice(0, 4);
    const cat = pick(r, cats);
    const deg = cat === "agut" ? int(r, 1, 89) : cat === "recte" ? 90 : cat === "obtús" ? int(r, 91, 179) : cat === "pla" ? 180 : 360;
    return { prompt: "Quin tipus d'angle és?", target: [cat], answer_kind: "choice", options: cats.slice(), figure: { type: "angle", deg, label: false } };
  }],
  ["triangle_by_sides", (r) => {
    const t = int(r, 0, 2);
    let s: number[];
    if (t === 0) {
      const e = int(r, 2, 12);
      s = [e, e, e];
    } else if (t === 1) {
      const e = int(r, 2, 12);
      const c = int(r, 1, 2 * e - 1);
      if (c === e) return null;
      s = [e, e, c];
    } else {
      s = [int(r, 2, 12), int(r, 2, 12), int(r, 2, 12)];
      if (!validTriangle(s) || new Set(s).size !== 3) return null;
    }
    return { prompt: "Quin tipus de triangle és, segons els costats?", target: [triangleKind(s)], answer_kind: "choice", options: TRIANGLE_NAMES.slice(), figure: { type: "triangle", sides: s, labels: true, unit: "cm" } };
  }],
  ["perimeter_figure", (r) => {
    const t = int(r, 0, 2);
    let fig: Figure;
    let total: number;
    if (t === 0) {
      const s = [int(r, 2, 15), int(r, 2, 15), int(r, 2, 15)];
      if (!validTriangle(s)) return null;
      fig = { type: "triangle", sides: s, labels: true, unit: "cm" };
      total = s.reduce((x, y) => x + y, 0);
    } else if (t === 1) {
      const w = int(r, 2, 20);
      const h = int(r, 2, 20);
      fig = { type: "rect", w, h, labels: true, unit: "cm" };
      total = 2 * (w + h);
    } else {
      const n = int(r, 3, 8);
      const regular = r() < 0.5;
      const s = regular ? Array<number>(n).fill(int(r, 2, 12)) : Array.from({ length: n }, () => int(r, 2, 12));
      fig = { type: "polygon", sides: s, regular, labels: true, unit: "cm" };
      total = s.reduce((x, y) => x + y, 0);
    }
    return { prompt: "Quant fa el perímetre?", target: [String(total)], answer_kind: "unit", unit: "cm", figure: fig };
  }],
  ["area_figure", (r) => {
    if (r() < 0.5) {
      const w = int(r, 2, 20);
      const h = int(r, 2, 20);
      return { prompt: "Quina és l'àrea del rectangle?", target: [String(w * h)], answer_kind: "unit", unit: "cm²", figure: { type: "rect", w, h, labels: true, unit: "cm" } };
    }
    // a right triangle with whole sides (3k, 4k, 5k): the legs are the two shorter sides, the prompt says so
    const k = int(r, 1, 3);
    return {
      prompt: "Quina és l'àrea del triangle rectangle? (els catets són els dos costats més curts)",
      target: [String(6 * k * k)],
      answer_kind: "unit",
      unit: "cm²",
      figure: { type: "triangle", sides: [3 * k, 4 * k, 5 * k], labels: true, unit: "cm" },
    };
  }],
  ["circle_element", (r) => {
    const mark = pick(r, CIRCLE_MARKS);
    const rot = int(r, 0, 359); // the same mark turns: the cards differ, the answer does not
    return {
      prompt: "Quin element del cercle està marcat?",
      target: [CIRCLE_NAME[mark]],
      answer_kind: "choice",
      options: CIRCLE_MARKS.map((m) => CIRCLE_NAME[m]),
      figure: { type: "circle", mark, rot },
    };
  }],
  ["bars_read", (r) => {
    const n = int(r, 3, 5);
    const labels = subset(r, COLOURS, n);
    const values = labels.map(() => int(r, 1, 12));
    const figure: Figure = { type: "bars", labels, values, title: "Alumnes que han triat cada color" };
    const t = int(r, 0, 2);
    if (t === 0) {
      const i = int(r, 0, n - 1);
      return { prompt: `Quants alumnes han triat el ${labels[i] ?? ""}?`, target: [String(values[i] ?? 0)], figure };
    }
    if (t === 1) {
      const max = Math.max(...values);
      if (values.filter((v) => v === max).length > 1) return null;
      return { prompt: "Quin és el color més triat?", target: [labels[values.indexOf(max)] ?? ""], answer_kind: "choice", options: labels.slice(), figure };
    }
    const sum = values.reduce((x, y) => x + y, 0);
    if (sum % n !== 0) return null;
    return { prompt: "Quina és la mitjana d'alumnes per color?", target: [String(sum / n)], figure };
  }],
  ["grid_point", (r) => {
    const x = int(r, 0, 10);
    const y = int(r, 0, 10);
    return { prompt: "Quines coordenades té el punt?", target: [`(${x}, ${y})`], answer_kind: "pair", figure: { type: "grid", points: [[x, y]], size: 10 } };
  }],
  // E4 §6: a product of two factors with `digits: [da, db]` digits each (1 digit = 2..9, 2 = 10..99, 3 = 100..999).
  // The same product twice, or a×b and b×a, is the same card: the key keeps one of them.
  ["mult", (r, p) => {
    const d = paramDigits(p);
    const [loA, hiA] = DIGIT_RANGE[d[0]] ?? [2, 9];
    const [loB, hiB] = DIGIT_RANGE[d[1]] ?? [2, 9];
    const a = int(r, loA, hiA);
    const b = int(r, loB, hiB);
    return { prompt: `${a} × ${b}`, target: [String(a * b)], key: `${Math.min(a, b)}×${Math.max(a, b)}` };
  }],
]);

/** The digits of each factor of a `mult` list: `digits: [da, db]`, each 1, 2 or 3; else [1, 1]. */
const DIGIT_RANGE: Record<number, [number, number]> = { 1: [2, 9], 2: [10, 99], 3: [100, 999] };
function paramDigits(p: Params): [number, number] {
  const v = p.digits;
  const ok = Array.isArray(v) && v.length === 2 && v.every((x) => Number.isInteger(x) && x >= 1 && x <= 3);
  return ok ? [v[0] as number, v[1] as number] : [1, 1];
}

// ---- m7 generators (docs/ENCARREC-M7-E5-FLASH.md §4): the same rules as the m5 ones --------
// Each answer is worked out from the numbers drawn, never read back from the card. A figure is built the way
// checkFigure builds it, so the card and its checked figure are the same object.

const MINUS_SIGN = "−";
const signedText = (n: number): string => (n < 0 ? `${MINUS_SIGN}${-n}` : String(n));
const signedPlus = (n: number): string => (n < 0 ? `${MINUS_SIGN}${-n}` : `+${n}`);
const SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹";
const supText = (n: number): string => String(n).split("").map((d) => SUPERSCRIPTS[Number(d)]).join("");
const pt = (x: number, y: number): [number, number] => [x, y];

/** The figure a generator draws, as checkFigure keeps it (the same object the server would check). */
function checkedFigure(raw: JsonRecord): Figure {
  const c = checkFigure(raw);
  if (!("figure" in c)) throw new Error(`figura de generador no vàlida: ${c.problem}`);
  return c.figure;
}

/** A whole number in ±1..max (never 0). */
function nonZero(r: Rng, max: number): number {
  const v = int(r, 1, max);
  return r() < 0.5 ? -v : v;
}

/** A fraction num/den (den > 0) reduced, as text: 3/4, −7/12, or a whole number. */
function fracTextE5(num: number, den: number): string {
  const g = gcd(num, den) || 1;
  const n = num / g;
  const d = den / g;
  if (d === 1) return signedText(n);
  return `${n < 0 ? MINUS_SIGN : ""}${Math.abs(n)}/${d}`;
}

/** One or two letters, in alphabetical order, with exponents 1..maxExp. */
function monoPick(r: Rng, maxExp: number): Array<[string, number]> {
  const letters = subset(r, ["x", "y", "a", "b"], int(r, 1, 2)).sort();
  return letters.map((v): [string, number] => [v, int(r, 1, maxExp)]);
}

/** The letters of a monomial as text: x²y. */
function letterText(m: Array<[string, number]>): string {
  return m.map(([v, e]) => (e > 1 ? `${v}${supText(e)}` : v)).join("");
}

/** A monomial with a coefficient as text: 3x², −x, −5ab. */
function termText(coef: number, m: Array<[string, number]>): string {
  const lit = letterText(m);
  if (coef === 1) return lit;
  if (coef === -1) return `${MINUS_SIGN}${lit}`;
  return `${coef < 0 ? MINUS_SIGN : ""}${Math.abs(coef)}${lit}`;
}

/** The product of two monomials, letters merged and alphabetical. */
function monoMerge(a: Array<[string, number]>, b: Array<[string, number]>): Array<[string, number]> {
  const d = new Map<string, number>();
  for (const [v, e] of [...a, ...b]) d.set(v, (d.get(v) ?? 0) + e);
  return [...d.entries()].sort(([x], [y]) => (x < y ? -1 : x > y ? 1 : 0));
}

/** A sexagesimal total in minutes as text: 2 h 35 min, 3 h, 45 min; angles 75° 40', 18°. */
function sexaText(totalMin: number, mode: SexaMode): string {
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (mode === "time") return h && m ? `${h} h ${m} min` : h ? `${h} h` : `${m} min`;
  return m ? `${h}° ${m}'` : `${h}°`;
}

const LADDER_AREA: Array<[string, number]> = [["km²", 6], ["hm²", 4], ["dam²", 2], ["m²", 0], ["dm²", -2], ["cm²", -4], ["mm²", -6]];
const LADDER_VOLUME: Array<[string, number]> = [["m³", 3], ["dm³", 0], ["cm³", -3]];
const LADDER_CAPACITY: Array<[string, number]> = [["m³", 3], ["l", 0], ["ml", -3]];
/** A phrase with a number k (2..9), its expression and three plausible wrong ones (all different). */
const TRANSLATIONS: Array<(k: number) => [string, string, string[]]> = [
  (k) => [`El doble d'un nombre més ${k}`, `2x + ${k}`, [`2(x + ${k})`, `x + ${k}`, `2x − ${k}`]],
  (k) => [`El triple d'un nombre menys ${k}`, `3x − ${k}`, [`3(x − ${k})`, `x − ${k}`, `${k} − 3x`]],
  (k) => [`La meitat d'un nombre augmentada en ${k}`, `x/2 + ${k}`, [`x/4 + ${k}`, `(x + ${k})/2`, `2x + ${k}`]],
  (k) => [`El quadrat d'un nombre menys ${k}`, `x² − ${k}`, [`(x − ${k})²`, `x² + ${k}`, `2x − ${k}`]],
  (k) => [`La suma d'un nombre i el seu doble, més ${k}`, `3x + ${k}`, [`3(x + ${k})`, `3x − ${k}`, `x + ${k}`]],
  (k) => [`Un nombre disminuït en ${k} i multiplicat per 2`, `2(x − ${k})`, [`2x − ${k}`, `x − ${2 * k}`, `x/2 − ${k}`]],
  (k) => [`Un nombre dividit per ${k}`, `x/${k}`, [`${k}/x`, `x − ${k}`, `${k}x`]],
  (k) => [`Un nombre més ${k} vegades el mateix nombre`, `${k + 1}x`, [`${k}x`, `x + ${k}`, `x${supText(k)}`]],
];
const DIRECT_CASES = [
  "Kg de pomes i preu pagat",
  "Hores de feina i diners guanyats (mateix salari)",
  "Litres de benzina i quilòmetres recorreguts",
  "Nombre de llibres comprats i cost total",
];
const INVERSE_CASES = [
  "Nombre d'obrers i dies per acabar una obra",
  "Velocitat i temps per fer el mateix trajecte",
  "Nombre de persones i dies que duren les provisions",
  "Nombre de grifs i temps per omplir una piscina",
];
const NOTABLE: Array<[string, string]> = [
  ["Punt on es tallen les mediatrius", "circumcentre"],
  ["Punt on es tallen les bisectrius", "incentre"],
  ["Punt on es tallen les medianes", "baricentre"],
  ["Punt on es tallen les altures", "ortocentre"],
  ["Centre de la circumferència que passa pels tres vèrtexs", "circumcentre"],
  ["Centre de la circumferència inscrita en el triangle", "incentre"],
  ["Punt de gravetat del triangle", "baricentre"],
  ["Punt on es tallen les altures del triangle, o les seves prolongacions", "ortocentre"],
];
const NOTABLE_NAMES = ["circumcentre", "incentre", "baricentre", "ortocentre"];
const POLYGON_NAMES: Record<number, string> = { 3: "triangle", 4: "quadrilàter", 5: "pentàgon", 6: "hexàgon", 7: "heptàgon", 8: "octàgon", 9: "eneàgon", 10: "decàgon" };
const VARIABLES: Array<[string, string]> = [
  ["Nombre de germans", "quantitativa discreta"],
  ["Color preferit", "qualitativa"],
  ["Alçada", "quantitativa contínua"],
  ["Nombre de llibres a la biblioteca", "quantitativa discreta"],
  ["Temperatura de l'aigua", "quantitativa contínua"],
  ["Estat civil", "qualitativa"],
  ["Pes d'un paquet", "quantitativa contínua"],
  ["Marca de cotxe", "qualitativa"],
  ["Nombre de gols d'un partit", "quantitativa discreta"],
  ["Temps de viatge", "quantitativa contínua"],
];
const VARIABLE_KINDS = ["qualitativa", "quantitativa discreta", "quantitativa contínua"];
// [card, favourable outcomes, outcomes] (equally likely), worked out by hand and checked by the tests
const LAPLACE: Array<[string, number, number]> = [
  ["Dos daus: probabilitat que la suma sigui 7", 6, 36],
  ["Dos daus: probabilitat que la suma sigui 2", 1, 36],
  ["Dos daus: probabilitat que la suma sigui més gran que 10", 3, 36],
  ["Dos daus: probabilitat que els dos nombres siguin iguals", 6, 36],
  ["Dues monedes: probabilitat de dues cares", 1, 4],
  ["Dues monedes: probabilitat d'una cara i una creu", 2, 4],
  ["Un dau: probabilitat de treure un nombre primer", 3, 6],
  ["Un dau: probabilitat de treure un múltiple de 3", 2, 6],
  ["Una moneda i un dau: probabilitat de cara i nombre parell", 3, 12],
];
const PYTHAGOREAN: Array<[number, number, number]> = [[3, 4, 5], [5, 12, 13], [8, 15, 17], [7, 24, 25], [20, 21, 29]];
const DECIMAL_TYPES = ["exacte", "periòdic pur", "periòdic mixt"];

const E5_GENERATORS: Array<[string, Generator]> = [
  ["int_signs", (r) => {
    const t = int(r, 0, 2);
    if (t === 0) {
      const a = nonZero(r, 12);
      const b = nonZero(r, 12);
      return { prompt: `(${signedPlus(a)}) · (${signedPlus(b)})`, target: [signedText(a * b)] };
    }
    if (t === 1) {
      const b = nonZero(r, 12);
      const q = nonZero(r, 12);
      return { prompt: `(${signedPlus(b * q)}) : (${signedPlus(b)})`, target: [signedText(q)] };
    }
    const a = int(r, -20, 20);
    const b = nonZero(r, 20);
    const plus = r() < 0.5;
    return { prompt: `${signedText(a)} ${plus ? "+" : "−"} ${b > 0 ? b : `(${signedText(b)})`}`, target: [signedText(plus ? a + b : a - b)] };
  }],
  ["abs_opp", (r) => {
    const a = nonZero(r, 20);
    if (r() < 0.5) return { prompt: `|${signedText(a)}| = ?`, target: [String(Math.abs(a))] };
    return { prompt: `Oposat de ${signedText(a)}`, target: [signedText(-a)] };
  }],
  ["int_combined", (r) => {
    const t = int(r, 0, 2);
    if (t === 0) {
      const a = int(r, -9, 9);
      const b = int(r, 2, 6);
      const c = nonZero(r, 4);
      return { prompt: `${signedText(a)} + ${b} · (${signedPlus(c)})²`, target: [signedText(a + b * c * c)] };
    }
    if (t === 1) {
      const a = int(r, 1, 12);
      const b = nonZero(r, 9);
      const c = nonZero(r, 9);
      return { prompt: `[${a} − (${signedPlus(b)})] · (${signedPlus(c)})`, target: [signedText((a - b) * c)] };
    }
    const a = nonZero(r, 9);
    const b = nonZero(r, 9);
    const c = nonZero(r, 9);
    return { prompt: `(${signedPlus(a)}) · (${signedPlus(b)}) − (${signedPlus(c)})`, target: [signedText(a * b - c)] };
  }],
  ["prime_factors", (r) => {
    const n = int(r, 24, 2000);
    const f = primeFactorList(n);
    if (f.reduce((s, [, e]) => s + e, 0) < 3) return null;
    return { prompt: `Descompon ${n} en factors primers`, target: [factorText(f)], answer_kind: "factorization" };
  }],
  ["gcd_lcm", (r) => {
    const a = int(r, 4, 99);
    const b = int(r, 4, 99);
    if (a === b) return null;
    const lo = Math.min(a, b);
    const hi = Math.max(a, b);
    const g = gcd(a, b);
    if (r() < 0.5) return { prompt: `MCD(${a}, ${b})`, target: [String(g)], key: `mcd ${lo} ${hi}` };
    return { prompt: `mcm(${a}, ${b})`, target: [String((a * b) / g)], key: `mcm ${lo} ${hi}` };
  }],
  ["frac_simplify", (r) => {
    const den = int(r, 3, 12);
    const num = int(r, 1, den - 1);
    if (gcd(num, den) !== 1) return null;
    const g = int(r, 2, 12);
    return { prompt: `Simplifica ${num * g}/${den * g}`, target: [`${num}/${den}`], answer_kind: "fraction", form: "simplest" };
  }],
  ["frac_combined", (r) => {
    const f = (): [number, number] => {
      const d = int(r, 2, 6);
      return [int(r, 1, d - 1), d];
    };
    if (r() < 0.5) {
      const [a, b] = f();
      const [c, d] = f();
      const [e, g] = f();
      return { prompt: `(${a}/${b} + ${c}/${d}) · ${e}/${g}`, target: [fracTextE5((a * d + c * b) * e, b * d * g)], answer_kind: "fraction" };
    }
    const [a, b] = f();
    const [c, d] = f();
    return { prompt: `(${a}/${b})² − ${c}/${d}`, target: [fracTextE5(a * a * d - c * b * b, b * b * d)], answer_kind: "fraction" };
  }],
  ["decimal_type", (r) => {
    const den = pick(r, [2, 3, 4, 5, 6, 8, 9, 11, 12, 15, 16, 20, 25]);
    const num = int(r, 1, den - 1);
    const g = gcd(num, den);
    const d = den / g;
    let rem = num / g;
    const digits: number[] = [];
    for (let i = 0; i < 6 && rem !== 0; i++) {
      rem *= 10;
      digits.push(Math.floor(rem / d));
      rem %= d;
    }
    const shown = rem === 0 ? digits.join("") : `${digits.slice(0, 4).join("")}…`;
    let rest = d;
    while (rest % 2 === 0) rest /= 2;
    while (rest % 5 === 0) rest /= 5;
    const kind = rest === 1 ? "exacte" : d % 2 === 0 || d % 5 === 0 ? "periòdic mixt" : "periòdic pur";
    return { prompt: `Quin tipus de decimal és 0,${shown}?`, target: [kind], answer_kind: "choice", options: DECIMAL_TYPES.slice() };
  }],
  ["generatrix", (r) => {
    const k = int(r, 1, 3);
    const num = int(r, 1, 999);
    if (num % 10 === 0) return null; // the last decimal is not a zero: the fraction is not whole
    return { prompt: `${decComma(num, k)} = ?`, target: [fracTextE5(num, 10 ** k)], answer_kind: "fraction", form: "simplest" };
  }],
  ["power_props", (r) => {
    const b = int(r, 2, 9);
    const m = int(r, 2, 6);
    const n = int(r, 2, 6);
    switch (int(r, 0, 3)) {
      case 0: return { prompt: `${b}${supText(m)} · ${b}${supText(n)} = ${b}^?`, target: [String(m + n)] };
      case 1: return { prompt: `(${b}${supText(m)})${supText(n)} = ${b}^?`, target: [String(m * n)] };
      case 2:
        if (m === n) return null;
        return { prompt: `${b}${supText(Math.max(m, n))} : ${b}${supText(Math.min(m, n))} = ${b}^?`, target: [String(Math.abs(m - n))] };
      default: {
        const a = int(r, 2, 9);
        const c = int(r, 2, 9);
        return { prompt: `${a}${supText(m)} · ${c}${supText(m)} = ?^${m}`, target: [String(a * c)] };
      }
    }
  }],
  ["int_sqrt", (r) => {
    const n = int(r, 10, 200);
    const root = Math.floor(Math.sqrt(n)); // exact for n this small
    return { prompt: `Arrel quadrada sencera de ${n} i residu (escriu (arrel, residu))`, target: [`(${root}, ${n - root * root})`], answer_kind: "pair" };
  }],
  ["translate_expr", (r) => {
    const [phrase, right, wrong] = pick(r, TRANSLATIONS)(int(r, 2, 9));
    return { prompt: phrase, target: [right], answer_kind: "choice", options: subset(r, [right, ...wrong], 4) };
  }],
  ["value_expr", (r) => {
    const a = int(r, 2, 9);
    const b = int(r, 1, 9);
    const plus = r() < 0.5;
    const v = nonZero(r, 9);
    return { prompt: `${a}x ${plus ? "+" : "−"} ${b} per a x = ${signedText(v)}`, target: [signedText(a * v + (plus ? b : -b))] };
  }],
  ["monomial_parts", (r) => {
    const c = nonZero(r, 12);
    if (Math.abs(c) < 2) return null; // a coefficient of 1 is not shown: no card for it
    const m = monoPick(r, 4);
    const txt = termText(c, m);
    if (r() < 0.5) return { prompt: `Grau de ${txt}`, target: [String(m.reduce((s, [, e]) => s + e, 0))] };
    return { prompt: `Coeficient de ${txt}`, target: [signedText(c)] };
  }],
  ["monomial_ops", (r) => {
    const t = int(r, 0, 2);
    if (t === 0) {
      const m = monoPick(r, 2);
      const lit = letterText(m);
      const a = int(r, 2, 9);
      const b = int(r, 2, 9);
      const c = int(r, 1, 9);
      const s = a + b - c;
      if (s === 0) return null;
      return { prompt: `${a}${lit} + ${b}${lit} − ${c === 1 ? "" : c}${lit}`, target: [termText(s, m)], answer_kind: "algebraic" };
    }
    if (t === 1) {
      const m1 = monoPick(r, 2);
      const m2 = monoPick(r, 2);
      const k = int(r, 2, 6);
      const q = int(r, 2, 6);
      return { prompt: `(${k}${letterText(m1)}) · (${q}${letterText(m2)})`, target: [termText(k * q, monoMerge(m1, m2))], answer_kind: "algebraic" };
    }
    const m = monoPick(r, 2);
    const a = int(r, 2, 9);
    const b = int(r, 2, 9);
    if (a === b) return null;
    return { prompt: `${a}${letterText(m)} − ${b}${letterText(m)}`, target: [termText(a - b, m)], answer_kind: "algebraic" };
  }],
  ["linear_eq", (r) => {
    // a(x − p) = c·x + q, with the solution x0: q = (a − c)·x0 − a·p
    const a = int(r, 2, 5);
    const c = int(r, 1, 4);
    if (c === a) return null;
    const p = int(r, -5, 5);
    const x0 = int(r, -6, 6);
    const q = (a - c) * x0 - a * p;
    const left = p === 0 ? `${a}x` : `${a}(x ${p > 0 ? "−" : "+"} ${Math.abs(p)})`;
    const cx = c === 1 ? "x" : `${c}x`;
    const right = q === 0 ? cx : `${cx} ${q > 0 ? "+" : "−"} ${Math.abs(q)}`;
    return { prompt: `${left} = ${right}. Quant val x?`, target: [signedText(x0)] };
  }],
  ["proportion_type", (r) => {
    const direct = r() < 0.5;
    const text = pick(r, direct ? DIRECT_CASES : INVERSE_CASES);
    return { prompt: `${text}. Quina proporcionalitat hi ha?`, target: [direct ? "directa" : "inversa"], answer_kind: "choice", options: ["directa", "inversa"] };
  }],
  ["rule_of_three", (r) => {
    if (r() < 0.5) {
      const a = int(r, 2, 9);
      const b = int(r, 2, 12);
      const m = int(r, 2, 9);
      return { prompt: `Si ${a} llibres costen ${b} €, quant costen ${a * m} llibres?`, target: [String(b * m)] };
    }
    const a = int(r, 2, 12);
    const b = int(r, 2, 12);
    const divisors = Array.from({ length: 11 }, (_, i) => i + 2).filter((c) => c !== a && (a * b) % c === 0);
    if (!divisors.length) return null;
    const c = pick(r, divisors); // c obrers: the days are a·b/c, whole
    return { prompt: `Si ${a} obrers fan una feina en ${b} dies, quants dies trigaran ${c} obrers?`, target: [String((a * b) / c)] };
  }],
  ["chained_percent", (r) => {
    const base = int(r, 1, 8) * 50;
    const up = pick(r, [5, 10, 15, 20, 25]);
    const down = pick(r, [5, 10, 15, 20, 25]);
    const numer = base * (100 + up) * (100 - down); // the value is numer / 10^4, exact
    return { prompt: `${base} €, puja un ${up} % i baixa un ${down} %. Quant val al final?`, target: [decComma(numer, 4)] };
  }],
  ["quadrant_point", (r) => {
    const x = int(r, -6, 6);
    const y = int(r, -6, 6);
    return {
      prompt: "Quines coordenades té el punt?",
      target: [`(${signedText(x)}, ${signedText(y)})`],
      answer_kind: "pair",
      figure: checkedFigure({ type: "grid", points: [pt(x, y)], min: -6, max: 6 }),
    };
  }],
  ["linear_func", (r) => {
    const a = nonZero(r, 5);
    const b = nonZero(r, 9);
    const x = int(r, -4, 4);
    const lin = `${a === 1 ? "" : a === -1 ? MINUS_SIGN : signedText(a)}x`;
    const bt = b > 0 ? ` + ${b}` : ` − ${-b}`;
    return { prompt: `y = ${lin}${bt}. Quant val y per a x = ${signedText(x)}?`, target: [signedText(a * x + b)] };
  }],
  ["line_read", (r) => {
    const m = nonZero(r, 4);
    const n = int(r, -5, 5);
    const figure = checkedFigure({ type: "grid", points: [], min: -6, max: 6, line: { m, n } });
    if (r() < 0.5) return { prompt: "Quin és el pendent de la recta?", target: [signedText(m)], figure };
    return { prompt: "Quina és l'ordenada a l'origen de la recta?", target: [signedText(n)], figure };
  }],
  ["pythagoras", (r) => {
    const [x, y, z] = pick(r, PYTHAGOREAN);
    const k = int(r, 1, 2);
    const legs: [number, number] = r() < 0.5 ? [x * k, y * k] : [y * k, x * k];
    const c = z * k;
    const ask = pick(r, ["a", "b", "c"] as const);
    const want = ask === "a" ? legs[0] : ask === "b" ? legs[1] : c;
    return {
      prompt: "Calcula el costat que falta (?)",
      target: [String(want)],
      answer_kind: "unit",
      unit: "cm",
      figure: checkedFigure({ type: "right_triangle", a: legs[0], b: legs[1], c, ask, unit: "cm" }),
    };
  }],
  ["parallel_angles", (r) => {
    const known = int(r, 1, 8);
    const ask = int(r, 1, 8);
    if (ask === known) return null;
    const angle = 5 * int(r, 7, 29); // E9 §4: 35°..145° in steps of 5 (a small angle makes the arcs and the label collide)
    return {
      prompt: "Quant mesura l'angle marcat amb «?»",
      target: [String(parallelValue(angle, known, ask))],
      figure: checkedFigure({ type: "parallels", angle, known, ask }),
    };
  }],
  ["polygon_angle_sum", (r) => {
    const n = int(r, 3, 10);
    const name = POLYGON_NAMES[n];
    const prompt = r() < 0.5 ? `Suma dels angles interiors d'un ${name}` : `Quants graus sumen els angles interiors d'un ${name}?`;
    return { prompt, target: [String((n - 2) * 180)] };
  }],
  ["notable_points", (r) => {
    const [card, name] = pick(r, NOTABLE);
    return { prompt: card, target: [name], answer_kind: "choice", options: NOTABLE_NAMES.slice() };
  }],
  ["composite_area", (r) => {
    if (r() < 0.5) {
      const big = int(r, 3, 10);
      const small = int(r, 1, big - 1);
      return { prompt: `Corona circular de radis ${big} cm i ${small} cm (π = 3,14)`, target: [decComma(314 * (big * big - small * small), 2)], answer_kind: "unit", unit: "cm²" };
    }
    // sector: 3.14 · r² · θ / 360 = 314 · r² · θ / 36000, which must end: its denominator only 2s and 5s
    const th = pick(r, [60, 90, 120, 180]);
    const rad = int(r, 2, 10);
    const numer = 314 * rad * rad * th;
    const g = gcd(numer, 36000);
    const n2 = numer / g;
    const d2 = 36000 / g;
    let rest = d2;
    let twos = 0;
    let fives = 0;
    while (rest % 2 === 0) {
      rest /= 2;
      twos++;
    }
    while (rest % 5 === 0) {
      rest /= 5;
      fives++;
    }
    if (rest !== 1) return null;
    const places = Math.max(twos, fives);
    return { prompt: `Sector de ${th}° de radi ${rad} cm (π = 3,14)`, target: [decComma(n2 * (10 ** places / d2), places)], answer_kind: "unit", unit: "cm²" };
  }],
  ["unit_area_volume", (r) => {
    const ladder = pick(r, [LADDER_AREA, LADDER_VOLUME, LADDER_CAPACITY]);
    const i = int(r, 0, ladder.length - 1);
    let j = int(r, 0, ladder.length - 2);
    if (j >= i) j += 1;
    const [ua, ea] = ladder[i] as [string, number];
    const [ub, eb] = ladder[j] as [string, number];
    const k = int(r, 0, 2);
    const m = k === 0 ? int(r, 1, 99) : int(r, 11, 999);
    if (k > 0 && m % 10 === 0) return null;
    const e = ea - eb - k; // m·10^-k in ua is m·10^e in ub
    if (e < -3 || e > 6) return null;
    const target = e >= 0 ? decComma(m * 10 ** e, 0) : decComma(m, -e);
    return { prompt: `${decComma(m, k)} ${ua} = ? ${ub}`, target: [target], answer_kind: "unit", unit: ub };
  }],
  ["speed_convert", (r) => {
    if (r() < 0.5) {
      const k = int(r, 1, 10);
      return { prompt: `${18 * k} km/h = ? m/s`, target: [String(5 * k)], answer_kind: "unit", unit: "m/s" };
    }
    const d = int(r, 1, 20);
    const v = int(r, 1, 20);
    return { prompt: `Densitat ${d} g/cm³ i volum ${v} cm³. Massa = ? g`, target: [String(d * v)], answer_kind: "unit", unit: "g" };
  }],
  ["sexagesimal_ops", (r) => {
    const mode: SexaMode = r() < 0.5 ? "time" : "angle";
    const t1 = mode === "time" ? int(r, 60, 900) : int(r, 600, 4000);
    const op = int(r, 0, 3);
    if (op === 0) {
      const k = int(r, 2, 5);
      return { prompt: `${sexaText(t1, mode)} × ${k}`, target: [sexaText(t1 * k, mode)], answer_kind: "sexagesimal", mode };
    }
    if (op === 1) {
      const t2 = int(r, 1, t1 - 1);
      return { prompt: `${sexaText(t1, mode)} − ${sexaText(t2, mode)}`, target: [sexaText(t1 - t2, mode)], answer_kind: "sexagesimal", mode };
    }
    if (op === 2) {
      const t2 = int(r, 10, 300);
      return { prompt: `${sexaText(t1, mode)} + ${sexaText(t2, mode)}`, target: [sexaText(t1 + t2, mode)], answer_kind: "sexagesimal", mode };
    }
    const k = int(r, 2, 5);
    if (t1 % k !== 0) return null; // the division is exact
    return { prompt: `${sexaText(t1, mode)} : ${k}`, target: [sexaText(t1 / k, mode)], answer_kind: "sexagesimal", mode };
  }],
  ["variable_type", (r) => {
    const [name, kind] = pick(r, VARIABLES);
    return { prompt: `Quin tipus de variable és «${name}»?`, target: [kind], answer_kind: "choice", options: VARIABLE_KINDS.slice() };
  }],
  ["freq_relative", (r) => {
    const total = int(r, 4, 40);
    const n = int(r, 1, total - 1);
    return { prompt: `${total} alumnes, ${n === 1 ? "1 té" : `${n} tenen`} gos. Freqüència relativa?`, target: [fracTextE5(n, total)], answer_kind: "fraction" };
  }],
  ["median", (r) => {
    const count = int(r, 5, 8);
    const vals: number[] = [];
    for (let i = 0; i < count; i++) vals.push(int(r, 1, 30));
    const s = [...vals].sort((x, y) => x - y);
    if (count % 2 === 1) return { prompt: `Mediana de ${vals.join(", ")}`, target: [String(s[(count - 1) / 2])] };
    const sum = (s[count / 2 - 1] as number) + (s[count / 2] as number);
    if (sum % 2 !== 0) return null; // the median would be a half
    return { prompt: `Mediana de ${vals.join(", ")}`, target: [String(sum / 2)] };
  }],
  ["weighted_mean", (r) => {
    const count = int(r, 2, 3);
    const vals: number[] = [];
    const ws: number[] = [];
    for (let i = 0; i < count; i++) {
      vals.push(int(r, 4, 10));
      ws.push(int(r, 1, 3));
    }
    const W = ws.reduce((x, y) => x + y, 0);
    const S = vals.reduce((x, _, i) => x + (vals[i] as number) * (ws[i] as number), 0);
    let rest = W;
    let twos = 0;
    let fives = 0;
    while (rest % 2 === 0) {
      rest /= 2;
      twos++;
    }
    while (rest % 5 === 0) {
      rest /= 5;
      fives++;
    }
    if (rest !== 1) return null; // the mean must be a decimal of a few places
    const places = Math.max(twos, fives);
    const parts = vals.map((v, i) => `${v} (pes ${ws[i]})`);
    const text = parts.length === 2 ? `${parts[0]} i ${parts[1]}` : `${parts[0]}, ${parts[1]} i ${parts[2]}`;
    return { prompt: `Notes ${text}. Mitjana ponderada?`, target: [decComma(S * (10 ** places / W), places)] };
  }],
  ["laplace", (r) => {
    const [card, fav, all] = pick(r, LAPLACE);
    return { prompt: card, target: [fracTextE5(fav, all)], answer_kind: "fraction" };
  }],
];
// ---- m6 generators (docs/ENCARREC-M6-E9-FLASH.md §1): the same rules as the m5 and m7 ones ----------
// Each answer is worked out from the numbers drawn. A decimal answer is exact and written with a comma.

/** The area units of m6, with their powers of ten against the m² (the hectare is hm², the are is dam²). */
const LADDER_M6_AREA: Array<[string, number]> = [["km²", 6], ["ha", 4], ["a", 2], ["m²", 0], ["cm²", -4], ["mm²", -6]];
/** The volume and capacity units of m6, against the m³ (1 dm³ = 1 l, 1 cm³ = 1 ml). */
const LADDER_M6_VOLUME: Array<[string, number]> = [["m³", 3], ["dm³", 0], ["cm³", -3], ["l", 0], ["ml", -3]];

/** A conversion inside one ladder: `m` with `k` decimals in unit ua, asked in unit ub. Null when the answer
 *  would need more places than the card can show (at most three after the comma). */
function ladderCard(r: Rng, ladder: Array<[string, number]>): GenItem | null {
  const i = int(r, 0, ladder.length - 1);
  let j = int(r, 0, ladder.length - 2);
  if (j >= i) j += 1;
  const [ua, ea] = ladder[i] as [string, number];
  const [ub, eb] = ladder[j] as [string, number];
  const k = int(r, 0, 2);
  const m = k === 0 ? int(r, 1, 99) : int(r, 11, 999);
  if (k > 0 && m % 10 === 0) return null; // the last decimal is not a zero
  const e = ea - eb - k; // m · 10^-k in ua is m · 10^e in ub
  if (e < -3 || e > 6) return null;
  const target = e >= 0 ? decComma(m * 10 ** e, 0) : decComma(m, -e);
  return { prompt: `${decComma(m, k)} ${ua} = ? ${ub}`, target: [target], answer_kind: "unit", unit: ub };
}

const E9_GENERATORS: Array<[string, Generator]> = [
  ["power_value", (r) => {
    const t = int(r, 0, 2);
    if (t === 0) {
      const b = int(r, 2, 12);
      const e = int(r, 2, 4);
      if (b ** e > 10000) return null;
      return { prompt: `Quant és ${b}${supText(e)}?`, target: [String(b ** e)] };
    }
    if (t === 1) {
      const k = int(r, 2, 25);
      return { prompt: `Quant és √${k * k}?`, target: [String(k)] };
    }
    const k = int(r, 2, 10);
    return { prompt: `Quant és ∛${k ** 3}?`, target: [String(k)] };
  }],
  // The figure marks the START temperature, never the result (the answer must not be on screen).
  ["int_number_line", (r) => {
    const start = int(r, -9, 9);
    const d = nonZero(r, 9);
    const end = start + d;
    if (end < -10 || end > 10) return null;
    return {
      prompt: `Eren ${signedText(start)} °C i ${d > 0 ? "puja" : "baixa"} ${Math.abs(d)} °C. Quina temperatura hi ha ara?`,
      target: [signedText(end)],
      figure: checkedFigure({ type: "number_line", min: -10, max: 10, point: start, label: "°C" }),
    };
  }],
  ["frac_ops4", (r) => {
    const f = (): [number, number] => {
      const d = int(r, 2, 9);
      return [int(r, 1, d - 1), d];
    };
    const [a, b] = f();
    const [c, d] = f();
    const fr = (text: string, num: number, den: number): GenItem => {
      const g = gcd(num, den) || 1; // the answer in lowest terms (a value is accepted in any form anyway)
      return fracItem(text, num / g, den / g);
    };
    switch (int(r, 0, 3)) {
      case 0: return fr(`${a}/${b} + ${c}/${d}`, a * d + c * b, b * d);
      case 1:
        if (a * d <= c * b) return null; // the difference is positive
        return fr(`${a}/${b} − ${c}/${d}`, a * d - c * b, b * d);
      case 2: return fr(`${a}/${b} · ${c}/${d}`, a * c, b * d);
      default: return fr(`${a}/${b} : ${c}/${d}`, a * d, b * c);
    }
  }],
  ["dec_division", (r) => {
    if (r() < 0.5) {
      // a decimal divisor (0,2 … 0,9) and a whole quotient: the dividend is q · d
      const dv = int(r, 2, 9);
      const q = int(r, 2, 40);
      const a10 = q * dv; // the dividend in tenths
      if (a10 % 10 === 0) return null; // a whole dividend has no decimal to show
      return { prompt: `${decComma(a10, 1)} : ${decComma(dv, 1)}`, target: [String(q)] };
    }
    // a whole divisor and a quotient with one decimal (1,1 … 9,9)
    const d = int(r, 2, 9);
    const q10 = int(r, 11, 99);
    if (q10 % 10 === 0) return null;
    return { prompt: `${decComma(q10 * d, 1)} : ${d}`, target: [decComma(q10, 1)] };
  }],
  ["percent_change", (r) => {
    const pct = pick(r, [5, 10, 15, 20, 25, 30, 40, 50]);
    const base = (100 / gcd(pct, 100)) * int(r, 2, 30); // so that the change is whole
    const change = (base * pct) / 100;
    if (r() < 0.5) return { prompt: `Augment del ${pct} % sobre ${base}`, target: [String(base + change)] };
    return { prompt: `Descompte del ${pct} % sobre ${base}`, target: [String(base - change)] };
  }],
  ["scale", (r) => {
    const n = pick(r, [5000, 10000, 20000, 25000, 50000, 100000, 250000, 500000, 1000000]);
    const k = int(r, 1, 20); // centimetres on the map
    const head = `Escala 1:${thousands(n)}. ${k} cm al mapa = ? `;
    if (r() < 0.5) return { prompt: `${head}km`, target: [decComma(k * n, 5)], answer_kind: "unit", unit: "km" };
    return { prompt: `${head}m`, target: [decComma(k * n, 2)], answer_kind: "unit", unit: "m" };
  }],
  ["area_units", (r) => ladderCard(r, LADDER_M6_AREA)],
  ["volume_units", (r) => ladderCard(r, LADDER_M6_VOLUME)],
  ["angle_ops", (r) => {
    // minutes in steps of 5′ (10′ … 55′), so the text never shows 5′ alone
    const x = int(r, 10, 80) * 60 + 5 * int(r, 2, 11);
    if (r() < 0.5) {
      const y = int(r, 10, 80) * 60 + 5 * int(r, 2, 11);
      return { prompt: `${sexaText(x, "angle")} + ${sexaText(y, "angle")}`, target: [sexaText(x + y, "angle")], answer_kind: "sexagesimal", mode: "angle" };
    }
    return { prompt: `90° − ${sexaText(x, "angle")}`, target: [sexaText(90 * 60 - x, "angle")], answer_kind: "sexagesimal", mode: "angle" };
  }],
  ["area_polygon_formula", (r) => {
    const t = int(r, 0, 2);
    if (t === 0) {
      // a regular polygon: the apothem is the true one for the side, rounded to tenths; area = n · s · a / 2
      const n = pick(r, [5, 6, 8]);
      const s = int(r, 2, 12);
      const a10 = Math.round((10 * s) / (2 * Math.tan(Math.PI / n)));
      return { prompt: `${POLYGON_NAMES[n]} regular de costat ${s} cm i apotema ${decComma(a10, 1)} cm. Àrea?`, target: [decComma(n * s * a10 * 5, 2)], answer_kind: "unit", unit: "cm²" };
    }
    if (t === 1) {
      const D = int(r, 2, 20);
      const d = int(r, 2, 20);
      return { prompt: `Rombe de diagonals D = ${D} cm i d = ${d} cm. Àrea?`, target: [decComma(D * d * 5, 1)], answer_kind: "unit", unit: "cm²" };
    }
    const B = int(r, 4, 20);
    const b = int(r, 2, B - 1);
    const h = int(r, 2, 20);
    return { prompt: `Trapezi de bases ${B} cm i ${b} cm i altura ${h} cm. Àrea?`, target: [decComma((B + b) * h * 5, 1)], answer_kind: "unit", unit: "cm²" };
  }],
  ["circle_measures", (r) => {
    const t = int(r, 0, 2);
    if (t === 0) {
      const rad = int(r, 1, 20);
      return { prompt: `Longitud d'una circumferència de radi ${rad} cm (π = 3,14)`, target: [decComma(628 * rad, 2)], answer_kind: "unit", unit: "cm" };
    }
    if (t === 1) {
      const rad = int(r, 1, 20);
      return { prompt: `Àrea d'un cercle de radi ${rad} cm (π = 3,14)`, target: [decComma(314 * rad * rad, 2)], answer_kind: "unit", unit: "cm²" };
    }
    const dm = int(r, 2, 20);
    return { prompt: `Longitud d'una circumferència de diàmetre ${dm} cm (π = 3,14)`, target: [decComma(314 * dm, 2)], answer_kind: "unit", unit: "cm" };
  }],
  ["volume_solid", (r) => {
    if (r() < 0.5) {
      const a = int(r, 2, 15);
      const b = int(r, 2, 15);
      const c = int(r, 2, 15);
      return { prompt: `Prisma rectangular de ${a} cm × ${b} cm × ${c} cm. Volum?`, target: [String(a * b * c)], answer_kind: "unit", unit: "cm³" };
    }
    const rad = int(r, 1, 8);
    const h = int(r, 2, 15);
    return { prompt: `Cilindre de radi ${rad} cm i altura ${h} cm (π = 3,14). Volum?`, target: [decComma(314 * rad * rad * h, 2)], answer_kind: "unit", unit: "cm³" };
  }],
];
for (const [kind, gen] of E9_GENERATORS) GENERATORS.set(kind, gen);

for (const [kind, gen] of E5_GENERATORS) GENERATORS.set(kind, gen);

/** The generator kinds a `generate` block may name (besides `op`). */
export const GEN_KINDS: readonly string[] = [...GENERATORS.keys()];

/** The most cards some kinds can make (their vocabulary is finite): a list asks for `count` and gets at most this.
 *  Mirror in hooks/curriculum.py (MATH_GEN_ROOM). Every other kind makes GEN_COUNT_MAX. */
export const GEN_ROOM: Readonly<Record<string, number>> = { proportion_type: 8, notable_points: 8, variable_type: 10, laplace: 9, polygon_angle_sum: 16 };

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
    if (!item) continue;
    const card = (item.key ?? item.prompt) + "\u0000" + JSON.stringify(item.figure ?? null); // a figure card is its prompt and its figure
    if (seen.has(card)) continue;
    seen.add(card);
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
  if (kind === "pair" && parsePair(answer[0]) === null) return `${answer[0]} no són unes coordenades (x, y)`;
  if (kind === "factorization" && "problem" in factorization(answer[0])) return `${answer[0]} no és una descomposició en primers`;
  if (kind === "algebraic" && parsePoly(answer[0]) === null) return `${answer[0]} no és una expressió algebraica`;
  if (kind === "sexagesimal") {
    const sx = parseSexa(answer[0], sexaMode(item.mode, answer[0] ?? ""));
    if (sx === null || !sx.normalized) return `${answer[0]} no és un temps o un angle normalitzat`;
  }
  if (kind === "number" || kind === "unit") {
    const sop = simpleOp(item.prompt);
    if (sop) {
      const r = opResult(sop.a, sop.op, sop.b);
      if (r === null) return `${item.prompt} no dona un resultat enter ≥ 0`;
      if (numericValue(answer[0]) !== r) return `${item.prompt} és ${r}, no ${answer[0]}`;
    }
  }
  if (item.figure !== undefined) {
    const f = checkFigure(item.figure);
    if ("problem" in f) return `figura: ${f.problem}`;
    const why = figureAnswerProblem(f.figure, item.prompt, kind as AnswerKind, answer);
    if (why) return `figura i resposta no coincideixen: ${why}`;
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
  if (kind === "sexagesimal") w.mode = sexaMode(item.mode, w.target[0] ?? "");
  if (item.figure !== undefined) {
    const f = checkFigure(item.figure);
    if ("figure" in f) w.figure = f.figure;
  }
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
// Same scale and rule as hooks/curriculum.py (LEVELS, find_curriculum): the course the learner
// is doing is the lowest level, from the profile's current_level up to its target_level, that has
// no certificate; every level certified → the last one. null when there is no curriculum.
const LEVELS = ["A0", "A1", "A2", "B1", "B2", "C1", "C2", "M1", "M2", "M3", "M4", "M5", "M6", "M7"];
const lvlIndex = (v: unknown): number => {
  const i = LEVELS.indexOf(String(v ?? "").trim().toUpperCase());
  return i < 0 ? 99 : i;
};

export function courseLevel(root: string, dataDir: string, learner: JsonRecord): string | null {
  const lang = String(learner.target_language ?? "").trim().toLowerCase();
  const target = lvlIndex(learner.target_level);
  if (!lang || target === 99) return null;
  let floor = lvlIndex(learner.current_level);
  if (floor === 99 || floor > target) floor = -1;
  const levels: string[] = [];
  let files: string[] = [];
  try {
    files = fs.readdirSync(path.join(root, "curriculum")).filter((f) => f.endsWith(".md"));
  } catch {
    return null;
  }
  for (const f of files) {
    let head = "";
    try {
      head = fs.readFileSync(path.join(root, "curriculum", f), "utf8").split("\n---")[0] ?? "";
    } catch {
      continue;
    }
    const meta = (k: string) => (new RegExp(`^${k}:\\s*(.+)$`, "m").exec(head)?.[1] ?? "").trim();
    const lv = meta("level").toUpperCase();
    if (meta("language").toLowerCase() === lang && floor <= lvlIndex(lv) && lvlIndex(lv) <= target) levels.push(lv);
  }
  if (!levels.length) return null;
  levels.sort((a, b) => lvlIndex(a) - lvlIndex(b));
  let certs: unknown = [];
  try {
    certs = JSON.parse(fs.readFileSync(path.join(dataDir, "certificates.json"), "utf8"));
  } catch {
    /* no certificates yet */
  }
  const done = new Set(
    (Array.isArray(certs) ? certs : [])
      .map(asRecord)
      .filter((c) => String(c.language ?? "").trim().toLowerCase() === lang)
      .map((c) => String(c.level ?? "").trim().toUpperCase()),
  );
  return levels.find((l) => !done.has(l)) ?? levels[levels.length - 1]!;
}

export function flashListsResponse(root: string, dataDir: string): JsonRecord {
  const profile = readJson(path.join(dataDir, "learner-profile.json"));
  const learner = asRecord(profile.learner);
  const native = String(learner.native_language ?? "").trim();
  const code = nativeCode(native);
  const target = String(learner.target_language ?? "").trim();
  // Only the lists of the level being worked on (2026-10-17, Albert: an m5 learner saw m6/m7 too).
  // The course level, as the path computes it; without a curriculum, the declared current level.
  const level = (courseLevel(root, dataDir, learner) ?? String(learner.current_level ?? "")).trim().toUpperCase();
  const cfg = flashConfig(readJson(path.join(root, "config", "domain.json")), profileDomain(profile));
  if (!cfg.enabled || !cfg.dir) {
    return { ok: true, enabled: false, native, nativeCode: code, target, level, lists: [] };
  }
  const all = loadFlashLists(root, cfg.dir, code);
  const lists = level ? all.filter((l) => String(l.level ?? "").trim().toUpperCase() === level) : all;
  return { ok: true, enabled: true, native, nativeCode: code, target, level, lists };
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
