import { stepsV2CardTail } from "./steps.ts";

/**
 * Offline exercise bank: card text + feedback text, matching the visual
 * format the tutor writes today (measured live, nes-en, 2026-09-24 —
 * "## Exercise N: Writing (Easy) <name> <span class="comp-tag">id</span>",
 * "**Sentence:** ...", "**Type your answer (just the missing word):**",
 * then next turn "**Corrections:** / **Correct version:** / **Score: N/10**").
 * The wording of the feedback line was always the model's own free text, so
 * there is no single "correct" copy to match byte for byte — this mirrors
 * the observed shape closely; Albert checks it on screen before it's trusted.
 *
 * Selection and grading themselves stay in Python (hooks/bank.py), the same
 * way curriculum.py already owns pacing — this file only renders text and
 * shells out, so there is exactly one place (bank.py) that decides right or
 * wrong. See PLA-EXERCICIS-TANCATS.md.
 */

export interface BankItem {
  id: string;
  competence: string;
  type: "complete" | "choose" | "meaning" | "translate" | "correct" | "compute" | "compare" | "steps";
  instruction: string;
  /** Language items blank a "___" inside a sentence; math items carry a
   *  `problem` instead (DISSENY-MATEMATIQUES §4.1). */
  sentence?: string;
  problem?: string;
  /** Optional math-only: the error class a WRONG verdict is filed under
   *  (db_schema ERROR_CATEGORIES); defaults to "calculation". */
  error_class?: string;
  context: string;
  answer: string;
  also_accept: string[];
  options: string[];
  why: string;
  /** steps items only (WP2.2/§4.2): the expected worked solution. */
  method?: string;
  steps?: BankStep[];
}

/** One expected step of a `steps` item (hooks/bank.py serves these). */
export interface BankStep {
  n: number;
  expect: string;
  value?: string;
  accept?: string[];
  error_class?: string;
  why?: string;
}

/** One graded step (WP2.3): `got` is the learner's line for that step or
 *  null; `propagated` marks every step AFTER the first failure — it was not
 *  graded on its own, the error of the first failure simply carries over. */
export interface BankStepGrade {
  n: number;
  ok: boolean;
  got: string | null;
  propagated?: boolean;
}

export interface BankGrade {
  score: number;
  verdict: "correct" | "typo" | "near" | "wrong" | "empty";
  note: string;
  correct_version: string;
  /** What the learner typed, as mathgrade parsed it (math items). */
  got?: string;
  /** steps items only: one entry per expected step, in order. */
  steps?: BankStepGrade[];
  /** steps items only: the first failure's category and step number. */
  error_class?: string;
  failed_step?: number;
  /** steps items only (WP2.5): which interaction produced the trace — v1
   *  all-at-once (propagation) or v2 one-step-per-message (no propagation).
   *  Only the lead sentence differs; the parseable contract does not. */
  mode?: "v1" | "v2";
  item: BankItem;
}

/** compute/compare are math-only; `choose` exists in both domains — the
 *  language one blanks a sentence, the math one offers options for a problem.
 *  Same rule as hooks/bank.py `_is_math_item`. */
export function isMathItem(item: BankItem): boolean {
  return (
    item.type === "compute" ||
    item.type === "compare" ||
    item.type === "steps" ||
    (item.type === "choose" && Boolean(item.problem) && !item.sentence)
  );
}

const DEPTH_LABEL: Record<string, string> = { light: "Easy", normal: "Medium", deep: "Hard" };

/** No deterministic label existed before this — the model chose "Easy" /
 *  "Medium" / "Hard" on its own each time. This ties it to the curriculum's
 *  own Depth: field so it stops drifting. */
export function difficultyLabel(depth?: string | null): string {
  return DEPTH_LABEL[String(depth || "normal").toLowerCase()] ?? "Medium";
}

export function bankExerciseCard(
  item: BankItem,
  exerciseNumber: number,
  difficulty: string,
  competenceName: string,
  credited?: "yes" | "no",
  /** steps items only (WP2.5): "v2" asks for the FIRST operation only — the
   *  rest of the trace is collected one step per message (server/src/steps.ts).
   *  The "**Una operació per línia:**" marker line stays on the card either
   *  way: web/app.js detects it to switch the composer, and the mode then
   *  stays sticky across the exchange without re-detecting it. */
  stepsMode?: "v1" | "v2"
): string {
  const tag = `<span class="comp-tag"${credited ? ` data-credit="${credited}"` : ""}>${item.competence}</span>`;
  // Not "Writing": that is its own practice now (📝, open production). A bank
  // card is grammar or vocabulary, and the header said Writing on every one.
  const kind = item.type === "steps" ? "Steps"
    : isMathItem(item) ? "Calculation"
    : /(^|\.)vocab_/.test(item.competence) ? "Vocabulary" : "Grammar";
  const head = `## Exercise ${exerciseNumber}: ${kind} (${difficulty}) ${competenceName} ${tag}`;
  if (item.type === "steps") {
    // WP2.2/2.4: the learner writes the WHOLE worked solution, one operation
    // per line. The card keeps the math shape ("**Problem:**" fingerprints it,
    // "**Type your answer:**" is the answer marker) and adds the fixed
    // "**Una operació per línia:**" line — web/app.js detects THAT to switch
    // the composer to the multi-line placeholder (no numeric keypad).
    if (stepsMode === "v2") {
      // WP2.5: same card, but it asks for the FIRST operation only; the
      // server collects the rest one step per message (server/src/steps.ts).
      return `${head}\n\n**Problem:** ${item.problem}\n\n**Una operació per línia:**\n\n` +
        stepsV2CardTail(item);
    }
    return `${head}\n\n**Problem:** ${item.problem}\n\n**Una operació per línia:**\n\n**Type your answer:**`;
  }
  if (isMathItem(item)) {
    // Math card: the problem, the options when the answer is a pick, and the
    // math marker line (web/app.js recognizes "**Type your answer:**" as mode
    // "math" — the two parenthesized language markers keep working unchanged).
    const opts = item.options?.length ? `\n**Options:** ${item.options.join("   ·   ")}` : "";
    return `${head}\n\n**Problem:** ${item.problem}${opts}\n\n**Type your answer:**`;
  }
  if (item.type === "meaning") {
    return `${head}\n\n**Meaning:** ${item.instruction} ${item.sentence}\n**Word:** ___`;
  }
  if (item.type === "translate") {
    return `${head}\n\n**Translate:** ${item.instruction}\n**Word:** ___`;
  }
  if (item.type === "correct") {
    return `${head}\n\n**Sentence to correct:** "${item.sentence}"\n\n**Type the correct sentence:**`;
  }
  return `${head}\n\n**Sentence:** ${item.sentence}\n\n**Type your answer (just the missing word):**`;
}

export function bankFeedback(g: BankGrade): string {
  if (g.item.type === "steps") return stepsFeedback(g);
  if (isMathItem(g.item)) return mathFeedback(g);
  const known = g.score >= 8; // KNOWN_SCORE, pacing.ts
  const marker = known ? "✅" : g.verdict === "typo" ? "🟡" : "❌";
  const lead = known
    ? `${marker} Perfect! "${g.correct_version}" is right.`
    : g.verdict === "typo"
      ? `${marker} Almost — ${g.note}.`
      : `${marker} Close! The correct form is "${g.correct_version}".`;
  const correctionLine = known
    ? `- ✅ "${g.correct_version}" — exactly right.`
    : `- ❌ → **"${g.correct_version}"**${g.note ? ` (${g.note})` : ""}`;
  const closing =
    g.score >= 10
      ? "🎉 Perfect! You got it right on the first try. Keep up the good work!"
      : known
        ? "👍 Correct!"
        : g.verdict === "typo"
          ? "One letter away. Try the next one!"
          : "Keep practising — you'll get it.";
  return (
    `${lead}\n\n**Corrections:**\n${correctionLine}\n\n**Correct version:**\n"${g.correct_version}"\n\n` +
    `**Score: ${g.score}/10** ${closing}`
  );
}

/** The annotated trace of a `steps` item (WP2.4, §4.5): one line per expected
 *  step — ✅, or ❌ with the expected expression, what the learner wrote, and
 *  the step's `why` for the FIRST failure; steps after it say they carry the
 *  first failure's error (they were not graded on their own). The parseable
 *  contract is unchanged: a `- ❌ "got" → **"right"** (category — why)` line
 *  with the failed step's error_class, "Correct version:" = the full correct
 *  trace (one step per line), and the "**Score: N/10**" line. */
function stepsFeedback(g: BankGrade): string {
  const known = g.score >= 8; // KNOWN_SCORE, pacing.ts
  const marker = known ? "✅" : g.verdict === "near" ? "🟡" : "🔴";
  const recs = g.steps ?? [];
  const recByN = new Map(recs.map((s) => [s.n, s]));
  const firstFail = recs.find((s) => !s.ok && !s.propagated) ?? null;
  const itemSteps = g.item.steps ?? [];
  // The learner's line goes inside quotes and backticks — a stray " or ` in
  // it would break the parseable correction line and the markdown alike.
  const safe = (t: string) => String(t ?? "").replace(/["`]/g, "'");
  const wantLine = (s: BankStep) => (s.value && s.value !== s.expect ? `${s.expect} = ${s.value}` : s.expect);
  const trace = itemSteps.map((s) => {
    const rec = recByN.get(s.n);
    const want = wantLine(s);
    if (rec?.ok) return `- ✅ ${s.n} · \`${want}\``;
    if (rec?.propagated) return `- ❌ ${s.n} · \`${want}\` · arrossega l'error del pas ${firstFail?.n ?? "?"}`;
    const got = rec?.got ? `has escrit \`${safe(rec.got)}\`` : "no has escrit res per a aquest pas";
    const why = s.why ? ` — ${s.why}` : "";
    return `- ❌ ${s.n} · esperat \`${want}\` · ${got}${why}`;
  });
  // v1: the first non-propagated failure. v2 (WP2.5): a retried-then-correct
  // step has ok=true so there is no failed trace entry — the correction still
  // names the step that needed the retry, which finalize_steps put in
  // failed_step. (For v1 failed_step === firstFail.n, so this changes nothing
  // there.)
  const failStep = firstFail
    ? itemSteps.find((s) => s.n === firstFail.n) ?? null
    : g.failed_step != null
      ? itemSteps.find((s) => s.n === g.failed_step) ?? null
      : null;
  const lead = known
    ? `${marker} Perfect! Tot el procediment és correcte.`
    : g.verdict === "near"
      ? `${marker} Gairebé — ${g.note}.`
      : firstFail
        ? g.mode === "v2"
          ? `${marker} El pas ${firstFail.n} no et sortia; te'l vaig haver de revelar.`
          : `${marker} El pas ${firstFail.n} falla; els de després arrosseguen l'error.`
        : `${marker} Not quite.`;
  const category = g.verdict === "near" ? "calculation" : String(g.error_class || g.item.error_class || "calculation");
  const why = failStep?.why || g.note || "revisa el procediment";
  const want = failStep ? wantLine(failStep) : "";
  const got = safe(String(g.got ?? ""));
  const correctionLine = known
    ? `- ✅ "${g.item.problem}" — tot el procediment correcte.`
    : got
      ? `- ❌ "${got}" → **"${want}"** (${category} — ${why})`
      : `- ❌ → **"${want}"** (${category} — ${why})`; // missing step: nothing was written there
  const closing =
    g.score >= 10
      ? "🎉 Perfect! You got it right on the first try. Keep up the good work!"
      : known
        ? "👍 Correct!"
        : g.verdict === "near"
          ? "Very close — read the note and try the next one!"
          : "Keep practising — you'll get it.";
  return (
    `${lead}\n\n**Passos:**\n${trace.join("\n")}\n\n**Corrections:**\n${correctionLine}\n\n` +
    `**Correct version:**\n"${g.correct_version}"\n\n` +
    `**Score: ${g.score}/10** ${closing}`
  );
}

/** Math verdicts (compute/choose/compare, graded by hooks/mathgrade.py): the
 *  same parseable contract persist-session.parse_error_patterns reads — a
 *  severity marker aligned with the score (✅ / 🟡 near / 🔴 wrong), a
 *  `- ❌ "got" → **"right"** (category — why)` correction ONLY when the
 *  answer was wrong or near, "Correct version:" = the problem with the answer
 *  filled in, and the "**Score: N/10**" line. Category: near is always
 *  "calculation" (a transcription slip); wrong uses the item's optional
 *  `error_class` (db_schema ERROR_CATEGORIES) and falls back to "calculation". */
function mathFeedback(g: BankGrade): string {
  const known = g.score >= 8; // KNOWN_SCORE, pacing.ts
  const marker = known ? "✅" : g.verdict === "near" ? "🟡" : "🔴";
  const lead = known
    ? `${marker} Perfect! "${g.correct_version}" is right.`
    : g.verdict === "near"
      ? `${marker} Almost — ${g.note}.`
      : `${marker} Not quite — the correct answer is "${g.correct_version}".`;
  const category = g.verdict === "near" ? "calculation" : String(g.item.error_class || "calculation");
  const why = g.verdict === "near" ? g.note : g.item.why || g.note || "revisa el càlcul";
  const got = String(g.got ?? "");
  const correctionLine = known
    ? `- ✅ "${g.correct_version}" — exactly right.`
    : got
      ? `- ❌ "${got}" → **"${g.correct_version}"** (${category} — ${why})`
      : `- ❌ → **"${g.correct_version}"** (${category} — ${why})`; // empty answer: nothing was written
  const closing =
    g.score >= 10
      ? "🎉 Perfect! You got it right on the first try. Keep up the good work!"
      : known
        ? "👍 Correct!"
        : g.verdict === "near"
          ? "Very close — read the note and try the next one!"
          : "Keep practising — you'll get it.";
  return (
    `${lead}\n\n**Corrections:**\n${correctionLine}\n\n**Correct version:**\n"${g.correct_version}"\n\n` +
    `**Score: ${g.score}/10** ${closing}`
  );
}
