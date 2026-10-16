// Flash v0 — vocabulari ràpid, sense model (docs/ENCARREC-FLASH-v0.md).
// Pantalla pròpia: surt una paraula, l'alumne escriu la traducció i el client
// corregeix a l'instant. Dues parts: el nucli pur (correcció, caixes Leitner,
// rondes) exposat a globalThis.FlashCore, que server/test/flash.test.ts carrega
// amb vm; i la interfície, que només corre quan hi ha un document i usa api()
// d'app.js.

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

  globalThis.FlashCore = {
    BOX_MAX,
    ROUND_MAX,
    normalize,
    fold,
    stripArticle,
    check,
    hint,
    nextBox,
    emptyState,
    recordResult,
    listStatus,
    closeIfDone,
    buildRound,
    repassaRound,
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

  let screen = null; // #flash-screen
  let data = null; // resposta de /api/flash/lists
  let state = null; // progrés de les llistes (localStorage)
  let stateKey = "";
  let prefs = loadPrefs();
  let selected = null; // id de la llista triada al menú
  let view = "menu"; // menu | card | summary
  let round = null; // ronda en curs
  let card = null; // targeta en curs
  let advanceTimer = 0;
  let clockTimer = 0;

  // ---- persistència per visitant (tot dins try/catch) ----------------------
  function loadPrefs() {
    try {
      const p = JSON.parse(localStorage.getItem(PREFS_KEY) || "null");
      if (p && ["nt", "tn", "mix"].includes(p.dir)) return { dir: p.dir, timer: p.timer === true };
    } catch {
      /* sense emmagatzematge: valors per defecte */
    }
    return { dir: "nt", timer: false };
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

  function saveState() {
    try {
      localStorage.setItem(stateKey, JSON.stringify(state));
    } catch {
      /* la pàgina funciona igual */
    }
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

  function fmt(sec) {
    return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
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

  function startClock() {
    stopClock();
    if (!prefs.timer) return;
    clockTimer = setInterval(tick, 1000);
    tick();
  }

  function tick() {
    const el = q("#flash-clock");
    if (!el || !round) return;
    el.hidden = false;
    el.textContent = fmt(Math.floor((Date.now() - round.start) / 1000));
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

  function renderMenu() {
    view = "menu";
    round = null;
    card = null;
    clearAdvance();
    stopClock();
    const lists = data.lists;
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
          <h2>⚡ Flash <span class="flash-sub">${escText(data.target)} · ${escText(data.level)}</span></h2>
          <button type="button" class="ghost" data-act="close" title="Tanca">✕</button>
        </div>
        <div class="flash-body">
          <p class="flash-label">Direcció</p>
          <div class="flash-seg" role="group" aria-label="Direcció">${dirButton("nt")}${dirButton("tn")}${dirButton("mix")}</div>
          <label class="flash-check-row"><input type="checkbox" data-act="timer"${prefs.timer ? " checked" : ""}> Cronòmetre</label>
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
    const dir = round.dir === "mix" ? (Math.random() < 0.5 ? "nt" : "tn") : round.dir;
    const w = item.word;
    const nt = dir === "nt";
    return {
      word: w,
      returned: item.returned,
      dir,
      prompt: (nt ? w.native[0] : w.target[0]) || "—",
      accepted: nt ? w.target : w.native,
      lang: nt ? TARGET_CODE : data.nativeCode,
      misses: 0,
      done: false,
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
      start: Date.now(),
      queue: words.map((w) => ({ word: w, returned: false })),
      presented: 0,
      first: 0,
      errors: 0,
      streak: 0,
      best: 0,
    };
    advance();
  }

  function renderCard() {
    view = "card";
    const st = C.listStatus(round.list, state);
    const dirLabel = card.dir === "nt" ? `Escriu-ho en ${data.target}` : `Escriu-ho en ${NATIVE_NAME[data.nativeCode] || data.nativeCode}`;
    screen.innerHTML = `
      <div class="flash-panel flash-play">
        <div class="flash-top">
          <button type="button" class="ghost" data-act="menu">‹ Menú</button>
          <span class="flash-prog">${st.known}/${st.total} sabudes${round.repassa ? " · repàs" : ""}</span>
          <span class="flash-clock" id="flash-clock" hidden></span>
        </div>
        <div class="flash-stage" id="flash-stage">
          <p class="flash-dir">${escText(dirLabel)}</p>
          <div class="flash-word">${escText(card.prompt)}</div>
          <div class="flash-hint" id="flash-hint"></div>
          <div class="flash-feedback" id="flash-feedback" aria-live="polite"></div>
        </div>
        <form class="flash-form" id="flash-form" autocomplete="off">
          <input id="flash-input" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Traducció">
          <button type="submit" class="primary" id="flash-ok">Comprova</button>
        </form>
      </div>`;
    const clock = q("#flash-clock");
    if (clock) clock.hidden = !prefs.timer;
    startClock();
    paintCard(null);
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
    let text =
      card.how === "revealed"
        ? `La resposta és «${card.accepted[0]}».`
        : "✓ Correcte" + (card.exact ? "" : ` · l'ortografia és «${card.form}»`);
    if (others.length) text += ` També: ${others.join(", ")}.`;
    if (card.how === "revealed") text += (card.returned ? "" : " Torna al final de la ronda.") + " Enter per continuar.";
    fb.textContent = text;
    btn.textContent = "Següent";
  }

  // Una resposta de l'alumne: encert, error (1r, 2n) o 3r error (resposta mostrada).
  function attempt(text) {
    if (!card || card.done || !String(text).trim()) return;
    const res = C.check(text, card.accepted, card.lang);
    if (res.ok) {
      resolve(card.misses === 0 ? "first" : "retry", res);
      return;
    }
    card.misses += 1;
    if (card.misses >= 3) {
      resolve("revealed", null);
      return;
    }
    const input = q("#flash-input");
    if (input) {
      input.value = "";
      input.focus();
    }
    paintCard("shake");
  }

  function resolve(how, res) {
    const r = round;
    card.done = true;
    card.how = how;
    if (res) {
      card.form = res.form;
      card.exact = res.exact;
    }
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
    // La revelada torna una vegada al final de la ronda.
    if (how === "revealed" && !card.returned) r.queue.push({ word: card.word, returned: true });
    paintCard(null);
    if (how !== "revealed") {
      // Amb altres respostes vàlides es llegeixen una mica més.
      const more = card.accepted.some((x) => x !== card.form);
      advanceTimer = setTimeout(advance, more ? 1800 : 1100);
    }
  }

  function advance() {
    clearAdvance();
    if (!round) return renderMenu();
    if (!round.queue.length) return finishRound();
    card = makeCard(round.queue.shift());
    renderCard();
  }

  function finishRound() {
    const r = round;
    const elapsed = Math.round((Date.now() - r.start) / 1000);
    stopClock();
    clearAdvance();
    view = "summary";
    const closedNow = C.listStatus(r.list, state).closed;
    const idx = data.lists.indexOf(r.list);
    const nextOpen = data.lists.slice(idx + 1).find(isOpen) || null;
    if (!r.repassa) selected = pickSelection(r.list.id);
    screen.innerHTML = `
      <div class="flash-panel">
        <div class="flash-head">
          <h2>${closedNow && !r.repassa ? "Llista completa ✓" : "Ronda acabada"}</h2>
          <button type="button" class="ghost" data-act="close" title="Tanca">✕</button>
        </div>
        <div class="flash-body">
          <p class="flash-sum-title">${escText(r.list.title)}</p>
          <ul class="flash-stats">
            <li><span>Encerts a la primera</span><strong>${r.first}/${r.presented}</strong></li>
            <li><span>Errors</span><strong>${r.errors}</strong></li>
            <li><span>Millor ratxa</span><strong>${r.best}</strong></li>
            ${prefs.timer ? `<li><span>Temps</span><strong>${fmt(elapsed)}</strong></li>` : ""}
          </ul>
          ${r.repassa ? '<p class="flash-note">Repàs: el progrés no canvia.</p>' : ""}
          <div class="flash-actions">
            <button type="button" class="primary" data-act="again">Una altra ronda</button>
            ${nextOpen ? `<button type="button" data-act="start" data-list="${escText(nextOpen.id)}">Següent llista</button>` : ""}
            <button type="button" data-act="menu">Menú</button>
          </div>
        </div>
      </div>`;
  }

  // ---- entrada -------------------------------------------------------------
  function ensureScreen() {
    if (screen) return;
    screen = document.createElement("div");
    screen.id = "flash-screen";
    screen.className = "flash-screen";
    screen.hidden = true;
    screen.setAttribute("role", "dialog");
    screen.setAttribute("aria-modal", "true");
    screen.setAttribute("aria-label", "Flash — vocabulari ràpid");
    document.body.appendChild(screen);
    screen.addEventListener("click", onClick);
    screen.addEventListener("submit", onSubmit);
    screen.addEventListener("change", onChange);
    screen.addEventListener("keydown", onKey);
  }

  function onClick(e) {
    const t = e.target.closest ? e.target.closest("[data-act],[data-dir],[data-list]") : null;
    if (!t) return;
    if (t.dataset.dir) {
      prefs.dir = t.dataset.dir;
      savePrefs();
      return renderMenu();
    }
    if (t.dataset.list && !t.dataset.act) {
      selected = t.dataset.list;
      return renderMenu();
    }
    switch (t.dataset.act) {
      case "close":
        return closeFlash();
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

  function onChange(e) {
    if (e.target.dataset && e.target.dataset.act === "timer") {
      prefs.timer = e.target.checked;
      savePrefs();
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

  function closeFlash() {
    clearAdvance();
    stopClock();
    round = null;
    card = null;
    if (screen) screen.hidden = true;
  }

  async function openFlash() {
    ensureScreen();
    screen.hidden = false;
    screen.innerHTML = '<div class="flash-panel"><p class="flash-note">Carregant…</p></div>';
    try {
      data = await api("/flash/lists");
    } catch (err) {
      data = null;
      console.warn("flash:", err);
    }
    if (!data || !data.ok || !data.enabled) {
      screen.innerHTML = `<div class="flash-panel"><div class="flash-head"><h2>⚡ Flash</h2><button type="button" class="ghost" data-act="close" title="Tanca">✕</button></div><p class="flash-note">Flash no està disponible per a aquest perfil.</p></div>`;
      return;
    }
    stateKey = `flowed.flash.v1|${window.__FLOWED_DOMAIN || "language"}|${data.target}|${data.nativeCode}`;
    state = loadState(stateKey);
    selected = pickSelection(null);
    renderMenu();
  }

  globalThis.openFlash = openFlash;
})();
