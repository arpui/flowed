// The bank on the server side — run with:
//   node --experimental-strip-types server/test/bank.test.ts

import { readFileSync } from "node:fs";
import { bankExerciseCard, bankFeedback, type BankGrade, type BankItem } from "../src/bank.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

const item = (competence: string) => ({
  id: `${competence}.001`, competence, type: "complete", instruction: "", sentence: "I ___ swim.",
  context: "", answer: "can", also_accept: [], options: [], why: "", status: "reviewed",
}) as never;

// "Writing" is its own practice now; a bank card said Writing on every exercise.
const g = bankExerciseCard(item("a1.can_ability"), 1, "Medium", "Can (ability)");
const v = bankExerciseCard(item("a1.vocab_colors_adjectives"), 2, "Easy", "Colours");
check("a grammar card says Grammar", g.includes("Exercise 1: Grammar (Medium)"), g);
check("a vocabulary card says Vocabulary", v.includes("Exercise 2: Vocabulary (Easy)"), v);
check("neither says Writing", !/Writing/.test(g + v));

// 🎓 Review on the bank (fase 4), and the day's count for every bank answer.
const ag = readFileSync(new URL("../src/agent.ts", import.meta.url), "utf8");
check("Review goes through the bank when it is on",
  ag.includes('this.currentCommand.get(sessionId) === "math-review"') && ag.includes("this.tryBankReviewTurn(sessionId, agent)"));
check("it asks curriculum.py for a review item", ag.includes('"review-pick", "--used"'));
check("the record names the queue item it reviewed, so SM-2 advances it",
  ag.includes("queueId ? { item_id: queueId, sm2_quality:"));
check("Go's bank answers count for the day", /appendBankRecord\(sessionId, prev\.competence, Boolean\(competence\.vocab\), graded\);\s*this\.creditBankAnswer\(sessionId, false/.test(ag));
check("Review's count for the lesson too", ag.includes("this.creditBankAnswer(sessionId, true, prev.queueId ?? prev.itemId)"));
check("an item left by one practice is not graded by the other",
  ag.includes('?.practice === "review") this.assignedBankItem.delete') && ag.includes('?.practice === "go") this.assignedBankItem.delete'));

// ---- WP1.3: math bank types (compute / choose / compare) --------------------
const mathItem = (over: Partial<BankItem>): BankItem =>
  ({ id: "m4.add_frac.001", competence: "m4.add_frac", type: "compute", instruction: "Calcula.",
    problem: "1/4 + 3/8", answer: "5/8", also_accept: [], options: [], why: "Denominador comú 8.",
    status: "validated", ...over } as BankItem);

const cc = bankExerciseCard(mathItem({}), 3, "Medium", "Fractions");
check("a compute card shows the problem, not a sentence",
  cc.includes("**Problem:** 1/4 + 3/8") && !cc.includes("Sentence"), cc);
check("a compute card ends with the math marker line", cc.includes("**Type your answer:**"), cc);
check("a math card header says Calculation", cc.includes("Exercise 3: Calculation (Medium)"), cc);

const ch = bankExerciseCard(mathItem({ id: "m4.doble.004", competence: "m4.doble", type: "choose",
  problem: "Quina operació resol «el doble de 5»?", options: ["5+2", "5×2", "5−2"], answer: "5×2" }), 4, "Easy", "Doble");
check("a choose card lists its options", ch.includes("**Options:** 5+2   ·   5×2   ·   5−2"), ch);

const cp = bankExerciseCard(mathItem({ id: "m4.compara.006", competence: "m4.compara", type: "compare",
  problem: "3/4 ○ 2/3", options: [">", "<", "="], answer: ">" }), 5, "Easy", "Comparar");
check("a compare card shows the open circle and the three symbols",
  cp.includes("3/4 ○ 2/3") && cp.includes("**Options:** >   ·   <   ·   ="), cp);

// Feedback keeps the parseable contract (persist-session.parse_error_patterns):
// severity marker by score, an arrow correction ONLY when wrong/near, and the
// category — "calculation" for near, the item's error_class for wrong.
const nearGrade = { score: 7, verdict: "near", note: "gairebé: s'escriu «264»",
  correct_version: "24 × 9 + 48 = 264", got: "246",
  item: mathItem({ problem: "24 × 9 + 48", answer: "264", why: "Multipliqueu primer; després sumeu." }) } as unknown as BankGrade;
const fbNear = bankFeedback(nearGrade);
check("near: 🟡 marker and a calculation correction",
  fbNear.includes("🟡 Almost") &&
  fbNear.includes('- ❌ "246" → **"24 × 9 + 48 = 264"** (calculation — gairebé: s\'escriu «264»)') &&
  fbNear.includes("**Score: 7/10**"), fbNear);

const wrongGrade = { score: 3, verdict: "wrong", note: "3/4 = 0,75 i 2/3 ≈ 0,66.",
  correct_version: "3/4 > 2/3", got: "<",
  item: mathItem({ id: "m4.compara.006", competence: "m4.compara", type: "compare", problem: "3/4 ○ 2/3",
    options: [">", "<", "="], answer: ">", why: "3/4 = 0,75 i 2/3 ≈ 0,66.", error_class: "sign" }) } as unknown as BankGrade;
const fbWrong = bankFeedback(wrongGrade);
check("wrong: 🔴 marker and the item's own error_class",
  fbWrong.includes("🔴 Not quite") &&
  fbWrong.includes('- ❌ "<" → **"3/4 > 2/3"** (sign — 3/4 = 0,75 i 2/3 ≈ 0,66.)'), fbWrong);

const okGrade = { score: 10, verdict: "correct", note: "", correct_version: "1/4 + 3/8 = 5/8", got: "5/8",
  item: mathItem({}) } as unknown as BankGrade;
const fbOk = bankFeedback(okGrade);
check("correct: ✅ and no arrow correction to parse", fbOk.includes("✅") && !fbOk.includes("→"), fbOk);

// The exact correction regex persist-session.parse_error_patterns runs over the
// transcript — if a math feedback line stops matching it, mistakes-db silently
// loses the pattern (tests/test_bank_math.py checks the same strings in Python).
const PERSIST_CORRECTION = /"([^"]+)"\s*→\s*\*\*"([^"]+)"\*\*\s*\(([\w-]+)/;
check("persist's correction regex extracts the near category",
  PERSIST_CORRECTION.exec(fbNear)?.[3] === "calculation", PERSIST_CORRECTION.exec(fbNear));
check("persist's correction regex extracts the wrong category",
  PERSIST_CORRECTION.exec(fbWrong)?.[3] === "sign", PERSIST_CORRECTION.exec(fbWrong));
check("a correct answer carries no correction match", !PERSIST_CORRECTION.test(fbOk), fbOk);

// The record the server writes for a math answer (agent.ts appendBankRecord).
check("math records are filed under the math taxonomy",
  ag.includes('verdict === "near" ? "calculation"') && ag.includes('String(item.error_class || "calculation")'));
check("math records count as the computation skill", ag.includes('"computation"'));

console.log(failures === 0 ? "\nbank: all checks passed" : `\nbank: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
