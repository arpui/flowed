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
    const t = String(s ?? "").replace(/\s+/g, "").replace(/−/g, "-").replace(/,/g, ".");
    return /^-?\d+(\.\d+)?$/.test(t) ? Number(t) : null;
  }

  // Com check(), però per valor (les operacions no tenen article ni accents).
  function checkNumber(answer, accepted) {
    let a = numeric(answer);
    const bare = String(answer ?? "").replace(/\s+/g, "");
    if (a === null && /^-?\d{1,3}(\.\d{3})+$/.test(bare) && accepted.some((x) => /^\d{5,}$/.test(String(x).trim()))) {
      a = Number(bare.replace(/\./g, "")); // 4.735.200 → 4735200 (thousands dots, more than four digits)
    }
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

  // Pista segons el tipus: fracció → el denominador (?/8); choice → cap (ja hi ha l'opció desactivada).
  function hintFor(kind, target, lang, mode) {
    if (kind === "fraction") {
      const m = /\/(\d+)$/.exec(String(target));
      return m ? `?/${m[1]}` : "?";
    }
    if (kind === "pair") {
      const p = parsePair(target);
      return p ? `(${p[0]}, ?)` : "?";
    }
    if (kind === "choice") return "";
    if (kind === "factorization") {
      const fz = factorization(target);
      return "factors" in fz ? `${fz.factors.size} primers diferents` : "";
    }
    if (kind === "algebraic") {
      const pl = parsePoly(target);
      return pl ? `grau ${polyDegree(pl)}` : "";
    }
    if (kind === "sexagesimal") {
      const sx = parseSexa(target, mode || "time");
      return sx ? `${Math.floor(sx.seconds / 3600)}${mode === "angle" ? "°" : " h"} ?` : "";
    }
    return hint(target, lang);
  }

  // Fracció: n/d, mixta (1 1/2), enter o decimal (0,25). Null si no ho és o el denominador és 0.
  function parseFraction(s) {
    const t = String(s ?? "").trim().replace(/−/g, "-");
    let m = /^(-?)(\d+)\s+(\d+)\s*\/\s*(\d+)$/.exec(t);
    if (m) {
      const d = Number(m[4]);
      return d === 0 ? null : { num: (m[1] ? -1 : 1) * (Number(m[2]) * d + Number(m[3])), den: d };
    }
    m = /^(-?)(\d+)\s*\/\s*(\d+)$/.exec(t);
    if (m) {
      const d = Number(m[3]);
      return d === 0 ? null : { num: (m[1] ? -1 : 1) * Number(m[2]), den: d };
    }
    m = /^(-?)(\d+)[,.](\d+)$/.exec(t);
    if (m) return { num: (m[1] ? -1 : 1) * Number(m[2] + m[3]), den: 10 ** m[3].length };
    m = /^(-?)(\d+)$/.exec(t);
    if (m) return { num: (m[1] ? -1 : 1) * Number(m[2]), den: 1 };
    return null;
  }

  function gcd(a, b) {
    let x = Math.abs(a);
    let y = Math.abs(b);
    while (y) [x, y] = [y, x % y];
    return x;
  }

  // Irreductible tal com s'escriu: enter si el valor és enter; n/d o mixta amb la part fraccionària reduïda.
  // Els decimals no compten.
  function isSimplest(s) {
    const t = String(s ?? "").trim().replace(/−/g, "-");
    const f = parseFraction(t);
    if (!f) return false;
    if (f.num % f.den === 0) return /^-?\d+$/.test(t);
    if (/^(-?)(\d+)[,.](\d+)$/.test(t)) return false;
    const m = /^(-?)(\d+)\s+(\d+)\s*\/\s*(\d+)$/.exec(t);
    if (m) return Number(m[3]) > 0 && Number(m[3]) < Number(m[4]) && gcd(Number(m[3]), Number(m[4])) === 1;
    return gcd(f.num, f.den) === 1;
  }

  // Fracció: el valor ha de ser el de una de les acceptades. 'simplest' exigeix la forma irreductible.
  // exact: escrita igual que l'acceptada (sense espais); si no, el client mostra la forma habitual.
  function checkFraction(answer, accepted, rule) {
    const a = parseFraction(answer);
    if (!a) return { ok: false, exact: true, form: null };
    let hit = null;
    for (const raw of accepted) {
      const t = parseFraction(raw);
      if (t && a.num * t.den === t.num * a.den) {
        hit = raw;
        break;
      }
    }
    if (hit === null) return { ok: false, exact: true, form: null };
    if (rule === "simplest" && !isSimplest(answer)) return { ok: false, exact: true, form: hit };
    const exact = String(answer).replace(/\s+/g, "") === String(hit).replace(/\s+/g, "");
    return { ok: true, exact, form: hit };
  }

  // Unitat: la caixa només porta el número. Si l'alumne l'escriu enganxada (3500 m), es treu.
  function stripUnit(s, unit) {
    const t = String(s ?? "").trim();
    if (!unit) return t;
    for (const u of [unit, unit.replace("²", "2"), unit.replace("³", "3")]) {
      if (t.toLowerCase().endsWith(u.toLowerCase())) return t.slice(0, t.length - u.length).trim();
    }
    return t;
  }

  // choice: l'opció triada ha de ser la correcta (text exacte).
  function checkChoice(picked, accepted) {
    return accepted.includes(picked) ? { ok: true, exact: true, form: picked } : { ok: false, exact: true, form: null };
  }

  // pair: un punt (x, y) escrit (3, 4), 3,4, 3 4 o (3 ; 4). L'ordre compta: (4,3) és un altre punt.
  // Null si no són unes coordenades; els parèntesis han d'anar parells.
  function parsePair(s) {
    const t = String(s ?? "").trim().replace(/−/g, "-");
    if (t.startsWith("(") !== t.endsWith(")")) return null;
    const m = /^\s*(-?\d+)\s*(?:[,;]\s*|\s+)(-?\d+)\s*$/.exec(t.startsWith("(") ? t.slice(1, -1) : t);
    return m ? [Number(m[1]), Number(m[2])] : null;
  }

  // pair: els valors han de ser els de l'acceptat. exact: escrit igual (sense espais) que la forma habitual.
  function checkPair(answer, accepted) {
    const a = parsePair(answer);
    if (!a) return { ok: false, exact: true, form: null };
    for (const raw of accepted) {
      const t = parsePair(raw);
      if (t && t[0] === a[0] && t[1] === a[1]) {
        return { ok: true, exact: String(answer).replace(/\s+/g, "") === String(raw).replace(/\s+/g, ""), form: raw };
      }
    }
    return { ok: false, exact: true, form: null };
  }

  // ---- tipus de resposta de m7 (docs/ENCARREC-M7-E5-FLASH.md §2) ---------------
  // Mateixes regles que server/src/flash.ts (factorization, parsePoly, parseSexa) i hooks/mathgrade.py (parse_poly).
  const SUPER = "⁰¹²³⁴⁵⁶⁷⁸⁹";
  const stripSpaces = (s) => String(s ?? "").replace(/\s+/g, "");

  function isPrime(n) {
    if (!Number.isInteger(n) || n < 2) return false;
    for (let d = 2; d * d <= n; d++) if (n % d === 0) return false;
    return true;
  }

  // Factors primers amb repetició: Map primer → nombre de vegades, o { problem }.
  function factorization(s) {
    const t = String(s ?? "").trim();
    if (!t) return { problem: "buit" };
    const factors = new Map();
    for (const tok of t.split(/\s*[·*x×]\s*|\s+/).filter((x) => x.length > 0)) {
      const m = /^(\d+)(?:\^(\d+)|([⁰¹²³⁴⁵⁶⁷⁸⁹]+))?$/.exec(tok);
      if (!m) return { problem: `${tok} no és un factor` };
      const p = Number(m[1]);
      if (!isPrime(p)) return { problem: `${p} no és primer` };
      let e = 1;
      if (m[2] !== undefined) e = Number(m[2]);
      else if (m[3] !== undefined) e = [...m[3]].reduce((acc, c) => acc * 10 + SUPER.indexOf(c), 0);
      if (e < 1) return { problem: `${tok}: l'exponent ha de ser ≥ 1` };
      factors.set(p, (factors.get(p) || 0) + e);
    }
    return { factors };
  }

  function sameFactors(a, b) {
    if (a.size !== b.size) return false;
    for (const [p, e] of a) if (b.get(p) !== e) return false;
    return true;
  }

  // Polinomis: nombres racionals exactes (BigInt). Un monomi és [[lletra, exponent], …] ordenat.
  const ALG_FAIL = {}; // llançat quan la resposta no és un polinomi
  const bgcd = (a, b) => {
    let x = a < 0n ? -a : a;
    let y = b < 0n ? -b : b;
    while (y) [x, y] = [y, x % y];
    return x;
  };
  const rat = (n, d = 1n) => {
    if (d === 0n) throw ALG_FAIL;
    const sign = d < 0n ? -1n : 1n;
    const g = bgcd(n, d) || 1n;
    return { n: (sign * n) / g, d: (sign * d) / g };
  };
  const ratAdd = (x, y) => rat(x.n * y.d + y.n * x.d, x.d * y.d);
  const ratMul = (x, y) => rat(x.n * y.n, x.d * y.d);
  const ratText = (x) => (x.d === 1n ? String(x.n) : `${x.n}/${x.d}`);
  const monoKey = (m) => m.map(([v, e]) => `${v}${e}`).join("");
  function monoMul(a, b) {
    const d = new Map();
    for (const [v, e] of [...a, ...b]) d.set(v, (d.get(v) || 0) + e);
    return [...d.entries()].sort(([x], [y]) => (x < y ? -1 : x > y ? 1 : 0));
  }
  const polyConst = (c) => (c.n === 0n ? new Map() : new Map([["", { mono: [], c }]]));
  const polyVar = (v) => new Map([[monoKey([[v, 1]]), { mono: [[v, 1]], c: rat(1n) }]]);
  function polyAdd(a, b, sign = 1n) {
    const out = new Map(a);
    for (const [k, t] of b) {
      const cur = out.get(k);
      const c = ratAdd(cur ? cur.c : rat(0n), rat(sign * t.c.n, t.c.d));
      if (c.n === 0n) out.delete(k);
      else out.set(k, { mono: t.mono, c });
    }
    return out;
  }
  function polyMul(a, b) {
    const out = new Map();
    for (const x of a.values()) {
      for (const y of b.values()) {
        const mono = monoMul(x.mono, y.mono);
        const k = monoKey(mono);
        const cur = out.get(k);
        const c = ratAdd(cur ? cur.c : rat(0n), ratMul(x.c, y.c));
        if (c.n === 0n) out.delete(k);
        else out.set(k, { mono, c });
      }
    }
    return out;
  }
  function polyScale(p, k) {
    const out = new Map();
    for (const [key, t] of p) {
      const c = ratMul(t.c, k);
      if (c.n !== 0n) out.set(key, { mono: t.mono, c });
    }
    return out;
  }
  function polyPow(base, n) {
    let out = polyConst(rat(1n));
    for (let i = 0; i < n; i++) out = polyMul(out, base);
    return out;
  }
  // El valor d'un polinomi que és una constant no nul·la, o null (una divisió o un exponent el necessiten).
  function nonzeroConstant(p) {
    if (p.size !== 1) return null;
    const t = p.get("");
    return t ? t.c : null;
  }

  // La normalització de _normalize_alg (hooks/mathgrade.py): signes d'operació, superíndexs, ^ com a **, coma decimal,
  // producte implícit. Un separador de milers es rebutja.
  function normalizeAlg(text) {
    let s = String(text ?? "").trim();
    s = s.replace(/[×·∗⋅]/g, "*").replace(/[÷⁄]/g, "/").replace(/[−–—]/g, "-");
    s = s.replace(/²/g, "^2").replace(/³/g, "^3").replace(/⁴/g, "^4");
    s = s.replace(/\^/g, "**");
    s = s.replace(/(?<=\d),(?=\d)/g, ".");
    if (/\d{1,3}(?:\.\d{3}){2,}/.test(s)) throw ALG_FAIL;
    s = s.replace(/(\d)\s*(?=[a-zA-Z(])/g, "$1*");
    s = s.replace(/([a-zA-Z)])\s*(?=\()/g, "$1*");
    s = s.replace(/([a-zA-Z)])\s*(?=[a-zA-Z(])/g, "$1*");
    return s.replace(/\s+/g, " ").trim();
  }

  function decimalRat(text) {
    const [whole = "", frac = ""] = text.split(".");
    return rat(BigInt((whole || "0") + frac), 10n ** BigInt(frac.length));
  }

  function tokenizeAlg(s) {
    const out = [];
    let i = 0;
    while (i < s.length) {
      const ch = s[i];
      if (ch === " ") {
        i++;
        continue;
      }
      const num = /^(\d+\.?\d*|\.\d+)/.exec(s.slice(i));
      if (num) {
        out.push({ t: "num", v: decimalRat(num[1]) });
        i += num[0].length;
      } else if (/^[a-zA-Z]$/.test(ch)) {
        out.push({ t: "name", v: ch });
        i++;
      } else if (s.startsWith("**", i)) {
        out.push({ t: "op", v: "**" });
        i += 2;
      } else if ("+-*/()".includes(ch)) {
        out.push({ t: "op", v: ch });
        i++;
      } else {
        throw ALG_FAIL;
      }
    }
    return out;
  }

  // El polinomi expandit d'una resposta algebraica (les regles de parse_poly), o null si no ho és.
  // Mapa: clau del monomi ("x2y1"; "" és la constant) → { mono, c }.
  function parsePoly(text) {
    try {
      const s = normalizeAlg(text);
      if (!s) throw ALG_FAIL;
      const toks = tokenizeAlg(s);
      let pos = 0;
      const isOp = (v) => pos < toks.length && toks[pos].t === "op" && toks[pos].v === v;
      const expr = () => {
        let p = term();
        while (isOp("+") || isOp("-")) {
          const op = toks[pos++].v;
          p = polyAdd(p, term(), op === "+" ? 1n : -1n);
        }
        return p;
      };
      const term = () => {
        let p = factor();
        while (isOp("*") || isOp("/")) {
          const op = toks[pos++].v;
          const q = factor();
          if (op === "*") p = polyMul(p, q);
          else {
            const c = nonzeroConstant(q);
            if (c === null) throw ALG_FAIL;
            p = polyScale(p, rat(c.d, c.n));
          }
        }
        return p;
      };
      const factor = () => {
        if (isOp("+") || isOp("-")) {
          const neg = toks[pos++].v === "-";
          const f = factor();
          return neg ? polyScale(f, rat(-1n)) : f;
        }
        return power();
      };
      const power = () => {
        const base = primary();
        if (!isOp("**")) return base;
        pos++;
        const e = nonzeroConstant(factor());
        if (e === null || e.d !== 1n || e.n < 1n || e.n > 6n) throw ALG_FAIL;
        return polyPow(base, Number(e.n));
      };
      const primary = () => {
        const t = toks[pos++];
        if (!t) throw ALG_FAIL;
        if (t.t === "num") return polyConst(t.v);
        if (t.t === "name") return polyVar(t.v);
        if (t.v !== "(") throw ALG_FAIL;
        const p = expr();
        if (!isOp(")")) throw ALG_FAIL;
        pos++;
        return p;
      };
      const result = expr();
      if (pos !== toks.length) throw ALG_FAIL;
      return result;
    } catch (e) {
      if (e === ALG_FAIL) return null;
      throw e;
    }
  }

  // Forma canònica: dos polinomis iguals tenen la mateixa clau.
  function polyKey(p) {
    return [...p.entries()]
      .map(([k, t]) => `${k}:${ratText(t.c)}`)
      .sort()
      .join("|");
  }

  function polyDegree(p) {
    let d = 0;
    for (const t of p.values()) d = Math.max(d, t.mono.reduce((s, [, e]) => s + e, 0));
    return d;
  }

  // Temps o angle com a segons. normalized és fals quan els minuts o els segons són 60 o més. Null si no és cap dels dos.
  function parseSexa(s, mode) {
    const t = String(s ?? "")
      .trim()
      .replace(/º/g, "°")
      .replace(/’’|′′|″|”|“/g, "''")
      .replace(/[′’‘]/g, "'")
      .replace(/\s+/g, " ");
    let m;
    let a = 0;
    let b = 0;
    let c = 0;
    if (mode === "time") {
      if ((m = /^(\d+):(\d+)(?::(\d+))?$/.exec(t))) {
        a = Number(m[1]);
        b = Number(m[2]);
        c = m[3] === undefined ? 0 : Number(m[3]);
      } else if ((m = /^(?:(\d+) ?h)?(?: ?(\d+) ?min)?(?: ?(\d+) ?s)?$/i.exec(t)) && m.slice(1).some((x) => x !== undefined)) {
        a = Number(m[1] || 0);
        b = Number(m[2] || 0);
        c = Number(m[3] || 0);
      } else return null;
    } else {
      m = /^(\d+) ?°(?: ?(\d+) ?'(?: ?(\d+) ?'')?)?$/.exec(t);
      if (!m) return null;
      a = Number(m[1]);
      b = Number(m[2] || 0);
      c = Number(m[3] || 0);
    }
    return { seconds: a * 3600 + b * 60 + c, normalized: b < 60 && c < 60 };
  }

  // Pistes: el primer error no en dona cap. Factors → quants primers diferents; algebraica → el grau; temps → les hores.
  // ---- comprovacions (com check/checkFraction: { ok, exact, form, note }) ----
  function checkFactorization(answer, accepted) {
    const a = factorization(answer);
    if (!("factors" in a)) return { ok: false, exact: true, form: null, note: a.problem };
    for (const raw of accepted) {
      const b = factorization(raw);
      if ("factors" in b && sameFactors(a.factors, b.factors)) {
        return { ok: true, exact: stripSpaces(answer) === stripSpaces(raw), form: raw };
      }
    }
    return { ok: false, exact: true, form: null };
  }

  function checkAlgebraic(answer, accepted) {
    const a = parsePoly(answer);
    if (a === null) return { ok: false, exact: true, form: null };
    const key = polyKey(a);
    for (const raw of accepted) {
      const b = parsePoly(raw);
      if (b !== null && polyKey(b) === key) return { ok: true, exact: stripSpaces(answer) === stripSpaces(raw), form: raw };
    }
    return { ok: false, exact: true, form: null };
  }

  function checkSexagesimal(answer, target, mode) {
    const a = parseSexa(answer, mode);
    if (a === null) return { ok: false, exact: true, form: null };
    if (!a.normalized) {
      return { ok: false, exact: true, form: null, note: "Normalitza: els minuts i els segons han de ser menors que 60." };
    }
    const b = parseSexa(target, mode);
    if (b !== null && b.seconds === a.seconds) {
      return { ok: true, exact: stripSpaces(answer) === stripSpaces(target), form: target };
    }
    return { ok: false, exact: true, form: null };
  }

  // Angle de la posició `ask` d'una figura `parallels` (E5 §3): 1 i 4 al paral·lela de dalt, 5 i 8 a la de baix
  // són l'angle de la secant; la resta són el seu suplement.
  function parallelValue(angle, known, ask) {
    const same = (p) => p === 1 || p === 4 || p === 5 || p === 8;
    const alpha = same(known) ? angle : 180 - angle;
    return same(ask) ? alpha : 180 - alpha;
  }


  // ---- figures (docs/ENCARREC-M5-E3-FIGURES.md §2) ----------------------------
  // Dibuix SVG en línia per a la figura d'una targeta. Les dades ja les ha validat el servidor.
  // El dibuix no mostra la resposta: un angle no porta graus (tret que label), i una marca de cercle no té nom.
  // Colors: classes fig-* amb els tokens --flash-*; les línies usen currentColor.
  function escXml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  // Un enter amb el signe menys de tipografia: −3.
  const sg = (v) => (v < 0 ? `−${-v}` : String(v));

  const f1 = (n) => Number(n.toFixed(1));
  const xy = (p) => `${f1(p[0])},${f1(p[1])}`;

  function svgText(x, y, s, anchor = "middle", cls = "fig-text") {
    return `<text class="${cls}" x="${f1(x)}" y="${f1(y)}" text-anchor="${anchor}" dominant-baseline="middle">${escXml(s)}</text>`;
  }

  // Punts en coordenades de matemàtiques (y amunt) ajustats a una caixa {x0,y0,x1,y1} de l'SVG (y avall), amb escala uniforme.
  function fitPoints(pts, box) {
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const s = Math.min((box.x1 - box.x0) / (maxX - minX || 1), (box.y1 - box.y0) / (maxY - minY || 1));
    const offX = box.x0 + (box.x1 - box.x0 - (maxX - minX) * s) / 2;
    const offY = box.y0 + (box.y1 - box.y0 - (maxY - minY) * s) / 2;
    return pts.map((p) => [offX + (p[0] - minX) * s, offY + (maxY - p[1]) * s]);
  }

  function centreOf(pts) {
    return [pts.reduce((a, p) => a + p[0], 0) / pts.length, pts.reduce((a, p) => a + p[1], 0) / pts.length];
  }

  // Caixa dins la qual es fitten les figures amb etiquetes de costat: prou marge perquè les mides caiguin dins el dibuix.
  const FIG_BOX = { x0: 52, y0: 40, x1: 248, y1: 180 };

  // L'etiqueta d'un costat: fora de la figura, sobre la normal exterior del mig del costat. La caixa del text
  // queda tota al costat de fora (amplada ~8 px per caràcter, alçada del text), així no trepitja la línia.
  function edgeLabel(a, b, text, centre) {
    const mx = (a[0] + b[0]) / 2;
    const my = (a[1] + b[1]) / 2;
    const ex = b[0] - a[0];
    const ey = b[1] - a[1];
    const len = Math.hypot(ex, ey) || 1;
    let nx = -ey / len;
    let ny = ex / len;
    if ((mx - centre[0]) * nx + (my - centre[1]) * ny < 0) {
      nx = -nx;
      ny = -ny;
    }
    const hw = (text.length * 8) / 2;
    const hh = 8;
    const d = Math.abs(nx) * hw + Math.abs(ny) * hh + 6;
    return svgText(mx + nx * d, my + ny * d, text);
  }

  function figureDraw(f) {
    const us = f.unit ? ` ${f.unit}` : "";
    switch (f.type) {
      case "angle": {
        const V = [150, 112];
        const R = 42; // arc
        const L = 92; // rays
        const rad = (f.deg * Math.PI) / 180;
        const at = (t, r) => [V[0] + r * Math.cos(t), V[1] - r * Math.sin(t)];
        const ray = (end) => `<line class="fig-line" x1="${f1(V[0])}" y1="${f1(V[1])}" x2="${f1(end[0])}" y2="${f1(end[1])}"/>`;
        let body = ray(at(0, L));
        if (f.deg === 360) {
          body += `<circle class="fig-mark" cx="${f1(V[0])}" cy="${f1(V[1])}" r="${R}"/>`;
        } else {
          body += ray(at(rad, L));
          body += `<path class="fig-mark" d="M ${xy(at(0, R))} A ${R} ${R} 0 ${f.deg > 180 ? 1 : 0} 0 ${xy(at(rad, R))}"/>`;
        }
        if (f.label) {
          const mid = at(rad / 2, 66);
          body += svgText(mid[0], mid[1], `${f.deg}°`);
        }
        return { vb: "0 0 300 224", body, label: f.label ? `Angle de ${f.deg} graus` : "Angle dibuixat" };
      }
      case "triangle": {
        const [a, b, c] = f.sides;
        const x2 = (c * c + a * a - b * b) / (2 * a);
        const y2 = Math.sqrt(Math.max(0, c * c - x2 * x2));
        const p = fitPoints([[0, 0], [a, 0], [x2, y2]], FIG_BOX);
        const ctr = centreOf(p);
        let body = `<polygon class="fig-line" points="${p.map(xy).join(" ")}"/>`;
        if (f.labels) {
          body += edgeLabel(p[0], p[1], `${a}${us}`, ctr) + edgeLabel(p[1], p[2], `${b}${us}`, ctr) + edgeLabel(p[2], p[0], `${c}${us}`, ctr);
        }
        return { vb: "0 0 300 220", body, label: f.labels ? `Triangle de costats ${f.sides.map((x) => `${x}${us}`).join(", ")}` : "Triangle" };
      }
      case "polygon": {
        const n = f.sides.length;
        const raw = [];
        for (let k = 0; k < n; k++) {
          const t = -Math.PI / 2 + (2 * Math.PI * k) / n;
          raw.push([Math.cos(t), Math.sin(t)]);
        }
        const p = fitPoints(raw, FIG_BOX);
        const ctr = centreOf(p);
        let body = `<polygon class="fig-line" points="${p.map(xy).join(" ")}"/>`;
        if (f.labels) f.sides.forEach((x, k) => (body += edgeLabel(p[k], p[(k + 1) % n], `${x}${us}`, ctr)));
        return { vb: "0 0 300 220", body, label: `Polígon de ${n} costats` };
      }
      case "rect": {
        const s = Math.min(190 / f.w, 140 / f.h);
        const W = f.w * s;
        const H = f.h * s;
        const x0 = (300 - W - 44) / 2; // 44 px kept on the right for the height label
        const y0 = (220 - H) / 2;
        let body = `<rect class="fig-line" x="${f1(x0)}" y="${f1(y0)}" width="${f1(W)}" height="${f1(H)}" fill="none"/>`;
        if (f.labels) {
          body += svgText(x0 + W / 2, y0 - 14, `${f.w}${us}`) + svgText(x0 + W + 8, y0 + H / 2, `${f.h}${us}`, "start");
        }
        return { vb: "0 0 300 220", body, label: f.labels ? `Rectangle de ${f.w}${us} per ${f.h}${us}` : "Rectangle" };
      }
      case "circle": {
        const cx = 150;
        const cy = 120;
        const R = 88;
        const at = (deg) => [cx + R * Math.cos((deg * Math.PI) / 180), cy - R * Math.sin((deg * Math.PI) / 180)];
        const r0 = f.rot;
        let mark;
        if (f.mark === "radius") mark = `<line class="fig-mark" x1="${cx}" y1="${cy}" x2="${f1(at(r0)[0])}" y2="${f1(at(r0)[1])}"/>`;
        else if (f.mark === "diameter") mark = `<line class="fig-mark" x1="${f1(at(r0)[0])}" y1="${f1(at(r0)[1])}" x2="${f1(at(r0 + 180)[0])}" y2="${f1(at(r0 + 180)[1])}"/>`;
        else if (f.mark === "chord") mark = `<line class="fig-mark" x1="${f1(at(r0)[0])}" y1="${f1(at(r0)[1])}" x2="${f1(at(r0 + 100)[0])}" y2="${f1(at(r0 + 100)[1])}"/>`;
        else if (f.mark === "arc") mark = `<path class="fig-mark" d="M ${xy(at(r0))} A ${R} ${R} 0 0 0 ${xy(at(r0 + 100))}"/>`;
        else mark = `<circle class="fig-dot" cx="${cx}" cy="${cy}" r="5"/>`;
        return { vb: "0 0 300 240", body: `<circle class="fig-line" cx="${cx}" cy="${cy}" r="${R}" fill="none"/>${mark}`, label: "Cercle amb un element marcat" };
      }
      case "bars": {
        const left = 46;
        const right = 290;
        const top = 40;
        const bottom = 196;
        const n = f.labels.length;
        const maxV = Math.max(1, ...f.values);
        const step = Math.max(1, Math.ceil(maxV / 4));
        const topVal = Math.ceil(maxV / step) * step;
        const yOf = (v) => bottom - (v / topVal) * (bottom - top);
        let body = f.title ? svgText(150, 14, f.title, "middle", "fig-title") : "";
        for (let v = 0; v <= topVal; v += step) {
          body += `<line class="fig-grid" x1="${left}" y1="${f1(yOf(v))}" x2="${right}" y2="${f1(yOf(v))}"/>`;
          body += svgText(left - 6, yOf(v), String(v), "end", "fig-tick");
        }
        body += `<line class="fig-line" x1="${left}" y1="${top}" x2="${left}" y2="${bottom}"/>`;
        body += `<line class="fig-line" x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}"/>`;
        const slot = (right - left) / n;
        f.values.forEach((v, i) => {
          const x = left + i * slot + slot * 0.2;
          body += `<rect class="fig-bar" x="${f1(x)}" y="${f1(yOf(v))}" width="${f1(slot * 0.6)}" height="${f1(bottom - yOf(v))}"/>`;
          body += svgText(left + (i + 0.5) * slot, bottom + 14, f.labels[i], "middle", "fig-tick");
        });
        const names = f.labels.join(", ");
        return { vb: "0 0 300 240", body, label: `Diagrama de barres${f.title ? `: ${f.title}` : ""}, amb les barres ${names}` };
      }
      case "grid": {
        // Un quadrat de mn a mx (per defecte 0..10: els eixos passen pel 0). Amb `line`, la recta y = m·x + n.
        const mn = f.min ?? 0;
        const mx = f.max ?? f.size ?? 10;
        const S = mx - mn;
        const u = 200 / S;
        const X = (v) => 40 + (v - mn) * u;
        const Y = (v) => 220 - (v - mn) * u;
        let body = "";
        for (let v = mn; v <= mx; v++) {
          body += `<line class="fig-grid" x1="${f1(X(v))}" y1="${f1(Y(mn))}" x2="${f1(X(v))}" y2="${f1(Y(mx))}"/>`;
          body += `<line class="fig-grid" x1="${f1(X(mn))}" y1="${f1(Y(v))}" x2="${f1(X(mx))}" y2="${f1(Y(v))}"/>`;
          if (mn < 0) {
            // amb un interval que baixa de 0 els números van a la vora del quadrat: no es troben als eixos
            body += svgText(X(v), Y(mn) + 12, sg(v), "middle", "fig-tick");
            body += svgText(X(mn) - 6, Y(v), sg(v), "end", "fig-tick");
          } else {
            body += svgText(X(v), Y(0) + 12, sg(v), "middle", "fig-tick");
            if (v !== 0) body += svgText(X(0) - 10, Y(v), sg(v), "end", "fig-tick");
          }
        }
        body += `<line class="fig-line" x1="${f1(X(mn))}" y1="${f1(Y(0))}" x2="${f1(X(mx) + 6)}" y2="${f1(Y(0))}"/>`;
        body += `<line class="fig-line" x1="${f1(X(0))}" y1="${f1(Y(mn))}" x2="${f1(X(0))}" y2="${f1(Y(mx) - 6)}"/>`;
        body += svgText(X(mx) + 12, Y(0), "x", "start") + svgText(X(0) + 8, Y(mx) - 4, "y", "start");
        if (f.line) {
          const { m, n } = f.line;
          if (m === 0) {
            body += `<line class="fig-mark" x1="${f1(X(mn))}" y1="${f1(Y(n))}" x2="${f1(X(mx))}" y2="${f1(Y(n))}"/>`;
          } else {
            // el tram de la recta dins el quadrat
            const xa = (mn - n) / m;
            const xb = (mx - n) / m;
            const lo = Math.max(mn, Math.min(xa, xb));
            const hi = Math.min(mx, Math.max(xa, xb));
            if (lo <= hi) {
              body += `<line class="fig-mark" x1="${f1(X(lo))}" y1="${f1(Y(m * lo + n))}" x2="${f1(X(hi))}" y2="${f1(Y(m * hi + n))}"/>`;
            }
          }
        }
        for (const [px, py] of f.points) body += `<circle class="fig-dot" cx="${f1(X(px))}" cy="${f1(Y(py))}" r="5"/>`;
        const n = f.points.length;
        const parts = [];
        if (n === 1) parts.push("un punt marcat");
        else if (n > 1) parts.push(`${n} punts marcats`);
        if (f.line) parts.push("una recta");
        return {
          vb: "0 0 300 250",
          body,
          label: `Quadrícula de coordenades de ${sg(mn)} a ${sg(mx)}${parts.length ? `, amb ${parts.join(" i ")}` : ""}`,
        };
      }
      case "parallels": {
        // Dues paral·leles i una secant. Les posicions 1–8 (1–4 a la de dalt, 5–8 a la de baix; 1 UL, 2 UR, 3 DL, 4 DR).
        const alpha = [1, 4, 5, 8].includes(f.known) ? f.angle : 180 - f.angle; // l'angle de la secant
        const rad = (alpha * Math.PI) / 180;
        const cx = 160;
        const yT = 75;
        const yB = 165;
        const dx = ((yB - yT) * Math.cos(rad)) / Math.sin(rad);
        const P = [cx - dx / 2, yT];
        const Q = [cx + dx / 2, yB];
        const D = [Math.cos(rad), Math.sin(rad)];
        const R = [1, 0];
        const L = [-1, 0];
        const mD = [-D[0], -D[1]];
        const ext = 16;
        let body = `<line class="fig-line" x1="10" y1="${yT}" x2="310" y2="${yT}"/>`;
        body += `<line class="fig-line" x1="10" y1="${yB}" x2="310" y2="${yB}"/>`;
        body += `<line class="fig-line" x1="${f1(P[0] - D[0] * ext)}" y1="${f1(P[1] - D[1] * ext)}" x2="${f1(Q[0] + D[0] * ext)}" y2="${f1(Q[1] + D[1] * ext)}"/>`;
        // la posició k: el punt de la secant i els dos raigs de l'angle (UL, UR, DL, DR)
        const place = (k) => ({ X: k > 4 ? Q : P, rays: [[L, mD], [R, mD], [L, D], [R, D]][(k - 1) % 4] });
        const bisector = (u1, u2) => {
          const s = [u1[0] + u2[0], u1[1] + u2[1]];
          const len = Math.hypot(s[0], s[1]);
          return [s[0] / len, s[1] / len];
        };
        const arc = (k) => {
          const { X, rays } = place(k);
          const [u1, u2] = rays;
          const a = [X[0] + u1[0] * 16, X[1] + u1[1] * 16];
          const b = [X[0] + u2[0] * 16, X[1] + u2[1] * 16];
          const cross = u1[0] * u2[1] - u1[1] * u2[0];
          return `<path class="fig-mark" d="M ${xy(a)} A 16 16 0 0 ${cross > 0 ? 1 : 0} ${xy(b)}"/>`;
        };
        const label = (k, text) => {
          const { X, rays } = place(k);
          const b = bisector(rays[0], rays[1]);
          return svgText(X[0] + b[0] * 28, X[1] + b[1] * 28, text);
        };
        body += arc(f.known) + label(f.known, `${f.angle}°`) + arc(f.ask) + label(f.ask, "?");
        return {
          vb: "0 0 320 240",
          body,
          label: `Dues rectes paral·leles tallades per una secant, amb un angle de ${f.angle} graus marcat`,
        };
      }
      case "right_triangle": {
        // Angle recte a baix a l'esquerra: a és el catet de baix, b el de l'esquerra, c la hipotenusa.
        const us = f.unit ? ` ${f.unit}` : "";
        const p = fitPoints(
          [
            [0, 0],
            [f.a, 0],
            [0, f.b],
          ],
          FIG_BOX,
        );
        const ctr = centreOf(p);
        const unitVec = (from, to) => {
          const dx = to[0] - from[0];
          const dy = to[1] - from[1];
          const len = Math.hypot(dx, dy) || 1;
          return [dx / len, dy / len];
        };
        const ua = unitVec(p[0], p[1]);
        const ub = unitVec(p[0], p[2]);
        const s = 12;
        const q1 = [p[0][0] + ua[0] * s, p[0][1] + ua[1] * s];
        const q2 = [q1[0] + ub[0] * s, q1[1] + ub[1] * s];
        const q3 = [p[0][0] + ub[0] * s, p[0][1] + ub[1] * s];
        const side = (which, v) => (f.ask === which ? "?" : `${v}${us}`);
        let body = `<polygon class="fig-line" points="${p.map(xy).join(" ")}"/>`;
        body += `<path class="fig-line" d="M ${xy(q1)} L ${xy(q2)} L ${xy(q3)}"/>`;
        body += edgeLabel(p[0], p[1], side("a", f.a), ctr) + edgeLabel(p[1], p[2], side("c", f.c), ctr) + edgeLabel(p[2], p[0], side("b", f.b), ctr);
        return { vb: "0 0 300 220", body, label: "Triangle rectangle, amb un costat per calcular" };
      }
      case "number_line": {
        // Recta numèrica amb un punt marcat; una marca cada 1, 2 o 5 unitats segons l'obertura.
        const L = 30;
        const R = 270;
        const y = 112;
        const span = f.max - f.min;
        const step = span <= 12 ? 1 : span <= 24 ? 2 : 5;
        const X = (v) => L + ((v - f.min) / span) * (R - L);
        let body = `<line class="fig-line" x1="${L - 10}" y1="${y}" x2="${R + 10}" y2="${y}"/>`;
        for (let v = f.min; v <= f.max; v += step) {
          body += `<line class="fig-line" x1="${f1(X(v))}" y1="${y - 5}" x2="${f1(X(v))}" y2="${y + 5}"/>`;
          body += svgText(X(v), y + 20, sg(v), "middle", "fig-tick");
        }
        body += `<circle class="fig-dot" cx="${f1(X(f.point))}" cy="${y}" r="6"/>`;
        if (f.label) body += svgText(R + 10, y + 42, f.label, "end");
        return { vb: "0 0 300 170", body, label: `Recta numèrica de ${sg(f.min)} a ${sg(f.max)}` };
      }
      default:
        return null;
    }
  }

  // El SVG d'una figura (o "" si no n'hi ha cap de conegut).
  function figureSvg(f) {
    const d = f ? figureDraw(f) : null;
    return d ? `<svg class="flash-fig-svg" viewBox="${d.vb}" role="img" aria-label="${escXml(d.label)}" focusable="false">${d.body}</svg>` : "";
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
    if (a.exhausted) return "revealed"; // choice: només en queda una d'activa
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
    parseFraction,
    isSimplest,
    checkFraction,
    stripUnit,
    checkChoice,
    parsePair,
    checkPair,
    factorization,
    checkFactorization,
    parsePoly,
    polyKey,
    polyDegree,
    checkAlgebraic,
    parseSexa,
    checkSexagesimal,
    parallelValue,
    figureSvg,
    hintFor,
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
  // Respostes que s'escriuen de més d'una manera: si no és la forma habitual, es mostra.
  const FORM_KINDS = ["fraction", "pair", "factorization", "algebraic", "sexagesimal"];

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
    const kind = math ? w.answer_kind || "number" : "text"; // number | fraction | unit | choice | pair, or text (language)
    return {
      word: w,
      figure: math && w.figure ? w.figure : null, // drawn above the prompt
      returned: item.returned,
      dot: item.dot,
      dir,
      math,
      kind,
      rule: w.form || "value", // fraction: value | simplest
      mode: math && w.answer_kind === "sexagesimal" ? w.mode || (/[°']/.test(w.target[0] || "") ? "angle" : "time") : null,
      unit: math && w.unit ? w.unit : "", // unit kind: shown outside the box
      options: kind === "choice" ? (w.options || []).slice() : [],
      off: [], // choice: the buttons that were wrong
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
    const choice = card.kind === "choice";
    const dirLabel = card.math
      ? choice ? "Tria" : card.kind === "pair" ? "Escriu les coordenades"
        : card.kind === "factorization" ? "Escriu els factors primers"
        : card.kind === "algebraic" ? "Escriu l'expressió reduïda"
        : card.kind === "sexagesimal" ? (card.mode === "angle" ? "Escriu l'angle" : "Escriu el temps")
        : "Calcula"
      : card.dir === "nt"
        ? `Escriu-ho en ${data.target}`
        : `Escriu-ho en ${NATIVE_NAME[data.nativeCode] || data.nativeCode}`;
    const input = card.kind === "fraction"
      ? ' aria-label="Fracció"'
      : card.kind === "pair" ? ' aria-label="Coordenades"'
      : card.kind === "factorization" ? ' aria-label="Descomposició en factors"'
      : card.kind === "algebraic" ? ' aria-label="Expressió"'
      : card.kind === "sexagesimal" ? ' aria-label="Temps o angle"'
      : card.math ? ' inputmode="numeric" aria-label="Resultat"' : ' aria-label="Traducció"';
    const buttons = choice
      ? `<div class="flash-choices" id="flash-choices" role="group" aria-label="Opcions">${card.options
          .map((o, i) => `<button type="button" class="flash-choice" data-choice="${i}"><kbd>${i + 1}</kbd><span>${escText(o)}</span></button>`)
          .join("")}</div>`
      : "";
    screen.innerHTML = `
      <div class="flash-panel flash-play">
        <div class="flash-top">
          <button type="button" class="ghost" data-act="menu">‹ Menú</button>
          <span class="flash-prog" id="flash-prog"></span>
        </div>
        <div class="flash-dots" id="flash-dots" aria-hidden="true"></div>
        <div class="flash-stage${card.prompt.length > 40 ? " flash-long" : ""}" id="flash-stage">
          <p class="flash-dir">${escText(dirLabel)}</p>
          ${card.figure ? `<div class="flash-fig">${C.figureSvg(card.figure)}</div>` : ""}
          <div class="flash-word">${escText(card.prompt)}</div>
          <div class="flash-timer ok" id="flash-timer"${card.limit ? "" : " hidden"}>
            <div class="flash-tbar"><i id="flash-tbar"></i></div>
            <span class="flash-tsec" id="flash-tsec"></span>
          </div>
          <div class="flash-hint" id="flash-hint"></div>
          <div class="flash-feedback" id="flash-feedback" aria-live="polite"></div>
        </div>
        ${buttons}
        <form class="flash-form" id="flash-form" autocomplete="off">
          <input id="flash-input" type="text"${input}${choice ? " hidden" : ""} autocomplete="off" autocapitalize="off" spellcheck="false">
          <span class="flash-unit" id="flash-unit"${card.unit ? "" : " hidden"}>${escText(card.unit)}</span>
          <button type="submit" class="primary" id="flash-ok"${choice ? " hidden" : ""}>Comprova</button>
        </form>
      </div>`;
    paintProgress();
    paintCard(null);
    startTimer();
    if (choice) focusChoice();
    else q("#flash-input").focus();
  }

  // choice: els botons segueixen l'estat de la targeta (errors desactivats; en acabar, la correcta marcada).
  function paintChoices() {
    const box = q("#flash-choices");
    if (!box || !card) return;
    box.querySelectorAll("[data-choice]").forEach((b) => {
      const i = Number(b.dataset.choice);
      const off = card.off.includes(i);
      b.disabled = off || card.done;
      b.classList.toggle("wrong", off);
      b.classList.toggle("right", card.done && card.options[i] === card.accepted[0]);
    });
  }

  function focusChoice() {
    const box = q("#flash-choices");
    if (!box || card.done) return;
    const next = box.querySelector("[data-choice]:not(:disabled)");
    if (next) next.focus();
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
    const choice = card.kind === "choice";
    paintChoices();
    if (btn) btn.hidden = choice && !card.done;
    if (!card.done) {
      fb.textContent = card.note || (card.misses === 0 ? "" : card.misses === 1 ? "No és aquesta. Torna-ho a provar." : "Encara no. Mira la pista.");
      hint.textContent = card.misses >= 2 ? C.hintFor(card.kind, card.accepted[0], card.lang, card.mode) : "";
      btn.textContent = "Comprova";
      if (choice) focusChoice();
      return;
    }
    stage.classList.add(card.how === "revealed" ? "reveal" : "ok");
    hint.textContent = "";
    const shown = card.how === "revealed" ? card.accepted[0] : card.form;
    const others = card.accepted.filter((x) => x !== shown);
    const answerText = card.accepted[0] + (card.unit ? ` ${card.unit}` : "");
    let text;
    if (card.timedOut) text = `⏱ Temps! La resposta és «${answerText}».`;
    else if (card.how === "revealed") text = `La resposta és «${answerText}».`;
    else if (card.exact) text = "✓ Correcte";
    else if (FORM_KINDS.includes(card.kind)) text = `✓ Correcte · la forma habitual és «${card.form}»`;
    else text = `✓ Correcte · l'ortografia és «${card.form}»`;
    if (others.length) text += ` També: ${others.join(", ")}.`;
    if (card.how === "revealed") {
      text += (card.returned ? "" : " Torna al final de la ronda.") + (card.timedOut ? "" : " Enter per continuar.");
    }
    fb.textContent = text;
    btn.textContent = "Següent";
    if (choice) btn.focus();
  }

  // Una resposta de l'alumne: encert, error (1r, 2n) o 3r error (resposta mostrada).
  function attempt(text) {
    if (!card || card.done || card.kind === "choice" || !String(text).trim()) return;
    let res;
    if (!card.math) res = C.check(text, card.accepted, card.lang);
    else if (card.kind === "fraction") res = C.checkFraction(text, card.accepted, card.rule);
    else if (card.kind === "unit") res = C.checkNumber(C.stripUnit(text, card.unit), card.accepted);
    else if (card.kind === "pair") res = C.checkPair(text, card.accepted);
    else if (card.kind === "factorization") res = C.checkFactorization(text, card.accepted);
    else if (card.kind === "algebraic") res = C.checkAlgebraic(text, card.accepted);
    else if (card.kind === "sexagesimal") res = C.checkSexagesimal(text, card.accepted[0], card.mode);
    else res = C.checkNumber(text, card.accepted);
    if (res.ok) {
      resolve(C.outcome({ ok: true, misses: card.misses }), res);
      return;
    }
    card.misses += 1;
    card.note = res.note || null; // a note of the check (p. ex. normalitza), shown until the next try
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

  // Una opció de choice: encert, o error (el botó triat queda desactivat). Quan només en queda una
  // d'activa, la resposta es revela.
  function choose(i) {
    if (!card || card.done || card.kind !== "choice" || card.off.includes(i) || i < 0 || i >= card.options.length) return;
    const res = C.checkChoice(card.options[i], card.accepted);
    if (res.ok) {
      resolve(C.outcome({ ok: true, misses: card.misses }), res);
      return;
    }
    card.misses += 1;
    card.off.push(i);
    const exhausted = card.options.length - card.off.length <= 1;
    const how = C.outcome({ ok: false, misses: card.misses, exhausted });
    if (how) {
      resolve(how, null);
      return;
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
    const t = e.target.closest ? e.target.closest("[data-act],[data-dir],[data-timer],[data-list],[data-choice]") : null;
    if (!t) return;
    if (t.dataset.choice !== undefined) return choose(Number(t.dataset.choice));
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
    if (e.key === "Escape") {
      if (view === "menu") closeFlash();
      else renderMenu();
      return;
    }
    // choice: les tecles 1..n trien l'opció
    if (view === "card" && card && card.kind === "choice" && !card.done && /^[1-9]$/.test(e.key)) {
      e.preventDefault();
      choose(Number(e.key) - 1);
    }
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
