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
 * Retry policy (bounded, so a stuck learner never loops): TWO attempts per
 * step. The first failure gets a retry note; the second reveals that step's
 * expected line, marks the step failed, and moves on — the learner continues
 * the trace with the corrected state.
 *
 * Scoring (mirrors v1's 10/7/3 exactly, see hooks/bank.py `finalize_steps`):
 * every step right on the first try → 10; every step right but one needed a
 * retry → 7; a step had to be revealed → 3.
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
  /** failed attempts on the pending step (0 or 1; 2 reveals). */
  attempts: number;
  /** the pending step's first rejected line, kept across its attempts. */
  firstWrong?: string;
  firstNear?: boolean;
  results: StepsV2Result[];
}

export const STEPS_V2_MAX_ATTEMPTS = 2;

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
  return { kind: "retry", done: false, step, result: { n: step.n, ok: false, got: line, attempts: state.attempts } };
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
    const lead = move.result.near
      ? `🟡 Gairebé, pas ${k} de ${N}: el resultat és a un dígit del que toca.`
      : `❌ Aquesta línia no és el pas ${k} de ${N}.`;
    const goal = (item.steps ?? []).find((x) => x.n === k)?.goal?.trim();
    const hint = goal ? `\n\n**Pas ${k} de ${N}** — ${goal.replace(/[.:]+$/, "")}.` : "";
    return `${lead}\n\n${prob}${hint}\n\nEscriu només aquest pas i torna-ho a provar.`;
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
