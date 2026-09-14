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

console.log(failures === 0 ? "web-render: all checks passed" : `web-render: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
