// Fluent web client — talks to the opencode API through the local proxy (/api/*).
// Locked-down learner view: chat + practice-mode buttons, pinned to the "learner" agent.
//
// Rendering is incremental: messages and parts are appended as they happen (SSE /event
// plus the blocking POST responses) instead of re-fetching the whole history after each
// turn. A safety poll runs while a turn is active so a lost SSE stream never blocks the UI.

const API = "/api";
const AGENT = "learner";

// Learner-clean view: command chips show icon only, successful skill/bash
// tool chips are hidden (status messages + errors always visible). Debug mode
// (?debug=1 or triple-click the brand) reveals command text + all tool chips.
const DEBUG =
  new URLSearchParams(location.search).get("debug") === "1" ||
  localStorage.getItem("fluent.debug") === "1";

const $ = (s) => document.querySelector(s);
const messagesEl = $("#messages");
const composerEl = $("#composer");
const inputEl = $("#input");
const sendBtn = $("#send");
const expandBtn = $("#expand");
const statusEl = $("#status");
const skillDotEl = $("#skill-dot");

// header is `position: fixed` (2026-09-22, Albert: on some mobile browsers
// `sticky` let the wrapped nav row of buttons scroll away while only the
// brand/status line stayed put) — so it no longer reserves its own space in
// the layout. Keep --header-h in sync with its REAL height (it changes: the
// pace pill and per-day badges show/hide, and the nav wraps to two lines on
// narrow screens) so main's top padding always clears it exactly.
(() => {
  const headerEl = document.querySelector("header");
  if (!headerEl || typeof ResizeObserver === "undefined") return;
  const sync = () => {
    document.documentElement.style.setProperty("--header-h", `${headerEl.offsetHeight}px`);
  };
  new ResizeObserver(sync).observe(headerEl);
  sync();
})();

const enc = encodeURIComponent;

let sessionId = localStorage.getItem("fluent.session") || null;
let busy = false;
let nearBottom = true;
let lastActivity = 0;
let pendingUser = null; // { text, el } — optimistic user bubble not yet confirmed by the server

const renderedMsgs = new Map(); // mid -> { div, role, parts: Map<partId, rec>, placeholder? }
const pendingParts = new Map(); // mid -> Map<partId, part> (parts that arrived before their message.updated)

messagesEl.addEventListener("scroll", () => {
  nearBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 80;
});

function scrollIfNear(entry) {
  // Selective stick: when the latest tutor text is an open exercise (pure
  // question or post-Score tail), DON'T follow — the flow stops at the end
  // of the feedback and the exercise card shows the question in parallel.
  // The learner scrolls down only if they want the in-flow copy.
  if (entry && entry.role !== "user" && !stickAllowed(entry)) return;
  if (nearBottom) messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Open exercise = what the card WOULD pin for this entry (card parked).
function stickAllowed(entry) {
  if (!FREEZE_FOR_CARD) return true;
  if (!entry) return true;
  const text = entryText(entry);
  if (!text) return true;
  return !splitFeedbackQuestion(text).question;
}

function entryText(entry) {
  if (!entry) return "";
  return [...entry.parts.values()]
    .filter((r) => r.type === "text")
    .map((r) => r.text || "")
    .join("\n")
    .trim();
}

// Paint feedback backgrounds (idempotent): the "Correct version" paragraph
// gets a green wash; ❌ / ✅ correction items get red/green washes.
// Canonical markers only — anything else renders unpainted.
function paintFeedback(el) {
  if (!el || !el.querySelectorAll) return;
  for (const st of el.querySelectorAll("strong")) {
    if (/^\s*correct version\s*:?\s*$/i.test(st.textContent || "")) {
      const block = st.closest("p, div, li, blockquote");
      if (block && block !== el) block.classList.add("fb-correct");
    }
  }
  for (const li of el.querySelectorAll("li")) {
    const t = (li.textContent || "").trim();
    if (t.startsWith("❌")) li.classList.add("fb-wrong");
    else if (t.startsWith("✅")) li.classList.add("fb-right");
  }
}

// ---- hear it said properly (local TTS) --------------------------------------
// The single thing a written tutor cannot do. A 🔊 button appears on the two
// places worth hearing — the exercise itself and the "correct version" of a
// correction — and nowhere else: an English voice reading the Catalan
// explanation would teach the wrong thing.
//
// If no voice is installed on this machine the server says so once and no
// button is ever drawn. Better nothing than a button that fails.

let ttsReady = false;
let ttsLanguage = null;
let currentAudio = null;

async function initTts() {
  try {
    const r = await api("/fluent/tts-state");
    ttsReady = r.enabled === true;
    ttsLanguage = r.language || null;
  } catch {
    ttsReady = false;
  }
  document.body.classList.toggle("has-tts", ttsReady);
}

function speakUrl(text) {
  const q = new URLSearchParams({ text: text.slice(0, 400) });
  if (ttsLanguage) q.set("lang", ttsLanguage);
  return `${API}/fluent/say?${q.toString()}`;
}

async function speak(text, btn) {
  if (!ttsReady || !text) return;
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  const audio = new Audio(speakUrl(text));
  currentAudio = audio;
  btn?.classList.add("speaking");
  const stop = () => {
    btn?.classList.remove("speaking");
    if (currentAudio === audio) currentAudio = null;
  };
  audio.addEventListener("ended", stop);
  audio.addEventListener("error", () => {
    stop();
    btn?.classList.add("speak-failed");
  });
  try {
    await audio.play();
  } catch {
    stop(); // autoplay refused, or no audio device
  }
}

function speakerButton(text) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "speak";
  b.title = "Escolta-ho";
  b.setAttribute("aria-label", "Escolta-ho");
  b.textContent = "🔊";
  b.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    speak(text, b);
  });
  return b;
}

// What may be read aloud, and how we know.
//
// The obvious idea — put a speaker on the exercise — is wrong: an exercise is
// not reliably in the target language. "Translate into English: Ahir vaig anar
// al mercat" is Catalan, and an English voice reading it teaches the opposite
// of what the exercise is for. Guessing the language from the string is a
// heuristic that fails LOUDLY (wrong accent, wrong sounds, learner none the
// wiser).
//
// So the tutor marks it instead: [[say]]…[[/say]] around any target-language
// sentence worth hearing. When the model forgets, you lose a button — the
// failure is silent and harmless, which is the right direction for this trade.
// The marker never reaches the learner's eyes either way.
const SAY_RE = /\[\[say\]\]([\s\S]{1,400}?)\[\[\/say\]\]/g;

// esc() is for text content and leaves quotes alone, which is fine there and
// broken here: a tutor sentence containing " would end the attribute early.
function escAttr(s) {
  return esc(s).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function markSayable(text) {
  return String(text || "").replace(SAY_RE, (_whole, inner) => {
    const clean = String(inner).trim();
    if (!clean) return "";
    return ttsReady ? `<span class="sayable" data-say="${escAttr(clean)}">${esc(clean)}</span>` : clean;
  });
}

// Where a target-language sentence actually appears in this tutor's feedback.
//
// Measured, not assumed. The canonical `**Correct version:**` label the code
// was written against does not appear in live output at all; what does is:
//
//   **Natural alternative:**
//   You could also say: "I had an appointment last Friday with my doctor."
//
//   **Now type the correct version yourself:**
//   "I had an appointment last Friday"
//
// In both, the sentence is the quoted part, and it is always in the target
// language. Anchor on the label, take the quote — never the label's own words,
// which are instructions to the learner.
const SPEAKABLE_LABEL_RE = /(correct version|natural alternative|you could also say)/i;

/** The quoted sentence in a block — the longest one, if several. */
function quotedIn(text) {
  const quotes =
    String(text || "").match(/[\u201c\u201d\u00ab]([^\u201c\u201d\u00ab\u00bb]{2,300})[\u201c\u201d\u00bb]|"([^"]{2,300})"/g) || [];
  let best = "";
  for (const q of quotes) {
    const inner = q.slice(1, -1).trim();
    if (inner.length > best.length) best = inner;
  }
  return best;
}

// The text of a block minus a leading "Label:" — the label is the tutor's
// scaffolding, not the sentence the learner is meant to repeat.
function sentenceOf(block) {
  const raw = (block.textContent || "").trim();
  const stripped = raw.replace(/^[^:]{0,30}:\s*/, "");
  return (stripped || raw).replace(/^["“'‘]|["”'’]$/g, "").trim();
}

/** Add 🔊 wherever we KNOW the text is in the target language. */
function paintSpeakers(el) {
  if (!ttsReady || !el || !el.querySelectorAll) return;
  // 1. Anything the tutor marked explicitly.
  for (const span of el.querySelectorAll(".sayable")) {
    if (span.querySelector(":scope > .speak")) continue;
    const text = span.getAttribute("data-say") || span.textContent || "";
    if (text.trim()) span.appendChild(speakerButton(text.trim()));
  }
  // 2. The model answer, wherever this tutor happens to put it. Needs no
  //    marker and no prompt change: the quoted sentence after one of these
  //    labels is in the target language by definition.
  for (const block of el.querySelectorAll("p, li, blockquote, div.md > *")) {
    if (block.querySelector && block.querySelector(".speak")) continue;
    const text = block.textContent || "";
    if (!SPEAKABLE_LABEL_RE.test(text)) continue;
    const sentence = quotedIn(text) || sentenceOf(block);
    if (sentence && sentence.length > 1) block.appendChild(speakerButton(sentence));
  }
}

// The tutor closes a review with a machine-readable block that the server
// parses (```fluent:review_results ... ```). It is data, not conversation:
// strip it before rendering so the learner never sees it.
const MACHINE_BLOCK_RE = /```fluent:[a-z_]+[\s\S]*?```/g;
// The tutor also prints the internal id of a review item ("**Item ID:**
// agreement_she_goes_to_school") because it sees the queue as JSON. The
// learner has no use for it and it reads as a bug. Whatever the model prints,
// the line does not reach the screen; the stored text keeps it.
const INTERNAL_ID_LINE_RE = /^[ \t]*(?:\*\*)?Item ID:?(?:\*\*)?[^\n]*\n?/gim;
function stripMachineBlocks(text) {
  return String(text || "")
    .replace(MACHINE_BLOCK_RE, "")
    .replace(INTERNAL_ID_LINE_RE, "")
    .trimEnd();
}

// The learner has buttons, not a command line, so a tutor sentence like
// "try /fluent-vocab" is advice they cannot follow. rules.md forbids it and the
// skills no longer print any — but a 14B model improvises, and the learner
// should never be the one who finds out. Rewriting at render time is the only
// guarantee: whatever the model says, what reaches the screen names a button.
const BUTTON_NAMES = {
  "fluent-learn": "🎲 Surprise me!",
  "fluent-review": "🔁 Review",
  "fluent-vocab": "📚 Vocabulary",
  "fluent-writing": "📝 Writing",
  "fluent-speaking": "🗣️ Speaking",
  "fluent-reading": "📖 Reading",
  "fluent-progress": "📊 Progress",
  "fluent-checkpoint": "🧪 Level test",
  "fluent-end": "🏁 End",
  "fluent-setup": "l'administrador",
  "fluent-use": "l'administrador",
};
const SLASH_RE = /`?\/(fluent-[a-z]+)`?/g;

function humanizeCommands(text) {
  return String(text || "").replace(SLASH_RE, (whole, cmd) => {
    const name = BUTTON_NAMES[cmd];
    return name ? `**${name}**` : whole;
  });
}

function renderTutorText(el, text) {
  const clean = markSayable(humanizeCommands(stripMachineBlocks(text)));
  el.innerHTML = md(clean);
  paintFeedback(el);
  paintExerciseBlocks(el, clean);
  paintModeLine(el);
  paintSpeakers(el);
}

// 2026-09-22, Albert: at a glance, "Write the complete sentence" and "Type
// the missing word" read the same — both just plain text next to a blanked
// ("___") sentence, so a quick skim misses which one is being asked for and
// he answers with only the missing word when the whole sentence was wanted.
// These two lines are always rendered bold by the tutor (fluent-feedback-
// formatter's own rule — see FULL_SENTENCE_RE above), so marked() turns them
// into <strong> — find that node by its exact text and give it its own
// background instead of relying on bold alone to be noticed.
const MODE_LINE_FULL_RE = /^type your answer \(the complete sentence\):?$/i;
const MODE_LINE_WORD_RE = /^type your answer \(just the missing word\):?$/i;
function paintModeLine(el) {
  if (!el || !el.querySelectorAll) return;
  for (const s of el.querySelectorAll("strong")) {
    s.classList.remove("mode-flag", "mode-flag-full", "mode-flag-word");
    const t = (s.textContent || "").trim();
    if (MODE_LINE_FULL_RE.test(t)) s.classList.add("mode-flag", "mode-flag-full");
    else if (MODE_LINE_WORD_RE.test(t)) s.classList.add("mode-flag", "mode-flag-word");
  }
}

// Exercise background at paragraph granularity: pure questions tint the
// whole text part; bundled messages tint from the first block holding an
// exercise marker onward (feedback keeps its own paint). Idempotent.
function paintExerciseBlocks(el, text) {
  if (!el) return;
  el.classList.remove("ex-block", "ex-start");
  if (el.querySelectorAll) {
    for (const k of el.querySelectorAll(".ex-block, .ex-start")) {
      k.classList.remove("ex-block", "ex-start");
    }
  }
  const split = splitFeedbackQuestion(text);
  if (!split.question || !el.children) return;
  if (!split.feedback) {
    el.classList.add("ex-block", "ex-start");
    return;
  }
  const kids = [...el.children];
  const idx = kids.findIndex((k) => EXERCISE_START_RE.test(k.textContent || ""));
  if (idx === -1) return;
  for (let i = idx; i < kids.length; i++) kids[i].classList.add("ex-block");
  kids[idx].classList.add("ex-start"); // question start stands out
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function md(text) {
  if (window.marked) {
    marked.setOptions({ breaks: true, gfm: true });
    return marked.parse(text || "");
  }
  return "<p>" + esc(text).replace(/\n/g, "<br>") + "</p>";
}

// OpenCode sometimes attaches an *object* as info.error (or info.error.message),
// which String() would render as the literal "[object Object]". Serialize it so the
// real cause is visible instead of a useless placeholder.
function errText(e) {
  if (!e) return "error";
  if (typeof e === "string") return e;
  if (e.message) return typeof e.message === "string" ? e.message : JSON.stringify(e.message);
  try { return JSON.stringify(e); } catch { return String(e); }
}

// ---- session progress (where you are) ---------------------------------------
// The count comes from the server, which counts the graded answers it has
// actually recorded — the model is not asked to keep score.
const paceEl = $("#pace");

// 📖 Reading is hard to follow below A1 (fluent-reading's own skill file says
// so: "skip below A1 mastery 3") — hidden until the learner is past A1, so
// nobody on a fresh A0 profile finds it and gets a text they can't read
// (2026-09-22, Albert). `p.lesson.level` already carries the learner's
// current CEFR level (lessonState() reads it from learner-profile.json), so
// no new server field is needed. Level unknown → stays hidden (fails safe).
const CEFR_ORDER = ["A0", "A1", "A2", "B1", "B2", "C1", "C2"];
function readingUnlocked(level) {
  const i = CEFR_ORDER.indexOf(String(level || "").toUpperCase());
  return i > CEFR_ORDER.indexOf("A1");
}

// The button ring is a client-side memory of the last mode button clicked —
// it has no idea the server is already in a mode after a reload or a resumed
// session (2026-09-22, Albert: lost the Go ring after nothing but a reload).
// session-progress now ships the server's own `mode`; sync the ring to it
// whenever it disagrees, instead of only setting it from local clicks.
function syncModeFromServer(mode) {
  if (typeof mode === "undefined") return;
  const m = mode || null;
  if (m === currentMode) return;
  currentMode = m;
  updateActiveModeButton();
}

function renderPace(p) {
  syncModeFromServer(p && p.mode);
  if (!paceEl) return;
  if (!p || typeof p.graded !== "number") {
    paceEl.hidden = true;
    renderLessonBadge(null);
    renderSkillBadge(speakingBtn, speakingWasPending, (v) => (speakingWasPending = v), null, "");
    renderSkillBadge(readingBtn, readingWasPending, (v) => (readingWasPending = v), null, "");
    renderSkillBadge(writingBtn, writingWasPending, (v) => (writingWasPending = v), null, "");
    if (readingBtn) readingBtn.hidden = true;
    return;
  }
  // The day's effort, with a face that climbs to the goal. No target line and
  // no ceiling: going past the goal is a good day, not an error.
  const goal = p.goal > 0 ? p.goal : 0;
  const face = p.face || "😐";
  paceEl.innerHTML = `✏️ ${p.graded}<span class="pace-face">${face}</span>`;
  paceEl.classList.toggle("done", goal > 0 && p.graded >= goal);
  paceEl.title = goal
    ? p.graded >= goal
      ? `${p.graded} exercicis avui — objectiu de ${goal} assolit 🤩`
      : `${p.graded} exercicis avui · objectiu ${goal} (en falten ${goal - p.graded})`
    : `${p.graded} exercicis avui`;
  paceEl.hidden = false;
  renderLessonBadge(p.lesson);
  renderSkillBadge(speakingBtn, speakingWasPending, (v) => (speakingWasPending = v),
    p.speaking, "Speaking d'avui");
  renderSkillBadge(readingBtn, readingWasPending, (v) => (readingWasPending = v),
    p.reading, "Reading d'avui");
  renderSkillBadge(writingBtn, writingWasPending, (v) => (writingWasPending = v),
    p.writing, "Writing d'avui");
  if (readingBtn) readingBtn.hidden = !readingUnlocked(p.lesson && p.lesson.level);
}

// The badge on 🎓 Lesson. Amber while there is work, a green tick for a moment
// when it empties, then nothing. It never disables anything: the learner can
// press whatever they like, the badge just says what is still owed.
const lessonBtn = document.querySelector('#commands button[data-cmd="fluent-review"]');
let lessonWasPending = false;

function renderLessonBadge(lesson) {
  if (!lessonBtn) return;
  const badge = lessonBtn.querySelector(".badge");
  if (!badge) return;
  if (!lesson || !lesson.total) {
    lessonBtn.classList.remove("pending", "done");
    badge.hidden = true;
    return;
  }
  const pending = lesson.pending || 0;
  if (pending > 0) {
    lessonWasPending = true;
    badge.textContent = String(pending);
    badge.hidden = false;
    lessonBtn.classList.add("pending");
    lessonBtn.classList.remove("done");
    const parts = [`Lliçó d'avui: ${lesson.done}/${lesson.total}`];
    if (lesson.due > 0) parts.push(`${lesson.due} repàs pendent`);
    if (lesson.slot) parts.push(`inclou ${lesson.slot}`);
    lessonBtn.title = parts.join(" · ");
    return;
  }
  lessonBtn.classList.remove("pending");
  lessonBtn.title = `Lliçó d'avui feta ✓ (${lesson.total} exercicis)`;
  if (lessonWasPending) {
    lessonWasPending = false;
    badge.textContent = "✓";
    badge.hidden = false;
    lessonBtn.classList.add("done");
    setTimeout(() => {
      badge.hidden = true;
      lessonBtn.classList.remove("done");
    }, 4000);
  } else {
    badge.hidden = true;
    lessonBtn.classList.remove("done");
  }
}

// The same "1 pending today" reminder on 🗣️ Speaking and 📖 Reading — same
// principle as 🎓 Review (a daily badge, cleared only by using that button,
// never by an equivalent exercise surfacing on its own in Mix), but with
// none of Review's own complexity: always a fixed target of 1, so this is a
// small generic version reused for both buttons rather than duplicating
// `renderLessonBadge`'s richer (due/slot) logic. Never a gate — Mix keeps
// choosing whatever it likes; this only says "you haven't done one of these
// today" (2026-09-22, Albert).
const speakingBtn = document.querySelector('#commands button[data-cmd="fluent-speaking"]');
const readingBtn = document.querySelector('#commands button[data-cmd="fluent-reading"]');
// 📝 Writing joined them on 2026-09-23 (Albert): the one practice where she writes her
// own words, owed once a day at every level — like Speaking, unlike Reading (> A1).
const writingBtn = document.querySelector('#commands button[data-cmd="fluent-writing"]');
let speakingWasPending = false;
let readingWasPending = false;
let writingWasPending = false;

function renderSkillBadge(btn, wasPending, setWasPending, view, label) {
  if (!btn) return;
  const badge = btn.querySelector(".badge");
  if (!badge) return;
  if (!view || !view.total) {
    btn.classList.remove("pending", "done");
    badge.hidden = true;
    return;
  }
  const pending = view.pending || 0;
  if (pending > 0) {
    setWasPending(true);
    badge.textContent = String(pending);
    badge.hidden = false;
    btn.classList.add("pending");
    btn.classList.remove("done");
    btn.title = `${label}: encara no fet`;
    return;
  }
  btn.classList.remove("pending");
  btn.title = `${label} fet ✓`;
  if (wasPending) {
    setWasPending(false);
    badge.textContent = "✓";
    badge.hidden = false;
    btn.classList.add("done");
    setTimeout(() => {
      badge.hidden = true;
      btn.classList.remove("done");
    }, 4000);
  } else {
    badge.hidden = true;
    btn.classList.remove("done");
  }
}

// Small bar in the header: opens the panel. Hidden when the profile's level
// has no curriculum.
const pathMiniEl = $("#path-mini");
let pathAt = 0;

const courseOverlay = $("#course-overlay");
const courseBody = $("#course-body");
let courseNoticeShown = false;

function showCourseNotice(n) {
  if (!courseOverlay || courseNoticeShown || !n) return;
  const html = renderCourseNotice(n);
  if (!html) return;
  courseNoticeShown = true;
  courseBody.innerHTML = html;
  courseOverlay.hidden = false;
}

if (courseOverlay) {
  $("#course-ok").addEventListener("click", async () => {
    courseOverlay.hidden = true;
    try { await api("/fluent/path/seen", { method: "POST" }); } catch { /* it will be shown again: harmless */ }
    courseNoticeShown = false;
  });
}

const checkpointBtn = document.querySelector('#commands button[data-cmd="fluent-checkpoint"]');

function renderPathMiniBar(p) {
  if (p && p.notice) showCourseNotice(p.notice);
  if (checkpointBtn) {
    const offer = pathCheckpointOffer(p);
    checkpointBtn.hidden = !offer;
    if (offer) checkpointBtn.title = offer.label;
  }
  if (!pathMiniEl) return;
  const m = renderPathMini(p);
  if (!m) {
    pathMiniEl.hidden = true;
    return;
  }
  pathMiniEl.innerHTML = m.html;
  pathMiniEl.title = m.title;
  pathMiniEl.hidden = false;
}

async function refreshPath(force = false) {
  if (!pathMiniEl) return;
  if (!force && Date.now() - pathAt < 1500) return;
  pathAt = Date.now();
  try {
    const res = await api("/fluent/path");
    renderPathMiniBar(res && res.ok ? res.data : null);
  } catch {
    /* the bar is never worth an error */
  }
}

if (pathMiniEl) pathMiniEl.addEventListener("click", openProgress);

async function refreshPace() {
  refreshPath();
  if (!sessionId) {
    renderPace(null);
    return;
  }
  try {
    renderPace(await api(`/fluent/session-progress?session=${encodeURIComponent(sessionId)}`));
  } catch {
    /* the indicator is never worth an error */
  }
}

function setBusy(b) {
  busy = b;
  if (b) lastActivity = Date.now();
  sendBtn.disabled = b;
  inputEl.disabled = b;
  expandBtn.disabled = b;
  for (const btn of document.querySelectorAll("#commands button")) btn.disabled = b;
  $("#new-session").disabled = b;
  statusEl.textContent = b ? "el tutor està pensant…" : statusEl.dataset.online || "offline";
  // Focus mode: hide the practice-mode nav while a turn is running so it
  // doesn't break the question → answer flow. Purely visual, trivially
  // reversible (piece 1 of items 3+4).
  document.body.classList.toggle("focusing", b);
  // Fresh "your turn" affordance: highlight the composer when a turn ends.
  if (b) {
    composerEl.classList.remove("awaiting");
  } else {
    composerEl.classList.add("awaiting");
    trackLatestTutor();
    refreshExerciseCard();
    updateSendState();
  }
  if (!b) inputEl.focus();
}

function toolChip(part, n) {
  const name = part.tool || part.state?.tool || "tool";
  const st = part.state?.status || "pending";
  // Learner view: hide successful skill/bash noise (the tutor text + status
  // messages carry the meaning). Errors and deep-evaluation always show.
  if (!DEBUG && (name === "skill" || name === "bash") && (st === "completed" || st === "success")) return "";
  const icon = st === "error" ? "✗" : st === "completed" || st === "success" ? "✓" : "⏳";
  // The deep-evaluation tool shows a friendly label (and its call number)
  // instead of the raw tool name.
  const label =
    name === "fluent_deep_evaluate"
      ? "avaluant resposta" + (n && n > 1 ? " (" + n + ")" : "")
      : esc(name);
  // Collapsible: open while running (live feedback), closed once settled so
  // tool noise doesn't crowd out the actual tutor text. Expanding reveals
  // the raw tool name + status (or the error, if any).
  const open = st !== "completed" && st !== "success" && st !== "error" ? " open" : "";
  const body =
    st === "error" && part.state?.error
      ? `<div class="tool-err">${esc(errText(part.state.error).slice(0, 300))}</div>`
      : `<div class="tool-meta">${esc(name)} · ${esc(st)}</div>`;
  return `<details class="toold"${open}><summary><span class="chip ${st === "error" ? "err" : ""}">${icon} ${label}</span></summary>${body}</details>`;
}

function evalCount(entry) {
  let n = 0;
  for (const r of entry.parts.values()) if (r.tool === "fluent_deep_evaluate") n++;
  return n;
}

function scoreOf(text) {
  const m = /score\s*:\s*(\d+(?:\.\d+)?)\s*\/\s*10/i.exec(text || "");
  return m ? m[1] + "/10" : null;
}

// Tag in-flow tutor messages so the question → feedback structure is visible
// at a glance: open exercises get an accent edge + "Exercici" chip, feedback
// gets the extracted score chip. Recomputed on every text update (cheap
// regex); user messages are never tagged.
// Empty-send ("next") is only enabled when the tutor is NOT waiting for an
// answer: i.e. the latest tutor message is not an open exercise. Determined
// from the flow tags (msg-exercise without msg-feedback). Typed text always
// sends, even "next" (explicit intent to skip).
function latestTutorOpen() {
  const tutors = messagesEl.querySelectorAll(".msg.assistant");
  if (!tutors.length) return false;
  const last = tutors[tutors.length - 1];
  return last.classList.contains("msg-exercise") && !last.classList.contains("msg-feedback");
}
function updateSendState() {
  const blocked = latestTutorOpen();
  sendBtn.classList.toggle("cant-next", blocked);
  sendBtn.title = blocked
    ? "L'exercici espera la teva resposta — escriu-la (o escriu «next» per saltar)"
    : "Envia (buit = següent exercici)";
}
function tagFlowMessage(entry) {
  if (!entry || !entry.div) return;
  if (entry.role === "user") {
    entry.div.classList.remove("msg-exercise", "msg-feedback");
    const stale = entry.div.querySelector(":scope > .flow-tag");
    if (stale) stale.remove();
    return;
  }
  const text = entryText(entry);
  const score = scoreOf(text);
  const open = !score && isOpenExercise(text);
  let tag = entry.div.querySelector(":scope > .flow-tag");
  if (!score && !open) {
    entry.div.classList.remove("msg-exercise", "msg-feedback");
    if (tag) tag.remove();
    return;
  }
  entry.div.classList.toggle("msg-feedback", !!score);
  entry.div.classList.toggle("msg-exercise", open);
  if (!tag) {
    tag = document.createElement("div");
    tag.className = "flow-tag";
    entry.div.prepend(tag);
  }
  tag.innerHTML = score
    ? `<span class="chip">★ ${esc(score)}</span>`
    : `<span class="chip">✏️ Exercici</span>`;
  updateSendState();
}

// Command messages (e.g. /fluent-learn) arrive as user text containing the full expanded
// prompt. The learner only needs to see which mode was started, so collapse them to a chip.
function userBubbleHTML(text) {
  // "next" (typed or via empty send) renders as a continue chip.
  if (/^\s*next\s*$/i.test(text || "")) {
    const label = DEBUG ? "next" : "";
    return `<span class="chip" title="next">⏭${label}</span>`;
  }
  const m = /^Execute\s+\/(fluent-[a-z0-9-]+)/im.exec(text || "");
  if (m) {
    const key = m[1].slice("fluent-".length);
    const icons = { learn: "🎲", checkpoint: "🧪", review: "🔄", vocab: "📖", writing: "📝", speaking: "🗣️", reading: "👀", progress: "📊", setup: "⚙️" };
    // Learner view: icon only (the command text adds nothing for the learner).
    // Debug mode reveals which command was started.
    const label = DEBUG ? ` /fluent-${esc(key)}` : "";
    return `<span class="chip" title="/fluent-${esc(key)}">${icons[key] || "🎯"}${label}</span>`;
  }
  return md(text);
}

// Remove the "…" placeholder once the first visible part lands.
function clearPlaceholder(entry) {
  if (entry.role !== "user" && entry.placeholder && entry.placeholder.isConnected) {
    entry.placeholder.remove();
    entry.placeholder = null;
  }
}

// Append/update one part inside its message div.
function applyPart(entry, part) {
  if (!part || !part.id) return;
  if (entry.role === "user") {
    if (entry.parts.has(part.id)) return;
    entry.parts.set(part.id, { type: part.type, text: part.type === "text" ? part.text || "" : "" });
    const text = [...entry.parts.values()]
      .filter((r) => r.type === "text")
      .map((r) => r.text || "")
      .join("\n");
    let bubble = entry.div.querySelector(".bubble");
    if (!bubble) {
      bubble = document.createElement("div");
      bubble.className = "bubble";
      entry.div.appendChild(bubble);
    }
    bubble.innerHTML = userBubbleHTML(text);
    scrollIfNear();
    return;
  }
  const existing = entry.parts.get(part.id);
  if (existing) {
    if (part.type === "text") {
      clearPlaceholder(entry);
      existing.text = part.text || "";
      renderTutorText(existing.el, existing.text);
      tagFlowMessage(entry);
    } else if (part.type === "tool") {
      clearPlaceholder(entry);
      existing.el.innerHTML = toolChip(part, evalCount(entry));
    }
    scrollIfNear(entry);
    return;
  }
  let el = null;
  if (part.type === "text") {
    clearPlaceholder(entry);
    el = document.createElement("div");
    el.className = "md";
    renderTutorText(el, part.text || "");
    entry.parts.set(part.id, { type: "text", el, text: part.text || "" });
    tagFlowMessage(entry);
  } else if (part.type === "tool") {
    clearPlaceholder(entry);
    el = document.createElement("div");
    entry.parts.set(part.id, { type: "tool", el, tool: part.tool || part.state?.tool });
    el.innerHTML = toolChip(part, evalCount(entry));
  } else {
    return;
  }
  entry.div.appendChild(el);
  scrollIfNear(entry);
}

// Create the message div if needed (dedup by message id), flush buffered parts.
function ensureMsg(info, parts) {
  if (!info || !info.id) return null;
  const mid = info.id;
  const already = renderedMsgs.get(mid);
  if (already) {
    // Re-apply parts so the safety poll can update an already-rendered message
    // (e.g. the "…" placeholder created before the first part existed).
    if (info.error && !already.errorShown) {
      const el = document.createElement("div");
      el.className = "md";
      el.innerHTML = "⚠️ " + esc(errText(info.error));
      already.div.appendChild(el);
      already.errorShown = true;
      clearPlaceholder(already);
    }
    if (parts) for (const part of parts) applyPart(already, part);
    return already;
  }
  let entry = null;
  if (info.role === "user" && pendingUser) {
    // Adopt the optimistic bubble. The SSE message.updated event arrives
    // WITHOUT parts (the text lands in a later message.part.updated), so a
    // text comparison can only be done when parts are present (safety poll /
    // history). Without parts this must be the pending bubble — sends are
    // serialized, so at most one is pending at a time.
    const text = (parts || [])
      .map((p) => (p.type === "text" ? p.text || "" : ""))
      .join("\n");
    if (!parts || text.trim() === String(pendingUser.text).trim()) {
      pendingUser.el.dataset.mid = mid;
      entry = { div: pendingUser.el, role: "user", parts: new Map() };
      renderedMsgs.set(mid, entry);
      pendingUser = null;
    }
  }
    if (!entry) {
      const div = document.createElement("div");
      div.className = "msg " + (info.role === "user" ? "user" : "assistant");
      entry = { div, role: info.role, parts: new Map() };
      if (info.role !== "user") {
        if (info.error) {
          const el = document.createElement("div");
          el.className = "md";
          el.innerHTML = "⚠️ " + esc(errText(info.error));
          div.appendChild(el);
          entry.errorShown = true;
        } else {
          // Live "pensant… N s" counter until the first part lands.
          const ph = document.createElement("div");
          ph.className = "md";
          ph.innerHTML = '<em class="thinking">pensant… 0 s</em>';
          div.appendChild(ph);
          entry.placeholder = ph;
          entry.thinkStart = Date.now();
        }
      }
      messagesEl.appendChild(div);
      renderedMsgs.set(mid, entry);
    }
  const buf = pendingParts.get(mid);
  if (buf) {
    for (const part of buf.values()) applyPart(entry, part);
    pendingParts.delete(mid);
  }
  if (parts) for (const part of parts) applyPart(entry, part);
  return entry;
}

function addUserMsg(text) {
  const div = document.createElement("div");
  div.className = "msg user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = md(text);
  div.appendChild(bubble);
  messagesEl.appendChild(div);
  scrollIfNear();
  return div;
}

async function api(path, opts = {}) {
  const doFetch = () =>
    fetch(API + path, {
      method: opts.method || "GET",
      headers: { "content-type": "application/json" },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  let res = await doFetch();
  if (res.status === 401) {
    // browser shows the basic-auth prompt on the retry
    res = await doFetch();
  }
  if (res.status === 204) return null;
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error("HTTP " + res.status + (t ? " — " + t.slice(0, 200) : ""));
  }
  return res.json();
}

function showError(e) {
  const div = document.createElement("div");
  div.className = "msg error";
  div.innerHTML = `<div class="md">⚠️ ${esc(e.message)}</div>`;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// TurnOutcome.debug (agent.ts) — server-only, never written by the model.
// Green: skill loaded, context comfortable. Amber: context over 80% of the
// model's window (getting close to the point where llama.cpp starts
// trimming from the front, where the rules live). Red: the skill is not
// loaded for this session right now — grading and exercise rules are gone
// and the tutor is improvising, however normal its reply reads. Measured
// live 2026-09-23: exactly this, 20+ turns, nothing in the chat showed it.
function updateSkillStatus(debug) {
  if (!skillDotEl) return;
  if (!debug) {
    skillDotEl.hidden = true;
    return;
  }
  skillDotEl.hidden = false;
  skillDotEl.classList.remove("warn", "err");
  const pct = debug.ctxRatio != null ? Math.round(debug.ctxRatio * 100) : null;
  if (!debug.skillLoaded) {
    skillDotEl.classList.add("err");
    skillDotEl.title = "Skill no carregat en aquesta sessió — el tutor no té el contracte de correcció ni les regles d'exercici. Prova de prémer un botó de pràctica.";
  } else if (pct != null && pct >= 80) {
    skillDotEl.classList.add("warn");
    skillDotEl.title = `Skill carregat (${debug.skillName || "?"}) — context al ${pct}% del límit (${debug.promptTokens}/${debug.ctxLimit} tok).`;
  } else {
    skillDotEl.title = `Skill carregat (${debug.skillName || "?"})${pct != null ? ` — context al ${pct}%` : ""}.`;
  }
}

// The blocking POST returns { info: AssistantMessage, parts: Part[] }. Render it unless
// SSE already did; if the shape is unexpected, fall back to a full re-render.
async function appendAssistant(res) {
  lastActivity = Date.now();
  updateSkillStatus(res && res.debug);
  const info = res && res.info;
  if (!info || !info.id) {
    await refresh().catch(() => {});
    return;
  }
  ensureMsg(info, res.parts);
}

// Resume the stored session only if it is still alive.
//
// Closing the browser does nothing on the server: the session is finished by
// the 🏁 button or by the sweeper after 30 idle minutes. Resuming it blindly
// meant coming back next morning into a session that had already been
// finalized (so nothing after that point ever got a summary) and that kept
// growing until the prompt passed the model's context — at which point
// llama.cpp truncates from the left, where the rules live. The server decides;
// the client just asks.
async function ensureSession() {
  if (sessionId) {
    const s = await api("/session/" + enc(sessionId)).catch(() => null);
    if (s) {
      let resume = true;
      try {
        const state = await api(`/fluent/session-state?session=${enc(sessionId)}`);
        resume = state.resumable !== false;
      } catch {
        resume = true; // the check is never worth blocking on
      }
      if (resume) return;
    }
    sessionId = null;
    localStorage.removeItem("fluent.session");
  }
  const s = await api("/session", { method: "POST", body: { title: "Fluent" } });
  sessionId = s.id || s.info?.id;
  if (!sessionId) throw new Error("no s'ha pogut crear la sessió");
  localStorage.setItem("fluent.session", sessionId);
}

async function renderHistory() {
  const list = await api(`/session/${enc(sessionId)}/message?limit=200`).catch(() => []);
  messagesEl.innerHTML = "";
  renderedMsgs.clear();
  pendingParts.clear();
  pendingUser = null;
  for (const m of list || []) ensureMsg(m.info, m.parts);
  const empty = !(list || []).length;
  if (empty) {
    const div = document.createElement("div");
    div.className = "msg hint";
    div.innerHTML =
      '<div class="md">Benvingut/da! 🌍 Tria un mode de pràctica amb els botons o escriu una pregunta a sota.</div>';
    messagesEl.appendChild(div);
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
  trackLatestTutor();
  refreshExerciseCard(false); // no snap on (re)load — respect current view
  return empty;
}

async function refresh() {
  await renderHistory();
}

async function send(text) {
  if (busy) return;
  // Empty send = "next", but only when the tutor is not waiting for an
  // answer (latest tutor message is not an open exercise).
  if (!text.trim() && latestTutorOpen()) return;
  const msg = text.trim() ? text : "next";
  pendingUser = { text: msg, el: addUserMsg(msg) };
  inputEl.value = "";
  autosize();
  composerEl.classList.remove("awaiting");
  setBusy(true);
  showThinkingTip();
  try {
    const res = await api(`/session/${enc(sessionId)}/message`, {
      method: "POST",
      body: { agent: AGENT, parts: [{ type: "text", text: msg }] },
    });
    if (res && res.bounce) {
      // Session from before a server restart: the answer was not sent anywhere.
      if (pendingUser) pendingUser.el.remove();
      pendingUser = null;
      clearAllPlaceholders();
      setBusy(false);
      handleSessionBounce(res.bounce);
      return;
    }
    await appendAssistant(res);
  } catch (e) {
    if (pendingUser) {
      pendingUser.el.remove();
      pendingUser = null;
    }
    clearAllPlaceholders();
    showError(e);
  }
  setBusy(false);
}

// "Where am I" marker on the nav — only the modes that stay open-ended long
// enough for it to matter (Go, Review, Reading, Speaking; 2026-09-22, Albert:
// "només dels tres modes, quatre sumant reading" — Writing/Vocab are hidden
// anyway and Stats/End are one-shot, not a place you stay). A plain ring, not
// a color, so it never collides with the pending (amber) / done (green)
// meaning those three buttons already carry.
const TRACKED_MODE_CMDS = ["fluent-learn", "fluent-review", "fluent-reading", "fluent-speaking", "fluent-writing"];
function updateActiveModeButton() {
  for (const cmd of TRACKED_MODE_CMDS) {
    const btn = document.querySelector(`#commands button[data-cmd="${cmd}"]`);
    if (btn) btn.classList.toggle("current-mode", cmd === currentMode);
  }
}

async function runCommand(cmd) {
  if (busy) return;
  currentMode = cmd;
  updateActiveModeButton();
  inputEl.placeholder = MODE_PLACEHOLDERS[cmd] || DEFAULT_PLACEHOLDER;
  setBusy(true);
  showThinkingTip();
  try {
    const res = await api(`/session/${enc(sessionId)}/command`, {
      method: "POST",
      body: { agent: AGENT, command: cmd, arguments: "" },
    });
    if (res && res.bounce) {
      clearAllPlaceholders();
      setBusy(false);
      handleSessionBounce(res.bounce);
      return;
    }
    await appendAssistant(res);
  } catch (e) {
    clearAllPlaceholders();
    showError(e);
  }
  setBusy(false);
}

// Decide the first command to auto-run when opening a (fresh) session.
// Onboarding is NOT the learner's job: profiles are created by the admin
// (scripts/fluent-profile.py), so a profile that is not set up gets a short
// notice instead of a form it should not be filling in. Falls back to
// fluent-learn if setup-state is unreachable (never blocks normal use).
async function initialCommand() {
  try {
    const r = await api("/fluent/setup-state");
    if (r.setup_complete === false) return null;
  } catch {
    /* the check is never worth blocking on */
  }
  return "fluent-learn";
}

function showSetupNotice() {
  const el = document.createElement("div");
  el.className = "msg assistant";
  el.innerHTML =
    "<div class=\"bubble\"><p>Aquest perfil encara no està configurat.</p>" +
    "<p>La configuració la fa l'administrador; quan el perfil estigui llest, " +
    "podràs començar a practicar des dels botons de dalt.</p></div>";
  messagesEl.appendChild(el);
}

async function newSession(opts) {
  const skipConfirm = !!(opts && opts.skipConfirm);
  if (busy && !skipConfirm) return;
  if (!skipConfirm && !confirm("Tancar aquesta sessió i en començar una de nova?")) return;
  sessionId = null;
  localStorage.removeItem("fluent.session");
  messagesEl.innerHTML = "";
  renderedMsgs.clear();
  pendingParts.clear();
  pendingUser = null;
  stopTrackingLatest();
  exerciseMsgId = null;
  exerciseCard.hidden = true;
  currentMode = null;
  updateActiveModeButton();
  inputEl.placeholder = DEFAULT_PLACEHOLDER;
  await ensureSession();
  // The count is the DAY's, not the session's — a new session does not reset it.
  const empty = await renderHistory();
  if (empty) {
    const cmd = await initialCommand();
    if (cmd) runCommand(cmd);
    else showSetupNotice();
  }
}

// The server decided THIS session is no longer reliable (context had to be
// trimmed to fit, or several answers in a row went ungraded — see
// bounceReason in pacing.ts) and told us to bounce it: a short, plain notice
// — never the raw reason code — then straight into a clean session, no
// confirm() (there is nothing left worth keeping in this one).
const BOUNCE_REASON_TEXT = {
  "context-full": "Aquesta sessió ha crescut massa i el model ha començat a perdre el fil.",
  "not-grading": "El model ha deixat de puntuar els exercicis.",
  restart: "L'app s'ha reiniciat i l'exercici pendent s'ha perdut.",
};

async function handleSessionBounce(reason) {
  const el = document.createElement("div");
  el.className = "msg assistant";
  const why = BOUNCE_REASON_TEXT[reason] || "Aquesta sessió ha deixat de funcionar bé.";
  el.innerHTML =
    `<div class="bubble">⚠️ ${why} Començo una sessió nova automàticament.</div>`;
  messagesEl.appendChild(el);
  scrollIfNear(null);
  await new Promise((r) => setTimeout(r, 1600));
  await newSession({ skipConfirm: true });
}

function autosize() {
  if (composerEl.classList.contains("expanded")) return; // CSS owns the height
  inputEl.style.height = "auto";
  const max = Math.floor(window.innerHeight * 0.38);
  inputEl.style.height = Math.max(64, Math.min(inputEl.scrollHeight, max)) + "px";
}

// ---- live stream (SSE) -------------------------------------------------------

let es = null;
let esTries = 0;

function openSSE() {
  if (es) return;
  try {
    es = new EventSource(API + "/event");
  } catch {
    es = null;
    setTimeout(openSSE, 5000);
    return;
  }
  es.onopen = () => {
    esTries = 0;
  };
  es.onmessage = (ev) => {
    let d;
    try {
      d = JSON.parse(ev.data);
    } catch {
      return;
    }
    handleEvent(d);
  };
  es.onerror = () => {
    if (es && es.readyState === EventSource.CLOSED) {
      es.close();
      es = null;
      const delay = Math.min(15000, 500 * 2 ** esTries);
      esTries += 1;
      setTimeout(openSSE, delay);
    }
    // readyState CONNECTING: the browser is already retrying on its own
  };
}

function handleEvent(d) {
  const t = d && d.type;
  const p = (d && d.properties) || {};
  if (t === "session.bounce") {
    if (!p.sessionID || p.sessionID !== sessionId) return;
    handleSessionBounce(p.reason);
    return;
  }
  if (t === "message.updated") {
    const info = p.info;
    if (!info || info.sessionID !== sessionId) return;
    ensureMsg(info);
  } else if (t === "message.part.updated") {
    const part = p.part;
    if (!part || part.sessionID !== sessionId) return;
    const entry = renderedMsgs.get(part.messageID);
    if (entry) {
      applyPart(entry, part);
    } else {
      if (!pendingParts.has(part.messageID)) pendingParts.set(part.messageID, new Map());
      pendingParts.get(part.messageID).set(part.id, part);
    }
  } else if (t === "message.part.delta") {
    if (!p.sessionID || p.sessionID !== sessionId) return;
    if (p.field !== "text" || !p.delta) return;
    const entry = renderedMsgs.get(p.messageID);
    const rec = entry && entry.parts.get(p.partID);
    if (!rec || rec.type !== "text") return;
    rec.text = (rec.text || "") + p.delta;
    renderTutorText(rec.el, rec.text);
    tagFlowMessage(entry);
    scrollIfNear(entry);
  } else if (t === "message.removed") {
    const info = p.info;
    if (!info || info.sessionID !== sessionId) return;
    const entry = renderedMsgs.get(info.id);
    if (entry) {
      entry.div.remove();
      renderedMsgs.delete(info.id);
    }
    pendingParts.delete(info.id);
  } else if (t === "session.progress") {
    if (p.sessionID === sessionId) renderPace(p);
  } else if (t === "session.idle") {
    if (p.sessionID === sessionId && busy) setBusy(false);
    // A course can close on THIS turn (the level test's last answer). Without
    // this, the "course finished / welcome to A2" notice only showed up once
    // the learner happened to open Progress by hand — nothing told them a
    // turn had changed anything, so pressing Lesson right after (which is
    // already the new course, `find_curriculum` skips the certified one) felt
    // like a coin flip instead of a clear "you're done, here's what's next".
    if (p.sessionID === sessionId) refreshPath(true);
  } else if (t === "session.error") {
    if (p.sessionID === sessionId) {
      const msg = p.error && p.error.message ? p.error.message : String(p.error || "error de sessió");
      showError(new Error(msg));
    }
  }
}

// Live "pensant… N s" counter for assistant messages waiting for their first part.
setInterval(() => {
  for (const entry of renderedMsgs.values()) {
    if (!entry.placeholder || !entry.placeholder.isConnected || !entry.thinkStart) continue;
    const el = entry.placeholder.querySelector(".thinking");
    if (el) {
      el.textContent =
        "pensant… " + Math.max(0, Math.floor((Date.now() - entry.thinkStart) / 1000)) + " s";
    }
  }
}, 1000);

// One-time hint: the first characters can take a few seconds (context + tools).
function showThinkingTip() {
  if (localStorage.getItem("fluent.tip.thinking")) return;
  localStorage.setItem("fluent.tip.thinking", "1");
  const div = document.createElement("div");
  div.className = "msg hint";
  div.innerHTML =
    '<div class="md"><em>💡 El primer caràcter pot trigar uns segons (el model carrega el context i les eines). Quan arribi contingut, el comptador desapareix.</em></div>';
  messagesEl.appendChild(div);
  scrollIfNear();
}

function clearAllPlaceholders() {
  for (const entry of renderedMsgs.values()) clearPlaceholder(entry);
}

// Safety net: while a turn is running (or for a short window after it ends), re-check the
// history so events lost to a dead SSE stream still show up.
setInterval(() => {
  if (!sessionId) return;
  if (!busy && Date.now() - lastActivity > 15000) return;
  api(`/session/${enc(sessionId)}/message?limit=60`)
    .then((list) => {
      for (const m of list || []) ensureMsg(m.info, m.parts);
    })
    .catch(() => {});
}, 5000);

async function init() {
  try {
    const h = await api("/global/health");
    statusEl.dataset.online = "v" + (h.version || "?");
    statusEl.textContent = statusEl.dataset.online;
  } catch (e) {
    statusEl.textContent = "error de connexió";
    showError(new Error("No es pot connectar al servidor: " + e.message + " (comprova el password del navegador)"));
    return;
  }
  // the learner agent must exist on this server
  const agents = await api("/agent").catch(() => []);
  if (!agents?.some?.((a) => (a.name || a.id) === AGENT)) {
    showError(new Error("L'agent 'learner' no existeix en aquest servidor"));
    return;
  }
  await initTts(); // before the first render, so 🔊 appears on the history too
  await ensureSession();
  const empty = await renderHistory();
  refreshPace(); // a reload mid-session must not lose the count
  lastActivity = Date.now(); // short safety-poll window in case a turn is already running
  openSSE();
  inputEl.focus();
  if (empty) {
    // auto-start: greet right away, unless the profile is not set up yet
    const cmd = await initialCommand();
    if (cmd) runCommand(cmd);
    else showSetupNotice();
  }
}

// ---- visual progress dashboard (modal) -------------------------------------

const progressOverlay = $("#progress-overlay");
const progressBody = $("#progress-body");

const SKILL_LABELS = {
  writing: "Escriptura",
  speaking: "Expressió oral",
  vocabulary: "Vocabulari",
  reading: "Lectura",
  listening: "Comprensió oral",
};

function skillLabel(name) {
  return SKILL_LABELS[name] || String(name || "—");
}

function stars(level) {
  const n = Math.max(0, Math.min(5, Math.round(Number(level) || 0)));
  return "★".repeat(n) + "☆".repeat(5 - n);
}

function fmtPct(v) {
  return typeof v === "number" && Number.isFinite(v) ? v + "%" : "—";
}

function shortDate(d) {
  const s = String(d || "");
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? `${m[2]}-${m[3]}` : esc(s || "—");
}

function prettyId(id) {
  return String(id || "").replace(/_/g, " ");
}

// ---- the learner's path (bar towards the level) ------------------------------
// Data from /api/fluent/path (hooks/curriculum.py json). The learner sees a
// plain view: bar, what is being worked on, states in words. What could
// discourage (stalled, forgotten, per-competence accuracy) sits in a folded
// "Detall (docent)" block. Pure functions: no DOM, no fetch.
function pathBarPct(it) {
  if (!it) return 0;
  // Server-computed continuous score (hooks/curriculum.py display_score):
  // grows with real same-day effort but stays capped below full until
  // practice is spread over enough days -- falls back to the old n/need
  // ratio only for a payload that predates this field.
  if (typeof it.pct === "number") return Math.max(0, Math.min(100, Math.round(it.pct)));
  if (it.state === "consolidated" || it.state === "mastered") return 100;
  if (it.state === "unseen" || !(it.need > 0)) return 0;
  return Math.max(0, Math.min(99, Math.round((100 * (Number(it.n) || 0)) / it.need)));
}

function pathCheckpointText(p) {
  if (p.checkpoint === "promoted" && p.promotion) {
    const c = p.promotion.carried ? ` · ${p.promotion.carried} competències per reforçar` : "";
    return `🎉 Nivell ${esc(p.promotion.achieved)} assolit el ${esc(p.promotion.date)}${c}`;
  }
  if (p.checkpoint === "ready") return `✅ Ja pots fer la prova de nivell ${esc(p.level)}`;
  const n = Number(p.checkpoint_pending) || 0;
  return n > 0
    ? `Prova de nivell: encara hi ha ${n} competències bàsiques per començar a practicar`
    : "Prova de nivell: falta consolidar el que has començat";
}

// The course is over: the level is certified and a new course starts. Said once.
function renderCourseNotice(n) {
  if (!n || n.type !== "course_completed") return "";
  const pct = typeof n.pct === "number" ? ` Resultat de la prova: <strong>${esc(Math.round(n.pct))}%</strong>.` : "";
  const next = n.next_level
    ? `<p>Comença un curs nou: <strong>${esc(n.level)} → ${esc(n.next_level)}</strong>. La barra torna a zero i no es pot tornar enrere. El que has après es manté i el repàs d'errades continua.</p>`
    : "<p>Has arribat al teu objectiu.</p>";
  const weak = Array.isArray(n.weak) && n.weak.length
    ? `<p class="path-line">Per reforçar: ${n.weak.map((w) => esc(prettyId(w))).join(" · ")}</p>` : "";
  return `<h2 id="course-title">🎉 Has assolit el nivell ${esc(n.level)}</h2><p>${pct.trim()}</p>${next}${weak}`;
}

// The level test is offered when the server says the learner is ready (or one is running).
function pathCheckpointOffer(p) {
  if (!p || !p.available || p.checkpoint === "promoted") return null;
  const run = p.checkpoint_run || {};
  if (run.active) return { label: `Continua la prova de nivell (pregunta ${run.i}/${run.total})` };
  if (p.checkpoint === "ready" && !(p.checkpoint_wait_until && p.checkpoint_wait_until > (p.as_of || ""))) {
    return { label: `Fes la prova de nivell ${p.level}` };
  }
  return null;
}

function renderPathMini(p) {
  if (!p || !p.available) return null;
  const pct = Math.max(0, Math.min(100, Number(p.pct) || 0));
  return {
    html: `<span class="path-mini-bar"><i style="width:${pct}%"></i></span>${esc(Math.round(pct))}%`,
    title: `Camí cap al ${p.level}: ${Math.round(pct)}% · ${p.core_done}/${p.core_total} competències assolides`,
  };
}

function renderPathAdmin(a) {
  if (!a) return "";
  const eta = typeof a.eta_days === "number" ? `~${a.eta_days} dies al ritme actual` : "sense estimació encara";
  const alerts = Array.isArray(a.alerts) && a.alerts.length
    ? `<ul class="path-alerts">${a.alerts.map((x) => `<li>⚠️ ${esc(x)}</li>`).join("")}</ul>`
    : '<p class="p-empty">Cap alerta (res estancat ni oblidat).</p>';
  const hist = Array.isArray(a.history) && a.history.length
    ? a.history.map((h) => `<div class="week-row"><span>${shortDate(h.day)}</span><span class="wm">${esc(h.pct)}%</span></div>`).join("")
    : '<p class="p-empty">Encara no hi ha evolució.</p>';
  const rows = (Array.isArray(a.rows) ? a.rows : []).map((r) =>
    `<tr><td>${esc(r.name)}</td><td>${esc(r.state)}</td><td>${esc(r.n)}/${esc(r.need)}</td>` +
    `<td>${r.acc_all == null ? "—" : esc(r.acc_all) + "%"}</td><td>${r.acc_recent == null ? "—" : esc(r.acc_recent) + "%"}</td>` +
    `<td>${shortDate(r.last_day)}</td><td>${esc(r.depth)}·${esc(r.weight)}</td>` +
    `<td>${r.bank_total == null ? "—" : `${r.bank_unseen <= (a.bank_low_at ?? 3) ? "⚠️ " : ""}${esc(r.bank_unseen)}/${esc(r.bank_total)}`}</td></tr>`).join("");
  const cps = Array.isArray(a.checkpoints) && a.checkpoints.length
    ? a.checkpoints.map((c) => `<div class="week-row"><span>${esc(c.date || "—")}</span><span class="wm">${esc(c.pct ?? "—")}% · ${esc(c.result || "—")}</span></div>`).join("")
    : '<p class="p-empty">Cap prova de nivell feta.</p>';
  return `<details class="path-admin"><summary>Detall (docent)</summary>
    <p class="path-line">Estimació per arribar al nivell: <strong>${esc(eta)}</strong></p>
    ${alerts}
    <h4>Evolució (setmanal)</h4>${hist}
    <h4>Per competència</h4>
    <div class="path-scroll"><table class="path-table"><thead><tr><th>Competència</th><th>Estat</th><th>Resp.</th><th>Encert</th><th>Recent</th><th>Últim</th><th>Prof.·pes</th><th title="Exercicis del banc que encara no ha vist / total">Banc nous</th></tr></thead><tbody>${rows}</tbody></table></div>
    <h4>Proves de nivell</h4>${cps}
  </details>`;
}

function renderPath(p) {
  if (!p || !p.available) return "";
  const pct = Math.max(0, Math.min(100, Number(p.pct) || 0));
  const names = (xs) => xs.map((x) => esc(x.name)).join(" · ");
  const now = Array.isArray(p.now) && p.now.length
    ? `<p class="path-line">🎯 Ara treballes: <strong>${names(p.now)}</strong></p>` : "";
  const review = Array.isArray(p.review) && p.review.length
    ? `<p class="path-line">🔁 Per repassar: ${names(p.review)}</p>` : "";
  const groups = (Array.isArray(p.sections) ? p.sections : []).map((s) => `
    <div class="path-group"><h4>${esc(s.name)}</h4>${(s.items || []).map((it) => `
      <div class="path-item st-${esc(it.state)}${it.resting ? " resting" : ""}${it.bank_low ? " bank-low" : ""}"${it.bank_low ? ' title="Queden pocs exercicis nous d\'aquest tema"' : ""}>
        <span class="path-name">${esc(it.name)}${it.core ? "" : ' <span class="chip">extra</span>'}</span>
        <span class="path-state">${esc(it.label)}${it.resting ? " · ⏸ avui" : ""}</span>
        <div class="bar"><i style="width:${pathBarPct(it)}%"></i></div>
      </div>`).join("")}</div>`).join("");
  return `<section class="path">
    <h3>El teu camí cap al ${esc(p.level)}</h3>
    ${Array.isArray(p.certified) && p.certified.length ? `<p class="path-line path-levels">${p.certified.map((c) => `<span class="chip">${esc(c.level)} ✓</span>`).join(" ")} <span class="chip">${esc(p.level)} en curs</span></p>` : ""}
    <div class="path-head"><div class="bar big"><i style="width:${pct}%"></i></div><strong>${esc(Math.round(pct))}%</strong></div>
    <p class="path-line">Assolides <strong>${esc(p.core_done)}</strong> de ${esc(p.core_total)} · en curs ${esc(p.in_progress)} · per començar ${esc(p.unseen)}</p>
    ${now}${review}
    <p class="path-line path-check">${pathCheckpointText(p)}</p>
    ${pathCheckpointOffer(p) ? `<p><button class="primary" data-start-checkpoint>🧪 ${esc(pathCheckpointOffer(p).label)}</button></p>` : ""}
    ${groups}
    ${renderPathAdmin(p.admin)}
  </section>`;
}

function openProgress() {
  progressOverlay.hidden = false;
  loadProgress();
}

function closeProgress() {
  progressOverlay.hidden = true;
}

async function loadProgress() {
  progressBody.innerHTML = '<p class="p-loading">Carregant el progrés…</p>';
  try {
    const [res, path] = await Promise.all([
      api("/fluent/progress"),
      api("/fluent/path").catch(() => null), // the path is a bonus: never blocks the panel
    ]);
    if (!res || !res.ok || !res.data) {
      throw new Error((res && res.error) || "resposta buida del servidor");
    }
    const pathData = path && path.ok ? path.data : null;
    renderPathMiniBar(pathData);
    progressBody.innerHTML = renderPath(pathData) + renderProgress(res.data);
  } catch (e) {
    progressBody.innerHTML =
      `<div class="p-error">⚠️ No s'ha pogut carregar el progrés: ${esc(errText(e))}</div>`;
  }
}

function renderProgress(d) {
  const learner = d.learner || {};
  const streak = d.streak || {};
  const ov = d.overview || {};
  const skills = Array.isArray(d.skills) ? d.skills : [];
  const patterns = d.patterns || {};
  const weak = Array.isArray(patterns.weak) ? patterns.weak : [];
  const trends = d.trends || {};
  const accuracyTrend = Array.isArray(trends.accuracy_trend) ? trends.accuracy_trend : [];
  const weekly = Array.isArray(trends.weekly) ? trends.weekly : [];
  const recent = Array.isArray(d.recent_sessions) ? d.recent_sessions : [];
  const milestones = Array.isArray(d.milestones) ? d.milestones : [];
  const achievements = Array.isArray(d.achievements) ? d.achievements : [];
  const warnings = Array.isArray(d.warnings) ? d.warnings : [];

  const lvl = [learner.current_level, learner.target_level].filter(Boolean).join(" → ");
  const headerSub = [learner.name, learner.target_language, lvl].filter(Boolean).join(" · ");

  const kpis = [
    ["🔥", streak.current_days ?? 0, "dies de ratxa"],
    ["📚", ov.total_sessions ?? 0, "sessions"],
    ["✏️", ov.total_exercises ?? 0, "exercicis"],
    ["🎯", fmtPct(ov.accuracy), "encert"],
    ["⏱️", ov.total_study_minutes ?? 0, "minuts"],
    ["🔁", ov.due_today ?? 0, "reviews avui"],
  ]
    .map(([icon, v, l]) => `<div class="kpi"><div class="v">${icon} ${esc(v)}</div><div class="l">${esc(l)}</div></div>`)
    .join("");

  const dueItems = Array.isArray(ov.due_items) ? ov.due_items : [];
  const dueChips = dueItems.length
    ? `<div class="due-chips">${dueItems.slice(0, 12).map((i) => `<span class="chip">${esc(prettyId(i))}</span>`).join("")}${dueItems.length > 12 ? `<span class="chip">+${dueItems.length - 12} més</span>` : ""}</div>`
    : "";

  const skillsHtml = skills.length
    ? skills.map((s) => {
        const m = Math.max(0, Math.min(5, Math.round(Number(s.mastery_level) || 0)));
        const meta = `${s.sessions ?? 0} sessions · ${s.exercises ?? 0} exercicis · últim: ${esc(s.last_practiced || "—")}`;
        return `<div class="skill-row">
          <div class="skill-top"><span><strong>${esc(skillLabel(s.name))}</strong> <span class="stars">${stars(m)}</span></span><span class="acc">${fmtPct(s.accuracy)}</span></div>
          <div class="bar"><i style="width:${m * 20}%"></i></div>
          <div class="skill-meta">${meta}</div>
        </div>`;
      }).join("")
    : '<p class="p-empty">Encara no hi ha dades per skill.</p>';

  const patsHtml = weak.length
    ? `<ul class="pat-list">${weak.map((p) => `<li>
        <span class="pat-id">${esc(prettyId(p.id))}</span> <span class="chip">${esc(p.category || "general")}</span>
        <div class="pat-meta">×${p.frequency ?? 0} · nivell ${p.mastery_level ?? 0}/5 · vist: ${esc(p.last_seen || "—")}</div>
      </li>`).join("")}</ul>
      ${patterns.total > weak.length ? `<div class="pat-meta">${patterns.total - weak.length} patrons més registrats</div>` : ""}`
    : '<p class="p-empty">Cap patró feble registrat. 🎉</p>';

  const trendHtml = accuracyTrend.length
    ? `<div class="trend">${accuracyTrend.map((t) => {
        const a = typeof t.accuracy === "number" && Number.isFinite(t.accuracy) ? t.accuracy : 0;
        return `<div class="t-col" title="${esc(t.date || "")}: ${a}% (${t.exercises ?? 0} ex.)">
          <div class="t-val">${a}%</div>
          <div class="t-bar" style="height:${Math.max(3, Math.round(a))}%"></div>
          <div class="t-date">${shortDate(t.date)}</div>
        </div>`;
      }).join("")}</div>`
    : '<p class="p-empty">Encara no hi ha tendència.</p>';

  const weeklyHtml = weekly.length
    ? weekly.map((w) => `<div class="week-row"><span>setmana ${shortDate(w.week_start)}</span><span class="wm">${w.sessions ?? 0} sess. · ${w.total_minutes ?? 0} min · ${fmtPct(w.accuracy)}</span></div>`).join("")
    : '<p class="p-empty">Encara no hi ha resum setmanal.</p>';

  const recentHtml = recent.length
    ? `<ul class="sess-list">${recent.map((s) => `<li>
        <strong>${esc(s.date || "—")}</strong> · ${esc(s.skills || "—")}
        <div class="sess-meta">${s.exercises ?? 0} exercicis · ${fmtPct(s.accuracy)} · ${s.duration_minutes ?? 0} min</div>
      </li>`).join("")}</ul>`
    : '<p class="p-empty">Encara no hi ha sessions.</p>';

  const achHtml = achievements.length
    ? `<ul class="ach-list">${achievements.map((a) => `<li>🏅 <strong>${esc(a.name || a.id || "")}</strong>${a.description && a.description !== (a.name || "") ? ` — ${esc(a.description)}` : ""}<div class="ach-meta">${esc(a.earned_date || "")}</div></li>`).join("")}</ul>`
    : "";
  const mileHtml = milestones.length
    ? `<ul class="ach-list">${milestones.map((m) => `<li>🚩 ${esc(m.milestone || "")} <span class="ach-meta">· ${esc(m.date || "")}</span></li>`).join("")}</ul>`
    : "";
  const fameHtml = achHtml || mileHtml
    ? `${achHtml}${mileHtml}`
    : '<p class="p-empty">Encara no hi ha fites ni assoliments.</p>';

  const warnHtml = warnings.length
    ? `<div class="p-warn">⚠️ ${warnings.map(esc).join("<br>")}</div>`
    : "";

  return `${warnHtml}
    <section><p class="progress-sub">${esc(headerSub || "—")}</p><div class="kpis">${kpis}</div>${dueChips}</section>
    <section><h3>Mastery per skill</h3>${skillsHtml}</section>
    <section><h3>Patrons febles</h3>${patsHtml}</section>
    <section><h3>Tendència d'encert</h3>${trendHtml}</section>
    <section><h3>Resum setmanal</h3>${weeklyHtml}</section>
    <section><h3>Sessions recents</h3>${recentHtml}</section>
    <section><h3>Fites i assoliments</h3>${fameHtml}</section>`;
}

progressBody.addEventListener("click", (e) => {
  if (e.target.closest && e.target.closest("[data-start-checkpoint]")) {
    closeProgress();
    runCommand("fluent-checkpoint");
  }
});
$("#progress-close").addEventListener("click", closeProgress);
$("#progress-refresh").addEventListener("click", loadProgress);
progressOverlay.addEventListener("click", (e) => {
  if (e.target === progressOverlay) closeProgress();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !progressOverlay.hidden) closeProgress();
});

// ---- composer: roomy input, contextual hints, expand, jump-to-latest ----

const DEFAULT_PLACEHOLDER = "Escriu la teva resposta…";
const MODE_PLACEHOLDERS = {
  "fluent-end": "Sessió tancada — tria una pràctica a dalt…",
  "fluent-learn": "Respon l'exercici…",
  "fluent-review": "Escriu el que recordis…",
  "fluent-vocab": "Escriu la traducció…",
  "fluent-writing": "Escriu el teu text en l'idioma meta…",
  "fluent-speaking": "Respon com en una conversa real…",
  "fluent-reading": "Respon segons el text…",
  "fluent-checkpoint": "Escriu la teva resposta…",
};
let currentMode = null;

// Display flags (tanteig): the exercise card is parked for now — in-flow
// marks carry the structure instead. Extraction is still used for paint.
const EXERCISE_CARD_ENABLED = false;
const FREEZE_FOR_CARD = false;

const currentQBtn = $("#current-q");
let trackedMsgId = null;
let latestObserver = null;
let trackedDiv = null;

// "Jump to latest" pill: it only appears when the latest tutor message has
// scrolled out of view. No duplicated text, no collapsing — the message is
// always fully readable in the flow; the pill is just a shortcut back to it.
function stopTrackingLatest() {
  trackedMsgId = null;
  markLatest(null);
  if (latestObserver) {
    latestObserver.disconnect();
    latestObserver = null;
  }
  currentQBtn.hidden = true;
}

// Green left edge on the latest tutor message ("darrera resposta").
function markLatest(div) {
  if (trackedDiv === div) return;
  if (trackedDiv) trackedDiv.classList.remove("msg-latest");
  trackedDiv = div || null;
  if (trackedDiv) trackedDiv.classList.add("msg-latest");
}

function trackLatestTutor() {
  let last = null;
  for (const [mid, entry] of renderedMsgs) {
    if (entry.role !== "user") last = { mid, entry };
  }
  if (!last || last.mid === trackedMsgId) return;
  stopTrackingLatest();
  trackedMsgId = last.mid;
  markLatest(last.entry.div);
  if (typeof IntersectionObserver === "undefined" || !last.entry.div) {
    currentQBtn.hidden = false; // no observer: always offer the jump
    return;
  }
  latestObserver = new IntersectionObserver(
    (entries) => {
      const visible = entries.some((e) => e.isIntersecting);
      currentQBtn.hidden = visible;
    },
    { root: messagesEl, threshold: 0.4 },
  );
  latestObserver.observe(last.entry.div);
}

currentQBtn.addEventListener("click", () => {
  if (!trackedMsgId) return;
  const entry = renderedMsgs.get(trackedMsgId);
  if (entry) entry.div.scrollIntoView({ behavior: "smooth", block: "center" });
});

// ---- active-exercise card (heuristic, client-side only) ----------------------
// An "open exercise" is the latest tutor message that is NOT feedback
// (feedback always carries the canonical `Score: X/10` marker), NOT the
// skill menu, and NOT a wall of text. Everything else (short prompts,
// questions, reading texts) counts as the exercise to keep pinned.
const SCORE_RE = /score\s*:\s*\d+(\.\d+)?\s*\/\s*10/i;
// A menu is not an exercise. The tutor opens with one, offers one when the
// review queue is empty, and ends with one — and each time the flow tag used to
// label it "✏️ Exercici", which tells the learner to answer a list of options.
// An exercise asks you to PRODUCE something; a menu offers you a choice.
const MENU_RE = new RegExp(
  [
    "type\\s+a\\s+number\\s+or\\s+skill\\s+name",
    "what\\s+would\\s+you\\s+like\\s+to\\s+practice",
    "what\\s+shall\\s+we\\s+do\\s+next",
    "no\\s+reviews?\\s+due",
    "spaced\\s+repetition\\s+is\\s+up\\s+to\\s+date",
    "(use|press|prem|tria)\\b[^.\\n]{0,30}\\bbut(t|ó)on",
    "want\\s+to\\s+practice\\s+something\\s+new",
  ].join("|"),
  "i",
);

// Two or more practice-button names in one message is a menu, whatever words
// surround them. Cheaper and more robust than chasing every phrasing a 14B
// model invents.
const BUTTON_MENTION_RE = /(surprise\s+me|🎲|🔁\s*review|📚\s*vocabulary|📝\s*writing|🗣️?\s*speaking|📖\s*reading|📊\s*progress)/gi;
function looksLikeMenu(text) {
  if (MENU_RE.test(text)) return true;
  const hits = String(text || "").match(BUTTON_MENTION_RE);
  return !!hits && hits.length >= 2;
}
// Session wrap-ups ("Session Complete", "Today's Stats", "Breakthroughs")
// are NEVER exercises — not even when they trail a Score.
const SESSION_END_RE = /session\s+complete|today'?s\s+stats|breakthroughs/i;
const EXERCISE_MAX_LEN = 1500;

function isOpenExercise(text) {
  if (!text) return false;
  if (SCORE_RE.test(text)) return false;
  if (looksLikeMenu(text)) return false;
  if (SESSION_END_RE.test(text)) return false;
  if (text.length > EXERCISE_MAX_LEN) return false;
  return true;
}

// The tutor bundles feedback + next question in ONE message
// ("…Score: 8/10 🎉 …Next: translate X…"). Split it: everything after the
// Score marker is candidate; the question itself starts at the first
// exercise marker ("Exercise 5:", "## Exercise", "Question:") so the
// closing commentary ("Nice use of…! Let's try one more…") stays in the
// flow and OUT of the card.
const EXERCISE_START_RE = /(exercise\s+\d+\s*:|#{1,6}\s*exercise\b|#{1,6}\s*question\b|\bquestion\s*\d*\s*:)/i;

function splitFeedbackQuestion(text) {
  const m = SCORE_RE.exec(text || "");
  if (!m) return { feedback: false, score: null, question: isOpenExercise(text) ? text : "" };
  const tail = text.slice(m.index + m[0].length).trim();
  const clean = tail.replace(/^[\s*_\-–—:;,.!?()[\]"'«»]+/, "").trim();
  let question = clean;
  const start = EXERCISE_START_RE.exec(clean);
  if (start) question = clean.slice(start.index).trim();
  if (
    question.length <= 40 ||
    looksLikeMenu(question) ||
    SESSION_END_RE.test(question) ||
    question.length > EXERCISE_MAX_LEN
  ) {
    question = "";
  }
  const sm = /(\d+(?:\.\d+)?)\s*\/\s*10/.exec(m[0]);
  return { feedback: true, score: sm ? sm[1] + "/10" : null, question };
}

const exerciseCard = $("#exercise-card");
const exerciseBody = $("#exercise-body");
let exerciseMsgId = null;

function lastTutorText() {
  let last = null;
  for (const [mid, entry] of renderedMsgs) {
    if (entry.role !== "user") last = { mid, entry };
  }
  if (!last) return null;
  const text = entryText(last.entry);
  return text ? { mid: last.mid, entry: last.entry, text } : null;
}

// The tutor is SUPPOSED to end a blanked ("___") exercise with one of these
// two exact lines (fluent-feedback-formatter's blank-marker rule) — the
// ONLY reliable ground truth. Measured live, 2026-09-22: "Type: writing"
// does NOT reliably mean "write the whole sentence" — a writing-skill
// item can still just blank a single word (e.g. "What time ___ it?" /
// skill "Telling the time" wanted just "is"). So there is no safe
// fallback to guess "full" from the Type line; guessing was producing
// wrong hints. Absent the marker line, mode is unknown and no hint is
// shown, rather than a wrong one.
const FULL_SENTENCE_RE = /\*\*Type your answer \(the complete sentence\):?\*\*/i;
const MISSING_WORD_RE = /\*\*Type your answer \(just the missing word\):?\*\*/i;

function blankExerciseMode(text) {
  if (FULL_SENTENCE_RE.test(text)) return "full";
  if (MISSING_WORD_RE.test(text)) return "word";
  return null;
}

// Measured live, 2026-09-22: a separate badge/color easily goes unseen.
// Simplest reliable signal — put the hint as plain text right on the
// "Skill:" line itself, since that line is always visible in the card.
const SKILL_LINE_RE = /^(\s*\*{0,2}skill:?\*{0,2}\s*[^\n]*)$/im;
function injectModeHint(text, mode) {
  const hint =
    mode === "full" ? " — ✍️ ESCRIU LA FRASE SENCERA!" : mode === "word" ? " — 🔤 NOMÉS LA PARAULA" : "";
  if (!hint || !SKILL_LINE_RE.test(text)) return text;
  return text.replace(SKILL_LINE_RE, (m) => m + hint);
}

function refreshExerciseCard(snap = true) {
  if (!EXERCISE_CARD_ENABLED) {
    exerciseCard.hidden = true;
    return;
  }
  const last = lastTutorText();
  const split = last ? splitFeedbackQuestion(last.text) : { question: "" };
  if (split.question) {
    exerciseMsgId = last.mid;
    const mode = blankExerciseMode(split.question);
    exerciseBody.innerHTML = md(humanizeCommands(injectModeHint(split.question, mode)));
    exerciseCard.hidden = false;
    const fullSentence = mode === "full";
    const missingWord = mode === "word";
    exerciseCard.classList.toggle("ex-full-sentence", fullSentence);
    const badge = $("#ex-mode-badge");
    const label = $("#ex-head-label");
    if (badge) {
      if (fullSentence) {
        badge.textContent = "✍️ Escriu la frase sencera";
        badge.hidden = false;
      } else if (missingWord) {
        badge.textContent = "🔤 Només la paraula";
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    }
    if (label) label.textContent = fullSentence ? "✍️ Exercici" : "✏️ Exercici";
    if (ttsReady) {
      const head = $("#ex-speak");
      if (head) {
        head.hidden = false;
        head.onclick = () => speak(sentenceOf(exerciseBody), head);
      }
    }
    // Nudge the fold so the in-flow exercise stays hidden behind the card:
    // bundled → Score marker at ~55% of the viewport; pure question →
    // message top just below the fold. Skipped if the learner scrolled up
    // on purpose (don't yank readers).
    if (snap) snapFlowForCard(last.entry, split.feedback);
  } else {
    exerciseMsgId = null;
    exerciseCard.hidden = true;
  }
}

// Position the viewport fold right after the feedback so the pinned
// question stays below it (hidden behind the card). One-shot at turn end,
// never during streaming, never when the learner is reading history.
function snapFlowForCard(entry, bundled) {
  if (!nearBottom || !entry || !entry.div) return;
  const c = messagesEl.getBoundingClientRect();
  if (bundled && entry.div.querySelectorAll) {
    const strongs = entry.div.querySelectorAll("strong");
    for (const st of strongs) {
      if (/score\s*:/i.test(st.textContent || "")) {
        const r = st.getBoundingClientRect();
        messagesEl.scrollTop += r.top - c.top - c.height * 0.55;
        return;
      }
    }
  }
  const r = entry.div.getBoundingClientRect();
  messagesEl.scrollTop += r.top - c.bottom + 24;
}

exerciseBody.addEventListener("click", () => {
  if (!exerciseMsgId) return;
  const entry = renderedMsgs.get(exerciseMsgId);
  if (entry) entry.div.scrollIntoView({ behavior: "smooth", block: "center" });
});

expandBtn.addEventListener("click", () => {
  composerEl.classList.toggle("expanded");
  if (composerEl.classList.contains("expanded")) {
    inputEl.style.height = "";
  } else {
    autosize();
  }
  inputEl.focus();
});

sendBtn.addEventListener("click", () => send(inputEl.value));
inputEl.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    send(inputEl.value);
    return;
  }
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send(inputEl.value);
  }
});
inputEl.addEventListener("input", () => {
  composerEl.classList.remove("awaiting");
  autosize();
});
document.querySelectorAll("#commands button").forEach((b) =>
  b.addEventListener("click", () => {
    // 📊 Progress opens the visual dashboard directly (no agent turn).
    if (b.dataset.cmd === "fluent-progress") {
      if (!busy) openProgress();
      return;
    }
    runCommand(b.dataset.cmd);
  }),
);
$("#new-session").addEventListener("click", newSession);

// Triple-click the brand toggles debug mode (reveals command text + tool chips).
{
  const brand = document.querySelector(".brand");
  if (brand) {
    let clicks = 0, timer = 0;
    brand.style.cursor = "pointer";
    brand.title = "FlowEd (triple-clic: mode debug)";
    brand.addEventListener("click", () => {
      clicks++;
      clearTimeout(timer);
      timer = setTimeout(() => (clicks = 0), 600);
      if (clicks >= 3) {
        clicks = 0;
        const on = localStorage.getItem("fluent.debug") === "1";
        localStorage.setItem("fluent.debug", on ? "0" : "1");
        location.reload();
      }
    });
  }
}

init();
