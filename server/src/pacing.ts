// Fluent server — session pacing.
//
// How many exercises a practice session runs for was only ever a sentence in a
// skill ("plan a 20-min session… 3-4 exercises"), and a model counting its own
// turns is not a mechanism: the same command could end after 8 exercises or
// drag on past 18. The length belongs to the learner (an 8-year-old and a
// teenager do not want the same session), and enforcing it belongs to the
// server, which now knows exactly how many answers have been graded — the
// structured records of math_record_answer.
//
// Kept free of Bun imports so server/test/*.test.ts can exercise it under node.
// (normalizeSkillKey lives in tools.ts — the record layer's single source for
// the five math skill keys — and pulls in nothing but node builtins.)
import { normalizeSkillKey } from "./tools.ts";

/** Exercises per practice session when the profile does not say. */
export const DEFAULT_SESSION_LENGTH = 12;

// ---- the guided Lesson, and the day's goal ---------------------------------
//
// "12" used to be one number pretending to be two things: a budget (how much
// today) and a plan (what today). It was neither, which is why passing it —
// 15/12 on a live session — meant nothing. They are now separate:
//
//   🎓 Lesson  — has an END. Today's due review items, topped up with drills on
//                weak patterns so it is never a token gesture. Nothing is
//                blocked: the badge says what is left, and that is all.
//   ✏️ N       — has no end. Everything graded today, free play included.

/** The Lesson is what is pending, however much that is: 2 items or 15. Only an
 *  EMPTY queue gets this many drills on weak patterns, so "nothing due" is
 *  still a (short) lesson rather than "bye". No padding otherwise. */
export const LESSON_MINIMUM = 3;

/** Answers a day aims for. The face on the counter walks up to it. */
export const DEFAULT_DAILY_GOAL = 15;

export function resolveDailyGoal(profile: unknown): number {
  const prefs = (profile as { preferences?: Record<string, unknown> })?.preferences ?? {};
  const raw = prefs.daily_goal ?? prefs.session_length;
  if (raw === 0 || raw === "0") return 0;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return DEFAULT_DAILY_GOAL;
  return Math.max(1, Math.min(100, Math.round(n)));
}

/**
 * The daily badge for a single-exercise reminder (Speaking, Reading): done
 * once today's count is ≥1, out of a fixed target of 1. Same shape as the
 * Lesson badge (`total`/`done`/`pending`) so the web side can reuse one
 * rendering function for all three buttons, but with none of the Lesson's
 * own complexity (no due-item count, no drills, no slot) — it is just "have
 * you done one of these today, via this button", nothing more.
 */
export function skillBadge(countToday: number): { total: number; done: number; pending: number } {
  const done = Math.min(1, Math.max(0, countToday));
  return { total: 1, done, pending: 1 - done };
}

/**
 * How long today's Lesson is.
 *
 * Exactly what is due (capped by the daily limit): the part that cannot wait
 * without breaking the spacing. No padding to a fixed size. With an empty queue
 * the lesson is LESSON_MINIMUM drills on weak patterns, so it is never "nothing
 * due, bye".
 */
export function lessonTarget(sr: unknown, today: string): { total: number; due: number; drills: number } {
  const due = dueItemIds(sr, today).length;
  const limit = reviewDailyLimit(sr);
  const total = due > 0 ? Math.min(due, Math.max(limit, 1)) : LESSON_MINIMUM;
  return { total, due: Math.min(due, total), drills: Math.max(0, total - due) };
}

/**
 * The face beside the day's count.
 *
 * Four steps, at 0 / a third / two thirds / done. 😐 and 😑 are the same eight
 * grey pixels at this size, so the ladder starts neutral and climbs from there
 * — the point is that it visibly moves, not that it starts sad.
 */
export function dailyFace(graded: number, goal = DEFAULT_DAILY_GOAL): string {
  if (goal <= 0) return graded > 0 ? "🙂" : "😐";
  if (graded >= goal) return "🤩";
  if (graded >= Math.round((goal * 2) / 3)) return "😄";
  if (graded >= Math.round(goal / 3)) return "🙂";
  return "😐";
}

/**
 * What happens when the target is reached.
 *  - "soft" (default): the tutor OFFERS to finish — the learner decides.
 *  - "hard": the tutor closes.
 * A number on its own is a wall; a number you can see is orientation. The
 * count is shown in the UI either way, so reaching it never comes as a
 * surprise.
 */
export type StopMode = "soft" | "hard";

/** Modes that end on their own shape, not on a count of exercises: one
 *  explained solution (reasoning) or one word problem (problems) is a whole
 *  practice, not one item of a dozen. Math skill keys (C7). */
const SELF_LIMITING_SKILLS = new Set(["reasoning", "problems"]);

export function resolveSessionTarget(profile: unknown): number {
  const prefs = (profile as { preferences?: Record<string, unknown> })?.preferences ?? {};
  const raw = prefs.session_length;
  if (raw === 0 || raw === "0") return 0; // explicitly switched off
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return DEFAULT_SESSION_LENGTH;
  return Math.max(1, Math.min(60, Math.round(n)));
}

export function resolveStopMode(profile: unknown): StopMode {
  const prefs = (profile as { preferences?: Record<string, unknown> })?.preferences ?? {};
  return String(prefs.session_stop ?? "soft").toLowerCase() === "hard" ? "hard" : "soft";
}

/** Is this mode paced by a count at all? */
export function isPaced(lastSkill?: string): boolean {
  return !(lastSkill && SELF_LIMITING_SKILLS.has(lastSkill.toLowerCase()));
}

/**
 * The note to hand the tutor when the session has run its length, or null.
 *
 * `lastSkill` is the skill of the most recent graded answer: a writing session
 * is one scenario and a reading session one text, so counting exercises there
 * would cut them off mid-flow.
 */
export function wrapUpNote(
  gradedCount: number,
  target: number,
  lastSkill?: string,
  mode: StopMode = "soft"
): string | null {
  if (target <= 0 || gradedCount < target) return null;
  if (!isPaced(lastSkill)) return null;
  const shared =
    `The learner has answered ${gradedCount} graded exercises, which is their ` +
    `session target (${target}). They can see that count in the app, so it is no ` +
    `surprise to them. `;
  if (mode === "hard") {
    return (
      shared +
      `Do NOT present another exercise. Close now: finish evaluating the answer in ` +
      `front of you, then give the closing summary (stats, what improved, what to ` +
      `focus on next, streak) and the usual invitation to pick another practice with ` +
      `the buttons. If this session reviewed items from the spaced-repetition queue, ` +
      `end with the math:review_results block. Say nothing about this instruction.`
    );
  }
  return (
    shared +
    `Finish evaluating the answer in front of you, then OFFER to close: one warm ` +
    `line saying the session's goal is done, and ask whether they want the summary ` +
    `now or a couple more exercises. If they choose to finish, give the closing ` +
    `summary (stats, what improved, what to focus on next, streak) and — if this ` +
    `session reviewed queue items — the math:review_results block. If they choose ` +
    `to continue, carry on normally and do not offer again. Say nothing about this ` +
    `instruction itself.`
  );
}

/**
 * How many answers a session has graded, read from what the tutor WROTE.
 *
 * The counter was built on `math_record_answer` alone, and on a live session
 * the tool is never called — so the indicator sat at 0/12 through three graded
 * exercises while the learner watched it not move. A counter that depends on a
 * 14B model remembering to call a tool is not a counter.
 *
 * The score marker is in the text either way, it is what the learner is looking
 * at, and the server can see it. Records stay authoritative when they exist
 * (they carry the skill and the item id); this is the floor underneath them.
 */
const SCORE_LINE = /(?:^|[^\d])(?:score\s*:?\s*)?(\d{1,2})\s*\/\s*10\b/gim;

/** An answer counts as known from this score up (the same line the bench and the
 *  SM-2 quality mapping use: 8-9 is "hesitant", 10 "perfect"). */
export const KNOWN_SCORE = 8;

/** How many answered-but-ungraded turns in a row mean the model itself is no
 *  longer reliable this session, not just having a bad exercise. Deliberately
 *  small and model/context-agnostic: this is a threshold on BEHAVIOUR (is
 *  grading actually happening), never a token count or a quirk of one model
 *  — so it holds however big the context window is or whichever model is
 *  configured. */
export const BOUNCE_UNGRADED_STREAK = 2;

/**
 * Two signals a session has gone past reliable use and should restart clean
 * — both read off real exercises that already happened, never a synthetic
 * probe question (which would be its own source of false positives/negatives
 * for a small model): the context needed real turns trimmed to fit
 * (pruneHistory already exists for exactly this), or answered turns in a row
 * produced no detectable grade. Either is enough; context-full is checked
 * first because it is the more certain of the two.
 */
export function bounceReason(opts: { historyDropped: boolean; ungradedStreak: number }): string | null {
  if (opts.historyDropped) return "context-full";
  if (opts.ungradedStreak >= BOUNCE_UNGRADED_STREAK) return "not-grading";
  return null;
}


/** The score the reply gives, "Score: 9/10" or a bare "9/10", or null.
 *  Headings are skipped: "## Word 8/10" is progress through a set, not a grade
 *  (read as one, every eighth word of Vocabulary would count as known). */
export function scoreOfReply(text: string): number | null {
  const body = String(text || "")
    .split("\n")
    .filter((l) => !/^\s*#{1,6}\s/.test(l))
    .join("\n");
  const m = /\*{0,2}Score:?\*{0,2}\s*(\d{1,2})\s*\/\s*10/i.exec(body) ||
    /\b(\d{1,2})\s*\/\s*10\b/.exec(body);
  return m ? Math.min(10, Number(m[1])) : null;
}

export function countGradedInText(messages: Iterable<string>): number {
  let n = 0;
  for (const text of messages) {
    SCORE_LINE.lastIndex = 0;
    // One score per message: the tutor's breakdown ("Communication: 4/5") is
    // out of 5, not 10, and a message grades exactly one answer.
    if (/\b\d{1,2}\s*\/\s*10\b/.test(String(text || ""))) n += 1;
  }
  return n;
}

/**
 * Which skills are being avoided.
 *
 * Writing and reading are the ones a learner quietly drops: they are longer and
 * harder than a flashcard, so a week of "vocabulary, vocabulary, vocabulary"
 * looks like diligence and is a hole. mastery-db already records when each
 * skill was last practised, so the debt is a subtraction, not new bookkeeping.
 *
 * It is shown, never enforced: a dot on the button, and a slot in the Lesson.
 */
export const SKILL_DEBT_DAYS = 3;
// The five math skill keys (C7). mastery-db stores them under `skills` — the
// old `skills_mastery` spelling never existed in any writer, so the debts
// silently read an empty object (WP1.7, 2026-10-06).
export const TRACKED_SKILLS = ["computation", "steps", "problems", "reasoning", "facts"] as const;

export interface SkillDebt {
  skill: string;
  daysIdle: number | null; // null = never practised
  due: boolean;
}

export function skillDebts(masteryDb: unknown, today: string, thresholdDays = SKILL_DEBT_DAYS): SkillDebt[] {
  const skills = (masteryDb as { skills?: Record<string, { last_practiced?: unknown }> })
    ?.skills ?? {};
  const todayMs = Date.parse(`${today}T00:00:00Z`);
  return TRACKED_SKILLS.map((skill) => {
    const last = skills[skill]?.last_practiced;
    if (typeof last !== "string" || !last.trim()) {
      return { skill, daysIdle: null, due: true };
    }
    const lastMs = Date.parse(`${String(last).slice(0, 10)}T00:00:00Z`);
    if (!Number.isFinite(lastMs) || !Number.isFinite(todayMs)) {
      return { skill, daysIdle: null, due: true };
    }
    const daysIdle = Math.max(0, Math.round((todayMs - lastMs) / 86400000));
    return { skill, daysIdle, due: daysIdle >= thresholdDays };
  });
}

/**
 * Every third Lesson reserves a slot for a skill being avoided.
 *
 * Days-idle alone is a poor trigger for someone who practises in bursts: a week
 * off makes everything overdue at once. Tying it to lesson cadence instead
 * means the obligation arrives at a steady rate — two lessons as you like, the
 * third carries one piece of reasoning or a word problem — and it only fires
 * when the skill really has been skipped.
 */
export const SKILL_SLOT_EVERY = 3;
/** Only the two that get quietly dropped — the open-ended ones; nobody avoids
 *  flashcards (facts) and Go is all computation. Math keys (C7). */
export const SLOT_SKILLS = ["reasoning", "problems"] as const;

export function lessonSkillSlot(
  lessonsCompleted: number,
  debts: SkillDebt[],
  every = SKILL_SLOT_EVERY
): string | null {
  if (every <= 0) return null;
  if ((Math.max(0, lessonsCompleted) + 1) % every !== 0) return null;
  const candidates = debts
    .filter((d) => (SLOT_SKILLS as readonly string[]).includes(d.skill) && d.due)
    .sort((a, b) => (b.daysIdle ?? 9999) - (a.daysIdle ?? 9999));
  return candidates[0]?.skill ?? null;
}

/**
 * A short fingerprint of every exercise a message poses.
 *
 * "Never repeat an exercise" was a line in rules.md, and a 14B with a handful
 * of weak patterns to drill loops back to the same three sentences within one
 * lesson: "A book of english", "where are the park", "I lunch", and round
 * again. Telling it not to is not a mechanism. Recording what has been asked
 * and handing back the list is.
 *
 * Matches the shapes this tutor actually writes:
 *     ## Exercise 6: Grammar (A book of english)
 *     **Sentence:** A book of english
 *     **Question:** Rewrite this sentence correctly.
 */
const EXERCISE_MARKS = [
  /\*\*Sentence:?\*\*\s*(.+)/gi,
  /^#{1,6}\s*(?:Exercise|Question)\s*\d*\s*:?[^(\n]*\(([^)]{3,80})\)/gim,
  // "**Exercise:** What is the Catalan word for "afternoon"?" — the shape a
  // spaced-review item comes in. Without it, the only thing fingerprinted from
  // such a turn was the heading's parenthetical, which is the difficulty, not
  // the exercise: a real plan file from 2026-09-16 has "critical" sitting in
  // its already-asked list, once, standing in for fifteen different questions.
  /\*\*(?:Exercise|Item ID):?\*\*\s*(.+)/gi,
  // The math bank card (bank.ts, WP1.3): "**Problem:** 24 × 3" with a bare
  // "**Type your answer:**" below. Without this mark the card only fingerprinted
  // through EXERCISE_FALLBACK_MARKS — which never runs once any primary mark
  // matches elsewhere in a bundled feedback+question message, so the
  // already-asked guard could not reliably stop the bank repeating an item
  // (found by WP1.6, 2026-10-06).
  /\*\*Problem:?\*\*\s*(.+)/gi,
  // A Writing exercise is a scenario and a task ("Write a short email…", an
  // instruction, which BARE_INSTRUCTION rightly refuses). It had no fingerprint at
  // all, so the server could not tell that a Writing answer was waiting, and a
  // reply that ignored it (a new exercise built from the answer) went unchecked.
  /\*\*Scenario:?\*\*:?\s*(.+)/gi,
  // The curriculum's own Check shapes ("Complete: X", "Complete the sentence:
  // X") land in a plain "Question:" line with no "**Sentence:**" and a heading
  // that is "Exercise N: Writing (Easy) a1.present_simple" — no "/M", no
  // "Question N:", no quoted subject under a bare label. None of the marks
  // above catch it, and it does not fall to EXERCISE_FALLBACK_MARKS either
  // unless "Question:" happens to be bold. Measured live, 2026-09-23: "They
  // ___ (not/like) cheese." asked three times in one session, unnoticed —
  // fingerprinted to nothing every time. Unlike a bare "Question:" (sometimes
  // a generic instruction, kept out of EXERCISE_MARKS on purpose — see
  // EXERCISE_FALLBACK_MARKS below), "Complete the sentence:"/"Complete:" is
  // one of curriculum.py's own Check verbs and always carries the actual
  // sentence inline, so it is safe here.
  /\*{0,2}Question:?\*{0,2}\s*Complete(?: the sentence)?:?\s*(.{4,150})/gi,
];

/** Only when nothing above matched. "**Question:**" is sometimes the exercise
 *  ("What is the correct spelling of 'today'?") and sometimes a generic
 *  instruction ("Rewrite this sentence correctly") that belongs to every
 *  exercise of that shape. Recording the generic one would quote it back as
 *  already-asked and ban a whole exercise type for the rest of the day. */
const EXERCISE_FALLBACK_MARKS = [
  /\*\*Question:?\*\*\s*(.+)/gi,
  // A vocabulary card labels its term with the language, and the language
  // varies by learner: "**English:** apple", "**Català:** poma". Measured over
  // a whole Vocabulary practice: not one card fingerprinted, so the
  // already-asked list stayed empty and nothing could tell a repeat from a new
  // word. Any short bolded label with a short value, minus the labels that are
  // structure rather than content.
  /^\*\*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ]{2,19})\s*(?:\([^)]{0,20}\))?:\*\*[ \t]*(.{1,60})$/gim,
  // The qualifier is part of how the tutor writes these: "**Word (Catalan):**
  // l'anglès". Without it none of a whole run of vocabulary exercises was
  // fingerprinted, so they never reached the already-asked list.
  /\*\*(?:Translate|Word|Phrase|Sentence)\s*(?:\([^)]{0,40}\))?\s*:?\*\*\s*(.+)/gi,
];

/** The quoted subject of an exercise, when there is one.
 *
 *  "What is the correct article to use before the word \"apple\"?" is not the
 *  same exercise as the one about "house", but as whole sentences they differ
 *  by one word out of eleven and share every instruction word. Fingerprinting
 *  the sentence made six legitimate article drills look like six repetitions of
 *  one, and the guard rewrote them all: twenty-seven rewrites in thirty-three
 *  turns, which is not a safety net, it is the tutor's main obstacle.
 *
 *  What identifies an exercise is what it is ABOUT. These exercises say so, in
 *  quotes, because the learner has to see which word is meant. */
const QUOTED_SUBJECT = /["“”'«]([^"“”'»\n]{2,40})["“”'»]/;
const ITALIC_SUBJECT = /(?<![*\w])\*([^*\n]{2,40})\*(?![*\w])/;

/** An imperative with nothing named after it: "Choose the correct article for
 *  the sentence", "Rewrite this sentence correctly". It is the wrapper around
 *  an exercise, identical for every exercise of that shape, and recording it
 *  bans the shape for the rest of the day. */
const BARE_INSTRUCTION =
  /^(choose|complete|fill|rewrite|select|write|translate|identify|match|correct|put|change)\b/i;

export function normalizeExercise(raw: string): string {
  const quoted = QUOTED_SUBJECT.exec(String(raw || ""));
  if (quoted) return normalizeLabel(quoted[1]!);
  const label = normalizeLabel(raw);
  return BARE_INSTRUCTION.test(label) ? "" : label;
}

function normalizeLabel(raw: string): string {
  // Trim BEFORE stripping the trailing punctuation, not after. With a single
  // trailing space the `$` never matched, so "…word for perquè?" and "…word for
  // perquè" were two different exercises as far as the already-asked list was
  // concerned — and the guard let the repeat through. Both forms sat side by
  // side in a real plan file.
  return String(raw || "")
    .replace(/[*_`"\u201c\u201d]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[.?!,;:¿¡"'\u2026]+$/u, "")
    .trim()
    .toLowerCase()
    .slice(0, 80);
}

/** Words that name a category or a difficulty, never an exercise. Fingerprinting
 *  one of these puts "critical" on the already-asked list and lets fifteen
 *  distinct questions hide behind it — observed, in a real plan file. */
const NOT_AN_EXERCISE = new Set([
  "easy", "medium", "hard", "critical", "review", "spaced review", "drill", "new",
  // Language-era skill words: kept as a deny-list — old transcripts and the
  // preserved language path still carry them, and a fingerprinted category
  // hides fifteen real questions behind one word.
  "vocabulary", "grammar", "spelling", "capitalization", "writing", "reading",
  "speaking", "listening", "translation", "practice",
  // Math kind-words (C7 / the bank card headings of bank.ts: "Calculation",
  // "Steps"). WP1.9: a card heading's parenthetical is the difficulty, but a
  // tutor that writes "**Exercise:** Steps" or a heading without "(Easy)"
  // must not fingerprint the KIND. Catalan spellings too — the tutor answers
  // in the learner's language.
  "calculation", "computation", "steps", "problems", "word problem", "reasoning",
  "facts", "math talk", "càlcul", "computació", "passos", "problemes", "raonament",
  "fets",
  // Priority tags on a review card ("Review (High Priority)") are not exercises.
  "high priority", "medium priority", "low priority", "critical priority", "priority",
  "high", "low",
]);

/** At most this many per turn: one exercise usually matches two markers (its
 *  sentence and its question), and a third is repetition, not information. The
 *  list is quoted back to the tutor every turn, so its length is context. */
const MAX_FINGERPRINTS_PER_TURN = 2;

/** Bolded labels that carry structure, not the exercise. */
const NOT_A_LABEL = new Set([
  "corrections", "correct version", "correct answer", "answer", "score", "type",
  "context", "last reviewed", "current mastery", "scenario", "tip", "hint",
  "streak", "reviewed", "accuracy", "time", "breakdown", "definition", "note",
  // The closing summary. Its "**What to work on:** Keep practicing to maintain
  // your progress" was read as an exercise and put on the already-asked list, so
  // the (correct) closing message of a finished lesson counted as a repeated
  // question — three runs of six, and a guard event each time.
  "what went well", "what to work on", "need more practice", "good", "mastered",
  "strong", "next review", "tomorrow", "this week", "words reviewed",
  "words mastered", "new words learned", "well done", "summary",
  // The opening of a lesson ("**Items Due Today:** 6", "**Estimated Time:** ~12
  // min"). With nothing else fingerprinted in that reply, "~12 min" WAS the
  // first exercise: the first answer was credited to it, and the guard then
  // reported "already counted: ~12 min" five times per run.
  "items due today", "items due", "estimated time", "estimated", "duration",
  "total", "goal", "focus", "level", "progress",
]);

function collect(text: string, marks: RegExp[]): string[] {
  const out: string[] = [];
  for (const re of marks) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      // A two-group mark is <label>:<value>; the label decides whether the
      // value is an exercise at all.
      if (m.length > 2) {
        if (NOT_A_LABEL.has((m[1] ?? "").trim().toLowerCase())) continue;
        m = [m[0], m[2]] as unknown as RegExpExecArray;
      }
      const label = normalizeExercise(m[1] ?? "");
      // Two letters are enough when the subject is quoted: "pa", "mà", "ou" are
      // whole words, and a card about one of them fingerprinted to nothing.
      const short = label.length === 2 && QUOTED_SUBJECT.test(m[1] ?? "");
      if ((label.length < 3 && !short) || NOT_AN_EXERCISE.has(label) || out.includes(label)) continue;
      out.push(label);
    }
  }
  return out;
}

/** The exercise when "**Exercise:**" stands alone on its line and the content
 *  comes below it:
 *
 *      **Exercise:**
 *      Complete the sentence with the correct form of the word:
 *      "She ___ to school every day."
 *
 *  The one-line marks above read only the line after the label, which is the
 *  instruction, and an instruction is dropped on purpose. So this whole shape
 *  fingerprinted to nothing: measured in a six-run bench, one sentence asked six
 *  and seven times in a row and the repeat guard never saw it, because there was
 *  nothing to compare. The exercise is the quoted line. Only a quoted line
 *  counts: guessing at an unquoted one would put an instruction on the
 *  already-asked list, which is the mistake BARE_INSTRUCTION exists to prevent. */
function collectBlock(text: string): string[] {
  const out: string[] = [];
  const re = /\*\*(?:Exercise|Item ID):?\*\*[ \t]*\n((?:[ \t]*[^\n*][^\n]*(?:\n|$)){1,4})/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    for (const line of (m[1] ?? "").split("\n")) {
      const q = /^\s*["\u201c\u00ab](.{2,120}?)["\u201d\u00bb][.?!:]?\s*$/.exec(line);
      if (!q) continue;
      const label = normalizeLabel(q[1]!);
      if (label.length >= 2 && !NOT_AN_EXERCISE.has(label) && !out.includes(label)) out.push(label);
      break;
    }
  }
  return out;
}

/**
 * The exercise of a numbered review card that has NO "**Exercise:**" label:
 *
 *     ## Review 2/6 — medium
 *     **Type:** vocabulary
 *     **Last reviewed:** 1 day ago
 *     What is the English word for "finestra"?
 *     **Type your answer:**
 *
 * Some profiles get this shape (an A1 profile did, in every run measured on
 * 2026-09-20), and it fingerprinted to nothing: the server believed every reply
 * asked nothing, guarded 7-9 turns per run, and credited answers to whatever else
 * looked like a label. The exercise is the first unlabeled line of the card with a
 * quoted subject — the same rule as `collectBlock`, and for the same reason.
 */
function collectReviewCard(text: string): string[] {
  const out: string[] = [];
  // The heading is either numbered ("Review 2/6") or the card's own title
  // ("# 🔄 Today's Spaced Repetition Review"): measured 2026-09-21 (days, A2
  // profile) the title-only card fingerprinted to nothing on every turn of a
  // day — "asks nothing" guards, nothing credited, and the feedback shifted.
  // Two passes, not one alternation: a lesson opening has the title AND a
  // numbered card under it, and one match would swallow the other.
  const HEADINGS = [
    /^#{1,6}\s*(?:Review|Exercise|Question)\s*\d+\s*\/\s*\d+[^\n]*\n((?:[^\n]*(?:\n|$)){1,9})/gim,
    /^#{1,6}\s*[^\n]*?\bSpaced Repetition Review\b[^\n]*\n((?:[^\n]*(?:\n|$)){1,9})/gim,
  ];
  for (const re of HEADINGS) collectCards(text, re, out);
  return out;
}

function collectCards(text: string, re: RegExp, out: string[]): void {
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    for (const line of (m[1] ?? "").split("\n")) {
      const t = line.trim();
      if (/^#{1,6}\s/.test(t) || /type your answer/i.test(t)) break;
      if (!t || t === "---" || t.startsWith("**")) continue;
      // "What is the English word for *finestra*?" — the subject in italics.
      // Measured 2026-09-21 (days, A2 profile): nothing found, so the reply was
      // "asking nothing", the lesson credited nothing and the guard rewrote a
      // perfectly good turn.
      let q = QUOTED_SUBJECT.exec(t);
      if (!q) {
        // "*Type:* vocabulary" is a field of the card, not its subject.
        const it = ITALIC_SUBJECT.exec(t);
        q = it && !/[:：]/.test(it[1]!) ? it : null;
      }
      if (!q) continue;
      const label = normalizeLabel(q[1]!);
      if (label.length >= 2 && !NOT_AN_EXERCISE.has(label) && !out.includes(label)) out.push(label);
      break;
    }
  }
}

/**
 * `math-speaking`'s own card: `## Question {N}: {Topic}` (or, the shape the
 * tutor actually writes, `## Question {N}/{total}: {Topic}`) followed by a
 * PLAIN sentence — "What is your name?" — no quotes, no italics, nothing
 * `collectCards`'s QUOTED_SUBJECT/ITALIC_SUBJECT can grab. Fingerprinted to
 * nothing (measured live, 2026-09-22, test-en, math-speaking): `lastAsked`
 * stayed empty turn after turn, the server could not tell what a reply was
 * answering, and the tutor — with no memory of having asked it — asked "What
 * is your name?" again, and again, three times over while the same "Nes"
 * kept arriving. Takes the first substantive line verbatim (normalized),
 * same exclusions as everywhere else (a bare imperative names no exercise).
 *
 * A second drift (measured live, 2026-09-22, test-en, math-speaking): the
 * tutor sometimes skips "## Question N: Topic" entirely and reuses the
 * session's own opening heading ("## 🗣️ English Speaking Practice")
 * directly above the question, with the question itself wrapped whole in
 * "**...**" — not a "**Label:** value" metadata line, which is why those are
 * still skipped. "What is your favorite hobby?" fingerprinted to nothing
 * this way and got asked twice in a row.
 */
const BOLD_ONLY_LINE_RE = /^\*\*([^*\n]+)\*\*$/;
function collectPlainQuestion(text: string): string[] {
  const out: string[] = [];
  const re =
    /^#{1,6}\s*(?:Question\s*\d+(?:\s*\/\s*\d+)?\s*:?[^\n]*|[^\n]*Speaking Practice[^\n]*)\n((?:[^\n]*(?:\n|$)){1,6})/gim;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    // Under the session's OPENING heading only a real question counts. The first
    // line there is usually the greeting: "Hello, Test!" was fingerprinted as an
    // exercise, and every new Speaking session of the day was then rewritten for
    // "already asked hello, test" (tutor-bench, 2026-09-29: twice in one run).
    const opening = !/^#{1,6}\s*Question\b/i.test(m[0]);
    for (const line of (m[1] ?? "").split("\n")) {
      let t = line.trim();
      if (/^#{1,6}\s/.test(t) || /type your answer/i.test(t)) break;
      if (!t || t === "---") continue;
      const boldOnly = BOLD_ONLY_LINE_RE.exec(t);
      if (boldOnly && !/:/.test(boldOnly[1]!)) {
        t = boldOnly[1]!.trim();
      } else if (t.startsWith("**")) {
        continue;
      }
      if (opening && !/\?\s*$/.test(t)) continue;
      if (/^(?:hello|hi|hey|welcome|good (?:morning|afternoon|evening))\b/i.test(t)) continue;
      const label = normalizeLabel(t);
      if (label.length < 3 || NOT_AN_EXERCISE.has(label) || BARE_INSTRUCTION.test(label)) continue;
      if (!out.includes(label)) out.push(label);
      break;
    }
  }
  return out;
}

export function exerciseFingerprints(text: string): string[] {
  const body = String(text || "");
  const found = collect(body, EXERCISE_MARKS);
  for (const label of collectBlock(body)) if (!found.includes(label)) found.push(label);
  for (const label of collectReviewCard(body)) if (!found.includes(label)) found.push(label);
  for (const label of collectPlainQuestion(body)) if (!found.includes(label)) found.push(label);
  // A message that closes the lesson asks nothing. Its bolded labels ("**What to
  // work on next:** Keep up the excellent work") are a summary, and a label list
  // that grows a new wording every run cannot be kept up as a deny list.
  const closing = /\b(?:session|lesson)\s+(?:is\s+)?complete\b/i.test(body);
  const out = found.length ? found : closing ? [] : collect(body, EXERCISE_FALLBACK_MARKS);
  return out.slice(0, MAX_FINGERPRINTS_PER_TURN);
}

// ---- what the server tells the tutor ---------------------------------------
//
// Kept here, Bun-free, for the same reason as everything else in this file: it
// is the part that broke, so it has to be runnable in a test without a model,
// a database or a GPU.

/** The review item the server hands the tutor for the next exercise. */
export interface AssignedItem {
  id: string;
  content: string;
  answer?: string;
  type?: string;
  /** For a rule the learner broke: what she actually wrote (`learner_wrote`). */
  wrong?: string;
}

/**
 * The next due item to review, skipping the ones already used today.
 *
 * Handing the tutor the whole due list and asking it to work through them one
 * at a time leaves the server guessing, afterwards, which one an answer was
 * for — and guessing is how a review schedule gets corrupted. So the server
 * takes the top of the queue itself. It decides WHICH item; the tutor still
 * decides what the exercise looks like, at what level, in what form. The queue
 * was always an order: that is what spaced repetition is.
 */
export function nextDueItem(
  sr: unknown,
  today: string,
  usedIds: readonly string[] = []
): AssignedItem | null {
  const items = (sr as { items?: Record<string, Record<string, unknown>> })?.items ?? {};
  for (const id of dueItemIds(sr, today)) {
    if (usedIds.includes(id)) continue;
    const it = items[id] ?? {};
    const content = String(it.content ?? "").trim();
    return {
      id,
      content: content || id.replace(/^[a-z]+_/, "").replace(/_/g, " "),
      ...(it.answer ? { answer: String(it.answer) } : {}),
      ...(it.type ? { type: String(it.type) } : {}),
      ...(it.learner_wrote && String(it.learner_wrote).trim() !== content
        ? { wrong: String(it.learner_wrote).trim() }
        : {}),
    };
  }
  return null;
}

export interface LessonView {
  total: number;
  done: number;
  pending: number;
  due: number;
  slot: string | null;
  /** Real weak patterns available to drill. Zero + nothing due = nothing to
   *  review, and the lesson has to be honest about that. */
  material?: number;
  /** Math level (m1..m6) from the learner profile, for a lesson built from scratch. */
  level?: string;
}

/**
 * The lesson as the tutor has to see it while an answer is in front of it.
 *
 * The plan is credited AFTER the reply, so when answer k arrives it says k-1
 * done, and the note told the tutor "1 exercise still to go, do not close" at
 * the sixth answer of six. The tutor obeyed: no feedback for that answer, a
 * seventh exercise, a lesson that never closed — measured, six runs of six.
 * The answer in front is credited in this very turn, so it counts here.
 *
 * Not for a button, not without an answer, and not for a retry of an exercise
 * that was already credited (it is not credited twice).
 */
export function withAnswerInFront<T extends { done: number; pending: number }>(
  lesson: T,
  st: { inLesson: boolean; isAnswer: boolean; alreadyCredited: boolean }
): T {
  if (!st.inLesson || !st.isAnswer || st.alreadyCredited || lesson.pending <= 0) return lesson;
  return { ...lesson, done: lesson.done + 1, pending: lesson.pending - 1 };
}

/**
 * The block that carries the current practice's own instructions into the
 * SYSTEM prompt.
 *
 * It goes last, so it outranks the generic rules above it, and it goes in the
 * system prompt rather than the history because the history is pruned when the
 * context fills and the grading contract must be the one thing that cannot
 * quietly disappear.
 */
export function skillBlock(skill?: { name: string; body: string } | null): string | null {
  if (!skill || !skill.body.trim()) return null;
  return (
    `Instructions for the practice you are running right now. Follow them EXACTLY:\n\n` +
    `<skill_content name="${skill.name}">\n${skill.body.trim()}\n</skill_content>`
  );
}

/**
 * A skill as the MODEL should see it, which is not the same as the file a
 * person maintains.
 *
 * Three transformations, each one a failure observed live on a 14B:
 *
 *  1. **Drop `## Examples`.** The section is headed, in the file itself,
 *     "(Placeholders. NEVER copy the language of an example into a session)".
 *     A rule that says do-not-copy-this is a rule the prompt should not
 *     contain: the first lesson run with the skill actually loaded produced
 *     "Review 1/6 — 🟡 ... {Target}: {the word}", verbatim from Example 1.
 *  2. **Resolve the language names.** `{Target}` and `{Native}` are the two
 *     placeholders the server can actually fill, and it knows them from the
 *     learner profile. Left unfilled they get printed.
 *  3. **Ban the braces.** Every remaining `{slot}` is an instruction to the
 *     tutor, and a small model prints instructions. One explicit rule at the
 *     end costs twenty tokens and names the exact failure — the morning's
 *     transcript opens with a literal "{✅}".
 */
export function renderSkillForModel(
  body: string,
  langs?: { target?: string | null; native?: string | null }
): string {
  let out = String(body || "");

  // 1. everything from "## Examples" to the next same-level heading.
  out = out.replace(/\n##\s+Examples?\b[\s\S]*?(?=\n##\s+|$)/i, "\n");

  // 2. the two the server can fill.
  const title = (v?: string | null) =>
    (v ?? "").trim().replace(/^\p{Ll}/u, (c) => c.toUpperCase());
  const target = title(langs?.target);
  const native = title(langs?.native);
  if (target) out = out.replace(/\{Target\}/g, target);
  if (native) out = out.replace(/\{Native\}/g, native);
  // The long form some skills use in prose ("{native_language} orthography"):
  // left unfilled, it is a slot the model copies verbatim into its reply.
  if (target) out = out.replace(/\{target_language\}/g, target);
  if (native) out = out.replace(/\{native_language\}/g, native);

  // 3. the rest are slots, and slots get filled, never printed.
  out = out.trimEnd() + `\n\n## One absolute rule about this document\n\n` +
    `Anything written inside curly brackets above is a SLOT for you to fill, never text to ` +
    `print. A curly bracket must never appear in anything you send the learner. If you are ` +
    `about to write one, you are copying this document instead of using it: write the real ` +
    `content instead — the learner's actual word, their actual answer, the actual score.`;
  return out;
}

/** The `math-*` skills a skill's frontmatter declares it needs. */
export function requiredSkills(body: string): string[] {
  const fm = /^---\n([\s\S]*?)\n---/.exec(String(body || ""));
  if (!fm) return [];
  const line = /^requires:\s*(.+)$/m.exec(fm[1] ?? "");
  if (!line) return [];
  return (line[1] ?? "")
    .replace(/[[\]]/g, " ")
    .split(/[,\s]+/)
    .map((x) => x.trim())
    .filter((x) => /^(math|fluent)-[a-z0-9-]+$/.test(x));
}

/**
 * What the server tells the tutor in a practice that is NOT the Lesson.
 *
 * Only one thing, and it is the thing it cannot know: what has already been
 * asked today, in any practice. Vocabulary used to get nothing at all — no
 * list, no referee — and over three measured runs it repeated a word between
 * visits every single time. There is no lesson counter here and no pacing: the
 * Lesson is what has an end, free practice does not.
 */
export function practiceNote(
  covered: readonly string[],
  lastAsked?: string | null,
  answerInFront = false
): string | null {
  // The exercise the learner is answering right now is not "already asked" in
  // the sense of the ban: putting it on the list told the tutor not to touch
  // it, and it answered a "morn" for "matí" with the same card again, twice.
  const inPlay = answerInFront && lastAsked ? lastAsked : null;
  const banned = covered.filter((c) => c !== inPlay);
  const bits: string[] = [];
  if (inPlay) {
    bits.push(
      `The learner's message is their answer to "${inPlay}". Grade it first — verdict, ` +
        `the correct version and the score — and only then give the next exercise.`
    );
  }
  if (banned.length) {
    bits.push(
      `Already answered correctly today, in this session or another practice — do not ask any of these again: ` +
        banned.map((c) => `"${c}"`).join(", ") + `.`
    );
  }
  if (!bits.length) return null;
  if (lastAsked && !inPlay) bits.push(`Your previous exercise was "${lastAsked}".`);
  bits.push(`Say nothing about this note.`);
  return bits.join(" ");
}

// (WP1.9: `writingLengthNote` — the A1..C2 table of email/postcard writing
// tasks — is deleted. It returned null for every m-level, and the length of a
// math REASONING task is the math-writing skill's own m1-m3 / upper-level
// table, which the tutor reads in its system prompt.)

/**
 * Topics the teacher (or the parent) wants practised — `topics.txt` in the
 * profile's data directory, one per line.
 *
 * A line is free text: "present perfect", "there is / there are", "food and
 * restaurants", "asking for directions", "comparatives: taller than, the tallest".
 * Blank lines and lines starting with `#` are ignored, as are list bullets and
 * numbers. Capped, so a pasted syllabus cannot flood the prompt.
 */
export const MAX_TOPICS = 30;
export const MAX_TOPIC_CHARS = 160;

export function parseTopics(text: string | null | undefined): string[] {
  const out: string[] = [];
  for (const raw of String(text ?? "").split(/\r?\n/)) {
    const line = raw
      .trim()
      .replace(/^(?:[-*\u2022]+|\d+[.)])\s+/, "")
      .trim();
    if (!line || line.startsWith("#")) continue;
    const t = line.slice(0, MAX_TOPIC_CHARS);
    if (!out.some((o) => o.toLowerCase() === t.toLowerCase())) out.push(t);
    if (out.length >= MAX_TOPICS) break;
  }
  return out;
}

/** `n` topics, starting where `seed` points and wrapping: every topic gets its turn. */
export function pickTopics(topics: readonly string[], seed: number, n = 2): string[] {
  if (topics.length === 0) return [];
  const take = Math.min(n, topics.length);
  const start = ((Math.floor(seed) % topics.length) + topics.length) % topics.length;
  return Array.from({ length: take }, (_, i) => topics[(start + i) % topics.length]!);
}

/**
 * The note that turns the list into behaviour. What it must NOT do is as
 * important as what it does: the queue always comes first (an item due is an
 * item due, whatever the topic), the topic never replaces the learner's level,
 * and a topic that does not fit the practice is dropped instead of forced.
 */
export function topicsNote(topics: readonly string[], seed: number, level?: string | null): string | null {
  const picked = pickTopics(topics, seed);
  if (picked.length === 0) return null;
  const l = String(level ?? "").trim().toUpperCase();
  return (
    `The learner's teacher wants these topics practised: ${picked.map((t) => `"${t}"`).join(", ")}. ` +
    `Whenever YOU choose what a new exercise is about — free practice, Writing, Speaking, Reading, ` +
    `or a lesson exercise with no review item or weak pattern assigned — build it around one of them, ` +
    `in the usual format of the practice. A topic may be a grammar structure (the exercise uses it), a ` +
    `theme (the words and the situation come from it) or a skill (the exercise trains it): treat it as ` +
    `whichever it is. Keep it ${l ? `at ${l}` : "at the learner's level"}: if a topic is harder than that, use its simplest form. ` +
    `A review item that is due, or a weak pattern the server assigned, ALWAYS comes first and is never ` +
    `replaced by a topic. If a topic does not fit this practice, ignore it rather than force it. ` +
    `Do not announce the topic, do not lecture on it unless she gets it wrong, and say nothing about this note.`
  );
}

/**
 * What the server tells the tutor about the lesson in progress: STATE, not a
 * script.
 *
 * The script version of this note said "This is a CONTINUATION", "Do NOT greet,
 * do NOT show a menu", "Present exercise N of M now, and nothing else" — as a
 * system message at the very end of the prompt, on every single turn. Two
 * things went wrong with that, and both were measured on 2026-09-16:
 *
 *  - It outranked the command. The command's first line said to load the
 *    math-review skill; the last line the model read said to present an
 *    exercise and nothing else. A 14B follows the last, most concrete
 *    instruction, so the skill never loaded and the grading contract never
 *    arrived.
 *  - It froze. The text is a function of `done`; `done` stopped moving; so the
 *    tutor received the same sentence, byte for byte, with the same exercise
 *    index, for twenty-five consecutive turns — and did exactly that, twenty-
 *    five times.
 *
 * So the note now carries only what the server knows and the tutor cannot: how
 * far along the lesson is, and what has already been asked today. How to run an
 * exercise belongs to the skill, and saying it twice in two voices is how the
 * two end up disagreeing.
 */
export function lessonNote(
  lesson: LessonView,
  covered: readonly string[] = [],
  lastAsked?: string | null,
  assigned?: AssignedItem | null
): string {
  const bits = [`Lesson progress: ${lesson.done} of ${lesson.total} done.`];
  if (lesson.done > 0) {
    bits.push(`The lesson is already under way: continue it rather than starting it again.`);
  }
  // `due === 0` on its own: what there is to drill decides where the REST of
  // the lesson comes from, not whether there is a review to do. Gating this on
  // material too meant two junk patterns were enough to send the tutor into
  // "build from the weak patterns" — and it improvised a review instead.
  if (lesson.due === 0) {
    // Nothing is due AND there are no recorded weak patterns: a new profile, or
    // one whose databases are still the provisioning template. Asked to "review"
    // six items that do not exist, the tutor invents them — and on a 14B that
    // means copying the nearest example it can see, placeholders and all. Seen
    // live on test-en: "Review 1/6 — 🟡 ... {Target}: {the word}".
    bits.push(
      `There is NOTHING to review today: the queue is empty and no weak patterns have been recorded yet. ` +
        `Nothing is due, so there is no review to do and nothing to report as "last reviewed" or ` +
        `"mastery" — writing one invents a history she never had. Do NOT label these exercises ` +
        `"Review". ` +
        ((lesson.material ?? 0) > 0
          ? `Build the ${lesson.total} exercises from the weak patterns in mistakes-db`
          : `Teach ${lesson.total} pieces of NEW material at the learner's level`) +
        `${lesson.level ? ` (${lesson.level})` : ""}, and grade each answer exactly as always.`
    );
  }
  // The skill ends a review session when the queue runs out. The lesson ends
  // when its exercises are done. With two items due and a lesson of six, those
  // two contracts disagree — and the tutor followed the skill: "Review Session
  // Complete! Reviewed: 2", with four exercises never asked and the badge left
  // at 2 of 6. The server sets the length, so the server has to say so.
  // Grading and asking are ONE turn. A reply that only corrects leaves the
  // learner with a blank screen and nothing to do — and the tutor that did this
  // graded six different answers against the same unchanged question, while the
  // badge climbed to 6 of 6. Observed live, 2026-09-19.
  bits.push(
    `Every reply does BOTH: grade the answer in front of you AND present the next, DIFFERENT exercise ` +
      `in the same message. Never grade without asking something new, and never ask the same question twice. ` +
      `No second try in the Lesson either: a wrong answer gets the correct version and you go on to the ` +
      `next exercise — that item comes back on its own schedule.`
  );
  bits.push(
    `${lesson.pending} exercise(s) still to go: do NOT show a session summary and do NOT close the ` +
      `session before then, not even if the review queue runs out first.`
  );
  if (lesson.slot) {
    bits.push(
      `Still missing from this lesson: one ${lesson.slot} exercise. Fit it in as a normal part of it, not as a penalty.`
    );
  }
  if (covered.length) {
    bits.push(
      `Already answered correctly today — not again, in any form: ` + covered.map((c) => `"${c}"`).join(", ") + `.`
    );
  }
  if (lastAsked) {
    bits.push(
      `Your previous exercise was "${lastAsked}". The learner's message is their answer to THAT ` +
        `exercise: grade it, and only it.`
    );
  }
  if (assigned) {
    bits.push(
      `The next exercise reviews this item: "${assigned.content}"` +
        (assigned.answer ? ` (answer: "${assigned.answer}")` : "") +
        `. Build the exercise yourself — the wording, the level and the form are yours — ` +
        `but keep it about that item, not another one from the queue. It is the top of today's queue. ` +
        `It has not been asked yet, so nothing has been answered for it.` +
        // A rule she broke is only tested by an exercise she can fail in the same
        // way. "Complete: I speak English on ___" hides the capital letter the item
        // is about, and "mondays" in lowercase then passes (10/10, measured).
        (assigned.wrong && assigned.type !== "vocabulary"
          ? ` Her own mistake was "${assigned.wrong}". Set the exercise so that repeating it ` +
            `would be marked wrong — for instance, ask her to correct a sentence that contains it. ` +
            `Do not hide it behind a fill-in-the-blank that lets her answer without meeting it.`
          : ``)
    );
  }
  bits.push(`The learner sees this progress in the app. Say nothing about this note.`);
  return bits.join(" ");
}

// ---- the turn has to move the lesson forward -------------------------------
//
// Three rules have been asked for in the skill and in the note, and all three
// kept being broken in live lessons: grade AND ask the next question, never
// ask the same question twice, and do not close the lesson before its exercises
// are done. Asking a 14B a fourth time is not a plan.
//
// Same conclusion as the traffic-light marker, which was asked for three times
// and fixed in one line the moment the server stopped asking: if a rule matters,
// the server enforces it. Here it cannot rewrite the reply — only the tutor
// knows the next question — so it does the next best thing and makes it write
// the turn again, once, with the problem named.

/** The shape of a review card: a made-up one has all of this and no item. */
const FABRICATED_REVIEW = /last reviewed|current mastery|review item|spaced repetition review/i;

export interface TurnGuardState {
  /** Is this turn inside the Lesson? */
  inLesson: boolean;
  /** Exercises still to do; 0 means the lesson is over. */
  pending: number;
  /** Fingerprints of everything asked today, in any practice. */
  coveredToday: readonly string[];
  /** Fingerprints asked in THIS practice today. A word may legitimately come
   *  up in two practices — the Lesson spelling "because" and a Vocabulary card
   *  for "because" are different exercises about the same word — so a bare term
   *  only counts as a repeat within the practice that asked it. */
  askedHere?: readonly string[];
  /** Fingerprints in the reply being judged. */
  asked: readonly string[];
  /** Did the reply grade an answer? */
  graded: boolean;
  /** The reply itself, for the checks that look at more than the fingerprints. */
  replyText?: string;
  /** Did the reply close the session? */
  closing: boolean;
  /** Items genuinely due today. Zero means every "Review Item" in the reply is
   *  invented. */
  due?: number;
  /** The learner's message is an answer to this exercise (the previous one).
   *  Set in every practice, not only the Lesson. */
  answering?: string | null;
  /** The item the server assigned for the exercise this reply has to ask (Lesson). */
  assigned?: { content: string; answer?: string } | null;
  /** The item that was on screen — the one the learner's message answers (Lesson). */
  grading?: { content: string; answer?: string } | null;
  /** The curriculum competence the server assigned for the exercise this reply has
   *  to ask (free practice: Mix and Vocabulary). */
  competence?: AssignedCompetence | null;
  /** What the learner wrote, for the sentence that sends the tutor back. */
  answerText?: string | null;
  /** The turn was opened by a button: nothing has been answered yet. */
  buttonTurn?: boolean;
  /** Free practice that goes one card at a time (Vocabulary): every graded
   *  reply must ask the next one. The Lesson has its own rule, with a counter. */
  oneAtATime?: boolean;
}

/** What to tell the tutor to make it write the turn again, or null if the turn
 *  is fine. One retry only — the caller must not loop. */
/** Words of a text, accents and case folded away. */
function wordsOf(text: string): Set<string> {
  const folded = String(text || "").toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
  return new Set(folded.match(/[a-z0-9']+/g) ?? []);
}

/** The competence of the curriculum the server chose for the next free-practice exercise. */
export interface AssignedCompetence {
  id: string;
  name: string;
  can_do?: string;
  /** Words or phrases that show up in an exercise about it ("now", "at the moment"). */
  signals: string[];
  /** Vocabulary competence: it is asked in the learner's language, so the text says nothing. */
  vocab?: boolean;
  kind?: string;
  /** The word list curriculum.py offered for this competence, when it is a
   *  vocabulary one — used by openBlankGuard to check the exercise actually
   *  fixes one of them (a digit shown for a number, etc.) instead of leaving
   *  the blank open to anything. */
  words?: string[];
}

/** Text with accents and case folded away, single-spaced, padded for whole-word search. */
function foldedPadded(text: string): string {
  const f = String(text || "").toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
  return ` ${f.replace(/[^a-z0-9']+/g, " ").trim()} `;
}

// The exercise's own scaffolding ("Question: Complete the sentence...",
// "Type your answer:") is boilerplate the tutor writes on every single
// exercise, whatever it is about — not content. Left in, its words collide
// with unrelated competences' signals: "Question:" satisfies a1.question_words
// ("question"), "Type your answer:" satisfies a1.possessive_adjectives
// ("your"), on every exercise, regardless of what it actually asks. Measured
// 2026-09-22: eight demonstratives exercises in a row ("This"/"These"), each
// stamped with a different, wrong competency (possessive_adjectives,
// question_words, imperatives...) purely from this boilerplate — the real
// a1.demonstratives count never advanced, so the model kept being handed the
// same canned example and kept producing the same answer.
const EXERCISE_BOILERPLATE = /\b(type your answer|context|question|sentence|prompt|instructions?|task)\s*:/gi;

// The server's OWN debug markup ends up inside the very text this function
// judges -- tagCompetency() (this file) prints the assigned competence's raw
// id right on the exercise heading ("<span class=\"comp-tag\">a1.there_is_are
// </span>"). Folded, that id's underscores become spaces: "a1 there is are"
// -- which contains "there is" as a plain substring, one of a1.there_is_are's
// OWN signals. The guard below was checking whether the id satisfies its own
// signal list, which it always trivially does for any id built from its
// signal words (there_is_are, have_got, can_ability...) -- it could never
// catch drift on those competences. Measured live, 2026-09-23 (nes-en,
// ses_e727dae): a present-simple "brush your teeth" exercise sailed straight
// through assigned to a1.there_is_are, because the tag alone made the check
// pass. Strip the WHOLE comp-tag span -- delimiters AND the id text inside,
// not just the bare "<...>" brackets (which would leave the id itself
// sitting in the text) -- before folding, so only what the model actually
// wrote is ever judged. Any other stray HTML is stripped bracket-only after,
// same as before.
const COMP_TAG_SPAN = /<span\s+class="comp-tag"[^>]*>[^<]*<\/span>/gi;
const HTML_TAG = /<[^>]+>/g;

/** `foldedPadded`, with the exercise's own field labels ("Question:", "Type
 *  your answer:") and any HTML the server itself injected (comp-tag and
 *  friends) stripped first so neither can masquerade as content. */
function foldedContent(text: string): string {
  return foldedPadded(
    String(text || "").replace(COMP_TAG_SPAN, " ").replace(HTML_TAG, " ").replace(EXERCISE_BOILERPLATE, " ")
  );
}

/**
 * Is the exercise a reply ends on about the competence the server assigned?
 *
 * Judged by the competence's signals (words or phrases that an exercise about it
 * cannot do without: "now", "at the moment", "goes"). One of them is enough: the
 * tutor builds the exercise, it does not copy a sentence. True when there is
 * nothing to judge (no competence, vocabulary, no signals, no exercise).
 */
export function followsCompetence(
  comp: AssignedCompetence | null | undefined,
  reply: string
): boolean {
  if (!comp || comp.vocab || !comp.signals?.length) return true;
  const exercise = trailingExercise(String(reply || ""));
  if (exercise === null) return true; // no exercise: nothing to judge
  const hay = foldedContent(exercise);
  // An exercise headed with the competence's own name ("## Exercise 5: Prepositions of Time
  // and Place") is about it, whatever the gap hides.
  const name = foldedPadded(comp.name).trim();
  if (name && hay.includes(` ${name} `)) return true;
  return comp.signals.some((sg) => {
    const w = foldedPadded(sg).trim();
    return w !== "" && hay.includes(` ${w} `);
  });
}

/**
 * Is the exercise a reply ends on about the item the server assigned?
 *
 * Half of the item's words in the exercise is enough: the tutor builds the
 * exercise ("She go to school") from the item ("She goes to school"), it does
 * not copy it. True when there is nothing to judge (no item, no exercise).
 * Measured 2026-09-21 (days 073725): asked to review «escola» the tutor asked
 * «matí» — the next one in the queue it can see — and the answer for «escola»
 * was marked wrong; the whole day slid. It also graded «window» as if it were
 * the next item's answer, for the same reason.
 */
export function followsAssigned(
  item: { content: string; answer?: string } | null | undefined,
  reply: string
): boolean {
  if (!item) return true;
  const want = new Set([...wordsOf(item.content), ...wordsOf(item.answer ?? "")]);
  if (!want.size) return true;
  const text = String(reply || "");
  const heads = [...text.matchAll(/^#{1,6} .*$/gm)];
  const last = heads[heads.length - 1];
  if (!last || last.index === undefined) return true; // no exercise heading: nothing to judge
  const tail = wordsOf(text.slice(last.index));
  let hit = 0;
  for (const w of want) if (tail.has(w)) hit++;
  return hit / want.size >= 0.5;
}

const FILLER = new Set([
  "the", "and", "for", "you", "she", "her", "his", "not", "are", "was", "with", "that", "this",
  "have", "has", "from", "your", "its", "our", "but", "can", "did", "does", "into", "than", "then",
]);

function contentWords(text: string): Set<string> {
  return new Set([...wordsOf(text)].filter((w) => w.length >= 3 && !FILLER.has(w)));
}

/**
 * Is the feedback in a reply about the item the learner just answered?
 *
 * Measured 2026-09-21 (days 073725, totes): the answer «table» to «cuina» got
 * "The correct form is 'an apple', not 'a apple'" — feedback for an answer the
 * learner never gave, built from the NEXT item's history that the note carries
 * ("Her own mistake was 'I eat a apple every day'") — and then the next word
 * was asked. The answer was graded 6/10 (SM-2 passes it), the word was counted
 * as known, and the next item's answer was graded against the wrong exercise.
 *
 * At least one content word of the item — or of its answer — has to appear in
 * the feedback (everything before the last heading). Nothing to judge → true.
 */
export function feedbackFollowsGrading(
  item: { content: string; answer?: string } | null | undefined,
  reply: string
): boolean {
  if (!item) return true;
  const want = new Set([...contentWords(item.content), ...contentWords(item.answer ?? "")]);
  if (!want.size) return true;
  const text = String(reply || "");
  if (!/Correct version:|\*\*Score/i.test(text)) return true;
  const heads = [...text.matchAll(/^#{1,6} .*$/gm)];
  const last = heads[heads.length - 1];
  const feedback = last && last.index !== undefined && last.index > 0 ? text.slice(0, last.index) : text;
  if (feedback.trim().length < 20) return true;
  const have = wordsOf(feedback);
  for (const w of want) if (have.has(w)) return true;
  return false;
}

/** This app is text-only: no picture, photo, image or diagram is ever shown to
 *  the learner. Measured 2026-09-22: the small local model kept inventing "Look
 *  at the picture below. Describe what you see." around the curriculum's
 *  "There is/There are" example ("___ a book on the table."), across several
 *  turns and even a fresh session, despite the skill saying not to — a
 *  deterministic catch is needed. */
export function pictureGuard(text: string): string | null {
  const re =
    /\b(?:look at the (?:picture|photo|image|diagram)\b|in the (?:picture|photo|image)\s+(?:below|above)\b|describe what you see)/i;
  if (!re.test(text)) return null;
  return (
    `This turn refers to a picture, photo, image or diagram — but this app is text-only, there is ` +
    `nothing to look at and no such content exists. Write the turn again with no reference to a ` +
    `picture, photo, image or diagram anywhere (Context line included); describe the scene in words, ` +
    `or use a different exercise for this competence.`
  );
}

/**
 * Writing is where she writes her OWN words. Every closed exercise — a gap, a
 * sentence to complete — belongs to 🎲 Go, which drills the same structures
 * and is checked for a single right answer. Albert, 2026-09-23: the practice
 * called Writing had slid into "asking for sentences with gaps and nothing
 * else", which is Go with another name and left the app with no free
 * production at all. The skill says so; this is what makes it true.
 */
// Where the task she is being GIVEN starts: a practice heading or the
// **Task:** label. Shared by the two Raonament guards below — the feedback
// half of a reply quotes her text and the corrected version, and only the
// task half is judged.
const REASONING_TASK_CUT =
  /#{1,3}\s*(?:✍️|📝)?\s*(?:Writing|Raonament|Reasoning|Repte)\s*(?:Exercise|Task)?|\*\*Task:?\*\*/i;

export function writingBlankGuard(text: string, command?: string | null): string | null {
  if (command !== "math-writing") return null;
  const t = String(text || "");
  // The feedback half of a reply quotes her text and the corrected version;
  // only the task she is being given matters here.
  const cut = t.search(REASONING_TASK_CUT);
  const task = cut >= 0 ? t.slice(cut) : t;
  if (!/___+/.test(task) && !/\b(?:fill in the (?:gap|blank)s?|complete the sentences?|completa|emplena els? buits?)\b/i.test(task)) return null;
  return (
    `This is Raonament (📝): she explains her own mathematical thinking. A gap to fill or a sentence to ` +
    `complete is a Go exercise, not a reasoning task. Write the turn again with an open task instead: one ` +
    `small thing to explain, justify or invent ("explica com ho has resolt", "per què 3 + 2 × 4 no és ` +
    `20?", "inventa un problema que es resolgui amb 3/4 + 1/8") — no "___", nothing to complete, nothing to copy.`
  );
}

/**
 * WP3.3 math guards for Raonament (📝). The practice dies two ways, both seen
 * in the language fork's Writing: the task asks for a LIST — items to produce,
 * not reasons to give — or it asks for a result with no reason attached, which
 * is Go under another name. The math-writing skill says never a bare list and
 * always a justification; this is what makes it true. The third WP3.3 rule —
 * an answer that is only the result scores low on procedure/justification —
 * lives in the deep rubric (tools.ts DEEP_RUBRIC), because it is about her
 * answer, not about the task; the rewrite note below makes the tutor say it
 * out loud when it fires.
 *
 * Only the task half is judged (same cut as writingBlankGuard): a reply that
 * only gives feedback, or a summary, presents no task and passes through.
 */
export function reasoningTaskGuard(text: string, command?: string | null): string | null {
  if (command !== "math-writing") return null;
  const t = String(text || "");
  const cut = t.search(REASONING_TASK_CUT);
  if (cut < 0) return null; // no task being presented this turn
  const task = t.slice(cut);

  // (a) never a bare list.
  if (
    /\b(?:fes|feu|fem|crea|make|do|create)\s+(?:una?\s+|la\s+)?(?:llista|llistat|lista|list)\b|llista de|llistat de|\benumera\b|anomena\s+(?:tots|totes|tothom)|\blist of\b|\benumerate\b|\bname all\b/i.test(
      task
    )
  ) {
    return (
      `This is Raonament (📝): she explains her mathematical thinking in her own words. A list to ` +
      `produce is not a justification — "fes una llista de…" asks for items, not reasons. Write the ` +
      `turn again asking for ONE explanation with the reason attached: "explica com ho has resolt i per ` +
      `què funciona", "per què 3 + 2 × 4 no és 20?", "troba l'error i explica'l" — no bare list.`
    );
  }

  // (b) always require justification: the task must ask HOW or WHY, in any of
  //     the shapes the skill offers (explain / why / justify / prove / find
  //     the error / invent a problem / which operation and why).
  if (
    !/\b(?:explica|per què|perquè|com ho (?:has|heu|vas|vau|faries|faràs|faras|fareu)|com funciona|com ho faries|com ho feu|justifica|demostra|motiva|argumenta|raona|troba|inventa|necessites|quina operació|què cal|què necessites|why|explain|justify|prove|how did you|which operation|what operation)\b/i.test(
      task
    )
  ) {
    return (
      `This is Raonament (📝): every task must ask her to explain or justify, not only to produce a ` +
      `result — a task with no "explica / per què / justifica / demostra" is a closed Go exercise under ` +
      `another name. Write the turn again: state the situation, then ask HOW or WHY, and tell her that ` +
      `the answer alone, without the reasoning, will not score.`
    );
  }
  return null;
}

/**
 * WP3.2 math guard for 📖 Problemes (word problems). The practice dies the
 * same way Raonament did: the "problem" degenerates into a bare arithmetic
 * card — "Calcula 24 ÷ 6" — which is Go under another name and grades the
 * calculation only, never the setup the practice exists to teach. And the
 * task must ask for the WORK: the WP3.1 rubric (tools.ts DEEP_RUBRIC,
 * task='word-problem') scores a bare numeric answer in the 0-4 band
 * (procedure/justification), so a prompt that asks only for the result sets
 * the learner up to lose points she never had a chance to earn.
 *
 * Same shape as reasoningTaskGuard: only the task half is judged (a reply
 * that gives feedback and then presents the next problem is cut at the
 * problem heading), and only inside math-reading.
 */
const PROBLEM_TASK_CUT =
  /#{1,3}\s*(?:📖)?\s*(?:Problema\b|Word problem\b)|\*\*Enunciat:?\*\*/i;

export function wordProblemTaskGuard(text: string, command?: string | null): string | null {
  if (command !== "math-reading") return null;
  const t = String(text || "");
  const cut = t.search(PROBLEM_TASK_CUT);
  if (cut < 0) return null; // no problem being presented this turn
  const task = t.slice(cut);

  // (a) the statement must be a story, not an expression.
  const en = /\*\*Enunciat:?\*\*\s*([^\n]+)/i.exec(task);
  if (en?.[1] && /^[\d\s.,+\-−×x*/·÷()=]+$/.test(en[1].trim())) {
    return (
      `This is 📖 Problemes: she reads a situation and decides which operation ` +
      `it calls for. "**Enunciat:** 24 ÷ 6" is a bare calculation — a Go card in a ` +
      `Problemes costume. Write the turn again with a real story (1-4 sentences in ` +
      `her language: shopping and change, sharing equally, "quants en falten per…", ` +
      `double/half), and let the operation be the thing she has to find.`
    );
  }

  // (b) the task must ask for the work, not only the result.
  if (
    !/\b(?:operació|operacions|una per línia|pas a pas|com ho (?:has|heu|vas|vau|faries)|explica|raona|justifica)\b/i.test(
      task
    )
  ) {
    return (
      `This is 📖 Problemes: the task must ask her to SHOW THE WORK — the ` +
      `operation(s), one per line, and the result. A prompt that asks only for the ` +
      `result invites a bare number, and the rubric scores a bare answer 0-4 ` +
      `(procedure/justification) — she would lose points she never had a chance to ` +
      `earn. Write the turn again: state the situation, then ask for the operations ` +
      `("escriu les operacions, una per línia, i el resultat") and say the answer ` +
      `alone, without the operations, will not score.`
    );
  }
  return null;
}

export function turnGuard(st: TurnGuardState): string | null {
  // A button opens the practice; nobody has answered anything. A reply that
  // opens with "❌ Close! matí means morning, not table" is grading an answer the
  // learner never gave — the tutor filled in the one from the day before.
  // Measured 2026-09-20 (days, day 3): the lesson then asked for another item
  // than the one assigned, and the whole day slid one exercise. Applies to any
  // practice; a closing summary is not grading.
  if (st.buttonTurn && st.graded && !st.closing && /Correct version:/i.test(st.replyText ?? "")) {
    return (
      `The learner has not answered anything yet — this turn was opened by a button, so there ` +
      `is nothing to grade and no answer to correct. Write the turn again as the opening only: ` +
      `no feedback, no correction, no score. Present the first exercise.`
    );
  }

  // Repeating a question the learner already answered today is wrong in every
  // practice, not only inside the Lesson. Guarding only the Lesson left
  // Vocabulary with no memory and no referee: over three measured runs it
  // repeated a word between visits every single time. The rules that ARE about
  // the lesson stay behind the flag.
  // A full question repeated anywhere is a repeat. A bare term — "apple",
  // "because" — is only a repeat inside the practice that already asked it:
  // banning it across practices made the guard reject nine legitimate turns in
  // three runs, and every rewrite is a chance to lose the correction.
  // An answer in front and a new exercise with no grading: the learner is left
  // without the one thing they came for. Measured in free practice — "morn" for
  // "matí" got the same card back, twice, with no feedback. Applies everywhere.
  if (st.answering && !st.graded && st.asked.length > 0 && !st.closing) {
    const again = st.asked.includes(st.answering) ? ` Do not repeat "${st.answering}".` : "";
    return (
      `The learner answered "${st.answering}" and your reply does not grade it. Write the turn ` +
      `again: first the feedback on that answer (verdict, the correct version, the score), ` +
      `then the next exercise.${again}`
    );
  }

  // The Lesson hands out the item; a reply that asks about another one is wrong
  // even when it is a fine exercise.
  if (st.assigned && !st.closing && st.asked.length > 0 && !followsAssigned(st.assigned, st.replyText ?? "")) {
    return (
      `The next exercise must review "${st.assigned.content}"` +
      (st.assigned.answer ? ` (answer: "${st.assigned.answer}")` : "") +
      ` — your reply asks about something else. Write the turn again with an exercise about that item.`
    );
  }

  // Free practice with a curriculum: the server picked the competence.
  if (st.competence && !st.closing && st.asked.length > 0 && !followsCompetence(st.competence, st.replyText ?? "")) {
    return (
      `The next exercise must practice "${st.competence.name}"` +
      (st.competence.can_do ? ` (${st.competence.can_do})` : "") +
      ` — your reply asks about something else. Write the turn again with an exercise about that competence.`
    );
  }

  // Feedback about another item than the one she answered.
  if (st.grading && st.answering && st.graded && !feedbackFollowsGrading(st.grading, st.replyText ?? "")) {
    return (
      `Your feedback is about something else. The learner's message ` +
      (st.answerText ? `("${st.answerText}") ` : ``) +
      `answers the exercise on "${st.grading.content}" — grade THAT answer: the verdict, the correct ` +
      `version and the score. Not the next item's; nothing has been answered for it yet. Then present ` +
      `the next exercise.`
    );
  }

  // The closing reply of a lesson has to grade the LAST answer too. Measured
  // 2026-09-21 (days 083631, temp06): "window" was answered and the reply went
  // straight to "Review Session Complete! Accuracy 100%" — no verdict, no score
  // — so the answer was never credited (plan 1 of 2) and the item was recorded
  // only through the summary block.
  if (st.closing && st.inLesson && st.grading && st.answering && !st.graded) {
    return (
      `The learner's message ` + (st.answerText ? `("${st.answerText}") ` : ``) +
      `answers the last exercise, on "${st.grading.content}", and your reply does not grade it. ` +
      `Write the turn again: first the feedback on that answer — the verdict, the correct version ` +
      `and the score — and then close the lesson.`
    );
  }

  // What counts as covered is what she answered CORRECTLY (KNOWN_SCORE), so a bare
  // term is refused everywhere too: the ban used to be per practice because
  // "covered" meant "shown", and a card shown in the Lesson banned a legitimate
  // one in Vocabulary. A word she has got right does not come back as a card.
  const here = st.askedHere ?? st.coveredToday;
  // The exercise just graded THIS turn is not in `coveredToday`/`askedHere`
  // yet — those only update afterwards, in creditTurn, once this reply is
  // already final. Feedback and the next exercise arrive in the SAME
  // message, so without this the guard cannot see that "the next exercise"
  // is the one it just finished grading. Measured 2026-09-22: Question 13
  // repeated Question 12 verbatim, one turn after grading it 10/10.
  const justAnswered = st.answering ? [st.answering] : [];
  const repeated = st.asked.filter(
    (a) => st.coveredToday.includes(a) || here.includes(a) || justAnswered.includes(a)
  );
  if (repeated.length && repeated.length === st.asked.length) {
    return (
      `You have already asked "${repeated[0]}" today. Write the turn again with a DIFFERENT ` +
      `exercise — a different word, sentence or rule. Keep your feedback on the answer in front ` +
      `of you exactly as it was.`
    );
  }

  // Fabricated reviews. With an empty queue the tutor ran fifteen "Spaced
  // Repetition Review" exercises in a row, inventing every word — "perquè",
  // "naranja" (Spanish), "culler" (not a word) — each one stamped "Last
  // reviewed: 0 days ago, Current mastery: ⭐". None of it was reviewing
  // anything. A made-up review history is worse than no review: the learner is
  // told she once knew a word that never existed.
  if ((st.due ?? 1) === 0 && FABRICATED_REVIEW.test(st.asked.join(" ") + " " + (st.replyText ?? ""))) {
    return (
      `There is nothing due for review today, so there is no review item to show and no ` +
      `"last reviewed" or "mastery" to report — writing one invents a history the learner ` +
      `never had. Write the turn again as what it is: a new exercise, presented plainly.`
    );
  }

  // Vocabulary graded the answer and left the learner with nothing to answer: twice
  // in a row in one measured run, "Let's try another one." and no card. The
  // Lesson had this rule, free practice did not. Writing is left out on purpose:
  // one scenario per session, and its feedback ends by pointing at the buttons.
  if (st.oneAtATime && st.answering && st.graded && st.asked.length === 0 && !st.closing) {
    return (
      `Your reply corrects the answer but asks nothing, so the learner is left with a blank ` +
      `screen. Write the turn again: the same feedback, and then the next card in the same message.`
    );
  }

  if (!st.inLesson) return null;

  if (st.closing && st.pending > 0) {
    return (
      `You ended the session with ${st.pending} exercise(s) of today's lesson still to do. ` +
      `The lesson's length is set here, not by the review queue. Write the turn again: finish ` +
      `evaluating the answer in front of you, then present the next exercise. Do not show a summary.`
    );
  }

  if (st.graded && st.pending > 0 && st.asked.length === 0) {
    return (
      `Your reply corrects the answer but asks nothing, so the learner is left with a blank ` +
      `screen. Write the turn again: the same feedback, and then the next exercise in the same ` +
      `message.`
    );
  }

  return null;
}

/**
 * A rewrite that is only the next exercise, put back after the feedback.
 *
 * The rewrite is asked for "the same feedback, and a different exercise", and a
 * 14B answers with the card alone: no correction, no score. The caller used to
 * throw such a rewrite away for having lost the feedback, and with it the new
 * exercise, so the repeat stayed on screen. Measured over six runs: 11 of 50
 * guard actions were that rejection, and every one of the 11 was a bare card
 * ("## Review 5/6 …"). The feedback is not lost — the first reply has it. Keep
 * the first reply up to and including its score line, and take the exercise
 * from the rewrite.
 *
 * Returns null when this does not apply: the first reply has no score line to
 * cut at, or the rewrite carries feedback of its own, or it poses nothing.
 */
export function spliceFeedback(first: string, rewrite: string): string | null {
  const a = String(first || "");
  const b = String(rewrite || "").trim();
  if (!b || /Correct version:/i.test(b) || /\*\*Score/i.test(b)) return null;
  if (!looksLikeExercise(b)) return null;
  const score = /\*\*Score[^\n]*(?:\n|$)/i.exec(a);
  if (!score) return null;
  // The score line often carries a question of its own — "**Score: 2/10** 🔴
  // Let's try again. What is the English word for "finestra"?" — and that one is
  // the very exercise being replaced. Kept, the learner sees two questions.
  const close = /\*\*Score[^*\n]*\*\*/i.exec(score[0]);
  const cut = close ? close.index + close[0].length : 0;
  const line = close
    ? (score[0].slice(0, cut) + score[0].slice(cut).replace(/(?:^|\s)[^.!?\n]*\?\s*$/, "")).trimEnd()
    : score[0].trimEnd();
  const feedback = (a.slice(0, score.index) + line).trimEnd();
  if (!/Correct version:/i.test(feedback)) return null;
  return `${feedback}\n\n${b}`;
}

/**
 * The exercise part of a rewrite, and nothing else.
 *
 * When a guard is about the EXERCISE (asked nothing, or asked one already
 * answered), the first reply's feedback is right and only the exercise has to be
 * replaced. Asked to "write the turn again", the model writes a whole new turn —
 * and it grades again, but the next exercise's answer, which the learner has not
 * given. Measured 2026-09-20, 8 replies in 4 runs: «morning» for *matí* was
 * praised as "Window is the correct word for finestra", a correct "table" was
 * corrected as "bread". The originals were right; the rewrites were the bug.
 *
 * A rewrite that is only an exercise is returned whole; one that also carries
 * feedback is cut at its last heading. Null when there is no exercise in it.
 */
/** Fingerprints are strict about labels; a "Review 2/6" or "Word 6/10" heading is an exercise anyway. */
function looksLikeExercise(text: string): boolean {
  return (
    exerciseFingerprints(text).length > 0 ||
    /^#{1,6}\s*(?:Review|Exercise|Question|Word|Card)\b/im.test(text)
  );
}

export function exerciseOnlyOf(rewrite: string): string | null {
  const b = String(rewrite || "").trim();
  if (!b) return null;
  if (!/Correct version:|\*\*Score/i.test(b)) return looksLikeExercise(b) ? b : null;
  const heads = [...b.matchAll(/^#{1,6}\s.*$/gm)];
  const last = heads[heads.length - 1];
  if (!last || last.index === undefined) return null;
  const tail = b.slice(last.index).trim();
  // The server's fingerprints are strict about labels; a heading that says
  // "Review 2/6" or "Word 6/10" is an exercise on its own.
  return looksLikeExercise(tail) ? tail : null;
}

/**
 * The exercise a reply ends with: from the last heading whose tail is an exercise.
 * Null when the reply asks nothing.
 */
export function trailingExercise(text: string): string | null {
  const b = String(text || "");
  const heads = [...b.matchAll(/^#{1,6}\s.*$/gm)];
  for (let i = heads.length - 1; i >= 0; i--) {
    const at = heads[i]!.index;
    if (at === undefined) continue;
    const tail = b.slice(at).trim();
    if (looksLikeExercise(tail)) return tail;
  }
  return null;
}

/**
 * Guard "answered but not graded": the reply asks the next exercise and has
 * a verdict at best ("✅ Perfect! X is correct."), with no correct version and
 * no score. Measured 2026-09-21 (days 185739, 2 of 12 runs): asked to "write the
 * turn again", the model wrote the feedback for the NEXT card — the one it had
 * just put on screen — and the whole day slid one exercise (plan 4 of 6, or 2 of 6
 * with penalties). The exercise is right; only the feedback is missing.
 * The closing variant of the note is not this one: there is no exercise to keep.
 */
export function isFeedbackGuard(note: string): boolean {
  const n = String(note || "");
  return /and your reply does not grade it\. Write the turn again: first the feedback/i.test(n) &&
    !/then close the lesson/i.test(n);
}

/**
 * The first reply's exercise, with the rewrite's feedback in front of it.
 *
 * The rewrite was asked for the feedback ONLY. Whatever exercise it added is cut
 * off (a rewrite that also asks something is grading nothing but its own
 * question). Null — keep the first reply — when the first reply has no exercise,
 * when the rewrite has no "Correct version" and score, or when its feedback is
 * about another item than the one answered.
 */
export function mergeFeedbackOnly(
  first: string,
  rewrite: string,
  grading: { content: string; answer?: string } | null
): string | null {
  const exercise = trailingExercise(first);
  if (!exercise) return null;
  const r = String(rewrite || "").trim();
  const tail = trailingExercise(r);
  const feedback = (tail ? r.slice(0, r.lastIndexOf(tail)) : r).trim();
  if (!/Correct version:/i.test(feedback) || !/\*\*Score/i.test(feedback)) return null;
  if (grading && !feedbackFollowsGrading(grading, feedback)) return null;
  return `${feedback}\n\n${exercise}`;
}

/** Guards whose only complaint is the exercise, not the feedback. */
export function isExerciseGuard(note: string): boolean {
  return /corrects the answer but asks nothing|You have already asked|must (?:review|practice) "/i.test(String(note || ""));
}

// ---- the marker has to agree with the score --------------------------------
//
// "Score: 0/10 🟢". Green, for nothing right. Asked for in the feedback skill,
// then again in the review skill, then again in the note — and still there in
// every graded reply of three consecutive live lessons. A child reads the emoji
// before the number, and the emoji told her she had done well.
//
// This is not something to keep asking for. The score is written down, right
// there in the same sentence, so the server can simply make them agree.

/** 🔴/❌ for 0-4, 🟡 for 5-7, 🟢/✅ for 8-10. */
export function markerForScore(score: number): "🔴" | "🟡" | "🟢" {
  if (score <= 4) return "🔴";
  if (score <= 7) return "🟡";
  return "🟢";
}

const LESSON_HEADER = /^(#{1,6}\s*(?:Review|Exercise|Question)\s*)(\d{1,3})\s*\/\s*(\d{1,3})/gim;

/**
 * Make the tutor's own "Review 4/6" header say the truth.
 *
 * Seen live: "## Review 7/6 — high", exercise seven of six, in a lesson the
 * server knows is on its fourth. The tutor counts its own turns and loses track
 * across a detour; the server has the number written down. Asking for it would
 * be a fourth rule the model half-follows, so it is simply corrected.
 */
/** "## Exercise {N}: Grammar (Medium)" / "## Question {N}: Topic" — the model's
 *  own running number, nowhere computed by the server. Measured 2026-09-22:
 *  under context pressure this is one of the first things a small model
 *  drops — four turns running with a bare "Exercici" and no number. The
 *  server already knows how many of these headings this practice has shown
 *  (see exerciseSeq in agent.ts); use that instead of trusting the count the
 *  model kept in its own head. Same idea as alignLessonHeader below, for the
 *  practices that are not the numbered Review lesson. */
const EXERCISE_HEADER = /^(#{1,6}\s*(?:Exercise|Question)\b)\s*\d*(\s*:)/gim;

export function hasExerciseHeader(text: string): boolean {
  EXERCISE_HEADER.lastIndex = 0;
  return EXERCISE_HEADER.test(String(text || ""));
}

export function alignExerciseNumber(text: string, n: number): string {
  if (!(n > 0)) return String(text || "");
  EXERCISE_HEADER.lastIndex = 0;
  return String(text || "").replace(EXERCISE_HEADER, (_m, head, colon) => `${head} ${n}${colon}`);
}

/** The curriculum note explicitly tells the model "never say the name of the
 *  competence to her" (hooks/curriculum.py), but nothing enforced that — the
 *  model leaked the raw id straight into the exercise text (seen 2026-09-22:
 *  "a1.greetings_introductions" printed inline, then doubled by tagCompetency
 *  on top of it). Strip any bare competence id before it ever reaches the
 *  learner or gets tagged again. Matches the curriculum's own id shape:
 *  CEFR level + dot + snake_case name (e.g. a1.verb_to_be). */
const COMPETENCY_ID_LEAK = /\b[abc][12]\.[a-z][a-z0-9_]{2,}\b\.?/gi;
export function stripCompetencyLeak(text: string): string {
  return String(text || "").replace(COMPETENCY_ID_LEAK, "").replace(/[ \t]{2,}/g, " ").replace(/[ \t]+\n/g, "\n");
}

/** Debug aid: tags the exercise heading with the competence id it was built
 *  for, in a barely-visible span — so the rotation can be watched live in the
 *  web UI while testing, instead of only after the fact in the records. Never
 *  for the learner to notice; a no-op without both a heading and a competence
 *  (see .comp-tag in web/style.css for how muted it renders).
 *
 *  `credited` says what happened to the answer THIS reply is grading (the
 *  previous exercise, not the new one the tag sits next to) — whether it is
 *  about to land in the record with a competency, per the exact same check
 *  recordCompetence() makes. It is a flash, not a label: "yes"/"no" render in
 *  color for a moment (see [data-credit] in web/style.css) and fade back to
 *  the same muted grey the id itself uses, so a missed credit is visible the
 *  instant it happens instead of only afterwards in .records. Added
 *  2026-09-23 (Albert) after the mid-turn gradingCompetence clobber bug was
 *  hard to catch any other way. */
export function tagCompetency(
  text: string,
  compId: string | null | undefined,
  credited?: "yes" | "no" | "na"
): string {
  const t = String(text || "");
  if (!compId) return t;
  EXERCISE_HEADER.lastIndex = 0;
  const m = EXERCISE_HEADER.exec(t);
  if (!m || m.index === undefined) return t;
  const lineEnd = t.indexOf("\n", m.index);
  const at = lineEnd === -1 ? t.length : lineEnd;
  const attr = credited && credited !== "na" ? ` data-credit="${credited}"` : "";
  return `${t.slice(0, at)} <span class="comp-tag"${attr}>${compId}</span>${t.slice(at)}`;
}

export function alignLessonHeader(text: string, done: number, total: number): string {
  if (!(total > 0)) return String(text || "");
  LESSON_HEADER.lastIndex = 0;
  // The tutor's own number is never trusted for the result, only matched so the
  // replace fires: it runs ahead after a retry loop and, worse, resets to 1 on
  // a fresh session right after a bounce (server/src/agent.ts bounceReason) —
  // the tutor has no memory of the 11 it already did today. `done` is the
  // server's persisted daily plan, always right; the header always shows
  // done+1, capped to the real total. Seen live 2026-09-24: "Review 1/14"
  // after a bounce with done=11 already on file.
  return String(text || "").replace(LESSON_HEADER, (_m, head) => {
    const shown = Math.min(Math.max(1, done + 1), total);
    return `${head}${shown}/${total}`;
  });
}

const ANY_MARKER = /[🟢🟡🔴]/gu;
const SCORE_FOR_MARKER = /\*{0,2}Score:?\*{0,2}\s*(\d{1,2})\s*\/\s*10/i;

/**
 * Repaint the traffic-light markers in a tutor reply so they match the score it
 * gave. Only 🟢🟡🔴 are touched: ✅ and ❌ read as "right"/"wrong" about the
 * answer rather than as a severity, and the tutor uses them inside correction
 * bullets where they are already correct.
 */
export function alignMarkersToScore(text: string): string {
  const body = String(text || "");
  const m = SCORE_FOR_MARKER.exec(body);
  if (!m) return body;
  const score = Number(m[1]);
  if (!Number.isFinite(score) || score < 0 || score > 10) return body;
  const want = markerForScore(score);
  ANY_MARKER.lastIndex = 0;
  const painted = body.replace(ANY_MARKER, want);

  // ✅ and ❌ inside a correction bullet are about one word and stay as they
  // are — but on the VERDICT line they say the same thing the score says, and
  // "❌ Not quite" above "Score: 10/10" is the contradiction a child reads
  // first. Only the two unambiguous ends are repainted; a middling score leaves
  // them alone.
  if (score >= 8 || score <= 4) {
    const wanted = score >= 8 ? "✅" : "❌";
    const lines = painted.split("\n");
    const first = lines.findIndex((l) => l.trim());
    for (let i = 0; i < lines.length; i++) {
      const isVerdict = i === first || SCORE_FOR_MARKER.test(lines[i]!);
      if (!isVerdict) continue;
      lines[i] = lines[i]!.replace(/[✅❌]/gu, wanted);
    }
    return lines.join("\n");
  }
  return painted;
}

// ---- which build is actually running ---------------------------------------
//
// Twice now a test has been judged against a server that was not running the
// code being tested: once a stale copy of the whole repo, once a restart that
// did not happen. Skills and prompts are read from disk on every turn, so those
// changes appear immediately; the TypeScript does not, and the difference is
// invisible from the outside. Guessing which half of a mixed result is real
// costs more than this stamp does.

export function buildStamp(root: string, readFile: (p: string) => string,
                           listDir: (p: string) => string[]): string {
  const bits: string[] = [];
  const walk = (dir: string, exts: string[]) => {
    let names: string[] = [];
    try { names = listDir(dir).sort(); } catch { return; }
    for (const name of names) {
      if (!exts.some((e) => name.endsWith(e))) continue;
      try { bits.push(`${name}:${readFile(`${dir}/${name}`).length}`); } catch { /* skip */ }
    }
  };
  walk(`${root}/server/src`, [".ts"]);
  let hash = 5381;
  for (const ch of bits.join("|")) hash = ((hash << 5) + hash + ch.charCodeAt(0)) | 0;
  return (hash >>> 0).toString(36);
}

// ---- reading the tutor's own feedback --------------------------------------
//
// `math_record_answer` is the structured record of a graded answer, and it is
// what spaced repetition, the error patterns and every count downstream are
// built on. It is also a tool call, which a 14B forgets: measured over three
// live lessons, six answers graded in perfectly good prose and not one call.
// The learner sees a correct, helpful tutor and the databases learn nothing.
//
// The tutor's own text already contains everything the call would have carried
// — it has to, because the learner reads it. So the server reads it too. This
// is the same rule as everywhere else here: what the model has to remember, the
// server remembers instead.

export interface ParsedCorrection {
  wrong: string;
  right: string;
  category: string;
  severity: string;
}

export interface ParsedFeedback {
  score: number;
  corrections: ParsedCorrection[];
  correctVersion?: string;
  skill?: string;
}

const SCORE_LINE_RE = /\*{0,2}Score:?\*{0,2}\s*(\d{1,2})\s*\/\s*10/i;
/** Any "N/10" at all — the same thing countGradedInText accepts. Three places
 *  were deciding what "graded" means and only two agreed: the counter moved on
 *  a bare 7/10, the record refused to be written without the literal word
 *  "Score", and the learner's answer vanished from the databases. Five records
 *  for eight graded answers, measured. */
const BARE_SCORE_RE = /\b(\d{1,2})\s*\/\s*10\b/;
// WP3.3: the quoted parts go up to 400 chars, not 120. In Raonament a
// correction quotes a WHOLE explanation or claim — the skill says so — and a
// 120-char cap silently dropped those lines from the derived record (seen
// live: a 158-char wrong part, corrections: [] in .records, while the Python
// prose fallback, which has no cap, found it). The two parsers must agree.
const CORRECTION_RE =
  /^[-*]\s*[🔴🟡🟢❌✅]?\s*["“']([^"”\n]{1,400})["”']\s*(?:→|->|=>)\s*\*{0,2}["“']?([^"”\n*]{1,400})["”']?\*{0,2}\s*(?:\(([^)\n]{0,80})\))?/u;
const CORRECT_VERSION_RE = /\*\*Correct version:?\*\*\s*\n+\s*["“']?([^\n"”']{1,400})/i;
// WP3.1: the math practices first (the five skill keys C7, plus the surface
// spellings a math heading actually carries — "Repte de Raonament",
// "Problema 3"). The language-era words stay at the end so an old heading is
// still recognized and mapped to its math counterpart by normalizeSkillKey,
// never stored as a phantom skill.
const SKILL_IN_HEADING_RE =
  /^#{1,6}[^\n]*?\b(computation|steps|problems|reasoning|facts|raonament|problema|problemes|passos|fets|càlcul|calcul|vocabulary|grammar|spelling|writing|reading|speaking|listening|capitalization|agreement|tenses|punctuation)\b/im;

/** Everything `math_record_answer` would have carried, read out of the reply
 *  the learner just got. Returns null when the turn did not grade anything. */
export function parseFeedback(text: string): ParsedFeedback | null {
  const body = String(text || "");
  const score = SCORE_LINE_RE.exec(body) ?? BARE_SCORE_RE.exec(body);
  if (!score) return null;
  const n = Number(score[1]);
  if (!Number.isFinite(n) || n < 0 || n > 10) return null;

  const corrections: ParsedCorrection[] = [];
  for (const line of body.split("\n")) {
    const m = CORRECTION_RE.exec(line.trim());
    if (!m) continue;
    const wrong = (m[1] ?? "").trim();
    const right = (m[2] ?? "").trim();
    if (!wrong || !right || wrong === right) continue;
    // "(carrying — the carried 1 was dropped)": the category is the
    // part before the dash, the rest is the explanation.
    const note = (m[3] ?? "").trim();
    // Fallback mirrors DEFAULT_ERROR_CATEGORY in hooks/db_schema.py.
    const category = (note.split(/[—–-]/)[0] ?? "").trim().toLowerCase() || "calculation";
    corrections.push({
      wrong, right,
      category: category.replace(/\s+/g, "_").slice(0, 32),
      severity: n <= 4 ? "critical" : n <= 7 ? "moderate" : "minor",
    });
    if (corrections.length >= 6) break;
  }

  const cv = CORRECT_VERSION_RE.exec(body);
  const heading = SKILL_IN_HEADING_RE.exec(body);
  return {
    score: n,
    corrections,
    ...(cv ? { correctVersion: cv[1]!.trim() } : {}),
    // Math skill keys (C7): a math heading ("Repte de Raonament") and a
    // language-era one both normalize to one of the five.
    ...(heading ? { skill: normalizeSkillKey(heading[1]) } : {}),
  };
}

// ---- history pruning -------------------------------------------------------
//
// Hit in production: `request (41808 tokens) exceeds the available context size
// (40960 tokens)`. The turn simply fails — the learner gets an error instead of
// an exercise. Every turn carries the whole session, so a long practice grows
// until it walks off the edge.
//
// This was deliberately left undone because rules.md told the tutor to scan the
// whole history so it would not repeat an exercise. That reason is gone: the
// server now records what has been asked (plan.covered) and hands the list
// back, so the history no longer has to be complete to be correct.
//
// What is kept: the system prompt (never touched — it carries the rules and the
// language identity), the very FIRST history message (the preloaded state —
// due queue, mastery, mistakes — is injected there once and never resent;
// dropping it silently left the tutor improvising instead of following the
// real queue, measured live 2026-09-22, test-en), and as many of the MOST
// RECENT messages as fit in between. The oldest of what is left go first,
// which is also the pedagogically cheapest loss.

/** Rough token count. No tokenizer here, and a cheap over-estimate is exactly
 *  what a safety margin should be. ~3.2 chars/token errs on the safe side for
 *  English and Catalan prose. */
export function estimateTokens(text: string): number {
  return Math.ceil(String(text || "").length / 3.2);
}

export interface PrunableMessage {
  content?: string | null;
}

export interface PruneResult<T> {
  messages: T[];
  dropped: number;
  estimatedTokens: number;
}

/**
 * Trim history to a token budget, keeping the newest.
 *
 * `reserve` is what must still fit alongside: the system prompt, the pacing
 * note, and the room the model needs to actually answer.
 */
export function pruneHistory<T extends PrunableMessage>(
  history: T[],
  budgetTokens: number
): PruneResult<T> {
  if (budgetTokens <= 0) return { messages: history, dropped: 0, estimatedTokens: 0 };
  const sizes = history.map((m) => estimateTokens(String(m.content ?? "")) + 8);
  let total = sizes.reduce((a, b) => a + b, 0);
  if (total <= budgetTokens) return { messages: history, dropped: 0, estimatedTokens: total };
  // Nothing sits between a lone first message and itself, or between a first
  // and a last with nothing in between — keep both as they are rather than
  // break the "first and last are always kept" promise.
  if (history.length <= 2) return { messages: history, dropped: 0, estimatedTokens: total };

  // Always keep index 0 (the preloaded state) and the last message (the
  // learner's answer — a turn without it is incoherent whatever the budget
  // says). Drop from what is between them, oldest first.
  let cut = 1;
  while (cut < history.length - 1 && total > budgetTokens) {
    total -= sizes[cut]!;
    cut += 1;
  }
  const messages = [history[0]!, ...history.slice(cut)];
  return { messages, dropped: cut - 1, estimatedTokens: total };
}

/** The budget for history, given the model's context and what else must fit. */
export function historyBudget(contextTokens: number, systemTokens: number, maxOutputTokens: number): number {
  // 10% headroom: the estimate is rough and llama.cpp counts the template too.
  const headroom = Math.ceil(contextTokens * 0.1);
  return Math.max(1000, contextTokens - systemTokens - maxOutputTokens - headroom);
}

// ---- spaced-repetition gate ------------------------------------------------
//
export const REVIEW_DAILY_LIMIT_DEFAULT = 20;


/** Ids of queue items due on or before `today` (YYYY-MM-DD), most overdue first. */
/**
 * A value that is still the shape of the template it came from.
 *
 * A freshly provisioned profile ships with example rows — `"item_id":
 * "{unique_identifier}"`, `"due_date": "{YYYY-MM-DD}"`, an error pattern called
 * `example_pattern_1` with frequency 0. Counted as real, they turn an empty
 * profile into "6 items to review" and the tutor, asked to review six things
 * that do not exist, copies the nearest example it can see. Observed exactly
 * that way on test-en.
 */
export function isTemplateValue(v: unknown): boolean {
  if (typeof v !== "string") return false;
  const t = v.trim();
  return (t.startsWith("{") && t.endsWith("}")) || t.startsWith("example_") || t === "...";
}

export function dueItemIds(sr: unknown, today: string): string[] {
  const items = (sr as { items?: Record<string, { due_date?: unknown; item_id?: unknown }> })?.items;
  if (!items || typeof items !== "object") return [];
  return Object.entries(items)
    .filter(([id, it]) => !isTemplateValue(id) && !isTemplateValue(it?.item_id))
    .filter(([, it]) => typeof it?.due_date === "string" && (it.due_date as string) <= today)
    .sort((a, b) => String(a[1].due_date).localeCompare(String(b[1].due_date)))
    .map(([id]) => id);
}

/**
 * How many real weak patterns there are to drill.
 *
 * When this is zero AND nothing is due, there is nothing to review — and
 * saying so is the whole point. A lesson built on no material is worse than no
 * lesson: it is six invented "reviews" of things the learner has never seen.
 */
/** Mastery at or above this means the learner has fixed it. Mirrors
 *  HEALED_MASTERY in hooks/read-db.py — the two must agree, or the Lesson
 *  counts material the tutor is no longer offered. */
export const HEALED_MASTERY = 4;

export function drillMaterial(mistakes: unknown): number {
  const pats = (mistakes as {
    error_patterns?: Record<string, { frequency?: unknown; mastery_level?: unknown }>;
  })?.error_patterns;
  if (!pats || typeof pats !== "object") return 0;
  return Object.entries(pats).filter(
    ([id, p]) =>
      !isTemplateValue(id) &&
      Number(p?.frequency ?? 0) > 0 &&
      Number(p?.mastery_level ?? 0) < HEALED_MASTERY
  ).length;
}

export function reviewDailyLimit(sr: unknown): number {
  const raw = (sr as { daily_limits?: Record<string, unknown> })?.daily_limits?.review_items_per_day;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : REVIEW_DAILY_LIMIT_DEFAULT;
}

/** `preferences.review_gate: false` switches the rule off for a learner. */

// ---- 2026-09-27: what the tutor-bench found (docs/MODELBENCH.md) -----------

/** `{❌}`, `{✅}`, `{8/10}`: a template slot the model filled but did not
 *  unwrap. Only braces around something with no letters — `{Target}` and the
 *  like are a different leak, handled where the prompt is built. */
export function stripTemplateBraces(text: string): string {
  return String(text ?? "")
    .replace(/\{([^\p{L}{}\n]{1,12})\}/gu, "$1")
    // The Reading skill's own heading instruction, copied as is (14B,
    // 2026-09-29): `## {"Question 1: Main idea" — in English}` → the quoted part.
    .replace(/\{\s*"([^"\n{}]{1,80})"\s*[—–-][^{}\n]{0,60}\}/gu, "$1");
}

/** The feedback a learner must see, rebuilt from the tutor's own
 *  math_record_answer call — for a reply that graded in the tool and then
 *  showed nothing of it (27B, 2026-09-27: "Waiting for your answer! ⏱️"). */
export function feedbackFromRecord(args: Record<string, unknown> | null | undefined): string | null {
  const score = Number((args ?? {})["score"]);
  if (!Number.isFinite(score) || score < 0 || score > 10) return null;
  const corrections = Array.isArray((args ?? {})["corrections"])
    ? ((args ?? {})["corrections"] as Array<Record<string, unknown>>)
    : [];
  const lines = corrections
    .map((c) => [String(c["wrong"] ?? "").trim(), String(c["right"] ?? "").trim()])
    .filter(([w, r]) => w && r && w !== r)
    .map(([w, r]) => `- ❌ "${w}" → **"${r}"**`);
  const head = lines.length ? `**Corrections:**\n${lines.join("\n")}` : "✅ Correct!";
  return alignMarkersToScore(`${head}\n\n**Score: ${Math.round(score)}/10** 🟢`);
}
