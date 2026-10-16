// Flash v0.1 + v1 + math — vocabulari ràpid i càlcul, sense model (docs/ENCARREC-FLASH-v0.md, v0.1, v1 i MATH).
// El progrés viu al servidor (data/flash-db.json, /api/flash/state); el navegador en guarda una còpia.
// Pantalla pròpia sota la capçalera de FlowEd: surt una paraula, l'alumne escriu
// la traducció i el client corregeix a l'instant. Dues parts: el nucli pur
// (correcció, caixes Leitner, rondes, temps) exposat a globalThis.FlashCore, que
// server/test/flash.test.ts carrega amb vm; i la interfície, que només corre quan
// hi ha un document i usa api() d'app.js.

// ---- nucli pur -------------------------------------------------------------
(function () {
  "use strict";

  // Articles que es treuen del davant. Les llistes són d'anglès (en-*); la
  // llengua de la resposta és 'en' quan és l'idioma i el natiu quan és el natiu.
  const ARTICLES = {
    en: ["the", "a", "an", "to"],
    ca: ["el", "la", "l'", "els", "les", "un", "una"],
    es: ["el", "la", "los", "las", "un", "una"],
  };
  const BOX_MAX = 2; // caixa 2 = sabuda
  const ROUND_MAX = 10;
  const TIMER_OPTIONS = [10, 20, 30]; // segons per paraula; false = sense límit
  const TIMER_DEFAULT = 20;

  // Minúscules, espais col·lapsats, sense puntuació final.
  function normalize(s) {
    return String(s ?? "")
      .replace(/’/g, "'")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase()
      .replace(/^[¿¡]+/, "")
      .replace(/[.!?;:,…]+$/, "")
      .trim();
  }

  // Sense accents (ç → c, à → a, ñ → n) per comparar.
  function fold(s) {
    return s.normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  // Treu un sol article inicial; si no en té, torna la mateixa cadena.
  function stripArticle(s, lang) {
    for (const a of ARTICLES[lang] || []) {
      if (a.endsWith("'")) {
        if (s.startsWith(a) && s.length > a.length) return s.slice(a.length);
      } else if (s.startsWith(a + " ")) {
        return s.slice(a.length + 1);
      }
    }
    return s;
  }

  // ok: encert. exact: false quan només ha passat gràcies a treure accents
  // (aleshores form és l'ortografia correcta). form: la forma acceptada que ha encertat.
  function check(answer, accepted, lang) {
    const a = stripArticle(normalize(answer), lang);
    if (!a) return { ok: false, exact: false, form: null };
    let folded = null;
    for (const raw of accepted) {
      const want = stripArticle(normalize(raw), lang);
      if (!want) continue;
      if (a === want) return { ok: true, exact: true, form: raw };
      if (folded === null && fold(a) === fold(want)) folded = raw;
    }
    if (folded !== null) return { ok: true, exact: false, form: folded };
    return { ok: false, exact: false, form: null };
  }

  // Math: el resultat com a número. Espais fora, coma o punt decimal: 72, 72,0 i 72.0 són iguals.
  function numeric(s) {
    const t = String(s ?? "").replace(/\s+/g, "").replace(/,/g, ".");
    return /^-?\d+(\.\d+)?$/.test(t) ? Number(t) : null;
  }

  // Com check(), però per valor (les operacions no tenen article ni accents).
  function checkNumber(answer, accepted) {
    const a = numeric(answer);
    if (a === null) return { ok: false, exact: true, form: null };
    for (const raw of accepted) {
      if (numeric(raw) === a) return { ok: true, exact: true, form: raw };
    }
    return { ok: false, exact: true, form: null };
  }

  // Pista del tercer pas: primera lletra i guions ("m _ _ _ _ _"; "/" és un espai).
  function hint(form, lang) {
    const s = stripArticle(normalize(form), lang);
    return [...s].map((c, i) => (c === " " ? "/" : i === 0 ? c : "_")).join(" ");
  }

  // how: 'first' (encert a la 1a), 'retry' (encert a la 2a o 3a),
  // 'revealed' (resposta mostrada, és a dir 3r error).
  function nextBox(box, how) {
    if (how === "first") return Math.min(BOX_MAX, box + 1);
    if (how === "revealed") return Math.max(0, box - 1);
    return box;
  }

  // Resultat d'una targeta a partir de l'intent: ok (encert), misses (errors
  // fins ara, sense comptar l'encert), timedOut (temps esgotat). Torna 'first',
  // 'retry', 'revealed' o null (encara es pot intentar). El temps esgotat és
  // exactament una revelació.
  function outcome(a) {
    if (a.timedOut) return "revealed";
    if (a.ok) return a.misses === 0 ? "first" : "retry";
    return a.misses >= 3 ? "revealed" : null;
  }

  // Color de la fila de punts de la ronda, segons el resultat de la targeta.
  function dotClass(how) {
    if (how === "first") return "ok";
    if (how === "retry") return "retry";
    return "err";
  }

  // Temps restant (segons) d'una targeta: no baixa de 0 ni puja del límit.
  function timeLeft(start, now, limitSec) {
    return Math.min(limitSec, Math.max(0, limitSec - (now - start) / 1000));
  }

  // Amplada de la barra (0..100) segons el temps restant.
  function barPct(left, limitSec) {
    return Math.max(0, Math.min(100, (left / limitSec) * 100));
  }

  // To de la barra: verd, ambre als últims 5 s, vermell als últims 3 s.
  function timerTone(left) {
    if (left <= 3) return "err";
    if (left <= 5) return "warn";
    return "ok";
  }

  // Preferències de l'alumne. timer: false (sense límit) | 10 | 20 | 30.
  // El valor antic `true` (cronòmetre general) passa a 20.
  function migratePrefs(raw) {
    const p = raw && typeof raw === "object" ? raw : {};
    const dir = ["nt", "tn", "mix"].includes(p.dir) ? p.dir : "nt";
    let timer = TIMER_DEFAULT;
    if (p.timer === false) timer = false;
    else if (p.timer === true) timer = 20;
    else if (TIMER_OPTIONS.includes(Number(p.timer))) timer = Number(p.timer);
    return { dir, timer };
  }

  // Punts de la ronda: 'pending' (buit), 'cur' (la targeta actual), 'ok' | 'retry' | 'err'.
  // Una targeta revelada que torna al final afegeix un punt nou al final.
  function addReturn(dots) {
    return dots.concat(["pending"]);
  }

  // Text "Paraula N de M": N és la targeta actual (o les respostes fetes si no n'hi ha), M els punts.
  function roundLabel(dots) {
    const cur = dots.indexOf("cur");
    const n = cur >= 0 ? cur + 1 : dots.filter((d) => d !== "pending").length;
    return { n, m: dots.length };
  }

  function clone(x) {
    return JSON.parse(JSON.stringify(x));
  }

  function emptyState() {
    return { version: 1, lists: {} };
  }

  // Aplica el resultat d'una targeta (només la primera presentació d'una
  // paraula en una ronda). misses = errors d'aquesta targeta.
  function recordResult(state, listId, wordId, how, misses, today) {
    const next = clone(state);
    const list = next.lists[listId] || { words: {}, closed_at: null };
    const old = list.words[wordId] || { box: 0, seen: 0, first_try: 0, misses: 0, last: null };
    list.words[wordId] = {
      box: nextBox(old.box, how),
      seen: old.seen + 1,
      first_try: old.first_try + (how === "first" ? 1 : 0),
      misses: old.misses + misses,
      last: today,
    };
    next.lists[listId] = list;
    return next;
  }

  // Quantes paraules sabudes i si la llista està tancada.
  function listStatus(list, state) {
    const entry = listEntry(state, list.id);
    const known = list.words.filter((w) => ((entry.words[w.id] || {}).box || 0) >= BOX_MAX).length;
    return { known, total: list.words.length, closed: entry.closed_at != null };
  }

  // Paraules a mig camí (caixa 1).
  function halfway(list, state) {
    const entry = listEntry(state, list.id);
    return list.words.filter((w) => (entry.words[w.id] || {}).box === 1).length;
  }

  function listEntry(state, listId) {
    const l = (state.lists || {})[listId] || {};
    return { words: l.words || {}, closed_at: l.closed_at === undefined ? null : l.closed_at };
  }

  // Totes sabudes ⇒ llista tancada (closed_at = data).
  function closeIfDone(list, state, today) {
    const st = listStatus(list, state);
    if (st.total === 0 || st.known < st.total || st.closed) return state;
    const next = clone(state);
    const l = next.lists[list.id] || { words: {}, closed_at: null };
    l.closed_at = today;
    next.lists[list.id] = l;
    return next;
  }

  // Ronda nova (màx. ROUND_MAX): primer les vistes i no sabudes (caixa més
  // baixa primer), després les no vistes en ordre de llista. Les sabudes no surten.
  function buildRound(list, state, size = ROUND_MAX) {
    const ws = listEntry(state, list.id).words;
    const seen = [];
    const fresh = [];
    list.words.forEach((w, i) => {
      const e = ws[w.id];
      if (e && e.seen > 0) {
        if (e.box < BOX_MAX) seen.push({ w, i, box: e.box });
      } else {
        fresh.push(w);
      }
    });
    seen.sort((a, b) => a.box - b.box || a.i - b.i);
    return seen.map((x) => x.w).concat(fresh).slice(0, size);
  }

  // Repàs d'una llista tancada: barrejades, no toquen l'estat.
  function repassaRound(list, size = ROUND_MAX, rand = Math.random) {
    const a = list.words.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a.slice(0, size);
  }

  // Hi ha progrés a l'estat (alguna paraula vista o alguna ronda)?
  function hasProgress(state) {
    const lists = (state && state.lists) || {};
    return Object.values(lists).some((l) => Object.keys((l && l.words) || {}).length > 0);
  }

  // Rondes fetes avui (no de repàs): el ⚡ de la barra en vol una.
  function roundsOn(state, day) {
    return Number(((state && state.rounds_by_day) || {})[day]) || 0;
  }

  // Una ronda més acabada el dia `day` (torna un estat nou).
  function countRound(state, day) {
    const next = clone(state);
    next.rounds_by_day = next.rounds_by_day || {};
    next.rounds_by_day[day] = (Number(next.rounds_by_day[day]) || 0) + 1;
    return next;
  }

  globalThis.FlashCore = {
    BOX_MAX,
    ROUND_MAX,
    TIMER_OPTIONS,
    TIMER_DEFAULT,
    normalize,
    fold,
    stripArticle,
    check,
    hint,
    nextBox,
    outcome,
    dotClass,
    timeLeft,
    barPct,
    timerTone,
    migratePrefs,
    addReturn,
    roundLabel,
    checkNumber,
    emptyState,
    recordResult,
    listStatus,
    halfway,
    closeIfDone,
    buildRound,
    repassaRound,
    hasProgress,
    roundsOn,
    countRound,
  };
})();

// ---- interfície ------------------------------------------------------------
(function () {
  "use strict";
  if (typeof document === "undefined") return; // node: només el nucli

  const C = globalThis.FlashCore;
  const TARGET_CODE = "en"; // les llistes són d'anglès (en-*)
  const NATIVE_NAME = { ca: "català", es: "castellà" };
  const PREFS_KEY = "flowed.flash.prefs";
  const DIR_LABEL = { nt: "Natiu → idioma", tn: "Idioma → natiu", mix: "Barrejat" };
  const TIME_LABEL = { off: "Desactivat", 10: "10 s", 20: "20 s", 30: "30 s" };
  // Llistes de math (kind "math"): operació → resultat, sense direcció ni article.
  const isMath = (l) => !!l && l.kind === "math";
  const noun = (l) => (isMath(l) ? "operació" : "paraula");
  const TIMEOUT_PAUSE_MS = 2000; // temps esgotat: passa sola a la següent

  let screen = null; // #flash-screen
  let data = null; // resposta de /api/flash/lists
  let state = null; // progrés de les llistes (localStorage)
  let stateKey = "";
  let prefs = loadPrefs();
  let selected = null; // id de la llista triada al menú
  let view = "menu"; // menu | card | summary
  let round = null; // ronda en curs
  let card = null; // targeta en curs
  let session = null; // rondes fetes des d'obrir Flash (per a la traça al xat)
  let advanceTimer = 0;
  let clockTimer = 0;

  // ---- persistència per visitant (tot dins try/catch) ----------------------
  function loadPrefs() {
    try {
      return C.migratePrefs(JSON.parse(localStorage.getItem(PREFS_KEY) || "null"));
    } catch {
      /* sense emmagatzematge: valors per defecte */
    }
    return C.migratePrefs(null);
  }

  function savePrefs() {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    } catch {
      /* la pàgina funciona igual */
    }
  }

  function loadState(key) {
    try {
      const s = JSON.parse(localStorage.getItem(key) || "null");
      if (s && s.version === 1 && s.lists) return s;
    } catch {
      /* il·legible: es comença de zero */
    }
    return C.emptyState();
  }

  // El progrés és al servidor (data/flash-db.json). El navegador en guarda una
  // còpia, i una marca si l'última pujada ha fallat (aleshores és més nova que el servidor).
  function pendingKey() {
    return `${stateKey}|pending`;
  }

  function readPending() {
    try {
      return localStorage.getItem(pendingKey()) === "1";
    } catch {
      return false;
    }
  }

  function writePending(on) {
    try {
      if (on) localStorage.setItem(pendingKey(), "1");
      else localStorage.removeItem(pendingKey());
    } catch {
      /* sense emmagatzematge: el servidor s'actualitza igualment en el desat següent */
    }
  }

  // Cada desat envia l'estat sencer (PUT, escriptura atòmica al servidor). Les pujades
  // van en fila perquè no es creuin; si una falla, el desat següent ho torna a provar.
  let pushChain = Promise.resolve();
  function pushState() {
    if (!data || !data.enabled) return;
    pushChain = pushChain
      .then(() => api("/flash/state", { method: "PUT", body: state }))
      .then(
        () => writePending(false),
        (err) => {
          writePending(true);
          console.warn("flash: el servidor no ha desat el progrés, es tornarà a provar", err);
        },
      );
  }

  function saveState() {
    try {
      localStorage.setItem(stateKey, JSON.stringify(state));
    } catch {
      /* la pàgina funciona igual */
    }
    pushState();
  }

  // Al obrir: el servidor manda. Si és buit i el navegador té progrés (el de v0/v0.1),
  // es puja una sola vegada. Si la darrera pujada ha fallat, el navegador és el més nou.
  async function loadServerState(local) {
    let remote = null;
    try {
      remote = await api("/flash/state");
    } catch (err) {
      console.warn("flash: sense servidor, es treballa amb la còpia del navegador", err);
    }
    if (!remote || !remote.ok || !remote.enabled) {
      return local; // sense servidor: la còpia local, i el desat següent ho pujarà
    }
    if (readPending() || (!C.hasProgress(remote.state) && C.hasProgress(local))) {
      pushState();
      return local;
    }
    return remote.state;
  }

  // ---- utilitats -----------------------------------------------------------
  function escText(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  function today() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  const q = (sel) => (screen ? screen.querySelector(sel) : null);

  function clearAdvance() {
    clearTimeout(advanceTimer);
    advanceTimer = 0;
  }

  function stopClock() {
    clearInterval(clockTimer);
    clockTimer = 0;
  }

  // Comença el compte enrere de la targeta (només si hi ha límit).
  function startTimer() {
    stopClock();
    if (!card || !card.limit) return;
    clockTimer = setInterval(tickTimer, 200);
    tickTimer();
  }

  // Barra que s'escurça i segons. Els errors no reinicien el temps.
  function tickTimer() {
    if (!card || card.done || !card.limit) return stopClock();
    const left = C.timeLeft(card.start, Date.now(), card.limit);
    const box = q("#flash-timer");
    if (box) box.className = `flash-timer ${C.timerTone(left)}`;
    const bar = q("#flash-tbar");
    if (bar) bar.style.width = `${C.barPct(left, card.limit)}%`;
    const sec = q("#flash-tsec");
    if (sec) sec.textContent = String(Math.ceil(left));
    if (left <= 0) resolve(C.outcome({ ok: false, misses: card.misses, timedOut: true }), null, true);
  }

  // ---- menú ----------------------------------------------------------------
  function isOpen(l) {
    return !C.listStatus(l, state).closed;
  }

  // Després d'una ronda: la llista tancada cedeix la selecció a la següent oberta.
  function pickSelection(prev) {
    const lists = data.lists;
    const cur = lists.find((l) => l.id === prev);
    if (cur && isOpen(cur)) return cur.id;
    if (cur) {
      const after = lists.slice(lists.indexOf(cur) + 1).find(isOpen);
      if (after) return after.id;
    }
    const first = lists.find(isOpen);
    return (first || lists[0] || { id: null }).id;
  }

  function dirButton(key) {
    const on = prefs.dir === key;
    return `<button type="button" data-dir="${key}" aria-pressed="${on}">${escText(DIR_LABEL[key])}</button>`;
  }

  function timeButton(v) {
    const key = v === false ? "off" : String(v);
    return `<button type="button" data-timer="${key}" aria-pressed="${prefs.timer === v}">${escText(TIME_LABEL[key])}</button>`;
  }

  function setActive(on) {
    const b = document.querySelector('#commands button[data-cmd="math-flash"]');
    if (!b) return;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  }

  function renderMenu() {
    view = "menu";
    round = null;
    card = null;
    clearAdvance();
    stopClock();
    const lists = data.lists;
    const math = lists.length > 0 && lists.every(isMath);
    const sel = lists.find((l) => l.id === selected);
    const selClosed = sel ? C.listStatus(sel, state).closed : false;
    const rows = lists
      .map((l) => {
        const st = C.listStatus(l, state);
        const pct = st.total ? Math.round((st.known / st.total) * 100) : 0;
        const cls = ["flash-row", st.closed ? "closed" : "", l.id === selected ? "sel" : ""].join(" ").trim();
        return `<button type="button" class="${cls}" data-list="${escText(l.id)}" aria-pressed="${l.id === selected}">
          <span class="flash-mark">${st.closed ? "✓" : ""}</span>
          <span class="flash-row-title">${escText(l.title)}</span>
          <span class="flash-bar" aria-hidden="true"><span style="width:${pct}%"></span></span>
          <span class="flash-count">${st.known}/${st.total}</span>
        </button>`;
      })
      .join("");
    screen.innerHTML = `
      <div class="flash-panel">
        <div class="flash-head">
          <h2>⚡ Flash <span class="flash-sub">${escText(math ? "Matemàtiques" : data.target)} · ${escText(data.level)}</span></h2>
        </div>
        <div class="flash-body">
          ${math ? "" : `<p class="flash-label">Direcció</p>
          <div class="flash-seg" role="group" aria-label="Direcció">${dirButton("nt")}${dirButton("tn")}${dirButton("mix")}</div>`}
          <p class="flash-label">Temps per ${noun(lists[0] || {})}</p>
          <div class="flash-seg" role="group" aria-label="Temps per ${noun(lists[0] || {})}">${timeButton(false)}${C.TIMER_OPTIONS.map(timeButton).join("")}</div>
          <p class="flash-label">Llistes</p>
          <div class="flash-lists">${rows || '<p class="flash-note">Encara no hi ha llistes.</p>'}</div>
          <div class="flash-actions">
            <button type="button" class="primary" data-act="go"${sel ? "" : " disabled"}>${selClosed ? "Repassa" : "Comença"}</button>
          </div>
        </div>
      </div>`;
  }

  // ---- ronda ---------------------------------------------------------------
  function makeCard(item) {
    const math = isMath(round.list);
    const dir = math ? "nt" : round.dir === "mix" ? (Math.random() < 0.5 ? "nt" : "tn") : round.dir;
    const w = item.word;
    const nt = dir === "nt";
    return {
      word: w,
      returned: item.returned,
      dot: item.dot,
      dir,
      math,
      prompt: (math ? w.prompt : nt ? w.native[0] : w.target[0]) || "—",
      accepted: nt ? w.target : w.native,
      lang: math ? null : nt ? TARGET_CODE : data.nativeCode,
      limit: round.timer || 0, // segons; 0 = sense límit
      start: Date.now(),
      misses: 0,
      done: false,
      timedOut: false,
      how: null,
      form: null,
      exact: true,
    };
  }

  function startRound(listId, repassa) {
    const list = data.lists.find((l) => l.id === listId);
    if (!list) return renderMenu();
    selected = listId;
    const review = repassa || C.listStatus(list, state).closed;
    let words = review ? C.repassaRound(list) : C.buildRound(list, state);
    if (!words.length) words = C.repassaRound(list);
    if (!words.length) return renderMenu();
    round = {
      list,
      repassa: review,
      dir: prefs.dir,
      timer: prefs.timer,
      known0: C.listStatus(list, state).known,
      dots: words.map(() => "pending"),
      queue: words.map((w, i) => ({ word: w, returned: false, dot: i })),
      presented: 0,
      first: 0,
      errors: 0,
      streak: 0,
      best: 0,
      timeSum: 0,
      timed: 0,
    };
    advance();
  }

  // Els punts de la ronda i "Paraula N de M".
  function paintProgress() {
    const prog = q("#flash-prog");
    const dots = q("#flash-dots");
    if (!prog || !dots || !round) return;
    const { n, m } = C.roundLabel(round.dots);
    const unit = isMath(round.list) ? "Operació" : "Paraula";
    prog.textContent = `${unit} ${n} de ${m}${round.repassa ? " · repàs" : ""}`;
    dots.innerHTML = round.dots.map((d) => `<span class="flash-dot ${d}"></span>`).join("");
  }

  function renderCard() {
    view = "card";
    const dirLabel = card.math
      ? "Calcula"
      : card.dir === "nt"
        ? `Escriu-ho en ${data.target}`
        : `Escriu-ho en ${NATIVE_NAME[data.nativeCode] || data.nativeCode}`;
    screen.innerHTML = `
      <div class="flash-panel flash-play">
        <div class="flash-top">
          <button type="button" class="ghost" data-act="menu">‹ Menú</button>
          <span class="flash-prog" id="flash-prog"></span>
        </div>
        <div class="flash-dots" id="flash-dots" aria-hidden="true"></div>
        <div class="flash-stage" id="flash-stage">
          <p class="flash-dir">${escText(dirLabel)}</p>
          <div class="flash-word">${escText(card.prompt)}</div>
          <div class="flash-timer ok" id="flash-timer"${card.limit ? "" : " hidden"}>
            <div class="flash-tbar"><i id="flash-tbar"></i></div>
            <span class="flash-tsec" id="flash-tsec"></span>
          </div>
          <div class="flash-hint" id="flash-hint"></div>
          <div class="flash-feedback" id="flash-feedback" aria-live="polite"></div>
        </div>
        <form class="flash-form" id="flash-form" autocomplete="off">
          <input id="flash-input" type="text"${card.math ? ' inputmode="numeric" aria-label="Resultat"' : ' aria-label="Traducció"'} autocomplete="off" autocapitalize="off" spellcheck="false">
          <button type="submit" class="primary" id="flash-ok">Comprova</button>
        </form>
      </div>`;
    paintProgress();
    paintCard(null);
    startTimer();
    q("#flash-input").focus();
  }

  // Pinta la targeta segons el seu estat (errors, pista, resultat).
  function paintCard(flag) {
    const stage = q("#flash-stage");
    if (!stage || !card) return;
    stage.classList.remove("shake", "ok", "reveal");
    if (flag === "shake") {
      void stage.offsetWidth; // reinicia l'animació
      stage.classList.add("shake");
    }
    const fb = q("#flash-feedback");
    const hint = q("#flash-hint");
    const btn = q("#flash-ok");
    if (!card.done) {
      fb.textContent = card.misses === 0 ? "" : card.misses === 1 ? "No és aquesta. Torna-ho a provar." : "Encara no. Mira la pista.";
      hint.textContent = card.misses >= 2 ? C.hint(card.accepted[0], card.lang) : "";
      btn.textContent = "Comprova";
      return;
    }
    stage.classList.add(card.how === "revealed" ? "reveal" : "ok");
    hint.textContent = "";
    const shown = card.how === "revealed" ? card.accepted[0] : card.form;
    const others = card.accepted.filter((x) => x !== shown);
    let text;
    if (card.timedOut) text = `⏱ Temps! La resposta és «${card.accepted[0]}».`;
    else if (card.how === "revealed") text = `La resposta és «${card.accepted[0]}».`;
    else text = "✓ Correcte" + (card.exact ? "" : ` · l'ortografia és «${card.form}»`);
    if (others.length) text += ` També: ${others.join(", ")}.`;
    if (card.how === "revealed") {
      text += (card.returned ? "" : " Torna al final de la ronda.") + (card.timedOut ? "" : " Enter per continuar.");
    }
    fb.textContent = text;
    btn.textContent = "Següent";
  }

  // Una resposta de l'alumne: encert, error (1r, 2n) o 3r error (resposta mostrada).
  function attempt(text) {
    if (!card || card.done || !String(text).trim()) return;
    const res = card.math ? C.checkNumber(text, card.accepted) : C.check(text, card.accepted, card.lang);
    if (res.ok) {
      resolve(C.outcome({ ok: true, misses: card.misses }), res);
      return;
    }
    card.misses += 1;
    const how = C.outcome({ ok: false, misses: card.misses });
    if (how) {
      resolve(how, null);
      return;
    }
    const input = q("#flash-input");
    if (input) {
      input.value = "";
      input.focus();
    }
    paintCard("shake");
  }

  // Final d'una targeta. timedOut: el temps s'ha acabat (com una revelació, però passa sola).
  function resolve(how, res, timedOut = false) {
    const r = round;
    stopClock();
    card.done = true;
    card.how = how;
    card.timedOut = timedOut;
    if (res) {
      card.form = res.form;
      card.exact = res.exact;
    }
    if (!timedOut) {
      r.timeSum += Date.now() - card.start;
      r.timed += 1;
    }
    if (card.dot !== undefined) r.dots[card.dot] = C.dotClass(how);
    if (!card.returned) {
      r.presented += 1;
      if (how === "first") {
        r.first += 1;
        r.streak += 1;
        r.best = Math.max(r.best, r.streak);
      } else {
        r.streak = 0;
      }
      if (!r.repassa) {
        state = C.recordResult(state, r.list.id, card.word.id, how, card.misses, today());
        state = C.closeIfDone(r.list, state, today());
        saveState();
      }
    }
    r.errors += card.misses;
    // La revelada torna una vegada al final de la ronda, amb un punt nou.
    if (how === "revealed" && !card.returned) {
      r.dots = C.addReturn(r.dots);
      r.queue.push({ word: card.word, returned: true, dot: r.dots.length - 1 });
    }
    paintCard(null);
    paintProgress();
    if (how !== "revealed") {
      // Amb altres respostes vàlides es llegeixen una mica més.
      const more = card.accepted.some((x) => x !== card.form);
      advanceTimer = setTimeout(advance, more ? 1800 : 1100);
    } else if (timedOut) {
      advanceTimer = setTimeout(advance, TIMEOUT_PAUSE_MS);
    }
  }

  function advance() {
    clearAdvance();
    if (!round) return renderMenu();
    if (!round.queue.length) return finishRound();
    const item = round.queue.shift();
    round.dots[item.dot] = "cur";
    card = makeCard(item);
    renderCard();
  }

  function finishRound() {
    const r = round;
    stopClock();
    clearAdvance();
    view = "summary";
    const st = C.listStatus(r.list, state);
    const closedNow = st.closed;
    const half = C.halfway(r.list, state);
    const idx = data.lists.indexOf(r.list);
    const nextOpen = data.lists.slice(idx + 1).find(isOpen) || null;
    if (!r.repassa) {
      selected = pickSelection(r.list.id);
      state = C.countRound(state, today()); // compta per al ⚡ d'avui
      saveState();
    }
    const avg = r.timed ? `${((r.timeSum / r.timed) / 1000).toFixed(1).replace(".", ",")} s` : "—";
    // Compta la ronda per a la traça del xat (una línia en tancar Flash).
    session = session || { rounds: 0, first: 0, presented: 0, titles: [], known: 0, total: 0, math: false };
    session.math = isMath(r.list);
    session.rounds += 1;
    session.first += r.first;
    session.presented += r.presented;
    if (!session.titles.includes(r.list.title)) session.titles.push(r.list.title);
    session.known = st.known;
    session.total = st.total;
    screen.innerHTML = `
      <div class="flash-panel">
        <div class="flash-head">
          <h2>${closedNow && !r.repassa ? "Llista completa ✓" : "Ronda acabada"}</h2>
        </div>
        <div class="flash-body">
          <p class="flash-sum-title">${escText(r.list.title)}</p>
          <ul class="flash-stats">
            <li><span>Sabudes</span><strong>${r.known0} → ${st.known} de ${st.total}</strong></li>
            <li><span>A mig camí</span><strong>${half}</strong></li>
            <li><span>Encerts a la primera</span><strong>${r.first}/${r.presented}</strong></li>
            <li><span>Errors</span><strong>${r.errors}</strong></li>
            <li><span>Millor ratxa</span><strong>${r.best}</strong></li>
            ${r.timer ? `<li><span>Temps mitjà per ${noun(r.list)}</span><strong>${avg}</strong></li>` : ""}
          </ul>
          <p class="flash-note">Una ${noun(r.list)} queda sabuda quan l'encertes a la primera en dues rondes.</p>
          ${r.repassa ? '<p class="flash-note">Repàs: el progrés no canvia.</p>' : ""}
          <div class="flash-actions">
            <button type="button" class="primary" data-act="again">Una altra ronda</button>
            ${nextOpen ? `<button type="button" data-act="start" data-list="${escText(nextOpen.id)}">Següent llista</button>` : ""}
            <button type="button" data-act="menu">Menú</button>
          </div>
        </div>
      </div>`;
  }

  // Línia de la traça al xat: totes les rondes d'aquesta obertura de Flash.
  function traceText(s) {
    const who = s.titles.length === 1 ? s.titles[0] : `${s.titles.length} llistes`;
    if (s.math) return `⚡ Flash · ${who} — ${s.first}/${s.presented} a la primera · operacions sabudes ${s.known}/${s.total}`;
    return `⚡ Flash · ${who} — ${s.first}/${s.presented} a la primera · sabudes ${s.known}/${s.total}`;
  }

  // Només visual i local: no va al servidor ni pel canal d'enviament, i no és un missatge del tutor.
  function appendTrace(text) {
    const box = document.querySelector("#messages");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "flash-trace";
    el.textContent = text;
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
  }

  // ---- entrada -------------------------------------------------------------
  function ensureScreen() {
    if (screen) return;
    screen = document.createElement("div");
    screen.id = "flash-screen";
    screen.className = "flash-screen";
    screen.hidden = true;
    screen.setAttribute("role", "dialog");
    screen.setAttribute("aria-label", "Flash — vocabulari ràpid");
    document.body.appendChild(screen);
    screen.addEventListener("click", onClick);
    screen.addEventListener("submit", onSubmit);
    screen.addEventListener("keydown", onKey);
  }

  function onClick(e) {
    const t = e.target.closest ? e.target.closest("[data-act],[data-dir],[data-timer],[data-list]") : null;
    if (!t) return;
    if (t.dataset.dir) {
      prefs.dir = t.dataset.dir;
      savePrefs();
      return renderMenu();
    }
    if (t.dataset.timer) {
      prefs.timer = t.dataset.timer === "off" ? false : Number(t.dataset.timer);
      savePrefs();
      return renderMenu();
    }
    if (t.dataset.list && !t.dataset.act) {
      selected = t.dataset.list;
      return renderMenu();
    }
    switch (t.dataset.act) {
      case "menu":
        return renderMenu();
      case "go":
        return startRound(selected, false);
      case "again":
        return startRound(round ? round.list.id : selected, false);
      case "start":
        return startRound(t.dataset.list, false);
    }
  }

  function onSubmit(e) {
    if (!e.target || e.target.id !== "flash-form") return;
    e.preventDefault();
    if (!card) return;
    if (card.done) return advance();
    attempt(q("#flash-input").value);
  }

  function onKey(e) {
    if (e.key !== "Escape") return;
    if (view === "menu") closeFlash();
    else renderMenu();
  }

  // Tanca Flash (guardant l'estat). Si s'ha acabat almenys una ronda, deixa una línia al xat.
  function closeFlash() {
    const wasOpen = isFlashOpen();
    clearAdvance();
    stopClock();
    round = null;
    card = null;
    if (session && session.rounds > 0) appendTrace(traceText(session));
    session = null;
    if (screen) screen.hidden = true;
    setActive(false);
    if (wasOpen && typeof refreshFlashBadge === "function") refreshFlashBadge(); // app.js: el ⚡ d'avui
  }

  function isFlashOpen() {
    return !!screen && !screen.hidden;
  }

  async function openFlash() {
    ensureScreen();
    screen.hidden = false;
    setActive(true);
    screen.innerHTML = '<div class="flash-panel"><p class="flash-note">Carregant…</p></div>';
    try {
      data = await api("/flash/lists");
    } catch (err) {
      data = null;
      console.warn("flash:", err);
    }
    if (!data || !data.ok || !data.enabled) {
      screen.innerHTML = `<div class="flash-panel"><div class="flash-head"><h2>⚡ Flash</h2></div><p class="flash-note">Flash no està disponible per a aquest perfil.</p></div>`;
      return;
    }
    stateKey = `flowed.flash.v1|${window.__FLOWED_DOMAIN || "language"}|${data.target}|${data.nativeCode}`;
    state = loadState(stateKey);
    state = await loadServerState(state);
    selected = pickSelection(null);
    renderMenu();
  }

  // ⚡ de la barra: obre o tanca Flash.
  function toggleFlash() {
    if (isFlashOpen()) closeFlash();
    else openFlash();
  }

  globalThis.openFlash = openFlash;
  globalThis.closeFlash = closeFlash;
  globalThis.toggleFlash = toggleFlash;
})();
