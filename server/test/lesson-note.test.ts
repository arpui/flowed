// Replay of the 2026-09-16 incident — run with:
//   node --experimental-strip-types server/test/lesson-note.test.ts
//
// Every string below is verbatim from that day's sessions.db and .daily/ files.
// The point is not that these functions are correct in the abstract: it is that
// the exact inputs that produced sixty turns without a single correction now
// produce something different.

import fs from "node:fs";
import path from "node:path";
import {
  lessonNote,
  skillBlock,
  exerciseFingerprints,
  countGradedInText,
  renderSkillForModel,
  requiredSkills,
  parseFeedback,
  dueItemIds,
  drillMaterial,
  lessonTarget,
  buildStamp,
  alignMarkersToScore,
  markerForScore,
  turnGuard,
  followsCompetence,
  followsAssigned,
  feedbackFollowsGrading,
  parseTopics,
  exerciseOnlyOf,
  isExerciseGuard,
  isFeedbackGuard,
  mergeFeedbackOnly,
  trailingExercise,
  spliceFeedback as spliceFb,
  pickTopics,
  topicsNote,
  scoreOfReply,
  KNOWN_SCORE,
  alignLessonHeader,
  nextDueItem,
  practiceNote,
  normalizeExercise,
} from "../src/pacing.ts";
import { loadSkill, loadCommand } from "../src/commands.ts";

const ROOT = path.resolve(import.meta.dirname, "..", "..");

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

// --- the skill actually reaches the prompt ---------------------------------

const review = loadSkill(ROOT, "math-review");
check("the server finds the review skill on disk", !!review);
const block = skillBlock(review);
check("it becomes a system-prompt block", !!block && block.includes("<skill_content"));
for (const token of ["**Correct version:**", "Score: ", "math_record_answer", "Every answer gets BOTH"]) {
  check(`the block carries the grading contract: ${token.trim()}`, !!block && block.includes(token));
}
check("no skill, no block", skillBlock(undefined) === null);
check("an unknown skill is not invented", loadSkill(ROOT, "math-nope") === undefined);
check("a path is not a skill name", loadSkill(ROOT, "../../etc") === undefined);

const commanded = fs.readFileSync(path.join(ROOT, "prompts", "commands", "math-review.md"), "utf8");
check("the command no longer delegates the load to the model",
  !commanded.includes("via the skill tool"));

// --- the note is state, not a script ---------------------------------------
//
// Iona's real plan, frozen: .daily/lesson-2026-09-16.json said done 0 of 12
// while she worked through thirteen exercises.

const IONA_COVERED = [
  "tom plays the guirar",
  "my brother speaks english",
  "my sister runs to day",
  "my sister runs today",
];
const frozen = { total: 12, done: 0, pending: 12, due: 12, slot: null };
const note = lessonNote(frozen, IONA_COVERED, null);

for (const banned of [
  "and nothing else",
  "Present exercise",
  "CONTINUATION",
  "Do NOT greet",
  "do not use the same shape",
]) {
  check(`the note never says "${banned}"`, !note.includes(banned), note);
}
check("it does say where the lesson is", note.includes("0 of 12 done"));
check("it hands back what was already asked", note.includes('"my sister runs today"'));

// The killer property: two consecutive turns must not produce the same note
// when anything has moved. On 2026-09-16 nothing moved, and the identical
// sentence arrived twenty-five times.
const afterOne = lessonNote({ ...frozen, done: 1, pending: 11 }, IONA_COVERED, "my sister runs today");
check("the note moves when the lesson moves", afterOne !== note);
check("progress moves it", afterOne.includes("1 of 12 done"));
check("the last exercise is named so it is not repeated",
  afterOne.includes('Your previous exercise was "my sister runs today"'));
check("a lesson under way says so", afterOne.includes("continue it rather than starting it again"));
check("a fresh lesson does not", !note.includes("continue it rather than starting it again"));

// --- the fingerprints catch what the tutor really wrote ---------------------

const EX5_IONA = `## Exercise 5: Vocabulary

**Word (Catalan):** l'anglès

**Context:** Iona is learning to speak English.

**Question:** What is the English word for "l'anglès"?

**Type your answer:**`;

const EX9_IONA = `## Exercise 9: Spelling

**Sentence:** My sister runs today

**Question:** What is the correct spelling of the word "today" in this sentence?

**Type your answer:**`;

const NAIA_LOOP = `## Exercise 2: Spaced Review (Critical)

**Item ID:** "vocab_afternoon"

**Exercise:** What is the Catalan word for "afternoon"?

**Type your answer:**`;

const f5 = exerciseFingerprints(EX5_IONA);
check("the qualified vocabulary label is seen at last", f5.includes("word (catalan): l'anglès") || f5.some((l) => l.includes("anglès")), f5);
check("a vocabulary turn is no longer invisible", f5.length > 0, f5);

const f9 = exerciseFingerprints(EX9_IONA);
check("the repeated spelling exercise is fingerprinted", f9.includes("my sister runs today"), f9);

const fn = exerciseFingerprints(NAIA_LOOP);
check("the difficulty is not mistaken for the exercise", !fn.includes("critical"), fn);
// The subject, not the sentence: the item id and the word it is about, which
// is what tells this exercise from the next one.
check("the subject of the question is what gets recorded",
  fn.some((l) => l.includes("afternoon")), fn);

check("never more than two per turn", exerciseFingerprints(EX9_IONA).length <= 2, f9);

// The loop, replayed: exercise 9 asked what exercise 4 already asked.
const alreadyAsked = new Set(IONA_COVERED);
check("with the fix, the repeat is already on the list",
  f9.some((l) => alreadyAsked.has(l)), { f9, IONA_COVERED });

// --- the counter's two witnesses -------------------------------------------
//
// Verbatim: the tutor called math_record_answer and wrote this as its whole
// visible reply. No marker, no correction, no score — and under the old rule
// the lesson counter read this as "nothing happened".

const GRADED_BUT_SILENT = `## Exercise 2: Capitalization

**Sentence:** My brother speaks english

**Question:** What is the correct capitalization of the word "english" in this sentence?

**Type your answer:**`;

check("the text alone really did say nothing was graded",
  countGradedInText([GRADED_BUT_SILENT]) === 0);
check("a proper feedback turn still counts",
  countGradedInText([`🟡 Almost.\n\n**Correct version:**\n"English"\n\n**Score: 6/10**`]) === 1);

// --- the state block is not re-injected on every press ---------------------

const first = await loadCommand("math-review", {
  root: ROOT, dataDir: ROOT, env: {}, skipDirectives: true,
});
check("a continuing command resolves", !!first);
check("it carries the skill with it", first?.skill?.name === "math-review");
check("and it does NOT re-run read-db.py",
  !!first && !first.body.includes("!`python3 hooks/read-db.py`") &&
  first.body.includes("in your system prompt"));

// --- the learner state survives a pruned history ----------------------------
//
// The block naming the learner, their level, their due queue and their weak
// patterns used to live in the first message of the session. pruneHistory
// drops the oldest first, so on a long session that block is the FIRST thing
// to go — while the next command says "it is in the history above; do NOT
// reload it". The tutor then teaches someone it knows nothing about.

// The directive itself runs through Bun.spawn, which node cannot execute, so
// what is checked here is the wiring — that the state is collected apart from
// the turn and pinned to the system prompt. The subprocess path is covered by
// PROVES.md § 22.
const src = fs.readFileSync(path.join(ROOT, "server", "src", "commands.ts"), "utf8");
check("the directive output is collected, not spliced into the turn",
  src.includes("if (opts.collect) opts.collect.push(stdout.trimEnd());"));
check("and returned as its own field", src.includes("...(state ? { state } : {})"));
const agentSrc = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
check("the server pins it to the system prompt", agentSrc.includes("this.activeState.set(sessionId"));
const systemPromptBody = (agentSrc.split("private buildSystemPrompt")[1] ?? "").split("// ---- history")[0] ?? "";
check("where pruning cannot reach it", systemPromptBody.includes("this.activeState.get(sessionId)"));
check("and the later commands are told where it is",
  src.includes("in your system prompt, above"));

// --- the lesson ends when the lesson ends, not when the queue does ----------
const midLesson = lessonNote(
  { total: 6, done: 2, pending: 4, due: 0, slot: null, material: 2 }, [], null
);
check("a queue that runs out does not end the lesson",
  midLesson.includes("4 exercise(s) still to go"), midLesson);
check("and closing early is forbidden in as many words",
  midLesson.includes("do NOT close the") && midLesson.includes("not even if the review queue runs out"));
check("grading and asking are one turn",
  midLesson.includes("grade the answer in front of you AND present the next, DIFFERENT exercise"));
check("and repeating a question is ruled out in the note too",
  midLesson.includes("never ask the same question twice"));
const reviewSkill = fs.readFileSync(path.join(ROOT, "skills", "math-review", "SKILL.md"), "utf8");
check("any valid notation is accepted, but only the math is graded",
  reviewSkill.includes("Any valid notation is a real answer. Only the math gets graded"));
check("and a native-language slip is never filed",
  reviewSkill.includes("do not record it"));
check("retrying has a limit", reviewSkill.includes("One retry, then move on"));
check("and a third identical question is ruled out",
  reviewSkill.includes("Never ask the same question a third time"));
check("and makes the marker match the score",
  reviewSkill.includes("The marker has to match the score"));
check("the plan can remember what it already counted",
  fs.readFileSync(path.join(ROOT, "server", "src", "daily.ts"), "utf8").includes("credited?: string[]"));
check("and the server refuses to count one exercise twice",
  fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8")
    .includes("already counted — not twice"));
check("the skill says the same thing",
  fs.readFileSync(path.join(ROOT, "skills", "math-review", "SKILL.md"), "utf8")
    .includes("The lesson's length is the server's, not the queue's"));

// --- what the model is actually handed --------------------------------------
//
// The first lesson run with the skill really loaded produced, verbatim:
//   Review 1/6 — 🟡
//   Type: vocabulary
//   {Target}: {the word}
//   What does it mean in {Native}?
// That is Example 1 of the skill, copied out. And the morning transcript opens
// with a literal "{✅}", which is the feedback template's "{✅ or ❌}".

const rendered = loadSkill(ROOT, "math-review", path.join(ROOT, "data-examples"));
const shown = rendered?.body ?? "";
check("the worked examples are not shipped to the model", !/##\s+Examples/.test(shown));
check("their placeholders go with them", !shown.includes("{the word}"), 
  shown.match(/\{the word\}/g));
check("the braces rule is stated", shown.includes("must never appear in anything you send"));
check("the feedback template travels with the skill",
  shown.includes('name="math-feedback-formatter"'));
check("so the grading shape is present", shown.includes("**Correct version:**"));
check("the dependency is declared, not guessed",
  requiredSkills(fs.readFileSync(path.join(ROOT, "skills", "math-review", "SKILL.md"), "utf8"))
    .includes("math-feedback-formatter"));

const resolved = renderSkillForModel(
  "## Overview\n\n**{Target}:** hello — what is it in {Native}?\n\n## Examples\n\n> {the word}\n",
  { target: "english", native: "català" }
);
check("the two languages the server knows are filled in",
  resolved.includes("**English:**") && resolved.includes("in Català"), resolved.slice(0, 120));
check("and the example section is gone", !resolved.includes("{the word}"));

// --- a profile with nothing to review ---------------------------------------
//
// test-en ships as the provisioning template: review_queue.today empty, one
// item whose item_id is the string "{unique_identifier}", one error pattern
// called example_pattern_1 with frequency 0. Counted as real, that becomes
// "6 items due" and the tutor reviews six things that do not exist.

const TEMPLATE_SR = {
  review_queue: { today: [], tomorrow: [], this_week: [], later: [] },
  items: {
    example_item_id: { item_id: "{unique_identifier}", due_date: "{YYYY-MM-DD}" },
  },
};
const TEMPLATE_MISTAKES = { error_patterns: { example_pattern_1: { frequency: 0 } } };

check("a template item is not due", dueItemIds(TEMPLATE_SR, "2026-09-16").length === 0);
check("a template pattern is not material", drillMaterial(TEMPLATE_MISTAKES) === 0);
check("a real item still counts",
  dueItemIds({ items: { vocab_dog: { due_date: "2026-09-01" } } }, "2026-09-16").length === 1);
check("a real pattern still counts",
  drillMaterial({ error_patterns: { be_with_main_verb: { frequency: 5 } } }) === 1);

const empty = lessonTarget(TEMPLATE_SR, "2026-09-16");
const firstLesson = lessonNote(
  { total: empty.total, done: 0, pending: empty.total, due: 0, slot: null, material: 0, level: "A1" },
  [], null
);
check("an empty profile is told there is nothing to review",
  firstLesson.includes("NOTHING to review today"), firstLesson);
check("and not to dress it up as one",
  firstLesson.includes('Do NOT label these exercises') && firstLesson.includes("invents a history"));
check("it still gets a full lesson of new material",
  firstLesson.includes(`Teach ${empty.total} pieces of NEW material`));
check("at the learner's level", firstLesson.includes("(A1)"));
// With patterns to drill it is still "nothing to review" — that is what an
// empty queue means. What the patterns change is where the REST of the lesson
// comes from. Gating the whole branch on them let two junk patterns send the
// tutor off to improvise a review that did not exist.
const withPatterns = lessonNote(
  { total: 6, done: 0, pending: 6, due: 0, slot: null, material: 3 }, [], null);
check("an empty queue is an empty queue, patterns or not",
  withPatterns.includes("NOTHING to review"));
check("but the exercises come from the patterns",
  withPatterns.includes("from the weak patterns in mistakes-db"));
check("and with no patterns, from new material",
  lessonNote({ total: 6, done: 0, pending: 6, due: 0, slot: null, material: 0, level: "A1" }, [], null)
    .includes("pieces of NEW material"));

// --- a review of nothing is not a review -----------------------------------
const FABRICATED = `**Type:** vocabulary
**Last reviewed:** 0 days ago
**Current mastery:** ⭐

What is the English word for "culler"?`;
const fabState = { inLesson: true, pending: 4, coveredToday: [], askedHere: [],
                   asked: ["what is the english word for culler"], graded: false,
                   closing: false, replyText: FABRICATED };
check("an invented review card is sent back when nothing is due",
  (turnGuard({ ...fabState, due: 0 }) ?? "").includes("nothing due for review"));
check("with real items due it is a real review",
  turnGuard({ ...fabState, due: 3 }) === null);
check("and a plain exercise on an empty queue is fine",
  turnGuard({ ...fabState, due: 0, replyText: "What is the plural of child?" }) === null);
check("the skill forbids inventing one too",
  fs.readFileSync(path.join(ROOT, "skills", "math-review", "SKILL.md"), "utf8")
    .includes("Never invent a review item"));
check("and writing asks for a length the level can reach",
  fs.readFileSync(path.join(ROOT, "skills", "math-writing", "SKILL.md"), "utf8")
    .includes("Length follows the level"));

// --- the record the tutor never files --------------------------------------
//
// Verbatim from three live lessons: good corrections, in prose, and not one
// call to math_record_answer. The databases learned nothing from any of them.

const REAL_FEEDBACK = `**Corrections:**
- ❌ "banana" → **"pa amb tomàquet"** (vocabulary - "banana" is not related)

**Correct version:**
"Pa amb tomàquet"

**Score: 1/10** 🔴 Let's try again!`;

const p1 = parseFeedback(REAL_FEEDBACK);
check("the score is read out of the tutor's own text", p1?.score === 1, p1?.score);
check("and so is the correction",
  p1?.corrections[0]?.wrong === "banana" && p1?.corrections[0]?.right === "pa amb tomàquet",
  p1?.corrections);
check("with its category", p1?.corrections[0]?.category === "vocabulary", p1?.corrections[0]);
check("a low score makes it critical", p1?.corrections[0]?.severity === "critical");
check("the correct version comes through", p1?.correctVersion === "Pa amb tomàquet", p1?.correctVersion);

const p2 = parseFeedback(`❌ Almost.

**Corrections:**
- ❌ "She go to school" → **"She goes to school"** (agreement — with he/she/it the verb takes -s)
- ✅ "to school" — exactly right

**Correct version:**
"She goes to school."

**Score: 7/10** 🟡`);
check("the category stops at the dash", p2?.corrections[0]?.category === "agreement", p2?.corrections[0]);
check("a middling score is moderate", p2?.corrections[0]?.severity === "moderate");
check("the ✅ line is not a correction", p2?.corrections.length === 1, p2?.corrections);

check("a turn that grades nothing parses to nothing",
  parseFeedback("## Exercise 2: Vocabulary\n\n**Word:** cat\n\n**Type your answer:**") === null);
check("and so does an empty one", parseFeedback("") === null);

const agentText = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
check("the server writes it only when the tool did not",
  agentText.includes("this.recordCount(sessionId) === recordsBefore") &&
  agentText.includes("this.deriveRecord(sessionId, text"));   // (…, answeredAll) since the bank
check("a derived record never invents an item_id",
  agentText.includes("item && known ? { item_id") && agentText.includes("private itemExists"));

// --- the feedback template has no braces left to copy ----------------------
const formatter = fs.readFileSync(
  path.join(ROOT, "skills", "math-feedback-formatter", "SKILL.md"), "utf8");
const fbRendered = renderSkillForModel(formatter, { target: "english", native: "català" });
check("nothing in the feedback template is copyable as a slot",
  !/\{[^}\n]{0,40}\}/.test(fbRendered), (fbRendered.match(/\{[^}\n]{0,40}\}/) ?? [""])[0]);
check("the marker must agree with the score", formatter.includes("must agree with the number"));

// --- which build is running ------------------------------------------------
const read = (f: string) => fs.readFileSync(f, "utf8");
const list = (d: string) => fs.readdirSync(d);
const stampA = buildStamp(ROOT, read, list);
check("the build stamp is stable", stampA === buildStamp(ROOT, read, list), stampA);
check("and it changes when the source does",
  stampA !== buildStamp(ROOT, (f: string) => read(f) + (f.endsWith("agent.ts") ? "x" : ""), list));
check("the server serves it", fs.readFileSync(path.join(ROOT, "server", "src", "http.ts"), "utf8")
  .includes("build: opts.build"));
check("and the e2e refuses to judge a stale one",
  fs.readFileSync(path.join(ROOT, "scripts", "flowed-e2e.py"), "utf8")
    .includes("corre un build diferent del que hi ha al disc"));

// --- the marker is made to agree, not asked to -----------------------------
const REAL_GREEN_TWO = `❌ Close! The English word for "casa" is "house".

**Corrections:**
- ❌ "xxx" → **"house"** (vocabulary — "casa" is Catalan for "house")

**Correct version:**
"house"

**Score: 2/10** 🟢 Try again with a new word!`;
const fixed = alignMarkersToScore(REAL_GREEN_TWO);
check("a green light on a 2/10 is repainted", fixed.includes("**Score: 2/10** 🔴"), fixed.slice(-40));
check("and nothing else in the reply moves",
  fixed.includes('"casa" is Catalan for "house"') && fixed.includes('**Correct version:**'));
check("✅ and ❌ are left alone", fixed.includes('- ❌ "xxx"'));
check("a high score keeps its green",
  alignMarkersToScore(REAL_GREEN_TWO.replace("2/10", "9/10")).includes("9/10** 🟢"));
check("a reply with no score is untouched",
  alignMarkersToScore("just a question 🟢") === "just a question 🟢");
check("the thresholds are the ones the skill states",
  markerForScore(0) === "🔴" && markerForScore(4) === "🔴" && markerForScore(5) === "🟡" &&
  markerForScore(7) === "🟡" && markerForScore(8) === "🟢" && markerForScore(10) === "🟢");
check("the server applies it before storing the reply",
  fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8")
    .includes("text: this.tidyTutorText(sessionId, step.text)"));

// --- and the record question is asked of the records, not of the text ------
const ag = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
check("the derived record asks the records file directly",
  ag.includes("private recordCount(sessionId: string): number"));
check("not gradedSoFar, which falls back to counting score lines",
  !ag.includes("this.gradedSoFar(sessionId).count === recordsBefore"));

// --- the guard: forced, not asked ------------------------------------------
//
// Three rules asked for in the skill and the note, all three broken live. The
// traffic-light marker was asked for three times and fixed in one line when the
// server stopped asking. Same treatment here.

const base = { inLesson: true, pending: 4, coveredToday: ["casa", "aigua"],
               asked: ["pa"], graded: true, closing: false };
check("a turn that moves the lesson is left alone", turnGuard(base) === null);
check("closing with exercises left is sent back",
  (turnGuard({ ...base, closing: true }) ?? "").includes("still to do"));
check("but closing a finished lesson is fine",
  turnGuard({ ...base, closing: true, pending: 0 }) === null);
check("re-asking today's question is sent back",
  (turnGuard({ ...base, asked: ["casa"] }) ?? "").includes('already asked "casa"'));
check("a reply that corrects and asks nothing is sent back",
  (turnGuard({ ...base, asked: [] }) ?? "").includes("asks nothing"));
check("a turn that asks something new AND something old is allowed through",
  turnGuard({ ...base, asked: ["casa", "pa"] }) === null);
// Repetition is wrong everywhere; the lesson's own rules are not. Guarding
// only the Lesson left Vocabulary with no referee, and it repeated a word
// between visits in all three measured runs.
check("outside the lesson, a repeat is still a repeat",
  (turnGuard({ ...base, inLesson: false, asked: ["casa"] }) ?? "").includes('already asked "casa"'));
check("but the lesson's own rules stay inside it",
  turnGuard({ ...base, inLesson: false, asked: ["pa"], closing: true }) === null);
check("and a fresh question outside is left alone",
  turnGuard({ ...base, inLesson: false, asked: ["pa"] }) === null);

const pn = practiceNote(["casa", "aigua"], "aigua");
check("free practice is told what it already asked", Boolean(pn?.includes('"casa", "aigua"')));
check("and nothing about pacing", !(pn ?? "").includes("Lesson progress"));
check("with nothing asked yet there is no note", practiceNote([]) === null);

// The exercise being answered is not "already asked" in the sense of the ban, and
// the tutor is told to grade first (measured: "morn" for "matí" got the same card
// back twice, with no feedback, because "matí" was on the ban list).
{
  const ans = practiceNote(["matí", "finestra"], "matí", true) ?? "";
  check("an answer in front: the tutor is told to grade it first",
    ans.includes('answer to "matí"') && ans.includes("Grade it first"), ans);
  check("the exercise in play is not on the ban list",
    ans.includes('"finestra"') && !ans.includes('do not ask any of these again: "matí"') &&
      !/again:[^.]*"matí"/.test(ans), ans);
  const only = practiceNote(["matí"], "matí", true) ?? "";
  check("even when it is the only one covered, the grading instruction stays",
    only.includes("Grade it first") && !only.includes("Already answered"), only);
  const noAnswer = practiceNote(["matí"], "matí", false) ?? "";
  check("no answer in front: as before", noAnswer.includes('"matí"') &&
    noAnswer.includes("Your previous exercise") && !noAnswer.includes("Grade it first"), noAnswer);
}

// --- an answer in front and no grading, in any practice -----------------------
{
  const base = {
    inLesson: false, pending: 0, coveredToday: ["matí"], askedHere: [] as string[],
    asked: ["matí"], graded: false, closing: false,
  };
  const g = turnGuard({ ...base, answering: "matí" });
  check("a free-practice reply that re-asks without grading is sent back",
    Boolean(g && g.includes('answered "matí"') && g.includes("does not grade")), g);
  check("and it is told not to repeat the exercise", Boolean(g && g.includes('Do not repeat "matí"')), g);
  check("a different new exercise with no grading is sent back too",
    Boolean(turnGuard({ ...base, asked: ["finestra"], answering: "matí" })));
  check("a graded reply is left alone",
    turnGuard({ ...base, asked: ["finestra"], graded: true, answering: "matí" }) === null);
  check("no answer in front (a menu choice): left alone",
    turnGuard({ ...base, asked: ["finestra"], answering: null }) === null);
  check("a reply that asks nothing is not this guard's business",
    turnGuard({ ...base, asked: [], answering: "matí" }) === null);
  check("the closing message is not sent back",
    turnGuard({ ...base, asked: ["finestra"], closing: true, answering: "matí" }) === null);
}

const ag2 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
check("the server rewrites the turn rather than asking again",
  ag2.includes("private async enforceTurn") && ag2.includes("this.db.updatePart"));
// Calls, not mentions: the comments around the streaming path name it too.
check("and only once", ag2.split("await this.enforceTurn(").length === 2);

// --- the rig cannot be mis-set-up any more ---------------------------------
//
// A seeded run reported seven failures and every one of them was the rig: the
// morning's finished lesson was still in .daily, so the tutor was told the
// lesson was complete, said so, asked nothing — correctly — and every check
// that counts exercises read zero.
const seed = fs.readFileSync(path.join(ROOT, "scripts", "flowed-seed.py"), "utf8");
check("seeding a past empties today", seed.includes("avui") && seed.includes('".daily"'));
const e2e = fs.readFileSync(path.join(ROOT, "scripts", "flowed-e2e.py"), "utf8");
// WP1.9: the math journey cannot meet a half-finished lesson — it seeds its own
// day (queue, plan, T0 snapshots and the answered-today ledger all cleared)
// before the first turn. The old refusal of an inherited lesson went with the
// language scenarios it guarded.
check("and the test clears the day before judging",
  e2e.includes('archive(prof_dir / ".daily")') && e2e.includes("seed_math_review"));
check("no CEFR wording leaks into a math session",
  e2e.includes("CEFR_LEAK"));

// --- the lesson header says what the server knows --------------------------
// Seen live: "## Review 7/6 — high", exercise seven of six, in a lesson the
// server knew was on its fourth. The tutor counts its own turns and loses the
// thread across a detour.
check("a header past the end is brought back",
  alignLessonHeader("## Review 7/6 — high", 3, 6) === "## Review 4/6 — high",
  alignLessonHeader("## Review 7/6 — high", 3, 6));
check("a wrong total is corrected", alignLessonHeader("## Review 3/3", 2, 6) === "## Review 3/6");
check("with no plan it is left alone", alignLessonHeader("## Review 7/6", 3, 0) === "## Review 7/6");
check("only the lesson's own headers are touched",
  alignLessonHeader("## Word 4/10", 2, 6) === "## Word 4/10");
check("the server applies it inside the lesson only",
  fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8")
    .includes('this.currentCommand.get(sessionId) !== "math-review"'));
check("a review item that is not a fact is not a card",
  fs.readFileSync(path.join(ROOT, "skills", "math-vocab", "SKILL.md"), "utf8")
    .includes("A facts card needs one right answer"));
// WP1.9: on the bank path this is server behaviour, not rig bookkeeping —
// pressing Review again with a card on screen re-shows THAT card instead of
// skipping it (the `still && !answering` branch in tryBankReviewTurn).
check("and coming back to an unanswered exercise is not a repetition",
  ag2.includes("still && !answering && still.item"));

// --- a vocabulary card is an exercise too ----------------------------------
// Verbatim from a Vocabulary practice in which not one card was fingerprinted,
// so the already-asked list stayed empty and a repeat was indistinguishable
// from a new word.
const CARD = `## Word 3/10

**English:** apple

**Context:** What is the correct article for the word "apple"?

**What does it mean in català?**

**Type your answer:**`;
check("the card's term is what gets recorded",
  exerciseFingerprints(CARD).includes("apple"), exerciseFingerprints(CARD));
check("and the context line is not mistaken for it",
  !exerciseFingerprints(CARD).some((f) => f.includes("correct article")), exerciseFingerprints(CARD));
check("structure labels are never exercises",
  exerciseFingerprints("**Type:** vocabulary\n**Score: 2/10**\n**Last reviewed:** 3 days ago").length === 0);
check("a graded reply still fingerprints its exercise, not its feedback",
  exerciseFingerprints(`**Correct version:**\n"house"\n\n**Score: 2/10** 🔴\n\n## Review 3/6\n\n**Exercise:**\nWhat is the plural of "child"?`)
    .includes("child"));

const ag3 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
check("guard events land in the profile, not only in /tmp",
  ag3.includes("guards.jsonl") && ag3.includes("private logGuard"));

// --- the four uses that were only ever listed ------------------------------
const e2eSrc = fs.readFileSync(path.join(ROOT, "scripts", "flowed-e2e.py"), "utf8");
// WP1.9: on the bank path "stays finished" is enforced by the server itself —
// pressing Review on a finished day returns the fixed closing, never a new
// exercise (the `lesson.total > 0 && lesson.pending <= 0` branch). The rig's
// own guard is that a card answered right never comes back inside the lesson.
check("a finished lesson has to stay finished",
  ag2.includes("lesson.total > 0 && lesson.pending <= 0"));
check("and inside the rig, nothing answered right comes back",
  e2eSrc.includes("cap exercici contestat bé no torna dins la lliçó"));
check("and point at the buttons", e2eSrc.includes("l'orienta cap als botons"));
check("yesterday is checkable without waiting a day",
  fs.existsSync(path.join(ROOT, "scripts", "flowed-advance-day.py")));
check("what she knew does not come back",
  e2eSrc.includes("el que va encertar ahir (i ja sabia) no torna avui"));
check("what she missed does", e2eSrc.includes("el que va fallar ahir torna avui"));
const adv = fs.readFileSync(path.join(ROOT, "scripts", "flowed-advance-day.py"), "utf8");
check("and a real learner's dates are never rewritten",
  adv.includes("només en perfils de proves"));

// --- the server dispenses the queue, it does not hand it over -------------
//
// Measured on a real profile after a full lesson: 0 of 15 records carried an
// item_id. The tool that would have carried one is never called, and a record
// derived from the text cannot invent one — a wrong id advances the wrong
// item's schedule, in silence. So the server takes the top of the queue
// itself: it knows which item the answer was for because it chose it.
const SR = { items: {
  capitalization_English: { due_date: "2026-09-01", content: "English", answer: "English" },
  spelling_because: { due_date: "2026-09-02", content: "because" },
  later_one: { due_date: "2027-01-01", content: "nope" },
} };
check("it takes the oldest due item first",
  nextDueItem(SR, "2026-09-19")?.id === "capitalization_English");
check("and moves on once one is used",
  nextDueItem(SR, "2026-09-19", ["capitalization_English"])?.id === "spelling_because");
check("an item due later is not touched",
  nextDueItem(SR, "2026-09-19", ["capitalization_English", "spelling_because"]) === null);
check("an empty queue assigns nothing", nextDueItem({ items: {} }, "2026-09-19") === null);

const assignedNote = lessonNote(
  { total: 6, done: 2, pending: 4, due: 2, slot: null, material: 3 }, [], null,
  nextDueItem(SR, "2026-09-19"));
check("the note names the item", assignedNote.includes('reviews this item: "English"'));
check("and hands the teaching back to the tutor",
  assignedNote.includes("the wording, the level and the form are yours"));
check("no assignment, no sentence",
  !lessonNote({ total: 6, done: 2, pending: 4, due: 0, slot: null, material: 3 }, [], null)
    .includes("reviews this item"));

const ag4 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
check("the answer is credited to the PREVIOUS assignment",
  ag4.includes("this.gradingItem.set(sessionId, prev)"));
check("an id is still checked against the queue before it is written",
  ag4.includes("private itemExists") && ag4.includes("item && known ? { item_id"));
check("and the queue is not handed out twice in a session",
  ag4.includes("this.usedItems.set(sessionId"));
// WP1.9: pacingNote pre-assigns a due item (model path) into usedItems before
// tryBankReviewTurn runs. On the bank path that item is never served, so leaving
// it in the used list made review-pick skip the FIRST due item of every lesson
// and fill it with weak picks. The bank review must drop the model-path pick.
check("the bank review drops the model-path pick from the used list",
  ag4.includes("const modelPick = this.assignedItem.get(sessionId)?.id") &&
  ag4.includes(".filter((id) => id !== modelPick)"));

// --- a repeat has to be a repeat -------------------------------------------
// The first --repeat 3 gave one usable run, one on a lesson that run 1 had
// already finished, and one that refused to start. A lesson eats the day and
// the queue; if that is not put back, the runs are three different experiments.
const e2eB = fs.readFileSync(path.join(ROOT, "scripts", "flowed-e2e.py"), "utf8");
check("the profile is captured before the first run", e2eB.includes("def snapshot(prof_dir"));
check("and put back between runs", e2eB.includes("restore(prof_dir, snap)"));
check("restoring a real learner's profile is refused",
  e2eB.includes("restaurar només en perfils de proves"));
check("an aborted run does not throw away the good ones",
  e2eB.includes("resumeixo les") && e2eB.includes("break"));
// Not "unfinished" — UNTOUCHED. Run 2 of the first --repeat 3 finished run 1's
// lesson and reported it as its own; only run 3 refused, and only because by
// then the lesson was full. WP1.9: the math journey cannot inherit a lesson —
// seed_math_review clears the plan, the T0 snapshots and the answered-today
// ledger before the first turn, which is the same protection from the source.
check("a lesson already under way cannot be inherited",
  e2eB.includes("def seed_math_review") && e2eB.includes('archive(prof_dir / ".update-state")'));
check("and --reset cannot quietly eat the starting point",
  e2eB.includes("--reset i --repeat no es combinen"));
check("each run of a repeat reports its own result",
  e2eB.includes("bé\"") || e2eB.includes("} bé"));

// --- trailing punctuation is not a different question ----------------------
// Both of these sat in a real plan file, counted as two exercises, so the guard
// saw no repeat: the punctuation was stripped BEFORE the trim, and one trailing
// space was enough to keep the question mark.
check("a trailing question mark and a space collapse",
  normalizeExercise("What is the english word for perquè? ") ===
  normalizeExercise("What is the english word for perquè"),
  normalizeExercise("What is the english word for perquè? "));
check("and so does bold with trailing space",
  normalizeExercise("**What is the english word for un?**  ") === "what is the english word for un");

// --- the sweep writes its results down --------------------------------------
const sweep = fs.readFileSync(path.join(ROOT, "scripts", "flowed-sweep.py"), "utf8");
check("a setting is restarted into, or it was never tested",
  sweep.includes("--stop") && sweep.includes("--app"));
check("the config is put back whatever happens", sweep.includes("finally:"));
check("and the numbers land in a csv", sweep.includes("summary.csv"));
check("a real profile is refused", sweep.includes("només en perfils de proves"));

// --- the guard must not become the problem ---------------------------------
//
// Making the already-asked list global turned a bare term into a cross-practice
// ban: the Lesson spelling "because" stopped Vocabulary from having a card for
// "because", which is a different exercise about the same word. Nine rewrites
// in three runs — and every rewrite is a chance to lose the correction, which is
// exactly what happened to a third of the replies.
const cross = { inLesson: false, pending: 0,
                coveredToday: ["because", "what is the correct spelling of because"],
                askedHere: [] as string[], graded: true, closing: false };
check("a word she got right in another practice is a repeat too",
  turnGuard({ ...cross, asked: ["because"] }) !== null);
check("the same word again in the SAME practice is",
  turnGuard({ ...cross, askedHere: ["because"], asked: ["because"] }) !== null);
check("a whole question repeated anywhere is",
  turnGuard({ ...cross, asked: ["what is the correct spelling of because"] }) !== null);
check("and something new passes", turnGuard({ ...cross, asked: ["grape"] }) === null);

const ag5 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
check("a rewrite that loses the correction is thrown away",
  ag5.includes("the rewrite lost the feedback") && ag5.includes("lostVersion || lostMarker"));
check("each practice remembers what IT asked",
  ag5.includes("private askedByPractice"));

// --- one definition of "graded", not three ---------------------------------
// The counter moved on a bare "7/10", the derived record refused to be written
// without the literal word "Score", and the test counted it as graded: five
// records for eight graded answers, and the difference vanished silently.
for (const t of ["**Score: 2/10** 🔴", "You got 7/10 on that one.", "Nice try — 3/10."]) {
  check(`the counter and the record agree on ${JSON.stringify(t.slice(0, 18))}`,
    countGradedInText([t]) === 1 && parseFeedback(t) !== null);
}
check("and a percentage is not a score", parseFeedback("**Accuracy:** 67%") === null);
check("nor is a reply with no number at all", parseFeedback("Nice work!") === null);

const e2eC = fs.readFileSync(path.join(ROOT, "scripts", "flowed-e2e.py"), "utf8");
check("a repeat's summary shows why, not only how often",
  e2eC.includes("for d in dict.fromkeys"));

// --- the sweep records whether the run destroyed the profile ---------------
// A T0 keyed on a recycled session number rolled a real profile from twelve
// spaced-repetition items back to two, and nothing failed while it happened.
const sw = fs.readFileSync(path.join(ROOT, "scripts", "flowed-sweep.py"), "utf8");
check("the queue is counted before and after each run", sw.includes("def profile_state"));
check("and a shrinking queue is called out", sw.includes("la cua ha PERDUT"));
check("the numbers reach the csv", sw.includes('"items_before"') && sw.includes('"items_after"'));
const udb = fs.readFileSync(path.join(ROOT, "hooks", "update-db.py"), "utf8");
check("a T0 belongs to one session on one day", udb.includes('f"{session_id}@{day}"'));
check("with no undated fallback", udb.includes("A snapshot from another day is not"));
const seedSrc = fs.readFileSync(path.join(ROOT, "scripts", "flowed-seed.py"), "utf8");
check("and seeding does not leave one behind", seedSrc.includes('".update-state"'));

// --- the battery is the same every time ------------------------------------
const bench = fs.readFileSync(path.join(ROOT, "scripts", "flowed-bench.sh"), "utf8");
check("the baseline comes first, or the rest means nothing",
  bench.indexOf('"base:"') < bench.indexOf("temp06"));
check("temperature and the penalties are tried apart before together",
  bench.includes("temp06:") && bench.includes("penal:") && bench.includes("totes:"));
check("and it refuses a real learner's profile",
  bench.includes("només corre en perfils de proves"));
check("the sweep compares check by check, not just totals",
  sw.includes("què canvia, comprovació per comprovació"));

// --- a fingerprint names the subject, not the wrapper ----------------------
//
// The guard fired twenty-seven times in thirty-three turns and rewrote every
// one. What it was blocking, from a real profile: six article drills — apple,
// house, book, university, hour, egg — whose sentences differ by one word in
// eleven, and the generic instruction they all carry. Six different exercises
// read as six repetitions of one.
check("the quoted subject is the exercise",
  normalizeExercise('What is the correct article to use before the word "apple"?') === "apple");
check("so two drills of the same shape are two exercises",
  normalizeExercise('...before the word "apple"?') !==
  normalizeExercise('...before the word "house"?'));
check("a bare instruction identifies nothing and is not recorded",
  normalizeExercise("Choose the correct article for the sentence.") === "");
check("nor is the old offender", normalizeExercise("Rewrite this sentence correctly.") === "");
check("a sentence with no quotes is still itself",
  normalizeExercise("My sister runs today") === "my sister runs today");
check("and an empty fingerprint never reaches the list",
  exerciseFingerprints("**Exercise:**\nRewrite this sentence correctly.").length === 0,
  exerciseFingerprints("**Exercise:**\nRewrite this sentence correctly."));




{
  const ag3 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  const cmd = ag3.slice(ag3.indexOf("this.answerInFront.set(sessionId, false);"));
  check("a button forgets the previous practice's exercise",
    cmd.slice(0, 900).includes("this.lastAsked.delete(sessionId)"));
}

// What "already asked" means: what she answered CORRECTLY. Shown-and-left, and
// answered-wrong, may come back.
{
  check("the score is read from the feedback line", scoreOfReply("Well done!\n**Score: 9/10** 🟢") === 9);
  check("or from a bare 'n/10'", scoreOfReply("You got 10/10 today") === 10);
  check("a heading 'Word 9/10' is progress, not a grade",
    scoreOfReply("## Word 9/10\n**Català:** casa") === null, scoreOfReply("## Word 9/10"));
  check("feedback above a heading still gives its score",
    scoreOfReply("✅ Perfect!\n**Score: 10/10** ✅\n\n## Word 9/10\n**Català:** casa") === 10);
  check("known starts at 8", KNOWN_SCORE === 8);
  const ag4 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("covered grows on a known answer, not on display",
    ag4.includes("score >= KNOWN_SCORE") && !ag4.includes("for (const label of asked) if (!here.includes(label))"));
  check("and the guard counts the exercise this reply is grading as known",
    ag4.includes("...justKnown"));
}

// WP1.9: `writingLengthNote` (the A1..C2 email/postcard table) is deleted — it
// returned null for every m-level, and the length of a math reasoning task is
// the math-writing skill's own table. What must NOT come back:
{
  const pc = fs.readFileSync(path.join(ROOT, "server", "src", "pacing.ts"), "utf8");
  const ag5 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("no CEFR writing table in the server",
    !pc.includes("export function writingLengthNote") && !ag5.includes("writingLengthNote("));
  check("the stall warning is the Lesson's", ag5.includes('turns === 4 && this.currentCommand.get(sessionId) === "math-review"'));
}

{
  const ag6 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("a leaked </think> is removed before the learner sees the text",
    ag6.includes("<think>[\\s\\S]*?<\\/think>") && ag6.includes("<\\/?think>"));
}

// An error the learner made is tested by an exercise she can fail the same way.
{
  const sr = { items: {
    cap: { type: "error_pattern", content: "I speak English on Mondays", answer: "I speak English on Mondays",
           learner_wrote: "i speak english on mondays", due_date: "2026-09-13" },
    mat: { type: "vocabulary", content: "matí", answer: "morning", learner_wrote: "mornint", due_date: "2026-09-13" },
  } };
  const cap = nextDueItem(sr, "2026-09-13", []);
  check("an error item carries what she wrote", cap?.wrong === "i speak english on mondays", cap);
  const note = lessonNote(
    { total: 6, done: 1, pending: 5, due: 5, slot: null, material: 0, level: "A2" },
    [], null, cap
  );
  check("the note asks for an exercise she can fail the same way",
    note.includes('Her own mistake was "i speak english on mondays"') && note.includes("fill-in-the-blank"), note);
  const mat = nextDueItem(sr, "2026-09-13", ["cap"]);
  const noteV = lessonNote(
    { total: 6, done: 1, pending: 5, due: 5, slot: null, material: 0, level: "A2" },
    [], null, mat
  );
  check("a vocabulary item does not get that instruction", !noteV.includes("Her own mistake"), noteV);
}

// Writing has a fingerprint: the server knows an answer is waiting.
{
  const fp = exerciseFingerprints(
    "## ✍️ Writing Exercise\n\n**Scenario:** You are writing a short note to a friend.\n\n**Task:** Write a short note.\n");
  check("a Writing scenario is fingerprinted", fp.length === 1 && fp[0]!.startsWith("you are writing a short note"), fp);
  check("so a reply that ignores the answer and sets a new scenario is sent back",
    Boolean(turnGuard({ inLesson: false, pending: 0, coveredToday: [], asked: ["you are writing"],
      graded: false, closing: false, answering: "you are writing a short note to a friend" })));
}

// The closing reply has to grade the last answer (days 083631, temp06 day 3).
{
  const st = { inLesson: true, pending: 0, coveredToday: [] as string[], asked: [] as string[], graded: false, closing: true,
               grading: { content: "finestra", answer: "window" }, answering: "finestra", answerText: "window",
               replyText: "## 🎉 Review Session Complete!\n\n**Reviewed:** 2" };
  check("a closing reply that does not grade the last answer is sent back",
    (turnGuard(st) ?? "").includes("does not grade it"));
  check("not when it grades", turnGuard({ ...st, graded: true }) === null);
  check("not for a message after the lesson (nothing on screen)", turnGuard({ ...st, grading: null }) === null);
}

// A subject in italics is still the subject (days 083631, A2 profile: «*finestra*»).
{
  const card = (q: string) => `## Review 2/2 — high\n\n**Type:** vocabulary  \n**Last reviewed:** 0 days ago\n\n${q}\n\n**Type your answer:**`;
  check("an italic subject fingerprints", JSON.stringify(exerciseFingerprints(card("What is the English word for *finestra*?  "))) === '["finestra"]');
  check("an italic field of the card is not a subject", exerciseFingerprints(card("*Last reviewed: 0 days ago*")).length === 0);
}

// The feedback has to be about the item she answered (days 073725, totes: «table» → "an apple").
{
  const item = { content: "cuina", answer: "kitchen" };
  const reply = (fb: string, q = 'What is the English word for "llibre"?') =>
    `${fb}\n\n**Score: 2/10** 🔴\n\n## Review 5/5 — medium\n\n${q}\n\n**Type your answer:**`;
  const good = reply('❌ Close! "cuina" is "kitchen", not "table".\n\n**Correct version:**\n"kitchen"');
  const bad = reply('❌ Close! The correct form is "an apple", not "a apple".\n\n**Correct version:**\n"an apple"');
  check("feedback about the answered item passes", feedbackFollowsGrading(item, good));
  check("feedback about another item does not", !feedbackFollowsGrading(item, bad));
  check("no item, no judgement", feedbackFollowsGrading(null, bad));
  check("no feedback in the reply, no judgement", feedbackFollowsGrading(item, "## Word 3/10\n\nWhat does this mean?"));
  check("a sentence item is judged on its content words",
    feedbackFollowsGrading({ content: "I eat an apple every day", answer: "I eat an apple every day" },
      reply('❌ Almost.\n\n**Correct version:**\n"I eat an apple every day."')));
  const st = { inLesson: true, pending: 1, coveredToday: [] as string[], asked: ["llibre"], graded: true, closing: false,
               grading: item, answering: "cuina", answerText: "table", replyText: bad };
  check("the guard sends the tutor back to the answer she gave",
    (turnGuard(st) ?? "").includes('answers the exercise on "cuina"'));
  check("and that is a whole-turn rewrite, not an exercise-only splice", !isExerciseGuard(turnGuard(st) ?? ""));
  check("not when the feedback is about the item", turnGuard({ ...st, replyText: good }) === null);
  const ag = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("the server passes the item on screen and the answer",
    ag.includes("this.gradingItem.get(sessionId) ?? null") && ag.includes("answerText: this.lastAnswer.get(sessionId)"));
}

// The reply has to ask about the item the server assigned (days 073725).
{
  const item = { content: "escola", answer: "school" };
  const card = (q: string) => `❌ Close!\n\n**Correct version:**\n"x"\n\n**Score: 2/10** 🔴\n\n## Review 3/6 — high\n\n${q}\n\n**Type your answer:**`;
  check("asking the assigned word is following it", followsAssigned(item, card('What is the English word for "escola"?')));
  check("the other direction counts too", followsAssigned(item, card('What does "school" mean in Catalan?')));
  check("asking another word from the queue does not", !followsAssigned(item, card('What is the English word for "matí"?')));
  check("a sentence built from the item follows it",
    followsAssigned({ content: "She goes to school", answer: "She goes to school" }, card('Correct this sentence: "She go to school."')));
  check("no item, no judgement", followsAssigned(null, card("anything")));
  check("no exercise heading, no judgement", followsAssigned(item, "Well done!"));
  const st = { inLesson: true, pending: 3, coveredToday: [] as string[], asked: ["matí"], graded: true, closing: false,
               assigned: item, replyText: card('What is the English word for "matí"?') };
  check("the guard names the item the reply should have asked",
    (turnGuard(st) ?? "").includes('must review "escola"'));
  check("not when the reply follows it", turnGuard({ ...st, asked: ["escola"], replyText: card('What is the English word for "escola"?') }) === null);
  check("it is an exercise guard: feedback stays, only the exercise is replaced", isExerciseGuard(turnGuard(st) ?? ""));
  const ag = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("the server passes the assigned item to the guard", ag.includes("assigned: inLesson ? this.assignedItem.get(sessionId)"));
}

// A button turn that grades an answer nobody gave (days 223056, day 3).
{
  const st = { inLesson: true, pending: 2, coveredToday: [] as string[], asked: ["finestra"],
               graded: true, closing: false, answering: null, buttonTurn: true,
               replyText: '❌ Close! matí means "morning", not "table".\n\n**Correct version:**\n"morning"\n\n**Score: 2/10**' };
  check("a button turn that grades is sent back to open plainly",
    (turnGuard(st) ?? "").includes("not answered anything"));
  check("not when an answer is in front", turnGuard({ ...st, buttonTurn: false }) === null);
  check("not when it only opens (no grading)", turnGuard({ ...st, graded: false }) === null);
  check("not this note when it closes the session", !(turnGuard({ ...st, closing: true }) ?? "").includes("not answered anything"));
}

// Vocabulary: a graded reply must ask the next card.
{
  const st = { inLesson: false, pending: 0, coveredToday: [] as string[], asked: [] as string[],
               graded: true, closing: false, answering: "casa", oneAtATime: true };
  check("Vocabulary graded with no next card is sent back",
    (turnGuard(st) ?? "").includes("asks nothing"));
  check("not when it is not one-at-a-time (Writing)", turnGuard({ ...st, oneAtATime: false }) === null);
  check("not when it closes the session", turnGuard({ ...st, closing: true }) === null);
  check("not when there was no answer (a button)", turnGuard({ ...st, answering: null }) === null);
  check("not when it does ask", turnGuard({ ...st, asked: ["gat"] }) === null);
  const ag8 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("the server passes the one-at-a-time flag",
    ag8.includes('oneAtATime: this.currentCommand.get(sessionId) === "math-vocab"'));
}

{
  const ag9 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("the rewrite is told which exercises are off limits",
    ag9.includes("const retryNote =") &&
    ag9.includes("she already got them right today") &&
    ag9.includes('content: retryNote'));
  // 224927: «llibre» came back because the off-limits list kept only the last 12 of a longer day.
  check("the off-limits list is not cut to the last dozen", !ag9.includes("slice(-12)") && ag9.includes("slice(-40)"));
  check("the Lesson note says there is no second try",
    lessonNote(frozen, IONA_COVERED, "my sister runs today").includes("No second try in the Lesson"));
}

{
  const raw = [
    "# topics for Nes — edit freely",
    "",
    "present perfect",
    "- there is / there are",
    "2. Food and restaurants",
    "  * asking for directions  ",
    "Present Perfect",
    "comparatives: taller than, the tallest",
  ].join("\n");
  const t = parseTopics(raw);
  check("comments, blanks, bullets and numbers are dropped; duplicates too",
    JSON.stringify(t) === JSON.stringify([
      "present perfect", "there is / there are", "Food and restaurants",
      "asking for directions", "comparatives: taller than, the tallest",
    ]), JSON.stringify(t));
  check("no file, no topics", parseTopics(null).length === 0 && parseTopics("").length === 0);
  check("windows line endings", parseTopics("a\r\nb\r\n").length === 2);
  check("a pasted syllabus is capped", parseTopics(Array.from({ length: 80 }, (_, i) => `topic ${i}`).join("\n")).length === 30);
  check("a long line is cut", parseTopics("x".repeat(500))[0]!.length === 160);
  check("two topics per turn, wrapping", JSON.stringify(pickTopics(["a", "b", "c"], 2)) === '["c","a"]');
  check("every topic gets a turn", new Set([0, 1, 2, 3, 4].flatMap((i) => pickTopics(["a", "b", "c", "d", "e"], i * 2))).size === 5);
  check("a negative seed does not crash", pickTopics(["a", "b"], -3).length === 2);
  check("one topic, one pick", pickTopics(["a"], 7).length === 1);
  check("no topics, no note", topicsNote([], 0, "A2") === null);
  const n = topicsNote(["present perfect", "food"], 0, "A2") ?? "";
  check("the note names the topics and the level",
    n.includes('"present perfect"') && n.includes('"food"') && n.includes("at A2"), n);
  check("the queue always wins", n.includes("ALWAYS comes first") && n.includes("never") && n.includes("replaced by a topic"), n);
  check("a topic that does not fit is dropped, and the note is silent",
    n.includes("ignore it rather than force it") && n.includes("say nothing about this note"), n);
  const ag = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("the server reads topics.txt each turn and only where the tutor picks the subject",
    ag.includes('"topics.txt"') && ag.includes("!assigned ? this.topicsNoteFor") &&   // (drills removed, fase 5)
    ag.includes('"math-speaking"'));
}

{
  // Verbatim from sweep-20260920-214531 (A1 journey), answer 1.
  const first =
    '✅ Perfect! "Morning" is the correct English word for "matí".\n\n**Correct version:**\n"morning"\n\n' +
    "**Score: 10/10** ✅ Well done! You got it right on the first try. 🎉";
  const rewrite =
    '✅ Perfect! "Window" is the correct English word for "finestra".\n\n**Correct version:**\n"window"\n\n' +
    "**Score: 10/10** ✅ Well done!\n\n## Review 2/6 — high\n**Type:** error_pattern\n" +
    'Complete the sentence correctly: "She ___ to school."\n**Type your answer:**\n---';
  const only = exerciseOnlyOf(rewrite) ?? "";
  check("a rewrite that graded again is cut at its exercise",
    only.startsWith("## Review 2/6") && !only.includes("Window") && !only.includes("Score"), only);
  const merged = spliceFb(first, only) ?? "";
  check("the first reply's feedback survives, the rewrite's does not",
    merged.includes('"Morning"') && merged.includes("She ___ to school") && !merged.includes("Window"), merged);
  {
    // Verbatim from sweep-20260920-223716 (A1 journey): the score line carries its own retry question.
    const f =
      '❌ Close! Let\'s fix the sentence.\n\n**Corrections:**\n- ❌ "dog" → **"table"** (vocabulary)\n\n**Correct version:**\n"table"\n\n' +
      '**Score: 2/10** 🔴 Let\'s try again. What is the English word for "taula"?';
    const m = spliceFb(f, "## Word 3/10\n\n**Català:** cotxe\n\n**What does it mean in English?**") ?? "";
    check("the retry question on the score line is not kept next to the new exercise",
      m.includes("**Score: 2/10**") && !m.includes("taula") && m.includes("cotxe"), m);
    const g = spliceFb('**Correct version:**\n"x"\n**Score: 2/10**', "## Word 3/10\n**Català:** cotxe") ?? "";
    check("a bare score line is left alone", g.includes("**Score: 2/10**") && g.includes("cotxe"), g);
  }
  check("a bare exercise is returned whole",
    exerciseOnlyOf('## Word 6/10\n\n**Català:** cotxe\n\n**What does it mean in English?**') !== null);
  check("nothing to ask, nothing returned", exerciseOnlyOf("Well done!") === null && exerciseOnlyOf("") === null);
  check("feedback with no heading has no exercise to take",
    exerciseOnlyOf("**Correct version:**\n\"x\"\n**Score: 8/10**") === null);
  check("guards about the exercise are recognised",
    isExerciseGuard("Your reply corrects the answer but asks nothing, so the learner is left with a blank screen.") &&
    isExerciseGuard('You have already asked "llibre" today. Write the turn again with a DIFFERENT exercise') &&
    !isExerciseGuard('The learner answered "x" and your reply does not grade it.') &&
    !isExerciseGuard("There is nothing due for review today"));
  const ag10 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("the server splices for exercise guards and tells the model to write only the exercise",
    ag10.includes("const exerciseOnly = isExerciseGuard(note)") &&
    ag10.includes("write ONLY the next exercise") &&
    ag10.includes("exerciseOnlyOf(better)") && ag10.includes("if (!spliced && (lostVersion || lostMarker))"));
}

{
  // Verbatim from sweep-20260920-222217 (A1 profile): no "**Exercise:**" label.
  const intro =
    "# 🔄 Today's Spaced Repetition Review\nHello, Test! Time to review items.\n**Items Due Today:** 6\n" +
    "**Estimated Time:** ~12 min\nWhy review? Spaced repetition prevents forgetting.\n" +
    "**Ready? Let's start!** 💪\n\n## Review 1/6 — high\n**Type:** vocabulary\n" +
    '**Last reviewed:** 1 day ago\n**Current mastery:** ⭐\nWhat is the English word for "matí"?\n' +
    "**Type your answer:**\n---";
  const fp1 = exerciseFingerprints(intro);
  check("the lesson opening fingerprints the first exercise, not the estimated time",
    JSON.stringify(fp1) === '["matí"]', JSON.stringify(fp1));
  const card = (n: number, line: string) =>
    `## Review ${n}/6 — medium\n**Type:** error_pattern\n**Last reviewed:** 1 day ago\n` +
    `**Current mastery:** ⭐\n${line}\n**Type your answer:**\n---`;
  check("an unlabeled sentence card is fingerprinted by its quoted sentence",
    JSON.stringify(exerciseFingerprints(card(3, 'Correct this sentence: "She go to school".'))) ===
      '["she go to school"]');
  check("a fill-in card too",
    JSON.stringify(exerciseFingerprints(card(3, 'Complete the sentence correctly: "She ___ to school."'))) ===
      '["she to school"]');
  check("a card with no quoted subject still fingerprints to nothing (an instruction is not an exercise)",
    exerciseFingerprints(card(3, "Correct the sentence below.")).length === 0);
  check("the labeled shape is not doubled",
    JSON.stringify(exerciseFingerprints('## Review 1/6 — high\n**Type:** vocabulary\n**Exercise:** What is the English word for "matí"?\n**Type your answer:**')) === '["matí"]');
  check("feedback followed by the next card gives the next card only",
    JSON.stringify(exerciseFingerprints(
      '✅ Perfect! "Morning" is the correct English word for "matí".\n**Correct version:**\n"morning"\n**Score: 10/10**\n\n' +
      card(2, 'What is the English word for "finestra"?'))) === '["finestra"]');
  // A card titled only "Today's Spaced Repetition Review" (no "Review N/M" heading)
  // and a two-letter subject. Measured 2026-09-21: both fingerprinted to nothing.
  const titled = (line: string) =>
    "# 🔄 Today's Spaced Repetition Review\n\n**Type:** vocabulary  \n**Last reviewed:** 0 days ago  \n" +
    `**Current mastery:** ⭐\n\n${line}\n\n**Type your answer:**\n\n---`;
  check("a card with only the title heading is fingerprinted",
    JSON.stringify(exerciseFingerprints(titled('What is the English word for "matí"?'))) === '["matí"]',
    JSON.stringify(exerciseFingerprints(titled('What is the English word for "matí"?'))));
  check("a two-letter quoted subject is an exercise",
    JSON.stringify(exerciseFingerprints(card(3, 'What is the English word for "pa"?'))) === '["pa"]');
  check("a two-letter subject after feedback, in a titled card",
    JSON.stringify(exerciseFingerprints(
      '❌ Almost.\n**Correct version:**\n"water"\n**Score: 2/10** 🔴\n\n' +
      titled('What is the English word for "pa"?'))) === '["pa"]');
  check("the lesson opening with a title and a numbered card still gives the card only",
    JSON.stringify(exerciseFingerprints(intro)) === '["matí"]');
  // Phase 0 of the learner path: the recorded answers are tagged after each persistence.
  const agentSrc0 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  const autoPersist = agentSrc0.slice(agentSrc0.indexOf("private async runAutoPersistence"));
  check("the learner path is rebuilt after the session is accumulated, only through --auto",
    autoPersist.indexOf("accumulate-session.py") < autoPersist.indexOf("curriculum.py") &&
      autoPersist.includes('"rebuild", "--auto", "--quiet"'));
  check("and a failure there cannot break the persistence (its own try/catch)",
    /try \{\s*const cp = Bun\.spawn\(\s*\["python3", path\.join\(root, "hooks", "curriculum\.py"\)[\s\S]*?\} catch \{/.test(autoPersist));
  // "Answered but not graded": keep the exercise on screen, rewrite only the feedback.
  // Measured 2026-09-21 (days 185739): the whole-turn rewrite graded the NEXT card.
  const cardFor = (line: string) =>
    `## Review 3/6 — high\n\n**Type:** error_pattern\n**Last reviewed:** 0 days ago\n\n${line}\n\n**Type your answer:**`;
  const firstReply = `✅ Perfect! "She goes to school" is correct.\n\n${cardFor('Correct this sentence: "I wake up at seven yesterday".')}`;
  check("trailingExercise takes the card the reply ends with",
    (trailingExercise(firstReply) ?? "").startsWith("## Review 3/6") && !(trailingExercise(firstReply) ?? "").includes("Perfect"));
  check("and nothing when the reply asks nothing", trailingExercise("✅ Perfect!\n\n**Correct version:**\n\"morning\"\n**Score: 10/10**") === null);
  check("the not-graded note is a feedback guard; the closing one and the asks-nothing one are not",
    isFeedbackGuard('The learner answered "she go to school" and your reply does not grade it. Write the turn again: first the feedback on that answer (verdict, the correct version, the score), then the next exercise.') &&
      !isFeedbackGuard('The learner\'s message ("x") answers the last exercise, on "y", and your reply does not grade it. Write the turn again: first the feedback on that answer — the verdict, the correct version and the score — and then close the lesson.') &&
      !isFeedbackGuard("Your reply corrects the answer but asks nothing, so the learner is left with a blank screen."));
  const feedback = `✅ Perfect! "She goes to school" is correct.\n\n**Correct version:**\n"She goes to school."\n\n**Score: 10/10** ✅`;
  const merged = mergeFeedbackOnly(firstReply, feedback, { content: "She goes to school" });
  check("the rewrite's feedback goes in front of the first reply's exercise",
    !!merged && merged.startsWith("✅ Perfect!") && merged.includes("**Score: 10/10**") &&
      merged.includes('"I wake up at seven yesterday"') && merged.indexOf("Score") < merged.indexOf("## Review 3/6"), merged ?? "null");
  check("an exercise the rewrite added is cut off",
    (mergeFeedbackOnly(firstReply, `${feedback}\n\n${cardFor('Correct this sentence: "I eat an apple every day".')}`, null) ?? "").includes("apple") === false);
  check("no score in the rewrite: keep the first reply", mergeFeedbackOnly(firstReply, "✅ Perfect! It is correct.", null) === null);
  check("feedback about the next item (not the one answered): keep the first reply",
    mergeFeedbackOnly(firstReply,
      `❌ Close!\n\n**Correct version:**\n"I woke up at seven yesterday"\n\n**Score: 7/10** 🟡`, { content: "She goes to school" }) === null);
  check("a first reply with no exercise cannot be merged", mergeFeedbackOnly("✅ Perfect!", feedback, null) === null);
  const agentSrc1 = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  check("the guard uses the feedback-only rewrite for that note",
    agentSrc1.includes("isFeedbackGuard(note) && trailingExercise(text) !== null") &&
      agentSrc1.includes("mergeFeedbackOnly(text, better, gradingNow)"));
}

// --- Phase 2: the curriculum hands out the competence in free practice -----
{
  const comp = { id: "present_simple_vs_continuous", name: "Present simple vs continuous",
    can_do: "chooses between 'she works' and 'she is working'", signals: ["now", "at the moment", "every day", "usually"] };
  const ex = (line: string) => `✅ Perfect!\n\n**Correct version:**\n"x"\n**Score: 10/10** ✅\n\n## Exercise\n\n${line}\n\n**Type your answer:**`;
  check("an exercise with a signal follows the competence",
    followsCompetence(comp, ex("Complete: She ___ (read) a book right now.")));
  check("a multi-word signal counts, accents and case folded",
    followsCompetence(comp, ex("Complete: He ___ (sleep) AT THE MOMENT.")));
  check("an exercise about something else does not",
    !followsCompetence(comp, ex("Complete: I have two ___ (child).")));
  check("a signal is a whole word: 'known' is not 'now'",
    !followsCompetence(comp, ex("Complete: She has ___ (know) him.")));
  check("feedback is not judged: only the exercise the reply ends on",
    !followsCompetence({ ...comp, signals: ["Perfect"] }, ex("Complete: I have two ___ (child).")));
  check("an exercise headed with the competence's name follows it even if the gap hides every signal",
    followsCompetence({ id: "p", name: "Prepositions of time and place", signals: ["at", "on"] },
      ex("Complete: The party is ___ Saturday ___ 8.").replace("## Exercise", "## Exercise 5: Prepositions of Time and Place")));
  check("vocabulary, no signals, no competence and no exercise are all left alone",
    followsCompetence({ ...comp, vocab: true }, ex("x")) && followsCompetence({ ...comp, signals: [] }, ex("x")) &&
      followsCompetence(null, ex("x")) && followsCompetence(comp, "✅ Perfect!\n\n**Score: 10/10**"));
  const cg = { inLesson: false, pending: 0, coveredToday: [], asked: ["i have two"], graded: true, closing: false,
    competence: comp, replyText: ex("Complete: I have two ___ (child).") };
  const gnote = turnGuard(cg) ?? "";
  check("the guard names the competence and sends the tutor back",
    gnote.includes('must practice "Present simple vs continuous"') && gnote.includes("about that competence"), gnote);
  check("that guard rewrites only the exercise", isExerciseGuard(gnote));
  check("a reply that follows is left alone",
    turnGuard({ ...cg, asked: ["she read"], replyText: ex("Complete: She ___ (read) right now.") }) === null);
  check("closing is never sent back for it", turnGuard({ ...cg, closing: true }) === null);
  const ag = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  const tl = fs.readFileSync(path.join(ROOT, "server", "src", "tools.ts"), "utf8");
  check("agent asks hooks/curriculum.py next, only in Mix and Vocabulary",
    ag.includes('"hooks", "curriculum.py"') && ag.includes('"next", "--auto"') &&
      ag.includes('cmdNow === "math-learn" || cmdNow === "math-vocab"'));
  check("Vocabulary is only handed competences with words", ag.includes('args.push("--vocab")'));
  check("the competence note replaces the topics note",
    ag.includes("compNote ?? topics"));
  check("the guard state, the note log and the record all carry the competence",
    // compAtStart: the competence snapshotted before pacingNote() can reassign it mid-turn
    ag.includes("competence: inLesson ? null : compAtStart") &&
      ag.includes("const compAtStart = this.assignedCompetence.get(sessionId)") &&
      ag.includes("competence: comp ? { id: comp.id") && tl.includes("competency: opts.gradingCompetence(sid)") &&
      ag.includes("competency: this.recordCompetence(sessionId)"));
  check("the record is tagged only when the exercise was seen to follow it, and never for vocabulary",
    ag.includes("c && c.followed && !c.vocab"));
}


// --- the level test is run by the server, without the model ----------------------
{
  const src = fs.readFileSync(path.join(ROOT, "server", "src", "agent.ts"), "utf8");
  // Only checkpointTurn's own body: up to the next method, not to executeTurn —
  // the bank's methods now sit in between and mention executeTurn in comments.
  const start = src.indexOf("private async checkpointTurn");
  const next = src.slice(start + 10).search(/\n  (?:private|public|async) /);
  const body = src.slice(start, next < 0 ? undefined : start + 10 + next);
  check("level test: no model in the loop", body.length > 200 && !/runTurn|executeTurn|resolveModel\(agent, this\.models\)\s*;\s*const msg = .*runTurn/.test(body));
  check("level test: the button is answered before any command file is loaded",
    src.indexOf('commandName === "math-checkpoint"') > 0 &&
      src.indexOf('commandName === "math-checkpoint"') < src.indexOf("await loadCommand(commandName"));
  check("level test: the answers of a running test go to it, also after a restart",
    src.includes('this.checkpointTurn(sessionId, "answer", text)') && src.includes('cmd === undefined) && this.checkpointRunning()'));
  check("level test: a test of another day is not answered", src.includes("run.day ===") && src.includes("checkpoint-run.json"));
  check("level test: the CLI is the curriculum's", src.includes('"checkpoint", action, "--auto"'));
}

console.log(failures === 0 ? "lesson-note: all checks passed" : `lesson-note: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
