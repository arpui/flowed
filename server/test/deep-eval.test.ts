// WP3.1 — the math rubric, the open-task enum, and the math skill keys.
// Run with:  bun test server/test/deep-eval.test.ts
//
// The deep evaluator used to carry a LANGUAGE rubric: it judged
// "communicativeness", corrected words, and its task enum was
// writing/speaking/reading/scoring. WP3.1 replaces the judging with the math
// one (answer / procedure / justification / communication, on the closed
// path's 10/7/3 bands) and the enum with the open math task kinds. These
// checks pin the seam (C3) so the language rubric cannot creep back, and they
// pin the read-old/write-new maps: a stale prompt or a stored record with a
// language-era value must normalize, never crash and never persist the old
// name.

import {
  DEEP_RUBRIC,
  DEEP_TASKS,
  normalizeDeepTask,
  SKILL_KEYS,
  normalizeSkillKey,
  ERROR_CATEGORIES,
} from "../src/tools.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

// ---- the task enum -----------------------------------------------------------

check("the four open math task kinds",
  DEEP_TASKS.join(",") === "explain,error-analysis,compare-strategies,word-problem",
  DEEP_TASKS.join(","));

check("canonical task names pass through",
  DEEP_TASKS.every((t) => normalizeDeepTask(t) === t));

check("legacy language task names map to their math kind (read-old)",
  normalizeDeepTask("writing") === "explain" &&
  normalizeDeepTask("speaking") === "explain" &&
  normalizeDeepTask("reading") === "word-problem" &&
  normalizeDeepTask("scoring") === "explain");

check("drifted spellings normalize too",
  normalizeDeepTask("Explain-Reasoning") === "explain" &&
  normalizeDeepTask("word_problem") === "word-problem" &&
  normalizeDeepTask("error-analysis") === "error-analysis" &&
  normalizeDeepTask("compare-strategies") === "compare-strategies");

check("an unknown task falls back to explain, never rejects the call",
  normalizeDeepTask("essay") === "explain" && normalizeDeepTask("") === "explain");

// ---- the skill keys (C7) -----------------------------------------------------

check("the five math skill keys",
  SKILL_KEYS.join(",") === "computation,steps,problems,reasoning,facts",
  SKILL_KEYS.join(","));

check("canonical skill keys pass through",
  SKILL_KEYS.every((s) => normalizeSkillKey(s) === s));

check("legacy language skill keys map to their math counterpart (read-old)",
  normalizeSkillKey("writing") === "reasoning" &&
  normalizeSkillKey("speaking") === "reasoning" &&
  normalizeSkillKey("reading") === "problems" &&
  normalizeSkillKey("vocabulary") === "facts" &&
  normalizeSkillKey("grammar") === "computation");

check("surface spellings of the math practices normalize",
  normalizeSkillKey("Raonament") === "reasoning" &&
  normalizeSkillKey("raonament") === "reasoning" &&
  normalizeSkillKey("problemes") === "problems" &&
  normalizeSkillKey("passos") === "steps" &&
  normalizeSkillKey("fets") === "facts");

check("an unknown skill falls back to computation",
  normalizeSkillKey("mental-math") === "computation" && normalizeSkillKey("") === "computation");

// ---- the rubric text ---------------------------------------------------------

const rubric = DEEP_RUBRIC;

check("the rubric judges the four math dimensions",
  ["answer:", "procedure:", "justification:", "communication:"].every((d) => rubric.includes(d)));

check("the rubric names the closed path's 10/7/3 bands",
  rubric.includes("10/7/3") && rubric.includes("needed a retry") && rubric.includes("needed revealing"));

check("the rubric forbids grading the learner's language",
  rubric.includes("never the language the answer is written in"));

check("the rubric carries no language-era judging phrases",
  !/communicativeness|fully communicative|communication breaks|judge in the target language/i.test(rubric));

check("the rubric's categories are the math taxonomy, derived from the array",
  rubric.includes(`Allowed categories: ${ERROR_CATEGORIES.join(", ")}`) &&
  !/Allowed categories:[^\n]*(grammar|vocabulary|spelling)/i.test(rubric));

check("the rubric keeps the parseable correction shape",
  rubric.includes('`- "incorrect" → **"correct"** (category — short reason)`'));

check("a bare answer without reasoning is in the 0-4 band",
  /0-4 = .*bare\s*answer with no reasoning/s.test(rubric));

console.log(failures === 0 ? "\ndeep-eval: all checks passed" : `\ndeep-eval: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
