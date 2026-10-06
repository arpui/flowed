#!/usr/bin/env python3
"""Mathbench: is the model good enough for the OPEN math practices, and how good?

WP3.4. The closed path (bank: 🔁 Review / 🎲 Go / 📚 Facts) needs no model at
all. The open ones do — 📝 Raonament (math-writing: explain / error-analysis /
compare-strategies) and 📖 Problemes (math-reading: always task='word-problem')
— and nobody had measured the production model on them. This drives both
through the REAL server, over HTTP as the browser does, with the fixed learner
of bench/learner-math.md (the same seeded error classes for every model) and
scores the TUTOR's behaviour:

  sufficiency (rates; the verdict needs >= 90 % in each)
    ok          no LLM/HTTP error in the reply
    saved       the answer reached <profile>/.records
    graded      a score exists (math_record_answer or the text)
    shown       the score is on screen — she sees how she did
    consistent  the score in the tool call = the score shown
    contract    the parseable feedback: marker + correction arrow +
                **Correct version:** + **Score: N/10**
    taxonomy    every correction category is one of the 12 math classes
                (never a language one)
    band        the score lands in the rubric band the seeded error class
                deserves (bare → 0-4, calc-slip/thin → 5-7, correct → 8-10)
    skill       the record's skill matches the task: reasoning (📝) / problems (📖)
    task_ok     the task on screen has the guard shape: no bare list and a
                justification cue (📝); a real story and the work demanded (📖)
    clean       no template braces, menu, re-greeting or non-Latin script
    continues   after grading, the next task is presented
    grade_clean a score or an arrow only ever appears with a COMPLETE grade
                (intermediate turns stay clean — the WP2.5 rule the prose
                parser of persist-session depends on)
  quality (reported, not gated)
    band_soft   one band off in a rubric-defensible way (a strict 0-4 for a
                calculation slip; a lenient 5-7 for a full answer)
    long_corr   a correction quote at the 400-char CORRECTION_RE ceiling
    guards      task-guard rewrites the server had to force (0 = the model
                demanded the work on its own) — read from .metrics/guards.jsonl
    coverage    which of the four open tasks the model actually sent (the
                `task` argument of math_deep_evaluate)

  The learner's answers are generated from the task on screen (the expression
  or statement the tutor just set), so the seeded error always fits the real
  question — but a model that sets an unparseable task gets a generic answer,
  and a harsh grade on it is reported, not excused: the transcript shows why.

    # the server must be up on a TEST profile, talking to the model under test
    scripts/flowed-web.sh --app --port 4200 test-math
    python3 scripts/flowed-mathbench.py run --port 4200 --name qwen3-14b test-math
    python3 scripts/flowed-mathbench.py run --port 4200 --name cand --only reading
    python3 scripts/flowed-mathbench.py compare
    python3 scripts/flowed-mathbench.py rescore results/mathbench/<name>-<time>.json

It writes to the profile (it answers exercises), so only test*/demo*/e2e*.
Results: results/mathbench/<name>-<time>.json (+ .md transcript).
See docs/MODELBENCH.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import statistics
import sys
import time
import urllib.error
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("FLOWED_BENCH_OUT") or REPO / "results" / "mathbench")
sys.path.insert(0, str(REPO / "hooks"))
from main_paths import profiles_root  # noqa: E402
from db_schema import (ERROR_CATEGORIES, ERROR_CATEGORY_ALIASES,  # noqa: E402
                       normalize_error_category)


def _e2e():
    spec = importlib.util.spec_from_file_location("flowed_e2e", REPO / "scripts" / "flowed-e2e.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E2E = _e2e()

# The two open practices. `classes` are the seeded error classes of
# bench/learner-math.md, in the order they are answered; `skill` is the C7 key
# the record must land under.
PRACTICES = {
    "math-writing": {"skill": "reasoning", "classes": ["bare", "slip", "correct"]},
    "math-reading": {"skill": "problems", "classes": ["bare", "slip", "correct"]},
}

LLM_ERR = re.compile(r"LLM HTTP|TemplateError|Unable to connect|⚠️", re.I)
MARKER = re.compile(r"[🟢🟡🔴✅❌]")
SCORE = re.compile(r"\b(\d{1,2})\s*/\s*10\b")
# The grade line shape the server's own CORRECTION_RE (pacing.ts) parses; the
# 400-char quotes are its ceiling — a longer quote is dropped from the derived
# record, so the bench watches for it (long_corr).
ARROW = re.compile(
    r'^[-*]\s*[🔴🟡🟢❌✅]?\s*["“\']([^"”\n]{1,400})["”\']\s*(?:→|->|=>)\s*\*{0,2}["“\']?([^"”\n*]{1,400})',
    re.M)
NON_LATIN = re.compile(r"[Ѐ-ӿ֐-ۿ぀-ヿ㐀-鿿가-힯]")
NEXT_TASK = re.compile(
    r"explica|per què|justifica|demostra|troba|inventa|com ho|operació|enunciat|problema|"
    r"cua de repàs|escriv[^\n]{0,15}\"?(?:yes|no|sí)\"?|\?\s*$", re.I)

# Mirrors of the server guards (pacing.ts), for MEASUREMENT only — the guards
# themselves stay the product's; guards.jsonl is the authoritative record of
# them firing. These answer "did the task on screen have the shape the guards
# demand", so a run where the model needed no rewrite still proves it.
REASONING_CUT = re.compile(
    r"#{1,3}\s*(?:✍️|📝)?\s*(?:Writing|Raonament|Reasoning|Repte)\s*(?:Exercise|Task)?|\*\*Task:?\*\*", re.I)
PROBLEM_CUT = re.compile(r"#{1,3}\s*(?:📖)?\s*(?:Problema\b|Word problem\b)|\*\*Enunciat:?\*\*", re.I)
LIST_RE = re.compile(
    r"\b(?:fes|feu|fem|crea|make|do|create)\s+(?:una?\s+|la\s+)?(?:llista|llistat|lista|list)\b"
    r"|llista de|llistat de|\benumera\b|anomena\s+(?:tots|totes|tothom)|\blist of\b|\benumerate\b|\bname all\b", re.I)
JUSTIFY_RE = re.compile(
    r"\b(?:explica|per què|perquè|com ho (?:has|heu|vas|vau|faries|faràs|faras|fareu)|com funciona"
    r"|com ho faries|com ho feu|justifica|demostra|motiva|argumenta|raona|troba|inventa|necessites"
    r"|quina operació|què cal|què necessites|why|explain|justify|prove|how did you"
    r"|which operation|what operation)\b", re.I)
WORK_RE = re.compile(
    r"\b(?:operació|operacions|una per línia|pas a pas|com ho (?:has|heu|vas|vau|faries)"
    r"|explica|raona|justifica)\b", re.I)
PURE_EXPR = re.compile(r"^[\d\s.,+\-−×x*/·÷()=]+$")

# Which open task the presented task is (for the answer generator; the
# authoritative coverage signal is the task argument of math_deep_evaluate).
KIND_ERROR = re.compile(
    r"troba|què (?:no va bé|hi ha mal|està mal)|error|està (?:ben|mal)ament|té sentit|què hi ha de", re.I)
KIND_COMPARE = re.compile(
    r"estrat[èe]gia|compara|dues maneres|més fàcil|millor manera|quina (?:de les|manera|és més)", re.I)

# ---- arithmetic the answer generator needs (pure, tested) ---------------------
NUM = r"\d{1,3}(?:[.,]\d+)?"
WORKED_RE = re.compile(rf"({NUM})\s*([+\-−×x*/·÷])\s*({NUM})\s*=\s*({NUM})")
# spaced operators only: "3/4 d'un pastís" is a FRACTION in the statement, not
# the operation to run (run 2, 2026-10-06: the generator answered a fraction
# subtraction task with "3 / 4 = 0.75")
BARE_EXPR_RE = re.compile(
    rf"({NUM})\s+([+\-−×x*/·÷])\s+({NUM})(?!\s*(?:frases|paraules|words|dies|dias|xifres|anys))")
TRI_RE = re.compile(rf"({NUM})\s*([+\-−])\s*({NUM})\s*([×x*/·÷])\s*({NUM})")
TRI2_RE = re.compile(rf"({NUM})\s*([×x*/·÷])\s*({NUM})\s*([+\-−])\s*({NUM})")


def _num(s: str) -> float:
    return float(str(s).replace(",", "."))


def _apply(a: float, op: str, b: float) -> float:
    if op == "+":
        return a + b
    if op in "-−":
        return a - b
    if op in "×x*·":
        return a * b
    if op in "/÷":
        return a / b if b else float("nan")
    return float("nan")


def fmt_num(v: float) -> str:
    if v != v:  # NaN
        return "?"
    return str(int(v)) if float(v).is_integer() else f"{round(v, 2):g}"


def parse_worked(text: str) -> dict | None:
    """A worked line `a op b = c` (or the classic `a + b × c = d`, also written
    «no és 20») with its true value. None when the task shows no computable
    line with a claimed result."""
    tri = TRI_RE.search(text) or TRI2_RE.search(text)
    two = WORKED_RE.search(text)
    if two and (not tri or two.start() <= tri.start()):
        a, op, b, shown = _num(two.group(1)), two.group(2), _num(two.group(3)), _num(two.group(4))
        return {"a": a, "op": op, "b": b, "shown": shown, "true": _apply(a, op, b), "tri": False}
    if tri:
        t1, o1, t2, o2, t3 = (_num(tri.group(1)), tri.group(2), _num(tri.group(3)),
                              tri.group(4), _num(tri.group(5)))
        if o1 in "×x*/·÷":  # a × b + c — left-to-right already obeys precedence
            mid = _apply(t1, o1, t2)
            true = ltr = _apply(mid, o2, t3)
            step1 = f"{fmt_num(t1)} {o1} {fmt_num(t2)} = {fmt_num(mid)}"
            step2 = f"{fmt_num(mid)} {o2} {fmt_num(t3)} = {fmt_num(true)}"
            step2_slip = f"{fmt_num(mid)} {o2} {fmt_num(t3)} = {fmt_num(true + 7)}"
        else:               # a + b × c — precedence lives here
            mid = _apply(t2, o2, t3)
            true = _apply(t1, o1, mid)
            ltr = _apply(_apply(t1, o1, t2), o2, t3)
            step1 = f"{fmt_num(t2)} {o2} {fmt_num(t3)} = {fmt_num(mid)}"
            step2 = f"{fmt_num(t1)} {o1} {fmt_num(mid)} = {fmt_num(true)}"
            step2_slip = f"{fmt_num(t1)} {o1} {fmt_num(mid)} = {fmt_num(true + 7)}"
        # the claimed result: "= 20", "no és 20", "és 20" right after the line
        eq = re.search(rf"(?:=\s*|no\s+és\s+|és\s+)({NUM})", text[tri.end():])
        if not eq:
            return None  # a three-term expression with no claimed result is not a worked line
        return {"a": t1, "op": f"{o1} {o2}", "b": t3, "mid": mid, "step1": step1,
                "step2": step2, "step2_slip": step2_slip,
                "shown": _num(eq.group(1)), "true": true, "ltr": ltr, "tri": True}
    return None


def parse_bare_expr(text: str) -> tuple[float, str, float] | None:
    m = BARE_EXPR_RE.search(text)
    if not m:
        return None
    # never the prefix of a three-term line ("3 + 2" inside "3 + 2 × 4")
    rest = text[m.end():]
    if re.match(r"\s*[+\-−×x*/·÷]", rest):
        return None
    return _num(m.group(1)), m.group(2), _num(m.group(3))


OP_WHY = {"÷": "repartir entre iguals", "×": "tantes vegades el mateix grup",
          "−": "la diferència entre les dues quantitats", "+": "juntar les dues parts"}


# "repartir" alone is NOT division: "cada jugador rep 5 fitxes, 8 jugadors,
# quants se'n repartiran EN TOTAL" is × (run 2 artifact). The strong division
# cues are the sharing-equal-shares shapes; the multiplication cues are the
# equal-groups-of shape.
STRONG_DIV = (r"entre iguals|parts iguals|quants en toquen|a cada|en cada|"
              r"repartir-?los entre|entre \d+ (?:amics|amigues|nens|nenes|persones|cistelles|caixes|grups)")
MULT = (r"cada [a-zà-ú]+ (?:rep|té|te|conté|rebre|donen|donar|hi ha|neu)|"
        r"\b(?:files?|grups?|caixes?|paquets?|cistelles?) de \d+|"
        r"quants[^.\n]*en total|"
        r"per cada \d+|el doble|el triple|el qu[àa]druple")


def infer_op(text: str) -> tuple[str, bool]:
    """The operation a word-problem statement calls for, by story cues.
    The bool says whether a cue actually matched (confident) or we defaulted."""
    if re.search(MULT, text, re.I) and not re.search(STRONG_DIV, text, re.I):
        return "×", True
    if re.search(STRONG_DIV, text, re.I):
        return "÷", True
    cues = [("−", r"quants en falten|diferència|més gran|més petit|sobren|que li queda|restar|quants li (?:falten|sobren)"),
            ("+", r"en total|tots dos|totes dues|junts|sumar|quants hi ha|quants en té|quants en tindran")]
    for op, rx in cues:
        if re.search(rx, text, re.I):
            return op, True
    return "+", False


def classify_kind(task: str) -> str:
    if KIND_ERROR.search(task):
        return "error-analysis"
    if KIND_COMPARE.search(task):
        return "compare-strategies"
    return "explain"


def task_half(text: str, practice: str) -> str | None:
    """The task slice of a reply (from its task heading), or None when the
    reply presents no task — a pure grade, a claus table, a question. The
    learner's next answer is generated from the LAST real task, never from a
    feedback reply (whose quoted numbers would poison the generator)."""
    cut = REASONING_CUT.search(text) if practice == "math-writing" else PROBLEM_CUT.search(text)
    return text[cut.start():] if cut else None


OP_NAME = {"+": "una suma", "-": "una resta", "−": "una resta", "×": "una multiplicació",
           "x": "una multiplicació", "*": "una multiplicació", "·": "una multiplicació",
           "/": "una divisió", "÷": "una divisió"}


def parse_chain(text: str) -> list[tuple[float, str, float, float, float]]:
    """Every worked segment `a op b = c` in the task, with its true value —
    a multi-step solution shown by the tutor ("3 × 6 = 18, 18 − 4 = 14")."""
    out = []
    for m in WORKED_RE.finditer(text):
        a, op, b, shown = _num(m.group(1)), m.group(2), _num(m.group(3)), _num(m.group(4))
        out.append((a, op, b, shown, _apply(a, op, b)))
    return out


def make_answer(task: str, cls: str, practice: str) -> tuple[str, str]:
    """The fixed learner's answer (bench/learner-math.md) to the task on
    screen, seeding the requested error class. Returns (answer, seed) where
    seed is the class the answer ACTUALLY seeded (a slip on a word problem
    with a confident operation becomes wrong-op, which is the stronger test)."""
    kind = classify_kind(task)
    if practice == "math-reading":
        en = re.search(r"\*\*Enunciat:?\*\*\s*([^\n]+)", task, re.I)
        pool = en.group(1) if en else task
        nums = [int(n) for n in re.findall(r"\d+", pool) if int(n) > 1][:2]
        op, confident = infer_op(task)
        # "el doble/triple" needs only one number in the statement
        dbl = re.search(r"el (doble|triple|qu[àa]druple)", pool, re.I)
        if dbl and nums:
            m = {"doble": 2, "triple": 3}.get(dbl.group(1).lower(), 4)
            a = nums[0]
            if cls == "bare":
                return f"El resultat és {a * m}.", "bare"
            if cls == "slip":
                return f"Operació: {a} × {m} = {a * m + 7}. Resposta: {a * m + 7}.", "calc-slip"
            return (f"Operació: {a} × {m} = {a * m}. Resposta: {a * m}. "
                    f"L'enunciat diu {dbl.group(1).lower()}, per això multipliquem."), "correct"
        if len(nums) < 2:
            if cls == "bare":
                return "El resultat és 12.", "bare"
            if cls == "slip":
                return ("Primer llegeixo què demana l'enunciat i trió l'operació. "
                        "Després calculo a poc a poc. El resultat és 19."), "calc-slip"
            return ("Primer llegeixo què demana l'enunciat i trió l'operació: si reparteix entre "
                    "iguals, divisió. Després calculo i comprovo que el resultat té sentit."), "correct"
        # rate statements ("8 litres per cada 100 km, en fa 300") need two
        # steps: units first, then the total — a single a×b would be wrong
        rate = re.search(r"per cada (\d+(?:[.,]\d+)?)", pool)
        if rate:
            pre = re.search(r"(\d+(?:[.,]\d+)?)\s*[^.\n]*?per cada", pool)
            post = re.findall(r"\d+(?:[.,]\d+)?", pool[rate.end():])
            if pre and post:
                v, per, tot = _num(pre.group(1)), _num(rate.group(1)), _num(post[0])
                units = tot / per if per else 0.0
                final = v * units
                if cls == "bare":
                    return f"El resultat és {fmt_num(final)}.", "bare"
                if cls == "slip":
                    return (f"Operació: {fmt_num(tot)} ÷ {fmt_num(per)} = {fmt_num(units)}, "
                            f"després {fmt_num(v)} × {fmt_num(units)} = {fmt_num(final + 7)}. "
                            f"Resposta: {fmt_num(final + 7)}."), "calc-slip"
                return (f"Operació: {fmt_num(tot)} ÷ {fmt_num(per)} = {fmt_num(units)}, després "
                        f"{fmt_num(v)} × {fmt_num(units)} = {fmt_num(final)}. Resposta: "
                        f"{fmt_num(final)}. L'enunciat dona un ritme per cada unitat, per això "
                        "primer compto les unitats i després el total."), "correct"
        a, b = nums
        if cls == "bare":
            return f"El resultat és {fmt_num(_apply(a, op, b))}.", "bare"
        if cls == "slip":
            if confident and op != "+":
                return f"Operació: {a} + {b} = {a + b}. Resposta: {a + b}.", "wrong-op"
            val = _apply(a, op, b)
            return (f"Operació: {a} {op} {b} = {fmt_num(val + 7)}. "
                    f"Resposta: {fmt_num(val + 7)}."), "calc-slip"
        val = _apply(a, op, b)
        return (f"Operació: {a} {op} {b} = {fmt_num(val)}. Resposta: {fmt_num(val)}. "
                f"L'enunciat demana {OP_WHY[op]}, per això aquesta operació."), "correct"

    # math-writing: explain / error-analysis / compare-strategies
    w = parse_worked(task)
    chain = parse_chain(task)
    wrong = next((s for s in chain if s[3] != s[4]), None)
    if kind == "error-analysis" and (wrong or (w and w["shown"] != w["true"])):
        # she is asked to find the error in a shown line
        if cls == "bare":
            return "Està malament.", "bare"
        seg = wrong or (w["a"], w["op"], w["b"], w["shown"], w["true"])
        a, op, b, shown, true = seg
        if cls == "slip":
            return (f"He trobat l'error: el resultat hauria de ser {fmt_num(true + 7)} "
                    f"en lloc de {fmt_num(shown)}."), "calc-slip"
        return (f"L'error és el resultat: {fmt_num(a)} {op} {fmt_num(b)} fa "
                f"{fmt_num(true)}, no {fmt_num(shown)}. Perquè l'operació ben feta "
                "dona aquest nombre."), "correct"
    if w and w["shown"] != w["true"]:
        # the task shows a line whose result is wrong and asks to explain the
        # claim ("per què 3 + 2 × 4 no és 20?") — the work to show is the fix
        if cls == "bare":
            return f"El resultat és {fmt_num(w['true'])}.", "bare"
        if w["tri"]:
            if cls == "slip":
                return (f"Primer {w['step1']}, després {w['step2_slip']}. "
                        "Perquè la multiplicació es fa abans."), "calc-slip"
            return (f"Primer la multiplicació: {w['step1']}, després {w['step2']}. "
                    "Perquè la multiplicació va abans que la suma."), "correct"
        a, op, b = w["a"], w["op"], w["b"]
        if cls == "slip":
            return (f"{fmt_num(a)} {op} {fmt_num(b)} = {fmt_num(w['true'] + 7)}. "
                    "Per què funciona: perquè descompondre no canvia el resultat, només el fa "
                    "més fàcil de fer de cap."), "calc-slip"
        why = OP_WHY.get(op, "l'operació és la que demana la situació")
        return (f"{fmt_num(a)} {op} {fmt_num(b)} = {fmt_num(w['true'])}. "
                f"Per què funciona: perquè {why}, i descompondre no canvia el resultat."), "correct"
    if len(chain) >= 2:
        # the task shows a correct multi-step solution and asks her to explain
        # it: she replays the steps (with the seeded slip on the last one)
        final = chain[-1][3]
        if cls == "bare":
            return f"El resultat és {fmt_num(final)}.", "bare"
        steps = [f"{fmt_num(a)} {op} {fmt_num(b)} = {fmt_num(sh)}" for a, op, b, sh, _ in chain]
        why = (f"perquè primer faig {OP_NAME.get(chain[0][1], 'un càlcul')} i després "
               f"{OP_NAME.get(chain[-1][1], 'un altre càlcul')}")
        if cls == "slip":
            a, op, b, _sh, true = chain[-1]
            steps[-1] = f"{fmt_num(a)} {op} {fmt_num(b)} = {fmt_num(true + 7)}"
            return (", ".join(steps) + f". Per què funciona: perquè {why}."), "calc-slip"
        return (", ".join(steps) + f". Per què funciona: perquè {why}."), "correct"
    e = parse_bare_expr(task)
    if e:
        a, op, b = e
        val = _apply(a, op, b)
        if cls == "bare":
            return f"El resultat és {fmt_num(val)}.", "bare"
        if cls == "slip":
            return (f"{fmt_num(a)} {op} {fmt_num(b)} = {fmt_num(val + 7)}. "
                    "Per què funciona: perquè descompondre no canvia el resultat, només el fa "
                    "més fàcil de fer de cap."), "calc-slip"
        why = OP_WHY.get(op, "l'operació és la que demana la situació")
        return (f"{fmt_num(a)} {op} {fmt_num(b)} = {fmt_num(val)}. "
                f"Per què funciona: perquè {why}, i descompondre no canvia el resultat."), "correct"
    # no computable line: a claim or a strategy question. A task whose
    # operation is only implied by prose ("comparteixes 1/8 … quina fracció
    # quedarà?") cannot get a controlled answer — seed "generic" and let the
    # band gate skip it rather than blame the model for a wrong answer.
    if re.search(r"\d\s*/\s*\d", task):
        if cls == "bare":
            return "Està bé.", "generic"
        if cls == "slip":
            return ("Primer miro les fraccions i després faig l'operació. El resultat és "
                    "5/8 perquè restant a dalt i a baix les parts queden juntes."), "generic"
        return ("Primer converteixo a un denominador comú i després resto: per això el "
                "resultat és una fracció més petita que la que tenia al principi."), "generic"
    if cls == "bare":
        return ("Està bé." if kind != "compare-strategies" else "La primera."), "bare"
    if cls == "slip":
        return "Faccio la multiplicació perquè és més ràpida que sumar.", "thin"
    return ("Les dues maneres arriben al mateix resultat; la multiplicació és més ràpida "
            "perquè sumar tantes vegades el mateix nombre és exactament multiplicar."), "correct"


def judge_band(seed: str, score: int | None) -> str | None:
    """ok / soft / fail: does the score land in the rubric band the seeded
    class deserves (DEEP_RUBRIC bands 10 / 8-9 / 5-7 / 0-4)?"""
    if score is None:
        return None
    if seed == "bare":
        return "ok" if score <= 4 else "fail"
    if seed in ("calc-slip", "thin"):
        return "ok" if 5 <= score <= 7 else ("soft" if score <= 4 else "fail")
    if seed == "wrong-op":
        return "ok" if score <= 4 else "fail"
    if seed == "correct":
        return "ok" if score >= 8 else ("soft" if score >= 5 else "fail")
    return None  # "generic": no controlled error was seeded, no band verdict


def task_shape(text: str, practice: str) -> tuple[bool, str]:
    """Does the task on screen have the shape the WP3.3/WP3.2 guards demand?
    Measurement mirror only — see the note above the regexes."""
    cut = REASONING_CUT.search(text) if practice == "math-writing" else PROBLEM_CUT.search(text)
    task = text[cut.start():] if cut else text
    if practice == "math-writing":
        if LIST_RE.search(task):
            return False, "bare list"
        if not JUSTIFY_RE.search(task):
            return False, "no justification cue"
        return True, ""
    if not PROBLEM_CUT.search(text):
        return False, "no statement heading"
    en = re.search(r"\*\*Enunciat:?\*\*\s*([^\n]+)", task, re.I)
    if en and PURE_EXPR.match(en.group(1).strip()):
        return False, "Enunciat is pure arithmetic"
    if not WORK_RE.search(task):
        return False, "work not demanded"
    return True, ""


def categories_of(text: str) -> list[str]:
    """The correction categories the learner actually sees, read off the
    arrow lines (same shape the server's parseFeedback reads). Surface
    spellings ("transport — …") are normalized exactly as the server does;
    the raw label is kept for the report."""
    cats = []
    for line in text.splitlines():
        m = ARROW.match(line.strip())
        if not m:
            continue
        tail = line[line.find("→"):] if "→" in line else line
        cm = re.search(r"\(\s*([^—–\n)]{1,60})", tail)
        if cm:
            cats.append(cm.group(1).strip())
    return cats


# ---- live driving ------------------------------------------------------------

def record_of(outcome) -> dict | None:
    for p in (outcome or {}).get("parts") or []:
        if p.get("type") == "tool" and p.get("tool") == "math_record_answer":
            return ((p.get("state") or {}).get("input")) or {}
    return None


def deep_task_of(outcome) -> str | None:
    for p in (outcome or {}).get("parts") or []:
        if p.get("type") == "tool" and p.get("tool") == "math_deep_evaluate":
            inp = (p.get("state") or {}).get("input") or {}
            return inp.get("task") or None
    return None


def text_score(text: str) -> int | None:
    m = SCORE.search(text)
    return int(m.group(1)) if m else None


def turn(fn, *args):
    """One live turn. The remote model host has had brief resets; a refused
    connection is retried twice before the row is marked failed."""
    last_err = ""
    for i in range(3):
        t0 = time.time()
        try:
            out = fn(*args)
            return out, round(time.time() - t0, 1), ""
        except urllib.error.HTTPError as e:
            out, last_err = None, f"HTTP {e.code}"
            if e.code < 500:
                return out, round(time.time() - t0, 1), last_err
        except Exception as e:  # noqa: BLE001 — a bench reports, it does not crash
            last_err = str(e)[:200]
        if i < 2:
            time.sleep(4)
    return None, round(time.time() - t0, 1), last_err


def records_count(prof: Path, sid: str) -> int:
    f = prof / ".records" / f"{sid}.jsonl"
    try:
        return sum(1 for l in f.read_text(encoding="utf-8").splitlines() if l.strip())
    except OSError:
        return 0


def new_records(prof: Path, sid: str, before: int) -> list[dict]:
    f = prof / ".records" / f"{sid}.jsonl"
    try:
        lines = [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return []
    out = []
    for l in lines[before:]:
        try:
            out.append(json.loads(l))
        except ValueError:
            pass
    return out


def guard_fires(prof: Path, sid: str) -> list[str]:
    """Task-guard rewrites the server forced this session (reasoningTaskGuard,
    wordProblemTaskGuard, writingBlankGuard) — the authoritative signal that
    the model did NOT demand the work on its own."""
    f = prof / ".metrics" / "guards.jsonl"
    try:
        lines = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []
    fired = []
    for g in lines:
        if g.get("session") != sid:
            continue
        note = str(g.get("note", ""))
        if note.startswith("This is Raonament") or note.startswith("This is 📖 Problemes"):
            fired.append(note[:90])
    return fired


def category_is_math(raw: str) -> bool:
    """A correction category the learner sees is a math one only if it is a
    canonical class or a known surface alias. An INVENTED label ("justification
    — the explanation is missing", seen live 2026-10-06) passes the server's
    normalize only because unknown labels fall back to DEFAULT_ERROR_CATEGORY
    ("calculation") — which records a missing justification as an arithmetic
    slip. The bench must not let that through the taxonomy gate."""
    canon = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return canon in ERROR_CATEGORIES or canon in ERROR_CATEGORY_ALIASES


def judge(practice: str, step: str, text: str, err: str, tool: dict,
          seed: str | None, expected_skill: str, rec_skill: str | None) -> dict:
    shown = text_score(text)
    tool_score = tool.get("score") if isinstance(tool, dict) else None
    row = {"ok": not err and not LLM_ERR.search(text) and bool(text),
           "clean": not E2E.BRACE.search(E2E.on_screen(text))
                    and not E2E.MENU_RE.search(text) and not NON_LATIN.search(text)
                    and (step == "start" or not E2E.GREETING_RE.search(text))}
    if step == "pass":
        # the learner only answered the 📚 claus yes/no offer: nothing to grade,
        # so a score or an arrow here would be the tutor grading an answer it
        # never asked for
        row["grade_clean"] = not SCORE.search(text) and not ARROW.search(text)
        return row
    if step == "start":
        ok, why = task_shape(text, practice)
        row["task_ok"] = ok
        row["task_why"] = why
        row["grade_clean"] = not SCORE.search(text) and not ARROW.search(text)
        return row
    score = tool_score if isinstance(tool_score, (int, float)) else shown
    row["score"] = score
    row["graded"] = score is not None
    row["shown"] = shown is not None
    if isinstance(tool_score, (int, float)) and shown is not None:
        row["consistent"] = int(tool_score) == shown
    cats = categories_of(text)
    row["contract"] = (bool(MARKER.search(text)) and "Correct version:" in text
                       and shown is not None
                       and (score is None or score >= 8 or bool(cats)))
    # a surface spelling ("transport — …") is fine — the server normalizes it
    # to a math class; a language-era one ("grammar") or an invented one
    # ("justification") is what this dimension exists to catch
    row["taxonomy"] = all(category_is_math(c) for c in cats)
    row["grade_clean"] = not ((SCORE.search(text) or ARROW.search(text)) and "Correct version:" not in text)
    # the next task must come AFTER the grade — the feedback itself mentions
    # "operació" and "problema" constantly, so cues alone would always pass
    cut = REASONING_CUT if practice == "math-writing" else PROBLEM_CUT
    last = None
    for m in SCORE.finditer(text):
        last = m
    tail = text[last.end():] if last else text
    row["continues"] = bool(cut.search(tail)) or bool(NEXT_TASK.search(tail[-400:])) or tail.strip().endswith("?")
    row["long_corr"] = any(len(m.group(1)) >= 400 or len(m.group(2)) >= 400 for m in ARROW.finditer(text))
    if seed:
        row["band"] = judge_band(seed, score if score is not None else None)
        if row["band"] is not None:
            row["band_ok"] = row["band"] != "fail"
    got = rec_skill or (str(tool.get("skill", "")) if isinstance(tool, dict) else "")
    row["skill"] = got
    row["skill_ok"] = got == expected_skill
    return row


def run_once(cli, prof: Path, practice: str, spec: dict, transcript: list[str]) -> list[dict]:
    rows = []
    sid = cli.new_session()
    out, secs, err = turn(cli.command, sid, practice)
    text = E2E.tutor_text(out)
    cur_task = task_half(text, practice) or text
    kind = classify_kind(cur_task)
    transcript.append(f"## {practice} · sessió {sid}\n\n**[button]** ({secs}s)\n\n{text or err}\n")
    rows.append({"practice": practice, "step": "start", "kind": kind, "secs": secs,
                 "text": text or err, "sid": sid,
                 **judge(practice, "start", text, err, {}, None, spec["skill"], None)})
    for cls in spec["classes"]:
        answer, seed = make_answer(cur_task, cls, practice)
        before = records_count(prof, sid)
        out, secs, err = turn(cli.say, sid, answer)
        text = E2E.tutor_text(out)
        tool = record_of(out) or {}
        recs = []
        for _ in range(20):  # the server may write the record just after replying
            recs = new_records(prof, sid, before)
            if recs:
                break
            time.sleep(0.5)
        rec_skill = str(recs[-1].get("skill", "")) if recs else None
        row = {"practice": practice, "step": cls, "seed": seed, "kind": classify_kind(cur_task),
               "answer": answer, "secs": secs, "text": text or err, "sid": sid,
               "deep_task": deep_task_of(out), "tool_score": tool.get("score"),
               "saved": bool(recs),
               **judge(practice, cls, text, err, tool, seed, spec["skill"], rec_skill)}
        rows.append(row)
        transcript.append(f"**Learner** [{seed}]: {answer}\n\n**Tutor** ({secs}s, score {row.get('score')}, "
                          f"band {row.get('band')}):\n\n{text or err}\n")
        # the next answer is generated from the next task if the reply set one;
        # a reply that only grades keeps the current task (its quoted numbers
        # are not a problem statement — run 1, 2026-10-06, proved it)
        new_task = task_half(text, practice)
        if new_task:
            cur_task = new_task
        # 📖 Problemes offers the key vocabulary after every grade; the real
        # learner answers it and the practice moves on. Declining keeps the
        # exchange honest (the bench is not a learner that ignores questions).
        if re.search(r"cua de repàs|escriv[^\n]{0,15}\"?(?:yes|no|sí)\"?", text, re.I):
            out2, secs2, err2 = turn(cli.say, sid, "no")
            text2 = E2E.tutor_text(out2)
            rows.append({"practice": practice, "step": "pass", "answer": "no", "secs": secs2,
                         "text": text2 or err2, "sid": sid,
                         **judge(practice, "pass", text2, err2, {}, None, spec["skill"], None)})
            transcript.append(f"**Learner** [pass · claus]: no\n\n**Tutor** ({secs2}s):\n\n{text2 or err2}\n")
            nt = task_half(text2, practice)
            if nt:
                cur_task = nt
    fires = guard_fires(prof, sid)
    for r in rows:
        r["guard_fires"] = len(fires)
    if fires:
        transcript.append("**Guards de tasca forçats pel servidor:**\n" + "\n".join(f"- {f}" for f in fires))
    return rows


def join_metrics(prof: Path, rows: list[dict]) -> None:
    """The server's own per-turn numbers (<profile>/.metrics/turns.jsonl) onto
    the bench rows: tokens and the model's own seconds vs the wall time."""
    f = prof / ".metrics" / "turns.jsonl"
    try:
        lines = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return
    by: dict[str, list] = {}
    for m in lines:
        by.setdefault(m.get("session_id"), []).append(m)
    seen: dict[str, int] = {}
    for r in rows:
        sid = r.get("sid")
        i = seen.get(sid, 0)
        seen[sid] = i + 1
        ms = by.get(sid) or []
        if i < len(ms):
            m = ms[i]
            r["prompt_tokens"] = m.get("prompt_tokens")
            r["completion_tokens"] = m.get("completion_tokens")
            r["model_s"] = round((m.get("model_ms") or 0) / 1000, 1)


GATES = ("ok", "saved", "graded", "shown", "consistent", "contract", "taxonomy",
         "band_ok", "skill_ok", "task_ok", "clean", "continues", "grade_clean")


def rate(rows: list[dict], key: str) -> tuple[int, int]:
    have = [r[key] for r in rows if key in r]
    return sum(1 for v in have if v), len(have)


def pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    v = sorted(vals)
    return round(v[min(len(v) - 1, int(round(q * (len(v) - 1))))], 1)


def summary(rows: list[dict]) -> dict:
    s = {k: rate(rows, k) for k in GATES}
    secs = [r["secs"] for r in rows]
    s["secs_median"] = round(statistics.median(secs), 1) if secs else None
    s["timing"] = {"button": [r["secs"] for r in rows if r["step"] == "start"],
                   "answer": [r["secs"] for r in rows if r["step"] != "start"]}
    s["per_practice"] = {p: {k: rate([r for r in rows if r["practice"] == p], k) for k in GATES}
                         for p in PRACTICES}
    bands: dict[str, dict] = {}
    for r in rows:
        b = r.get("band")
        if not b:
            continue
        d = bands.setdefault(r["seed"], {"ok": 0, "soft": 0, "fail": 0, "scores": []})
        d[b] += 1
        if r.get("score") is not None:
            d["scores"].append(r["score"])
    for d in bands.values():
        d["median"] = statistics.median(d["scores"]) if d["scores"] else None
        del d["scores"]
    s["bands"] = bands
    s["coverage"] = dict(Counter(r["deep_task"] for r in rows if r.get("deep_task")))
    s["guards"] = {"fires": sum(r.get("guard_fires", 0) for r in rows if r["step"] == "start"),
                   "sessions": len({r["sid"] for r in rows if r["step"] == "start"}),
                   "first_try": sum(1 for r in rows if r["step"] == "start" and not r.get("guard_fires"))}
    s["long_corr"] = sum(1 for r in rows if r.get("long_corr"))
    s["sufficient"] = all(n == 0 or ok / n >= 0.9 for ok, n in (s[k] for k in GATES))
    s["failures"] = [{"practice": r["practice"], "step": r["step"], "seed": r.get("seed"),
                      "failed": [k for k in GATES if k in r and not r[k]],
                      "tail": (r.get("text") or "")[-200:]}
                     for r in rows if any(k in r and not r[k] for k in GATES)]
    return s


def fmt(k: tuple[int, int]) -> str:
    return f"{k[0]}/{k[1]}" if k[1] else "—"


def print_scorecard(name: str, s: dict) -> None:
    print(f"\n{name}: {'SUFICIENT' if s['sufficient'] else 'NO SUFICIENT'}")
    for k in GATES:
        print(f"  {k:12s} {fmt(s[k])}")
    print("  bandes de la rúbrica per classe sembrada:")
    for seed, d in sorted((s.get("bands") or {}).items()):
        med = d.get("median")
        print(f"    {seed:10s} ok {d['ok']} · fluixa {d['soft']} · falla {d['fail']}"
              f"   mediana {med}")
    cov = s.get("coverage") or {}
    print("  tasques obertes enviades: " + (" · ".join(f"{k} {v}" for k, v in sorted(cov.items())) or "—"))
    g = s.get("guards") or {}
    print(f"  guards de tasca: {g.get('fires', 0)} reescritures · "
          f"{g.get('first_try', 0)}/{g.get('sessions', 0)} sessions a la primera")
    if s.get("long_corr"):
        print(f"  ⚠ {s['long_corr']} correccions al sostre de 400 caràcters de CORRECTION_RE")
    t = s.get("timing") or {}
    for k in ("button", "answer"):
        v = t.get(k) or []
        if v:
            print(f"  temps {k:6s} mediana {pct(v, 0.5)}s · p90 {pct(v, 0.9)}s · màx {max(v)}s")


def cmd_run(a) -> int:
    prof = Path(a.dir).expanduser() if a.dir else profiles_root() / a.profile
    if not re.match(r"^(test|demo|e2e)", prof.name):
        print(f"error: {prof.name} is not a test profile (test*/demo*/e2e*) — the bench answers exercises", file=sys.stderr)
        return 2
    try:
        learner = json.loads((prof / "learner-profile.json").read_text(encoding="utf-8")).get("learner", {})
    except (OSError, ValueError):
        learner = {}
    unset = [k for k in ("name", "native_language", "current_level")
             if not learner.get(k) or str(learner.get(k)).strip().startswith("{")]
    if unset:
        print(f"error: {prof.name} is not set up ({', '.join(unset)} still empty or a placeholder).\n"
              f"  python3 scripts/flowed-profile.py {prof.name} --name Test --native Catalan --level M4", file=sys.stderr)
        return 2
    pw = prof / ".web-password"
    password = a.password or "".join((pw if pw.exists() else profiles_root() / ".web-password-default").read_text().split())
    cli = E2E.Client(a.port, password, a.timeout, a.user)
    try:
        health = cli._call("/api/global/health")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(f"error: the server on port {a.port} refuses {prof.name}'s password — it is running another\n"
                  f"  profile (a web left from an earlier run?). Restart it with this one:\n"
                  f"  scripts/flowed-web.sh --stop --port {a.port}\n"
                  f"  scripts/flowed-web.sh --app --port {a.port} {prof.name}", file=sys.stderr)
        else:
            print(f"error: the server on port {a.port} answers {e.code}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"error: no server on port {a.port}: {e}\n  scripts/flowed-web.sh --app --port {a.port} {prof.name}", file=sys.stderr)
        return 2
    # The server must run the code on disk (same check as the e2e): skills are
    # re-read every turn, TypeScript is not — a stale build measures the wrong
    # product.
    running = (health or {}).get("build")
    on_disk = E2E.disk_build_stamp()
    if running and on_disk and running != on_disk:
        print(f"\n❌ el servidor del port {a.port} corre un build diferent del que hi ha al disc\n"
              f"   servidor: {running}   disc: {on_disk}\n"
              f"   scripts/flowed-web.sh --stop --port {a.port} && scripts/flowed-web.sh --app --port {a.port} {prof.name}",
              file=sys.stderr)
        return 2
    rows, transcript = [], []
    for i in range(a.repeat):
        for practice, spec in PRACTICES.items():
            if a.only and practice.split("-")[-1] not in a.only:
                continue
            print(f"  [{i + 1}/{a.repeat}] {practice} …", flush=True)
            rows += run_once(cli, prof, practice, spec, transcript)
    join_metrics(prof, rows)
    s = summary(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    base = OUT / f"{a.name}-{stamp}"
    base.with_suffix(".json").write_text(json.dumps(
        {"name": a.name, "when": stamp, "host": a.host or os.uname().nodename, "port": a.port,
         "profile": prof.name, "repeat": a.repeat, "server": health.get("version"),
         "model_url": os.environ.get("FLOWED_DEEP_BASE_URL", ""),
         "summary": s, "rows": rows}, indent=1, ensure_ascii=False))
    base.with_suffix(".md").write_text(f"# {a.name} — mathbench — {stamp}\n\n" + "\n---\n\n".join(transcript),
                                       encoding="utf-8")
    print_scorecard(a.name, s)
    print(f"  → {base.with_suffix('.json')}\n  → {base.with_suffix('.md')} (transcripció)")
    return 0 if s["sufficient"] else 1


def cmd_rescore(a) -> int:
    """Re-judge a saved run with the current gates (the live exchange is kept
    in the .json rows, so a gate fix never needs a new model run)."""
    for f in a.files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        rows = d["rows"]
        for r in rows:
            tool = {"score": r["tool_score"]} if r.get("tool_score") is not None else {}
            new = judge(r["practice"], r["step"], r.get("text") or "", "", tool,
                        r.get("seed"), PRACTICES[r["practice"]]["skill"], r.get("skill"))
            r.update(new)
        d["summary"], d["rescored"] = summary(rows), True
        Path(f).write_text(json.dumps(d, indent=1, ensure_ascii=False))
        print_scorecard(d["name"] + " (rescore)", d["summary"])
    return 0


def cmd_compare(a) -> int:
    latest: dict[str, dict] = {}
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text())
        latest[d["name"]] = d
    if not latest:
        print("(cap resultat encara)")
        return 0
    keys = GATES
    print(f"{'model':18s} {'suf.':5s} " + " ".join(f"{k:>11s}" for k in keys))
    for n, d in latest.items():
        s = d["summary"]
        print(f"{n:18s} {'sí' if s['sufficient'] else 'no':5s} " + " ".join(f"{fmt(s[k]):>11s}" for k in keys))
    print(f"\n{'model':18s} " + " ".join(f"{b:>16s}" for b in ("bare", "calc-slip", "wrong-op", "thin", "correct")))
    for n, d in latest.items():
        bands = d["summary"].get("bands") or {}
        cells = []
        for b in ("bare", "calc-slip", "wrong-op", "thin", "correct"):
            x = bands.get(b)
            cells.append(f"{x['ok']}/{x['ok'] + x['soft'] + x['fail']} med {x['median']}" if x else "—")
        print(f"{n:18s} " + " ".join(f"{c:>16s}" for c in cells))
    print(f"\n{'model':18s} {'tasques enviades':38s} {'guards':>10s} {'med s':>7s}")
    for n, d in latest.items():
        s = d["summary"]
        cov = " ".join(f"{k[:6]}:{v}" for k, v in sorted((s.get("coverage") or {}).items()))
        g = s.get("guards") or {}
        print(f"{n:18s} {cov:38s} {g.get('fires', 0):>4d}/{g.get('sessions', 0):<2d} {s.get('secs_median')!s:>7}")
    print("  (el temps només compara models a la mateixa màquina/GPU)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("profile", nargs="?", default="test-math")
    r.add_argument("--dir")
    r.add_argument("--port", type=int, default=4200)
    r.add_argument("--name", required=True, help="label for the model under test, e.g. qwen3-14b")
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--only", nargs="*", help="writing / reading")
    r.add_argument("--timeout", type=int, default=300)
    r.add_argument("--user", default="opencode")
    r.add_argument("--password")
    r.add_argument("--host", help="label for the machine/GPU, e.g. llvm-4060ti (default: hostname)")
    sub.add_parser("compare")
    rs = sub.add_parser("rescore")
    rs.add_argument("files", nargs="+", help="results/mathbench/<name>-<time>.json")
    a = ap.parse_args()
    return {"run": cmd_run, "compare": cmd_compare, "rescore": cmd_rescore}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
