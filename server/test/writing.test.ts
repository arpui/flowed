// 📝 Writing — run with:
//   node --experimental-strip-types server/test/writing.test.ts
//
// Albert, 2026-09-23: the practice called Writing had slid into "asking for
// sentences with gaps and nothing else" — Go with another name, and no free
// production anywhere in the app. Writing is now open, guided production, and
// owed once a day like Speaking.

import { writingBlankGuard, writingLengthNote } from "../src/pacing.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

const OPEN = `## ✍️ Writing Exercise

**Topic:** La teva mascota

**Task:** Write 2 sentences in English.

**Use:** I have, It is

**Write your sentences below:**`;

const GAP = `## ✍️ Writing Exercise

**Task:** Complete the sentence: My dog ___ brown.`;

check("an open task passes", writingBlankGuard(OPEN, "math-writing") === null);
check("a gap in Writing is sent back", writingBlankGuard(GAP, "math-writing") !== null);
check("so is \"complete the sentence\" without a gap",
  writingBlankGuard("**Task:** Complete the sentences about your family.", "math-writing") !== null);
check("the same gap in Go is Go's business", writingBlankGuard(GAP, "math-learn") === null);

// The feedback half quotes her text; only the NEW task is judged.
const GRADED_THEN_OPEN = `### ❌ Areas to Improve
- 🔴 "I has a dog" → **"I have a dog"** (agreement — ...)

**Score: 6/10**

${OPEN}`;
check("feedback above an open task does not trip it", writingBlankGuard(GRADED_THEN_OPEN, "math-writing") === null);

const a1 = writingLengthNote("A1") ?? "";
check("A1 asks for her own sentences", /of her own/.test(a1), a1);
check("and forbids gaps outright", /never a gap/.test(a1), a1);
check("B1 still asks for an email", /email/.test(writingLengthNote("B1") ?? ""));

console.log(failures === 0 ? "\nwriting: all checks passed" : `\nwriting: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
