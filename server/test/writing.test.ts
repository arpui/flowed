// 📝 Raonament (the practice still named math-writing) — run with:
//   node --experimental-strip-types server/test/writing.test.ts
//
// Albert, 2026-09-23: the practice called Writing had slid into "asking for
// sentences with gaps and nothing else" — Go with another name, and no free
// production anywhere in the app. It is now open, guided production, and owed
// once a day. In FlowMath that practice is REASONING: the learner explains,
// justifies or invents (WP1.9 fixtures; the guard is the same one).

import { writingBlankGuard, reasoningTaskGuard, parseFeedback } from "../src/pacing.ts";

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

// ---- WP3.3: the math guards on the open task ---------------------------------
// Never a bare list; always a justification. The task half only — a reply
// that just gives feedback presents no task and passes through.

const EXPLAIN = `## 📝 Repte de Raonament

**Task:** Explica en 2-3 frases com vas fer 29 + 17 de cap i per què funciona.`;
check("an explain-task passes the WP3.3 guard", reasoningTaskGuard(EXPLAIN, "math-writing") === null);

const LIST = `## 📝 Repte de Raonament

**Task:** Fes una llista de totes les maneres de descompondre 24 × 13.`;
check("a bare list is sent back", reasoningTaskGuard(LIST, "math-writing") !== null);
check("the list rewrite asks for an explanation with the reason attached",
  /llista|justificació|reason/i.test(reasoningTaskGuard(LIST, "math-writing") ?? ""));

const RESULT_ONLY = `## 📝 Repte de Raonament

**Task:** Calcula 24 × 13 i escriu el resultat.`;
check("a task with no justification cue is sent back (it is Go under another name)",
  reasoningTaskGuard(RESULT_ONLY, "math-writing") !== null);
check("its rewrite tells the tutor to say the answer alone will not score",
  /will not score/i.test(reasoningTaskGuard(RESULT_ONLY, "math-writing") ?? ""));

const FIND_ERROR = `## 📝 Repte de Raonament

**Task:** Hi ha un error en aquesta resolució: 1/4 + 3/8 = 4/12. Troba'l i explica'l.`;
check("find-and-fix-the-error passes", reasoningTaskGuard(FIND_ERROR, "math-writing") === null);

const INVENT = `## 📝 Repte de Raonament

**Task:** Inventa un problema que es resolgui amb 3/4 + 1/8.`;
check("invent-a-problem passes", reasoningTaskGuard(INVENT, "math-writing") === null);

const JUSTIFY_CLAIM = `## 📝 Repte de Raonament

**Task:** Té sentit que 1/3 + 1/4 = 2/7? Demostra-ho.`;
check("justify-a-claim passes", reasoningTaskGuard(JUSTIFY_CLAIM, "math-writing") === null);

const WHICH_OP = `## 📝 Repte de Raonament

**Task:** Quina operació necessites per saber quants en falten per 20?`;
check("the lower-level 'which operation' task passes", reasoningTaskGuard(WHICH_OP, "math-writing") === null);

// Feedback-only turns (no task presented) are not judged.
const FEEDBACK_ONLY = `## Feedback

- 🟡 "24 + 7 = 21" → **"24 + 7 = 31"** (carrying — el transport)

**Score: 7/10**`;
check("a feedback-only turn passes through", reasoningTaskGuard(FEEDBACK_ONLY, "math-writing") === null);

// The guard belongs to Raonament only: Go and the other practices set closed
// exercises on purpose.
check("the same closed task in Go is Go's business",
  reasoningTaskGuard(RESULT_ONLY, "math-learn") === null);
check("and in Math talk too", reasoningTaskGuard(RESULT_ONLY, "math-speaking") === null);

// WP3.3: a reasoning correction quotes a WHOLE explanation — the parser must
// not drop it at a 120-char cap (seen live: corrections: [] in .records while
// the Python fallback, uncapped, found the same line).
const LONG_CORRECTION = `## Feedback

**Corrections:**
- 🔴 "Primer separo les parts i després les ajunto: 20 + 1 em surt 31. Per què funciona: perquè descompondre no canvia el resultat, només el fa més fàcil de fer de cap." → **"L'error és que has multiplicat 93 per 20 i afegit 1, quan hauries de dividir 93 entre 20 per saber quants caramels hi haurà en cada paquet. L'operació correcta és 93 ÷ 20 = 4,65."** (wrong_operation — the operation chosen does not match the problem)

**Correct version:**
"L'error és que has multiplicat 93 per 20 i afegit 1, quan hauries de dividir 93 entre 20."

**Score: 3/10**`;
const parsed = parseFeedback(LONG_CORRECTION);
check("a reasoning-length correction reaches the derived record",
  !!parsed && parsed.corrections.length === 1 &&
  parsed.corrections[0]?.category === "wrong_operation",
  parsed ? JSON.stringify(parsed.corrections).slice(0, 120) : "null");

console.log(failures === 0 ? "\nwriting: all checks passed" : `\nwriting: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
