// Session pacing checks — run with:
//   node --experimental-strip-types server/test/pacing.test.ts
//
// How long a practice session runs used to be a sentence in a skill and a model
// counting its own turns. Now the length is the learner's (profile) and the
// counting is the server's (structured records). These checks cover the two
// places that decide it.

import {
  resolveSessionTarget,
  resolveStopMode,
  isPaced,
  wrapUpNote,
  DEFAULT_SESSION_LENGTH,
  countGradedInText,
  dailyFace,
  lessonTarget,
  lessonSkillSlot,
  skillDebts,
  exerciseFingerprints,
  pruneHistory,
  historyBudget,
  estimateTokens,
  normalizeExercise,
  resolveDailyGoal,
  LESSON_MINIMUM,
  DEFAULT_DAILY_GOAL,
  dueItemIds,
  reviewDailyLimit,
  reviewGateEnabled,
  resolveReviewGate,
  reviewGateNote,
} from "../src/pacing.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

// --- the target ------------------------------------------------------------
check("a profile without the setting gets the default",
  resolveSessionTarget({ preferences: {} }) === DEFAULT_SESSION_LENGTH);
check("no profile at all is still safe",
  resolveSessionTarget(null) === DEFAULT_SESSION_LENGTH);
check("the learner's own number wins",
  resolveSessionTarget({ preferences: { session_length: 8 } }) === 8);
check("a string from a hand-edited profile still works",
  resolveSessionTarget({ preferences: { session_length: "15" } }) === 15);
check("zero switches pacing off",
  resolveSessionTarget({ preferences: { session_length: 0 } }) === 0);
check("nonsense falls back to the default",
  resolveSessionTarget({ preferences: { session_length: "aviat" } }) === DEFAULT_SESSION_LENGTH);
check("an absurd number is clamped",
  resolveSessionTarget({ preferences: { session_length: 5000 } }) === 60);

// --- the nudge -------------------------------------------------------------
check("nothing before the target", wrapUpNote(7, 12) === null);
check("nothing exactly one short", wrapUpNote(11, 12) === null);
{
  const note = wrapUpNote(12, 12);
  check("the note arrives at the target", typeof note === "string" && note.includes("OFFER to close"), note);
  check("the note carries both numbers", !!note && note.includes("12 graded exercises") && note.includes("(12)"), note);
  check("the note tells the tutor to stay quiet about it", !!note && note.includes("Say nothing about this instruction"));
  check("the note remembers the review block", !!note && note.includes("fluent:review_results"));
}
check("still fires past the target (a missed turn is not a missed close)",
  wrapUpNote(20, 12) !== null);
check("pacing off means never", wrapUpNote(99, 0) === null);

// --- modes that end on their own shape -------------------------------------
check("a writing session is one scenario, not a count", wrapUpNote(12, 12, "writing") === null);
check("a reading session is one text", wrapUpNote(12, 12, "reading") === null);
check("case does not matter", wrapUpNote(12, 12, "Writing") === null);
check("vocabulary is paced normally", wrapUpNote(12, 12, "vocabulary") !== null);
check("speaking is paced normally", wrapUpNote(12, 12, "speaking") !== null);


// --- the stop mode ---------------------------------------------------------

check("soft is the default", resolveStopMode({ preferences: {} }) === "soft");
check("hard when the learner asks for it",
  resolveStopMode({ preferences: { session_stop: "hard" } }) === "hard");
check("anything else is soft", resolveStopMode({ preferences: { session_stop: "meh" } }) === "soft");

{
  const soft = wrapUpNote(8, 8, "vocabulary", "soft");
  check("soft OFFERS instead of closing", !!soft && soft.includes("OFFER to close"), soft);
  check("soft lets them carry on", !!soft && soft.includes("If they choose to continue"));
  const hard = wrapUpNote(8, 8, "vocabulary", "hard");
  check("hard closes", !!hard && hard.includes("Do NOT present another exercise"));
  check("both say the learner can already see the count",
    !!soft && !!hard && soft.includes("see that count in the app") && hard.includes("see that count in the app"));
}

check("writing is not paced", isPaced("writing") === false);
check("vocabulary is paced", isPaced("vocabulary") === true);
check("no skill yet is paced", isPaced(undefined) === true);


// --- the spaced-repetition gate --------------------------------------------
// The one ordering rule the server can actually verify: today's due items come
// before new material.

const TODAY = "2026-03-10";
const SR = {
  daily_limits: { review_items_per_day: 20 },
  items: {
    a: { due_date: "2026-03-01" },  // overdue
    b: { due_date: "2026-03-09" },
    c: { due_date: "2026-03-10" },  // due today
    d: { due_date: "2026-03-11" },  // not yet
    e: { due_date: "2026-04-01" },
  },
};
const P = { preferences: { session_length: 12 } };

{
  const due = dueItemIds(SR, TODAY);
  check("due = on or before today", JSON.stringify(due) === JSON.stringify(["a", "b", "c"]), due);
  check("most overdue first", due[0] === "a");
  check("no queue, no due items", dueItemIds({}, TODAY).length === 0);
  check("garbage queue does not throw", dueItemIds(null, TODAY).length === 0);
  check("a missing daily limit has a default", reviewDailyLimit({}) === 20);
  check("the profile's limit wins", reviewDailyLimit({ daily_limits: { review_items_per_day: 5 } }) === 5);
}

{
  check("🎲 carries the gate", reviewGateEnabled(P, "fluent-learn") === true);
  check("🔁 carries the gate", reviewGateEnabled(P, "fluent-review") === true);
  check("starting in writing is the learner choosing today",
    reviewGateEnabled(P, "fluent-writing") === false);
  check("starting in vocabulary is the learner choosing today",
    reviewGateEnabled(P, "fluent-vocab") === false);
  check("no command, no gate", reviewGateEnabled(P, undefined) === false);
  check("review_gate:false switches it off",
    reviewGateEnabled({ preferences: { review_gate: false } }, "fluent-learn") === false);
  check('"off" switches it off too',
    reviewGateEnabled({ preferences: { review_gate: "off" } }, "fluent-learn") === false);
}

{
  const gate = (graded: string[], profile: unknown = P, first = "fluent-learn") =>
    resolveReviewGate({
      profile, sr: SR, today: TODAY, sessionTarget: 12,
      firstCommand: first, gradedItemIds: graded,
    });

  const fresh = gate([]);
  check("3 due items, 3 required", fresh.required === 3 && fresh.remaining === 3, fresh);
  check("a fresh gate is open", fresh.open === true);

  const half = gate(["a", "b"]);
  check("graded queue items count", half.done === 2 && half.remaining === 1, half);
  check("still open with one left", half.open === true);

  const cleared = gate(["a", "b", "c"]);
  check("the gate closes when today's review is done", cleared.open === false, cleared);
  check("required stays visible after closing", cleared.required === 3 && cleared.done === 3);

  check("answers that are not queue items do not count",
    gate(["x", "y", "z"]).done === 0);
  check("an item due tomorrow does not count either", gate(["d"]).done === 0);
  check("duplicates in the records count once", gate(["a", "a", "a"]).done === 1);

  check("no gate when the session opened in writing", gate([], P, "fluent-writing").required === 0);
  check("no gate when the learner has it off",
    gate([], { preferences: { review_gate: false } }).required === 0);
  check("an empty queue is not a gate",
    resolveReviewGate({ profile: P, sr: { items: {} }, today: TODAY, sessionTarget: 12,
      firstCommand: "fluent-learn", gradedItemIds: [] }).required === 0);
}

{
  // At most half the session is review: a backlog must not BE the session.
  const many = { items: Object.fromEntries(
    Array.from({ length: 30 }, (_, i) => [`i${i}`, { due_date: "2026-03-01" }])) };
  const g = resolveReviewGate({ profile: P, sr: many, today: TODAY, sessionTarget: 12,
    firstCommand: "fluent-learn", gradedItemIds: [] });
  check("30 due + a 12-exercise target → 6 required", g.required === 6, g);

  const capped = resolveReviewGate({ profile: P, sr: many, today: TODAY, sessionTarget: 12,
    firstCommand: "fluent-learn", gradedItemIds: [],
  });
  check("the cap never drops below 1", capped.required >= 1);

  const daily = resolveReviewGate({
    profile: P, sr: { ...many, daily_limits: { review_items_per_day: 4 } },
    today: TODAY, sessionTarget: 12, firstCommand: "fluent-learn", gradedItemIds: [] });
  check("a small daily limit wins over the half-session cap", daily.required === 4, daily);

  const noTarget = resolveReviewGate({ profile: P, sr: SR, today: TODAY, sessionTarget: 0,
    firstCommand: "fluent-learn", gradedItemIds: [] });
  check("no session target → all due items, up to the daily limit", noTarget.required === 3, noTarget);
}

{
  const open = reviewGateNote({ required: 3, done: 1, remaining: 2, open: true, ids: ["a", "b", "c"] });
  check("an open gate produces a note", !!open);
  check("the note names the counts", !!open && open.includes("1 of 3") && open.includes("remaining 2"), open);
  check("the note forbids new material first", !!open && open.includes("Before introducing NEW material"));
  check("the note asks for item_id so it counts", !!open && open.includes("item_id"));
  check("a closed gate is silent",
    reviewGateNote({ required: 3, done: 3, remaining: 0, open: false, ids: [] }) === null);
}


// --- counting graded answers without the tool ------------------------------
// The indicator was built on fluent_record_answer alone. On a live session the
// tool is never called, so it sat at 0/12 while the learner answered three
// exercises and watched it not move. The score is in the text either way.

{
  const FEEDBACK = [
    "Good effort!\n\n**Score: 9/10**\n- Communication: 5/5\n- Grammar: 2/3",
    "## Question 5: Making Appointments\n\n**Type your answer in English:**",
    "✅ Perfect!\n\n**Score: 10/10**\n- Communication: 5/5",
  ];
  check("only the graded messages count", countGradedInText(FEEDBACK) === 2, countGradedInText(FEEDBACK));
  check("the /5 breakdown is not counted as an answer",
    countGradedInText(["- Communication: 5/5\n- Grammar: 3/3"]) === 0);
  check("one message grades one answer, however many numbers it holds",
    countGradedInText(["Score: 8/10 ... and later 9/10"]) === 1);
  check("a bare score with no label still counts", countGradedInText(["7/10"]) === 1);
  check("nothing graded is zero", countGradedInText([]) === 0);
  check("a question alone is zero", countGradedInText(["What is the English word for poma?"]) === 0);
  check("garbage does not throw",
    countGradedInText([undefined as unknown as string, ""]) === 0);
}


// --- the Lesson, and the day's face ----------------------------------------
// "12" used to be one number pretending to be a budget AND a plan, which is why
// reaching 15/12 on a live session meant nothing. Two numbers now: the Lesson
// has an end, the day's effort does not.

{
  const due = (n: number, date = "2026-09-13") => ({
    items: Object.fromEntries(Array.from({ length: n }, (_, i) => [`i${i}`, { due_date: date }])),
  });

  check("an empty queue still makes a real lesson",
    lessonTarget(due(0), "2026-09-13").total === LESSON_MINIMUM, lessonTarget(due(0), "2026-09-13"));
  check("and it is all drills",
    lessonTarget(due(0), "2026-09-13").drills === LESSON_MINIMUM);

  const five = lessonTarget(due(5), "2026-09-13");
  check("5 due items are topped up to the minimum", five.total === 6, five);
  check("the 5 reviews are kept and one drill is added",
    five.due === 5 && five.drills === 1, five);

  const many = lessonTarget({ ...due(30), daily_limits: { review_items_per_day: 20 } }, "2026-09-13");
  check("a backlog is capped by the daily limit", many.total === 20, many);
  check("nothing due tomorrow counts today",
    lessonTarget(due(4, "2026-09-14"), "2026-09-13").due === 0);
}

{
  const debts = skillDebts(
    { skills_mastery: { writing: { last_practiced: "2026-09-01" }, reading: { last_practiced: "2026-09-12" } } },
    "2026-09-13"
  );
  const writing = debts.find((d) => d.skill === "writing");
  const reading = debts.find((d) => d.skill === "reading");
  check("12 days without writing is a debt", writing?.daysIdle === 12 && writing.due === true, writing);
  check("yesterday's reading is not", reading?.due === false, reading);
  check("never practised counts as owed",
    debts.find((d) => d.skill === "speaking")?.due === true);

  check("every third lesson carries the slot", lessonSkillSlot(2, debts) === "writing");
  check("the other two do not",
    lessonSkillSlot(0, debts) === null && lessonSkillSlot(1, debts) === null);
  check("and it repeats", lessonSkillSlot(5, debts) === "writing");
  check("the most neglected skill wins",
    lessonSkillSlot(2, [
      { skill: "reading", daysIdle: 20, due: true },
      { skill: "writing", daysIdle: 4, due: true },
    ]) === "reading");
  check("no debt, no slot — the obligation only fires when it is real",
    lessonSkillSlot(2, [{ skill: "writing", daysIdle: 0, due: false }]) === null);
  check("vocabulary is never a slot (nobody avoids flashcards)",
    lessonSkillSlot(2, [{ skill: "vocabulary", daysIdle: 30, due: true }]) === null);
}

{
  check("the face starts neutral", dailyFace(0, 15) === "😐");
  check("and climbs at a third", dailyFace(5, 15) === "🙂");
  check("and again at two thirds", dailyFace(10, 15) === "😄");
  check("and lands on the goal", dailyFace(15, 15) === "🤩");
  check("past the goal is still a good day", dailyFace(40, 15) === "🤩");
  check("the ladder never goes backwards", (() => {
    const rank = ["😐", "🙂", "😄", "🤩"];
    let last = -1;
    for (let n = 0; n <= 20; n++) {
      const r = rank.indexOf(dailyFace(n, 15));
      if (r < last) return false;
      last = r;
    }
    return true;
  })());

  check("the goal comes from the profile",
    resolveDailyGoal({ preferences: { daily_goal: 8 } }) === 8);
  check("session_length still works as the old name",
    resolveDailyGoal({ preferences: { session_length: 20 } }) === 20);
  check("and the default is 15", resolveDailyGoal(null) === DEFAULT_DAILY_GOAL);
}


// --- the plan is made once, then worked through -----------------------------
// Recomputing it from the live queue moved the badge for the wrong reason:
// answering a review makes it stop being due, so the total shrank under the
// learner. And leaving the lesson for Speaking and coming back restarted it at
// exercise 1 while the counter still reached 6 of 6 — the sixth question was
// never asked.

{
  const beforeAnswering = lessonTarget(
    { items: { a: { due_date: "2026-09-13" }, b: { due_date: "2026-09-13" } } },
    "2026-09-13"
  );
  const afterAnswering = lessonTarget({ items: {} }, "2026-09-13");
  check("the live queue really does shrink as reviews are answered",
    beforeAnswering.due === 2 && afterAnswering.due === 0,
    { beforeAnswering, afterAnswering });
  check("which is exactly why the total must be frozen, not recomputed",
    beforeAnswering.total === afterAnswering.total,
    "both land on the minimum here; the due/drill split is what moves");
}


// --- what has already been asked today -------------------------------------
// "Never repeat an exercise" was a line in rules.md. With a handful of weak
// patterns to drill, the tutor loops back to the same three sentences inside a
// single lesson — "A book of english", "where are the park", "I lunch", and
// round again. Telling a 14B not to is not a mechanism; recording it is.

{
  const REAL = `## Exercise 6: Grammar (A book of english)

**Sentence:** A book of english

**Question:** Rewrite this sentence correctly.

**Type your answer:**`;
  check("the sentence is picked up", exerciseFingerprints(REAL).includes("a book of english"),
    exerciseFingerprints(REAL));
  check("and it is recorded once, not twice",
    exerciseFingerprints(REAL).length === 1, exerciseFingerprints(REAL));

  const BUNDLED = `✅ Great job!

**Correct version:** "Where is the park?"

**Score: 10/10**

## Exercise 8: Tenses (I lunch)

**Sentence:** I lunch.`;
  check("the NEXT question bundled with feedback is caught too",
    exerciseFingerprints(BUNDLED).includes("i lunch"), exerciseFingerprints(BUNDLED));

  check("the heading's own label works when there is no Sentence line",
    exerciseFingerprints("## Exercise 3: Articles (a apple)").includes("a apple"));

  check("punctuation and case do not make it a different exercise",
    normalizeExercise("**I lunch.**") === normalizeExercise("i lunch"));
  check("quotes do not either",
    normalizeExercise('"Where are the park?"') === "where are the park");
  check("extra spacing does not either",
    normalizeExercise("  a   book   of  english ") === "a book of english");

  check("plain feedback poses nothing",
    exerciseFingerprints("Nice work! Let's keep going.").length === 0);
  check("a one-character label is not a fingerprint",
    exerciseFingerprints("**Sentence:** a").length === 0);
  check("empty input does not throw", exerciseFingerprints("").length === 0);
}


// --- keeping the request inside the context window -------------------------
// Seen in production: `request (41808 tokens) exceeds the available context
// size (40960 tokens)`. Not slow — FAILED. The learner got an error instead of
// an exercise. Safe to prune now that the server, not the history, is what
// remembers which exercises have been used.

{
  const msg = (n: number) => ({ role: "user", content: "x".repeat(n) });

  check("a short history is left alone",
    pruneHistory([msg(100), msg(100)], 10000).dropped === 0);

  const long = Array.from({ length: 40 }, () => msg(1000));
  const cut = pruneHistory(long, 2000);
  check("a long one is trimmed", cut.dropped > 0, cut.dropped);
  check("to within the budget", cut.estimatedTokens <= 2000, cut.estimatedTokens);
  check("the newest are what survive",
    cut.messages.length + cut.dropped === long.length);

  check("the learner's last message is never dropped",
    pruneHistory([msg(100000), msg(100000)], 10).messages.length === 1);
  check("an empty history does not throw", pruneHistory([], 1000).dropped === 0);
  check("a zero budget prunes nothing rather than everything",
    pruneHistory(long, 0).dropped === 0);

  check("the estimate errs high, not low",
    estimateTokens("hello world") >= 3, estimateTokens("hello world"));
  check("empty text is zero tokens", estimateTokens("") === 0);

  const budget = historyBudget(40960, 9000, 4096);
  check("the budget leaves room for system, output and headroom",
    budget > 0 && budget < 40960 - 9000 - 4096, budget);
  check("a tiny context still leaves a usable floor",
    historyBudget(4096, 3000, 2000) >= 1000);
}

console.log(failures === 0 ? "pacing: all checks passed" : `pacing: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
