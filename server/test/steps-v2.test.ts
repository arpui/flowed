// WP2.5 — v2 incremental steps: the per-session state machine and its text.
// Run with:
//   node --experimental-strip-types server/test/steps-v2.test.ts
//
// The state machine (advance / retry / reveal-after-3) is pure; the grading
// itself is hooks/bank.py's (pinned in tests/test_bank_steps_v2.py). What is
// pinned here: the transitions, the bounded retry, the note texts NOT looking
// like graded feedback (no Score marker, no correction arrow — the prose
// persistence fallback must stay asleep mid-exchange), the v2 card, the v2
// feedback lead, and the agent.ts wiring.

import { readFileSync, readdirSync } from "node:fs";
import {
  stepsV2Init, stepsV2Handle, stepsV2Note, stepsV2Resume, stepsV2CardTail,
  diagnoseStepLine, stepShape, stepTemplateLine,
  STEPS_V2_MAX_ATTEMPTS, type StepsV2State,
} from "../src/steps.ts";
import { bankExerciseCard, bankFeedback, type BankGrade, type BankItem } from "../src/bank.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

const item = {
  id: "m4.mult_2digit.031", competence: "m4.mult_2digit", type: "steps", instruction: "",
  problem: "93 × 25", answer: "2325", also_accept: [], options: [], why: "", status: "validated",
  steps: [
    { n: 1, expect: "93 × 20", value: "1860", accept: [], error_class: "procedure", why: "Separa 25 en 20 + 5." },
    { n: 2, expect: "93 × 5", value: "465", accept: [], error_class: "calculation", why: "Ara les unitats." },
    { n: 3, expect: "1860 + 465", value: "2325", accept: [], error_class: "carrying", why: "Suma els parcials." },
  ],
} as unknown as BankItem;

// ---- the state machine ------------------------------------------------------
let st: StepsV2State = stepsV2Init();
check("init: step 1 pending, no attempts", st.stepIdx === 0 && st.attempts === 0 && st.results.length === 0, st);

let mv = stepsV2Handle(item, st, "correct", "93 × 20");
check("correct advances to step 2", mv.kind === "advance" && !mv.done && st.stepIdx === 1, mv);
check("advance result records one attempt", mv.result.ok && mv.result.attempts === 1, mv.result);

mv = stepsV2Handle(item, st, "wrong", "93 × 6");
check("first failure retries the SAME step", mv.kind === "retry" && !mv.done && st.stepIdx === 1 && st.attempts === 1, mv);
check("retry does not push a result yet", st.results.length === 1, st.results);

mv = stepsV2Handle(item, st, "correct", "93 × 5");
check("retry then correct advances with attempts=2", mv.kind === "advance" && mv.result.attempts === 2 && mv.result.ok, mv.result);
check("the retried step keeps its first wrong line", mv.result.first_wrong === "93 × 6", mv.result);

mv = stepsV2Handle(item, st, "near", "93 × 5 = 456");
check("a near slip retries too (never advances a wrong value)", mv.kind === "retry" && mv.result.near === undefined, mv);
check("the retry move carries the near flag for the note", mv.near === true, mv);
mv = stepsV2Handle(item, st, "wrong", "93 × 9");
check("second failure RETRIES again (three attempts per step)", mv.kind === "retry" && !mv.done && st.stepIdx === 2 && st.attempts === 2, mv);
check("the second retry is not a near slip", mv.near === false, mv);
mv = stepsV2Handle(item, st, "wrong", "93 × 8");
check("third failure REVEALS and moves on", mv.kind === "reveal" && mv.done && st.stepIdx === 3, mv);
check("reveal marks the step failed, attempts=3", mv.result.ok === false && mv.result.revealed === true && mv.result.attempts === 3, mv.result);
check("reveal keeps the FIRST wrong line and its near flag",
  mv.result.first_wrong === "93 × 5 = 456" && mv.result.near === true, mv.result);
check("the trace is complete after the last step", mv.done === true);
check("the budget is three attempts", STEPS_V2_MAX_ATTEMPTS === 3, STEPS_V2_MAX_ATTEMPTS);

// ---- the notes: never look like graded feedback -----------------------------
st = stepsV2Init();
mv = stepsV2Handle(item, st, "correct", "93 × 20");
const adv = stepsV2Note(item, mv);
check("advance note names the step progress", adv.includes("Pas 1 de 3 correcte") && adv.includes("Pas 2 de 3"), adv);
check("advance note restates the problem", adv.includes("**Problema:** 93 × 25"), adv);
mv = stepsV2Handle(item, st, "wrong", "banana");
const rty = stepsV2Note(item, mv);
check("retry note re-asks the pending step (now step 2)", rty.includes("**Pas 2 de 3**") && rty.includes("Torna-ho a provar."), rty);
check("first slip note shows the template (Escriu-ho així)", rty.includes("Escriu-ho així: `▢ × ▢`"), rty);
check("first slip note restates the problem", rty.includes("**Problema:** 93 × 25"), rty);
check("a correct line shows no hint", !adv.includes("Escriu-ho així") && !adv.includes("Et poso"), adv);
for (const [name, note] of [["advance", adv], ["retry", rty]] as const) {
  check(`${name} note has NO Score marker (persistence fallback stays asleep)`, !/\*\*Score:\s*\d+\/10\*\*/.test(note), note);
  check(`${name} note has no correction arrow`, !/→\s*\*\*"/.test(note), note);
  check(`${name} note has no "Correct version:"`, !/Correct version:/i.test(note), note);
}
st = stepsV2Init();
stepsV2Handle(item, st, "wrong", "x");
stepsV2Handle(item, st, "wrong", "y");
mv = stepsV2Handle(item, st, "wrong", "z");
const rev = stepsV2Note(item, mv);
check("third failure reveals the step (note kind)", mv.kind === "reveal", mv.kind);
check("reveal shows the expected line", rev.includes("`93 × 20 = 1860`") && rev.includes("Pas 2 de 3"), rev);
check("reveal note has no Score marker", !/\*\*Score:\s*\d+\/10\*\*/.test(rev), rev);
check("resume re-asks the pending step", stepsV2Resume(item, st).includes("pas 2 de 3"), stepsV2Resume(item, st));

// ---- the card ---------------------------------------------------------------
const v2card = bankExerciseCard(item, 4, "Easy", "Multiplicacions", undefined, "v2");
check("v2 card keeps the steps marker line (web mode switch)", /\*\*Una operació per línia:\*\*/.test(v2card), v2card);
check("v2 card asks for the FIRST operation only", v2card.includes("**Pas 1 de 3 — escriu només aquesta operació:**"), v2card);
check("v2 card has no bare Type-your-answer line", !v2card.includes("**Type your answer:**"), v2card);
const v1card = bankExerciseCard(item, 4, "Easy", "Multiplicacions");
check("v1 card unchanged (all-at-once)", v1card.includes("**Type your answer:**") && !v1card.includes("Pas 1 de 3"), v1card);
check("card tail matches the state machine's", stepsV2CardTail(item).startsWith("**Pas 1 de 3"), stepsV2CardTail(item));

// ---- per-step goals (2026-10-08): the learner is told WHAT to write ---------
const gItem: BankItem = { ...item, steps: item.steps!.map((x, i) => ({ ...x, goal: ["Descompon i multiplica per les desenes", "Multiplica per les unitats", "Suma els dos productes"][i] })) };
const gCard = bankExerciseCard(gItem, 4, "Easy", "Multiplicacions", undefined, "v2");
check("card with goal tells what to do in step 1", gCard.includes("**Pas 1 de 3** — Descompon i multiplica per les desenes.") && gCard.includes("**Escriu només aquesta operació:**"), gCard);
let gs = stepsV2Init();
const gmv = stepsV2Handle(gItem, gs, "correct", "93 × 20");
check("advance note carries the NEXT step's goal", stepsV2Note(gItem, gmv).includes("**Pas 2 de 3** — Multiplica per les unitats."), stepsV2Note(gItem, gmv));
const gry = stepsV2Handle(gItem, gs, "wrong", "x");
check("retry note repeats the goal", stepsV2Note(gItem, gry).includes("Multiplica per les unitats"), stepsV2Note(gItem, gry));
check("resume carries the goal", stepsV2Resume(gItem, gs).includes("Multiplica per les unitats"), stepsV2Resume(gItem, gs));
const g1 = bankExerciseCard(gItem, 4, "Easy", "Multiplicacions");
check("v1 card lists the goals", g1.includes("**Passos:**") && g1.includes("3. Suma els dos productes"), g1);

// ---- the diagnosis, the template, the three-attempt notes ---------------------
const bankSteps = (m: string): BankItem[] => {
  const dir = new URL(`../../curriculum/bank/${m}/steps/`, import.meta.url);
  return readdirSync(dir).filter((f) => f.endsWith(".json")).sort()
    .flatMap((f) => JSON.parse(readFileSync(new URL(f, dir), "utf8")) as BankItem[]);
};
const bank = [...bankSteps("math-m4"), ...bankSteps("math-m5"), ...bankSteps("math-m7")];
const byId = (id: string): BankItem => {
  const it = bank.find((x) => x.id === id);
  if (!it) throw new Error(`no bank item ${id}`);
  return it;
};
const stepOf = (it: BankItem, n: number) => it.steps!.find((s) => s.n === n)!;
const grp = byId("m7.props_grouping.001"); // 2 × 20 × 5, grouping
const dis = byId("m5.distributive.001");   // 8 × (10 + 2)
const cfc = byId("m7.props_factor.001");   // 8 × 3 + 8 × 2
const mul = byId("m4.mult_2digit.031");    // 93 × 25
const frc = byId("m4.frac_add_unlike.032"); // 1/3 + 10/12 = 1 1/6

// the rules, in order, on real items
check("rule 6: the learner wrote 2x20 → the problem's numbers",
  diagnoseStepLine(grp, stepOf(grp, 1), "2x20") === "Fes servir els nombres del problema: 2, 20 i 5.",
  diagnoseStepLine(grp, stepOf(grp, 1), "2x20"));
check("rule 5 (grouping): the spec's exact sentence for (2 × 20) × 5",
  diagnoseStepLine(grp, stepOf(grp, 1), "(2 × 20) × 5") ===
    "Has agrupat el 2 i el 20. Busca els dos nombres que junts fan un resultat **rodó** (10, 100…).",
  diagnoseStepLine(grp, stepOf(grp, 1), "(2 × 20) × 5"));
check("rule 4: the same numbers without the parentheses",
  diagnoseStepLine(grp, stepOf(grp, 1), "2 × 5 × 20") === "Hi falten els **parèntesis**: marca quins nombres van junts.",
  diagnoseStepLine(grp, stepOf(grp, 1), "2 × 5 × 20"));
check("rule 1: only the result, where the step is an operation",
  diagnoseStepLine(grp, stepOf(grp, 1), "200") === "Aquí no cal el resultat: escriu l'**operació** del pas.");
check("rule 3: the next step's line comes first",
  (diagnoseStepLine(grp, stepOf(grp, 1), "10 × 20") ?? "").startsWith(
    "Això és el pas següent. Primer: Propietat associativa i commutativa: agrupa"),
  diagnoseStepLine(grp, stepOf(grp, 1), "10 × 20"));
check("rule 3 on the distributive item (80 + 16 is step 2)",
  (diagnoseStepLine(dis, stepOf(dis, 1), "80 + 16") ?? "").startsWith("Això és el pas següent. Primer: Propietat distributiva"));
check("rule 2: the final answer before the last step names the goal (abbreviated)",
  diagnoseStepLine(frc, stepOf(frc, 2), "1 1/6") === "Has saltat passos: primer suma els numeradors.",
  diagnoseStepLine(frc, stepOf(frc, 2), "1 1/6"));
check("rule 5b (distributive): the problem's numbers copied, not distributed",
  diagnoseStepLine(dis, stepOf(dis, 1), "8 × (10 + 2)") === "Multiplica el de fora per **cada** nombre del parèntesi.",
  diagnoseStepLine(dis, stepOf(dis, 1), "8 × (10 + 2)"));
check("rule 5b (common factor): the problem's numbers copied, not factored",
  diagnoseStepLine(cfc, stepOf(cfc, 1), "8 × 3 + 8 × 2") === "Treu fora el nombre que es repeteix.",
  diagnoseStepLine(cfc, stepOf(cfc, 1), "8 × 3 + 8 × 2"));
check("rule 7: no rule applies, the template sentence",
  diagnoseStepLine(mul, stepOf(mul, 1), "93 × 25") === "Mira el motlle i omple'l amb els nombres del problema.");
check("rule 6 with the step's own numbers, when they are not the problem's",
  diagnoseStepLine(mul, stepOf(mul, 2), "93 × 6") === "Fes servir els nombres d'aquest pas: 93 i 5.",
  diagnoseStepLine(mul, stepOf(mul, 2), "93 × 6"));
check("a final bare-number step never names its result in a hint",
  diagnoseStepLine(grp, stepOf(grp, 3), "201") === "Fes servir els nombres d'aquest pas: 10 i 20.",
  diagnoseStepLine(grp, stepOf(grp, 3), "201"));
check("an empty line has no diagnosis", diagnoseStepLine(grp, stepOf(grp, 1), "   ") === null);

// the template
check("stepShape: every number becomes ▢, parentheses spaced",
  stepShape("(2 × 5) × 20") === "( ▢ × ▢ ) × ▢", stepShape("(2 × 5) × 20"));
check("stepShape reveal=1 keeps the first number (spec example)",
  stepShape("(2 × 5) × 20", 1) === "( 2 × ▢ ) × ▢", stepShape("(2 × 5) × 20", 1));
check("stepShape handles mixed numbers and fractions", stepShape("1 1/6") === "▢ ▢/▢", stepShape("1 1/6"));
check("the template of a bare final step shows the previous operation",
  stepTemplateLine(grp, stepOf(grp, 3)) === "Calcula: `10 × 20 = ▢`", stepTemplateLine(grp, stepOf(grp, 3)));

// the notes, attempt by attempt (spec §5)
let hs = stepsV2Init();
let hm = stepsV2Handle(grp, hs, "wrong", "2x20");
const first = stepsV2Note(grp, hm);
check("1st error: diagnosis first (❌)", first.startsWith("❌ Fes servir els nombres del problema: 2, 20 i 5."), first);
check("1st error: the problem, the step and the template (spec §5 shape)",
  first.includes("**Problema:** 2 × 20 × 5\n**Pas 1 de 3** — Propietat associativa i commutativa: agrupa primer els dos nombres que fan un resultat rodó (escriu-ho amb parèntesis).") &&
  first.includes("Escriu-ho així: `( ▢ × ▢ ) × ▢`") && first.endsWith("Torna-ho a provar."), first);
hm = stepsV2Handle(grp, hs, "wrong", "(2 × 20) × 5");
const second = stepsV2Note(grp, hm);
check("2nd error: the new diagnosis and the template with its first number",
  second.startsWith("❌ Has agrupat el 2 i el 20.") && second.includes("Et poso el primer nombre: `( 2 × ▢ ) × ▢`") &&
  second.endsWith("Torna-ho a provar."), second);
check("2nd error: no Escriu-ho així (that is the 1st error's line)", !second.includes("Escriu-ho així"), second);
hm = stepsV2Handle(grp, hs, "wrong", "2 × 5 × 20");
const third = stepsV2Note(grp, hm);
check("3rd error: the step is revealed (❌ El pas 1 de 3 és …)", hm.kind === "reveal" &&
  third.startsWith("❌ El pas 1 de 3 és: `(2 × 5) × 20 = 200`."), third);
for (const [name, note] of [["1st", first], ["2nd", second], ["reveal", third]] as const) {
  check(`${name} note has NO Score marker (persistence fallback stays asleep)`, !/\*\*Score:\s*\d+\/10\*\*/.test(note), note);
}
// a line with no rule: the first slip gets the template sentence, the second
// (no specific diagnosis) gets the plain "not this step" line
hs = stepsV2Init();
stepsV2Handle(mul, hs, "wrong", "93 × 25");
const plain1 = stepsV2Note(mul, stepsV2Handle(mul, hs, "wrong", "93 × 25"));
check("no-rule 2nd error keeps the plain line, with the template number shown",
  plain1.startsWith("❌ Aquesta línia no és el pas 1 de 3.") && plain1.includes("Et poso el primer nombre: `93 × ▢`"), plain1);
// a near slip: the near lead stays, the template is added, no diagnosis
hs = stepsV2Init();
const nearNote = stepsV2Note(mul, stepsV2Handle(mul, hs, "near", "93 × 20 = 1870"));
check("near slip: 🟡 lead, template, no ❌ diagnosis",
  nearNote.startsWith("🟡 Gairebé, pas 1 de 3: el resultat és a un dígit del que toca.") &&
  nearNote.includes("Escriu-ho així: `▢ × ▢`") && !nearNote.includes("❌"), nearNote);

// every bank steps item: stepShape / diagnosis / template do not break and
// the template carries as many blanks as the step has numbers
const sweepFails: string[] = [];
let swept = 0;
for (const it of bank) {
  for (const s of it.steps ?? []) {
    swept += 1;
    const where = `${it.id} step ${s.n}`;
    const nums = (s.expect.split("=")[0]!.match(/\d+(?:[.,]\d+)?/g) ?? []).length;
    const blanks0 = (stepShape(s.expect).match(/▢/g) ?? []).length;
    const blanks1 = (stepShape(s.expect, 1).match(/▢/g) ?? []).length;
    const bare = /^\d+$/.test(s.expect.trim());
    if (!bare && blanks0 !== nums) sweepFails.push(`${where}: blanks ${blanks0} ≠ numbers ${nums} (${s.expect})`);
    if (!bare && blanks1 !== Math.max(0, nums - 1)) sweepFails.push(`${where}: reveal=1 blanks ${blanks1} (${s.expect})`);
    for (const line of [s.expect, "banana", "1", "0 + 0"]) {
      try {
        const d = diagnoseStepLine(it, s, line);
        if (typeof d !== "string" || d.length === 0) sweepFails.push(`${where}: no diagnosis for "${line}"`);
      } catch (e) {
        sweepFails.push(`${where}: diagnose("${line}") threw ${String(e)}`);
      }
    }
    try {
      const tpl = stepTemplateLine(it, s, 0);
      if (!tpl.includes("▢")) sweepFails.push(`${where}: template without ▢ (${tpl})`);
    } catch (e) {
      sweepFails.push(`${where}: template threw ${String(e)}`);
    }
  }
}
check(`every bank steps item (m4, m5, m7): shape, diagnosis and template hold (${swept} steps)`,
  sweepFails.length === 0 && swept >= 90, sweepFails.slice(0, 5));

// ---- the final feedback (v2 shape) ------------------------------------------
const gNear: BankGrade = {
  score: 7, verdict: "near", note: "el pas 2 va necessitar un segon intent",
  correct_version: "93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325",
  got: "93 × 6", error_class: "calculation", failed_step: 2, mode: "v2", item,
  steps: [{ n: 1, ok: true, got: "93 × 20" }, { n: 2, ok: true, got: "93 × 5" }, { n: 3, ok: true, got: "1860 + 465" }],
};
const fbNear = bankFeedback(gNear);
check("v2 retried trace: Gairebé lead", fbNear.includes("🟡 Gairebé — el pas 2 va necessitar un segon intent."), fbNear);
check("v2 retried trace: correction names the retried step",
  fbNear.includes('- ❌ "93 × 6" → **"93 × 5 = 465"** (calculation'), fbNear);
check("v2 retried trace: every step ✅ in the trace",
  (fbNear.match(/- ✅ \d/g) ?? []).length === 3, fbNear);
check("v2 retried trace keeps the parseable contract",
  /\*\*Correct version:\*\*/.test(fbNear) && /\*\*Score: 7\/10\*\*/.test(fbNear), fbNear);

const gWrong: BankGrade = {
  score: 3, verdict: "wrong", note: "el pas 2 no et sortia; te'l vaig haver de revelar",
  correct_version: "93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325",
  got: "93 × 6", error_class: "calculation", failed_step: 2, mode: "v2", item,
  steps: [{ n: 1, ok: true, got: "93 × 20" }, { n: 2, ok: false, got: "93 × 6" }, { n: 3, ok: true, got: "1860 + 465" }],
};
const fbWrong = bankFeedback(gWrong);
check("v2 revealed trace: reveal lead, NOT the propagation one",
  fbWrong.includes("El pas 2 no et sortia; te'l vaig haver de revelar.") && !fbWrong.includes("arrosseguen l'error"), fbWrong);
check("v2 revealed trace: the revealed step shows ❌ with its why",
  fbWrong.includes("- ❌ 2 · esperat `93 × 5 = 465` · has escrit `93 × 6` — Ara les unitats."), fbWrong);

// v1 lead unchanged (propagation wording) — the contract did not move.
const gV1: BankGrade = { ...gWrong, mode: undefined,
  steps: [{ n: 1, ok: true, got: "93 × 20" }, { n: 2, ok: false, got: "93 × 6" },
          { n: 3, ok: false, got: "1860 + 465", propagated: true }] };
check("v1 feedback still says later steps drag the error",
  bankFeedback(gV1).includes("arrosseguen l'error") && bankFeedback(gV1).includes("arrossega l'error del pas 2"), bankFeedback(gV1));

// ---- agent.ts wiring ---------------------------------------------------------
const ag = readFileSync(new URL("../src/agent.ts", import.meta.url), "utf8");
check("steps items are served v2 in Go", ag.includes('const stepsV2 = item.type === "steps" ? stepsV2Init() : undefined;'));
check("steps items are served v2 in Review too", ag.includes('stepsV2: item.type === "steps" ? stepsV2Init() : undefined,'));
check("the pending step is graded through the bank CLI", ag.includes('"grade-step", "--competence"'));
check("the trace is closed through the bank CLI", ag.includes('"finalize-steps", "--competence"'));
check("a whole-trace first answer escapes to v1", ag.includes('if (lines.length >= 2) {'));
check("intermediate steps emit a note, not a record", ag.includes('if (v2.kind === "note") return emit(v2.text);') &&
  ag.includes('if (v2.kind === "note") return this.emitBankText(sessionId, agent, v2.text);'));
check("the v2 record carries the whole trace as learner_answer", ag.includes(".map((r) => String(r.got ?? \"\")).join(\"\\n\")"));
check("the bank review keeps its OWN served list (multi-turn v2 safe, e0057b4 intact)",
  ag.includes("const used = this.bankUsedItems.get(sessionId) ?? [];") &&
  ag.includes("this.bankUsedItems.set(sessionId, used.slice(-60));"));

// ---- web/app.js: the composer mode stays sticky across the exchange ---------
const app = readFileSync(new URL("../../web/app.js", import.meta.url), "utf8");
check("steps mode is sticky across the v2 exchange (session state, not marker re-detection)",
  app.includes("let stepsExchangeActive = false;") &&
  app.includes('if (detected === "steps") stepsExchangeActive = true;') &&
  app.includes("const mode = detected ?? (stepsExchangeActive ? \"steps\" : null);"));

console.log(failures === 0 ? "\nsteps-v2: all checks passed" : `\nsteps-v2: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
