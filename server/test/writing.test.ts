// 📝 Raonament (the practice still named math-writing) — run with:
//   node --experimental-strip-types server/test/writing.test.ts
//
// Albert, 2026-09-23: the practice called Writing had slid into "asking for
// sentences with gaps and nothing else" — Go with another name, and no free
// production anywhere in the app. It is now open, guided production, and owed
// once a day. In FlowMath that practice is REASONING: the learner explains,
// justifies or invents (WP1.9 fixtures; the guard is the same one).

import { writingBlankGuard } from "../src/pacing.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

const OPEN = `## 📝 Raonament

**Task:** Explica com has resolt 24 × 13.

**Write your explanation below:**`;

const GAP = `## 📝 Raonament

**Task:** Completa: 24 × ___ = 312.`;

check("an open task passes", writingBlankGuard(OPEN, "math-writing") === null);
check("a gap in Raonament is sent back", writingBlankGuard(GAP, "math-writing") !== null);
check("so is \"complete the sentence\" without a gap",
  writingBlankGuard("**Task:** Complete the sentences about how you added the fractions.", "math-writing") !== null);
check("the same gap in Go is Go's business", writingBlankGuard(GAP, "math-learn") === null);

// The feedback half quotes her text; only the NEW task is judged.
const GRADED_THEN_OPEN = `### ❌ Areas to Improve
- 🔴 "3 + 2 × 4 = 20" → **"3 + 2 × 4 = 11"** (order_of_operations — primer la multiplicació)

**Score: 6/10**

${OPEN}`;
check("feedback above an open task does not trip it", writingBlankGuard(GRADED_THEN_OPEN, "math-writing") === null);

// WP1.9: writingLengthNote (the A1..C2 email/postcard table) is deleted; the
// reasoning task length is the math-writing skill's own m-level table.
check("the guard's rewrite speaks math, not language",
  /explica|justifica|inventa/.test(writingBlankGuard(GAP, "math-writing") ?? ""));

console.log(failures === 0 ? "\nwriting: all checks passed" : `\nwriting: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
