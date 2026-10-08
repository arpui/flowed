// Open practices per domain — run with:
//   node --experimental-strip-types server/test/open-practices.test.ts
//
// 2026-10-08 (Albert): math runs no open practice with a general model (it
// invents problems that do not add up). config/domain.json `open_practices`
// decides; re-enabling one is a manifest edit, not a code change.

import fs from "node:fs";
import path from "node:path";
import { openPracticeOf, practiceAllowed, hasNextAfterScore, turnGuard, isExerciseGuard } from "../src/pacing.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures++;
    console.log(`  FAIL ${name}`, detail ?? "");
  }
}

const manifest = JSON.parse(fs.readFileSync(path.join(import.meta.dirname, "..", "..", "config", "domain.json"), "utf8"));

check("speaking/writing/reading are open practices", openPracticeOf("math-speaking") === "speaking"
  && openPracticeOf("fluent-writing") === "writing" && openPracticeOf("math-reading") === "reading");
check("Go, Review, Facts are not", openPracticeOf("math-learn") === null && openPracticeOf("fluent-review") === null);

for (const p of ["math-speaking", "math-writing", "math-reading"]) {
  check(`math: ${p} is closed`, !practiceAllowed(manifest, "math", p));
  check(`language: ${p} stays open`, practiceAllowed(manifest, "language", p));
}
check("math: Go stays open", practiceAllowed(manifest, "math", "math-learn"));
check("a domain without the field keeps everything", practiceAllowed({ domains: { x: {} } }, "x", "math-speaking"));
check("re-enabling is a manifest edit",
  practiceAllowed({ domains: { math: { open_practices: ["writing"] } } }, "math", "math-writing"));

// ---- the reply must give her something to do next (2026-10-08) ------------
const fb = "❌ \"I go\" → **\"I went\"**\n\n**Correct version:**\n\"I went.\"\n\n**Score: 6/10** 🟡";
check("ends at the score: nothing next", !hasNextAfterScore(fb + " Close! Try the next one."));
check("a new heading after the score is next", hasNextAfterScore(fb + "\n\n## Question 3: Food\nWhat do you eat?"));
check("a question after the score is next", hasNextAfterScore(fb + "\n\nWhat do you like to do on Sundays?"));
check("an explicit retry is next", hasNextAfterScore(fb + " Prova-ho una altra vegada!"));
check("no score line: not this check's business", hasNextAfterScore("## Question 1\nHow are you?"));
const base = { inLesson: false, pending: 0, coveredToday: [], askedHere: [], due: 0, replyText: "" } as any;
const note = turnGuard({ ...base, asked: [], graded: true, closing: false,
  openPracticeAnswered: true, nextAfterScore: false });
check("the guard asks for the next question", !!note && isExerciseGuard(note), note);
check("…and keeps quiet when there is one", turnGuard({ ...base, asked: [], graded: true, closing: false,
  openPracticeAnswered: true, nextAfterScore: true }) === null);
check("…and outside the open practices", turnGuard({ ...base, asked: [], graded: true, closing: false,
  openPracticeAnswered: false, nextAfterScore: false }) === null);

console.log(failures === 0 ? "\nopen-practices: all checks passed" : `\nopen-practices: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
