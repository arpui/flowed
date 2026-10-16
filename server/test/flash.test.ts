// Flash v0 — the vocabulary drill without a model (docs/ENCARREC-FLASH-v0.md).
// Run with:
//   node --experimental-strip-types server/test/flash.test.ts

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";
import { flashConfig, flashListsResponse, loadFlashLists, nativeCode, profileDomain } from "../src/flash.ts";

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

type Word = { id: string; target: string[]; native: string[] };
type List = { id: string; level: string; title: string; words: Word[] };

// ---- the lists --------------------------------------------------------------
console.log("lists");
const listsCa: List[] = loadFlashLists(root, "curriculum/flash/en-*", "ca");
const listsEs: List[] = loadFlashLists(root, "curriculum/flash/en-*", "es");
check("five lists under curriculum/flash/en-*", listsCa.length === 5, listsCa.map((l) => l.id));
check("list ids are unique", new Set(listsCa.map((l) => l.id)).size === listsCa.length);
check("every list is A1 and titled", listsCa.every((l) => l.level === "A1" && l.title.length > 0));
check("every list has 12 words", listsCa.every((l) => l.words.length === 12), listsCa.map((l) => l.words.length));
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

// ---- manifest and profile --------------------------------------------------
console.log("manifest and profile");
const manifest = JSON.parse(read("config", "domain.json"));
check("language has flash on, en-* lists", JSON.stringify(flashConfig(manifest, "language")) === JSON.stringify({ enabled: true, dir: "curriculum/flash/en-*" }));
check("math has no flash (hidden)", flashConfig(manifest, "math").enabled === false);
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
  check("language profile: all five lists", Array.isArray(ca.lists) && ca.lists.length === 5);
  const mother = ca.lists[0].words.find((w: Word) => w.id === "mother");
  check("words carry only the native forms of the learner", mother && JSON.stringify(mother.native) === '["mare"]' && JSON.stringify(mother.target) === '["mother","mum","mom"]', mother);
  check("lists are ordered by level, then file name", ca.lists.map((l: List) => l.id).join() === "en-A1.flash.family,en-A1.flash.food,en-A1.flash.home,en-A1.flash.animals,en-A1.flash.verbs", ca.lists.map((l: List) => l.id));

  writeProfile({ native_language: "castellano", target_language: "English", current_level: "A1" });
  const es = flashListsResponse(root, dataDir) as any;
  check("castellano profile: nativeCode es, madre", es.nativeCode === "es" && es.lists[0].words.find((w: Word) => w.id === "mother").native.join() === "madre");

  writeProfile({ native_language: "Catalan", target_language: "English", current_level: "m3" });
  const math = flashListsResponse(root, dataDir) as any;
  check("math profile: disabled, no lists", math.enabled === false && math.lists.length === 0);
} finally {
  fs.rmSync(dataDir, { recursive: true, force: true });
}

// ---- wiring ----------------------------------------------------------------
console.log("wiring");
const http = read("server", "src", "http.ts");
const app = read("web", "app.js");
const index = read("web", "index.html");
check("http.ts injects window.__FLOWED_FLASH", http.includes("window.__FLOWED_FLASH=${flashOn}"));
check("http.ts serves GET /api/flash/lists", http.includes('p === "/api/flash/lists"'));
check("index.html has the Flash button after Review and loads flash.js",
  /data-cmd="math-review"[\s\S]*data-cmd="math-flash"/.test(index) && index.includes('src="/flash.js"'));
check("app.js hides Flash unless __FLOWED_FLASH", app.includes("!window.__FLOWED_FLASH"));
check("app.js: Flash after Review in the language bar", app.includes('"math-review", "math-flash"'));
check("app.js: Flash opens the drill, no agent turn", app.includes('b.dataset.cmd === "math-flash"') && app.includes("openFlash();"));

if (failures) {
  console.log(`\n${failures} FAILED`);
  process.exit(1);
}
console.log("\nall ok");
