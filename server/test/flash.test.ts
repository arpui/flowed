// Flash v0 / v0.1 — the vocabulary drill without a model (docs/ENCARREC-FLASH-v0.md, -v0.1.md),
// and the math answer kinds and generators of docs/ENCARREC-M5-E1-FLASH.md (§2, §3, §4).
// Run with:
//   node --experimental-strip-types server/test/flash.test.ts

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";
import {
  decComma,
  emptyFlashState,
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
check("every math list is kind math, level m5, titled, with words", listsMath.every((l) => l.kind === "math" && l.level === "m5" && l.title.length > 0 && l.words.length > 0));
check("every math word has a prompt, a native = [prompt] and a target", listsMath.every((l) => l.words.every((w) => w.prompt && w.native.join() === w.prompt && w.target.length > 0)));
for (const l of listsMath) {
  const ids = l.words.map((w) => w.id);
  check(`math word ids unique in ${l.id}`, new Set(ids).size === ids.length);
}
{
  const t7 = listsMath.find((l) => l.id === "math-m5.flash.taula-7");
  const w = t7?.words.find((x) => x.id === "7x3");
  check("taula del 7: ten words, 7 × 3 = 21", t7?.words.length === 10 && w?.prompt === "7 × 3" && w?.target.join() === "21", w);
  check("taula del 7: the ids are <a><op><b>", t7?.words.map((x) => x.id).join() === "7x1,7x2,7x3,7x4,7x5,7x6,7x7,7x8,7x9,7x10");
  const ex = listsMath.find((l) => l.id === "math-m5.flash.2x1-xifres");
  check("2×1 digits: twelve explicit items, 23 × 4 = 92", ex?.words.length === 12 && ex.words[0]?.prompt === "23 × 4" && ex.words[0]?.target.join() === "92");
}
check("math lists have no language entries (the lists are per domain)", listsMath.every((l) => !l.id.startsWith("en-")) && listsCa.every((l) => !l.id.startsWith("math-")));

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
  const mathState = { version: 1, lists: { "math-m5.flash.taula-7": { words: { "7x3": { box: 2, seen: 2, first_try: 2, misses: 0, last: "2026-10-16" } }, closed_at: null } }, rounds_by_day: { "2026-10-16": 1 } };
  const mathPut = saveFlashState(root, v1Dir, { ...mathState, lists: { ...mathState.lists, "en-A1.flash.family": good.lists["en-A1.flash.family"] } });
  check("math profile: PUT keeps the math lists, drops the language ones", mathPut.status === 200 && JSON.stringify(Object.keys((mathPut.body as any).state.lists)) === '["math-m5.flash.taula-7"]', (mathPut.body as any).state?.lists);
  check("math profile: the math progress is read back", JSON.stringify((flashStateResponse(root, v1Dir) as any).state.lists) === JSON.stringify(mathState.lists));
} finally {
  fs.rmSync(v1Dir, { recursive: true, force: true });
}


// ---- E1: answer kinds and generators (docs/ENCARREC-M5-E1-FLASH.md §2–§4) ---
// The arithmetic of every generated word is checked here with a second, independent
// reading of its prompt (a small evaluator, plain regexes), not with the generator's own code.
console.log("generators (E1)");
{
  const expected = ["round", "digit_value", "compare_numbers", "frac_of", "frac_equiv", "frac_same_den", "frac_dec", "dec_times_int", "percent_of", "divisible", "combined", "unit_convert", "complex_to_simple", "time_convert", "area_simple", "mean", "probability", "equation", "sequence"];
  check("the 19 generator kinds are the ones of §3", JSON.stringify([...GEN_KINDS].sort()) === JSON.stringify([...expected].sort()), GEN_KINDS);
  check("count: default 12, clamped to 1..50, a non-integer gives 12", genCount(undefined) === 12 && genCount(0) === 1 && genCount(51) === 50 && genCount(7) === 7 && genCount(12.5) === 12 && genCount("9") === 12);
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
    const words = generatedWords(`math-m5.flash.${kind}`, { kind, count: 50 });
    check(`${kind}: 50 words, ids g1…g50, prompts distinct`, words.length === 50 && words.every((w, i) => w.id === `g${i + 1}`) && new Set(words.map((w) => w.prompt)).size === 50, words.length);
    const bad = words.map((w) => verify(kind, w)).filter((x): x is string => x !== null);
    check(`${kind}: every result checked with an independent reading`, bad.length === 0, bad.slice(0, 3));
    const dflt = generatedWords(`math-m5.flash.${kind}`, { kind });
    check(`${kind}: the default count is 12 and they are the first twelve`, dflt.length === 12 && JSON.stringify(dflt) === JSON.stringify(words.slice(0, 12)));
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

if (failures) {
  console.log(`\n${failures} FAILED`);
  process.exit(1);
}
console.log("\nall ok");
