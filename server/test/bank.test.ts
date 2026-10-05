// The bank on the server side — run with:
//   node --experimental-strip-types server/test/bank.test.ts

import { readFileSync } from "node:fs";
import { bankExerciseCard } from "../src/bank.ts";

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

console.log(failures === 0 ? "\nbank: all checks passed" : `\nbank: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
