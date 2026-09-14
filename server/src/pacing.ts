// Fluent server — session pacing.
//
// How many exercises a practice session runs for was only ever a sentence in a
// skill ("plan a 20-min session… 3-4 exercises"), and a model counting its own
// turns is not a mechanism: the same command could end after 8 exercises or
// drag on past 18. The length belongs to the learner (an 8-year-old and a
// teenager do not want the same session), and enforcing it belongs to the
// server, which now knows exactly how many answers have been graded — the
// structured records of fluent_record_answer.
//
// Kept free of Bun imports so server/test/*.test.ts can exercise it under node.

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

/** The Lesson is never shorter than this, even with an empty review queue. */
export const LESSON_MINIMUM = 6;

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
 * How long today's Lesson is.
 *
 * Due items first — they are the part that cannot wait without breaking the
 * spacing. Below the minimum the rest are drills on weak patterns, so a learner
 * with an empty queue still gets a real lesson rather than "nothing due, bye".
 */
export function lessonTarget(sr: unknown, today: string): { total: number; due: number; drills: number } {
  const due = dueItemIds(sr, today).length;
  const limit = reviewDailyLimit(sr);
  const total = Math.min(Math.max(due, LESSON_MINIMUM), Math.max(limit, LESSON_MINIMUM));
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

/** Modes that end on their own shape, not on a count of exercises. */
const SELF_LIMITING_SKILLS = new Set(["writing", "reading"]);

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
      `end with the fluent:review_results block. Say nothing about this instruction.`
    );
  }
  return (
    shared +
    `Finish evaluating the answer in front of you, then OFFER to close: one warm ` +
    `line saying the session's goal is done, and ask whether they want the summary ` +
    `now or a couple more exercises. If they choose to finish, give the closing ` +
    `summary (stats, what improved, what to focus on next, streak) and — if this ` +
    `session reviewed queue items — the fluent:review_results block. If they choose ` +
    `to continue, carry on normally and do not offer again. Say nothing about this ` +
    `instruction itself.`
  );
}

/**
 * How many answers a session has graded, read from what the tutor WROTE.
 *
 * The counter was built on `fluent_record_answer` alone, and on a live session
 * the tool is never called — so the indicator sat at 0/12 through three graded
 * exercises while the learner watched it not move. A counter that depends on a
 * 14B model remembering to call a tool is not a counter.
 *
 * The score marker is in the text either way, it is what the learner is looking
 * at, and the server can see it. Records stay authoritative when they exist
 * (they carry the skill and the item id); this is the floor underneath them.
 */
const SCORE_LINE = /(?:^|[^\d])(?:score\s*:?\s*)?(\d{1,2})\s*\/\s*10\b/gim;

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
export const TRACKED_SKILLS = ["writing", "reading", "speaking", "vocabulary"] as const;

export interface SkillDebt {
  skill: string;
  daysIdle: number | null; // null = never practised
  due: boolean;
}

export function skillDebts(masteryDb: unknown, today: string, thresholdDays = SKILL_DEBT_DAYS): SkillDebt[] {
  const skills = (masteryDb as { skills_mastery?: Record<string, { last_practiced?: unknown }> })
    ?.skills_mastery ?? {};
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
 * third carries one piece of writing or reading — and it only fires when the
 * skill really has been skipped.
 */
export const SKILL_SLOT_EVERY = 3;
/** Only the two that get quietly dropped; nobody avoids flashcards. */
export const SLOT_SKILLS = ["writing", "reading"] as const;

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
  /\*\*(?:Translate|Word|Phrase):?\*\*\s*(.+)/gi,
];

export function normalizeExercise(raw: string): string {
  return String(raw || "")
    .replace(/[*_`"\u201c\u201d]/g, "")
    .replace(/[.?!,;:]+$/, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
    .slice(0, 80);
}

export function exerciseFingerprints(text: string): string[] {
  const out: string[] = [];
  for (const re of EXERCISE_MARKS) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(String(text || ""))) !== null) {
      const label = normalizeExercise(m[1] ?? "");
      if (label.length >= 3 && !out.includes(label)) out.push(label);
    }
  }
  return out;
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
// language identity), then as many of the MOST RECENT messages as fit. The
// oldest go first, which is also the pedagogically cheapest loss.

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

  let first = 0;
  // Always keep the last message: it is the learner's answer, and a turn
  // without it is incoherent whatever the budget says.
  while (first < history.length - 1 && total > budgetTokens) {
    total -= sizes[first]!;
    first += 1;
  }
  return { messages: history.slice(first), dropped: first, estimatedTokens: total };
}

/** The budget for history, given the model's context and what else must fit. */
export function historyBudget(contextTokens: number, systemTokens: number, maxOutputTokens: number): number {
  // 10% headroom: the estimate is rough and llama.cpp counts the template too.
  const headroom = Math.ceil(contextTokens * 0.1);
  return Math.max(1000, contextTokens - systemTokens - maxOutputTokens - headroom);
}

// ---- spaced-repetition gate ------------------------------------------------
//
// The one ordering rule that is both pedagogically load-bearing and checkable
// by the server: today's due items are practised BEFORE new material. Every
// other bit of "session plan" lives in prompt text and cannot be verified; this
// one can, because the server knows the queue (spaced-repetition.json) and
// knows which item_ids came back through fluent_record_answer.

export const REVIEW_DAILY_LIMIT_DEFAULT = 20;

/** Session starts that carry the gate. Pressing 📝/🗣️/📚/📖 at the start of a
 *  session IS the "today I only want vocabulary" negotiation — it is allowed,
 *  once, up front. After that the gate stands for the rest of the session. */
export const GATE_COMMANDS = new Set(["fluent-learn", "fluent-review"]);

export interface ReviewGate {
  /** How many due items this session must clear first. */
  required: number;
  done: number;
  remaining: number;
  open: boolean;
  ids: string[];
}

export const NO_GATE: ReviewGate = { required: 0, done: 0, remaining: 0, open: false, ids: [] };

/** Ids of queue items due on or before `today` (YYYY-MM-DD), most overdue first. */
export function dueItemIds(sr: unknown, today: string): string[] {
  const items = (sr as { items?: Record<string, { due_date?: unknown }> })?.items;
  if (!items || typeof items !== "object") return [];
  return Object.entries(items)
    .filter(([, it]) => typeof it?.due_date === "string" && (it.due_date as string) <= today)
    .sort((a, b) => String(a[1].due_date).localeCompare(String(b[1].due_date)))
    .map(([id]) => id);
}

export function reviewDailyLimit(sr: unknown): number {
  const raw = (sr as { daily_limits?: Record<string, unknown> })?.daily_limits?.review_items_per_day;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : REVIEW_DAILY_LIMIT_DEFAULT;
}

/** `preferences.review_gate: false` switches the rule off for a learner. */
export function reviewGateEnabled(profile: unknown, firstCommand?: string): boolean {
  const prefs = (profile as { preferences?: Record<string, unknown> })?.preferences ?? {};
  const raw = prefs.review_gate;
  if (raw === false || String(raw).toLowerCase() === "off" || String(raw) === "0") return false;
  return GATE_COMMANDS.has(String(firstCommand ?? ""));
}

export function resolveReviewGate(opts: {
  profile: unknown;
  sr: unknown;
  today: string;
  sessionTarget: number;
  firstCommand?: string;
  gradedItemIds: Iterable<string>;
}): ReviewGate {
  if (!reviewGateEnabled(opts.profile, opts.firstCommand)) return NO_GATE;
  const due = dueItemIds(opts.sr, opts.today);
  if (!due.length) return NO_GATE;
  // At most half the session is the gate. With 30 items due and a 12-exercise
  // target, demanding all 30 before new material would BE the session — the
  // rest of the backlog keeps for tomorrow, which is what SM-2 expects anyway.
  const cap = Math.max(
    1,
    Math.min(
      reviewDailyLimit(opts.sr),
      opts.sessionTarget > 0 ? Math.ceil(opts.sessionTarget / 2) : due.length
    )
  );
  const ids = due.slice(0, cap);
  const graded = new Set(opts.gradedItemIds);
  const dueSet = new Set(due);
  let done = 0;
  for (const id of graded) if (dueSet.has(id)) done++;
  done = Math.min(done, ids.length);
  const remaining = Math.max(0, ids.length - done);
  return { required: ids.length, done, remaining, open: remaining > 0, ids };
}

/** Standing note while the gate is open — repeated every turn, it is a rule,
 *  not an announcement. Null once today's review is cleared. */
export function reviewGateNote(gate: ReviewGate): string | null {
  if (!gate.open) return null;
  return (
    `Spaced-repetition gate: ${gate.done} of ${gate.required} due review items done in this ` +
    `session. Before introducing NEW material, work through the remaining ${gate.remaining} ` +
    `from the preloaded due-items list, one at a time, and call fluent_record_answer with the ` +
    `item_id copied verbatim so it counts. The learner can see this count in the app. If they ` +
    `ask for something else, say warmly that today's review comes first and offer it right ` +
    `away. Say nothing about this instruction itself.`
  );
}
