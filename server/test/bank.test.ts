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
// A steps item names its own category — the first failed step's error_class,
// from hooks/bank.py — so graded.error_class wins over the item's own.
check("math records are filed under the math taxonomy",
  ag.includes('verdict === "near" ? "calculation"') &&
  ag.includes('String(graded.error_class || item.error_class || "calculation")'));
check("math records count as the computation skill", ag.includes('"computation"'));
check("steps records carry the per-step trace and the steps skill",
  ag.includes('itemType === "steps" ? "steps"') && ag.includes("...(stepTrace ? { steps: stepTrace } : {})"));

// ---- WP2.2–2.4: steps items — card, annotated trace, contract --------------
const stepsItem = (over: Partial<BankItem>): BankItem =>
  ({ id: "m4.mult_2digit.001", competence: "m4.mult_2digit", type: "steps",
    instruction: "Resol-ho pas a pas. Una línia per pas.", problem: "93 × 25", method: "partial_products",
    answer: "2325", also_accept: [], options: [], why: "25 = 20 + 5.", status: "validated",
    steps: [
      { n: 1, expect: "93 × 20", value: "1860", accept: ["93 * 20"], error_class: "procedure",
        why: "Separa 25 en 20 + 5 i multiplica 93 × 20." },
      { n: 2, expect: "93 × 5", value: "465", accept: [], error_class: "calculation",
        why: "Ara les unitats: 93 × 5." },
      { n: 3, expect: "1860 + 465", value: "2325", accept: [], error_class: "carrying",
        why: "Suma els dos productes parcials." },
    ], ...over } as BankItem);

const sc = bankExerciseCard(stepsItem({}), 6, "Medium", "Multiplicar");
check("a steps card keeps the math shape (Problem + Type your answer)",
  sc.includes("**Problem:** 93 × 25") && sc.includes("**Type your answer:**"), sc);
check("a steps card carries the one-per-line marker and says Steps",
  sc.includes("**Una operació per línia:**") && sc.includes("Exercise 6: Steps (Medium)"), sc);

const stepsWrong = {
  score: 3, verdict: "wrong", note: "Ara les unitats: 93 × 5.",
  correct_version: "93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325",
  got: "93 × 5 = 400", error_class: "calculation", failed_step: 2,
  steps: [
    { n: 1, ok: true, got: "93 × 20 = 1860" },
    { n: 2, ok: false, got: "93 × 5 = 400" },
    { n: 3, ok: false, got: "1860 + 400 = 2260", propagated: true },
  ],
  item: stepsItem({}),
} as unknown as BankGrade;
const fbSteps = bankFeedback(stepsWrong);
check("steps feedback: 🔴 lead naming the failed step",
  fbSteps.includes("🔴 El pas 2 falla"), fbSteps);
check("steps feedback: trace with ✅/❌ per step and the why of the first failure",
  fbSteps.includes("- ✅ 1 · `93 × 20 = 1860`") &&
  fbSteps.includes("- ❌ 2 · esperat `93 × 5 = 465` · has escrit `93 × 5 = 400` — Ara les unitats: 93 × 5.") &&
  fbSteps.includes("- ❌ 3 · `1860 + 465 = 2325` · arrossega l'error del pas 2"), fbSteps);
check("steps feedback: Corrections line uses the failed step's error_class",
  fbSteps.includes('- ❌ "93 × 5 = 400" → **"93 × 5 = 465"** (calculation — Ara les unitats: 93 × 5.)'), fbSteps);
check("steps feedback: Correct version is the full trace, one step per line",
  fbSteps.includes('**Correct version:**\n"93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325"'), fbSteps);
check("steps feedback: Score line closes it", fbSteps.includes("**Score: 3/10**"), fbSteps);
check("steps feedback stays parseable",
  PERSIST_CORRECTION.exec(fbSteps)?.[3] === "calculation", PERSIST_CORRECTION.exec(fbSteps));

const stepsOk = {
  score: 10, verdict: "correct", note: "",
  correct_version: "93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325",
  steps: [{ n: 1, ok: true, got: "93 × 20 = 1860" }, { n: 2, ok: true, got: "93 × 5 = 465" },
          { n: 3, ok: true, got: "1860 + 465 = 2325" }],
  item: stepsItem({}),
} as unknown as BankGrade;
const fbStepsOk = bankFeedback(stepsOk);
check("all-correct steps: ✅, every step line ✅, no arrow correction",
  fbStepsOk.includes("✅ Perfect! Tot el procediment és correcte.") &&
  !PERSIST_CORRECTION.test(fbStepsOk) &&
  (fbStepsOk.match(/- ✅ \d/g) || []).length === 3, fbStepsOk);

const stepsEmpty = {
  score: 0, verdict: "empty", note: "25 = 20 + 5.",
  correct_version: "93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325", got: "",
  steps: [{ n: 1, ok: false, got: null }, { n: 2, ok: false, got: null }, { n: 3, ok: false, got: null }],
  item: stepsItem({}),
} as unknown as BankGrade;
const fbEmpty = bankFeedback(stepsEmpty);
check("empty steps: every step says nothing was written, no crash",
  fbEmpty.includes("no has escrit res per a aquest pas") && fbEmpty.includes("**Score: 0/10**"), fbEmpty);

// A translate card must show the sentence to translate even when the
// instruction does not repeat it (x.good_luck_babe.002 asked about nothing).
const trItem = { ...(item("a1.can_ability") as BankItem), type: "translate", instruction: "Say it in English.", sentence: "Bona sort!" } as BankItem;
const trCard = bankExerciseCard(trItem, 2, "Easy", "Song");
check("translate card shows the sentence", trCard.includes("«Bona sort!»") && trCard.includes("**Translate:** Say it in English: "), trCard);
const trItem2 = { ...trItem, instruction: "What is the English word for 'la veritat'?", sentence: "la veritat" } as BankItem;
check("translate card does not repeat a sentence already in the instruction", !bankExerciseCard(trItem2, 2, "Easy", "Song").includes("«"));

// A right answer in another form says so and explains how it is done
// (4/5 + 4/12 answered 68/60 for 1 2/15: "Perfect!" alone explained nothing).
const fracItem = { id: "m4.frac_add_unlike.050", competence: "m4.frac_add_unlike", type: "compute", instruction: "", problem: "4/5 + 4/12", answer: "1 2/15", also_accept: [], options: [], why: "Denominador comú 60. Com a nombre mixt: 17/15 = 1 + 2/15.", status: "validated" } as unknown as BankItem;
const fbEq = bankFeedback({ score: 10, verdict: "correct", note: "", correct_version: "4/5 + 4/12 = 1 2/15", given: "68/60", item: fracItem });
check("equivalent form is named", fbEq.includes("Has escrit «68/60»: val el mateix que «1 2/15»"), fbEq);
check("a right answer explains how it is done", fbEq.includes("**Com es fa:** Denominador comú 60") && fbEq.includes("1 + 2/15"), fbEq);
check("the parseable contract survives", /\*\*Correct version:\*\*\n"4\/5 \+ 4\/12 = 1 2\/15"/.test(fbEq) && /\*\*Score: 10\/10\*\*/.test(fbEq), fbEq);
const fbSame = bankFeedback({ score: 10, verdict: "correct", note: "", correct_version: "4/5 + 4/12 = 1 2/15", given: "1 2/15", item: fracItem });
check("the same form adds no equivalence line", !fbSame.includes("val el mateix"), fbSame);

// ---- ENCARREC-LANG-L2-BANC: `order` and `transform` cards (language, Go) -----
const orderItem = { id: "a1.verb_to_be.041", competence: "a1.verb_to_be", type: "order",
  instruction: "Put the words in order.", words: ["you", "where", "live", "do"], context: "",
  answer: "Where do you live?", also_accept: [], options: [], why: "Question word first, then do + subject + base verb.",
  status: "validated" } as unknown as BankItem;
const orderCard = bankExerciseCard(orderItem, 1, "Easy", "Verb to be");
check("order card: the words in the given order, the sentence's own end mark, and the write line",
  orderCard.includes("**Words:** you / where / live / do ?") && orderCard.includes("**Write the sentence:**"), orderCard);
check("order card is a grammar card", orderCard.includes("Exercise 1: Grammar (Easy)"), orderCard);
const orderStatement = { ...orderItem, answer: "I am a student.", words: ["a", "student", "am", "I"] } as unknown as BankItem;
check("order card for a statement shows its full stop as the mark",
  bankExerciseCard(orderStatement, 1, "Easy", "Verb to be").includes("**Words:** a / student / am / I ."));
const orderNoMark = { ...orderItem, answer: "they are not tired", words: ["tired", "are", "they", "not"] } as unknown as BankItem;
check("order card with no end mark adds none",
  bankExerciseCard(orderNoMark, 1, "Easy", "Verb to be").includes("**Words:** tired / are / they / not\n"));

const transformItem = { id: "a1.present_simple.061", competence: "a1.present_simple", type: "transform",
  instruction: "Make it negative.", sentence: "He plays football.", context: "",
  answer: "He doesn't play football.", also_accept: ["He does not play football."], options: [],
  why: "With he/she/it: doesn't + base verb, no -s.", status: "validated" } as unknown as BankItem;
const transformCard = bankExerciseCard(transformItem, 2, "Medium", "Present simple");
check("transform card: the instruction, the sentence, and the write line",
  transformCard.includes("Make it negative.\n\n**Sentence:** He plays football.") &&
  transformCard.includes("**Write the new sentence:**"), transformCard);
check("transform card has no marker the web composer would read as a gap",
  !/Type your answer|just the missing word/.test(transformCard), transformCard);

// Feedback: the same whole-sentence contract as `correct`, so the correction
// line still parses and a contraction is the same answer as its long form.
const orderWrong = { score: 3, verdict: "wrong", note: "Question word first, then do + subject + base verb.",
  correct_version: "Where do you live?", item: orderItem } as unknown as BankGrade;
const fbOrder = bankFeedback(orderWrong);
check("order wrong: ❌ lead with the right sentence and the why",
  fbOrder.includes('❌ Close! The correct form is "Where do you live?".') &&
  fbOrder.includes('- ❌ → **"Where do you live?"** (Question word first'), fbOrder);
check("order feedback keeps the Correct version and Score lines",
  fbOrder.includes('**Correct version:**\n"Where do you live?"') && fbOrder.includes("**Score: 3/10**"), fbOrder);
const transformOk = { score: 10, verdict: "correct", note: "", correct_version: "He doesn't play football.",
  item: transformItem } as unknown as BankGrade;
check("transform right: ✅ Perfect and no correction arrow",
  bankFeedback(transformOk).includes('✅ Perfect! "He doesn\'t play football." is right.') &&
  !bankFeedback(transformOk).includes("→"), bankFeedback(transformOk));

console.log(failures === 0 ? "\nbank: all checks passed" : `\nbank: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
