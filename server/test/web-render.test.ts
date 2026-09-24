// web/app.js rendering rules — run with:
//   node --experimental-strip-types server/test/web-render.test.ts
//
// Two rules that only ever break in front of the learner:
//
//  1. A MENU IS NOT AN EXERCISE. The tutor opens with a menu, offers one when
//     the review queue is empty, and closes with one. Each was being tagged
//     "✏️ Exercici" in the flow, which tells an eight-year-old to answer a list
//     of options.
//  2. NO SLASH COMMANDS REACH THE SCREEN. The learner has buttons and no
//     command line, so "try /fluent-vocab" is advice they cannot follow. The
//     prompts forbid it, but a 14B model improvises: the renderer is the only
//     guarantee.
//
// app.js is a browser script, not a module, so the functions under test are
// sliced out of the source and evaluated. Crude, but it tests the real code
// rather than a copy that can drift.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const src = fs.readFileSync(path.join(repo, "web", "app.js"), "utf8");

function slice(from: string, to: string): string {
  const a = src.indexOf(from);
  const b = src.indexOf(to);
  if (a === -1 || b === -1 || b <= a) {
    throw new Error(`could not slice web/app.js between ${JSON.stringify(from)} and ${JSON.stringify(to)} — did the file move?`);
  }
  return src.slice(a, b);
}

const menuBlock = slice("const SCORE_RE", "// The tutor bundles feedback + next question");
const cmdBlock = slice("const BUTTON_NAMES", "function renderTutorText");
const sayBlock = slice("const SAY_RE", "// Where a target-language sentence actually");
const quoteBlock = slice("const SPEAKABLE_LABEL_RE", "// The text of a block minus a leading");

const { isOpenExercise, looksLikeMenu } = new Function(
  `${menuBlock}; return { isOpenExercise, looksLikeMenu };`
)() as { isOpenExercise: (t: string) => boolean; looksLikeMenu: (t: string) => boolean };

const { humanizeCommands } = new Function(
  `${cmdBlock}; return { humanizeCommands };`
)() as { humanizeCommands: (t: string) => string };

// markSayable reads ttsReady and esc() from module scope; supply both.
const makeMarkSayable = (ttsReady: boolean) =>
  new Function(
    "ttsReady",
    `const esc = (x) => String(x ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
     ${sayBlock}; return markSayable;`
  )(ttsReady) as (t: string) => string;

const { quotedIn, SPEAKABLE_LABEL_RE } = new Function(
  `${quoteBlock}; return { quotedIn, SPEAKABLE_LABEL_RE };`
)() as { quotedIn: (t: string) => string; SPEAKABLE_LABEL_RE: RegExp };

const machineBlock = slice("const MACHINE_BLOCK_RE", "// The learner has buttons, not a command line");
const { stripMachineBlocks } = new Function(
  `${machineBlock}; return { stripMachineBlocks };`
)() as { stripMachineBlocks: (t: string) => string };

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

// --- a menu is not an exercise ---------------------------------------------

const NO_REVIEWS =
  "🎉 No reviews due today! Your spaced repetition is up to date.\n\n" +
  "Want to practice something new? Use the buttons at the top:\n" +
  "- 🎲 Surprise me! — adaptive mixed practice\n" +
  "- 📚 Vocabulary — learn new words\n" +
  "- 📊 Progress — see your stats";

check("the empty-queue message is a menu", looksLikeMenu(NO_REVIEWS));
check("and is never tagged as an exercise", isOpenExercise(NO_REVIEWS) === false);

check("the opening menu is a menu",
  isOpenExercise("Hello, Nes! What would you like to practice today?\n1. 📝 Writing\n2. 🗣️ Speaking") === false);
check("the closing menu is a menu",
  isOpenExercise("Use the buttons at the top (🎲 🔁 📚 📝 🗣️ 📖) to continue. What shall we do next?") === false);
check("the old numbered menu still counts",
  isOpenExercise("Type a number or skill name:") === false);
check("two button names alone are enough",
  looksLikeMenu("You could do 📚 Vocabulary or 📝 Writing now."));
check("one button name in passing is not a menu",
  looksLikeMenu("Nice — that is exactly the kind of sentence 📝 Writing drills.") === false);

// The other half: real exercises must survive the widened net.
check("a translation exercise is still an exercise",
  isOpenExercise("Translate into English: Ahir vaig anar al mercat.") === true);
check("a production prompt is still an exercise",
  isOpenExercise('How would you say "bon dia" in English?') === true);
check("a cloze is still an exercise",
  isOpenExercise("Fill in the blank: I ____ to school every day.") === true);
check("feedback with a score is not an open exercise",
  isOpenExercise("Good! Score: 8/10") === false);

// --- no slash commands reach the screen ------------------------------------

check("a bare command becomes its button",
  humanizeCommands("Try /fluent-vocab next.") === "Try **📚 Vocabulary** next.",
  humanizeCommands("Try /fluent-vocab next."));
check("a backticked command becomes its button",
  humanizeCommands("Run `/fluent-review` first.") === "Run **🔁 Review** first.",
  humanizeCommands("Run `/fluent-review` first."));
check("fluent-learn is the dice button",
  humanizeCommands("/fluent-learn").includes("Surprise me!"));
check("fluent-end is the finish button",
  humanizeCommands("/fluent-end").includes("End"), humanizeCommands("/fluent-end"));
check("setup points at the admin, not at a button",
  humanizeCommands("/fluent-setup").includes("administrador"));
check("every command in a list is rewritten",
  !humanizeCommands("- /fluent-learn\n- /fluent-vocab\n- /fluent-progress").includes("/fluent-"),
  humanizeCommands("- /fluent-learn\n- /fluent-vocab\n- /fluent-progress"));
check("the whole empty-queue message comes out clean",
  !humanizeCommands(
    "Try:\n- `/fluent-learn` — mixed\n- `/fluent-vocab` — words\n- `/fluent-progress` — stats"
  ).includes("/fluent-"));
check("an unknown command is left alone rather than mangled",
  humanizeCommands("/fluent-nonsense") === "/fluent-nonsense");
check("ordinary text is untouched",
  humanizeCommands("I am fluent in Catalan.") === "I am fluent in Catalan.");

// --- what may be read aloud -------------------------------------------------
// Only text we KNOW is in the target language. Putting a speaker on the whole
// exercise looks obvious and is wrong: "Translate into English: Ahir vaig anar
// al mercat" is Catalan, and an English voice reading it teaches the opposite
// of what the exercise is for. So the tutor marks it, and a forgotten marker
// costs a button — never a wrong-language reading.

{
  const withTts = makeMarkSayable(true);
  const noTts = makeMarkSayable(false);

  const out = withTts("Repeat after me: [[say]]Good morning[[/say]]");
  check("a marked sentence becomes a speakable span",
    out.includes('data-say="Good morning"') && out.includes("sayable"), out);
  check("the marker itself never reaches the learner", !out.includes("[[say]]"), out);

  check("with no voice installed the text survives plain",
    noTts("Repeat: [[say]]Good morning[[/say]]") === "Repeat: Good morning",
    noTts("Repeat: [[say]]Good morning[[/say]]"));
  check("and the marker is still stripped",
    !noTts("[[say]]x[[/say]]").includes("[["));

  const two = withTts("[[say]]One[[/say]] and [[say]]Two[[/say]]");
  check("several markers in one message all render",
    (two.match(/data-say=/g) || []).length === 2, two);

  check("text with no marker is untouched",
    withTts("Just feedback, nothing to hear.") === "Just feedback, nothing to hear.");
  check("an empty marker leaves nothing behind",
    withTts("a[[say]]   [[/say]]b") === "ab", withTts("a[[say]]   [[/say]]b"));
  check("an unclosed marker is left alone rather than eating the message",
    withTts("[[say]]oops").includes("[[say]]oops"));
  check("quotes in the sentence are escaped into the attribute",
    !withTts('[[say]]He said "hi"[[/say]]').includes('data-say="He said "'),
    withTts('[[say]]He said "hi"[[/say]]'));
  check("a runaway marker is not turned into a 5000-char button",
    withTts(`[[say]]${"x".repeat(5000)}[[/say]]`).includes("[[say]]"));
}

// --- the model answer, in the shape this tutor really writes -----------------
// Taken from a live speaking session. The canonical `**Correct version:**`
// label the code was first written against does not appear at all.

{
  const ALT = 'You could also say: "I had an appointment last Friday with my doctor."';
  check("a 'you could also say' line is speakable", SPEAKABLE_LABEL_RE.test(ALT));
  check("and the quote is what gets spoken, not the lead-in",
    quotedIn(ALT) === "I had an appointment last Friday with my doctor.", quotedIn(ALT));

  const RETYPE = 'Now type the correct version yourself:\n"I had an appointment last Friday"';
  check("the retype prompt is speakable", SPEAKABLE_LABEL_RE.test(RETYPE));
  check("its instruction text is never spoken",
    quotedIn(RETYPE) === "I had an appointment last Friday", quotedIn(RETYPE));

  check("the canonical label still works",
    SPEAKABLE_LABEL_RE.test('**Correct version:** "I have been waiting."'));
  check("and yields the sentence",
    quotedIn('**Correct version:** "I have been waiting."') === "I have been waiting.");

  check("the longest quote wins when there are several",
    quotedIn('You said "hi" but you could also say "Good morning to you"') === "Good morning to you");
  check("curly quotes count too",
    quotedIn("You could also say: \u201cGood evening\u201d") === "Good evening");

  check("an ordinary sentence is not a model answer",
    SPEAKABLE_LABEL_RE.test("Nice effort! Let's try again.") === false);
  check("a grammar note alone is not one either",
    SPEAKABLE_LABEL_RE.test('- 🟡 "I buy" → **"I bought"** (past tense)') === false);
  check("no quotes, nothing to speak", quotedIn("You could also say it differently") === "");
  check("an empty block does not throw", quotedIn("") === "");
}

// --- the learner never sees an internal id ---------------------------------------
{
  const CARD = `## Exercise 1: Spaced Review (High Priority)
**Item ID:** agreement_she_goes_to_school
**Sentence:** She go to school
**Question:** What is the correct form of the sentence?`;
  const out = stripMachineBlocks(CARD);
  check("the bolded Item ID line is gone", !/Item ID/i.test(out) && !out.includes("agreement_she"), out);
  check("the rest of the exercise stays",
    out.includes("**Sentence:** She go to school") && out.includes("**Question:**"));
  check("a plain 'Item ID: x' line goes too",
    !/Item ID/.test(stripMachineBlocks("Exercise 1\nItem ID: agreement_she_goes_to_school\nSentence: She go")));
  check("a sentence that merely mentions an item is left alone",
    stripMachineBlocks("Every item ID is private.") === "Every item ID is private.");
  check("the machine block is still stripped",
    stripMachineBlocks('Bé!\n```fluent:review_results\n[{"item_id":"x"}]\n```') === "Bé!");
}


// --- the learner's path: plain view for her, details folded for the teacher ---------
{
  const pathBlock = slice("// ---- the learner's path", "function openProgress");
  const { renderPath, renderPathMini, pathBarPct, renderCourseNotice, pathCheckpointOffer } = new Function(
    `const esc = (x) => String(x ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
     const shortDate = (d) => String(d || "—");
     const prettyId = (id) => String(id || "").replace(/_/g, " ");
     ${pathBlock}; return { renderPath, renderPathMini, pathBarPct, renderCourseNotice, pathCheckpointOffer };`
  )() as {
    renderCourseNotice: (n: unknown) => string;
    pathCheckpointOffer: (p: unknown) => { label: string } | null;
    renderPath: (p: unknown) => string;
    renderPathMini: (p: unknown) => { html: string; title: string } | null;
    pathBarPct: (it: unknown) => number;
  };
  const P = {
    available: true, language: "English", level: "A2", pct: 30.9, core_done: 0, core_total: 16,
    in_progress: 11, unseen: 5, mastered: 0, promotion: null, checkpoint: "pending", checkpoint_pending: 6,
    now: [{ id: "a", name: "Past simple" }], review: [{ id: "b", name: "Greetings <b>" }],
    sections: [{ name: "Gramàtica", items: [
      { id: "a", name: "Past simple", core: true, state: "practicing", label: "en pràctica", n: 5, need: 20, depth: "deep" },
      { id: "c", name: "Numbers", core: true, state: "consolidated", label: "consolidada", n: 12, need: 12, depth: "normal" },
      { id: "d", name: "Weather", core: false, state: "unseen", label: "per començar", n: 0, need: 12, depth: "light" },
    ] }],
    admin: { history: [{ day: "2026-09-14", pct: 5.2 }], eta_days: 31, alerts: ["Estancada: X"],
      rows: [{ name: "Past simple", state: "en pràctica", n: 5, need: 20, acc_all: 80, acc_recent: null, last_day: "2026-09-15", weight: 3, depth: "deep" }],
      checkpoints: [] },
  };
  const html = renderPath(P);
  check("path: nothing when there is no curriculum", renderPath({ available: false }) === "" && renderPath(null) === "");
  check("path: bar and % for the learner", html.includes("31%") && html.includes("width:30.9%"), html.slice(0, 200));
  check("path: what she is working on and what to review", html.includes("Ara treballes") && html.includes("Per repassar"));
  check("path: names are escaped", html.includes("Greetings &lt;b&gt;") && !html.includes("<b>"));
  check("path: competences by section with state in words", html.includes("Gramàtica") && html.includes("en pràctica") && html.includes("consolidada"));
  check("path: a non-core competence is marked extra", html.includes("extra"));
  check("path: teacher block is folded and holds the alerts",
    /<details class="path-admin">/.test(html) && html.indexOf("<details") < html.indexOf("Estancada"));
  check("path: nothing discouraging outside the folded block",
    !html.slice(0, html.indexOf("<details")).includes("Estancada") && !html.slice(0, html.indexOf("<details")).includes("Encert"));
  check("path: promotion shows the level reached",
    renderPath({ ...P, checkpoint: "promoted", promotion: { achieved: "A2", date: "2026-10-01", carried: 2 } }).includes("assolit el 2026-10-01"));
  check("path: ready checkpoint", renderPath({ ...P, checkpoint: "ready" }).includes("Ja pots fer la prova"));
  check("path: mini bar for the header", (renderPathMini(P) as { html: string }).html.includes("31%") && renderPathMini({ available: false }) === null);
  check("path: item bars", pathBarPct(P.sections[0].items[0]) === 25 && pathBarPct(P.sections[0].items[1]) === 100 && pathBarPct(P.sections[0].items[2]) === 0);
  check("path: a full n/need but not consolidated never shows 100%",
    pathBarPct({ state: "practicing", n: 30, need: 20 }) === 99);
  const notice = renderCourseNotice({ type: "course_completed", level: "A1", pct: 87.5, next_level: "A2", weak: ["there_is_are"] });
  check("course: says the level reached, the result and the new course",
    notice.includes("nivell A1") && notice.includes("88%") && notice.includes("A1 → A2") && notice.includes("no es pot tornar enrere"), notice);
  check("course: the weak ones are named without ids", notice.includes("there is are"));
  check("course: at the end of the target there is no new course",
    renderCourseNotice({ type: "course_completed", level: "A2", pct: 95, next_level: null, weak: [] }).includes("objectiu"));
  check("course: nothing for a notice of another kind", renderCourseNotice({ type: "x" }) === "" && renderCourseNotice(null) === "");
  check("course: certified levels are shown in the path",
    renderPath({ ...P, certified: [{ level: "A1", date: "2026-10-01" }] }).includes("A1 ✓"));
  check("test: not offered while the level is not ready", pathCheckpointOffer(P) === null);
  check("test: offered when ready", (pathCheckpointOffer({ ...P, checkpoint: "ready", as_of: "2026-09-25" }) || { label: "" }).label.includes("A2"));
  check("test: not offered on the days she has to wait", pathCheckpointOffer({ ...P, checkpoint: "ready", as_of: "2026-09-25", checkpoint_wait_until: "2026-09-28" }) === null);
  check("test: a running one is offered to continue, with its question number",
    (pathCheckpointOffer({ ...P, checkpoint_run: { active: true, i: 4, total: 24 } }) || { label: "" }).label.includes("4/24"));
  check("test: nothing once the level is certified", pathCheckpointOffer({ ...P, checkpoint: "promoted" }) === null);
  check("test: the panel has the button when ready",
    renderPath({ ...P, checkpoint: "ready", as_of: "2026-09-25" }).includes("data-start-checkpoint") && !renderPath(P).includes("data-start-checkpoint"));
  check("path: the server serves it (/api/fluent/path -> curriculum.py json)",
    /"\/api\/fluent\/path"/.test(fs.readFileSync(path.join(repo, "server", "src", "http.ts"), "utf8")) &&
    fs.readFileSync(path.join(repo, "server", "src", "http.ts"), "utf8").includes('"json", "--auto"'));
}


console.log(failures === 0 ? "web-render: all checks passed" : `web-render: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
