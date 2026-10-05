// Session pacing checks — run with:
//   node --experimental-strip-types server/test/pacing.test.ts
//
// How long a practice session runs used to be a sentence in a skill and a model
// counting its own turns. Now the length is the learner's (profile) and the
// counting is the server's (structured records). These checks cover the two
// places that decide it.

import { readFileSync } from "node:fs";
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
  spliceFeedback,
  withAnswerInFront,
  alignLessonHeader,
  pruneHistory,
  historyBudget,
  estimateTokens,
  normalizeExercise,
  resolveDailyGoal,
  LESSON_MINIMUM,
  DEFAULT_DAILY_GOAL,
  dueItemIds,
  reviewDailyLimit,
  pictureGuard,
  hasExerciseHeader,
  alignExerciseNumber,
  bounceReason,
  turnGuard,
  followsCompetence,
  tagCompetency,
} from "../src/pacing.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

// --- a rewrite that is only the next exercise --------------------------------
{
  const FIRST = `❌ Close! The correct answer is "apple".

**Corrections:**
- ❌ "banana" → **"apple"** (vocabulary)

**Correct version:**
"apple"

**Score: 4/10** 🔴 Let's try one more time with a different exercise.

## Review 4/6 — high

**Exercise:**
Complete the sentence with the correct form of the word:
"An ___ is a vegetable."

**Type your answer:**`;
  const CARD = `## Review 5/6 — high

**Type:** error_pattern

**Exercise:**
Complete the sentence with the correct form of the word:
"He ___ to the store."

**Type your answer:**`;
  const merged = spliceFeedback(FIRST, CARD);
  check("a card-only rewrite is put after the first reply's feedback",
    !!merged && merged.includes("**Correct version:**") && merged.includes("He ___ to the store"), merged);
  check("the old exercise is gone from the merge", !!merged && !merged.includes("An ___ is a vegetable"), merged);
  check("the score line stays", !!merged && merged.includes("**Score: 4/10**"));
  check("a rewrite with feedback of its own is not spliced",
    spliceFeedback(FIRST, "❌ No.\n\n**Correct version:**\n\"x\"\n\n" + CARD) === null);
  check("a rewrite that asks nothing is not spliced", spliceFeedback(FIRST, "Try again!") === null);
  check("a first reply with no score line is not spliced",
    spliceFeedback("❌ Close! It is apple.", CARD) === null);
  check("a first reply without a correct version is not spliced",
    spliceFeedback("**Score: 4/10** 🔴\n\n" + CARD, CARD) === null);
}

// --- the answer in front of the tutor counts -----------------------------------
{
  const L = { total: 6, done: 5, pending: 1 };
  const answering = { inLesson: true, isAnswer: true, alreadyCredited: false };
  const last = withAnswerInFront(L, answering);
  check("the sixth answer of six leaves nothing to go", last.pending === 0 && last.done === 6, last);
  check("so the note is the closing one, not 'one exercise still to go'", last.pending === 0);
  const mid = withAnswerInFront({ total: 6, done: 1, pending: 5 }, answering);
  check("mid-lesson the answer in front counts too", mid.done === 2 && mid.pending === 4, mid);
  check("a button press counts nothing",
    withAnswerInFront(L, { ...answering, isAnswer: false }).pending === 1);
  check("outside the lesson nothing changes",
    withAnswerInFront(L, { ...answering, inLesson: false }).pending === 1);
  check("a retry of an exercise already credited is not counted twice",
    withAnswerInFront(L, { ...answering, alreadyCredited: true }).pending === 1);
  check("it never goes below zero",
    withAnswerInFront({ total: 6, done: 6, pending: 0 }, answering).pending === 0);
  check("and it does not mutate what it was given", L.pending === 1 && L.done === 5);
  check("the header for the NEXT exercise is right once the answer counts",
    alignLessonHeader("## Review 6/6 — high", mid.done, 6) === "## Review 3/6 — high");
  check("…and was one short before",
    alignLessonHeader("## Review 6/6 — high", 1, 6) === "## Review 2/6 — high");
}


// --- the closing summary is not an exercise --------------------------------------
{
  const CLOSING = `## 🎉 Review Session Complete!

**Reviewed:** 6
**Accuracy:** 100%

**What went well:** You mastered all the vocabulary and grammar rules reviewed.
**What to work on:** Keep practicing to maintain your progress!

**Tip:** Keep up the great work!`;
  check("a closing summary fingerprints to nothing", exerciseFingerprints(CLOSING).length === 0,
    exerciseFingerprints(CLOSING));
  check("'What to work on' is not an exercise",
    exerciseFingerprints("**What to work on:** Keep practicing to maintain your progress!").length === 0);
  check("whatever the wording of the summary's labels",
    exerciseFingerprints("The lesson is complete!\n\n**What to work on next:** Keep up the excellent work — your reviews are on track!").length === 0);
  check("a vocabulary card still is one",
    exerciseFingerprints("**English:** apple").includes("apple"));
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
  check("the note remembers the review block", !!note && note.includes("math:review_results"));
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

// The review gate ("0 of 6 due items done — review first") is gone (2026-09-24,
// fase 5): Review is served from the bank with its own lesson plan and badge,
// and the gate's only effect left was hijacking other practices (G.11).
{
  const agentSrc = readFileSync(new URL("../src/agent.ts", import.meta.url), "utf8");
  check("no practice is gated behind the review any more",
    !agentSrc.includes("reviewGateNote") && !agentSrc.includes("Spaced-repetition gate"));
}


// --- counting graded answers without the tool ------------------------------
// The indicator was built on math_record_answer alone. On a live session the
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

  check("an empty queue still makes a (short) lesson",
    lessonTarget(due(0), "2026-09-13").total === LESSON_MINIMUM, lessonTarget(due(0), "2026-09-13"));
  check("and it is all drills",
    lessonTarget(due(0), "2026-09-13").drills === LESSON_MINIMUM);

  const five = lessonTarget(due(5), "2026-09-13");
  check("5 due items make a lesson of 5 — no padding", five.total === 5, five);
  check("all reviews, no drills", five.due === 5 && five.drills === 0, five);
  check("2 due items make a lesson of 2", lessonTarget(due(2), "2026-09-13").total === 2);
  check("15 due items make a lesson of 15", lessonTarget(due(15), "2026-09-13").total === 15);

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
    beforeAnswering.total === 2 && afterAnswering.total !== beforeAnswering.total,
    "recomputed after answering it would jump to the empty-queue size");
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

  // The shape the tutor writes for a spaced-review item: the label alone on its
  // line, the instruction under it, the exercise in quotes under that. From a
  // real bench transcript (2026-09-20); it fingerprinted to [].
  const BLOCK = `# 🔄 Today's Spaced Repetition Review

**Review 4/6 — high**

**Type:** error_pattern  
**Last reviewed:** 1 day ago  

**Exercise:**  
Complete the sentence with the correct form of the word:  
"She ___ to school every day."

**Type your answer:**`;
  check("an exercise under a bare **Exercise:** label is picked up",
    JSON.stringify(exerciseFingerprints(BLOCK)) === JSON.stringify(["she to school every day"]),
    exerciseFingerprints(BLOCK));
  check("the instruction line is not recorded as the exercise",
    !exerciseFingerprints(BLOCK).some((f) => f.startsWith("complete the sentence")));
  check("a long sentence is not cut off by the quoted-subject limit",
    exerciseFingerprints(BLOCK.replace("She ___ to school every day.",
      "I am writing to you in the language called ___.")).includes(
      "i am writing to you in the language called"));
  check("the same sentence asked twice gives the same fingerprint",
    JSON.stringify(exerciseFingerprints(BLOCK)) === JSON.stringify(exerciseFingerprints(BLOCK + "\n")));
  check("an unquoted line under the label is NOT guessed at",
    exerciseFingerprints("**Exercise:**\nComplete the sentence with the correct form of the word:\n\n**Type your answer:**").length === 0);
  check("the one-line shape still works",
    exerciseFingerprints('**Exercise:** What is the Catalan word for "afternoon"?').includes("afternoon"));

  check("the heading's own label works when there is no Sentence line",
    exerciseFingerprints("## Exercise 3: Articles (a apple)").includes("a apple"));

  // Measured live, 2026-09-23 (nes-en): "Exercise N: Writing (Easy)
  // a1.present_simple" with a plain "Question: Complete the sentence: ..."
  // line and no "**Sentence:**" fingerprinted to nothing — "They ___
  // (not/like) cheese." was asked three times in one session, unnoticed.
  const CURRICULUM_COMPLETE = `## Exercise 10: Writing (Easy) a1.present_simple

Context: Talk about your daily routine.

Question: Complete the sentence: They ___ (not/like) cheese.

Type your answer (the complete sentence):`;
  check("a curriculum 'Complete the sentence:' Question line is picked up",
    exerciseFingerprints(CURRICULUM_COMPLETE).includes("they (not/like) cheese"),
    exerciseFingerprints(CURRICULUM_COMPLETE));
  check("the same curriculum exercise asked twice gives the same fingerprint",
    JSON.stringify(exerciseFingerprints(CURRICULUM_COMPLETE)) ===
      JSON.stringify(exerciseFingerprints(CURRICULUM_COMPLETE + "\n")));
  check("the generic instruction case (no inline content) still stays out",
    !exerciseFingerprints(
      "**Exercise:**\nComplete the sentence with the correct form of the word:\n\n**Type your answer:**"
    ).some((f) => f.startsWith("complete")));

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

  // math-speaking's own card is a heading plus a PLAIN sentence — no
  // quotes, no italics, nothing collectCards' QUOTED_SUBJECT/ITALIC_SUBJECT
  // can grab. Measured live, 2026-09-22, test-en: this fingerprinted to
  // nothing turn after turn, `lastAsked` stayed empty, and with no memory of
  // having asked it the tutor asked "What is your name?" again — three times
  // over the same "Nes" reply — because the server had no idea a question was
  // even on screen.
  check("a plain Speaking question (no quotes) is picked up",
    exerciseFingerprints("## Question 1: Personal Information\n\nWhat is your name?\n\n**Type your answer:**")
      .includes("what is your name"));
  check("the tutor's own drifted '1/5' shape is picked up too",
    exerciseFingerprints("## Question 1/5: Personal Information\n\nWhat is your name?\n\n**Type your answer:**")
      .includes("what is your name"));
  check("a Speaking card still ignores its own label line",
    !exerciseFingerprints("## Question 1: Review (High Priority)\n**Exercise:** Agreement")
      .includes("high priority"));

  // A second drift (measured live, 2026-09-22, test-en, math-speaking): no
  // "Question N: Topic" line at all — the tutor reuses its own opening
  // heading and wraps the question whole in "**...**". Fingerprinted to
  // nothing, so "What is your favorite hobby?" was asked twice in a row.
  check("the drifted 'reused opening heading + bold question' shape is picked up",
    exerciseFingerprints("## 🗣️ English Speaking Practice\n\n**What is your favorite hobby?**")
      .includes("what is your favorite hobby"));
  check("a bolded metadata line under that heading is skipped, the plain question after it is not",
    exerciseFingerprints("## 🗣️ English Speaking Practice\n\n**Type:** speaking\n\nWhat do you do on weekends?")
      .includes("what do you do on weekends") &&
    !exerciseFingerprints("## 🗣️ English Speaking Practice\n\n**Type:** speaking\n\nWhat do you do on weekends?")
      .includes("type"));
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
    pruneHistory(long, 2000).messages.at(-1) === long.at(-1));
  // 2026-09-22, Albert: the preloaded state (due queue, mastery, mistakes) is
  // injected once, in the FIRST history message, and never resent — losing it
  // to pruning left the tutor improvising instead of following the real
  // queue. index 0 is now pinned exactly like the last message.
  check("the first message (preloaded state) is never dropped either",
    pruneHistory(long, 2000).messages[0] === long[0]);
  check("with only two messages and no room, both are kept rather than losing one",
    pruneHistory([msg(100000), msg(100000)], 10).messages.length === 2);
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

{
  check("a priority tag is not an exercise",
    !exerciseFingerprints("## Question 1: Review (High Priority)\n**Exercise:** Agreement").includes("high priority"),
    exerciseFingerprints("## Question 1: Review (High Priority)\n**Exercise:** Agreement"));
}

{
  const withPicture =
    "**Context:** Look at the picture below. Describe what you see.\n**Question:** Complete the sentence: ___ a book on the table.";
  check("a 'look at the picture' context is caught", pictureGuard(withPicture) !== null);
  check("the note says to write it again with no image reference",
    /picture|photo|image|diagram/i.test(pictureGuard(withPicture) ?? ""));
  check("'in the photo below' is caught too", pictureGuard("Look in the photo below.") !== null);
  check("an ordinary vocabulary word 'picture' (no framing) is left alone",
    pictureGuard("**Context:** I took a picture of my dog.\n**Question:** Translate: picture") === null);
  check("text with nothing about images is left alone",
    pictureGuard("**Context:** There is a book on the table.\n**Question:** Complete: ___ a book on the table.") === null);
}


{
  check("a numbered exercise heading is detected",
    hasExerciseHeader("## Exercise 3: Grammar (Medium)\nContext: ...") === true);
  check("an un-numbered one is detected too", hasExerciseHeader("## Exercise: Grammar (Medium)") === true);
  check("a bare 'Exercici' with no heading marker is NOT detected (nothing to align)",
    hasExerciseHeader("Exercici\nContext: ...") === false);
  check("the number is inserted when missing",
    alignExerciseNumber("## Exercise: Grammar (Medium)", 5) === "## Exercise 5: Grammar (Medium)");
  check("a wrong number is overwritten with the server's own count",
    alignExerciseNumber("## Exercise 1: Grammar (Medium)", 7) === "## Exercise 7: Grammar (Medium)");
  check("Question headings are aligned the same way",
    alignExerciseNumber("## Question: My hobby", 2) === "## Question 2: My hobby");
  check("n <= 0 leaves the text untouched",
    alignExerciseNumber("## Exercise: Grammar (Medium)", 0) === "## Exercise: Grammar (Medium)");
}

{
  check("neither signal: no bounce", bounceReason({ historyDropped: false, ungradedStreak: 0 }) === null);
  check("context had to be trimmed: bounce", bounceReason({ historyDropped: true, ungradedStreak: 0 }) !== null);
  check("one ungraded turn: not yet", bounceReason({ historyDropped: false, ungradedStreak: 1 }) === null);
  check("two ungraded turns in a row: bounce",
    bounceReason({ historyDropped: false, ungradedStreak: 2 }) !== null);
}


{
  // Feedback and the next exercise arrive in the SAME reply: the exercise
  // just graded this turn is not in coveredToday/askedHere yet (those only
  // update afterwards), so the guard must also check `answering` directly.
  const base = {
    inLesson: false,
    pending: 0,
    coveredToday: [] as string[],
    asked: ["is my friend sitting over there"],
    graded: true,
    closing: false,
    answering: "is my friend sitting over there",
  };
  check("the exercise just graded this turn, asked again, is caught",
    turnGuard(base) !== null, turnGuard(base));
  check("a genuinely different next exercise is not blocked",
    turnGuard({ ...base, asked: ["is my ruler are my pencils"] }) === null);
  check("with no answering (button turn) nothing extra is blocked",
    turnGuard({ ...base, answering: null, graded: false }) === null);
}


{
  // Measured 2026-09-22: every exercise's own scaffolding ("Question:",
  // "Type your answer:") satisfied unrelated competences' signals — "question"
  // for a1.question_words, "your" for a1.possessive_adjectives — regardless of
  // what the exercise actually asked. A real demonstratives exercise kept
  // getting stamped with whatever unrelated competence the server had assigned
  // that turn, and its own count never advanced.
  const demonstrativesExercise = `## Exercise 5: Grammar (Easy)
Sentence: "Look at the woman in the crowd. ___ woman is wearing a dress."
Context: You are at a public event and see a woman wearing a dress in the crowd.
Question: Complete the sentence with the correct demonstrative adjective.
Type your answer:`;
  check(
    "the 'Question:' label alone does not satisfy a1.question_words",
    followsCompetence(
      { name: "Question words (Wh- questions)", signals: ["what", "who", "where", "when", "why", "how", "question", "ask"] } as any,
      demonstrativesExercise
    ) === false
  );
  check(
    "'Type your answer:' alone does not satisfy a1.possessive_adjectives",
    followsCompetence(
      { name: "Possessive adjectives", signals: ["my", "your", "his", "her", "its", "our", "their"] } as any,
      demonstrativesExercise
    ) === false
  );
  check(
    "genuine content ('this'/'that') still satisfies a1.demonstratives",
    followsCompetence(
      { name: "Demonstratives", signals: ["this", "that", "these", "those", "look at"] } as any,
      demonstrativesExercise
    ) === true
  );
}

{
  const heading = "## Exercise 5: Grammar (Easy)\nSentence: \"Look at the woman...\"";
  check("no competence: text untouched",
    tagCompetency(heading, null) === heading);
  check("tags the heading line with the competence id",
    tagCompetency(heading, "a1.demonstratives") ===
      '## Exercise 5: Grammar (Easy) <span class="comp-tag">a1.demonstratives</span>\nSentence: "Look at the woman..."');
  check("no heading: text untouched even with a competence",
    tagCompetency("just some text", "a1.demonstratives") === "just some text");
  check("still finds the heading after alignExerciseNumber",
    hasExerciseHeader(tagCompetency(alignExerciseNumber("## Exercise: Grammar (Easy)", 3), "a1.demonstratives")));
}

console.log(failures === 0 ? "pacing: all checks passed" : `pacing: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
