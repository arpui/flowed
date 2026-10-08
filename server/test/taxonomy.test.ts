// Taxonomy per domain — run with:
//   node --experimental-strip-types server/test/taxonomy.test.ts
//
// 2026-10-08 (Albert, Stats of a language profile): the core filed everything
// under MATH skills and categories — grammar became Càlcul, vocabulary became
// Fets, and a language slip "I went" was stored as `calculation_I_went`. Each
// domain has its own skills and categories; they are never mixed.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  normalizeCategory, normalizeSkillKey, errorCategoriesFor, skillKeysFor, defaultCategoryFor,
  toolsForDomain, ERROR_CATEGORIES, SKILL_KEYS,
} from "../src/tools.ts";
import {
  domainOfDataDir, normalizeLanguageCategory, normalizeLanguageSkill,
  LANGUAGE_ERROR_CATEGORIES, LANGUAGE_SKILL_KEYS,
} from "../src/taxonomy.ts";
import { skillDebts, lessonSkillSlot, trackedSkillsFor, slotSkillsFor, parseFeedback } from "../src/pacing.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures++;
    console.log(`  FAIL ${name}`, detail ?? "");
  }
}

// ---- domain of a profile ----------------------------------------------------
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "taxo-"));
function profile(name: string, body: unknown): string {
  const d = path.join(tmp, name);
  fs.mkdirSync(d, { recursive: true });
  fs.writeFileSync(path.join(d, "learner-profile.json"), JSON.stringify(body));
  return d;
}
check("level A1 → language", domainOfDataDir(profile("en", { learner: { current_level: "A1" } })) === "language");
check("level m7 → math", domainOfDataDir(profile("m", { learner: { current_level: "m7" } })) === "math");
check("explicit domain wins", domainOfDataDir(profile("x", { domain: "language", learner: { current_level: "m7" } })) === "language");
check("no profile → math (the manifest default)", domainOfDataDir(path.join(tmp, "nope")) === "math");

// ---- categories ---------------------------------------------------------------
check("math: tenses is not a math category", normalizeCategory("tenses") === null);
check("language: tenses is kept", normalizeCategory("tenses", "language") === "tenses");
check("language: alias 'verb tense' → tenses", normalizeCategory("verb tense", "language") === "tenses");
check("language: a math label is rejected, not turned into 'calculation'", normalizeCategory("calculation", "language") === null);
check("math keeps its own", normalizeCategory("carrying") === "carrying" && normalizeCategory("càlcul") === "calculation");
check("the fallback is the domain's own", defaultCategoryFor("language") === "grammar" && defaultCategoryFor("math") === "calculation"
  && defaultCategoryFor() === "calculation");
check("category lists are the domain's own",
  errorCategoriesFor("language") === LANGUAGE_ERROR_CATEGORIES && errorCategoriesFor("math") === ERROR_CATEGORIES);
check("the old FlowEd ids are still accepted", normalizeLanguageCategory("gerund") === "gerund");

// ---- skills --------------------------------------------------------------------
check("math: grammar still maps onto computation (old math records)", normalizeSkillKey("grammar") === "computation");
check("language: grammar stays grammar", normalizeSkillKey("grammar", "language") === "grammar");
check("language: vocabulary stays vocabulary", normalizeSkillKey("vocabulary", "language") === "vocabulary");
check("language: a math key lands on a language skill, never invents a math one",
  normalizeSkillKey("reasoning", "language") === "writing" && normalizeSkillKey("facts", "language") === "vocabulary"
  && normalizeLanguageSkill("steps") === "grammar");
check("language: unknown → writing (as in FlowEd 0.5)", normalizeSkillKey("zzz", "language") === "writing");
check("skill lists are the domain's own",
  skillKeysFor("language") === LANGUAGE_SKILL_KEYS && skillKeysFor("math") === SKILL_KEYS);

// ---- the record tool shows the model its own domain's lists ------------------------
const defs = [{
  name: "math_record_answer", description: "d",
  parameters: { type: "object", properties: {
    skill: { type: "string", description: "computation | steps | problems | reasoning | facts" },
    corrections: { type: "array", items: { type: "object", properties: { category: { type: "string", description: "One of: calculation, sign" } } } },
  } },
  execute: async () => "",
}];
const lang = toolsForDomain(defs as any, "language")[0]!;
const langProps = (lang.parameters as any).properties;
check("language record tool lists language skills", /writing/.test(langProps.skill.description) && !/computation/.test(langProps.skill.description));
check("language record tool lists language categories",
  /tenses/.test(langProps.corrections.items.properties.category.description)
  && !/calculation/.test(langProps.corrections.items.properties.category.description));
check("math keeps its definitions as built", toolsForDomain(defs as any, "math") === defs);
check("the original definition is not mutated", (defs[0]!.parameters as any).properties.skill.description.includes("computation"));

// ---- the Lesson's neglected-skill slot ----------------------------------------------
const mastery = { skills: {} };
const langDebts = skillDebts(mastery, "2026-10-08", 3, trackedSkillsFor("language"));
check("language debts are language skills", langDebts.map((d) => d.skill).join() === "writing,reading,speaking,vocabulary");
const slotLang = lessonSkillSlot(2, langDebts, 3, slotSkillsFor("language"));
check("the language slot is writing or reading, never reasoning/problems", slotLang === "writing" || slotLang === "reading", slotLang);
const mathDebts = skillDebts(mastery, "2026-10-08");
check("math slot unchanged", ["reasoning", "problems"].includes(lessonSkillSlot(2, mathDebts) ?? ""));

// ---- a feedback heading names a skill in the domain's terms -------------------------
const fb = "## Exercise 3: Vocabulary\n\n**Score: 6/10**\n\n- ❌ \"I go\" → **\"I went\"** (tenses — past)";
check("language feedback: heading 'Vocabulary' → vocabulary", parseFeedback(fb, "language")?.skill === "vocabulary");
check("math feedback: the same heading still maps to a math skill", parseFeedback(fb)?.skill === "facts");

fs.rmSync(tmp, { recursive: true, force: true });
console.log(failures === 0 ? "\ntaxonomy: all checks passed" : `\ntaxonomy: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
