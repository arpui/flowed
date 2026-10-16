// Flash v0 / v0.1 — the vocabulary drill without a model (docs/ENCARREC-FLASH-v0.md, -v0.1.md),
// and the math answer kinds and generators of docs/ENCARREC-M5-E1-FLASH.md (§2, §3, §4).
// Run with:
//   node --experimental-strip-types server/test/flash.test.ts

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";
import {
  checkFigure,
  decComma,
  emptyFlashState,
  factorization,
  figureAnswerProblem,
  GEN_ROOM,
  parallelValue,
  parsePair,
  parsePoly,
  parseSexa,
  polyKey,
  polyTerms,
  sameFactors,
  sexaMode,
  type AnswerKind,
  type Figure,
  type SexaMode,
  expandGenerate,
  flashConfig,
  flashListsResponse,
  flashStateResponse,
  GEN_KINDS,
  generatedWords,
  genCount,
  isSimplestText,
  loadFlashLists,
  mathListProblems,
  mathWords,
  nativeCode,
  normalizeOp,
  numericValue,
  opResult,
  parseFraction,
  profileDomain,
  sanitizeFlashState,
  saveFlashState,
  simpleOp,
  type MathWord,
} from "../src/flash.ts";

// The kinds of docs/ENCARREC-M7-E5-FLASH.md §4 (35 generators of m7).
const E5_KINDS: string[] = [
  "int_signs", "abs_opp", "int_combined", "prime_factors", "gcd_lcm", "frac_simplify", "frac_combined", "decimal_type",
  "generatrix", "power_props", "int_sqrt", "translate_expr", "value_expr", "monomial_parts", "monomial_ops", "linear_eq",
  "proportion_type", "rule_of_three", "chained_percent", "quadrant_point", "linear_func", "line_read", "pythagoras",
  "parallel_angles", "polygon_angle_sum", "notable_points", "composite_area", "unit_area_volume", "speed_convert",
  "sexagesimal_ops", "variable_type", "freq_relative", "median", "weighted_mean", "laplace",
];

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

const root = path.join(import.meta.dirname, "..", "..");
const read = (...p: string[]) => fs.readFileSync(path.join(root, ...p), "utf8");

// The pure core of web/flash.js, loaded the way the browser does (no document here).
const ctx: Record<string, unknown> = {};
vm.createContext(ctx);
vm.runInContext(read("web", "flash.js"), ctx);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const C = ctx.FlashCore as any;

type Word = { id: string; target: string[]; native: string[]; prompt?: string };
type List = { id: string; level: string; title: string; words: Word[]; kind?: string };

// ---- the lists --------------------------------------------------------------
console.log("lists");
const listsCa: List[] = loadFlashLists(root, "curriculum/flash/en-*", "ca");
const listsEs: List[] = loadFlashLists(root, "curriculum/flash/en-*", "es");
// Every .json under curriculum/flash/en-* and math-* must be a list (an empty or broken file is skipped
// silently at run time, so it is caught here). A math file is checked with mathListProblems.
const listFiles = fs.readdirSync(path.join(root, "curriculum", "flash"))
  .filter((d) => d.startsWith("en-") || d.startsWith("math-"))
  .flatMap((d) => fs.readdirSync(path.join(root, "curriculum", "flash", d)).filter((f) => f.endsWith(".json")).sort().map((f) => `${d}/${f}`));
const enFiles = listFiles.filter((f) => f.startsWith("en-"));
const mathFiles = listFiles.filter((f) => f.startsWith("math-"));
const badFiles = listFiles.filter((f) => {
  try {
    const raw = JSON.parse(read("curriculum", "flash", f));
    if (f.startsWith("math-")) return !raw || typeof raw !== "object" || mathListProblems(raw).length > 0;
    return !raw || !Array.isArray(raw.words) || raw.words.length === 0;
  } catch {
    return true;
  }
});
check("every list file is valid JSON with words", badFiles.length === 0, badFiles);
check("one list per valid file under curriculum/flash/en-*", listsCa.length === enFiles.length - badFiles.filter((f) => f.startsWith("en-")).length, listsCa.map((l) => l.id));
check("list ids are unique", new Set(listsCa.map((l) => l.id)).size === listsCa.length);
check("every list is A1 and titled", listsCa.every((l) => l.level === "A1" && l.title.length > 0));
check("every list has words", listsCa.every((l) => l.words.length > 0), listsCa.map((l) => l.words.length));
for (const l of listsCa) {
  const ids = l.words.map((w) => w.id);
  check(`word ids unique in ${l.id}`, new Set(ids).size === ids.length);
  check(`every word has a target in ${l.id}`, l.words.every((w) => w.target.length > 0 && w.target.every((t) => t.length > 0)));
}
const bothLangs = listsCa.every((l, i) => l.words.every((w, j) => w.native.length > 0 && (listsEs[i]?.words[j]?.native.length ?? 0) > 0));
check("every word has a non-empty native form in ca and es", bothLangs);
check("ca and es give the same words", listsCa.every((l, i) => l.words.every((w, j) => w.id === listsEs[i]?.words[j]?.id)));
const firstCa = listsCa[0]?.words[0];
const firstEs = listsEs[0]?.words[0];
check("native forms are resolved to one language, not both", firstCa?.native.join() === "mare" && firstEs?.native.join() === "madre");
check("language lists carry no math fields", listsCa.every((l) => !("kind" in l) && l.words.every((w) => !("prompt" in w))));

// ---- math lists (docs/ENCARREC-FLASH-MATH.md) ---------------------------------
console.log("math lists");
const listsMath: List[] = loadFlashLists(root, "curriculum/flash/math-*", "ca");
for (const f of mathFiles) {
  const problems = mathListProblems(JSON.parse(read("curriculum", "flash", f)));
  check(`math file ${f} has no problems (no dropped item)`, problems.length === 0, problems);
}
check("one math list per file under curriculum/flash/math-*", listsMath.length === mathFiles.length, listsMath.map((l) => l.id));
check("every math list is kind math, level m5 or m7, titled, with words", listsMath.every((l) => l.kind === "math" && (l.level === "m5" || l.level === "m7") && l.title.length > 0 && l.words.length > 0));
check("every math word has a prompt, a native = [prompt] and a target", listsMath.every((l) => l.words.every((w) => w.prompt && w.native.join() === w.prompt && w.target.length > 0)));
for (const l of listsMath) {
  const ids = l.words.map((w) => w.id);
  check(`math word ids unique in ${l.id}`, new Set(ids).size === ids.length);
}
// E4 §6: the m5 multiplication lists (kind mult): the digits of each factor, no repeat, no commuted repeat, the result computed.
{
  const digitsOf = (n: number) => String(n).length;
  const multCheck = (id: string, count: number, da: number, db: number) => {
    const l = listsMath.find((x) => x.id === id);
    const pairs = (l?.words ?? []).map((w) => ((w.prompt ?? "").match(/^(\d+) × (\d+)$/) ?? []).slice(1).map(Number));
    const keys = pairs.map(([a, b]) => `${Math.min(a!, b!)}×${Math.max(a!, b!)}`);
    const okDigits = pairs.every(([a, b]) => digitsOf(a!) === da && digitsOf(b!) === db && a! >= 2 && b! >= 2);
    const okResult = (l?.words ?? []).every((w) => w.target.join() === String(pairs[(l?.words ?? []).indexOf(w)]!.reduce((x, y) => x * y, 1)));
    check(`${id}: ${count} words, ${da}×${db} digits, no repeat or commuted repeat, result computed`,
      !!l && l.words.length === count && okDigits && new Set(keys).size === keys.length && okResult && l.words.map((w) => w.id).join() === Array.from({ length: count }, (_, i) => `g${i + 1}`).join(),
      { n: l?.words.length, sample: l?.words.slice(0, 2) });
  };
  multCheck("math-m5.flash.taules-repas", 24, 1, 1);
  multCheck("math-m5.flash.mult-2x1", 12, 2, 1);
  multCheck("math-m5.flash.mult-3x1", 12, 3, 1);
  const repas = listsMath.find((l) => l.id === "math-m5.flash.taules-repas");
  check("taules (repàs): the factors are 2..9", (repas?.words ?? []).every((w) => { const [a, b] = (w.prompt ?? "").split(" × ").map(Number); return a! >= 2 && a! <= 9 && b! >= 2 && b! <= 9; }));
  const mult = mathWords({ id: "math-m5.flash.mult-2x1", generate: { kind: "mult", count: 12, params: { digits: [2, 1] } } }).words;
  check("mult: the same list gives the same words (deterministic, seeded by the id)", JSON.stringify(mult.map((w) => w.prompt)) === JSON.stringify(listsMath.find((l) => l.id === "math-m5.flash.mult-2x1")?.words.map((w) => w.prompt)));
}
check("math lists have no language entries (the lists are per domain)", listsMath.every((l) => !l.id.startsWith("en-")) && listsCa.every((l) => !l.id.startsWith("math-")));

// E4: the m5 lists — one per generator, numbered from 10, each with its three titles, count 12 and, when it
// names one, a competence that exists in math-m5.md.
{
  const compIds = new Set([...read("curriculum", "math-m5.md").matchAll(/^### (m5\.[a-z0-9_]+) /gm)].map((m) => m[1]));
  check("math list ids are unique across the domain", new Set(listsMath.map((l) => l.id)).size === listsMath.length);
  const m5Files = mathFiles.filter((f) => f.startsWith("math-m5/"));
  const numbers = m5Files.map((f) => Number(f.split("/")[1]?.slice(0, 2)));
  check("m5 files are numbered 01, 02, 03 (multiplications) and 10..35 (the 26 generators)", numbers.join() === [1, 2, 3, ...Array.from({ length: 26 }, (_, i) => i + 10)].join(), numbers);
  const gen = m5Files.map((f) => JSON.parse(read("curriculum", "flash", f)));
  check("every m5 list has the three titles and a level m5", gen.every((r) => r.level === "m5" && r.title && r.title.ca && r.title.es && r.title.en));
  const e4 = gen.slice(3);
  check("the 26 generated m5 lists (10..35) take a generate block of count 12", e4.length === 26 && e4.every((r) => r.generate && r.generate.kind && r.generate.count === 12 && !("items" in r)));
  const comps = gen.filter((r) => "competence" in r);
  check("every competence named by an m5 list exists in math-m5.md", comps.length > 0 && comps.every((r) => compIds.has(r.competence)), comps.map((r) => r.competence));
  check("E4 table: 15 generated lists name a competence over 11 distinct ones, plus mult-3x1 (m5.mult_3digit)", comps.length === 16 && new Set(comps.map((r) => r.competence)).size === 12, comps.map((r) => r.competence));
  const cardLists = listsMath.filter((l) => e4.some((r) => r.id === l.id));
  check("the 26 generated m5 lists (10..35) each give 12 words", cardLists.length === 26 && cardLists.every((l) => l.words.length === 12), cardLists.map((l) => `${l.id}:${l.words.length}`));
}

console.log("math engine");
check("normalizeOp: synonyms map to the four signs", normalizeOp("x") === "×" && normalizeOp("*") === "×" && normalizeOp("-") === "−" && normalizeOp("−") === "−" && normalizeOp("/") === ":" && normalizeOp(":") === ":" && normalizeOp("+") === "+");
check("normalizeOp: unknown or non-text → null (no prototype keys)", normalizeOp("%") === null && normalizeOp("constructor") === null && normalizeOp(7) === null);
check("opResult: exact division only, no zero divisor, no negatives", opResult(12, ":", 4) === 3 && opResult(10, ":", 4) === null && opResult(5, ":", 0) === null && opResult(3, "−", 5) === null && opResult(3, "−", 1) === 2);
check("simpleOp: reads 23 × 4, 8 x 3 and 5 - 2; not a sentence", JSON.stringify(simpleOp("23 × 4")) === '{"a":23,"op":"×","b":4}' && simpleOp("8 x 3")?.op === "×" && simpleOp("5 - 2")?.op === "−" && simpleOp("Quants són 2?") === null);
check("numericValue: 72, 72,0 and 72.0 are the same; spaces out; not a number → null", numericValue("72") === 72 && numericValue("72,0") === 72 && numericValue("72.0") === 72 && numericValue(" 7 2 ") === 72 && numericValue("") === null && numericValue("x") === null);
check("expandGenerate: taula del 7 → 10 items, results 7..70", JSON.stringify(expandGenerate({ op: "×", a: [7], b: { from: 1, to: 10 } }).map((w) => w.target[0])) === "[\"7\",\"14\",\"21\",\"28\",\"35\",\"42\",\"49\",\"56\",\"63\",\"70\"]");
check("expandGenerate: division with a rest is dropped", expandGenerate({ op: ":", a: [21], b: [2, 3, 7] }).map((w) => w.id).join() === "21d3,21d7", expandGenerate({ op: ":", a: [21], b: [2, 3, 7] }));
check("expandGenerate: negative result is dropped", expandGenerate({ op: "−", a: [3], b: [5, 1] }).map((w) => w.id).join() === "3m1");
check("expandGenerate: unknown op → nothing; a repeated id keeps one", expandGenerate({ op: "%", a: [1], b: [1] }).length === 0 && expandGenerate({ op: "+", a: [1, 1], b: [2] }).length === 1);
check("expandGenerate: a range longer than 1000 is refused", expandGenerate({ op: "+", a: [1], b: { from: 0, to: 5000 } }).length === 0);
{
  const r = mathWords({ items: [
    { id: "bad", prompt: "23 × 4", answer: ["91"] },
    { id: "good", prompt: "23 × 4", answer: ["92"] },
    { id: "open", prompt: "Quants caramels hi ha?", answer: ["12"] },
    { id: "good", prompt: "5 + 5", answer: ["10"] },
  ] });
  check("items: a wrong result is dropped and reported; an open prompt is kept; a repeated id is reported", r.words.map((w) => w.id).join() === "good,open" && r.problems.length === 2, r);
  check("items: the report names the item and the sum", !!r.problems[0]?.includes('"bad"') && !!r.problems[0]?.includes("92"), r.problems);
  check("mathListProblems: generate and items together are a problem", mathListProblems({ generate: { op: "+", a: [1], b: [1] }, items: [] }).length === 1);
  check("mathListProblems: neither generate nor items is a problem", mathListProblems({ title: {} }).length === 1);
}
{
  // A tmp curriculum: a both-keys file is skipped, generate and items files load, a new file shows up with no code change.
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "flash-math-"));
  try {
    const dir = path.join(tmp, "curriculum", "flash", "math-t1");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "01-gen.json"), JSON.stringify({ id: "math-t1.flash.gen", level: "t1", title: { ca: "Gen", en: "Gen" }, generate: { op: "+", a: [1], b: [1, 2] } }));
    fs.writeFileSync(path.join(dir, "02-both.json"), JSON.stringify({ id: "math-t1.flash.both", level: "t1", title: { en: "Both" }, generate: { op: "+", a: [1], b: [1] }, items: [] }));
    fs.writeFileSync(path.join(dir, "03-items.json"), JSON.stringify({ id: "math-t1.flash.items", level: "t1", title: { en: "Items" }, items: [{ id: "s", prompt: "2 + 2", answer: ["4"] }] }));
    const before = loadFlashLists(tmp, "curriculum/flash/math-*", "ca").map((l) => l.id).join();
    check("loader: a file with both generate and items is skipped; the others load as math", before === "math-t1.flash.gen,math-t1.flash.items", before);
    fs.writeFileSync(path.join(dir, "04-new.json"), JSON.stringify({ id: "math-t1.flash.new", level: "t1", title: { en: "New" }, generate: { op: "×", a: [3], b: [3] } }));
    const after = loadFlashLists(tmp, "curriculum/flash/math-*", "ca");
    check("loader: a new generated file appears with no code change", after.length === 3 && after[2]?.words[0]?.target.join() === "9", after.map((l) => l.id));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

// ---- native language -------------------------------------------------------
console.log("nativeCode");
check("Catalan variants → ca", ["Catalan", "català", "catalan", "Català", "ca"].every((t) => nativeCode(t) === "ca"));
check("Spanish variants → es", ["Spanish", "español", "castellano", "Castellà", "espanyol", "es"].every((t) => nativeCode(t) === "es"));
check("empty or missing → ca (default)", nativeCode("") === "ca" && nativeCode(undefined) === "ca" && nativeCode(null) === "ca");
check("unknown language → ca (default)", nativeCode("French") === "ca");

// ---- correction -----------------------------------------------------------
console.log("correction");
const norm = (s: string) => C.normalize(s);
check("normalize: case, spaces, trim", norm("  Hello   THERE ") === "hello there");
check("normalize: no final punctuation", norm("Mother.") === "mother" && norm("Really?!") === "really");
check("normalize: curly apostrophe", norm("l’avi") === "l'avi");
check("stripArticle: en the/a/an/to", C.stripArticle("the apple", "en") === "apple" && C.stripArticle("to eat", "en") === "eat" && C.stripArticle("an egg", "en") === "egg");
check("stripArticle: ca el/la/l'", C.stripArticle("el gos", "ca") === "gos" && C.stripArticle("l'avi", "ca") === "avi");
check("stripArticle: es los/las", C.stripArticle("los perros", "es") === "perros");
check("stripArticle: a bare article is kept", C.stripArticle("the", "en") === "the");
check("check: exact match", C.check("mother", ["mother", "mum"], "en").ok === true && C.check("mother", ["mother"], "en").exact === true);
check("check: article is ignored", C.check("The mother", ["mother"], "en").ok === true);
check("check: any accepted form", C.check("Mum.", ["mother", "mum"], "en").form === "mum");
check("check: 'eat' accepted for 'to eat'", C.check("eat", ["to eat", "eat"], "en").ok === true);
const acc = C.check("germa", ["germà"], "ca");
check("check: accent-free answer ok, flagged not exact", acc.ok === true && acc.exact === false && acc.form === "germà", acc);
check("check: accent-free Spanish answer", C.check("pajaro", ["pájaro"], "es").ok === true);
check("check: wrong word is wrong", C.check("dog", ["cat"], "en").ok === false);
check("check: empty answer is wrong", C.check("   ", ["cat"], "en").ok === false);
check("hint: first letter and dashes", C.hint("mother", "en") === "m _ _ _ _ _", C.hint("mother", "en"));
check("hint: article not counted", C.hint("to eat", "en") === "e _ _", C.hint("to eat", "en"));
check("hint: spaces shown as /", C.hint("ice cream", "en") === "i _ _ / _ _ _ _ _", C.hint("ice cream", "en"));

console.log("math correction");
check("checkNumber: 21 accepts 21, spaces out, comma or dot", C.checkNumber("21", ["21"]).ok && C.checkNumber(" 2 1 ", ["21"]).ok && C.checkNumber("72,0", ["72"]).ok && C.checkNumber("72.0", ["72"]).ok);
check("checkNumber: a different number, a word or nothing is wrong", !C.checkNumber("22", ["21"]).ok && !C.checkNumber("vint-i-u", ["21"]).ok && !C.checkNumber("   ", ["21"]).ok);
check("checkNumber: the accepted form is the target, exact", C.checkNumber("72,0", ["72"]).form === "72" && C.checkNumber("72,0", ["72"]).exact === true);
check("hint for a number: first digit and dashes", C.hint("21", null) === "2 _" && C.hint("72", null) === "7 _");

// ---- Leitner ---------------------------------------------------------------
console.log("leitner");
check("nextBox: first try climbs to 2 and stops", C.nextBox(0, "first") === 1 && C.nextBox(1, "first") === 2 && C.nextBox(2, "first") === 2);
check("nextBox: second-attempt success keeps the box", C.nextBox(0, "retry") === 0 && C.nextBox(1, "retry") === 1 && C.nextBox(2, "retry") === 2);
check("nextBox: revealed drops one, floor 0", C.nextBox(2, "revealed") === 1 && C.nextBox(0, "revealed") === 0);

const LIST: List = {
  id: "t.flash.test",
  level: "A1",
  title: "Test",
  words: Array.from({ length: 12 }, (_, i) => ({ id: `w${i + 1}`, target: [`t${i + 1}`], native: [`n${i + 1}`] })),
};
const ids = (ws: Word[]) => ws.map((w) => w.id);

{
  const s0 = C.emptyState();
  const s1 = C.recordResult(s0, LIST.id, "w1", "first", 0, "2026-10-16");
  check("recordResult: first try → box 1, seen 1, first_try 1", JSON.stringify(s1.lists[LIST.id].words.w1) === JSON.stringify({ box: 1, seen: 1, first_try: 1, misses: 0, last: "2026-10-16" }));
  check("recordResult: does not mutate the state it got", JSON.stringify(s0) === JSON.stringify(C.emptyState()));
  const s2 = C.recordResult(s1, LIST.id, "w1", "retry", 1, "2026-10-17");
  check("recordResult: retry keeps box, counts the miss", s2.lists[LIST.id].words.w1.box === 1 && s2.lists[LIST.id].words.w1.misses === 1);
  const s3 = C.recordResult(s2, LIST.id, "w1", "revealed", 3, "2026-10-18");
  check("recordResult: revealed drops box and adds misses", s3.lists[LIST.id].words.w1.box === 0 && s3.lists[LIST.id].words.w1.misses === 4);
}

{
  // Round composition: fresh words in list order at first.
  let s = C.emptyState();
  check("round 1: first ten words, in order", ids(C.buildRound(LIST, s)).join() === "w1,w2,w3,w4,w5,w6,w7,w8,w9,w10");
  // w1 twice first-try in two rounds → sabuda, out of the round.
  s = C.recordResult(s, LIST.id, "w1", "first", 0, "d1");
  s = C.recordResult(s, LIST.id, "w1", "first", 0, "d2");
  check("a word first-try in two rounds is known and leaves the rounds", C.listStatus(LIST, s).known === 1 && !ids(C.buildRound(LIST, s)).includes("w1"));
  // w2 revealed (box 0), w3 solved first (box 1): seen ones come first, lowest box first.
  s = C.recordResult(s, LIST.id, "w2", "revealed", 3, "d1");
  s = C.recordResult(s, LIST.id, "w3", "first", 0, "d1");
  const r = ids(C.buildRound(LIST, s));
  check("seen and unknown first, lowest box first, then unseen in list order", r[0] === "w2" && r[1] === "w3" && r[2] === "w4", r);
  check("a round holds at most ten words", C.buildRound(LIST, s).length <= 10);
}

{
  // Closing: all twelve known closes the list; a partial set does not.
  let s = C.emptyState();
  for (const w of LIST.words.slice(0, 11)) {
    s = C.recordResult(s, LIST.id, w.id, "first", 0, "d1");
    s = C.recordResult(s, LIST.id, w.id, "first", 0, "d2");
  }
  s = C.closeIfDone(LIST, s, "d2");
  check("eleven known: not closed", C.listStatus(LIST, s).closed === false && s.lists[LIST.id].closed_at === null);
  s = C.recordResult(s, LIST.id, "w12", "first", 0, "d1");
  s = C.recordResult(s, LIST.id, "w12", "first", 0, "d2");
  s = C.closeIfDone(LIST, s, "d2");
  check("all twelve known: closed, closed_at set", C.listStatus(LIST, s).closed === true && s.lists[LIST.id].closed_at === "d2");
}

{
  // A full drill, every answer first try: four rounds, no known word comes back, the list closes.
  let s = C.emptyState();
  let rounds = 0;
  let leaked = false;
  while (!C.listStatus(LIST, s).closed && rounds < 20) {
    rounds += 1;
    for (const w of C.buildRound(LIST, s)) {
      const e = (s.lists[LIST.id] || { words: {} }).words[w.id];
      if (e && e.box >= 2) leaked = true;
      s = C.recordResult(s, LIST.id, w.id, "first", 0, "d");
    }
    s = C.closeIfDone(LIST, s, "d");
  }
  check("a clean drill closes in four rounds", rounds === 4 && C.listStatus(LIST, s).closed, { rounds });
  check("known words never come back", !leaked);
}

{
  // Repassa: shuffled, and the state stays as it was.
  let s = C.emptyState();
  for (const w of LIST.words) {
    s = C.recordResult(s, LIST.id, w.id, "first", 0, "d1");
    s = C.recordResult(s, LIST.id, w.id, "first", 0, "d2");
  }
  s = C.closeIfDone(LIST, s, "d2");
  const before = JSON.stringify(s);
  const rep = C.repassaRound(LIST, 10, () => 0.42);
  check("repassa: ten words, distinct", rep.length === 10 && new Set(ids(rep)).size === 10);
  check("repassa: does not change the progress", JSON.stringify(s) === before);
  check("repassa: shuffles", ids(rep).join() !== ids(LIST.words.slice(0, 10)).join());
}

// ---- v0.1: prefs, timer, round dots, outcome, trace ------------------------
console.log("prefs and timer");
check("prefs: no stored value → nt, 20 s by default", JSON.stringify(C.migratePrefs(null)) === JSON.stringify({ dir: "nt", timer: 20 }));
check("prefs: old timer true → 20", C.migratePrefs({ dir: "tn", timer: true }).timer === 20 && C.migratePrefs({ dir: "tn", timer: true }).dir === "tn");
check("prefs: timer false stays off", C.migratePrefs({ timer: false }).timer === false);
check("prefs: 10/20/30 kept", [10, 20, 30].every((n) => C.migratePrefs({ timer: n }).timer === n));
check("prefs: unknown timer or dir → defaults", C.migratePrefs({ timer: 45, dir: "xx" }).timer === 20 && C.migratePrefs({ timer: 45, dir: "xx" }).dir === "nt");
check("timer options are 10, 20, 30", JSON.stringify(C.TIMER_OPTIONS) === "[10,20,30]");
check("timeLeft: full at start, zero after the limit, never negative", C.timeLeft(0, 0, 20) === 20 && C.timeLeft(0, 5000, 20) === 15 && C.timeLeft(0, 99000, 20) === 0);
check("barPct: 100 at full, 0 at zero", C.barPct(20, 20) === 100 && C.barPct(0, 20) === 0 && C.barPct(10, 20) === 50);
check("timerTone: green, amber in the last 5 s, red in the last 3 s", C.timerTone(12) === "ok" && C.timerTone(5) === "warn" && C.timerTone(4) === "warn" && C.timerTone(3) === "err" && C.timerTone(0) === "err");

console.log("outcome");
check("outcome: first try → first, later try → retry", C.outcome({ ok: true, misses: 0 }) === "first" && C.outcome({ ok: true, misses: 1 }) === "retry");
check("outcome: one or two errors → still trying", C.outcome({ ok: false, misses: 1 }) === null && C.outcome({ ok: false, misses: 2 }) === null);
check("outcome: third error → revealed", C.outcome({ ok: false, misses: 3 }) === "revealed");
check("outcome: timeout gives the same result as a reveal, whatever the misses", [0, 1, 2, 3].every((m) => C.outcome({ ok: false, misses: m, timedOut: true }) === "revealed"));
{
  const s0 = C.emptyState();
  const byTimeout = C.recordResult(s0, LIST.id, "w1", C.outcome({ ok: false, misses: 0, timedOut: true }), 0, "d1");
  const byReveal = C.recordResult(s0, LIST.id, "w1", C.outcome({ ok: false, misses: 3 }), 0, "d1");
  check("timeout and reveal leave the same box", byTimeout.lists[LIST.id].words.w1.box === byReveal.lists[LIST.id].words.w1.box);
  check("dot colours: first ok, retry amber, revealed or timeout red", C.dotClass("first") === "ok" && C.dotClass("retry") === "retry" && C.dotClass("revealed") === "err");
}

console.log("round dots and summary");
{
  let dots: string[] = Array.from({ length: 10 }, () => "pending");
  const first = C.roundLabel(dots);
  check("round starts at Paraula 0 de 10 before the first card", first.n === 0 && first.m === 10, first);
  dots[0] = "cur";
  check("current card is the one marked", JSON.stringify(C.roundLabel(dots)) === '{"n":1,"m":10}');
  dots[0] = "ok";
  dots[1] = "cur";
  check("answered cards keep their colour, next card is Paraula 2", JSON.stringify(C.roundLabel(dots)) === '{"n":2,"m":10}');
  // A revealed card comes back at the end: one more dot, so the total counts it.
  dots[1] = "err";
  dots = C.addReturn(dots);
  check("a returned card adds one dot at the end", dots.length === 11 && dots[10] === "pending", dots.length);
  dots[10] = "cur";
  check("the returned card is Paraula 11 de 11", JSON.stringify(C.roundLabel(dots)) === '{"n":11,"m":11}');
}
{
  let s = C.emptyState();
  s = C.recordResult(s, LIST.id, "w1", "first", 0, "d1");
  s = C.recordResult(s, LIST.id, "w2", "first", 0, "d1");
  s = C.recordResult(s, LIST.id, "w2", "first", 0, "d2");
  s = C.recordResult(s, LIST.id, "w3", "revealed", 3, "d1");
  check("halfway counts box 1 only (w1 box 1; w2 known; w3 box 0)", C.halfway(LIST, s) === 1, C.halfway(LIST, s));
  check("known count for the summary: 0 → 1", C.listStatus(LIST, C.emptyState()).known === 0 && C.listStatus(LIST, s).known === 1);
}

// ---- manifest and profile --------------------------------------------------
console.log("manifest and profile");
const manifest = JSON.parse(read("config", "domain.json"));
check("language has flash on, en-* lists", JSON.stringify(flashConfig(manifest, "language")) === JSON.stringify({ enabled: true, dir: "curriculum/flash/en-*" }));
check("math has flash on, over the math-* lists", JSON.stringify(flashConfig(manifest, "math")) === JSON.stringify({ enabled: true, dir: "curriculum/flash/math-*" }));
check("unknown domain has no flash", flashConfig(manifest, "nope").enabled === false && flashConfig(null, "language").enabled === false);
check("language still hides no commands (domain-shell rule)", !(manifest.domains.language.hidden_commands || []).length);
check("profileDomain: CEFR level means language", profileDomain({ learner: { current_level: "A1" } }) === "language");
check("profileDomain: math level means math", profileDomain({ learner: { current_level: "m3" } }) === "math");
check("profileDomain: explicit field wins", profileDomain({ domain: "math", learner: { current_level: "A1" } }) === "math");

// ---- the /api/flash/lists body, against a throwaway data dir ----------------
console.log("GET /api/flash/lists");
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "flash-test-"));
try {
  const writeProfile = (learner: Record<string, unknown>) =>
    fs.writeFileSync(path.join(dataDir, "learner-profile.json"), JSON.stringify({ learner }));

  writeProfile({ native_language: "Catalan", target_language: "English", current_level: "A1" });
  const ca = flashListsResponse(root, dataDir) as any;
  check("language profile: enabled, ca, English, A1", ca.ok === true && ca.enabled === true && ca.nativeCode === "ca" && ca.target === "English" && ca.level === "A1" && ca.native === "Catalan");
  check("language profile: all the lists", Array.isArray(ca.lists) && ca.lists.length === listsCa.length);
  const mother = ca.lists[0].words.find((w: Word) => w.id === "mother");
  check("words carry only the native forms of the learner", mother && JSON.stringify(mother.native) === '["mare"]' && JSON.stringify(mother.target) === '["mother","mum","mom"]', mother);
  check("lists are ordered by level, then file name", ca.lists.map((l: List) => l.id).join() === listsCa.map((l) => l.id).join() && ca.lists[0]?.id === "en-A1.flash.family", ca.lists.map((l: List) => l.id));

  writeProfile({ native_language: "castellano", target_language: "English", current_level: "A1" });
  const es = flashListsResponse(root, dataDir) as any;
  check("castellano profile: nativeCode es, madre", es.nativeCode === "es" && es.lists[0].words.find((w: Word) => w.id === "mother").native.join() === "madre");

  check("language profile: no math lists", ca.lists.every((l: List & { kind?: string }) => l.kind === undefined && !l.id.startsWith("math-")));

  writeProfile({ native_language: "Catalan", target_language: "English", current_level: "m5" });
  const math = flashListsResponse(root, dataDir) as any;
  check("math profile: enabled, the math-* lists only", math.enabled === true && math.lists.length === listsMath.length && math.lists.every((l: List & { kind?: string }) => l.kind === "math"), math.lists.map((l: List) => l.id));
} finally {
  fs.rmSync(dataDir, { recursive: true, force: true });
}

// ---- v1: progress on the server (data/flash-db.json) ------------------------
console.log("progress store (v1)");
check("hasProgress: empty state has none, a seen word has some", !C.hasProgress(C.emptyState()) && C.hasProgress(C.recordResult(C.emptyState(), LIST.id, "w1", "first", 0, "d1")));
check("roundsOn: missing day is 0", C.roundsOn({ version: 1, lists: {}, rounds_by_day: {} }, "2026-10-16") === 0);
{
  const s1 = C.countRound(C.emptyState(), "2026-10-16");
  const s2 = C.countRound(s1, "2026-10-16");
  check("countRound: adds one per round on that day, without mutating", C.roundsOn(s2, "2026-10-16") === 2 && C.roundsOn(s1, "2026-10-16") === 1 && C.roundsOn(C.emptyState(), "2026-10-16") === 0);
}

const KNOWN = new Set(["en-A1.flash.family", "en-A1.flash.food", "en-A1.flash.home", "en-A1.flash.animals", "en-A1.flash.verbs"]);
{
  const body = {
    version: 1,
    lists: {
      "en-A1.flash.family": {
        words: {
          mother: { box: 2, seen: 3, first_try: 2, misses: 1, last: "2026-10-16" },
          tooHigh: { box: 3, seen: 1, first_try: 0, misses: 0, last: "2026-10-16" },
          negative: { box: 1, seen: -1, first_try: 0, misses: 0, last: "2026-10-16" },
          badDate: { box: 1, seen: 1, first_try: 0, misses: 0, last: "16/10/2026" },
          fraction: { box: 1.5, seen: 1, first_try: 0, misses: 0, last: null },
        },
        closed_at: "2026-10-16",
      },
      "not.a.list": { words: { x: { box: 2, seen: 1, first_try: 1, misses: 0, last: null } }, closed_at: null },
    },
    rounds_by_day: { "2026-10-16": 2, "16-10-2026": 1, "2026-10-17": -3 },
  };
  const s = sanitizeFlashState(body, KNOWN);
  check("sanitize: keeps a good word, drops box out of range, bad fields and bad dates", JSON.stringify(Object.keys(s.lists["en-A1.flash.family"]?.words ?? {})) === '["mother"]', s.lists);
  check("sanitize: drops unknown list ids", !("not.a.list" in s.lists));
  const badDate = sanitizeFlashState({ version: 1, lists: { "en-A1.flash.family": { words: {}, closed_at: "soon" } } }, KNOWN);
  check("sanitize: keeps a valid closed_at, drops a bad one", s.lists["en-A1.flash.family"]?.closed_at === "2026-10-16" && badDate.lists["en-A1.flash.family"]?.closed_at === null);
  check("sanitize: rounds keep only valid days with counts ≥ 0", JSON.stringify(s.rounds_by_day) === '{"2026-10-16":2}', s.rounds_by_day);
  check("sanitize: wrong version or not an object gives the empty state", JSON.stringify(sanitizeFlashState({ version: 2, lists: {} }, KNOWN)) === JSON.stringify(emptyFlashState()) && JSON.stringify(sanitizeFlashState("x", KNOWN)) === JSON.stringify(emptyFlashState()));
}

console.log("GET and PUT /api/flash/state");
const v1Dir = fs.mkdtempSync(path.join(os.tmpdir(), "flash-v1-"));
try {
  const writeProfile = (learner: Record<string, unknown>) =>
    fs.writeFileSync(path.join(v1Dir, "learner-profile.json"), JSON.stringify({ learner }));
  const dbFile = path.join(v1Dir, "flash-db.json");

  writeProfile({ native_language: "Catalan", target_language: "English", current_level: "A1" });
  const empty = flashStateResponse(root, v1Dir) as any;
  check("GET with no file: enabled, empty state", empty.enabled === true && JSON.stringify(empty.state) === JSON.stringify(emptyFlashState()));
  check("GET with no file: nothing written", !fs.existsSync(dbFile));

  const good = { version: 1, lists: { "en-A1.flash.family": { words: { mother: { box: 2, seen: 2, first_try: 2, misses: 0, last: "2026-10-16" } }, closed_at: null } }, rounds_by_day: { "2026-10-16": 1 } };
  const put = saveFlashState(root, v1Dir, good);
  check("PUT valid state: 200, file written, body echoes the saved state", put.status === 200 && (put.body as any).state.lists["en-A1.flash.family"].words.mother.box === 2);
  check("PUT: no temporary file left behind", !fs.existsSync(`${dbFile}.tmp`) && fs.existsSync(dbFile));
  check("PUT: the file on disk is the sanitized state", JSON.parse(fs.readFileSync(dbFile, "utf8")).rounds_by_day["2026-10-16"] === 1);
  const back = flashStateResponse(root, v1Dir) as any;
  check("GET after PUT: the same progress", JSON.stringify(back.state.lists) === JSON.stringify(good.lists));

  const bad = saveFlashState(root, v1Dir, { version: 1, lists: { "en-A1.flash.family": { words: { mother: { box: 9, seen: 1, first_try: 0, misses: 0, last: null } } } } });
  check("PUT with a bad box: the word is dropped, the rest still saved", bad.status === 200 && Object.keys((bad.body as any).state.lists["en-A1.flash.family"].words).length === 0);
  const beforeRefused = fs.readFileSync(dbFile, "utf8");
  const refused = saveFlashState(root, v1Dir, { version: 2, lists: {} });
  check("PUT with another version: 400, file untouched", refused.status === 400 && fs.readFileSync(dbFile, "utf8") === beforeRefused);
  const notObject = saveFlashState(root, v1Dir, ["x"]);
  check("PUT with a non-object body: 400", notObject.status === 400);

  writeProfile({ native_language: "Catalan", target_language: "English", current_level: "m5" });
  const mathGet = flashStateResponse(root, v1Dir) as any;
  check("math profile: GET enabled, empty state", mathGet.enabled === true && JSON.stringify(mathGet.state) === JSON.stringify(emptyFlashState()));
  const mathState = { version: 1, lists: { "math-m5.flash.taules-repas": { words: { g3: { box: 2, seen: 2, first_try: 2, misses: 0, last: "2026-10-16" } }, closed_at: null } }, rounds_by_day: { "2026-10-16": 1 } };
  const mathPut = saveFlashState(root, v1Dir, { ...mathState, lists: { ...mathState.lists, "en-A1.flash.family": good.lists["en-A1.flash.family"] } });
  check("math profile: PUT keeps the math lists, drops the language ones", mathPut.status === 200 && JSON.stringify(Object.keys((mathPut.body as any).state.lists)) === '["math-m5.flash.taules-repas"]', (mathPut.body as any).state?.lists);
  check("math profile: the math progress is read back", JSON.stringify((flashStateResponse(root, v1Dir) as any).state.lists) === JSON.stringify(mathState.lists));
} finally {
  fs.rmSync(v1Dir, { recursive: true, force: true });
}


// ---- E1: answer kinds and generators (docs/ENCARREC-M5-E1-FLASH.md §2–§4) ---
// The arithmetic of every generated word is checked here with a second, independent
// reading of its prompt (a small evaluator, plain regexes), not with the generator's own code.
console.log("generators (E1)");
{
  const expected = ["round", "digit_value", "compare_numbers", "frac_of", "frac_equiv", "frac_same_den", "frac_dec", "dec_times_int", "percent_of", "divisible", "combined", "unit_convert", "complex_to_simple", "time_convert", "area_simple", "mean", "probability", "equation", "sequence", "mult"];
  const expectedE3 = [...expected, "angle_type", "triangle_by_sides", "perimeter_figure", "area_figure", "circle_element", "bars_read", "grid_point", ...E5_KINDS];
  check("the generator kinds of §3, the figure kinds of E3 and mult of §6", JSON.stringify([...GEN_KINDS].sort()) === JSON.stringify([...expectedE3].sort()), GEN_KINDS);
  check("count: default 12, clamped to 1..50, a non-integer gives 12", genCount(undefined) === 12 && genCount(0) === 1 && genCount(51) === 50 && genCount(7) === 7 && genCount(12.5) === 12 && genCount("9") === 12);
  // E7 §5: "1 té gos" (not "1 tenen gos") when the count is one
  const fq = generatedWords("math-m7.flash.freq-check", { kind: "freq_relative", count: 50 }).map((w) => w.prompt);
  check("freq_relative says '1 té gos' for one pupil", fq.every((p) => !/ 1 tenen gos/.test(p)) && fq.some((p) => /, 1 té gos\./.test(p)), fq.slice(0, 3));
  check("unknown kinds and prototype names give no words", generatedWords("x", { kind: "nope", count: 5 }).length === 0 && generatedWords("x", { kind: "constructor", count: 5 }).length === 0);
  const same1 = JSON.stringify(generatedWords("math-m5.flash.round", { kind: "round", count: 30 }));
  const same2 = JSON.stringify(generatedWords("math-m5.flash.round", { kind: "round", count: 30 }));
  const other = JSON.stringify(generatedWords("math-m5.flash.other", { kind: "round", count: 30 }));
  check("deterministic: the same list id gives the same words; another id gives others", same1 === same2 && same1 !== other);

  // An independent evaluator for the combined expressions (+ − × : and parentheses).
  const evalExpr = (src: string): number => {
    const toks = src.replace(/−/g, "-").replace(/×/g, "*").replace(/:/g, "/").match(/\d+|[-+*/()]/g) ?? [];
    let i = 0;
    const factor = (): number => {
      if (toks[i] === "(") {
        i++;
        const v = expr();
        i++;
        return v;
      }
      return Number(toks[i++]);
    };
    const term = (): number => {
      let v = factor();
      while (toks[i] === "*" || toks[i] === "/") {
        const op = toks[i++];
        const f = factor();
        v = op === "*" ? v * f : v / f;
      }
      return v;
    };
    const expr = (): number => {
      let v = term();
      while (toks[i] === "+" || toks[i] === "-") {
        const op = toks[i++];
        const t = term();
        v = op === "+" ? v + t : v - t;
      }
      return v;
    };
    return expr();
  };
  const POW10: Record<string, number> = { km: 3, m: 0, dm: -1, cm: -2, mm: -3, kg: 3, g: 0, mg: -3, kl: 3, l: 0, dl: -1, ml: -3 };
  const PAIR_FACTOR: Record<string, number> = { "m cm": 100, "kg g": 1000, "l ml": 1000 };
  const dec = (s: string) => Number(s.replace(",", "."));
  const num = (s: string) => Number(s.replace(/\./g, ""));
  const wholeEq = (v: number, t: string) => Number.isInteger(v) && String(v) === t;

  // Returns null when the word is right for its kind, else the reason.
  const verify = (kind: string, w: MathWord): string | null => {
    const p = w.prompt;
    const t = w.target[0] ?? "";
    const k = w.answer_kind ?? "number";
    let m: RegExpExecArray | null;
    switch (kind) {
      case "round":
        m = /^Arrodoneix ([\d.]+) a la (desena|centena|unitat de miler)$/.exec(p);
        if (!m) return "forma";
        return wholeEq(Math.round(num(m[1]!) / { desena: 10, centena: 100, "unitat de miler": 1000 }[m[2]!]!) * { desena: 10, centena: 100, "unitat de miler": 1000 }[m[2]!]!, t) ? null : "arrodoniment";
      case "digit_value": {
        m = /^Quin valor té el (\d) a ([\d.]+)\?$/.exec(p);
        if (!m) return "forma";
        const ds = m[2]!.replace(/\./g, "");
        const at = ds.indexOf(m[1]!);
        if (at < 0 || ds.indexOf(m[1]!, at + 1) >= 0) return "dígit repetit o absent";
        return wholeEq(Number(m[1]) * 10 ** (ds.length - 1 - at), t) ? null : "valor";
      }
      case "compare_numbers": {
        m = /^([\d.]+) \? ([\d.]+)$/.exec(p);
        if (!m) return "forma";
        const a = num(m[1]!);
        const b = num(m[2]!);
        const rel = a < b ? "<" : a > b ? ">" : "=";
        return t === rel && k === "choice" && JSON.stringify(w.options) === '["<",">","="]' ? null : "comparació";
      }
      case "frac_of":
        m = /^(\d+)\/(\d+) de (\d+)$/.exec(p);
        if (!m) return "forma";
        return (Number(m[1]) * Number(m[3])) % Number(m[2]) === 0 && wholeEq((Number(m[1]) * Number(m[3])) / Number(m[2]), t) ? null : "fracció de";
      case "frac_equiv":
        m = /^(\d+)\/(\d+) = \?\/(\d+)$/.exec(p);
        if (!m) return "forma";
        return (Number(m[1]) * Number(m[3])) % Number(m[2]) === 0 && wholeEq((Number(m[1]) * Number(m[3])) / Number(m[2]), t) ? null : "equivalent";
      case "frac_same_den": {
        m = /^(\d+)\/(\d+) ([+−]) (\d+)\/(\d+)$/.exec(p);
        if (!m || m[2] !== m[5] || k !== "fraction") return "forma";
        const v = m[3] === "+" ? Number(m[1]) + Number(m[4]) : Number(m[1]) - Number(m[4]);
        const tv = parseFraction(t);
        return tv && tv.num * Number(m[2]) === v * tv.den ? null : "suma o resta";
      }
      case "frac_dec": {
        m = /^(\d+)\/(\d+) = \?$/.exec(p);
        if (m) return dec(t) === Number(m[1]) / Number(m[2]) ? null : "decimal";
        m = /^(\d+),(\d+) = \?\/(\d+)$/.exec(p);
        if (!m) return "forma";
        return Math.abs(Number(`0.${m[2]}`) - Number(t) / Number(m[3])) < 1e-12 ? null : "numerador";
      }
      case "dec_times_int":
        m = /^([\d,]+) × (\d)$/.exec(p);
        if (!m) return "forma";
        return Math.abs(dec(t) - dec(m[1]!) * Number(m[2])) < 1e-9 ? null : "producte decimal";
      case "percent_of":
        m = /^(\d+) % de (\d+)$/.exec(p);
        if (!m) return "forma";
        return wholeEq((Number(m[1]) * Number(m[2])) / 100, t) ? null : "percentatge";
      case "divisible":
        m = /^És (\d+) divisible per (\d+)\?$/.exec(p);
        if (!m) return "forma";
        return t === (Number(m[1]) % Number(m[2]) === 0 ? "Sí" : "No") && k === "choice" ? null : "divisibilitat";
      case "combined": {
        const v = evalExpr(p);
        return wholeEq(v, t) && v >= 0 ? null : `resultat ${v}`;
      }
      case "unit_convert": {
        m = /^([\d,]+) (\w+) = \? (\w+)$/.exec(p);
        if (!m || k !== "unit" || w.unit !== m[3]) return "forma";
        const v = dec(m[1]!) * 10 ** (POW10[m[2]!]! - POW10[m[3]!]!);
        return Math.abs(dec(t) - v) < 1e-9 ? null : "conversió";
      }
      case "complex_to_simple": {
        m = /^(\d+) (\w+) (\d+) (\w+) = \? (\w+)$/.exec(p);
        if (!m || w.unit !== m[5]) return "forma";
        const f = PAIR_FACTOR[`${m[2]} ${m[4]}`];
        return f && wholeEq(Number(m[1]) * f + Number(m[3]), t) ? null : "complex";
      }
      case "time_convert":
        m = /^(\d+) h (\d+) min = \? min$/.exec(p);
        if (m) return wholeEq(Number(m[1]) * 60 + Number(m[2]), t) && w.unit === "min" ? null : "temps";
        m = /^(\d+) min (\d+) s = \? s$/.exec(p);
        if (!m) return "forma";
        return wholeEq(Number(m[1]) * 60 + Number(m[2]), t) && w.unit === "s" ? null : "temps";
      case "area_simple":
        m = /^Rectangle de (\d+) cm × (\d+) cm\. Àrea\?$/.exec(p);
        if (m) return wholeEq(Number(m[1]) * Number(m[2]), t) && w.unit === "cm²" ? null : "àrea";
        m = /^Triangle: base (\d+) cm, altura (\d+) cm\. Àrea\?$/.exec(p);
        if (!m) return "forma";
        return wholeEq((Number(m[1]) * Number(m[2])) / 2, t) && w.unit === "cm²" ? null : "àrea triangle";
      case "mean": {
        m = /^Mitjana de ([\d, ]+)$/.exec(p);
        if (!m) return "forma";
        const xs = m[1]!.split(", ").map(Number);
        return wholeEq(xs.reduce((x, y) => x + y, 0) / xs.length, t) ? null : "mitjana";
      }
      case "probability": {
        const tv = parseFraction(t);
        if (!tv || k !== "fraction") return "forma";
        let want: number | null = null;
        if (p === "Moneda: probabilitat de treure cara?") want = 1 / 2;
        else if ((m = /^Bossa amb (\d+) boles vermelles i (\d+) de blaves\./.exec(p))) want = Number(m[1]) / (Number(m[1]) + Number(m[2]));
        else if ((m = /^Dau de 6 cares: probabilitat de treure (.+)\?$/.exec(p))) {
          const text = m[1]!;
          const g = /més gran que (\d)/.exec(text);
          const sm = /més petit que (\d)/.exec(text);
          const fav = g ? 6 - Number(g[1]) : sm ? Number(sm[1]) - 1 : text === "un múltiple de 3" ? 2 : 3;
          want = fav / 6;
        }
        return want !== null && Math.abs(tv.num / tv.den - want) < 1e-9 ? null : "probabilitat";
      }
      case "mult":
        m = /^(\d+) × (\d+)$/.exec(p);
        if (!m) return "forma";
        return Number(m[1]) * Number(m[2]) === Number(t) && Number(m[1]) >= 2 && Number(m[2]) >= 2 ? null : "producte";
      case "equation":
        m = /^(\d+)·x ([+−]) (\d+) = (\d+)\. x = \?$/.exec(p);
        if (m) {
          const x = Number(t);
          const lhs = m[2] === "+" ? Number(m[1]) * x + Number(m[3]) : Number(m[1]) * x - Number(m[3]);
          return Number.isInteger(x) && x > 0 && lhs === Number(m[4]) ? null : "equació";
        }
        m = /^x \+ (\d+) = (\d+)\. x = \?$/.exec(p);
        if (!m) return "forma";
        return Number(t) + Number(m[1]) === Number(m[2]) && Number(t) > 0 ? null : "equació";
      case "sequence": {
        m = /^([\d, ]+), \?$/.exec(p);
        if (!m) return "forma";
        const xs = m[1]!.split(", ").map(Number);
        const d = xs[1]! - xs[0]!;
        if (xs.every((x, i) => i === 0 || x - xs[i - 1]! === d)) return wholeEq(xs[xs.length - 1]! + d, t) ? null : "seqüència";
        const q = xs[1]! / xs[0]!;
        return xs.every((x, i) => i === 0 || x === xs[i - 1]! * q) && wholeEq(xs[xs.length - 1]! * q, t) ? null : "seqüència";
      }
      default:
        return "kind desconegut";
    }
  };

  for (const kind of GEN_KINDS) {
    // mult at its default [1,1] has only 36 products (unordered): it is asked for 50 with [2,1] instead
    const pr = kind === "mult" ? { params: { digits: [2, 1] } } : {};
    const words = generatedWords(`math-m5.flash.${kind}`, { kind, count: 50, ...pr });
    const room = Math.min(50, GEN_ROOM[kind] ?? 50); // a kind with a small vocabulary makes its room, not 50
    check(`${kind}: ${room} words, ids g1…, cards distinct (prompt and figure)`, words.length === room && words.every((w, i) => w.id === `g${i + 1}`) && new Set(words.map((w) => w.prompt + JSON.stringify(w.figure ?? null))).size === room, words.length);
    const bad = (expected.includes(kind) ? words.map((w) => verify(kind, w)) : []).filter((x): x is string => x !== null); // E3 kinds: the figure block below
    check(`${kind}: every result checked with an independent reading`, bad.length === 0, bad.slice(0, 3));
    const dflt = generatedWords(`math-m5.flash.${kind}`, { kind, ...pr });
    check(`${kind}: the default count is 12 and they are the first twelve`, dflt.length === Math.min(12, room) && JSON.stringify(dflt) === JSON.stringify(words.slice(0, 12)));
  }
  check("decComma: 235 with 2 decimals is 2,35; 940 is 9,4; 7 with 2 decimals is 0,07", decComma(235, 2) === "2,35" && decComma(940, 2) === "9,4" && decComma(7, 2) === "0,07" && decComma(42, 0) === "42");
  check("isSimplestText: 3/2 and 1 1/2 are irreducible, 4/2 and 2/4 are not, 0,5 is not a fraction", isSimplestText("3/2") && isSimplestText("1 1/2") && isSimplestText("2") && !isSimplestText("4/2") && !isSimplestText("2/4") && !isSimplestText("0,5") && !isSimplestText("4/1"));
}

console.log("math answer kinds (E1)");
{
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "flash-e1-"));
  try {
    const dir = path.join(tmp, "curriculum", "flash", "math-t2");
    fs.mkdirSync(dir, { recursive: true });
    const put = (name: string, body: unknown) => fs.writeFileSync(path.join(dir, name), JSON.stringify(body));
    put("01-round.json", { id: "math-t2.flash.arrodonir", level: "m5", title: { en: "Round" }, generate: { kind: "round", count: 8 } });
    put("02-items.json", {
      id: "math-t2.flash.items", level: "m5", title: { en: "Items" },
      items: [
        { id: "ok-choice", prompt: "Angle de 135°: agut o obtús?", answer: ["obtús"], answer_kind: "choice", options: ["agut", "recte", "obtús", "pla"] },
        { id: "bad-choice", prompt: "Sí o no?", answer: ["Potser"], answer_kind: "choice", options: ["Sí", "No"] },
        { id: "few-opts", prompt: "Qui?", answer: ["jo"], answer_kind: "choice", options: ["jo"] },
        { id: "simplest-ok", prompt: "Quina fracció?", answer: ["3/8"], answer_kind: "fraction", form: "simplest" },
        { id: "simplest-bad", prompt: "Quina fracció?", answer: ["4/8"], answer_kind: "fraction", form: "simplest" },
        { id: "fraction-bad", prompt: "Quina fracció?", answer: ["vuit"], answer_kind: "fraction" },
        { id: "unit-ok", prompt: "2 km = ? m", answer: ["2000"], answer_kind: "unit", unit: "m" },
        { id: "unit-none", prompt: "2 km = ? m", answer: ["2000"], answer_kind: "unit" },
        { id: "kind-bad", prompt: "Quants?", answer: ["3"], answer_kind: "fruit" },
        { id: "simple-op-bad", prompt: "23 × 4", answer: ["91"], answer_kind: "number" },
      ],
    });
    put("03-both.json", { id: "x", level: "m5", title: { en: "Both" }, generate: { kind: "round" }, items: [] });
    put("04-unknown.json", { id: "math-t2.flash.unknown", level: "m5", title: { en: "Unknown" }, generate: { kind: "nope", count: 4 } });
    const lists = loadFlashLists(tmp, "curriculum/flash/math-*", "ca") as unknown as Array<{ id: string; words: Array<Record<string, unknown>> }>;
    const byId = Object.fromEntries(lists.map((l) => [l.id, l.words]));
    check("a generated list loads with g1…g8 and answer_kind number", (byId["math-t2.flash.arrodonir"] ?? []).length === 8 && (byId["math-t2.flash.arrodonir"] ?? [])[0]?.answer_kind === "number");
    check("an unknown generate kind loads a list with no words; a file with both keys is skipped", (byId["math-t2.flash.unknown"] ?? [{}]).length === 0 && !("x" in byId) && lists.length === 3, Object.keys(byId));
    const items = (byId["math-t2.flash.items"] ?? []) as Array<Record<string, unknown>>;
    check("items: only the valid answer kinds are kept", items.map((w) => w.id).join() === "ok-choice,simplest-ok,unit-ok", items.map((w) => w.id));
    const ids = items.map((w) => w.id);
    check("items: a wrong choice, too few options, a non-fraction, an unknown kind and a wrong sum are dropped", !ids.includes("bad-choice") && !ids.includes("few-opts") && !ids.includes("fraction-bad") && !ids.includes("kind-bad") && !ids.includes("simple-op-bad"), ids);
    check("items: a fraction written as not simplest is dropped when form is simplest", !ids.includes("simplest-bad") && ids.includes("simplest-ok"), ids);
    check("items: a unit item with no unit is dropped", !ids.includes("unit-none") && ids.includes("unit-ok"), ids);
    const choice = items.find((w) => w.id === "ok-choice");
    check("choice word carries options and answer_kind", choice?.answer_kind === "choice" && JSON.stringify(choice?.options) === '["agut","recte","obtús","pla"]' && JSON.stringify(choice?.target) === '["obtús"]', choice);
    const fr = items.find((w) => w.id === "simplest-ok");
    check("fraction word carries its form", fr?.answer_kind === "fraction" && fr?.form === "simplest", fr);
    const un = items.find((w) => w.id === "unit-ok");
    check("unit word carries its unit", un?.answer_kind === "unit" && un?.unit === "m", un);
    check("problems name the seven bad items", mathWords(JSON.parse(fs.readFileSync(path.join(dir, "02-items.json"), "utf8"))).problems.length === 7);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

console.log("answers: fractions, units, choice, thousands (E1)");
check("fraction: equivalent values accepted in value mode (10/16 for 5/8)", C.checkFraction("10/16", ["5/8"], "value").ok === true);
check("fraction: simplest asks for the irreducible form (10/16 no, 5/8 yes)", C.checkFraction("10/16", ["5/8"], "simplest").ok === false && C.checkFraction("5/8", ["5/8"], "simplest").ok === true);
check("fraction: mixed numbers (1 1/2 for 3/2), whole numbers, decimals in value mode", C.checkFraction("1 1/2", ["3/2"], "value").ok && C.checkFraction("2", ["2"], "value").ok && C.checkFraction("0,5", ["1/2"], "value").ok);
check("fraction: simplest accepts 1 1/2 and 2, refuses 2/4, 4/2 and 0,5", C.checkFraction("1 1/2", ["3/2"], "simplest").ok && C.checkFraction("2", ["2"], "simplest").ok && !C.checkFraction("2/4", ["1/2"], "simplest").ok && !C.checkFraction("4/2", ["2"], "simplest").ok && !C.checkFraction("0,5", ["1/2"], "simplest").ok);
check("fraction: denominator 0 is not a valid answer, nor a wrong value", !C.checkFraction("4/0", ["1/2"], "value").ok && !C.checkFraction("1/3", ["1/2"], "value").ok && !C.checkFraction("vuit", ["1/2"], "value").ok);
check("fraction: exact only when written as the target; otherwise the habitual form is shown", C.checkFraction("5/8", ["5/8"], "value").exact === true && C.checkFraction("10/16", ["5/8"], "value").exact === false && C.checkFraction("10/16", ["5/8"], "value").form === "5/8");
check("unit: the unit typed after the number is taken off (3500 m, 3500m)", C.stripUnit("3500 m", "m") === "3500" && C.stripUnit("3500m", "m") === "3500" && C.checkNumber(C.stripUnit("3500 m", "m"), ["3500"]).ok);
check("unit: a wrong unit is still wrong (3500 cm for m); cm² takes cm2 too", !C.checkNumber(C.stripUnit("3500 cm", "m"), ["3500"]).ok && C.stripUnit("2 cm2", "cm²") === "2");
check("choice: the picked option must be the right one, the text exactly", C.checkChoice("<", ["<"]).ok === true && C.checkChoice(">", ["<"]).ok === false && C.checkChoice("sí", ["Sí"]).ok === false);
check("hint: fraction shows the denominator, choice shows none, number keeps the first digit", C.hintFor("fraction", "5/8", null) === "?/8" && C.hintFor("choice", "<", null) === "" && C.hintFor("number", "4735200", null) === "4 _ _ _ _ _ _");
check("outcome: a choice with one option left is revealed at once", C.outcome({ ok: false, misses: 1, exhausted: true }) === "revealed" && C.outcome({ ok: false, misses: 1 }) === null);
check("numbers: 4.735.200 is accepted for 4735200 (more than four digits), 4.735 is not for 4735", C.checkNumber("4.735.200", ["4735200"]).ok === true && C.checkNumber("4.735", ["4735"]).ok === false && C.checkNumber("4735200", ["4735200"]).ok === true);
check("numbers: the comma still means a decimal point (0,25 for 0.25)", C.checkNumber("0,25", ["0,25"]).ok === true);


// ---- E3: figures and pairs (docs/ENCARREC-M5-E3-FIGURES.md §2–§5) ----------
console.log("figures and pairs (E3)");
{
  const goodFigures: unknown[] = [
    { type: "angle", deg: 1 },
    { type: "angle", deg: 360, label: true },
    { type: "triangle", sides: [3, 4, 5], labels: true, unit: "cm" },
    { type: "polygon", sides: [3, 3, 3], regular: true, labels: true },
    { type: "polygon", sides: [2, 7, 11, 4], regular: false, labels: true },
    { type: "rect", w: 8, h: 5, labels: true },
    { type: "circle", mark: "center" },
    { type: "circle", mark: "arc", rot: 359 },
    { type: "bars", labels: ["a", "b"], values: [0, 9], title: "T" },
    { type: "grid", points: [[0, 0], [10, 10]] },
    { type: "grid", points: [[2, 1]], size: 4 },
  ];
  const badFigures: unknown[] = [
    null, "angle", { type: "pie" }, { type: "angle", deg: 0 }, { type: "angle", deg: 361 }, { type: "angle", deg: 90.5 },
    { type: "triangle", sides: [1, 2, 3] }, { type: "triangle", sides: [3, 4] }, { type: "triangle", sides: [3, 4, 0] },
    { type: "polygon", sides: [4, 4] }, { type: "polygon", sides: Array(9).fill(2) }, { type: "polygon", sides: [3, 4, 5], regular: true },
    { type: "rect", w: 0, h: 3 }, { type: "circle", mark: "diagonal" }, { type: "circle", mark: "radius", rot: 360 },
    { type: "bars", labels: [], values: [] }, { type: "bars", labels: ["a", "b"], values: [1] }, { type: "bars", labels: ["a"], values: [-1] },
    { type: "bars", labels: Array(9).fill("x"), values: Array(9).fill(1) },
    { type: "grid", points: [[11, 0]] }, { type: "grid", points: [[1, 1]], size: 11 }, { type: "grid", points: [[1]] },
  ];
  check("checkFigure: the good figures are kept", goodFigures.every((f) => "figure" in checkFigure(f)), goodFigures.filter((f) => !("figure" in checkFigure(f))));
  check("checkFigure: the bad figures are refused with a reason", badFigures.every((f) => "problem" in checkFigure(f) && typeof (checkFigure(f) as { problem: string }).problem === "string"), badFigures.filter((f) => !("problem" in checkFigure(f))));
  const g = checkFigure({ type: "grid", points: [[1, 2]] });
  const a = checkFigure({ type: "angle", deg: 90 });
  const t = checkFigure({ type: "triangle", sides: [2, 2, 2] });
  check("checkFigure: defaults filled in (grid size 10, angle label false, triangle labels false)", "figure" in g && g.figure.type === "grid" && g.figure.size === 10 && "figure" in a && a.figure.type === "angle" && a.figure.label === false && "figure" in t && t.figure.type === "triangle" && t.figure.labels === false, { g, a, t });

  // pairs: the formats of §3, and the order
  for (const [text, want] of [["(3, 4)", [3, 4]], ["3,4", [3, 4]], ["3 4", [3, 4]], ["(3 ; 4)", [3, 4]], [" ( 3 , 4 ) ", [3, 4]], ["(-1, 2)", [-1, 2]]] as const) {
    check(`parsePair accepts ${JSON.stringify(text)}`, JSON.stringify(parsePair(text)) === JSON.stringify(want), parsePair(text));
  }
  for (const text of ["(3, 4", "3, 4)", "3;;4", "3", "(3,4,5)", "a,b", "3.5, 4", "((3,4))", "", "dos tres"]) {
    check(`parsePair refuses ${JSON.stringify(text)}`, parsePair(text) === null, parsePair(text));
  }
  check("parsePair keeps the order: (4,3) is another point", JSON.stringify(parsePair("(4,3)")) === "[4,3]" && JSON.stringify(parsePair("(4,3)")) !== JSON.stringify(parsePair("(3,4)")));
  check("client checkPair: (4,3) is wrong for (3, 4), 3,4 is right and not the habitual form", !C.checkPair("(4,3)", ["(3, 4)"]).ok && C.checkPair("3,4", ["(3, 4)"]).ok && C.checkPair("3,4", ["(3, 4)"]).exact === false && C.checkPair("(3,4)", ["(3, 4)"]).exact === true);
  check("client checkPair: a bad text is wrong; hint shows the first coordinate", !C.checkPair("tres", ["(3, 4)"]).ok && C.hintFor("pair", "(3, 4)", null) === "(3, ?)");
}

console.log("figure generators (E3)");
{
  // A second, plain reading of each figure card (no code shared with the generators).
  const eqPairs = (s: number[]) => (s[0] === s[1] ? 1 : 0) + (s[1] === s[2] ? 1 : 0) + (s[0] === s[2] ? 1 : 0);
  const TRI_NAME: Record<number, string> = { 3: "equilàter", 1: "isòsceles", 0: "escalè" };
  const CIRCLE_CA: Record<string, string> = { radius: "radi", diameter: "diàmetre", chord: "corda", arc: "arc", center: "centre" };
  const verifyFigureCard = (kind: string, w: MathWord): string | null => {
    const f = w.figure as Record<string, any> | undefined;
    const t = w.target[0] ?? "";
    switch (kind) {
      case "angle_type": {
        const d = f?.deg as number;
        const want = d >= 1 && d < 90 ? "agut" : d === 90 ? "recte" : d > 90 && d < 180 ? "obtús" : d === 180 ? "pla" : d === 360 ? "complet" : null;
        const opts = w.options ?? [];
        return want === t && opts.includes(t) && f?.type === "angle" ? null : `angle ${d} → ${want}, ${t}`;
      }
      case "triangle_by_sides": {
        const s = f?.sides as number[];
        const [x = 0, y = 0, z = 0] = s;
        const ok = x + y > z && x + z > y && y + z > x;
        return ok && TRI_NAME[eqPairs(s)] === t && JSON.stringify(w.options) === '["equilàter","isòsceles","escalè"]' ? null : `triangle ${s} → ${t}`;
      }
      case "perimeter_figure": {
        const per = f?.type === "rect" ? 2 * (f.w + f.h) : (f?.sides as number[]).reduce((x, y) => x + y, 0);
        return String(per) === t && w.unit === "cm" && w.answer_kind === "unit" ? null : `perímetre ${per} ≠ ${t}`;
      }
      case "area_figure": {
        if (f?.type === "rect") return String(f.w * f.h) === t && w.unit === "cm²" ? null : "àrea rect";
        const [a, b, c] = [...(f?.sides as number[])].sort((x, y) => x - y) as [number, number, number];
        return a * a + b * b === c * c && String((a * b) / 2) === t && w.unit === "cm²" ? null : "àrea triangle rectangle";
      }
      case "circle_element":
        return CIRCLE_CA[f?.mark] === t && JSON.stringify(w.options) === '["radi","diàmetre","corda","arc","centre"]' ? null : `marca ${f?.mark} → ${t}`;
      case "bars_read": {
        const labels: string[] = f?.labels;
        const values: number[] = f?.values;
        let m: RegExpExecArray | null;
        if ((m = /^Quants alumnes han triat el (.+)\?$/.exec(w.prompt))) return String(values[labels.indexOf(m[1]!)]) === t ? null : "lectura";
        if (w.prompt === "Quin és el color més triat?") {
          const max = Math.max(...values);
          return values.filter((v) => v === max).length === 1 && labels[values.indexOf(max)] === t ? null : "moda";
        }
        const sum = values.reduce((x, y) => x + y, 0);
        return sum % labels.length === 0 && String(sum / labels.length) === t ? null : "mitjana";
      }
      case "grid_point": {
        const p = /^\((\d+), (\d+)\)$/.exec(t);
        const q = f?.points[0] as number[];
        return p && Number(p[1]) === q[0] && Number(p[2]) === q[1] && w.answer_kind === "pair" ? null : `punt ${q} → ${t}`;
      }
      default:
        return "kind";
    }
  };
  for (const kind of ["angle_type", "triangle_by_sides", "perimeter_figure", "area_figure", "circle_element", "bars_read", "grid_point"]) {
    const words = generatedWords(`math-m5.flash.${kind}`, { kind, count: 50 });
    const bad = words.map((w) => verifyFigureCard(kind, w)).filter((x): x is string => x !== null);
    check(`${kind}: every figure card agrees with its figure and answer`, words.length === 50 && bad.length === 0, bad.slice(0, 3));
    check(`${kind}: every card has a figure of its type`, words.every((w) => w.figure !== undefined));
  }
  const angles = generatedWords("math-m5.flash.angle_type", { kind: "angle_type", count: 50, params: { full: true } });
  check("angle_type with full: the option complet is there and 360 is its answer", JSON.stringify(angles[0]?.options) === '["agut","recte","obtús","pla","complet"]' && angles.every((w) => w.options?.length === 5));
  const noFull = generatedWords("math-m5.flash.angle_type", { kind: "angle_type", count: 50 });
  check("angle_type without full: no complet, no reflex angle", noFull.every((w) => w.options?.length === 4 && (w.figure as any).deg <= 180));
}

console.log("explicit figure items (E3)");
{
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "flash-e3-"));
  try {
    const dir = path.join(tmp, "curriculum", "flash", "math-t3");
    fs.mkdirSync(dir, { recursive: true });
    const angleOpts = ["agut", "recte", "obtús", "pla"];
    fs.writeFileSync(path.join(dir, "01-items.json"), JSON.stringify({
      id: "math-t3.flash.figures", level: "m5", title: { en: "Figures" },
      items: [
        { id: "ang-ok", prompt: "Quin tipus d'angle és?", answer: ["agut"], answer_kind: "choice", options: angleOpts, figure: { type: "angle", deg: 45 } },
        { id: "ang-bad", prompt: "Quin tipus d'angle és?", answer: ["recte"], answer_kind: "choice", options: angleOpts, figure: { type: "angle", deg: 45 } },
        { id: "fig-bad", prompt: "Quant fa?", answer: ["12"], answer_kind: "unit", unit: "cm", figure: { type: "polygon", sides: [1, 2] } },
        { id: "per-ok", prompt: "Quin és el perímetre?", answer: ["12"], answer_kind: "unit", unit: "cm", figure: { type: "rect", w: 4, h: 2, labels: true, unit: "cm" } },
        { id: "per-bad", prompt: "Quin és el perímetre?", answer: ["10"], answer_kind: "unit", unit: "cm", figure: { type: "rect", w: 4, h: 2, labels: true, unit: "cm" } },
        { id: "area-bad", prompt: "Quina és l'àrea?", answer: ["9"], answer_kind: "unit", unit: "cm²", figure: { type: "rect", w: 3, h: 4 } },
        { id: "pair-ok", prompt: "Quines coordenades té el punt?", answer: ["(2, 3)"], answer_kind: "pair", figure: { type: "grid", points: [[2, 3]] } },
        { id: "pair-swap", prompt: "Quines coordenades té el punt?", answer: ["(3, 2)"], answer_kind: "pair", figure: { type: "grid", points: [[2, 3]] } },
        { id: "pair-bad", prompt: "Quines coordenades?", answer: ["dos tres"], answer_kind: "pair" },
        { id: "fig-none", prompt: "2 + 2", answer: ["4"] },
      ],
    }));
    const lists = loadFlashLists(tmp, "curriculum/flash/math-*", "ca") as unknown as Array<{ words: Array<Record<string, any>> }>;
    const words = lists[0]?.words ?? [];
    check("explicit items: the right ones are kept, the wrong figure, coherence and pair cases dropped", words.map((w) => w.id).join() === "ang-ok,per-ok,pair-ok,fig-none", words.map((w) => w.id));
    const ang = words.find((w) => w.id === "ang-ok");
    check("a kept figure reaches the client, checked and clean", JSON.stringify(ang?.figure) === '{"type":"angle","deg":45,"label":false}', ang?.figure);
    check("a pair word carries answer_kind pair", words.find((w) => w.id === "pair-ok")?.answer_kind === "pair");
    const probs = mathWords(JSON.parse(fs.readFileSync(path.join(dir, "01-items.json"), "utf8"))).problems;
    check("the report names the figure problems", probs.length === 6 && probs.some((p) => p.includes("figura")) && probs.some((p) => p.includes("coordenades")), probs);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

console.log("figure drawing (E3)");
{
  const samples: Figure[] = [
    { type: "angle", deg: 135, label: false },
    { type: "triangle", sides: [5, 7, 9], labels: true, unit: "cm" },
    { type: "polygon", sides: [4, 4, 4, 4, 4, 4], regular: true, labels: true },
    { type: "rect", w: 8, h: 5, labels: true, unit: "cm" },
    { type: "circle", mark: "chord", rot: 30 },
    { type: "bars", labels: ["vermell", "blau"], values: [9, 0], title: "Alumnes" },
    { type: "grid", points: [[3, 4]], size: 10, min: 0, max: 10 },
  ];
  for (const f of samples) {
    const svg = C.figureSvg(f) as string;
    check(`${f.type}: an inline svg with role img and a Catalan aria-label, no hex colours`, /^<svg class="flash-fig-svg" viewBox="[^"]+" role="img" aria-label="[^"]+"/.test(svg) && !/#[0-9a-fA-F]{3,6}\b/.test(svg), svg.slice(0, 120));
  }
  check("no figure, no svg", C.figureSvg(undefined) === "" && C.figureSvg(null) === "");
  const angleSvg = C.figureSvg({ type: "angle", deg: 135, label: false }) as string;
  check("an angle without label shows no degrees (no ° and no number in the aria)", !angleSvg.includes("°") && !/aria-label="[^"]*\d/.test(angleSvg));
  check("an angle with label shows the degrees", (C.figureSvg({ type: "angle", deg: 135, label: true }) as string).includes("135°"));
  check("a circle's aria does not name the marked element", /aria-label="Cercle amb un element marcat"/.test(C.figureSvg({ type: "circle", mark: "radius", rot: 0 })));
  check("labels are escaped inside the svg", (C.figureSvg({ type: "bars", labels: ["<b>x</b>"], values: [1] }) as string).includes("&lt;b&gt;x&lt;/b&gt;") && !(C.figureSvg({ type: "bars", labels: ["<b>x</b>"], values: [1] }) as string).includes("<b>"));
  const flashSrc = read("web", "flash.js");
  check("the card shows the figure above the prompt and the pair input has its own label", flashSrc.includes('C.figureSvg(card.figure)}</div>') && flashSrc.includes('flash-fig--wide') && flashSrc.indexOf("flash-fig\">") < flashSrc.indexOf('<div class="flash-word">') && flashSrc.includes('aria-label="Coordenades"'));
  const styleSrc = read("web", "style.css");
  check("style.css: the figure uses the flash tokens, sized for phones", styleSrc.includes(".flash-fig-svg") && styleSrc.includes("max-height: 260px") && styleSrc.includes("min(280px, 100%)") && styleSrc.includes("stroke: currentColor"));
  // E4 §3: a size label sits outside its figure (on the outward normal of its side), inside the drawing box.
  {
    const texts = (svg: string) => [...svg.matchAll(/<text class="fig-text" x="([-\d.]+)" y="([-\d.]+)"/g)].map((m) => [Number(m[1]), Number(m[2])]);
    const vb = (svg: string) => (svg.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/) ?? []).slice(1).map(Number);
    const inPoly = (pts: number[][], x: number, y: number) => {
      let c = false;
      for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        const [xi, yi] = pts[i] as number[];
        const [xj, yj] = pts[j] as number[];
        if ((yi! > y) !== (yj! > y) && x < ((xj! - xi!) * (y - yi!)) / (yj! - yi!) + xi!) c = !c;
      }
      return c;
    };
    const polyOf = (svg: string) => (svg.match(/<polygon class="fig-line" points="([^"]+)"/)?.[1] ?? "").split(" ").map((p) => p.split(",").map(Number));
    const inBox = (svg: string, [x, y]: number[]) => { const [W, H] = vb(svg); return x! >= 0 && y! >= 0 && x! <= W! && y! <= H!; };
    const cases: Array<[string, any]> = [
      ["triangle 5-7-9", { type: "triangle", sides: [5, 7, 9], labels: true, unit: "cm" }],
      ["triangle equilateral 12", { type: "triangle", sides: [12, 12, 12], labels: true, unit: "cm" }],
      ["triangle 3-4-5", { type: "triangle", sides: [3, 4, 5], labels: true, unit: "cm" }],
      ["square 4 sides of 10", { type: "polygon", sides: [10, 10, 10, 10], regular: true, labels: true, unit: "cm" }],
      ["hexagon 12", { type: "polygon", sides: [12, 12, 12, 12, 12, 12], regular: true, labels: true, unit: "cm" }],
    ];
    for (const [name, f] of cases) {
      const svg = C.figureSvg(f) as string;
      const ts = texts(svg);
      const poly = polyOf(svg);
      check(`${name}: one size label per side, all outside the figure and inside the drawing`, ts.length === f.sides.length && ts.every(([x, y]) => !inPoly(poly, x!, y!) && inBox(svg, [x!, y!])), ts);
    }
    const rect = C.figureSvg({ type: "rect", w: 20, h: 8, labels: true, unit: "cm" }) as string;
    const r = (rect.match(/<rect class="fig-line" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"/) ?? []).slice(1).map(Number);
    const rt = texts(rect);
    const outsideRect = rt.every(([x, y]) => x! < r[0]! || x! > r[0]! + r[2]! || y! < r[1]! || y! > r[1]! + r[3]!);
    check("rect: the width label is above the top edge and the height label to the right, both outside the rectangle", rt.length === 2 && outsideRect && rt[0]![1]! < r[1]! && rt[1]![0]! > r[0]! + r[2]! && rt.every(([x, y]) => inBox(rect, [x!, y!])), { r, rt });
  }
  const cardSrc = flashSrc;
  check("flash.js: the card says Tria for a choice, Escriu les coordenades for a pair, Calcula otherwise", cardSrc.includes('choice ? "Tria" : card.kind === "pair" ? "Escriu les coordenades"') && cardSrc.includes(': "Calcula"') && !cardSrc.includes("Tria la resposta"));
  check("flash.js: an enunciat longer than 40 characters puts flash-long on the stage (smaller word)", cardSrc.includes('card.prompt.length > 40 ? " flash-long" : ""') && styleSrc.includes(".flash-stage.flash-long .flash-word"));
}

// ---- wiring ----------------------------------------------------------------
console.log("wiring");
const http = read("server", "src", "http.ts");
const app = read("web", "app.js");
const index = read("web", "index.html");
const css = read("web", "style.css");
const flashJs = read("web", "flash.js");
check("http.ts injects window.__FLOWED_FLASH", http.includes("window.__FLOWED_FLASH=${flashOn}"));
check("http.ts serves GET /api/flash/lists", http.includes('p === "/api/flash/lists"'));
check("index.html has the Flash button after Review and loads flash.js",
  /data-cmd="math-review"[\s\S]*data-cmd="math-flash"/.test(index) && index.includes('src="/flash.js"'));
check("app.js hides Flash unless __FLOWED_FLASH", app.includes("!window.__FLOWED_FLASH"));
check("app.js: Flash after Review in the language bar", app.includes('"math-review", "math-flash"'));
check("app.js: Flash toggles the drill, no agent turn", app.includes('b.dataset.cmd === "math-flash"') && app.includes("toggleFlash();"));
check("app.js: any other bar button closes Flash first", app.includes("closeFlash();"));
check("style.css: Flash sits under the header (top: var(--header-h)), no inset/z above it", /\.flash-screen \{[^}]*top: var\(--header-h/.test(css) && !/\.flash-screen \{[^}]*inset: 0/.test(css));
check("style.css: --header-h has a :root default", /:root \{[\s\S]*--header-h:/.test(css));
// The chat trace is the only thing that must stay off the agent and the server (v0.1 §6).
const traceSrc = flashJs.slice(flashJs.indexOf("function appendTrace"), flashJs.indexOf("// ---- entrada"));
check("flash.js: the chat trace never goes through send() or the server", traceSrc.length > 0 && !/\bsend\(/.test(traceSrc) && !/\bapi\(|fetch\(/.test(traceSrc));
check("http.ts serves GET and PUT /api/flash/state", http.includes('p === "/api/flash/state"') && http.includes("saveFlashState(opts.root"));
check("flash.js saves progress with PUT /flash/state and reads it on open", flashJs.includes('api("/flash/state", { method: "PUT"') && flashJs.includes('api("/flash/state")'));
check("flash.js: math cards are a number answer (numeric keyboard, Calcula, no direction)", flashJs.includes('inputmode="numeric" aria-label="Resultat"') && flashJs.includes('"Calcula"') && flashJs.includes("checkNumber(text, card.accepted)") && flashJs.includes("lists.every(isMath)"));
check("flash.js: a finished round (not a review) is counted for the day", /if \(!r\.repassa\) \{[\s\S]*countRound\(state, today\(\)\)/.test(flashJs));
check("app.js: ⚡ reminder reuses renderSkillBadge with a target of 1, refreshed on load and on close",
  app.includes("async function refreshFlashBadge()") && app.includes('{ total: 1, pending: done >= 1 ? 0 : 1 }') && app.includes("refreshFlashBadge();\n  lastActivity") && flashJs.includes("refreshFlashBadge()"));
check("index.html: the Flash button carries the skill-badge class and a badge", /data-cmd="math-flash" class="skill-badge"[^>]*>[^<]*<span>Flash<\/span><span class="badge" hidden>/.test(index));
check("app.js: the path shows a Flash row from the server's flash block", app.includes("function pathFlashRow(f)") && app.includes("${pathFlashRow(p.flash)}"));

// ---- m7 (docs/ENCARREC-M7-E5-FLASH.md): the answer kinds, the figures and the 35 generators --------
// The arithmetic of each card is read again here with its own evaluator and its own regexes (no code of
// server/src/flash.ts): exact rationals in BigInt, a small expression parser, a numeric check of the algebra,
// a geometric check of the parallels (dot products of the drawn rays), and an enumeration for the probabilities.
console.log("m7 (E5)");
{
  type Q = [bigint, bigint];
  const gcdB = (a: bigint, b: bigint): bigint => {
    let x = a < 0n ? -a : a;
    let y = b < 0n ? -b : b;
    while (y) [x, y] = [y, x % y];
    return x;
  };
  const qn = (n: bigint, d: bigint = 1n): Q => {
    if (d === 0n) throw new Error("denominator 0");
    const s = d < 0n ? -1n : 1n;
    const g = gcdB(n, d) || 1n;
    return [(s * n) / g, (s * d) / g];
  };
  const qAdd = (x: Q, y: Q): Q => qn(x[0] * y[1] + y[0] * x[1], x[1] * y[1]);
  const qSub = (x: Q, y: Q): Q => qn(x[0] * y[1] - y[0] * x[1], x[1] * y[1]);
  const qMul = (x: Q, y: Q): Q => qn(x[0] * y[0], x[1] * y[1]);
  const qDiv = (x: Q, y: Q): Q => qn(x[0] * y[1], x[1] * y[0]);
  const qEq = (x: Q | null, y: Q | null): boolean => x !== null && y !== null && x[0] === y[0] && x[1] === y[1];
  const minus = (s: string) => s.replace(/−/g, "-");

  // an integer, a decimal with a comma or point, or a fraction n/d, all with the unicode minus, as Q
  const readQ = (text: string): Q | null => {
    const t = minus(text.trim());
    let m: RegExpExecArray | null;
    if ((m = /^(-?)(\d+)\/(\d+)$/.exec(t))) return qn(BigInt(m[1] ? `-${m[2]}` : m[2]!), BigInt(m[3]!));
    if ((m = /^(-?)(\d+)(?:[,.](\d+))?$/.exec(t))) {
      const frac = m[3] ?? "";
      const n = BigInt(`${m[2]}${frac}`);
      return qn(m[1] ? -n : n, 10n ** BigInt(frac.length));
    }
    return null;
  };

  // an arithmetic expression: + − · × * / : ^ (integer power), brackets [ ] and ( ), unary signs, superscripts
  const evalQ = (src: string): Q | null => {
    const s = minus(src).replace(/\s+/g, "").replace(/[·×]/g, "*").replace(/:/g, "/").replace(/\[/g, "(").replace(/\]/g, ")")
      .replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹]+/g, (sup) => `^${[...sup].map((c) => "⁰¹²³⁴⁵⁶⁷⁸⁹".indexOf(c)).join("")}`);
    const toks = s.match(/\d+|[-+*/()^]/g);
    if (!toks || toks.join("") !== s) return null;
    let i = 0;
    const fail = (): never => {
      throw new Error("expr");
    };
    const atom = (): Q => {
      const t = toks[i++];
      if (t === "(") {
        const v = expr();
        if (toks[i++] !== ")") fail();
        return v;
      }
      if (t && /^\d+$/.test(t)) return qn(BigInt(t));
      return fail();
    };
    const unary = (): Q => {
      if (toks[i] === "-") {
        i++;
        return qMul(qn(-1n), unary());
      }
      if (toks[i] === "+") {
        i++;
        return unary();
      }
      const base = atom();
      if (toks[i] === "^") {
        i++;
        const e = Number(toks[i++]);
        let out = qn(1n);
        for (let k = 0; k < e; k++) out = qMul(out, base);
        return out;
      }
      return base;
    };
    const term = (): Q => {
      let v = unary();
      while (toks[i] === "*" || toks[i] === "/") {
        const op = toks[i++];
        const w = unary();
        if (op === "*") v = qMul(v, w);
        else {
          if (w[0] === 0n) fail();
          v = qDiv(v, w);
        }
      }
      return v;
    };
    const expr = (): Q => {
      let v = term();
      while (toks[i] === "+" || toks[i] === "-") {
        const op = toks[i++];
        const w = term();
        v = op === "+" ? qAdd(v, w) : qSub(v, w);
      }
      return v;
    };
    try {
      const v = expr();
      return i === toks.length ? v : null;
    } catch {
      return null;
    }
  };

  // an algebraic text as a JavaScript function of the letters: implicit products made explicit
  const algFn = (text: string) => {
    let s = minus(text).replace(/[·×]/g, "*").replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹]+/g, (sup) => `**${[...sup].map((c) => "⁰¹²³⁴⁵⁶⁷⁸⁹".indexOf(c)).join("")}`);
    s = s.replace(/\s+/g, "").replace(/(\d)([a-z(])/g, "$1*$2").replace(/\)([a-z(])/g, ")*$1").replace(/([a-z])\(/g, "$1*(").replace(/([a-z])(?=[a-z])/g, "$1*");
    s = s.replace(/(\*\*\d+)([a-z])/g, "$1*$2");
    return new Function("x", "y", "a", "b", `return (${s});`) as (x: number, y: number, a: number, b: number) => number;
  };
  const SAMPLES: Array<[number, number, number, number]> = [[2, 3, 5, -7], [-1, 4, 2, 3], [3, -2, -4, 6]];
  const sameAlg = (p: string, q: string): boolean => {
    const f = algFn(p);
    const g = algFn(q);
    return SAMPLES.every(([x, y, a, b]) => Math.abs(f(x, y, a, b) - g(x, y, a, b)) < 1e-9);
  };

  // the factors of n by trial division, as [prime, count]
  const factorsOf = (n: number): Array<[number, number]> => {
    const out: Array<[number, number]> = [];
    let m = n;
    for (let p = 2; p <= m; p++) {
      let e = 0;
      while (m % p === 0) {
        m /= p;
        e++;
      }
      if (e) out.push([p, e]);
    }
    return out;
  };
  const euclid = (a: number, b: number): number => (b === 0 ? a : euclid(b, a % b));
  const isPrimeT = (n: number): boolean => n >= 2 && factorsOf(n).length === 1 && factorsOf(n)[0]![1] === 1;

  // the digits of p/q by long division (first `count`), and whether it ends
  const digitsOf = (p: number, q: number, count: number): { digits: string; ends: boolean } => {
    let rem = p;
    let out = "";
    for (let i = 0; i < count && rem !== 0; i++) {
      rem *= 10;
      out += Math.floor(rem / q);
      rem %= q;
    }
    return { digits: out, ends: rem === 0 };
  };
  // a decimal of a terminating rational as text with a comma (fails when it does not end)
  const decText = (v: Q): string | null => {
    let d = v[1];
    let twos = 0;
    let fives = 0;
    while (d % 2n === 0n) {
      d /= 2n;
      twos++;
    }
    while (d % 5n === 0n) {
      d /= 5n;
      fives++;
    }
    if (d !== 1n) return null;
    const k = Math.max(twos, fives);
    const scaled = (v[0] * 10n ** BigInt(k)) / v[1];
    const str = (scaled < 0n ? -scaled : scaled).toString().padStart(k + 1, "0");
    const int = str.slice(0, str.length - k);
    const frac = k ? str.slice(str.length - k).replace(/0+$/, "") : "";
    return (scaled < 0n ? "−" : "") + int + (frac ? `,${frac}` : "");
  };
  const supNum = (s: string) => Number([...s].map((c) => "⁰¹²³⁴⁵⁶⁷⁸⁹".indexOf(c)).join(""));

  // units of area, volume and capacity: power of ten of each, against the base unit (the m², m³ or the litre)
  const UNIT_EXP: Record<string, number> = {
    "km²": 6, "hm²": 4, "dam²": 2, "m²": 0, "dm²": -2, "cm²": -4, "mm²": -6,
    "m³": 3, "dm³": 0, "cm³": -3, "l": 0, "ml": -3,
  };
  const KINDS = ["qualitativa", "quantitativa discreta", "quantitativa contínua"];
  const STATS: Record<string, string> = {
    "Nombre de germans": "quantitativa discreta", "Color preferit": "qualitativa", "Alçada": "quantitativa contínua",
    "Nombre de llibres a la biblioteca": "quantitativa discreta", "Temperatura de l'aigua": "quantitativa contínua",
    "Estat civil": "qualitativa", "Pes d'un paquet": "quantitativa contínua", "Marca de cotxe": "qualitativa",
    "Nombre de gols d'un partit": "quantitativa discreta", "Temps de viatge": "quantitativa contínua",
  };
  const DIRECT = ["Kg de pomes i preu pagat", "Hores de feina i diners guanyats (mateix salari)", "Litres de benzina i quilòmetres recorreguts", "Nombre de llibres comprats i cost total"];
  const INVERSE = ["Nombre d'obrers i dies per acabar una obra", "Velocitat i temps per fer el mateix trajecte", "Nombre de persones i dies que duren les provisions", "Nombre de grifs i temps per omplir una piscina"];
  const NOTABLE: Record<string, string> = {
    "Punt on es tallen les mediatrius": "circumcentre", "Punt on es tallen les bisectrius": "incentre",
    "Punt on es tallen les medianes": "baricentre", "Punt on es tallen les altures": "ortocentre",
    "Centre de la circumferència que passa pels tres vèrtexs": "circumcentre",
    "Centre de la circumferència inscrita en el triangle": "incentre", "Punt de gravetat del triangle": "baricentre",
    "Punt on es tallen les altures del triangle, o les seves prolongacions": "ortocentre",
  };
  const POLY_N: Record<string, number> = { triangle: 3, quadrilàter: 4, pentàgon: 5, hexàgon: 6, heptàgon: 7, octàgon: 8, eneàgon: 9, decàgon: 10 };
  // the 8 places of a parallels figure, by the drawing: the ray pair of each sector (L, R, D = down-right, −D)
  const sectorDeg = (alphaDeg: number, place: number): number => {
    const a = (alphaDeg * Math.PI) / 180;
    const D = [Math.cos(a), Math.sin(a)];
    const L = [-1, 0];
    const R = [1, 0];
    const mD = [-D[0]!, -D[1]!];
    const pairs = [[L, mD], [R, mD], [L, D], [R, D]][(place - 1) % 4] as number[][];
    const dot = (u: number[], v: number[]) => u[0]! * v[0]! + u[1]! * v[1]!;
    return (Math.acos(Math.max(-1, Math.min(1, dot(pairs[0]!, pairs[1]!)))) * 180) / Math.PI;
  };

  // the independent reading of each generated card: null when it is right, else what is wrong
  const verifyE5 = (kind: string, w: MathWord): string | null => {
    const p = w.prompt;
    const t = w.target[0] ?? "";
    const fig = w.figure;
    let m: RegExpExecArray | null;
    const got = readQ(t);
    switch (kind) {
      case "int_signs":
      case "int_combined":
        return qEq(evalQ(p), got) ? null : `${p} ≠ ${t}`;
      case "abs_opp": {
        if (p.startsWith("|")) {
          const inner = evalQ(p.slice(1, p.indexOf("|", 1)));
          return inner && qEq(qn(inner[0] < 0n ? -inner[0] : inner[0], inner[1]), got) ? null : `|…| ${t}`;
        }
        const x = evalQ(p.replace("Oposat de ", ""));
        return x && qEq(qn(-x[0], x[1]), got) ? null : `oposat ${t}`;
      }
      case "prime_factors": {
        const n = Number(/Descompon (\d+)/.exec(p)?.[1]);
        const f = factorsOf(n);
        const text = f.map(([q, e]) => (e > 1 ? `${q}^${e}` : `${q}`)).join("·");
        return text === t && f.every(([q]) => isPrimeT(q)) ? null : `factors de ${n}: ${text} ≠ ${t}`;
      }
      case "gcd_lcm": {
        m = /(MCD|mcm)\((\d+), (\d+)\)/.exec(p);
        if (!m) return "forma";
        const a = Number(m[2]);
        const b = Number(m[3]);
        const want = m[1] === "MCD" ? euclid(a, b) : (a * b) / euclid(a, b);
        return String(want) === t ? null : `${p} → ${want}`;
      }
      case "frac_simplify": {
        m = /Simplifica (\d+)\/(\d+)/.exec(p);
        if (!m) return "forma";
        const value = qn(BigInt(m[1]!), BigInt(m[2]!));
        return qEq(value, readQ(t)) && euclid(Number(t.split("/")[0]), Number(t.split("/")[1])) === 1 ? null : `${p} ≠ ${t}`;
      }
      case "frac_combined":
        return qEq(evalQ(p), got) ? null : `${p} ≠ ${t}`;
      case "decimal_type": {
        m = /0,([\d]+)(…)?/.exec(p);
        if (!m) return "forma";
        const shown = m[1]!;
        const periodic = m[2] !== undefined;
        const classes = new Set<string>();
        for (let q = 2; q <= 25; q++) {
          for (let n = 1; n < q; n++) {
            const { digits, ends } = digitsOf(n, q, periodic ? 4 : 6);
            if (periodic ? digits !== shown : !(ends && digits === shown)) continue;
            const d = q / euclid(n, q);
            let rest = d;
            while (rest % 2 === 0) rest /= 2;
            while (rest % 5 === 0) rest /= 5;
            classes.add(rest === 1 ? "exacte" : d % 2 === 0 || d % 5 === 0 ? "periòdic mixt" : "periòdic pur");
          }
        }
        return classes.has(t) ? null : `${shown} as ${t}? ${[...classes]}`;
      }
      case "generatrix": {
        m = /^(\d+),(\d+) = \?$/.exec(p);
        if (!m) return "forma";
        const v = readQ(`${m[1]},${m[2]}`);
        const want = v ? `${v[0]}/${v[1]}` : "";
        return qEq(v, got) && euclid(Number(t.split("/")[0]), Number(t.split("/")[1] ?? 1)) === 1 ? null : `${p} → ${want}`;
      }
      case "power_props": {
        let a: number;
        let b: number;
        let e: number;
        if ((m = /^(\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+) · (\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+) = (\d)\^\?$/.exec(p))) {
          e = supNum(m[2]!) + supNum(m[4]!);
          return String(e) === t && Number(m[1]) === Number(m[3]) && Number(m[1]) === Number(m[5]) ? null : p;
        }
        if ((m = /^\((\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)\)([⁰¹²³⁴⁵⁶⁷⁸⁹]+) = (\d)\^\?$/.exec(p))) {
          e = supNum(m[2]!) * supNum(m[3]!);
          return String(e) === t && Number(m[1]) === Number(m[4]) ? null : p;
        }
        if ((m = /^(\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+) : (\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+) = (\d)\^\?$/.exec(p))) {
          e = Math.abs(supNum(m[2]!) - supNum(m[4]!));
          return String(e) === t && Number(m[1]) === Number(m[3]) && Number(m[1]) === Number(m[5]) ? null : p;
        }
        if ((m = /^(\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+) · (\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+) = \?\^(\d)$/.exec(p))) {
          a = Number(m[1]);
          b = Number(m[3]);
          const k = Number(m[5]);
          return supNum(m[2]!) === k && supNum(m[4]!) === k && String(a * b) === t ? null : p;
        }
        return "forma";
      }
      case "int_sqrt": {
        m = /de (\d+) i residu/.exec(p);
        const pair = /^\((\d+), (\d+)\)$/.exec(t);
        if (!m || !pair) return "forma";
        const n = Number(m[1]);
        const s = Number(pair[1]);
        const r = Number(pair[2]);
        return s * s + r === n && r >= 0 && r <= 2 * s ? null : `${n}: ${t}`;
      }
      case "translate_expr": {
        const rules: Array<[RegExp, (k: number) => string]> = [
          [/doble d'un nombre més (\d+)$/, (k) => `2x + ${k}`],
          [/triple d'un nombre menys (\d+)$/, (k) => `3x − ${k}`],
          [/meitat d'un nombre augmentada en (\d+)$/, (k) => `x/2 + ${k}`],
          [/quadrat d'un nombre menys (\d+)$/, (k) => `x² − ${k}`],
          [/suma d'un nombre i el seu doble, més (\d+)$/, (k) => `3x + ${k}`],
          [/disminuït en (\d+) i multiplicat per 2$/, (k) => `2(x − ${k})`],
          [/^Un nombre dividit per (\d+)$/, (k) => `x/${k}`],
          [/^Un nombre més (\d+) vegades el mateix nombre$/, (k) => `${k + 1}x`],
        ];
        for (const [re, expect] of rules) {
          const hit = re.exec(p);
          if (hit) {
            if (expect(Number(hit[1])) !== t) return `${p} → ${expect(Number(hit[1]))}`;
            const opts = w.options ?? [];
            return opts.length === 4 && new Set(opts).size === 4 && opts.includes(t) ? null : `opcions ${JSON.stringify(opts)}`;
          }
        }
        return `frase sense regla: ${p}`;
      }
      case "value_expr": {
        m = /^(\d+)x ([+−]) (\d+) per a x = (−?\d+)$/.exec(p);
        if (!m) return "forma";
        const v = Number(minus(m[4]!));
        const want = Number(m[1]) * v + (m[2] === "+" ? 1 : -1) * Number(m[3]);
        return String(want) === minus(t) ? null : `${p} → ${want}`;
      }
      case "monomial_parts": {
        m = /^(Grau de|Coeficient de) (−?)(\d*)([a-z⁰¹²³⁴⁵⁶⁷⁸⁹]*)$/.exec(p);
        if (!m) return "forma";
        const exps = [...m[4]!.matchAll(/[a-z]([⁰¹²³⁴⁵⁶⁷⁸⁹]*)/g)].map((x) => (x[1] ? supNum(x[1]) : 1));
        const coef = (m[2] ? -1 : 1) * Number(m[3] || 1);
        const want = m[1] === "Grau de" ? String(exps.reduce((s, e) => s + e, 0)) : String(coef);
        return want === minus(t) ? null : `${p} → ${want}`;
      }
      case "monomial_ops":
      case "linear_eq": {
        if (kind === "monomial_ops") {
          return SAMPLES.every(([x, y, a, b]) => Math.abs(algFn(p)(x, y, a, b) - algFn(t)(x, y, a, b)) < 1e-9) ? null : `${p} ≠ ${t}`;
        }
        const parts = p.replace(". Quant val x?", "").split(" = ");
        const x0 = Number(minus(t));
        const left = algFn(parts[0]!)(x0, 0, 0, 0);
        const right = algFn(parts[1]!)(x0, 0, 0, 0);
        return Number.isInteger(x0) && Math.abs(left - right) < 1e-9 ? null : `${p} amb x = ${t}`;
      }
      case "proportion_type":
        return (DIRECT.some((x) => p.startsWith(x)) ? "directa" : INVERSE.some((x) => p.startsWith(x)) ? "inversa" : "?") === t ? null : p;
      case "rule_of_three": {
        m = /^Si (\d+) llibres costen (\d+) €, quant costen (\d+) llibres\?$/.exec(p);
        if (m) return qEq(qn(BigInt(m[2]!) * BigInt(m[3]!), BigInt(m[1]!)), got) ? null : p;
        m = /^Si (\d+) obrers fan una feina en (\d+) dies, quants dies trigaran (\d+) obrers\?$/.exec(p);
        if (!m) return "forma";
        const prod = Number(m[1]) * Number(m[2]);
        return prod % Number(m[3]) === 0 && String(prod / Number(m[3])) === t ? null : p;
      }
      case "chained_percent": {
        m = /^(\d+) €, puja un (\d+) % i baixa un (\d+) %/.exec(p);
        if (!m) return "forma";
        const v = qn(BigInt(m[1]!) * BigInt(100 + Number(m[2])) * BigInt(100 - Number(m[3])), 10n ** 4n);
        return decText(v) === t ? null : `${p} → ${decText(v)}`;
      }
      case "quadrant_point": {
        const pr = /^\((−?\d+), (−?\d+)\)$/.exec(t);
        const f0 = fig && fig.type === "grid" ? fig.points[0] : undefined;
        return pr && f0 && Number(minus(pr[1]!)) === f0[0] && Number(minus(pr[2]!)) === f0[1] ? null : `${t} vs ${f0}`;
      }
      case "linear_func": {
        m = /^y = (.+)\. Quant val y per a x = (−?\d+)\?$/.exec(p);
        if (!m) return "forma";
        const x = Number(minus(m[2]!));
        return algFn(m[1]!)(x, 0, 0, 0) === Number(minus(t)) ? null : `${p} → ${algFn(m[1]!)(x, 0, 0, 0)}`;
      }
      case "line_read": {
        if (!fig || fig.type !== "grid" || !fig.line) return "figura";
        const want = /pendent/.test(p) ? fig.line.m : fig.line.n;
        return String(want) === minus(t) ? null : `${p} → ${want}`;
      }
      case "pythagoras": {
        if (!fig || fig.type !== "right_triangle") return "figura";
        const hyp = fig.a * fig.a + fig.b * fig.b === fig.c * fig.c;
        const legs = fig.a < fig.c && fig.b < fig.c;
        return hyp && legs && String(fig[fig.ask]) === t ? null : `${t} vs ${fig[fig.ask]}`;
      }
      case "parallel_angles": {
        if (!fig || fig.type !== "parallels") return "figura";
        const alpha = [fig.angle, 180 - fig.angle].find((a) => Math.abs(sectorDeg(a, fig.known) - fig.angle) < 1e-6);
        if (alpha === undefined) return "angle conegut";
        return Math.abs(sectorDeg(alpha, fig.ask) - Number(t)) < 1e-6 ? null : `${t} vs ${sectorDeg(alpha, fig.ask)}`;
      }
      case "polygon_angle_sum": {
        m = /d'un ([^\s?]+)\??$/.exec(p);
        const n = m ? POLY_N[m[1]!] : undefined;
        return n !== undefined && String((n - 2) * 180) === t ? null : `${p} → ${t}`;
      }
      case "notable_points": {
        const want = NOTABLE[p];
        return want === t ? null : `${p} → ${want}`;
      }
      case "composite_area": {
        m = /^Corona circular de radis (\d+) cm i (\d+) cm \(π = 3,14\)$/.exec(p);
        if (m) {
          const R = BigInt(m[1]!);
          const r = BigInt(m[2]!);
          return decText(qn(314n * (R * R - r * r), 100n)) === t ? null : p;
        }
        m = /^Sector de (\d+)° de radi (\d+) cm \(π = 3,14\)$/.exec(p);
        if (!m) return "forma";
        const v = qn(314n * BigInt(m[2]!) * BigInt(m[2]!) * BigInt(m[1]!), 36000n);
        return decText(v) === t ? null : `${p} → ${decText(v)}`;
      }
      case "unit_area_volume": {
        m = /^(\d+(?:,\d+)?) (\S+) = \? (\S+)$/.exec(p);
        if (!m) return "forma";
        const x = readQ(m[1]!);
        const shift = (UNIT_EXP[m[2]!] ?? 0) - (UNIT_EXP[m[3]!] ?? 0); // x ua = x·10^shift ub
        if (x === null) return "forma";
        const value = shift >= 0 ? qMul(x, qn(10n ** BigInt(shift))) : qDiv(x, qn(10n ** BigInt(-shift)));
        return decText(value) === t ? null : `${p} → ${decText(value)}`;
      }
      case "speed_convert": {
        m = /^(\d+) km\/h = \? m\/s$/.exec(p);
        if (m) return qEq(qn(BigInt(m[1]!) * 1000n, 3600n), got) ? null : p;
        m = /^Densitat (\d+) g\/cm³ i volum (\d+) cm³\. Massa = \? g$/.exec(p);
        return m && String(Number(m[1]) * Number(m[2])) === t ? null : p;
      }
      case "sexagesimal_ops": {
        const toMin = (s: string): number | null => {
          let h = /^(\d+) h(?: (\d+) min)?$/.exec(s);
          if (h) return Number(h[1]) * 60 + Number(h[2] ?? 0);
          h = /^(\d+) min$/.exec(s);
          if (h) return Number(h[1]);
          h = /^(\d+)°(?: (\d+)')?$/.exec(s);
          return h ? Number(h[1]) * 60 + Number(h[2] ?? 0) : null;
        };
        const ops = /^(.+) (×|−|\+|:) (.+)$/.exec(p);
        if (!ops) return "forma";
        const a = toMin(ops[1]!);
        const b = ops[2] === "×" || ops[2] === ":" ? Number(ops[3]) : toMin(ops[3]!);
        if (a === null || b === null) return "forma";
        const want = ops[2] === "×" ? a * b : ops[2] === ":" ? a / b : ops[2] === "+" ? a + b : a - b;
        const res = toMin(t);
        const angle = /°/.test(t);
        return res === want && (angle === /°/.test(ops[1]!)) && (ops[2] === ":" ? a % b === 0 : true) ? null : `${p} → ${t}`;
      }
      case "variable_type":
        return STATS[/«(.+)»/.exec(p)?.[1] ?? ""] === t && KINDS.includes(t) ? null : p;
      case "freq_relative": {
        m = /^(\d+) alumnes, (\d+) (?:tenen|té) gos/.exec(p);
        return m && qEq(qn(BigInt(m[2]!), BigInt(m[1]!)), got) ? null : p;
      }
      case "median": {
        const vals = p.replace("Mediana de ", "").split(", ").map(Number).sort((x, y) => x - y);
        const n = vals.length;
        const med = n % 2 ? vals[(n - 1) / 2]! : (vals[n / 2 - 1]! + vals[n / 2]!) / 2;
        return String(med) === t ? null : `${p} → ${med}`;
      }
      case "weighted_mean": {
        const pairs = [...p.matchAll(/(\d+) \(pes (\d+)\)/g)];
        const S = pairs.reduce((s, x) => s + Number(x[1]) * Number(x[2]), 0);
        const W = pairs.reduce((s, x) => s + Number(x[2]), 0);
        return qEq(qn(BigInt(S), BigInt(W)), got) ? null : `${p} → ${S}/${W}`;
      }
      case "laplace": {
        const die = [1, 2, 3, 4, 5, 6];
        const pairs = die.flatMap((x) => die.map((y) => [x, y] as const));
        const cnt = (pr: (x: number, y: number) => boolean, all: number) => pairs.filter(([x, y]) => pr(x, y)).length;
        let fav: number;
        let total: number;
        if (/^Dos daus: probabilitat que la suma sigui 7$/.test(p)) [fav, total] = [cnt((x, y) => x + y === 7, 36), 36];
        else if (/la suma sigui 2$/.test(p)) [fav, total] = [cnt((x, y) => x + y === 2, 36), 36];
        else if (/més gran que 10$/.test(p)) [fav, total] = [cnt((x, y) => x + y > 10, 36), 36];
        else if (/els dos nombres siguin iguals$/.test(p)) [fav, total] = [cnt((x, y) => x === y, 36), 36];
        else if (/dues cares$/.test(p)) [fav, total] = [1, 4];
        else if (/una cara i una creu$/.test(p)) [fav, total] = [2, 4];
        else if (/un nombre primer$/.test(p)) [fav, total] = [die.filter((x) => isPrimeT(x)).length, 6];
        else if (/múltiple de 3$/.test(p)) [fav, total] = [die.filter((x) => x % 3 === 0).length, 6];
        else if (/cara i nombre parell$/.test(p)) [fav, total] = [3, 12];
        else return `enunciat ${p}`;
        return qEq(qn(BigInt(fav), BigInt(total)), got) ? null : `${p} → ${fav}/${total}`;
      }
      default:
        return `sense comprovació: ${kind}`;
    }
  };

  // ---- answer kinds ----
  const sameTerms = (a: Record<string, string>, b: Record<string, string>) => {
    const ka = Object.keys(a).sort();
    const kb = Object.keys(b).sort();
    return JSON.stringify(ka) === JSON.stringify(kb) && ka.every((k) => a[k] === b[k]);
  };
  // hooks/mathgrade.py parse_poly on these expressions (python3 hooks/mathgrade.py, via curriculum-independent run)
  const PY_POLY: Array<[string, Record<string, string> | null]> = [
  ["3x + 5 + 2x", {"x": "5", "": "5"}],
  ["5x + 5", {"x": "5", "": "5"}],
  ["5(x+1)", {"x": "5", "": "5"}],
  ["3xy", {"xy": "3"}],
  ["2x²y", {"x^2y": "2"}],
  ["x^2y*3", {"x^2y": "3"}],
  ["-x^2", {"x^2": "-1"}],
  ["2x - -3", {"x": "2", "": "3"}],
  ["1/2x + 1,5", {"x": "1/2", "": "3/2"}],
  ["x/2 + x/3", {"x": "5/6"}],
  ["(x+1)(x-1)", {"x^2": "1", "": "-1"}],
  ["x**2 - 1", {"x^2": "1", "": "-1"}],
  ["3x - 2x", {"x": "1"}],
  ["x/x", null],
  ["x^0", null],
  ["1 1/2x", null],
  ["x5", null],
  ["2 3", null],
  ["1000.000.000", null],
  ["(x+1", null],
  ["x^7", null],
  ["x^-1", null],
  ["0", {}],
  ["7x²", {"x^2": "7"}],
  ["−3ab", {"ab": "-3"}],
  ["a(b+c)", {"ab": "1", "ac": "1"}],
  ["2(3)", {"": "6"}],
  ["x(x+1)^2", {"x^3": "1", "x^2": "2", "x": "1"}],
  ["(2x)(3x²)", {"x^3": "6"}],
  ["2x^2*x", {"x^3": "2"}],
  ["x^6", {"x^6": "1"}],
  ["3·x·y", {"xy": "3"}],
  ["2.5x", {"x": "5/2"}],
  ["x(-x)", {"x^2": "-1"}],
  ["−(a − b)·2", {"a": "-2", "b": "2"}],  ];
  const polyDiff = PY_POLY.filter(([s, want]) => {
    const p = parsePoly(s);
    return want === null ? p !== null : p === null || !sameTerms(polyTerms(p), want);
  }).map(([s]) => s);
  check("parse_poly: the same terms as hooks/mathgrade.py for 35 expressions (accepted and refused)", polyDiff.length === 0, polyDiff);

  const alg = (x: string, y: string) => {
    const a = parsePoly(x);
    const b = parsePoly(y);
    return a !== null && b !== null && polyKey(a) === polyKey(b);
  };
  check("algebraic: equal polynomials, whatever the order, the product or the fractions", [
    alg("3x + 5 + 2x", "5x + 5"), alg("5(x+1)", "5x+5"), alg("3xy", "3yx"), alg("2x²y", "2x^2y"), alg("x/2 + x/3", "5x/6"),
    alg("1/2x + 1,5", "0,5x + 1.5"), alg("3x² + 5x² − x²", "7x²"), alg("(x+1)(x-1)", "x^2 - 1"), alg("−3ab", "-3ba"),
    alg("(2x)(3x²)", "6x³"), alg("x(x+1)", "x² + x"), alg("2·x·x", "2x^2"),
  ].every(Boolean));
  check("algebraic: different polynomials are not equal", !alg("2x", "2") && !alg("x²", "x³") && !alg("5x", "5x²") && !alg("3ab", "3a + b"));
  check("algebraic: what parse_poly refuses is refused (x5, 2 3, x^7, x^0, x/x, x^-1, 1 1/2x, (x+1, 1.000.000, empty)", [
    "x5", "2 3", "x^7", "x^0", "x/x", "x^-1", "1 1/2x", "(x+1", "1000.000.000", "", "x y z ?",
  ].every((s) => parsePoly(s) === null));
  check("algebraic: the degree is the hint (x²y is 3; 7 is 0)", C.polyDegree(C.parsePoly("3x²y")) === 3 && C.polyDegree(C.parsePoly("7")) === 0 && C.hintFor("algebraic", "3x²y", "ca") === "grau 3");
  check("algebraic: client and server parse the same (sample of 35)", PY_POLY.every(([s]) => (C.parsePoly(s) === null) === (parsePoly(s) === null)));
  check("algebraic: the client checks an answer and says if it is not the usual form", C.checkAlgebraic("3x + 5x", ["8x"]).ok && C.checkAlgebraic("8x", ["8x"]).exact === true && C.checkAlgebraic("8*x", ["8x"]).exact === false && C.checkAlgebraic("8x²", ["8x"]).ok === false);

  const fzOk = (s: string, t: string) => {
    const a = factorization(s);
    const b = factorization(t);
    return "factors" in a && "factors" in b && sameFactors(a.factors, b.factors);
  };
  check("factorization: 2^3·3^2·5 = 2³·3²·5 = 2·2·2·3·3·5, with *, x, × or spaces between factors", [
    "2³·3²·5", "2·2·2·3·3·5", "2*2*2*3*3*5", "2x2x2x3x3x5", "2 × 2 × 2 × 3 × 3 × 5", "5 · 3^2 · 2^3",
  ].every((s) => fzOk(s, "2^3·3^2·5")));
  check("factorization: a factor that is not prime (12, 1, 360) is wrong, with the reason", "problem" in factorization("2^2·12") && "problem" in factorization("360") && "problem" in factorization("1") && !fzOk("2^2·3·5", "2^3·3^2·5") && !fzOk("2^3·3^2", "2^3·3^2·5"));
  check("factorization: 2^0 and words are not factorizations", "problem" in factorization("2^0") && "problem" in factorization("dos"));
  check("factorization: the hint is the number of different primes", C.hintFor("factorization", "2^3·3^2·5", "ca") === "3 primers diferents");
  check("factorization: the client check agrees with the server", C.checkFactorization("2·2·2·3·3·5", ["2^3·3^2·5"]).ok === true && C.checkFactorization("12", ["2^3·3^2·5"]).ok === false && C.checkFactorization("12", ["2^3·3^2·5"]).note === "12 no és primer");

  const sx = (s: string, mode: SexaMode) => parseSexa(s, mode);
  check("sexagesimal: time as h min s, h:mm and h:mm:ss, the same seconds", sx("2 h 15 min", "time")?.seconds === 8100 && sx("2:15", "time")?.seconds === 8100 && sx("2h15min", "time")?.seconds === 8100 && sx("2:05:10", "time")?.seconds === 7510);
  check("sexagesimal: angles with º and typographic quotes too, and their seconds", sx("75° 40'", "angle")?.seconds === 272400 && sx("75º 40’", "angle")?.seconds === 272400 && sx("75° 40' 10''", "angle")?.seconds === 272410 && sx("75° 40' 10″", "angle")?.seconds === 272410);
  check("sexagesimal: 1 h 75 min and 135 min are not normalized (min and s below 60)", sx("1 h 75 min", "time")?.normalized === false && sx("135 min", "time")?.normalized === false && sx("2:75", "time")?.normalized === false && sx("2 h 15 min", "time")?.normalized === true);
  check("sexagesimal: a time is not an angle and the other way round", sx("2 h", "angle") === null && sx("75°", "time") === null && sx("", "time") === null);
  check("sexagesimal: sexaMode reads the mode of an item, else its notation", sexaMode("angle", "2 h") === "angle" && sexaMode(undefined, "75° 40'") === "angle" && sexaMode(undefined, "2 h 35 min") === "time");
  check("sexagesimal: the client checks it, says 'normalitza' and accepts the usual form", C.checkSexagesimal("1 h 75 min", "2 h 15 min", "time").note?.startsWith("Normalitza") === true && C.checkSexagesimal("2h15min", "2 h 15 min", "time").ok === true && C.checkSexagesimal("2:15", "2 h 15 min", "time").exact === false && C.checkSexagesimal("18° 55'", "18° 55'", "angle").exact === true && C.checkSexagesimal("19°", "18° 55'", "angle").ok === false);
  check("sexagesimal: the hint is the hours (or the degrees)", C.hintFor("sexagesimal", "7 h 45 min", "ca", "time") === "7 h ?" && C.hintFor("sexagesimal", "75° 40'", "ca", "angle") === "75° ?");

  check("number: −24, -24 and − 24 are the same answer (server and client), 24 is not", numericValue("−24") === -24 && numericValue("-24") === -24 && numericValue("− 24") === -24 && C.checkNumber("−24", ["-24"]).ok && C.checkNumber("-24", ["−24"]).ok && C.checkNumber("− 24", ["−24"]).ok && !C.checkNumber("24", ["−24"]).ok);
  check("fraction and pair: −7/12 and (−3, 4) read with the unicode minus too", parseFraction("−7/12")?.num === -7 && parseFraction("−7/12")?.den === 12 && parsePair("(−3, 4)")?.[0] === -3 && C.parsePair("(−3, 4)")[0] === -3 && C.checkFraction("−7/12", ["-7/12"], "value").ok === true);


  // ---- the 35 generators: count, determinism, cards read again, figures and answers well formed ----
  for (const kind of E5_KINDS) {
    const words = generatedWords(`math-m7.flash.${kind}`, { kind, count: 50 });
    const want = Math.min(50, GEN_ROOM[kind] ?? 50);
    check(`${kind}: ${want} cards, ids g1…, the same list gives the same cards`, words.length === want && words.every((w, i) => w.id === `g${i + 1}`) && JSON.stringify(words) === JSON.stringify(generatedWords(`math-m7.flash.${kind}`, { kind, count: 50 })), words.length);
    const bad = words.map((w) => verifyE5(kind, w)).filter((x): x is string => x !== null);
    check(`${kind}: every card read again with its own arithmetic agrees with its answer`, bad.length === 0, bad.slice(0, 3));
    const shape = words.flatMap((w): string[] => {
      const out: string[] = [];
      if (w.figure !== undefined) {
        const f = checkFigure(w.figure);
        if ("problem" in f) out.push(`figura: ${f.problem}`);
        else {
          const why = figureAnswerProblem(f.figure, w.prompt, (w.answer_kind ?? "number") as AnswerKind, w.target);
          if (why) out.push(`figura i resposta: ${why}`);
        }
      }
      if (w.answer_kind === "choice") {
        const opts = w.options ?? [];
        if (!opts.includes(w.target[0] ?? "") || new Set(opts).size !== opts.length || opts.length < 2) out.push(`opcions ${JSON.stringify(opts)}`);
      }
      if (w.answer_kind === "algebraic" && parsePoly(w.target[0]) === null) out.push(`algebraica ${w.target[0]}`);
      if (w.answer_kind === "factorization" && "problem" in factorization(w.target[0])) out.push(`factors ${w.target[0]}`);
      if (w.answer_kind === "sexagesimal") {
        const s = parseSexa(w.target[0], w.mode ?? "time");
        if (!w.mode || !s || !s.normalized) out.push(`sexagesimal ${w.target[0]}`);
      }
      if (w.answer_kind === "fraction" && w.form === "simplest" && !isSimplestText(w.target[0])) out.push(`no és irreductible ${w.target[0]}`);
      return out;
    });
    check(`${kind}: the figures agree with the answers, the choices are options, the answers are well formed`, shape.length === 0, shape.slice(0, 3));
  }
  const withFigure = ["pythagoras", "parallel_angles", "quadrant_point", "line_read"];
  check("the figure kinds of m7 put a figure on every card", withFigure.every((k) => generatedWords(`math-m7.flash.${k}`, { kind: k, count: 50 }).every((w) => w.figure !== undefined)));
  check("sexagesimal_ops: both notations, the time with h and min, the angle with ° and '", (() => {
    const ws = generatedWords("math-m7.flash.sexagesimal_ops", { kind: "sexagesimal_ops", count: 50 });
    return ws.some((w) => w.mode === "time") && ws.some((w) => w.mode === "angle") && ws.every((w) => (w.mode === "angle") === /°/.test(w.target[0] ?? ""));
  })());
  check("the generators of m7 are listed in GEN_KINDS (35 new, none of the m5 ones lost)", E5_KINDS.every((k) => GEN_KINDS.includes(k)) && E5_KINDS.length === 35 && GEN_KINDS.length === 62);
  check("a list of a kind with a small room gives the room, not the count (GEN_ROOM)", Object.entries(GEN_ROOM).every(([k, n]) => generatedWords(`math-m7.flash.${k}`, { kind: k, count: 50 }).length === n));

  // ---- explicit items of the new kinds: kept or dropped (docs/ENCARREC-M7-E5-FLASH.md §2, §3) ----
  {
    const ws = mathWords({
      items: [
        { id: "f1", prompt: "Descompon 12", answer: ["2^2·3"], answer_kind: "factorization" },
        { id: "f2", prompt: "Descompon 12", answer: ["2^2·4"], answer_kind: "factorization" },
        { id: "a1", prompt: "Simplifica", answer: ["3x²"], answer_kind: "algebraic" },
        { id: "a2", prompt: "x", answer: ["3x^7"], answer_kind: "algebraic" },
        { id: "s1", prompt: "2 h 35 min × 3", answer: ["7 h 45 min"], answer_kind: "sexagesimal" },
        { id: "s2", prompt: "x", answer: ["7 h 75 min"], answer_kind: "sexagesimal" },
        { id: "s3", prompt: "75° 40' : 4", answer: ["18° 55'"], answer_kind: "sexagesimal", mode: "angle" },
        { id: "s4", prompt: "x", answer: ["18° 55'"], answer_kind: "sexagesimal", mode: "time" },
        { id: "n1", prompt: "x", answer: ["−24"] },
      ],
    });
    const ids = ws.words.map((w) => w.id);
    check("explicit items: the new kinds are kept when right and dropped when not (factors, algebra, normalitza, wrong mode)", JSON.stringify(ids) === JSON.stringify(["f1", "a1", "s1", "s3", "n1"]), { ids, problems: ws.problems });
    check("explicit sexagesimal: the mode is the one the item names, else the notation of its answer", ws.words.find((w) => w.id === "s3")?.mode === "angle" && ws.words.find((w) => w.id === "s1")?.mode === "time");
    check("explicit items: a list file with new kinds is a valid math list", mathListProblems({ id: "t", items: [{ id: "f1", prompt: "Descompon 12", answer: ["2^2·3"], answer_kind: "factorization" }] }).length === 0);
  }

  // ---- figures (docs/ENCARREC-M7-E5-FLASH.md §3) ----
  {
    const ok = (f: unknown) => "figure" in checkFigure(f);
    const bad = (f: unknown) => "problem" in checkFigure(f);
    check("grid: 0..10 by default (as before), −6..6 with min and max, a line y = m·x + n", ok({ type: "grid", points: [[1, 2]] }) && ok({ type: "grid", points: [[-3, 4]], min: -6, max: 6 }) && ok({ type: "grid", points: [], min: -6, max: 6, line: { m: 2, n: -3 } }));
    check("grid: the defaults are 0 and 10 (size 10, min 0, max 10); a range from below 0 has min and max (no size)", (() => {
      const g = checkFigure({ type: "grid", points: [[1, 2]] });
      const h = checkFigure({ type: "grid", points: [[-3, 4]], min: -6, max: 6 });
      return "figure" in g && g.figure.type === "grid" && g.figure.min === 0 && g.figure.max === 10 && g.figure.size === 10 && "figure" in h && h.figure.type === "grid" && h.figure.max - h.figure.min === 12 && h.figure.size === undefined;
    })());
    check("grid: refused when a point is outside, a line has n outside the grid, min is not ≤ 0, or there is neither point nor line", bad({ type: "grid", points: [[7, 0]], min: -6, max: 6 }) && bad({ type: "grid", points: [], min: -6, max: 6, line: { m: 2, n: 7 } }) && bad({ type: "grid", points: [[1, 1]], min: 1 }) && bad({ type: "grid", points: [] }) && bad({ type: "grid", points: [[11, 0]] }));
    check("parallels: angle 20..160, known and ask different places 1..8", ok({ type: "parallels", angle: 70, known: 1, ask: 4 }) && bad({ type: "parallels", angle: 170, known: 1, ask: 4 }) && bad({ type: "parallels", angle: 70, known: 2, ask: 2 }) && bad({ type: "parallels", angle: 70, known: 1, ask: 9 }));
    check("right_triangle: a² + b² = c² with legs a, b and ask a, b or c", ok({ type: "right_triangle", a: 3, b: 4, c: 5, ask: "c" }) && bad({ type: "right_triangle", a: 3, b: 4, c: 6, ask: "c" }) && bad({ type: "right_triangle", a: 3, b: 4, c: 5, ask: "d" }));
    check("number_line: min < max, at most 40 units, the point inside", ok({ type: "number_line", min: -5, max: 5, point: -3, label: "°C" }) && bad({ type: "number_line", min: 5, max: 5, point: 5 }) && bad({ type: "number_line", min: -30, max: 30, point: 0 }) && bad({ type: "number_line", min: 0, max: 10, point: 11 }));
    const fp = (f: unknown, prompt: string, kind: AnswerKind, a: string) => {
      const c = checkFigure(f);
      if (!("figure" in c)) throw new Error(`figura no vàlida: ${JSON.stringify(f)}`);
      return figureAnswerProblem(c.figure, prompt, kind, [a]);
    };
    check("the answer agrees with the figure: parallels (70° at 1 means 70° at 4 and 110° at 2)", fp({ type: "parallels", angle: 70, known: 1, ask: 4 }, "Quant mesura l'angle marcat amb «?»", "number", "70") === null && fp({ type: "parallels", angle: 70, known: 1, ask: 2 }, "Quant mesura l'angle marcat amb «?»", "number", "70") !== null && fp({ type: "parallels", angle: 70, known: 1, ask: 2 }, "x", "number", "110") === null);
    check("the answer agrees with the figure: right_triangle (the side marked ?, the perimeter, the area) and number_line (the point)", fp({ type: "right_triangle", a: 3, b: 4, c: 5, ask: "a" }, "Calcula el costat que falta (?)", "unit", "3") === null && fp({ type: "right_triangle", a: 3, b: 4, c: 5, ask: "a" }, "Calcula el costat que falta (?)", "unit", "4") !== null && fp({ type: "right_triangle", a: 3, b: 4, c: 5, ask: "a" }, "Quin és el perímetre?", "unit", "12") === null && fp({ type: "right_triangle", a: 3, b: 4, c: 5, ask: "a" }, "Quina és l'àrea?", "unit", "6") === null && fp({ type: "number_line", min: -5, max: 5, point: -3 }, "Quin nombre és?", "number", "−3") === null && fp({ type: "number_line", min: -5, max: 5, point: -3 }, "Quin nombre és?", "number", "3") !== null);
    check("the answer agrees with the figure: grid line (pendent and ordenada)", fp({ type: "grid", points: [], min: -6, max: 6, line: { m: 2, n: -3 } }, "Quin és el pendent de la recta?", "number", "2") === null && fp({ type: "grid", points: [], min: -6, max: 6, line: { m: 2, n: -3 } }, "Quina és l'ordenada a l'origen de la recta?", "number", "−3") === null && fp({ type: "grid", points: [], min: -6, max: 6, line: { m: 2, n: -3 } }, "Quin és el pendent de la recta?", "number", "3") !== null);
    // the parallels: every place's value, by the geometry (the angle of the secant and its supplement)
    let geomOk = true;
    for (let angle = 20; angle <= 160; angle += 7) {
      for (let known = 1; known <= 8; known++) {
        for (let ask = 1; ask <= 8; ask++) {
          if (ask === known) continue;
          const alpha = [angle, 180 - angle].find((a) => Math.abs(sectorDeg(a, known) - angle) < 1e-6);
          const want = alpha === undefined ? -1 : Math.round(sectorDeg(alpha, ask));
          if (want !== parallelValue(angle, known, ask)) geomOk = false;
        }
      }
    }
    check("parallelValue agrees with the angles between the drawn rays, for every pair of places", geomOk);
  }

  // ---- the drawings of the new figures (SVG in line, inside the box, the aria says no answer) ----
  {
    const texts = (svg: string) => [...svg.matchAll(/<text class="fig-text" x="([-\d.]+)" y="([-\d.]+)"/g)].map((m) => [Number(m[1]), Number(m[2])]);
    const vb = (svg: string) => (svg.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/) ?? []).slice(1).map(Number);
    const samples: Figure[] = [
      { type: "parallels", angle: 35, known: 1, ask: 7 },
      { type: "parallels", angle: 150, known: 6, ask: 2 },
      { type: "parallels", angle: 90, known: 3, ask: 8 },
      { type: "right_triangle", a: 3, b: 4, c: 5, ask: "c", unit: "cm" },
      { type: "right_triangle", a: 5, b: 12, c: 13, ask: "a" },
      { type: "grid", points: [[-3, 4]], min: -6, max: 6, size: 12 },
      { type: "grid", points: [], min: -6, max: 6, size: 12, line: { m: -3, n: 4 } },
      { type: "number_line", min: -5, max: 5, point: -3, label: "°C" },
      { type: "number_line", min: 0, max: 40, point: 17 },
    ];
    for (const f of samples) {
      const svg = C.figureSvg(f) as string;
      const [W, H] = vb(svg);
      const inside = texts(svg).every(([x, y]) => x! >= 0 && y! >= 0 && x! <= W! && y! <= H!);
      const hex = /#[0-9a-fA-F]{3,6}\b/.test(svg);
      check(`${f.type}: an svg in line with a Catalan aria, its labels inside the box, no hex colour`, /^<svg class="flash-fig-svg" viewBox="[^"]+" role="img" aria-label="[^"]+"/.test(svg) && inside && !hex, svg.slice(0, 160));
    }
    const par = C.figureSvg({ type: "parallels", angle: 35, known: 1, ask: 7 }) as string;
    check("parallels: the known angle shows its value and the asked one shows ?, and the two parallels are drawn", par.includes("35°") && par.includes(">?</text>") && (par.match(/<line class="fig-line" x1="8"/g) ?? []).length === 2 && par.includes('aria-label="Dues rectes paral·leles'));
    check("right_triangle: the asked side shows ? and the others their sizes; no answer in the aria", (C.figureSvg({ type: "right_triangle", a: 3, b: 4, c: 5, ask: "c", unit: "cm" }) as string).includes(">?</text>") && (C.figureSvg({ type: "right_triangle", a: 3, b: 4, c: 5, ask: "c" }) as string).includes('aria-label="Triangle rectangle, amb un costat per calcular"'));
    check("grid with a negative range: the ticks run from −6 to 6 and the line is drawn in amber", (() => {
      const svg = C.figureSvg({ type: "grid", points: [], min: -6, max: 6, size: 12, line: { m: 1, n: 0 } }) as string;
      return svg.includes(">−6</text>") && svg.includes(">6</text>") && svg.includes('class="fig-mark"') && svg.includes("de −6 a 6");
    })());
    check("number_line: a dot at the point, the tick labels and the unit label", (() => {
      const svg = C.figureSvg({ type: "number_line", min: -5, max: 5, point: -3, label: "°C" }) as string;
      return svg.includes('<circle class="fig-dot"') && svg.includes(">−5</text>") && svg.includes(">°C</text>") && svg.includes("Recta numèrica de −5 a 5");
    })());
  }

  // ---- the client's checks and the flash.js source: the card, the input, the note, the hint ----
  {
    const flashSrc = read("web", "flash.js");
    check("flash.js: the new kinds have their own inputs, directions and feedback (note for normalitza, forma habitual)", flashSrc.includes('card.kind === "factorization" ? "Escriu els factors primers"') && flashSrc.includes("C.checkSexagesimal(text, card.accepted[0], card.mode)") && flashSrc.includes("const FORM_KINDS = [\"fraction\", \"pair\", \"factorization\", \"algebraic\", \"sexagesimal\"]") && flashSrc.includes("card.note || (card.misses === 0"));
    check("flash.js: the direction label of a choice, a pair, a factorization, an algebra and a time is said in full", flashSrc.includes('card.kind === "pair" ? "Escriu les coordenades"') && flashSrc.includes(': "Calcula"'));
    check("flash.js: the number kind reads the unicode minus (numeric) and the figure of the grid uses min and max", flashSrc.includes('.replace(/−/g, "-").replace(/,/g, ".")') && flashSrc.includes("const mn = f.min ?? 0;"));
  }
}

if (failures) {
  console.log(`\n${failures} FAILED`);
  process.exit(1);
}
console.log("\nall ok");
