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
  type: "complete" | "choose" | "meaning" | "translate" | "correct";
  instruction: string;
  sentence: string;
  context: string;
  answer: string;
  also_accept: string[];
  options: string[];
  why: string;
}

export interface BankGrade {
  score: number;
  verdict: "correct" | "typo" | "wrong" | "empty";
  note: string;
  correct_version: string;
  item: BankItem;
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
  const kind = /(^|\.)vocab_/.test(item.competence) ? "Vocabulary" : "Grammar";
  const head = `## Exercise ${exerciseNumber}: ${kind} (${difficulty}) ${competenceName} ${tag}`;
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
