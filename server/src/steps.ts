/**
 * WP2.5 — v2 incremental steps (DISSENY-MATEMATIQUES §4.2 "v2 pas a pas").
 *
 * A `steps` bank item is solved ONE STEP PER MESSAGE: the server holds the
 * session state (which item, which step pending, how many failed attempts on
 * it — the same shape of per-session state `gradingItem` already is for the
 * review queue), grades each line with hooks/bank.py `grade_step` (the v1
 * `_grade_step_line` semantics: form AND value, `accept` alternates, near
 * slip), and advances, retries or reveals per the policy below.
 *
 * Retry policy (bounded, so a stuck learner never loops): THREE attempts per
 * step (STEPS_V2_MAX_ATTEMPTS). The first failure gets a diagnosis of the
 * line plus the step's template ("Escriu-ho així"); the second gets the same
 * template with its first number filled in; the third reveals that step's
 * expected line, marks the step failed, and moves on — the learner continues
 * the trace with the corrected state. A correct line is never annotated: the
 * hints only appear in front of an error.
 *
 * Scoring (mirrors v1's 10/7/3 exactly, see hooks/bank.py `finalize_steps`):
 * every step right on the first try → 10; every step right but one needed a
 * retry (a second or third try, i.e. with a hint) → 7; a step had to be
 * revealed → 3.
 *
 * The intermediate notes deliberately carry NO "**Score: N/10**" line and no
 * `"wrong" → **"right"** (category` correction shape: the persistence prose
 * fallback (hooks/persist-session.py `_feedback_of`/`parse_error_patterns`)
 * only fires on the Score marker, so a step note folds nothing into the
 * databases — the ONE record for the item is written at finalize, by the
 * bank CLI, in the v1 shape.
 */

import type { BankItem, BankStep } from "./bank.ts";

export interface StepsV2Result {
  n: number;
  ok: boolean;
  /** the line accepted (ok) or the last line attempted (revealed). */
  got: string | null;
  /** messages spent on this step: 1 = right on the first try. */
  attempts: number;
  revealed?: boolean;
  /** the first line that was NOT accepted, and whether it was a digit slip. */
  first_wrong?: string;
  near?: boolean;
}

export interface StepsV2State {
  /** index into item.steps of the pending step. */
  stepIdx: number;
  /** failed attempts on the pending step (0 .. MAX-1; MAX reveals). */
  attempts: number;
  /** the pending step's first rejected line, kept across its attempts. */
  firstWrong?: string;
  firstNear?: boolean;
  results: StepsV2Result[];
}

export const STEPS_V2_MAX_ATTEMPTS = 3;

export function stepsV2Init(): StepsV2State {
  return { stepIdx: 0, attempts: 0, results: [] };
}

export type StepsV2Verdict = "correct" | "near" | "wrong";

export interface StepsV2Move {
  /** advance: step done, more remain. retry: same step again. reveal: step
   *  failed after MAX attempts, its line shown, move on. */
  kind: "advance" | "retry" | "reveal";
  /** the whole trace is graded — the final feedback card follows. */
  done: boolean;
  step: BankStep;
  result: StepsV2Result;
  /** retry only: the rejected line was a digit slip (verdict "near"). Kept
   *  off `result` on purpose — a retry records nothing yet. */
  near?: boolean;
}

/** Apply one graded line to the state (mutates `state`). */
export function stepsV2Handle(item: BankItem, state: StepsV2State, verdict: StepsV2Verdict, line: string): StepsV2Move {
  const steps = item.steps ?? [];
  const step = steps[state.stepIdx]!;
  if (verdict === "correct") {
    const result: StepsV2Result = { n: step.n, ok: true, got: line, attempts: state.attempts + 1 };
    if (state.attempts > 0) {
      result.first_wrong = state.firstWrong;
      result.near = state.firstNear;
    }
    state.results.push(result);
    state.stepIdx += 1;
    state.attempts = 0;
    state.firstWrong = undefined;
    state.firstNear = undefined;
    return { kind: "advance", done: state.stepIdx >= steps.length, step, result };
  }
  if (state.attempts === 0) {
    state.firstWrong = line;
    state.firstNear = verdict === "near";
  }
  state.attempts += 1;
  if (state.attempts >= STEPS_V2_MAX_ATTEMPTS) {
    const result: StepsV2Result = {
      n: step.n, ok: false, got: line, attempts: state.attempts,
      revealed: true, first_wrong: state.firstWrong, near: state.firstNear,
    };
    state.results.push(result);
    state.stepIdx += 1;
    state.attempts = 0;
    state.firstWrong = undefined;
    state.firstNear = undefined;
    return { kind: "reveal", done: state.stepIdx >= steps.length, step, result };
  }
  return {
    kind: "retry", done: false, step, near: verdict === "near",
    result: { n: step.n, ok: false, got: line, attempts: state.attempts },
  };
}

/** The expected line of a step ("expect = value", or just the bare value). */
export function stepWantLine(s: BankStep): string {
  return s.value && s.value !== s.expect ? `${s.expect} = ${s.value}` : s.expect;
}

/** The v2 opening card's prompt line (the marker line stays on the card —
 *  web/app.js detects it to switch the composer; the per-step notes do NOT
 *  repeat it, the web keeps the mode sticky instead). */
export function stepsV2CardTail(item: BankItem): string {
  return stepPrompt(item, 1);
}

/** The prompt of step `k` (1-based). A step with a `goal` says WHAT to do
 *  there (the property or the technique to apply) — without it the learner
 *  cannot know what "the operation of step 1" is (2026-10-08, Albert). Steps
 *  without a goal keep the bare prompt. */
export function stepPrompt(item: BankItem, k: number): string {
  const N = item.steps?.length ?? 0;
  const goal = (item.steps ?? []).find((s) => s.n === k)?.goal?.trim();
  if (!goal) return `**Pas ${k} de ${N} — escriu només aquesta operació:**`;
  return `**Pas ${k} de ${N}** — ${goal.replace(/[.:]+$/, "")}.\n\n**Escriu només aquesta operació:**`;
}

// ---- hints on an error (v2 retry) --------------------------------------------
// Pure text from the bank fields: the learner's line is compared with the
// pending step (and the next one) and the first matching rule names the slip.
// The rules are tried in order; the first that applies is the diagnosis.

const NUM = /\d+(?:[.,]\d+)?/g;
const NO_RULE = "Mira el motlle i omple'l amb els nombres del problema.";

/** Compare form: no spaces; x / X / * / · are ×, − is -, and : or / are ÷
 *  when the expected line uses ÷. */
function normLine(s: string, div: boolean): string {
  let t = s.trim().replace(/[xX*·]/g, "×").replace(/−/g, "-").replace(/\s+/g, "");
  if (div) t = t.replace(/[:/]/g, "÷");
  return t;
}

/** The operation part of a line (what is written before any "= result"). */
const opPart = (s: string): string => s.split("=")[0] ?? "";
const numsOf = (s: string): string[] => (opPart(s).match(NUM) ?? []).map((x) => x.replace(",", "."));
const sameList = (a: string[], b: string[]): boolean =>
  a.length === b.length && [...a].sort().join("|") === [...b].sort().join("|");
const hasOp = (s: string): boolean => /[×÷+\-()]/.test(opPart(s));
const isBareNumber = (s: string): boolean => /^-?\d+(?:[.,]\d+)?$/.test(s.trim());
const sentence = (s: string): string => s.trim().replace(/[.:]+$/, "");
const joinCa = (xs: string[]): string =>
  xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} i ${xs[xs.length - 1]}`;

/** The goal in short, for "Has saltat passos: primer …": the part after a
 *  "Tema: " prefix, without the parenthesis, lower-cased first letter. */
function goalPhrase(goal: string | undefined): string {
  let g = (goal ?? "").trim();
  const colon = g.indexOf(": ");
  if (colon >= 0) g = g.slice(colon + 2);
  g = sentence(g.replace(/\s*\([^)]*\)/g, ""));
  return g.charAt(0).toLowerCase() + g.slice(1);
}

/** The method's hint for "same numbers, wrong structure". */
function methodHint(method: string | undefined, goal: string | undefined): string {
  if (method === "grouping") return "Busca els dos nombres que junts fan un resultat **rodó** (10, 100…).";
  if (method === "distributive") return "Multiplica el de fora per **cada** nombre del parèntesi.";
  if (method === "common_factor") return "Treu fora el nombre que es repeteix.";
  const g = goalPhrase(goal);
  return g ? `Recorda: ${g}.` : NO_RULE;
}

/** The numbers inside the first parenthesis, if there is one. */
function innerNums(s: string): string[] | null {
  const m = s.match(/\(([^()]*)\)/);
  return m ? (m[1]!.match(NUM) ?? []).map((x) => x.replace(",", ".")) : null;
}

/** The diagnosis rule that applies (`specific`) or the fallback (not). */
function diagnose(item: BankItem, step: BankStep, line: string): { text: string; specific: boolean } | null {
  const trimmed = line.trim();
  if (!trimmed) return null;
  const steps = item.steps ?? [];
  const N = steps.length;
  const idx = steps.findIndex((s) => s.n === step.n);
  const k = step.n;
  const goal = step.goal;
  const div = step.expect.includes("÷");
  const nl = normLine(trimmed, div);
  const said = (text: string) => ({ text, specific: true });

  // 1. only a number, where the step is an operation
  if (isBareNumber(trimmed) && hasOp(step.expect)) {
    return said("Aquí no cal el resultat: escriu l'**operació** del pas.");
  }
  // 2. the final answer, before the last step
  const answers = [item.answer, ...(item.also_accept ?? [])].filter(Boolean).map((a) => normLine(String(a), false));
  if (idx < N - 1 && answers.includes(nl)) {
    return said(goal ? `Has saltat passos: primer ${goalPhrase(goal)}.` : `Has saltat passos: fes primer el pas ${k}.`);
  }
  // 3. the line of the next step
  const next = steps[idx + 1];
  if (next) {
    const nextWants = [next.expect, ...(next.accept ?? []), stepWantLine(next)].map((x) => normLine(x, div));
    if (nextWants.includes(nl)) {
      return said(goal ? `Això és el pas següent. Primer: ${sentence(goal)}.`
        : `Això és el pas següent. Primer escriu el pas ${k}.`);
    }
  }
  const lineNums = numsOf(trimmed);
  const expNums = numsOf(step.expect);
  const probNums = (item.problem ?? "").match(NUM)?.map((x) => x.replace(",", ".")) ?? [];
  // 4. the same numbers without the parentheses the step needs
  if (step.expect.includes("(") && !opPart(trimmed).includes("(") && sameList(lineNums, expNums)) {
    return said("Hi falten els **parèntesis**: marca quins nombres van junts.");
  }
  // 5. the same numbers, grouped differently
  if (sameList(lineNums, expNums)) {
    const lineIn = innerNums(opPart(trimmed));
    const expIn = innerNums(step.expect);
    const lead = lineIn && expIn && lineIn.length === 2 && !sameList(lineIn, expIn)
      ? `Has agrupat el ${lineIn[0]} i el ${lineIn[1]}. ` : "";
    return said(lead + methodHint(item.method, goal));
  }
  // 5b. distributive / common factor: the learner copied the problem's own
  // numbers and did not distribute or factor them (the step's numbers differ,
  // so rule 5 cannot see it) — the method's hint is the useful one
  if ((item.method === "distributive" || item.method === "common_factor") && sameList(lineNums, probNums)) {
    return said(methodHint(item.method, goal));
  }
  // 6. numbers missing or extra (checked against the problem, then the step)
  if (!sameList(lineNums, probNums)) {
    // a final bare-number step: the numbers to use are the previous step's
    // operands — never its result, which would give the answer away
    const basis = isBareNumber(step.expect) && idx > 0 ? numsOf(steps[idx - 1]!.expect) : expNums;
    const inProblem = basis.every((n) => probNums.includes(n));
    return said(inProblem
      ? `Fes servir els nombres del problema: ${joinCa(probNums)}.`
      : `Fes servir els nombres d'aquest pas: ${joinCa(basis)}.`);
  }
  // 7. no rule applies
  return { text: NO_RULE, specific: false };
}

/** The diagnosis of a rejected line, one sentence in Catalan (null for an
 *  empty line). See `diagnose` for the rule order. */
export function diagnoseStepLine(item: BankItem, step: BankStep, line: string): string | null {
  return diagnose(item, step, line)?.text ?? null;
}

/** The step's shape for the learner: every number of `expect` becomes ▢,
 *  operators and parentheses stay. `reveal` numbers from the left stay
 *  visible: stepShape("(2 × 5) × 20", 1) → "( 2 × ▢ ) × ▢". */
export function stepShape(expect: string, reveal = 0): string {
  let seen = 0;
  return expect
    .replace(NUM, (m) => (seen++ < reveal ? m : "▢"))
    .replace(/[()]/g, " $& ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The template line of a step. A bare-number step (the final result) shows
 *  the previous step's operation with the result blank: "Calcula: 10 × 20 = ▢". */
export function stepTemplateLine(item: BankItem, step: BankStep, reveal = 0): string {
  const steps = item.steps ?? [];
  const idx = steps.findIndex((s) => s.n === step.n);
  if (isBareNumber(step.expect) && idx > 0) {
    return `Calcula: \`${steps[idx - 1]!.expect.trim()} = ▢\``;
  }
  const shape = stepShape(step.expect, reveal);
  return reveal > 0 ? `Et poso el primer nombre: \`${shape}\`` : `Escriu-ho així: \`${shape}\``;
}

/** The per-step note after a graded line. No Score marker, no correction
 *  arrow — see the block comment on why that matters. The problem is restated
 *  (as "**Problema:**", which no fingerprint mark matches) so the learner
 *  never loses the statement mid-exchange. */
export function stepsV2Note(item: BankItem, move: StepsV2Move): string {
  const N = item.steps?.length ?? 0;
  const k = move.step.n;
  const prob = item.problem ? `**Problema:** ${item.problem}` : "";
  if (move.kind === "advance" && !move.done) {
    return `✅ Pas ${k} de ${N} correcte.\n\n${prob}\n\n${stepPrompt(item, k + 1)}`;
  }
  if (move.kind === "retry") {
    const attempt = move.result.attempts; // 1: the first slip, 2: the second
    const d = diagnose(item, move.step, move.result.got ?? "");
    let lead: string;
    if (move.near) {
      lead = `🟡 Gairebé, pas ${k} de ${N}: el resultat és a un dígit del que toca.`;
    } else if (attempt === 1 || d?.specific) {
      lead = `❌ ${d?.text ?? NO_RULE}`;
    } else {
      lead = `❌ Aquesta línia no és el pas ${k} de ${N}.`;
    }
    const goal = move.step.goal?.trim();
    const head = `**Pas ${k} de ${N}**${goal ? ` — ${sentence(goal)}.` : ""}`;
    const probLine = item.problem ? `**Problema:** ${item.problem}\n` : "";
    return `${lead}\n\n${probLine}${head}\n\n${stepTemplateLine(item, move.step, attempt - 1)}\n\nTorna-ho a provar.`;
  }
  if (move.kind === "reveal" && !move.done) {
    return `❌ El pas ${k} de ${N} és: \`${stepWantLine(move.step)}\`.\n\n${prob}\n\n` +
      stepPrompt(item, k + 1);
  }
  return ""; // done: the final feedback card (with the trace) follows this turn
}

/** Re-show the pending step when the turn is not an answer (a button press
 *  mid-exchange): the card on screen must stay in sync with the state. */
export function stepsV2Resume(item: BankItem, state: StepsV2State): string {
  const N = item.steps?.length ?? 0;
  const k = (item.steps ?? [])[state.stepIdx]?.n ?? state.stepIdx + 1;
  const goal = (item.steps ?? [])[state.stepIdx]?.goal?.trim();
  return goal
    ? `Anem pel pas ${k} de ${N} de «${item.problem ?? ""}» — ${goal.replace(/[.:]+$/, "")}. Escriu només aquesta operació.`
    : `Anem pel pas ${k} de ${N} de «${item.problem ?? ""}» — escriu només aquesta operació.`;
}
