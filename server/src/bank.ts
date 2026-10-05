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
  type: "complete" | "choose" | "meaning" | "translate" | "correct" | "compute" | "compare";
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
}

export interface BankGrade {
  score: number;
  verdict: "correct" | "typo" | "near" | "wrong" | "empty";
  note: string;
  correct_version: string;
  /** What the learner typed, as mathgrade parsed it (math items). */
  got?: string;
  item: BankItem;
}

/** compute/compare are math-only; `choose` exists in both domains — the
 *  language one blanks a sentence, the math one offers options for a problem.
 *  Same rule as hooks/bank.py `_is_math_item`. */
export function isMathItem(item: BankItem): boolean {
  return (
    item.type === "compute" ||
    item.type === "compare" ||
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
  credited?: "yes" | "no"
): string {
  const tag = `<span class="comp-tag"${credited ? ` data-credit="${credited}"` : ""}>${item.competence}</span>`;
  // Not "Writing": that is its own practice now (📝, open production). A bank
  // card is grammar or vocabulary, and the header said Writing on every one.
  const kind = isMathItem(item) ? "Calculation" : /(^|\.)vocab_/.test(item.competence) ? "Vocabulary" : "Grammar";
  const head = `## Exercise ${exerciseNumber}: ${kind} (${difficulty}) ${competenceName} ${tag}`;
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
