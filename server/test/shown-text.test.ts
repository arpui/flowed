// What the learner must see — run with:
//   node --experimental-strip-types server/test/shown-text.test.ts
//
// Tutor-bench, 2026-09-27 (docs/MODELBENCH.md): the 14B put "{❌}" into Reading;
// the 27B graded in math_record_answer and then showed only
// "Waiting for your answer! ⏱️".

import {
  stripTemplateBraces,
  feedbackFromRecord,
  scoreOfReply,
  exerciseFingerprints,
} from "../src/pacing.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures++;
    console.log(`  FAIL ${name}`, detail ?? "");
  }
}

check("{❌} loses its braces", stripTemplateBraces("{❌} Close!") === "❌ Close!");
check("{8/10} too", stripTemplateBraces("Score: {8/10}") === "Score: 8/10");
check("the Reading heading instruction is unwrapped",
  stripTemplateBraces('## {"Question 1: Main idea" — in English}') === "## Question 1: Main idea");
check("{Target} is not touched here", stripTemplateBraces("in {Target}") === "in {Target}");

const fb = feedbackFromRecord({ score: 6, corrections: [{ wrong: "I go", right: "I went", category: "grammar" }] });
check("feedback rebuilt from the call has the fix", !!fb && fb.includes('"I went"'), fb);
check("…and a score she can see", scoreOfReply(fb ?? "") === 6, fb);
check("a right answer says so", (feedbackFromRecord({ score: 10, corrections: [] }) ?? "").includes("Correct"));
check("no score, nothing invented", feedbackFromRecord({ corrections: [] }) === null);

// The opening greeting is not an exercise (2026-09-29: "already asked hello,
// test" rewrote the opening of every new Speaking session of the day).
const opening = "# 🗣️ English Speaking Practice\n\nHello, Test!\n\nToday we're practicing speaking.";
check("the greeting is not fingerprinted", !exerciseFingerprints(opening).includes("hello, test"),
  exerciseFingerprints(opening));
check("a question under the opening heading still is",
  exerciseFingerprints("## 🗣️ English Speaking Practice\n\n**What is your favorite hobby?**").length === 1);
check("Question N still is",
  exerciseFingerprints("## Question 2: Food\n\nWhat do you eat for breakfast?").length === 1);

console.log(failures === 0 ? "\nshown-text: all checks passed" : `\nshown-text: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
