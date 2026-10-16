#!/usr/bin/env python3
"""Parametric math bank generator — WP1.5 (DISSENY-MATEMATIQUES §4.6, decisió D4).

The language bank was generated with an LLM and filtered with an LLM judge. The
math bank needs neither: every item comes from a PARAMETRIC TEMPLATE, and the
answer is computed by the SAME evaluator that will grade it —
`hooks/mathgrade.py` (`parse_expr` -> exact `Fraction`). Deterministic for a
given seed: same seed -> byte-identical JSON.

Item schema (identical to what WP1.3 `hooks/bank.py` serves):

  { "id": "<competence>.NNN", "competence": "...", "type": "compute"|"choose"|"compare",
    "instruction": "...", "problem": "1/4 + 3/8", "answer": "5/8", "also_accept": [],
    "options": [], "why": "...", "status": "validated", "source": "mathbank · <date> · seed N" }

WP3.2 word problems add one optional field: `"expression": "24 ÷ 6"`. Their
`problem` is a STORY (prose), so the two-path validation parses `expression`
instead, and every number >= 2 in it must appear in the story or the why.
Grading is the plain compute/choose path — no new grader anywhere.

`status: "validated"` means generator-verified; a human review flips it to
"reviewed" later. bank.py serves validated/reviewed, so generated items are
live — intended for the pilot.

Template families are selected per competence by a `Bank: <family>` line in the
curriculum .md (a key `hooks/curriculum.py` ignores; this script reads it).
Fallback for the pilot ids: DEFAULT_FAMILY_BY_ID.

WP2.1 adds the `steps` families (DISSENY-MATEMATIQUES §4.2): worked-solution
templates that emit a FULL expected trace — every step carries `expect` (the
form the method demands), `value` (its exact value), `accept` (alternative
lines), `error_class` (the §4.4 taxonomy, validated against
`db_schema.ERROR_CATEGORIES`) and `why`. They are written to SEPARATE files
`<competence>__steps.json` in a `steps/` SUBDIRECTORY of the bank dir
(default: `curriculum/bank/<stem>/steps/`). WP2.1 shipped them as
`status: "generated"` because the steps grader did not exist yet; WP2.2/2.3
wired `load_bank` to the subdir and the per-line grader, so they are now
generated `status: "validated"` like compute items — the status filter stays
the gate (a human can demote an item to "generated" to pull it from service).
Two guards still keep the SUBDIRECTORY out of the language-side paths:
  * the subdirectory is invisible to the one-level `bank/*/*.json` glob of
    tests/test_bank_review.py TheWholeBank — which grades every item it
    finds with `bank.grade`, and would crash on a steps item (no `sentence`);
    (a sibling dir like `bank/math-m4-steps/` would still match that glob;
    a nested `steps/` under the stem does not.)
  * the level test (`_bank_checkpoint_items`) skips items without `sentence`,
    so a whole worked solution never becomes a one-answer test question.
Generate them with an explicit `--family <steps family>` (a competence's
`Bank:` line names its compute family; steps families are chosen per run,
not per competence).

Steps validation before writing (fail loudly, on top of the rules above):
  * every step's `expect` and `value` parse via mathgrade.parse_expr and
    agree in value; every `accept` entry is an alternative line for that
    value (bare expression or "lhs = rhs", all sides equal);
  * the LAST step's value equals the item answer; the answer equals the
    problem's value (the template's own Fraction computation, re-derived by
    the evaluator — the same two-path rule);
  * `error_class` is one of the 12 canonical classes; step `n` is sequential.

Validation before writing (fail loudly, never emit a bad item):
  * the problem string parses with mathgrade.parse_expr and its value equals
    the template's own Fraction computation (two independent paths);
  * the answer string parses and equals that value;
  * compare items: both sides of the problem parse, the answer is the true
    relation and is one of the options [">", "<", "="] (distractors wrong by
    construction);
  * no duplicate problem within a competence (normalized notation);
  * ids sequential per competence, never reused (generation appends to an
    existing file and continues the numbering).

CLI:
  python3 scripts/mathbank.py gen --curriculum curriculum/math-m4.md \
      --competence m4.mult_2digit --n 30 [--seed N] [--out DIR] [--date YYYY-MM-DD]
  python3 scripts/mathbank.py gen --curriculum curriculum/math-m4.md \
      --competence m4.mult_2digit --family partial_products --n 12 [--seed N] [--out DIR]
  python3 scripts/mathbank.py validate --curriculum curriculum/math-m4.md [--competence ID] [--out DIR]

With an explicit --family the competence does not need a `Bank:` line (and for
the not-yet-in-the-curriculum steps pilots, m4.add_carry / m4.div_2x1, it does
not need to exist in the .md either — the curriculum entry is proposed in the
WP2.1 report). Without --out, steps families write to
curriculum/bank/<stem>/steps/ (compute families: curriculum/bank/<stem>/).

STDLIB ONLY (same rule as hooks/).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from datetime import date as _date
from fractions import Fraction
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hooks"))

import db_schema  # noqa: E402  (hooks/db_schema.py — ERROR_CATEGORIES, the §4.4 SSOT)
import mathgrade  # noqa: E402  (hooks/mathgrade.py — the grader itself)

__all__ = ["FAMILIES", "STEPS_FAMILIES", "build_item", "validate_item",
           "validate_file", "GenError"]


class GenError(Exception):
    """A template produced something we refuse to write. Never emit a bad item."""


# --------------------------------------------------------------- notation ---

_OPS = str.maketrans({"×": "*", "·": "*", "÷": "/", "−": "-", "–": "-"})


def norm_problem(s: str) -> str:
    """Notation-insensitive key for duplicate detection: '27 × 14' == '27*14'."""
    t = str(s).translate(_OPS).replace(",", ".")
    return re.sub(r"\s+", "", t)


def _fmt_frac(f: Fraction) -> str:
    """Canonical answer string: integer, reduced fraction, or mixed number."""
    if f.denominator == 1:
        return str(f.numerator)
    if abs(f) >= 1:
        whole, frac = divmod(f, 1)
        return f"{whole} {frac.numerator}/{frac.denominator}"
    return f"{f.numerator}/{f.denominator}"


def _fmt_dec(f: Fraction) -> str:
    """One-decimal Catalan rendering: Fraction(313,10) -> '31,3'."""
    tenths = f * 10
    if tenths.denominator != 1:
        raise GenError(f"not a one-decimal value: {f}")
    n = int(tenths)
    sign = "-" if n < 0 else ""
    n = abs(n)
    return f"{sign}{n // 10},{n % 10}"


def _lcm(a: int, b: int) -> int:
    return a * b // math.gcd(a, b)


# ------------------------------------------------------- template families ---
# Each family: fn(rng) -> dict with keys:
#   type, instruction, problem, answer, also_accept, options, value (Fraction), why
# The value is computed with plain Fraction arithmetic; validation then
# re-derives it from the PROBLEM STRING via mathgrade.parse_expr — if the two
# disagree, the template is broken and we die.

def mult_2digit(rng: random.Random) -> dict:
    """2x1 and 2x2 multiplications, with and without carrying."""
    kind = rng.choice(["2x1", "2x2"])
    want_carry = rng.random() < 0.5
    for _ in range(500):
        a = rng.randint(12, 99)
        b = rng.randint(2, 9) if kind == "2x1" else rng.randint(11, 99)
        if _has_carry(a, b) == want_carry:
            break
    else:
        raise GenError(f"mult_2digit: no {kind} pair with carry={want_carry} in 500 draws")
    value = Fraction(a * b)
    if want_carry:
        why = ("Multiplica per les unitats i per les desenes i suma els productes "
               "parcials alineats; no oblidis el transport.")
    else:
        why = ("Cap producte parcial passa de 9: multiplica per les unitats i per "
               "les desenes i suma sense transport.")
    return {
        "type": "compute",
        "instruction": "Calcula el resultat.",
        "problem": f"{a} × {b}",
        "answer": str(a * b),
        "also_accept": [],
        "options": [],
        "value": value,
        "why": why,
    }


def _has_carry(a: int, b: int) -> bool:
    """Does the standard algorithm for a × b need a carry anywhere?"""
    for db in (int(c) for c in str(b)):
        acc = 0
        for da in (int(c) for c in str(a)):
            prod = da * db + acc
            if prod >= 10:
                return True
            acc = prod // 10
    return False


def dec_add(rng: random.Random) -> dict:
    """Sum of two one-decimal numbers, total < 100."""
    for _ in range(500):
        ka = rng.randint(10, 999)   # tenths: 1,0 .. 99,9
        kb = rng.randint(10, 999)
        if ka + kb < 1000 and (ka + kb) % 10 != 0:
            break
    else:
        raise GenError("dec_add: no pair with sum < 100 in 500 draws")
    a, b = Fraction(ka, 10), Fraction(kb, 10)
    s = a + b
    return {
        "type": "compute",
        "instruction": "Calcula la suma.",
        "problem": f"{_fmt_dec(a)} + {_fmt_dec(b)}",
        "answer": _fmt_dec(s),
        "also_accept": [],
        "options": [],
        "value": s,
        "why": (f"Suma com amb enters ({ka} + {kb} = {ka + kb}) i torna a posar "
                "l'comma decimal a la mateixa posició."),
    }


def mixed_gloss(answer: str) -> str:
    """For a mixed-number answer ("1 2/15"): say what the notation means
    ("17/15 = 1 + 2/15"); the written form has no "+", and learners read it as
    1 · 2/15 or 12/15 (2026-10-08, Albert). Empty for anything else."""
    m = re.fullmatch(r"(\d+) (\d+)/(\d+)", str(answer).strip())
    if not m:
        return ""
    w, r, d = (int(x) for x in m.groups())
    return (f" Com a nombre mixt: {w * d + r}/{d} = {w} + {r}/{d}, que s'escriu {w} {r}/{d} "
            f"(sense el «+»).")


def frac_add_unlike(rng: random.Random) -> dict:
    """Sum of two proper fractions, denominators <= 12, unlike; the sum over the
    common denominator is reducible about half the time (both cases by design)."""
    want_reducible = rng.random() < 0.5
    for _ in range(2000):
        d1 = rng.randint(2, 12)
        d2 = rng.randint(2, 12)
        if d1 == d2:
            continue
        if d1 > d2:
            d1, d2 = d2, d1
        n1 = rng.randint(1, d1 - 1)
        n2 = rng.randint(1, d2 - 1)
        L = _lcm(d1, d2)
        num = n1 * (L // d1) + n2 * (L // d2)
        if (math.gcd(num, L) > 1) != want_reducible:
            continue
        break
    else:
        raise GenError(f"frac_add_unlike: no pair with reducible={want_reducible} in 2000 draws")
    s = Fraction(n1, d1) + Fraction(n2, d2)
    a1, a2 = n1 * (L // d1), n2 * (L // d2)
    why = (f"Denominador comú {L}: {n1}/{d1} = {a1}/{L} i {n2}/{d2} = {a2}/{L}; "
           f"suma els numeradors ({a1} + {a2} = {num}).")
    if math.gcd(num, L) > 1:
        why += f" Simplifica {num}/{L} dividint per {math.gcd(num, L)}."
    why += mixed_gloss(_fmt_frac(s))
    return {
        "type": "compute",
        "instruction": "Calcula i simplifica si es pot.",
        "problem": f"{n1}/{d1} + {n2}/{d2}",
        "answer": _fmt_frac(s),
        "also_accept": [],
        "options": [],
        "value": s,
        "why": why,
    }


def compare_fracs(rng: random.Random) -> dict:
    """Which of two fractions is bigger: >, < or = (options by construction)."""
    want = rng.choice([">", "<", "="])
    for _ in range(4000):
        b = rng.randint(2, 12)
        d = rng.randint(2, 12)
        n1 = rng.randint(1, b - 1)
        n2 = rng.randint(1, d - 1)
        if want == "=" and (n1, b) == (n2, d):
            continue  # an equal pair must be two different writings, not a copy
        f1, f2 = Fraction(n1, b), Fraction(n2, d)
        op = "=" if f1 == f2 else (">" if f1 > f2 else "<")
        if op == want:
            break
    else:
        raise GenError(f"compare_fracs: no pair with op={want} in 4000 draws")
    L = _lcm(b, d)
    x, y = n1 * (L // b), n2 * (L // d)
    if op == "=":
        why = f"Són equivalents: amb denominador comú {L}, les dues fan {x}/{L}."
    else:
        why = (f"Denominador comú {L}: {n1}/{b} = {x}/{L} i {n2}/{d} = {y}/{L}; "
               f"{x} {op} {y}.")
    return {
        "type": "compare",
        "instruction": "Compara: escriu >, < o =.",
        "problem": f"{n1}/{b} ? {n2}/{d}",
        "answer": op,
        "also_accept": [],
        "options": [">", "<", "="],
        "value": None,  # the "answer" is a relation, not a value
        "why": why,
    }


# ------------------------------------------------- word problems (WP3.2) ---
# §4.1/§5-3.2: the closed variant of the 📖 Problemes practice. A word-problem
# item is a COMPUTE item wearing a story: `problem` holds the statement (prose,
# in the learner's language) and the arithmetic lives in a new optional field,
# `expression` — the two-path validation parses THAT instead of the story and
# checks that every number it uses appears in the story, so the statement and
# the answer can never drift apart. Grading is untouched: hooks/bank.py grades
# it through the existing compute path (the learner writes the result; the
# story is what they had to read to know which operation to run).
#
# ~1 in 7 draws is a `choose` variant of the same story (p=0.15; the 12-item
# pilot with seed 42 lands on exactly 2): the learner writes the
# OPERATION that solves it, not the result — setup without arithmetic. The
# pilot had no choose items at all (the logged WP1.1 hole); these are the
# first, and they grade through bank.py's math-choose path (exact text, then
# value equivalence; a different option is wrong even one digit off).

_WP_PEOPLE = [("La", "Marta"), ("En", "Pere"), ("La", "Laia"), ("El", "Bruno"),
              ("La", "Núria"), ("En", "Marc")]
# (plural noun, gender) — the quantifier agrees, and a template that gets it
# wrong reads as a typo to a nine-year-old.
_WP_OBJECTS = [("galetes", "f"), ("caramels", "m"), ("cromos", "m"), ("postals", "f"),
               ("pomes", "f"), ("llapis", "m"), ("pastissos", "m"), ("taronges", "f")]


def _wp_person(rng: random.Random) -> tuple[str, str]:
    """(sentence-initial, mid-sentence) renderings of the same person: Catalan
    proper-name articles capitalize at the start of the statement and go
    lowercase after "i" — "La Marta reparteix…" but "…i la Marta ja n'ha…"."""
    art, name = rng.choice(_WP_PEOPLE)
    return f"{art} {name}", f"{art.lower()} {name}"


def _wp_quant(gender: str) -> str:
    return "quantes" if gender == "f" else "quants"


def _wp_story(rng: random.Random) -> dict:
    """One story: {story, expr, value, why, two (bool)}. The arithmetic is
    computed with plain Fraction here and re-derived from `expr` by the
    evaluator in build_item — the same two-path rule as every family."""
    kind = rng.choice(["share", "shop", "boxes", "missing", "double", "pizza"])
    art_name, art_name_mid = _wp_person(rng)
    obj, gender = rng.choice(_WP_OBJECTS)
    quant = _wp_quant(gender)
    if kind == "share":
        p = rng.randint(3, 9)
        q = rng.randint(3, 9)
        n = p * q
        story = f"{art_name} reparteix {n} {obj} igualment entre {p} amics. Quants en toquen a cada amic?"
        return {"story": story, "expr": f"{n} ÷ {p}", "value": Fraction(q), "two": True,
                "why": f"«repartir igualment entre» demana divisió: {n} ÷ {p} = {q}."}
    if kind == "shop":
        n = rng.randint(2, 6)
        p = rng.randint(2, 9)
        cost = n * p
        bills = [b for b in (10, 20, 50, 100) if b > cost and b - cost <= 30]
        if not bills:
            raise GenError(f"word_problems/shop: no bill above {cost}")
        b = rng.choice(bills)
        story = (f"{art_name} compra {n} {obj} a {p} € cada un i paga amb un bitllet "
                 f"de {b} €. Quants euros li tornen?")
        return {"story": story, "expr": f"{b} - {n} × {p}", "value": Fraction(b - cost), "two": False,
                "why": (f"Primer el cost total: {n} × {p} = {cost} €. Després el canvi: "
                        f"{b} − {cost} = {b - cost} €.")}
    if kind == "boxes":
        n = rng.randint(3, 9)
        p = rng.randint(3, 12)
        story = f"{art_name} té {n} caixes amb {p} {obj} a cada caixa. {quant.capitalize()} {obj} té en total?"
        return {"story": story, "expr": f"{n} × {p}", "value": Fraction(n * p), "two": True,
                "why": f"{n} grups de {p}: {n} × {p} = {n * p}."}
    if kind == "missing":
        n = rng.randint(20, 80)
        p = rng.randint(1, n - 1)
        story = f"Un àlbum té {n} espais i {art_name_mid} ja n'ha omplert {p}. Quants espais li falten?"
        return {"story": story, "expr": f"{n} - {p}", "value": Fraction(n - p), "two": True,
                "why": f"«quants en falten» és la diferència: {n} − {p} = {n - p}."}
    if kind == "double":
        n = rng.randint(4, 24)
        story = f"{art_name} té {n} {obj} i el seu germà en té el doble. {quant.capitalize()} {obj} tenen entre els dos?"
        return {"story": story, "expr": f"{n} + {n} × 2", "value": Fraction(3 * n), "two": False,
                "why": (f"«el doble» és 2 vegades {n}: {2 * n}; entre els dos, "
                        f"{n} + {2 * n} = {3 * n}.")}
    # pizza: the fraction remainder — the one numeric-or-fraction answer shape
    # the m4 curriculum reaches for (answer reduced by _fmt_frac).
    d = rng.randint(4, 12)
    n = rng.randint(1, d - 1)
    story = f"Una pizza està tallada en {d} parts iguals i {art_name_mid} se'n menja {n}. Quina part de la pizza queda?"
    return {"story": story, "expr": f"1 - {n}/{d}", "value": Fraction(d - n, d), "two": False,
            "why": f"De {d} parts, en queden {d - n}: {d - n}/{d} de la pizza."}


def _wp_choose(rng: random.Random, story: str, n: int, p: int, correct: str,
               value: Fraction, why: str) -> dict:
    """The setup-only variant: same story, but the deliverable is the
    OPERATION. Distractors are the other three operations on the same two
    numbers — wrong by construction, and the caller's draw loop has already
    ensured all four values differ (a distractor equal to the answer would be
    rejected by validate_item anyway)."""
    ops = {"+": f"{n} + {p}", "-": f"{n} - {p}", "×": f"{n} × {p}", "÷": f"{n} ÷ {p}"}
    opts = [correct] + [o for k, o in ops.items() if o != correct]
    rng.shuffle(opts)
    return {
        "type": "choose",
        "instruction": "Quina operació resol el problema? Escriu-la.",
        "problem": story,
        "expression": correct,
        "answer": correct,
        "also_accept": [],
        "options": opts,
        "value": value,
        "why": why,
    }


def word_problems(rng: random.Random) -> dict:
    """Story-based word problem: one numeric or fraction answer (compute), or
    — about one draw in five — the operation that solves it (choose)."""
    want_choose = rng.random() < 0.15
    for _ in range(500):
        s = _wp_story(rng)
        if want_choose and not s["two"]:
            continue
        if want_choose:
            # the four operations on (n, p) must give four different values,
            # or a distractor would be secretly correct.
            m = re.match(r"^(\d+) (?:÷|×|\+|-) (\d+)$", s["expr"])
            if not m:
                continue
            n, p = int(m.group(1)), int(m.group(2))
            vals = {n + p, n - p, n * p, Fraction(n, p)}
            if len(vals) != 4:
                continue
            return _wp_choose(rng, s["story"], n, p, s["expr"], s["value"],
                              s["why"] + " Les altres operacions no hi encaixen.")
        return {
            "type": "compute",
            "instruction": "Llegeix el problema i escriu el resultat.",
            "problem": s["story"],
            "expression": s["expr"],
            "answer": _fmt_frac(s["value"]),
            "also_accept": [],
            "options": [],
            "value": s["value"],
            "why": s["why"],
        }
    raise GenError(f"word_problems: no usable story in 500 draws (choose={want_choose})")


# ------------------------------------------- m7 algebra (WP1.1) ---
# docs/competencies1eso.md + docs/AlgebraNumericaBasica.md ("El Joc de les
# Propietats"): the learner transforms EXPRESSIONS, so the answer of these
# compute families is an expression, not a value. `value` is None (there is
# no numeric value to two-path against) and validation instead checks
# POLYNOMIAL EQUIVALENCE problem ≡ answer with mathgrade.parse_poly — the
# same normalizer that will grade the learner (5x+5 == 5+5x == 5(x+1)).
# Notation kept to what the drafts use: 3x, 4 · x, x^2 / x², x(x+5).

_ALG_LETTERS = re.compile(r"[a-zA-Z]")


def _alg_answer(poly: dict) -> tuple[str, list[str]]:
    """Canonical rendering of the answer, plus one reordered also_accept
    variant (equivalence accepts both anyway — the variant exercises the
    also_accept path end to end)."""
    main = mathgrade.poly_form(poly)
    parts = re.split(r" ([-+]) ", main)          # ["5x", "+", "5"] / ["-2x", "-", "8"]
    terms = [parts[0]] + [f"{op}{t}" for op, t in zip(parts[1::2], parts[2::2])]
    alts: list[str] = []
    if len(terms) >= 2:
        rev = terms[::-1]
        rebuilt = rev[0].lstrip("+")
        for t in rev[1:]:
            rebuilt = f"{rebuilt} - {t[1:]}" if t.startswith("-") else f"{rebuilt} + {t.lstrip('+')}"
        if rebuilt != main:
            alts.append(rebuilt)
    return main, alts


def syntax_grouping_letters(rng: random.Random) -> dict:
    """BLOC 2.4 — commutative/associative with letters: group the like terms.
    '3x + 5 + 2x' -> '5x + 5'; '4y + 7z + 2y + z' -> '6y + 8z'."""
    kind = rng.choice(["letters+number", "two-letters", "mixed-sign"])
    v = rng.choice(["x", "y", "z"])
    if kind == "letters+number":
        k1 = rng.randint(2, 6)
        k2 = rng.randint(2, 6)
        n = rng.randint(3, 12)
        problem = f"{k1}{v} + {n} + {k2}{v}"
        poly = {((v, 1),): Fraction(k1 + k2), (): Fraction(n)}
        why = (f"Agrupa les {v}: {k1}{v} + {k2}{v} = {k1 + k2}{v}; el número "
               f"{n} va sol a la seva banda.")
    elif kind == "two-letters":
        v1, v2 = rng.sample(["x", "y", "z"], 2)
        a = rng.randint(2, 6)
        b = rng.randint(2, 8)
        c = rng.randint(1, 3)
        d = rng.randint(1, 4)
        problem = f"{a}{v1} + {b}{v2} + {c}{v1} + {d}{v2}"
        poly = {((v1, 1),): Fraction(a + c), ((v2, 1),): Fraction(b + d)}
        why = (f"Les {v1} amb les {v1} ({a}{v1} + {c}{v1} = {a + c}{v1}) i les "
               f"{v2} amb les {v2} ({b}{v2} + {d}{v2} = {b + d}{v2}).")
    else:
        a = rng.randint(4, 9)
        b = rng.randint(2, a - 2)
        c = rng.randint(2, 6)
        d = rng.randint(2, 6)
        problem = f"{a}x + {c}y - {b}x + {d}y"
        poly = {(("x", 1),): Fraction(a - b), (("y", 1),): Fraction(c + d)}
        why = (f"{a}x − {b}x = {a - b}x i {c}y + {d}y = {c + d}y; només es poden "
               "agrupar les lletres iguals.")
    ans, alts = _alg_answer(poly)
    return {
        "type": "compute",
        "instruction": "Simplifica l'expressió agrupant les lletres iguals.",
        "problem": problem,
        "answer": ans,
        "also_accept": alts,
        "options": [],
        "value": None,
        "why": why,
    }


def value_numeric(rng: random.Random) -> dict:
    """A. Valor numèric — substitution: '2a − 3b, amb a = 5 i b = 2'. The
    deliverable IS a number, so this family keeps the numeric two-path: the
    substituted arithmetic lives in `expression` (the story is prose), exactly
    like the WP3.2 word problems."""
    v1, v2 = rng.sample(["a", "b", "x", "y"], 2)
    k1 = rng.randint(2, 5)
    k2 = rng.randint(2, 4)
    a = rng.randint(2, 9)
    b = rng.randint(2, 9)
    minus = rng.random() < 0.5
    if minus and k1 * a <= k2 * b:
        k1, k2 = k2, k1
        a, b = b, a
    op = "-" if minus else "+"
    value = k1 * a + (-(k2 * b) if minus else k2 * b)
    letters = f"{k1}{v1} {op} {k2}{v2}"
    story = (f"Si {v1} = {a} i {v2} = {b}, calcula el valor de {letters}.")
    expr = f"{k1} × {a} {op} {k2} × {b}"
    p1, p2 = k1 * a, k2 * b
    why = (f"Substitueix: {k1} × {a} = {p1} i {k2} × {b} = {p2}; "
           f"{p1} {op} {p2} = {value}. La lletra és una casella on entra el número.")
    return {
        "type": "compute",
        "instruction": "Substitueix els valors i calcula.",
        "problem": story,
        "expression": expr,
        "answer": str(value),
        "also_accept": [],
        "options": [],
        "value": Fraction(value),
        "why": why,
    }


def distributive_letters(rng: random.Random) -> dict:
    """B. Distributiva amb lletres: '3 · (x + 4)' -> '3x + 12', and the
    sign-management case from the complete draft: '-2 · (x + 4)' -> '-2x - 8'.
    The outside number multiplies ABSOLUTELY everything inside."""
    v = rng.choice(["x", "y", "z"])
    k = rng.choice([2, 3, 4, 5, -2, -3])
    c = rng.randint(2, 6)
    inner = "+" if rng.random() < 0.6 else "-"
    prob_inner = f"{v} + {c}" if inner == "+" else f"{v} - {c}"
    problem = f"{k} · ({prob_inner})"
    kc = k * c * (-1 if inner == "-" else 1)
    poly = {((v, 1),): Fraction(k), (): Fraction(kc)}
    ans, alts = _alg_answer(poly)
    if k < 0:
        why = (f"El {k} de fora multiplica els dos termes: {k} × {v} = {k}{v} i "
               f"{k} × ({prob_inner}) = {kc}. Amb un nombre negatiu de fora, els "
               "signes de dins canvien en desplegar.")
    else:
        why = (f"El {k} de fora multiplica absolutament tot: {k} × {v} = {k}{v} i "
               f"{k} × ({c if inner == '+' else '-' + str(c)}) = {kc}.")
    return {
        "type": "compute",
        "instruction": "Desplega el parèntesi (multiplica tot el que hi ha a dins).",
        "problem": problem,
        "answer": ans,
        "also_accept": alts,
        "options": [],
        "value": None,
        "why": why,
    }


def factor_letters(rng: random.Random) -> dict:
    """C. Factor comú amb lletres — the four levels of the draft:
    L1 only-letter (7x + 7y -> 7(x + y)), L2 letter+number (4x + xy ->
    x(4 + y)), L3 hidden number (8x + 12 -> 4(2x + 3)), L4 powers
    (x^2 + 9x -> x(x + 9))."""
    level = rng.choice(["letter", "letter+number", "hidden-number", "power"])
    v = rng.choice(["x", "y", "z"])
    if level == "letter":
        k = rng.randint(2, 9)
        v2 = rng.choice([c for c in "xyz" if c != v])
        problem = f"{k}{v} + {k}{v2}"
        answer = f"{k}({v} + {v2})"
        why = f"El {k} es repeteix a tots dos termes: {k}{v} + {k}{v2} = {k}({v} + {v2})."
    elif level == "letter+number":
        k = rng.randint(2, 9)
        v2 = rng.choice([c for c in "xyz" if c != v])
        problem = f"{k}{v} + {v}{v2}"
        answer = f"{v}({k} + {v2})"
        why = (f"El que es repeteix és la {v}: {k}{v} + {v}{v2} = "
               f"{v}({k} + {v2}).")
    elif level == "hidden-number":
        for _ in range(200):
            g = rng.randint(2, 6)
            p = rng.randint(2, 6)
            q = rng.randint(2, 6)
            if math.gcd(p, q) == 1 and p != q:
                break
        else:
            raise GenError("factor_letters/hidden-number: no coprime pair in 200 draws")
        problem = f"{g * p}{v} + {g * q}"
        answer = f"{g}({p}{v} + {q})"
        why = (f"La taula del {g} és compartida: {g * p}{v} + {g * q} = "
               f"{g} · {p}{v} + {g} · {q} = {g}({p}{v} + {q}).")
    else:
        k = rng.randint(2, 9)
        problem = f"{v}^2 + {k}{v}"
        answer = f"{v}({v} + {k})"
        why = (f"{v}^2 vol dir {v} · {v}: {v} · {v} + {k} · {v} = {v}({v} + {k}). "
               f"La {v} es repeteix a tot arreu.")
    if mathgrade.parse_poly(problem) != mathgrade.parse_poly(answer):
        raise GenError(f"factor_letters template bug: {problem!r} != {answer!r}")
    return {
        "type": "compute",
        "instruction": "Treu el factor comú (transforma l'expressió, no la resolquis).",
        "problem": problem,
        "answer": answer,
        "also_accept": [],
        "options": [],
        "value": None,
        "why": why,
    }


# ------------------------------------------- m5 families (E2, DISSENY-M5 §2.3) ---
# Fourteen families for the 5th level (curriculum/math-m5.md). Same contract as the
# families above: the value is re-derived from `expression` (or `problem`) by
# mathgrade, and every number >= 2 of an `expression` is written in its story or
# its why. A UNIT lives in `answer` ("3500 m", "40 cm²", "95 min"): mathgrade splits
# a trailing unit off (_parse_with_unit) and grading asks for it — a bare "3500" is
# "near" (7): "valor correcte, unitat que falta".

_MEASURE_UNITS = frozenset({"m", "cm", "mm", "km", "kg", "g", "l", "ml", "min", "m²", "cm²",
                            "dm", "dm²", "km²", "m³", "dm³", "cm³",  # m7 (E6) adds the volumes
                            "mm²", "ha"})  # m6 (E8) adds mm² and ha (not "a": a letter unit reads as algebra)


def _is_unit_answer(text) -> bool:
    """A value with a known measure unit ("40 cm²", "95 min"), not an expression with letters."""
    try:
        _, unit = mathgrade._parse_with_unit(text)
    except mathgrade.ParseError:
        return False
    return unit in _MEASURE_UNITS


def _answer_value(text) -> Fraction:
    """The exact value of an answer, with or without its unit."""
    return mathgrade._parse_with_unit(text)[0].value


def _fmt_fixed(f: Fraction, places: int) -> str:
    """Decimal comma with exactly `places` decimals: 4 -> '4,000', 0.25 -> '0,25'."""
    scaled = f * 10 ** places
    if scaled.denominator != 1:
        raise GenError(f"not a {places}-decimal value: {f}")
    n = int(scaled)
    sign = "-" if n < 0 else ""
    ip, fp = divmod(abs(n), 10 ** places)
    return f"{sign}{ip},{fp:0{places}d}" if places else f"{sign}{ip}"


def _fmt_min_dec(f: Fraction) -> str:
    """The shortest exact decimal: 9.4 -> '9,4', 2 -> '2', 2.45 -> '2,45'."""
    for places in range(0, 4):
        if (f * 10 ** places).denominator == 1:
            return _fmt_fixed(f, places)
    raise GenError(f"not a decimal with at most three places: {f}")


def _listing(values) -> str:
    """'4, 8, 6 i 2' — the Catalan listing of a short data set."""
    values = [str(v) for v in values]
    return ", ".join(values[:-1]) + " i " + values[-1]


def mult_3digit(rng: random.Random) -> dict:
    """3 digits x 2 digits and 3 x 3, with and without carrying."""
    kind = rng.choice(["3x2", "3x3"])
    want_carry = rng.random() < 0.5
    for _ in range(500):
        a = rng.randint(100, 999)
        b = rng.randint(11, 99) if kind == "3x2" else rng.randint(100, 999)
        if _has_carry(a, b) == want_carry:
            break
    else:
        raise GenError(f"mult_3digit: no {kind} pair with carry={want_carry} in 500 draws")
    if want_carry:
        why = ("Alguna multiplicació d'una xifra per una altra passa de 9: cal transportar. "
               "Multiplica per cada xifra del segon factor i suma els productes alineats.")
    else:
        why = ("Cap multiplicació d'una xifra per una altra passa de 9: no hi ha transport. "
               "Multiplica per cada xifra del segon factor i suma els productes alineats.")
    return {
        "type": "compute",
        "instruction": "Calcula el resultat.",
        "problem": f"{a} × {b}",
        "answer": str(a * b),
        "also_accept": [],
        "options": [],
        "value": Fraction(a * b),
        "why": why,
    }


def div_2digit(rng: random.Random) -> dict:
    """Exact division by a 2-digit divisor: a 3- or 4-digit dividend, no remainder."""
    d = rng.randint(11, 99)
    q = rng.randint(11, 99)
    a = d * q
    return {
        "type": "compute",
        "instruction": "Calcula el quocient (la divisió és exacta, sense residu).",
        "problem": f"{a} ÷ {d}",
        "answer": str(q),
        "also_accept": [],
        "options": [],
        "value": Fraction(q),
        "why": (f"Busca quantes vegades hi cap {d} dins {a}: {d} × {q} = {a}, "
                f"així que {a} ÷ {d} = {q}. Si la multiplicació dóna el dividend, la divisió és exacta."),
    }


def combined_ops(rng: random.Random) -> dict:
    """Hierarchy and parentheses: 3 or 4 operands, a whole result that is never negative."""
    shape = rng.randrange(5)
    for _ in range(500):
        if shape == 0:  # a + b × c - d
            a, b, c = rng.randint(2, 30), rng.randint(2, 12), rng.randint(2, 12)
            bc = b * c
            d = rng.randint(2, a + bc)
            v = a + bc - d
            if v < 0:
                continue
            problem = f"{a} + {b} × {c} - {d}"
            why = (f"Primer la multiplicació: {b} × {c} = {bc}; després, d'esquerra a dreta: "
                   f"{a} + {bc} = {a + bc} i {a + bc} − {d} = {v}.")
        elif shape == 1:  # (a + b) × c - d
            a, b, c = rng.randint(2, 20), rng.randint(2, 12), rng.randint(2, 9)
            s = (a + b) * c
            d = rng.randint(2, s)
            v = s - d
            problem = f"({a} + {b}) × {c} - {d}"
            why = (f"Primer el parèntesi: {a} + {b} = {a + b}; després la multiplicació: "
                   f"{a + b} × {c} = {s}; i per acabar {s} − {d} = {v}.")
        elif shape == 2:  # a × (b - c) + d
            a, b, c = rng.randint(2, 12), rng.randint(4, 20), rng.randint(2, 9)
            if c >= b:
                continue
            d = rng.randint(2, 40)
            p = a * (b - c)
            v = p + d
            problem = f"{a} × ({b} - {c}) + {d}"
            why = (f"Primer el parèntesi: {b} − {c} = {b - c}; després la multiplicació: "
                   f"{a} × {b - c} = {p}; i després la suma: {p} + {d} = {v}.")
        elif shape == 3:  # a × b - c × d
            a, b, c, d = rng.randint(3, 12), rng.randint(3, 12), rng.randint(2, 9), rng.randint(2, 9)
            p1, p2 = a * b, c * d
            if p1 < p2:
                continue
            v = p1 - p2
            problem = f"{a} × {b} - {c} × {d}"
            why = (f"Primer les dues multiplicacions: {a} × {b} = {p1} i {c} × {d} = {p2}; "
                   f"després la resta: {p1} − {p2} = {v}.")
        else:  # a + b × c - d ÷ e  (d = e × k, exact)
            a, b, c = rng.randint(2, 30), rng.randint(2, 12), rng.randint(2, 12)
            e, k = rng.randint(2, 9), rng.randint(2, 9)
            bc = b * c
            d = e * k
            v = a + bc - k
            if v < 0:
                continue
            problem = f"{a} + {b} × {c} - {d} ÷ {e}"
            why = (f"Primer la divisió ({d} ÷ {e} = {k}) i la multiplicació ({b} × {c} = {bc}); "
                   f"després, d'esquerra a dreta: {a} + {bc} − {k} = {v}.")
        return {
            "type": "compute",
            "instruction": "Calcula respectant l'ordre de les operacions.",
            "problem": problem,
            "answer": str(v),
            "also_accept": [],
            "options": [],
            "value": Fraction(v),
            "why": why,
        }
    raise GenError(f"combined_ops: no valid draw for shape {shape} in 500 tries")


def frac_same_den(rng: random.Random) -> dict:
    """Sum or difference of fractions with the SAME denominator. The direct result
    is the answer; its simplified form (a mixed number when it is improper) is
    accepted too."""
    d = rng.randint(3, 12)
    if rng.random() < 0.5:
        a, b = rng.randint(1, d - 1), rng.randint(1, d - 1)
        op, num = "+", a + b
    else:
        b = rng.randint(1, d - 2)
        a = rng.randint(b + 1, d - 1)
        op, num = "-", a - b
    value = Fraction(num, d)
    answer = f"{num}/{d}"
    simple = _fmt_frac(value)
    why = (f"Els denominadors són iguals ({d}): el denominador no canvia; només operes "
           f"amb els numeradors: {a} {op} {b} = {num}, és a dir {num}/{d}.")
    g = math.gcd(num, d)
    if g > 1:
        why += f" Simplifica dividint numerador i denominador per {g}: {simple}."
    why += mixed_gloss(simple)
    return {
        "type": "compute",
        "instruction": "Calcula i simplifica si es pot.",
        "problem": f"{a}/{d} {op} {b}/{d}",
        "answer": answer,
        "also_accept": [simple] if simple != answer else [],
        "options": [],
        "value": value,
        "why": why,
    }


def frac_of_quantity(rng: random.Random) -> dict:
    """A fraction of a quantity, as a short statement: 3/4 de 120 -> 90."""
    for _ in range(500):
        d = rng.choice([2, 3, 4, 5, 6, 8, 10])
        n = rng.randint(1, d - 1)
        if math.gcd(n, d) == 1:
            break
    else:
        raise GenError("frac_of_quantity: no reduced fraction in 500 draws")
    k = rng.randint(2, 30)
    q = d * k
    return {
        "type": "compute",
        "instruction": "Calcula la fracció de la quantitat.",
        "problem": f"Quant és {n}/{d} de {q}?",
        "expression": f"{n}/{d} × {q}",
        "answer": str(n * k),
        "also_accept": [],
        "options": [],
        "value": Fraction(n * k),
        "why": (f"Parteix {q} en {d} parts iguals ({q} ÷ {d} = {k}) i en prens {n}: "
                f"{n} × {k} = {n * k}."),
    }


def dec_ops(rng: random.Random) -> dict:
    """Sums and differences of decimals to the thousandth, and a decimal times a whole number."""
    kind = rng.choice(["add", "sub", "mul"])
    if kind == "mul":
        p = rng.choice([1, 2])
        lim = 10 ** p
        units = rng.randint(lim + 1, 10 * lim - 1)
        if units % lim == 0:
            units += 1
        m = rng.randint(2, 9)
        x = Fraction(units, lim)
        prod = x * m
        return {
            "type": "compute",
            "instruction": "Calcula (multiplica sense mirar la coma i després posa-la).",
            "problem": f"{_fmt_fixed(x, p)} × {m}",
            "answer": _fmt_min_dec(prod),
            "also_accept": [],
            "options": [],
            "value": prod,
            "why": (f"Sense la coma: {units} × {m} = {units * m}; el número té {p} "
                    f"{'xifra' if p == 1 else 'xifres'} decimal{'s' if p == 2 else ''}, "
                    f"així que el resultat és {_fmt_min_dec(prod)}."),
        }
    a = Fraction(rng.randint(1, 9999), 1000)
    b = Fraction(rng.randint(1, 9999), 1000)
    if kind == "sub":
        if a == b:
            raise GenError("dec_ops: equal operands in a subtraction")
        if a < b:
            a, b = b, a
        res = a - b
        op, opname = "-", "resta"
    else:
        res = a + b
        op, opname = "+", "suma"
    ua, ub = int(a * 1000), int(b * 1000)
    return {
        "type": "compute",
        "instruction": "Calcula i alinea les comes.",
        "problem": f"{_fmt_fixed(a, 3)} {op} {_fmt_fixed(b, 3)}",
        "answer": _fmt_min_dec(res),
        "also_accept": [],
        "options": [],
        "value": res,
        "why": (f"Alinea les comes i fes la {opname} com amb enters, en mil·lèsimes: "
                f"{ua} {op} {ub} = {int(res * 1000)}; torna a posar la coma."),
    }


def percent_basic(rng: random.Random) -> dict:
    """10, 25, 50 or 75 % of a quantity; the quantity is a multiple of 20, so every answer is whole."""
    p = rng.choice([10, 25, 50, 75])
    q = 20 * rng.randint(1, 20)
    v = Fraction(q * p, 100)
    return {
        "type": "compute",
        "instruction": "Calcula el percentatge.",
        "problem": f"Quant és el {p} % de {q}?",
        "expression": f"{q} × {p} ÷ 100",
        "answer": str(v),
        "also_accept": [],
        "options": [],
        "value": v,
        "why": f"El {p} % són {p} de cada 100: {q} × {p} ÷ 100 = {v}.",
    }


_SMD = [  # (big unit, small unit, factor between them, big name, small name)
    ("km", "m", 1000, "quilòmetres", "metres"),
    ("m", "cm", 100, "metres", "centímetres"),
    ("cm", "mm", 10, "centímetres", "mil·límetres"),
    ("kg", "g", 1000, "quilograms", "grams"),
    ("l", "ml", 1000, "litres", "mil·lilitres"),
]


def smd_convert(rng: random.Random) -> dict:
    """Length, mass and capacity conversions, answered with the unit: up (3,5 km -> 3500 m)
    or down (245 cm -> 2,45 m)."""
    big, small, f, bname, sname = rng.choice(_SMD)
    if rng.random() < 0.5:  # up: from the big unit to the small one
        x = Fraction(rng.randint(1, 99), 10)
        v = x * f
        return {
            "type": "compute",
            "instruction": "Converteix la unitat i escriu-la.",
            "problem": f"Quants {sname} són {_fmt_fixed(x, 1)} {big}?",
            "expression": f"{_fmt_fixed(x, 1)} × {f}",
            "answer": f"{int(v)} {small}",
            "also_accept": [],
            "options": [],
            "value": v,
            "why": f"1 {big} = {f} {small}: {_fmt_fixed(x, 1)} × {f} = {int(v)} {small}.",
        }
    y = rng.randint(10, 9 * f)  # down: from the small unit to the big one
    v = Fraction(y, f)
    value_txt = _fmt_min_dec(v)
    return {
        "type": "compute",
        "instruction": "Converteix la unitat i escriu-la.",
        "problem": f"Quants {bname} són {y} {small}?",
        "expression": f"{y} ÷ {f}",
        "answer": f"{value_txt} {big}",
        "also_accept": [],
        "options": [],
        "value": v,
        "why": f"1 {big} = {f} {small}: {y} {small} són {y} ÷ {f} = {value_txt} {big}.",
    }


def time_intervals(rng: random.Random) -> dict:
    """Start and end time -> duration in minutes (the same day)."""
    h1 = rng.randint(7, 18)
    m1 = rng.choice(range(0, 60, 5))
    dur = rng.choice(range(10, 241, 5))
    t1 = h1 * 60 + m1
    t2 = t1 + dur
    if t2 >= 23 * 60:
        raise GenError("time_intervals: the trip crosses midnight")
    h2, m2 = divmod(t2, 60)
    return {
        "type": "compute",
        "instruction": "Quants minuts dura?",
        "problem": (f"Un autobús surt a les {h1}:{m1:02d} i arriba a les {h2}:{m2:02d}. "
                    "Quants minuts dura el trajecte?"),
        "expression": f"{t2} - {t1}",
        "answer": f"{dur} min",
        "also_accept": [],
        "options": [],
        "value": Fraction(dur),
        "why": (f"Passa les hores a minuts: {h2}:{m2:02d} són {t2} min i {h1}:{m1:02d} són "
                f"{t1} min; {t2} − {t1} = {dur} min."),
    }


def area_perimeter(rng: random.Random) -> dict:
    """Area (cm²) and perimeter (cm) of rectangles, squares and triangles."""
    kind = rng.choice(["rect_area", "rect_perim", "square_perim", "tri_area", "tri_perim"])
    if kind == "rect_area":
        b, h = rng.randint(2, 12), rng.randint(2, 12)
        return {
            "type": "compute",
            "instruction": "Calcula l'àrea.",
            "problem": f"Un rectangle té {b} cm de base i {h} cm d'alçada. Quina és la seva àrea?",
            "expression": f"{b} × {h}",
            "answer": f"{b * h} cm²",
            "also_accept": [], "options": [], "value": Fraction(b * h),
            "why": f"L'àrea del rectangle és base × alçada: {b} × {h} = {b * h} cm².",
        }
    if kind == "rect_perim":
        b, h = rng.randint(2, 12), rng.randint(2, 12)
        p = 2 * (b + h)
        return {
            "type": "compute",
            "instruction": "Calcula el perímetre.",
            "problem": f"Quin és el perímetre d'un rectangle de {b} cm de base i {h} cm d'alçada?",
            "expression": f"2 × ({b} + {h})",
            "answer": f"{p} cm",
            "also_accept": [], "options": [], "value": Fraction(p),
            "why": f"Té 2 costats de {b} cm i 2 de {h} cm: 2 × ({b} + {h}) = {p} cm.",
        }
    if kind == "square_perim":
        s = rng.randint(2, 15)
        return {
            "type": "compute",
            "instruction": "Calcula el perímetre.",
            "problem": f"Un quadrat té {s} cm de costat. Quin és el seu perímetre?",
            "expression": f"4 × {s}",
            "answer": f"{4 * s} cm",
            "also_accept": [], "options": [], "value": Fraction(4 * s),
            "why": f"Té 4 costats iguals: 4 × {s} = {4 * s} cm.",
        }
    if kind == "tri_area":
        b, h = rng.randint(2, 14), rng.randint(2, 14)
        if (b * h) % 2:
            h += 1
        return {
            "type": "compute",
            "instruction": "Calcula l'àrea.",
            "problem": f"Un triangle té {b} cm de base i {h} cm d'alçada. Quina és la seva àrea?",
            "expression": f"{b} × {h} ÷ 2",
            "answer": f"{b * h // 2} cm²",
            "also_accept": [], "options": [], "value": Fraction(b * h, 2),
            "why": f"L'àrea del triangle és base × alçada ÷ 2: {b} × {h} = {b * h}, i {b * h} ÷ 2 = {b * h // 2} cm².",
        }
    # tri_perim: a valid triangle (each side shorter than the other two together)
    for _ in range(500):
        a, b, c = rng.randint(3, 15), rng.randint(3, 15), rng.randint(3, 15)
        if a < b + c and b < a + c and c < a + b:
            break
    else:
        raise GenError("area_perimeter: no valid triangle in 500 draws")
    p = a + b + c
    return {
        "type": "compute",
        "instruction": "Calcula el perímetre.",
        "problem": f"Un triangle té els costats de {a} cm, {b} cm i {c} cm. Quant mesura el seu perímetre?",
        "expression": f"{a} + {b} + {c}",
        "answer": f"{p} cm",
        "also_accept": [], "options": [], "value": Fraction(p),
        "why": f"El perímetre és la suma dels tres costats: {a} + {b} + {c} = {p} cm.",
    }


def mean_mode_range(rng: random.Random) -> dict:
    """The mean (always a whole number), the mode, or the range of a short data set."""
    kind = rng.choice(["mean", "mode", "range"])
    if kind == "mean":
        n = rng.choice([4, 5])
        for _ in range(500):
            data = [rng.randint(2, 20) for _ in range(n)]
            if sum(data) % n == 0:
                break
        else:
            raise GenError("mean_mode_range: no whole mean in 500 draws")
        total = sum(data)
        m = total // n
        return {
            "type": "compute",
            "instruction": "Calcula la mitjana.",
            "problem": f"Quina és la mitjana de les dades {_listing(data)}?",
            "expression": "(" + " + ".join(str(x) for x in data) + f") ÷ {n}",
            "answer": str(m),
            "also_accept": [], "options": [], "value": Fraction(m),
            "why": f"Hi ha {n} dades: les sumes totes ({total}) i reparteixes el total entre {n}: {total} ÷ {n} = {m}.",
        }
    if kind == "mode":
        n = rng.randint(6, 7)
        mode = rng.randint(1, 9)
        pool = [v for v in range(1, 10) if v != mode]
        others = []
        while len(others) < n - 3:
            v = rng.choice(pool)
            if others.count(v) < 2:  # no other value can tie the mode
                others.append(v)
        data = others + [mode] * 3
        rng.shuffle(data)
        return {
            "type": "compute",
            "instruction": "Quina és la moda? (el valor que més es repeteix)",
            "problem": f"Quina és la moda de les dades {_listing(data)}?",
            "expression": str(mode),
            "answer": str(mode),
            "also_accept": [], "options": [], "value": Fraction(mode),
            "why": f"La moda és el valor que més es repeteix: el {mode} surt 3 vegades, més que cap altre.",
        }
    for _ in range(500):
        n = rng.randint(5, 7)
        data = [rng.randint(2, 40) for _ in range(n)]
        if max(data) != min(data):
            break
    else:
        raise GenError("mean_mode_range: no range in 500 draws")
    mx, mn = max(data), min(data)
    return {
        "type": "compute",
        "instruction": "Calcula el rang (la diferència entre el més gran i el més petit).",
        "problem": f"Quin és el rang de les dades {_listing(data)}?",
        "expression": f"{mx} - {mn}",
        "answer": str(mx - mn),
        "also_accept": [], "options": [], "value": Fraction(mx - mn),
        "why": f"El més gran és {mx} i el més petit {mn}: {mx} − {mn} = {mx - mn}.",
    }


def probability_simple(rng: random.Random) -> dict:
    """Favourable over possible outcomes, written as a fraction. The direct count is the
    answer; its simplified form is accepted too."""
    x, y = rng.randint(1, 9), rng.randint(1, 9)
    t = x + y
    value = Fraction(x, t)
    answer = f"{x}/{t}"
    simple = _fmt_frac(value)
    why = (f"Casos favorables: {x} boles vermelles; casos possibles: {x} + {y} = {t}; "
           f"la probabilitat és {x}/{t}")
    why += f", que simplificada és {simple}." if simple != answer else "."
    return {
        "type": "compute",
        "instruction": "Escriu la probabilitat com a fracció.",
        "problem": (f"Una bossa té {x} boles vermelles i {y} de blaves. Si n'agafes una a l'atzar "
                    "sense mirar, quina és la probabilitat que sigui vermella?"),
        "expression": f"{x}/({x} + {y})",
        "answer": answer,
        "also_accept": [simple] if simple != answer else [],
        "options": [],
        "value": value,
        "why": why,
    }


def equations_simple(rng: random.Random) -> dict:
    """a·x + b = c with a whole solution: take b off both sides, then divide by a."""
    a, x, b = rng.randint(2, 9), rng.randint(2, 12), rng.randint(1, 20)
    c = a * x + b
    return {
        "type": "compute",
        "instruction": "Resol l'equació: quant val x?",
        "problem": f"Quant val x en l'equació {a}x + {b} = {c}?",
        "expression": f"({c} - {b}) ÷ {a}",
        "answer": str(x),
        "also_accept": [], "options": [], "value": Fraction(x),
        "why": (f"Treu {b} als dos costats: {a}x = {c} − {b} = {c - b}; després divideix "
                f"per {a}: x = {c - b} ÷ {a} = {x}."),
    }


# Two-to-three-operation stories. Each builder returns the story, the expression, its
# value, the why and WRONG operations on the same numbers (choose distractors); None
# when the draw does not fit (the caller draws again).
_MS_NOUNS = [("quaderns", "m"), ("gominoles", "f"), ("llibres", "m"), ("cromos", "m")]
_MS_PAIRS = [("quaderns", "bolígrafs"), ("gominoles", "xiclets"), ("llibres", "cromos")]


def _ms_story(rng: random.Random):
    kind = rng.choice(["change", "share", "boxes", "factory", "pair"])
    art, mid = _wp_person(rng)
    if kind == "change":
        n1, p1 = rng.randint(2, 6), rng.randint(2, 9)
        n2, p2 = rng.randint(2, 5), rng.randint(2, 9)
        total = n1 * p1 + n2 * p2
        bills = [b for b in (10, 20, 50, 100) if b > total and b - total <= 60]
        if not bills:
            return None
        bill = rng.choice(bills)
        o1, o2 = rng.choice(_MS_PAIRS)
        return {
            "story": (f"{art} compra {n1} {o1} a {p1} € cada un i {n2} {o2} a {p2} € cada un. "
                      f"Paga amb un bitllet de {bill} €. Quants euros li tornen?"),
            "expr": f"{bill} - ({n1} × {p1} + {n2} × {p2})",
            "value": Fraction(bill - total),
            "why": (f"Primer el cost: {n1} × {p1} = {n1 * p1} € i {n2} × {p2} = {n2 * p2} €, "
                    f"que sumen {total} €; després el canvi: {bill} − {total} = {bill - total} €."),
            "wrong": [f"{bill} - {n1} × {p1} + {n2} × {p2}", f"{n1} × {p1} + {n2} × {p2} - {bill}",
                      f"{bill} - {n1} × {p1}", f"({bill} - {n1}) × {p1}"],
        }
    if kind == "share":
        q, k, p = rng.randint(2, 6), rng.randint(2, 9), rng.randint(1, 9)
        n = q * k + p
        obj, g = rng.choice(_WP_OBJECTS)
        return {
            "story": (f"{art} té {n} {obj}. En dona {p} a un amic i reparteix la resta igualment "
                      f"entre {q} amics. {_wp_quant(g).capitalize()} {obj} rep cada amic?"),
            "expr": f"({n} - {p}) ÷ {q}",
            "value": Fraction(k),
            "why": (f"Primer en treu els {p} que dona: {n} − {p} = {n - p}; després les reparteix "
                    f"entre {q}: {n - p} ÷ {q} = {k}."),
            "wrong": [f"{n} - {p} ÷ {q}", f"{n} ÷ {q} - {p}", f"({n} + {p}) ÷ {q}"],
        }
    if kind == "boxes":
        c, p = rng.randint(3, 9), rng.randint(3, 12)
        r = rng.randint(1, c * p - 1)
        obj, g = rng.choice(_WP_OBJECTS)
        return {
            "story": (f"Hi ha {c} caixes amb {p} {obj} a cada caixa. Se'n treuen {r} per regalar. "
                      f"{_wp_quant(g).capitalize()} {obj} en queden?"),
            "expr": f"{c} × {p} - {r}",
            "value": Fraction(c * p - r),
            "why": f"{c} caixes de {p} són {c * p} {obj}; després en resten {r}: {c * p} − {r} = {c * p - r}.",
            "wrong": [f"{c} × ({p} - {r})", f"{c} + {p} - {r}", f"{c} × {p} + {r}"],
        }
    if kind == "factory":
        p, h, d = rng.randint(10, 40), rng.randint(3, 6), rng.randint(2, 30)
        return {
            "story": (f"Una fàbrica fa {p} peces cada hora. Funciona {h} hores i després en descarta "
                      f"{d} per defectuoses. Quantes peces bones té?"),
            "expr": f"{p} × {h} - {d}",
            "value": Fraction(p * h - d),
            "why": f"En {h} hores fa {p} × {h} = {p * h} peces; en descarta {d}: {p * h} − {d} = {p * h - d}.",
            "wrong": [f"{p} + {h} - {d}", f"{p} × ({h} - {d})", f"{p} × {h} + {d}"],
        }
    # pair: two collections, then some are lost
    n, m, d = rng.randint(4, 20), rng.randint(3, 20), rng.randint(1, 19)
    if d > n + m - 1:
        return None
    noun, g = rng.choice(_MS_NOUNS)
    return {
        "story": (f"{art} té {n} {noun} i el seu germà en té {m}. Entre els dos en perden {d}. "
                  f"{_wp_quant(g).capitalize()} {noun} els queden?"),
        "expr": f"{n} + {m} - {d}",
        "value": Fraction(n + m - d),
        "why": f"Primer els junts: {n} + {m} = {n + m}; després en perden {d}: {n + m} − {d} = {n + m - d}.",
        "wrong": [f"{n} + ({m} - {d})", f"{n} - {m} - {d}", f"{n} × {m} - {d}", f"{n} + {m} + {d}"],
    }


def word_problems_multistep(rng: random.Random) -> dict:
    """Two- and three-operation word problems (compute), or — about one in five — the
    whole operation that solves them (choose). The arithmetic is `expression`; every
    number in it is written in the story."""
    want_choose = rng.random() < 0.2
    for _ in range(500):
        s = _ms_story(rng)
        if s is None:
            continue
        if not want_choose:
            return {
                "type": "compute",
                "instruction": "Llegeix el problema i escriu el resultat.",
                "problem": s["story"],
                "expression": s["expr"],
                "answer": str(s["value"]),
                "also_accept": [],
                "options": [],
                "value": s["value"],
                "why": s["why"],
            }
        picks, seen = [], {s["value"]}
        for w in s["wrong"]:
            try:
                wv = mathgrade.parse_expr(w).value
            except mathgrade.ParseError:
                continue
            if wv not in seen:  # a distractor must be wrong by value, and distinct
                seen.add(wv)
                picks.append(w)
        if len(picks) < 3:
            continue
        options = [s["expr"], *picks[:3]]
        rng.shuffle(options)
        return {
            "type": "choose",
            "instruction": "Quina operació resol el problema? Escriu-la.",
            "problem": s["story"],
            "expression": s["expr"],
            "answer": s["expr"],
            "also_accept": [],
            "options": options,
            "value": s["value"],
            "why": s["why"] + " Les altres operacions no hi encaixen.",
        }
    raise GenError(f"word_problems_multistep: no usable story in 500 draws (choose={want_choose})")


# ------------------------------------- m7 families (E6, DISSENY-M7-M6 §1.1) ---
# Seventeen Go families for 1r d'ESO (curriculum/math-m7.md). Same contract as the
# families above: the value is re-derived from `expression` (or `problem`) by
# mathgrade, and every number >= 2 of an `expression` is written in its story or
# its why. Two cases the validator now knows (validate_item): an ALGEBRAIC
# `expression` is a polynomial (parse_poly), and a LINEAR EQUATION `lhs = rhs` in
# one letter, with a numeric answer, is valid when that answer solves it.

def _neg(n) -> str:
    """A number as written inside an expression: -3 -> '(-3)', 3 -> '3'."""
    return f"({n})" if n < 0 else str(n)


def _affine(a: int, b: int, var: str = "x") -> str:
    """'3x + 5', '-x - 2', '4x': a linear expression as a learner reads it."""
    head = {1: var, -1: f"-{var}"}.get(a, f"{a}{var}")
    if b == 0:
        return head
    return f"{head} + {b}" if b > 0 else f"{head} - {-b}"


def _mono(coef: int, parts) -> str:
    """A monomial as written: _mono(-4, [('x', 2), ('y', 1)]) -> '-4x^2y'."""
    lit = "".join(v if e == 1 else f"{v}^{e}" for v, e in parts)
    if not lit:
        return str(coef)
    if coef == 1:
        return lit
    if coef == -1:
        return f"-{lit}"
    return f"{coef}{lit}"


def _fac(n: int) -> dict:
    """Prime factorisation as {prime: exponent}."""
    out: dict = {}
    d = 2
    while d * d <= n:
        while n % d == 0:
            out[d] = out.get(d, 0) + 1
            n //= d
        d += 1
    if n > 1:
        out[n] = out.get(n, 0) + 1
    return out


def _fac_str(n: int) -> str:
    """360 -> '2^3 · 3^2 · 5' (the factorisation as the learner writes it)."""
    return " · ".join(f"{p}^{e}" if e > 1 else str(p) for p, e in sorted(_fac(n).items()))


def _prod_str(fac: dict) -> str:
    """{2: 2, 3: 1} -> '2^2 × 3' (an expression that the grader can evaluate)."""
    parts = [f"{p}^{e}" if e > 1 else str(p) for p, e in sorted(fac.items())]
    return " × ".join(parts) if parts else "1"


def integers_combined(rng: random.Random) -> dict:
    """Integers: negatives, powers, parentheses and a nested level (the 'claudàtor'
    is a parenthesis inside a parenthesis: the grader reads round brackets only).
    '(-3) · (4 - 9) + 2^2' -> 19."""
    shape = rng.randrange(4)
    a, b, c, d = rng.randint(2, 9), rng.randint(2, 9), rng.randint(2, 9), rng.randint(2, 5)
    if shape == 0:
        bc = b - c
        p = -a * bc
        value = p + d * d
        problem = f"({-a}) · ({b} - {c}) + {d}^2"
        why = (f"Primer el parèntesi: {b} - {c} = {bc}. Després la potència: {d}^2 = {d * d}. "
               f"Després el producte: ({-a}) · ({bc}) = {p}; el signe del producte el decideixen "
               f"els signes dels factors. Per acabar {p} + {d * d} = {value}.")
    elif shape == 1:
        bcd = (b - c) * d
        value = -a - bcd
        problem = f"-{a} - ({b} - {c}) · {d}"
        why = (f"Primer el parèntesi: {b} - {c} = {b - c}. Després el producte: {b - c} · {d} = {bcd}. "
               f"Per acabar {-a} - ({bcd}) = {value}: restar un nombre negatiu és sumar-lo.")
    elif shape == 2:
        value = a * b - c * c + d
        problem = f"({-a}) · ({-b}) - {c}^2 + {d}"
        why = (f"Dos negatius multipliquen positiu: ({-a}) · ({-b}) = {a * b}. La potència abans "
               f"de sumar: {c}^2 = {c * c}. Per acabar {a * b} - {c * c} + {d} = {value}.")
    else:
        cd = c - d
        bcd = b - cd
        value = a - bcd
        problem = f"{a} - ({b} - ({c} - {d}))"
        why = (f"Primer el parèntesi de dins: {c} - {d} = {cd}. Després el de fora: "
               f"{b} - ({cd}) = {bcd}. Per acabar {a} - ({bcd}) = {value}.")
    return {
        "type": "compute",
        "instruction": "Calcula respectant els parèntesis, les potències i els signes.",
        "problem": problem,
        "answer": str(value),
        "also_accept": [],
        "options": [],
        "value": Fraction(value),
        "why": why,
    }


def gcd_lcm_problems(rng: random.Random) -> dict:
    """Problems solved with the MCD (tiles or strips cut in equal pieces) or the mcm
    (buses that leave together). The expression is the factorisation that gives the
    answer; the factorisations of both numbers are written in the why."""
    if rng.random() < 0.5:
        for _ in range(200):
            p, q = rng.sample(range(2, 10), 2)
            if math.gcd(p, q) == 1:
                break
        else:
            raise GenError("gcd_lcm_problems: no coprime pair in 200 draws")
        g = rng.randint(2, 12)
        a, b = g * p, g * q
        res = g
        expr = _prod_str(_fac(g))
        problem = (f"Vols tallar dues tires de {a} cm i {b} cm en trossos iguals, tan llargs com "
                   "sigui possible i sense que en sobri res. Quant ha de mesurar cada tros (en cm)?")
        why = (f"{a} = {_fac_str(a)} i {b} = {_fac_str(b)}. Els factors comuns són {expr}, i el "
               f"tros més llarg possible és el MCD: {res} cm.")
        instruction = "Resol el problema (MCD: el tros més llarg que cap exactament en les dues tires)."
    else:
        for _ in range(500):
            a, b = rng.randint(4, 24), rng.randint(4, 24)
            if a == b:
                continue
            res = _lcm(a, b)
            if res > max(a, b) and res <= 200:
                break
        else:
            raise GenError("gcd_lcm_problems: no bus pair in 500 draws")
        fa, fb = _fac(a), _fac(b)
        fac = {p: max(fa.get(p, 0), fb.get(p, 0)) for p in set(fa) | set(fb)}
        expr = _prod_str(fac)
        problem = (f"Dos autobusos surten de l'estació a la vegada. Un passa cada {a} minuts i "
                   f"l'altre cada {b} minuts. Al cap de quants minuts tornen a sortir junts?")
        why = (f"{a} = {_fac_str(a)} i {b} = {_fac_str(b)}. El mcm agafa cada factor amb el seu "
               f"major exponent: {expr} = {res}.")
        instruction = "Resol el problema (mcm: el primer moment en què els dos coincideixen)."
    return {
        "type": "compute",
        "instruction": instruction,
        "problem": problem,
        "expression": expr,
        "answer": str(res),
        "also_accept": [],
        "options": [],
        "value": Fraction(res),
        "why": why,
    }


def frac_combined(rng: random.Random) -> dict:
    """Fractions with parentheses and powers. The answer is the raw result (not
    reduced); its reduced form is also accepted."""
    def frac():
        return rng.randint(1, 9), rng.randint(2, 9)

    shape = rng.randrange(3)
    if shape == 0:
        for _ in range(200):
            (p, q), (r, s), (t, u) = frac(), frac(), frac()
            if Fraction(p, q) > Fraction(r, s):
                break
        else:
            raise GenError("frac_combined: no decreasing pair in 200 draws")
        inner = Fraction(p, q) - Fraction(r, s)
        value = inner * Fraction(t, u)
        raw = f"{(p * s - r * q) * t}/{q * s * u}"
        problem = f"({p}/{q} - {r}/{s}) × ({t}/{u})"
        why = (f"Primer el parèntesi: {p}/{q} - {r}/{s} = {_fmt_frac(inner)}. Després la "
               f"multiplicació: {_fmt_frac(inner)} × {t}/{u} = {_fmt_frac(value)}.")
    elif shape == 1:
        (p, q), (r, s) = frac(), frac()
        value = Fraction(p, q) ** 2 + Fraction(r, s)
        raw = f"{p * p * s + r * q * q}/{q * q * s}"
        problem = f"({p}/{q})^2 + {r}/{s}"
        why = (f"Primer la potència: ({p}/{q})^2 = {p * p}/{q * q}. Després la suma amb {r}/{s}: "
               f"{_fmt_frac(value)}.")
    else:
        (p, q), (r, s), (t, u) = frac(), frac(), frac()
        inner = Fraction(p, q) + Fraction(r, s)
        value = inner / Fraction(t, u)
        raw = f"{(p * s + r * q) * u}/{q * s * t}"
        problem = f"({p}/{q} + {r}/{s}) ÷ ({t}/{u})"
        why = (f"Primer el parèntesi: {p}/{q} + {r}/{s} = {_fmt_frac(inner)}. Dividir per una "
               f"fracció és multiplicar per la inversa: {_fmt_frac(inner)} ÷ {t}/{u} = {_fmt_frac(value)}.")
    simple = _fmt_frac(value)
    return {
        "type": "compute",
        "instruction": "Calcula i dona el resultat (pots deixar-lo sense simplificar).",
        "problem": problem,
        "answer": raw,
        "also_accept": [simple] if simple != raw else [],
        "options": [],
        "value": value,
        "why": why + f" Sense simplificar queda {raw}; simplificada, {simple}.",
    }


def generatrix(rng: random.Random) -> dict:
    """An exact decimal written as an irreducible fraction: 0,36 -> 9/25, 2,5 -> 5/2."""
    k = rng.randint(1, 3)
    while True:
        n = rng.randint(1, 3 * 10 ** k - 1)
        if n % (10 ** k):
            break
    value = Fraction(n, 10 ** k)
    dec = _fmt_min_dec(value)
    answer = _fmt_frac(value)
    raw = f"{n}/{10 ** k}"
    g = math.gcd(n, 10 ** k)
    step = (f"Simplifiquem dividint numerador i denominador pel MCD ({g})." if g > 1
           else "Ja és irreductible: el numerador i el denominador no tenen cap factor comú.")
    return {
        "type": "compute",
        "instruction": "Escriu el decimal com a fracció irreductible.",
        "problem": dec,
        "answer": answer,
        "also_accept": [raw] if raw != answer else [],
        "options": [],
        "value": value,
        "why": (f"{dec} té {k} decimal{'s' if k > 1 else ''}, així que és {n}/{10 ** k}. {step} "
                f"Resultat: {answer}.{mixed_gloss(answer)}"),
    }


def powers_props(rng: random.Random) -> dict:
    """Powers: product (add exponents), quotient (subtract) and power of a power
    (multiply). The answer is the power ('2^7'); the value is accepted too."""
    shape = rng.randrange(3)
    a = rng.choice([2, 3, 5, 10])
    if shape == 0:
        m, n = rng.randint(2, 6), rng.randint(2, 6)
        problem = f"{a}^{m} × {a}^{n}"
        e = m + n
        why = (f"La base és la mateixa: en multiplicar se sumen els exponents. "
               f"{m} + {n} = {e}, així que {a}^{m} × {a}^{n} = {a}^{e}.")
    elif shape == 1:
        n = rng.randint(2, 5)
        m = rng.randint(n + 2, 9)
        problem = f"{a}^{m} ÷ {a}^{n}"
        e = m - n
        why = (f"La base és la mateixa: en dividir es resten els exponents. "
               f"{m} - {n} = {e}, així que {a}^{m} ÷ {a}^{n} = {a}^{e}.")
    else:
        m, n = rng.randint(2, 4), rng.randint(2, 3)
        problem = f"({a}^{m})^{n}"
        e = m * n
        why = (f"Potència de potència: es multipliquen els exponents. "
               f"{m} × {n} = {e}, així que ({a}^{m})^{n} = {a}^{e}.")
    return {
        "type": "compute",
        "instruction": "Aplica les propietats de les potències i dona el resultat com a potència.",
        "problem": problem,
        "answer": f"{a}^{e}",
        "also_accept": [str(a ** e)],
        "options": [],
        "value": Fraction(a ** e),
        "why": why,
    }


def translate_expr(rng: random.Random) -> dict:
    """Algebraic language: a sentence with the letter x becomes an expression. The
    sentence is the `problem` (prose); `expression` is the direct translation, a
    polynomial, and it is the one the validator checks (the algebra path)."""
    c = rng.randint(2, 9)
    k = rng.randint(2, 6)
    shape = rng.randrange(4)
    if shape == 0:
        story = f"el doble d'un nombre x, més {c}"
        # the translation is written in a surface form that is not the canonical answer
        # (grade_algebraic's verbatim-retype guard compares with `expression`)
        expr = f"x · 2 + {c}"
        poly = {(("x", 1),): Fraction(2), (): Fraction(c)}
        why = f"«El doble d'un nombre x» és 2 · x; «més {c}» és + {c}: 2x + {c}."
    elif shape == 1:
        story = f"un nombre x augmentat en {c} i després multiplicat per {k}"
        expr = f"(x + {c}) · {k}"
        poly = {(("x", 1),): Fraction(k), (): Fraction(k * c)}
        why = (f"«Augmentat en {c}» és x + {c}; «multiplicat per {k}» és {k} · (x + {c}), "
               f"que es desplega en {k}x + {k * c}.")
    elif shape == 2:
        story = f"la diferència entre el triple de x i {c}"
        expr = f"x · 3 - {c}"
        poly = {(("x", 1),): Fraction(3), (): Fraction(-c)}
        why = f"«El triple de x» és 3 · x; «la diferència amb {c}» és restar {c}: 3x - {c}."
    else:
        story = "el quadrat d'un nombre x més el seu triple"
        expr = "x · x + x · 3"
        poly = {(("x", 2),): Fraction(1), (("x", 1),): Fraction(3)}
        why = "«El quadrat de x» és x^2 i «el seu triple» és 3 · x: x^2 + 3x."
    ans, alts = _alg_answer(poly)
    return {
        "type": "compute",
        "instruction": "Tradueix l'enunciat a llenguatge algebraic (x és el nombre).",
        "problem": story,
        "expression": expr,
        "answer": ans,
        "also_accept": alts,
        "options": [],
        "value": None,
        "why": why,
    }


def monomials_ops(rng: random.Random) -> dict:
    """Monomials: product (multiply coefficients, add exponents), sum of like terms
    (add coefficients, keep the literal part) and a power of a monomial."""
    shape = rng.randrange(3)
    a = rng.randint(2, 6)
    b = rng.randint(2, 6)
    m, n, k = rng.randint(1, 3), rng.randint(1, 3), rng.randint(1, 2)
    if shape == 0:
        sb = rng.choice([b, -b])
        problem = f"{_mono(a, [('x', m)])} · ({_mono(sb, [('x', n), ('y', k)])})"
        poly = {(("x", m + n), ("y", k)): Fraction(a * sb)}
        why = (f"Coeficients: {a} · ({sb}) = {a * sb}. Lletres: x^{m} · x^{n} = x^{m + n} (els "
               f"exponents se sumen) i la y^{k} es queda igual.")
    elif shape == 1:
        cs = [a, b, -rng.randint(1, 6)]
        if sum(cs) == 0:
            cs[2] -= 1
        text = _mono(cs[0], [("x", m), ("y", k)])
        for c in cs[1:]:
            text += f" + {_mono(c, [('x', m), ('y', k)])}" if c > 0 else f" - {_mono(-c, [('x', m), ('y', k)])}"
        problem = text
        total = sum(cs)
        poly = {(("x", m), ("y", k)): Fraction(total)}
        why = (f"Són termes semblants (la mateixa part literal): només se sumen els coeficients, "
               f"{' '.join(f'{c:+d}' for c in cs)} = {total}, i la part literal es queda igual.")
    else:
        problem = f"({_mono(a, [('x', m)])})^2"
        poly = {(("x", 2 * m),): Fraction(a * a)}
        why = (f"Cada factor es multiplica per si mateix: el coeficient queda {a} · {a} = {a * a} "
               f"i l'exponent es dobla: x^{m} · x^{m} = x^{2 * m}.")
    ans, alts = _alg_answer(poly)
    return {
        "type": "compute",
        "instruction": "Opera amb els monomis i dona el resultat simplificat.",
        "problem": problem,
        "answer": ans,
        "also_accept": alts,
        "options": [],
        "value": None,
        "why": why,
    }


def _subst_side(side: str, var: str, value: Fraction) -> str:
    """The side with the unknown replaced by the value, in grader notation."""
    s = re.sub(rf"(?<![a-zA-Z]){var}(?![a-zA-Z])", f"({value})", side)
    return re.sub(r"(\d|\))\s*\(", r"\1*(", s)


def _solves_equation(item: dict) -> list[str]:
    """A linear equation in one letter with a numeric answer: the answer must make
    both sides equal (the same evaluator that grades the learner)."""
    sides = str(item["problem"]).split("=")
    if len(sides) != 2:
        return ["equation needs exactly one '='"]
    letters = set(_ALG_LETTERS.findall(str(item["problem"])))
    if len(letters) != 1:
        return ["equation needs exactly one unknown letter"]
    var = letters.pop()
    try:
        value = _answer_value(item["answer"])
    except mathgrade.ParseError as e:
        return [f"answer does not parse: {e}"]
    values = []
    for side in sides:
        try:
            values.append(mathgrade.parse_expr(_subst_side(side, var, value)).value)
        except mathgrade.ParseError as e:
            return [f"equation side {side!r} does not parse after substitution: {e}"]
    if values[0] != values[1]:
        return [f"answer {item['answer']!r} does not solve the equation {item['problem']!r}"]
    return []


def linear_equations(rng: random.Random) -> dict:
    """Linear equations with a whole solution: brackets first, then transposition.
    The answer is the value of x; the equation is checked by substitution."""
    x0 = rng.choice([v for v in range(-9, 13) if v != 0])
    if rng.random() < 0.5:
        p = rng.choice([2, 3, 4, 5, -2, -3])
        q = rng.choice([v for v in range(-6, 9) if v != 0])
        r = rng.choice([v for v in range(-4, 5) if v not in (0, -p)])
        lhs = f"{p} · (x {'+' if q > 0 else '-'} {abs(q)})"
        lhs += f" {'+' if r > 0 else '-'} {abs(r)} · x"
        s = p * (x0 + q) + r * x0
        problem = f"{lhs} = {s}"
        why = (f"Treu el parèntesi: {_affine(p, p * q)}. Redueix les x: {p + r}x = {s - p * q}. "
               f"Aïlla la x dividint per {p + r}: x = {x0}.")
    else:
        a = rng.choice([v for v in range(-6, 7) if v])
        c = rng.choice([v for v in range(-6, 7) if v and v != a])
        d = rng.randint(-9, 9)
        b = (c - a) * x0 + d
        problem = f"{_affine(a, b)} = {_affine(c, d)}"
        why = (f"Passa les x a un costat i els nombres a l'altre: {a - c}x = {d - b}. "
               f"Divideix per {a - c}: x = {x0}.")
    return {
        "type": "compute",
        "instruction": "Resol l'equació: quin valor té x?",
        "problem": problem,
        "answer": str(x0),
        "also_accept": [],
        "options": [],
        "value": None,
        "why": why,
    }


def proportion_problems(rng: random.Random) -> dict:
    """Direct proportion, inverse proportion and chained percentages. The arithmetic
    lives in `expression`; the answer carries its unit (€) or none."""
    shape = rng.randrange(3)
    if shape == 0:
        while True:
            a = rng.choice([2, 4, 5, 10, 20, 25])
            b = rng.randint(3, 80)
            c = rng.randint(2, 12)
            value = Fraction(b * c, a)
            try:
                txt = _fmt_min_dec(value)
                break
            except GenError:
                continue
        problem = (f"{a} quaderns iguals costen {b} €. Quant costen {c} quaderns com aquests?")
        expr = f"{b} ÷ {a} × {c}"
        why = (f"Proporció directa: un quadern val {b} ÷ {a} = {_fmt_min_dec(Fraction(b, a))} €; "
               f"{c} quaderns valen {c} × {_fmt_min_dec(Fraction(b, a))} = {txt} €.")
        answer = f"{txt} €"
    elif shape == 1:
        while True:
            a = rng.randint(2, 9)
            b = rng.randint(2, 12)
            c = rng.randint(2, 9)
            value = Fraction(a * b, c)
            try:
                txt = _fmt_min_dec(value)
                break
            except GenError:
                continue
        problem = f"{a} obrers fan una feina en {b} dies, tots al mateix ritme. Quants dies trigaran {c} obrers?"
        expr = f"{a} × {b} ÷ {c}"
        why = (f"Proporció inversa: el treball total és {a} × {b} = {a * b} obrers·dia. "
               f"Amb {c} obrers, {a * b} ÷ {c} = {txt} dies.")
        answer = txt
    else:
        p = rng.randrange(20, 200, 10)
        up = rng.choice([10, 20, 25, 50])
        down = rng.choice([10, 20, 25])
        value = Fraction(p * (100 + up) * (100 - down), 10000)
        txt = _fmt_min_dec(value)
        problem = (f"Un article val {p} €. Puja un {up} % i després baixa un {down} %. "
                   "Quin és el preu final?")
        expr = f"{p} × (1 + {up} / 100) × (1 - {down} / 100)"
        f_up = _fmt_min_dec(Fraction(100 + up, 100))
        f_down = _fmt_min_dec(Fraction(100 - down, 100))
        why = (f"Pujar un {up} % és multiplicar per {f_up} ({100 + up} de cada 100), i baixar un "
               f"{down} % és multiplicar per {f_down} ({100 - down} de cada 100): "
               f"{p} × {f_up} × {f_down} = {txt} €.")
        answer = f"{txt} €"
    return {
        "type": "compute",
        "instruction": "Resol el problema de proporcionalitat.",
        "problem": problem,
        "expression": expr,
        "answer": answer,
        "also_accept": [],
        "options": [],
        "value": value,
        "why": why,
    }


def linear_function(rng: random.Random) -> dict:
    """A straight line y = mx + n: the value of y for an x, the slope from two points,
    or the intercept n from a point and the slope."""
    shape = rng.randrange(3)
    if shape == 0:
        m = rng.choice([v for v in range(-5, 6) if v])
        n = rng.randint(-6, 6)
        x0 = rng.randint(-3, 5)
        value = m * x0 + n
        problem = f"La recta és y = {_affine(m, n)}. Quin valor té y quan x = {x0}?"
        expr = f"{_neg(m)} × {_neg(x0)} + {_neg(n)}"
        why = f"Substitueix la x per {x0}: {m} × ({x0}) + ({n}) = {value}."
        answer = str(value)
    elif shape == 1:
        m = rng.choice([v for v in range(-4, 5) if v])
        dx = rng.choice([1, 2, 3])
        x1, y1 = rng.randint(-4, 4), rng.randint(-5, 5)
        x2, y2 = x1 + dx, y1 + m * dx
        problem = f"Una recta passa pels punts ({x1}, {y1}) i ({x2}, {y2}). Quina és la seva pendent m?"
        expr = f"({_neg(y2)} - {_neg(y1)}) / ({_neg(x2)} - {_neg(x1)})"
        value = Fraction(m)
        why = (f"La pendent és l'increment de y entre l'increment de x: ({y2} - ({y1})) ÷ "
               f"({x2} - ({x1})) = {m}.")
        answer = str(m)
    else:
        m = rng.choice([v for v in range(-4, 5) if v])
        x1, y1 = rng.randint(-4, 4), rng.randint(-6, 6)
        n = y1 - m * x1
        problem = f"Una recta té pendent {m} i passa pel punt ({x1}, {y1}). Quina és l'ordenada a l'origen n?"
        expr = f"{_neg(y1)} - {_neg(m)} × {_neg(x1)}"
        value = Fraction(n)
        why = f"Com que y = mx + n: {y1} = {m} × ({x1}) + n, així que n = {y1} - ({m * x1}) = {n}."
        answer = str(n)
    return {
        "type": "compute",
        "instruction": "Respon a partir de la recta (y = mx + n).",
        "problem": problem,
        "expression": expr,
        "answer": answer,
        "also_accept": [],
        "options": [],
        "value": value,
        "why": why,
    }


def pythagoras(rng: random.Random) -> dict:
    """Pythagoras with the square of the length (no root needed): c^2 = a^2 + b^2,
    and the square of a missing leg. The answer is in cm²."""
    if rng.random() < 0.5:
        a, b = rng.randint(3, 15), rng.randint(3, 15)
        value = a * a + b * b
        problem = (f"Un triangle rectangle té catets de {a} cm i {b} cm. Quant val el quadrat de la "
                   "hipotenusa (en cm²)?")
        expr = f"{a}^2 + {b}^2"
        why = (f"Teorema de Pitàgores: c^2 = a^2 + b^2. {a}^2 = {a * a} i {b}^2 = {b * b}, "
               f"així que c^2 = {value} cm².")
    else:
        a = rng.randint(3, 14)
        c = rng.randint(a + 1, 20)
        value = c * c - a * a
        problem = (f"La hipotenusa d'un triangle rectangle mesura {c} cm i un catet mesura {a} cm. "
                   "Quant val el quadrat de l'altre catet (en cm²)?")
        expr = f"{c}^2 - {a}^2"
        why = (f"Teorema de Pitàgores aïllat: b^2 = c^2 - a^2. {c}^2 = {c * c} i {a}^2 = {a * a}, "
               f"així que b^2 = {value} cm².")
    return {
        "type": "compute",
        "instruction": "Calcula el quadrat (no cal treure l'arrel).",
        "problem": problem,
        "expression": expr,
        "answer": f"{value} cm²",
        "also_accept": [],
        "options": [],
        "value": Fraction(value),
        "why": why,
    }


def polygon_angles(rng: random.Random) -> dict:
    """Interior angles of a polygon: their sum (n - 2) · 180, or one angle of a
    regular polygon."""
    if rng.random() < 0.5:
        n = rng.randint(4, 14)
        value = (n - 2) * 180
        problem = f"Quina és la suma dels angles interiors d'un polígon de {n} costats (en graus)?"
        expr = f"({n} - 2) × 180"
        why = (f"Un polígon de {n} costats es divideix en {n - 2} triangles des d'un vèrtex; "
               f"cada triangle suma 180°: ({n} - 2) × 180 = {value}.")
    else:
        n = rng.choice([v for v in (3, 4, 5, 6, 8, 9, 10, 12, 15, 18, 20, 30, 36) if ((v - 2) * 180) % v == 0])
        value = (n - 2) * 180 // n
        problem = f"Cada angle interior d'un polígon regular de {n} costats, quant mesura (en graus)?"
        expr = f"({n} - 2) × 180 / {n}"
        why = (f"La suma dels angles interiors és ({n} - 2) × 180 = {(n - 2) * 180}°; en un polígon "
               f"regular tots són iguals: {(n - 2) * 180} ÷ {n} = {value}°.")
    return {
        "type": "compute",
        "instruction": "Calcula amb els angles interiors del polígon (en graus).",
        "problem": problem,
        "expression": expr,
        "answer": str(value),
        "also_accept": [],
        "options": [],
        "value": Fraction(value),
        "why": why,
    }


def composite_areas(rng: random.Random) -> dict:
    """Areas of composite figures: a rectangle with a square removed, a circle and a
    circular crown (π = 3,14). The answer carries cm²."""
    shape = rng.randrange(3)
    if shape == 0:
        a, b = rng.randint(5, 12), rng.randint(4, 10)
        c = rng.randint(1, min(a, b) - 1)
        value = Fraction(a * b - c * c)
        problem = (f"Un rectangle de {a} cm × {b} cm té retallat un quadrat de {c} cm de costat. "
                   "Quina és l'àrea que queda (en cm²)?")
        expr = f"{a} × {b} - {c} × {c}"
        why = f"L'àrea del rectangle és {a} × {b} = {a * b} cm² i la del quadrat {c} × {c} = {c * c} cm²: {a * b} - {c * c} = {value}."
    elif shape == 1:
        r = rng.randint(2, 12)
        value = Fraction(314, 100) * r * r
        problem = f"Un cercle té un radi de {r} cm. Quina és la seva àrea (π = 3,14, en cm²)?"
        expr = f"3,14 × {r}^2"
        why = (f"Àrea del cercle: π · r^2. r^2 = {r}^2 = {r * r}, i 3,14 × {r * r} = {_fmt_min_dec(value)} cm².")
    else:
        big = rng.randint(4, 12)
        small = rng.randint(1, big - 1)
        value = Fraction(314, 100) * (big * big - small * small)
        problem = (f"Una corona circular té un radi exterior de {big} cm i un radi interior de {small} cm. "
                   "Quina és la seva àrea (π = 3,14, en cm²)?")
        expr = f"3,14 × {big}^2 - 3,14 × {small}^2"
        why = (f"Corona = cercle gran menys cercle petit: 3,14 × {big}^2 - 3,14 × {small}^2 = "
               f"3,14 × {big * big} - 3,14 × {small * small} = {_fmt_min_dec(value)} cm².")
    return {
        "type": "compute",
        "instruction": "Calcula l'àrea de la figura composta.",
        "problem": problem,
        "expression": expr,
        "answer": f"{_fmt_min_dec(value)} cm²",
        "also_accept": [],
        "options": [],
        "value": value,
        "why": why,
    }


def units_derived(rng: random.Random) -> dict:
    """Area and volume units, km/h to m/s, and density. The answer keeps its unit
    when the grader can read it (cm², dm², cm³), else the instruction names it."""
    shape = rng.randrange(4)
    if shape == 0:
        s = rng.randint(2, 9)
        value = Fraction(s * 10) * Fraction(s * 10)
        problem = f"Un terra quadrat té {s} m de costat. Quants dm² fa?"
        expr = f"({s} × 10) × ({s} × 10)"
        why = f"1 m = 10 dm: el costat són {s * 10} dm i l'àrea {s * 10} × {s * 10} = {value} dm²."
        answer = f"{value} dm²"
    elif shape == 1:
        a, b, c = rng.randint(2, 9), rng.randint(2, 9), rng.randint(2, 9)
        value = Fraction(a * b * c)
        problem = f"Un prisma té la base de {a} cm × {b} cm i una alçada de {c} cm. Quin és el volum (en cm³)?"
        expr = f"{a} × {b} × {c}"
        why = f"Volum = àrea de la base × alçada: {a} × {b} × {c} = {value} cm³."
        answer = f"{value} cm³"
    elif shape == 2:
        v = rng.choice([18, 36, 54, 72, 90, 108, 126])
        value = Fraction(v) / Fraction(18, 5)
        problem = f"Un tren va a {v} km/h. Quants metres recorre en un segon? (Dona'l en m/s.)"
        expr = f"{v} ÷ 3,6"
        why = (f"Per passar de km/h a m/s es divideix entre 3,6: 1 km = 1000 m i 1 h = 3600 s, "
               f"i 1000 ÷ 3600 = 1 ÷ 3,6. Resultat: {v} ÷ 3,6 = {_fmt_min_dec(value)} m/s.")
        answer = _fmt_min_dec(value)
    else:
        vol = rng.choice([2, 4, 5, 8, 10, 20, 25, 40, 50])
        mass = rng.randint(3, 90)
        value = Fraction(mass, vol)
        problem = f"Una peça té una massa de {mass} g i un volum de {vol} cm³. Quina és la densitat (en g/cm³)?"
        expr = f"{mass} ÷ {vol}"
        why = f"La densitat és massa entre volum: {mass} ÷ {vol} = {_fmt_min_dec(value)} g/cm³."
        answer = _fmt_min_dec(value)
    return {
        "type": "compute",
        "instruction": "Fes la conversió o el càlcul amb les unitats indicades.",
        "problem": problem,
        "expression": expr,
        "answer": answer,
        "also_accept": [],
        "options": [],
        "value": value,
        "why": why,
    }


def sexagesimal_ops(rng: random.Random) -> dict:
    """Hours and minutes: a time multiplied, a sum, a difference. The answer is in
    minutes (the smallest unit), so the grader compares one number."""
    shape = rng.randrange(3)
    h1, m1 = rng.randint(0, 3), rng.randint(0, 59)
    if shape == 0:
        k = rng.randint(2, 4)
        value = (h1 * 60 + m1) * k
        problem = f"Una pel·lícula dura {h1} h {m1} min. Quants minuts duren {k} pel·lícules seguides?"
        expr = f"({h1} × 60 + {m1}) × {k}"
        why = (f"Passa-ho a minuts (1 h = 60 min): {h1} h = {h1 * 60} min, i {h1 * 60} + {m1} = "
               f"{h1 * 60 + m1} min. Després × {k} = {value} min.")
    elif shape == 1:
        h2, m2 = rng.randint(0, 3), rng.randint(0, 59)
        value = (h1 * 60 + m1) + (h2 * 60 + m2)
        problem = f"Una cursa ha durat {h1} h {m1} min i una altra {h2} h {m2} min. Quants minuts sumen les dues?"
        expr = f"({h1} × 60 + {m1}) + ({h2} × 60 + {m2})"
        why = f"Cada temps en minuts (1 h = 60 min): {h1 * 60 + m1} i {h2 * 60 + m2}; la suma és {value} min."
    else:
        h2 = h1 + rng.randint(1, 3)
        m2 = rng.randint(0, 59)
        value = (h2 * 60 + m2) - (h1 * 60 + m1)
        problem = f"Quant temps passa entre les {h1} h {m1} min i les {h2} h {m2} min? Dona-ho en minuts."
        expr = f"({h2} × 60 + {m2}) - ({h1} × 60 + {m1})"
        why = (f"En minuts: {h2 * 60 + m2} - {h1 * 60 + m1} = {value} min (1 h = 60 min, "
               "així que es resta el temps en minuts).")
    return {
        "type": "compute",
        "instruction": "Fes l'operació amb hores i minuts i dona el resultat en minuts.",
        "problem": problem,
        "expression": expr,
        "answer": f"{value} min",
        "also_accept": [],
        "options": [],
        "value": Fraction(value),
        "why": why,
    }


def stats_tables(rng: random.Random) -> dict:
    """Weighted mean (from a frequency table), median, mode and range of a short list."""
    shape = rng.randrange(4)
    if shape == 0:
        for _ in range(400):
            ns = [rng.randint(1, 6) for _ in range(3)]
            xs = [rng.randint(3, 10) for _ in range(3)]
            total = sum(ns)
            value = Fraction(sum(n * x for n, x in zip(ns, xs)), total)
            try:
                txt = _fmt_min_dec(value)
                break
            except GenError:
                continue
        else:
            raise GenError("stats_tables: no decimal weighted mean in 400 draws")
        n1, n2, n3 = ns
        x1, x2, x3 = xs
        problem = (f"En un examen, {n1} alumnes han tret un {x1}, {n2} un {x2} i {n3} un {x3}. "
                   "Quina és la nota mitjana del grup?")
        expr = (f"({n1} × {x1} + {n2} × {x2} + {n3} × {x3}) ÷ ({n1} + {n2} + {n3})")
        why = (f"Mitjana ponderada: cada nota pesa segons els alumnes que l'han tret. "
               f"{n1} + {n2} + {n3} = {total} alumnes; la suma de notes és "
               f"{n1 * x1 + n2 * x2 + n3 * x3}; {n1 * x1 + n2 * x2 + n3 * x3} ÷ {total} = {txt}.")
        answer = txt
    elif shape == 1:
        size = rng.choice([5, 6, 7])
        vals = rng.sample(range(2, 20), size)
        srt = sorted(vals)
        if size % 2:
            mid = srt[size // 2]
            expr = str(mid)
            value = Fraction(mid)
            why = f"Ordenades: {_listing(srt)}. La de la posició central és {mid}: la mediana."
        else:
            a, b = srt[size // 2 - 1], srt[size // 2]
            value = Fraction(a + b, 2)
            expr = f"({a} + {b}) ÷ 2"
            why = (f"Ordenades: {_listing(srt)}. Com que hi ha un nombre parell de dades, la mediana "
                   f"és la mitjana de les dues del mig: ({a} + {b}) ÷ 2 = {_fmt_min_dec(value)}.")
        problem = f"Les dades són {_listing(vals)}. Quina és la mediana?"
        answer = _fmt_min_dec(value)
    elif shape == 2:
        size = rng.randint(5, 7)
        pool = rng.sample(range(2, 15), size - 1)
        mode = rng.choice(pool)
        vals = pool + [mode]
        rng.shuffle(vals)
        value = Fraction(mode)
        problem = f"En un grup, les edats són {_listing(vals)}. Quina és la moda?"
        expr = str(mode)
        why = f"La moda és el valor que més es repeteix: {mode} (és el que apareix dues vegades)."
        answer = str(mode)
    else:
        size = rng.randint(4, 6)
        vals = rng.sample(range(3, 30), size)
        value = Fraction(max(vals) - min(vals))
        problem = f"Les temperatures d'una setmana han estat {_listing(vals)} graus. Quin és el rang?"
        expr = f"{max(vals)} - {min(vals)}"
        why = (f"El rang és la diferència entre el valor més gran ({max(vals)}) i el més petit "
               f"({min(vals)}): {max(vals)} - {min(vals)} = {value}.")
        answer = str(value)
    return {
        "type": "compute",
        "instruction": "Calcula el valor estadístic demanat.",
        "problem": problem,
        "expression": expr,
        "answer": answer,
        "also_accept": [],
        "options": [],
        "value": value,
        "why": why,
    }


def laplace(rng: random.Random) -> dict:
    """Laplace probability: favourable cases over possible ones, as a fraction. The
    simplified fraction is also accepted."""
    if rng.random() < 0.5:
        faces = [1, 2, 3, 4, 5, 6]
        event, label = rng.choice([
            (lambda f: f % 2 == 0, "un nombre parell"),
            (lambda f: f in (2, 3, 5), "un nombre primer"),
            (lambda f: f % 3 == 0, "un múltiple de 3"),
            (lambda f: f > 4, "un nombre més gran que 4"),
        ])
        fav = [f for f in faces if event(f)]
        fav_n, tot = len(fav), 6
        problem = f"Es llança un dau de 6 cares numerades de l'1 al 6. Quina probabilitat hi ha de treure {label}? Dona-la com a fracció."
        expr = f"{fav_n} / {tot}"
        why = (f"Els casos favorables són {_listing(fav)}: {fav_n} de {tot} casos possibles. "
               f"Probabilitat = {fav_n}/{tot}.")
        raw = f"{fav_n}/{tot}"
    else:
        red = rng.randint(2, 9)
        blue = rng.randint(2, 9)
        total = red + blue
        problem = (f"En una bossa hi ha {red} boles vermelles i {blue} de blaves. Quina probabilitat "
                   "hi ha de treure una bola vermella? Dona-la com a fracció.")
        expr = f"{red} / ({red} + {blue})"
        why = f"Casos possibles: {red} + {blue} = {total}; casos favorables: {red}. Probabilitat = {red}/{total}."
        fav_n, tot = red, total
        raw = f"{red}/{total}"
    value = Fraction(fav_n, tot)
    simple = _fmt_frac(value)
    return {
        "type": "compute",
        "instruction": "Calcula la probabilitat (casos favorables entre casos possibles).",
        "problem": problem,
        "expression": expr,
        "answer": raw,
        "also_accept": [simple] if simple != raw else [],
        "options": [],
        "value": value,
        "why": why,
    }


M7_FAMILIES = {
    "integers_combined": integers_combined,
    "gcd_lcm_problems": gcd_lcm_problems,
    "frac_combined": frac_combined,
    "generatrix": generatrix,
    "powers_props": powers_props,
    "translate_expr": translate_expr,
    "monomials_ops": monomials_ops,
    "linear_equations": linear_equations,
    "proportion_problems": proportion_problems,
    "linear_function": linear_function,
    "pythagoras": pythagoras,
    "polygon_angles": polygon_angles,
    "composite_areas": composite_areas,
    "units_derived": units_derived,
    "sexagesimal_ops": sexagesimal_ops,
    "stats_tables": stats_tables,
    "laplace": laplace,
}


# --------------------------------------------- m6 (E8, DISSENY-M7-M6 §2) ---
# The Go families of 6è de primària. Same contract as the rest: `value` is the
# template's Fraction, re-derived from `expression` (or `problem`) by the evaluator.
# Roots are "exact roots" only: the expression is a product of powers or a plain
# number (mathgrade does not read √). Units: a unit lives in `answer`; every unit
# used here is in _MEASURE_UNITS (the area "a" is only ever given, never asked:
# its answers are in m², because a letter-unit would read as algebra).


def powers_value(rng: random.Random) -> dict:
    """Exact powers (positive and negative bases), products of powers, and exact roots:
    the square or cube root of a perfect power, written as a product of prime powers."""
    shape = rng.randrange(4)
    if shape == 3:
        # a root is drawn from prime powers only, so its expression is a power or a plain
        # prime (mathgrade reads no root sign): 8 is 2^3, 7 is 7
        k = rng.choice([2, 3, 4, 5, 7, 8, 9, 11])
        square = rng.random() < 0.5
        n = k * k if square else k ** 3
        expr = _prod_str(_fac(k))
        name = "quadrada" if square else "cúbica"
        return {
            "type": "compute",
            "instruction": "Calcula l'arrel exacta (és un nombre enter).",
            "problem": f"Quina és l'arrel {name} exacta de {n}?",
            "expression": expr,
            "answer": str(k),
            "also_accept": [],
            "options": [],
            "value": Fraction(k),
            "why": (f"{n} = {_fac_str(n)}, i {k}{'²' if square else '³'} = {n}, així que "
                    f"l'arrel {name} de {n} és {k}. Com a potència exacta: {expr} = {k}."),
        }
    if shape == 0:
        b = rng.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
        emax = {2: 10, 3: 5, 4: 4, 5: 4, 6: 4, 7: 3, 8: 3, 9: 3, 10: 5, 11: 2, 12: 2}[b]
        e = rng.randint(2, emax)
        value = Fraction(b ** e)
        problem = f"{b}^{e}"
        why = f"{b}^{e} vol dir {' · '.join([str(b)] * e)} = {b ** e}."
    elif shape == 1:
        b = rng.randint(2, 6)
        e = rng.choice([2, 3])
        value = Fraction((-b) ** e)
        problem = f"({-b})^{e}"
        why = (f"Un negatiu elevat a un exponent {'senar' if e % 2 else 'parell'} dóna un resultat "
               f"{'negatiu' if e % 2 else 'positiu'}: ({-b})^{e} = {value}.")
    else:
        b1, b2 = rng.sample([2, 3, 5, 10], 2)
        e1, e2 = rng.randint(2, 3), rng.randint(2, 3)
        p1, p2 = b1 ** e1, b2 ** e2
        value = Fraction(p1 * p2)
        problem = f"{b1}^{e1} × {b2}^{e2}"
        why = f"{b1}^{e1} = {p1} i {b2}^{e2} = {p2}; {p1} × {p2} = {value}."
    return {
        "type": "compute",
        "instruction": "Calcula la potència o el producte de potències.",
        "problem": problem,
        "answer": str(value.numerator),
        "also_accept": [],
        "options": [],
        "value": value,
        "why": why,
    }


def integers_context(rng: random.Random) -> dict:
    """Sums and differences of integers in a context: temperatures, a lift below ground,
    a debt. The story is the problem; the arithmetic is the expression."""
    shape = rng.randrange(4)
    a = rng.randint(2, 12)
    b = rng.randint(2, 15)
    if shape == 0:
        story = (f"A les 8 del matí hi ha −{a} graus. Al migdia la temperatura puja {b} graus. "
                 "Quina temperatura hi ha al migdia?")
        why = f"Pujar és sumar: −{a} + {b} = {b - a}. Els nombres negatius estan sota zero."
    elif shape == 1:
        story = (f"L'ascensor és a la planta −{a} (el soterrani {a}). Puja {b} plantes. "
                 "En quina planta és ara?")
        why = f"Les plantes del soterrani tenen signe negatiu. Pujar és sumar: −{a} + {b} = {b - a}."
    elif shape == 2:
        story = (f"En Pau té un deute de {a} €, és a dir, un saldo de −{a} € al compte. "
                 f"Ingressa {b} €. Quin és el saldo ara?")
        why = f"Ingressar és sumar: −{a} + {b} = {b - a}. Un saldo negatiu és un deute."
    else:
        story = (f"Al matí hi fan {a} graus. Al vespre la temperatura baixa {b} graus. "
                 "Quina temperatura hi fa al vespre?")
        why = f"Baixar és restar: {a} − {b} = {a - b}. Si el resultat és negatiu, està sota zero."
    expr = f"-{a} + {b}" if shape < 3 else f"{a} - {b}"
    value = Fraction(b - a if shape < 3 else a - b)
    return {
        "type": "compute",
        "instruction": "Fes l'operació amb enters (pujar o ingressar és sumar, baixar és restar).",
        "problem": story,
        "expression": expr,
        "answer": str(value),
        "also_accept": [],
        "options": [],
        "value": value,
        "why": why,
    }


def frac_ops4(rng: random.Random) -> dict:
    """The four operations with fractions of different denominators; the answer is the
    irreducible form, and the unreduced result is also accepted."""
    op = rng.choice(["+", "-", "×", "÷"])
    for _ in range(2000):
        d1, d2 = rng.randint(2, 12), rng.randint(2, 12)
        if op in "+-" and d1 == d2:
            continue
        n1, n2 = rng.randint(1, d1 - 1), rng.randint(1, d2 - 1)
        f1, f2 = Fraction(n1, d1), Fraction(n2, d2)
        if op == "-":
            if f1 == f2:
                continue
            if f1 < f2:
                n1, d1, n2, d2 = n2, d2, n1, d1
                f1, f2 = f2, f1
            value = f1 - f2
        elif op == "+":
            value = f1 + f2
        elif op == "×":
            value = f1 * f2
        else:
            value = f1 / f2
        if value.denominator != 1:
            break
    else:
        raise GenError("frac_ops4: no fraction pair in 2000 draws")
    if op in "+-":
        L = _lcm(d1, d2)
        a1, a2 = n1 * (L // d1), n2 * (L // d2)
        raw_num = a1 + a2 if op == "+" else a1 - a2
        raw_den = L
        why = (f"Denominador comú {L}: {n1}/{d1} = {a1}/{L} i {n2}/{d2} = {a2}/{L}; "
               f"{'suma' if op == '+' else 'resta'} els numeradors: {a1} {op} {a2} = {raw_num}, "
               f"així que {raw_num}/{L}.")
    elif op == "×":
        raw_num, raw_den = n1 * n2, d1 * d2
        why = (f"Multiplica els numeradors ({n1} × {n2} = {raw_num}) i els denominadors "
               f"({d1} × {d2} = {raw_den}): {raw_num}/{raw_den}.")
    else:
        raw_num, raw_den = n1 * d2, d1 * n2
        why = (f"Dividir per una fracció és multiplicar per la inversa: {n1}/{d1} × {d2}/{n2} = "
               f"{raw_num}/{raw_den}.")
    g = math.gcd(raw_num, raw_den)
    answer = _fmt_frac(value)
    raw = f"{raw_num}/{raw_den}"
    if g > 1:
        why += f" Simplifica dividint per {g}: {answer}."
    why += mixed_gloss(answer)
    return {
        "type": "compute",
        "instruction": "Calcula i simplifica el resultat.",
        "problem": (f"{n1}/{d1} ÷ ({n2}/{d2})" if op == "÷" else f"{n1}/{d1} {op} {n2}/{d2}"),
        "answer": answer,
        "also_accept": [raw] if raw != answer else [],
        "options": [],
        "value": value,
        "why": why,
    }


def dec_division(rng: random.Random) -> dict:
    """A decimal divided by a whole number or by a one-decimal number, with an exact
    quotient (up to two decimals)."""
    for _ in range(500):
        if rng.random() < 0.5:
            d = Fraction(rng.randint(2, 9))
        else:
            k = rng.randint(2, 99)
            if k % 10 == 0:
                continue
            d = Fraction(k, 10)
        q = Fraction(rng.randint(11, 999), 100)
        dividend = d * q
        if dividend >= 1000 or (dividend * 1000).denominator != 1:
            continue
        break
    else:
        raise GenError("dec_division: no exact pair in 500 draws")
    ds, qs, xs = _fmt_min_dec(d), _fmt_min_dec(q), _fmt_min_dec(dividend)
    if d.denominator == 1:
        why = (f"Divideix {xs} per {ds} com amb enters i posa la coma al quocient just quan "
               f"baixes la primera xifra decimal del dividend: {xs} ÷ {ds} = {qs}.")
    else:
        why = (f"Per dividir per {ds} (un decimal), multiplica dividend i divisor per 10: "
               f"{_fmt_min_dec(dividend * 10)} ÷ {_fmt_min_dec(d * 10)} = {qs}, el mateix resultat.")
    return {
        "type": "compute",
        "instruction": "Calcula el quocient exacte (la coma al lloc correcte).",
        "problem": f"{xs} ÷ {ds}",
        "answer": qs,
        "also_accept": [],
        "options": [],
        "value": q,
        "why": why,
    }


def percent_change(rng: random.Random) -> dict:
    """Increases and decreases of a price (a factor 1 ± p/100), and a direct rule of three."""
    shape = rng.randrange(3)
    if shape == 2:
        for _ in range(400):
            n = rng.choice([2, 4, 5, 8])
            c = rng.randrange(10, 200, 10)
            k = rng.randint(2, 12)
            value = Fraction(c * k, n)
            if (value * 1000).denominator == 1:
                break
        else:
            raise GenError("percent_change: no exact rule of three in 400 draws")
        return {
            "type": "compute",
            "instruction": "Resol la regla de tres directa.",
            "problem": (f"{n} kg de pomes costen {c} €. Quant costen {k} kg de les mateixes "
                        "pomes?"),
            "expression": f"{c} × {k} ÷ {n}",
            "answer": _fmt_min_dec(value),
            "also_accept": [],
            "options": [],
            "value": value,
            "why": (f"Regla de tres directa: {c} × {k} = {c * k}; {c * k} ÷ {n} = "
                    f"{_fmt_min_dec(value)}. Més quilos, més euros."),
        }
    b = rng.randrange(10, 310, 10)
    p = rng.choice([5, 10, 15, 20, 25, 50])
    if shape == 0:
        factor = Fraction(100 + p, 100)
        story = f"Un article val {b} €. Puja un {p} %. Quin és el preu nou?"
        head = f"Augment del {p} %: el factor és 1 + {p}/100 = {_fmt_min_dec(factor)}."
    else:
        factor = Fraction(100 - p, 100)
        story = (f"Un article val {b} €. Es fa una rebaixa del {p} %. "
                 "Quin és el preu després de la rebaixa?")
        head = f"Descompte del {p} %: el factor és 1 − {p}/100 = {_fmt_min_dec(factor)}."
    value = b * factor
    return {
        "type": "compute",
        "instruction": "Calcula el preu final amb el factor de l'augment o del descompte.",
        "problem": story,
        "expression": f"{b} × {_fmt_min_dec(factor)}",
        "answer": _fmt_min_dec(value),
        "also_accept": [],
        "options": [],
        "value": value,
        "why": f"{head} {b} × {_fmt_min_dec(factor)} = {_fmt_min_dec(value)} €.",
    }


def scales(rng: random.Random) -> dict:
    """Map to real (1 cm on the map is n cm on the ground), real to map, and a real distance
    in km on a map at 1:n."""
    shape = rng.randrange(3)
    if shape == 0:
        n = rng.choice([100, 500, 1000, 2000, 5000, 10000, 25000, 50000])
        L = rng.randint(2, 12)
        value = Fraction(L * n, 100)
        return {
            "type": "compute",
            "instruction": "Passa la mesura del plànol a la real (en metres).",
            "problem": (f"En un plànol a escala 1:{n}, una paret mesura {L} cm. Quants metres "
                        "mesura la paret de veritat?"),
            "expression": f"{L} × {n} ÷ 100",
            "answer": f"{int(value)} m",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": (f"Cada centímetre del plànol són {n} cm de veritat: {L} × {n} = {L * n} cm. "
                    f"Passa-ho a metres (1 m = 100 cm): {L * n} ÷ 100 = {int(value)} m."),
        }
    if shape == 1:
        n = rng.choice([100, 200, 500, 1000])
        D = rng.randint(2, 40)
        value = Fraction(D * 100, n)
        return {
            "type": "compute",
            "instruction": "Passa la distància real a centímetres del mapa.",
            "problem": (f"En un mapa a escala 1:{n}, quants centímetres es dibuixen per a una "
                        f"distància real de {D} m?"),
            "expression": f"{D} × 100 ÷ {n}",
            "answer": f"{_fmt_min_dec(value)} cm",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": (f"1 m = 100 cm, així que {D} m = {D * 100} cm. {D * 100} ÷ {n} = "
                    f"{_fmt_min_dec(value)} cm sobre el mapa."),
        }
    K = rng.randint(2, 9)
    n = rng.choice([25000, 50000, 100000])
    value = Fraction(K * 100000, n)
    return {
        "type": "compute",
        "instruction": "Passa la distància real a centímetres del mapa.",
        "problem": (f"Dues ciutats estan a {K} km en línia recta. En un mapa a escala 1:{n}, "
                    "quants centímetres les separen?"),
        "expression": f"{K} × 100000 ÷ {n}",
        "answer": f"{int(value)} cm",
        "also_accept": [],
        "options": [],
        "value": value,
        "why": (f"1 km = 100000 cm, així que {K} km = {K * 100000} cm. {K * 100000} ÷ {n} = "
                f"{int(value)} cm."),
    }


# (big unit, small unit, how many small units in one big one).
_AREA_PAIRS = [("km²", "m²", 1000000), ("m²", "dm²", 100), ("dm²", "cm²", 100),
               ("cm²", "mm²", 100), ("m²", "cm²", 10000), ("ha", "m²", 10000), ("a", "m²", 100)]


def area_units(rng: random.Random) -> dict:
    """Changing area units: km² to mm², ha and a (answers in m² when a is involved).
    Down (multiply) or up (divide: a decimal answer)."""
    big, small, f = rng.choice(_AREA_PAIRS)
    up = rng.random() < 0.5 and big != "a"
    if not up:
        n = Fraction(rng.randint(1, 40), 10)
        value = n * f
        return {
            "type": "compute",
            "instruction": "Fes el canvi d'unitat de superfície.",
            "problem": f"Un terreny fa {_fmt_min_dec(n)} {big}. Quants {small} fa?",
            "expression": f"{_fmt_min_dec(n)} × {f}",
            "answer": f"{int(value)} {small}",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": (f"1 {big} = {f} {small}. Per tant {_fmt_min_dec(n)} {big} són "
                    f"{_fmt_min_dec(n)} × {f} = {int(value)} {small}."),
        }
    k = rng.randint(2, 999)
    m = k * (f // 100)
    value = Fraction(m, f)
    return {
        "type": "compute",
        "instruction": "Fes el canvi d'unitat de superfície (pot sortir un decimal).",
        "problem": f"Un terreny fa {m} {small}. Quants {big} fa?",
        "expression": f"{m} ÷ {f}",
        "answer": f"{_fmt_min_dec(value)} {big}",
        "also_accept": [],
        "options": [],
        "value": value,
        "why": (f"1 {big} = {f} {small}, així que {m} {small} = {m} ÷ {f} {big} = "
                f"{_fmt_min_dec(value)} {big}."),
    }


# (big unit, small unit, how many small units in one big one).
_VOL_PAIRS = [("m³", "dm³", 1000), ("dm³", "cm³", 1000), ("m³", "l", 1000), ("l", "ml", 1000)]


def volume_units(rng: random.Random) -> dict:
    """Volume and capacity units: m³, dm³, cm³, l and ml (down, or up with a decimal)."""
    big, small, f = rng.choice(_VOL_PAIRS)
    if rng.random() < 0.5:
        n = Fraction(rng.randint(1, 40), 10)
        value = n * f
        return {
            "type": "compute",
            "instruction": "Fes el canvi d'unitat de volum o de capacitat.",
            "problem": f"Un recipient té {_fmt_min_dec(n)} {big}. Quants {small} té?",
            "expression": f"{_fmt_min_dec(n)} × {f}",
            "answer": f"{int(value)} {small}",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": f"1 {big} = {f} {small}. {_fmt_min_dec(n)} × {f} = {int(value)} {small}.",
        }
    m = rng.randint(2, 4000)
    value = Fraction(m, f)
    return {
        "type": "compute",
        "instruction": "Fes el canvi d'unitat de volum o de capacitat (pot sortir un decimal).",
        "problem": f"Un recipient té {m} {small}. Quants {big} té?",
        "expression": f"{m} ÷ {f}",
        "answer": f"{_fmt_min_dec(value)} {big}",
        "also_accept": [],
        "options": [],
        "value": value,
        "why": (f"1 {big} = {f} {small}, així que {m} {small} = {m} ÷ {f} {big} = "
                f"{_fmt_min_dec(value)} {big}."),
    }


def areas_polygons(rng: random.Random) -> dict:
    """Area of a regular polygon (perimeter times apothem over two), of a rhombus
    (diagonals) and of a trapezium (bases and height)."""
    shape = rng.randrange(3)
    if shape == 0:
        n = rng.choice([5, 6, 8])
        s = rng.randint(2, 12)
        apo = Fraction(rng.randint(20, 90), 10)  # apothem 2,0 .. 9,0 cm
        perim = n * s
        value = Fraction(perim) * apo / 2
        return {
            "type": "compute",
            "instruction": "Calcula l'àrea del polígon regular amb la seva apotema.",
            "problem": (f"Un polígon regular de {n} costats mesura {s} cm de costat i té "
                        f"l'apotema de {_fmt_min_dec(apo)} cm. Quina és la seva àrea?"),
            "expression": f"{perim} × {_fmt_min_dec(apo)} ÷ 2",
            "answer": f"{_fmt_min_dec(value)} cm²",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": (f"El perímetre és {n} × {s} = {perim} cm. L'àrea del polígon regular és "
                    f"perímetre × apotema ÷ 2: {perim} × {_fmt_min_dec(apo)} ÷ 2 = "
                    f"{_fmt_min_dec(value)} cm²."),
        }
    if shape == 1:
        D = rng.randint(4, 20)
        d = rng.randint(4, 16)
        value = Fraction(D * d, 2)
        return {
            "type": "compute",
            "instruction": "Calcula l'àrea del rombe amb les diagonals.",
            "problem": f"Un rombe té les diagonals de {D} cm i {d} cm. Quina és la seva àrea?",
            "expression": f"{D} × {d} ÷ 2",
            "answer": f"{_fmt_min_dec(value)} cm²",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": (f"Àrea del rombe: diagonal major × diagonal menor ÷ 2 = {D} × {d} ÷ 2 = "
                    f"{_fmt_min_dec(value)} cm²."),
        }
    B = rng.randint(4, 20)
    b = rng.randint(2, B - 1)
    h = rng.randint(2, 12)
    value = Fraction((B + b) * h, 2)
    return {
        "type": "compute",
        "instruction": "Calcula l'àrea del trapezi amb les bases i l'altura.",
        "problem": (f"Un trapezi té les bases de {B} cm i {b} cm i l'altura de {h} cm. "
                    "Quina és la seva àrea?"),
        "expression": f"({B} + {b}) × {h} ÷ 2",
        "answer": f"{_fmt_min_dec(value)} cm²",
        "also_accept": [],
        "options": [],
        "value": value,
        "why": (f"Àrea del trapezi: (base gran + base petita) × altura ÷ 2 = "
                f"({B} + {b}) × {h} ÷ 2 = {_fmt_min_dec(value)} cm²."),
    }


def circle_measures(rng: random.Random) -> dict:
    """Circumference (from the radius or the diameter) and area of a circle, with π = 3,14."""
    shape = rng.randrange(3)
    r = rng.randint(2, 15)
    pi = Fraction(314, 100)
    if shape == 0:
        value = pi * 2 * r
        return {
            "type": "compute",
            "instruction": "Calcula la longitud de la circumferència (π = 3,14).",
            "problem": f"Un cercle té un radi de {r} cm. Quina és la longitud de la circumferència? (π = 3,14)",
            "expression": f"2 × 3,14 × {r}",
            "answer": f"{_fmt_min_dec(value)} cm",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": f"Circumferència = 2 × π × radi = 2 × 3,14 × {r} = {_fmt_min_dec(value)} cm.",
        }
    if shape == 1:
        value = pi * r * r
        return {
            "type": "compute",
            "instruction": "Calcula l'àrea del cercle (π = 3,14).",
            "problem": f"Un cercle té un radi de {r} cm. Quina és la seva àrea? (π = 3,14)",
            "expression": f"3,14 × {r} ^ 2",
            "answer": f"{_fmt_min_dec(value)} cm²",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": (f"Àrea = π × radi^2 = 3,14 × {r}^2 = 3,14 × {r * r} = "
                    f"{_fmt_min_dec(value)} cm²."),
        }
    d = 2 * r
    value = pi * d
    return {
        "type": "compute",
        "instruction": "Calcula la longitud de la circumferència a partir del diàmetre (π = 3,14).",
        "problem": f"Un cercle té un diàmetre de {d} cm. Quina és la longitud de la circumferència? (π = 3,14)",
        "expression": f"3,14 × {d}",
        "answer": f"{_fmt_min_dec(value)} cm",
        "also_accept": [],
        "options": [],
        "value": value,
        "why": f"Circumferència = π × diàmetre = 3,14 × {d} = {_fmt_min_dec(value)} cm.",
    }


def volumes_solids(rng: random.Random) -> dict:
    """Volume of a cuboid, of a cylinder (π = 3,14) and of a triangular prism."""
    shape = rng.randrange(3)
    if shape == 0:
        a, b, c = rng.randint(2, 12), rng.randint(2, 12), rng.randint(2, 12)
        value = Fraction(a * b * c)
        return {
            "type": "compute",
            "instruction": "Calcula el volum del prisma rectangular.",
            "problem": (f"Un prisma rectangular té les arestes de {a} cm, {b} cm i {c} cm. "
                        "Quin és el seu volum?"),
            "expression": f"{a} × {b} × {c}",
            "answer": f"{int(value)} cm³",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": f"Volum = llargada × amplada × alçada = {a} × {b} × {c} = {int(value)} cm³.",
        }
    if shape == 1:
        r, h = rng.randint(2, 10), rng.randint(2, 15)
        value = Fraction(314, 100) * r * r * h
        return {
            "type": "compute",
            "instruction": "Calcula el volum del cilindre (π = 3,14).",
            "problem": (f"Un cilindre té un radi de la base de {r} cm i una altura de {h} cm. "
                        "Quin és el seu volum? (π = 3,14)"),
            "expression": f"3,14 × {r} ^ 2 × {h}",
            "answer": f"{_fmt_min_dec(value)} cm³",
            "also_accept": [],
            "options": [],
            "value": value,
            "why": (f"Volum del cilindre = π × radi^2 × altura = 3,14 × {r}^2 × {h} = "
                    f"3,14 × {r * r} × {h} = {_fmt_min_dec(value)} cm³."),
        }
    b, hb = rng.randint(2, 12), rng.randint(2, 10)
    L = rng.randint(2, 12)
    base = Fraction(b * hb, 2)
    value = base * L
    return {
        "type": "compute",
        "instruction": "Calcula el volum del prisma de base triangular.",
        "problem": (f"Un prisma té una base triangular de {b} cm de base i {hb} cm d'altura, i "
                    f"una llargada de {L} cm. Quin és el seu volum?"),
        "expression": f"{b} × {hb} ÷ 2 × {L}",
        "answer": f"{_fmt_min_dec(value)} cm³",
        "also_accept": [],
        "options": [],
        "value": value,
        "why": (f"Àrea de la base = {b} × {hb} ÷ 2 = {_fmt_min_dec(base)} cm²; volum = àrea de "
                f"la base × llargada = {_fmt_min_dec(base)} × {L} = {_fmt_min_dec(value)} cm³."),
    }


def sexagesimal_ops_easy(rng: random.Random) -> dict:
    """Times and angles in hours (or degrees) and minutes, in the easy range of m6: the sum
    of two durations or two angles, minutes multiples of five. The answer is in minutes."""
    shape = rng.randrange(2)
    h1, m1 = rng.randint(0, 2), rng.randrange(0, 60, 5)
    h2, m2 = rng.randint(0, 2), rng.randrange(0, 60, 5)
    total = (h1 * 60 + m1) + (h2 * 60 + m2)
    if shape == 0:
        problem = (f"Una classe de matemàtiques dura {h1} h {m1} min i una de música {h2} h "
                   f"{m2} min. Quants minuts duren les dues juntes?")
        unit_word = "hores i minuts"
    else:
        problem = (f"Un angle mesura {h1} graus i {m1} minuts, i un altre {h2} graus i "
                   f"{m2} minuts. Quants minuts sumen els dos angles?")
        unit_word = "graus i minuts"
    return {
        "type": "compute",
        "instruction": f"Passa cada quantitat ({unit_word}) a minuts i suma-les (1 hora o 1 grau = 60 minuts).",
        "problem": problem,
        "expression": f"({h1} × 60 + {m1}) + ({h2} × 60 + {m2})",
        "answer": f"{total} min",
        "also_accept": [],
        "options": [],
        "value": Fraction(total),
        "why": (f"Cada quantitat en minuts (1 hora o 1 grau = 60 minuts): {h1 * 60 + m1} i "
                f"{h2 * 60 + m2}; la suma és {total} min."),
    }


M6_FAMILIES = {
    "powers_value": powers_value,
    "integers_context": integers_context,
    "frac_ops4": frac_ops4,
    "dec_division": dec_division,
    "percent_change": percent_change,
    "scales": scales,
    "area_units": area_units,
    "volume_units": volume_units,
    "areas_polygons": areas_polygons,
    "circle_measures": circle_measures,
    "volumes_solids": volumes_solids,
    "sexagesimal_ops_easy": sexagesimal_ops_easy,
}


FAMILIES = {
    "mult_2digit": mult_2digit,
    "frac_add_unlike": frac_add_unlike,
    "dec_add": dec_add,
    "compare_fracs": compare_fracs,
    "word_problems": word_problems,
    "syntax_grouping_letters": syntax_grouping_letters,
    "value_numeric": value_numeric,
    "distributive_letters": distributive_letters,
    "factor_letters": factor_letters,
    # m5 (E2)
    "mult_3digit": mult_3digit,
    "div_2digit": div_2digit,
    "combined_ops": combined_ops,
    "frac_same_den": frac_same_den,
    "frac_of_quantity": frac_of_quantity,
    "dec_ops": dec_ops,
    "percent_basic": percent_basic,
    "smd_convert": smd_convert,
    "time_intervals": time_intervals,
    "area_perimeter": area_perimeter,
    "mean_mode_range": mean_mode_range,
    "probability_simple": probability_simple,
    "equations_simple": equations_simple,
    "word_problems_multistep": word_problems_multistep,
    # m7 (E6)
    **M7_FAMILIES,
    # m6 (E8)
    **M6_FAMILIES,
}

# Fallback when the curriculum .md has no `Bank:` line (the pilot ids).
DEFAULT_FAMILY_BY_ID = {
    "m4.mult_2digit": "mult_2digit",
    "m4.frac_add_unlike": "frac_add_unlike",
    "m4.dec_add": "dec_add",
    "m4.compare_fracs": "compare_fracs",
    "m4.word_problems": "word_problems",
}


# ------------------------------------------------------- steps families (WP2.1) ---
# §4.2: a `steps` item is a worked solution — the FULL expected trace. Each
# family returns a dict with keys:
#   type ("steps"), instruction, problem, method, answer, value (Fraction),
#   why, steps: [{n, expect, value, accept, error_class, why}, ...]
# `expect` is the FORM the method demands (grade_step form-matches it);
# `value` is the step's exact value as a canonical string; `accept` lists
# alternative lines for that step (bare expression or "lhs = rhs").
# `error_class` is the class of slip expected AT that step — the taxonomy
# (db_schema.ERROR_CATEGORIES) that becomes the mistake pattern id in §4.2.

STEPS_INSTRUCTION = "Resol-ho pas a pas. Una línia per pas."


def partial_products(rng: random.Random) -> dict:
    """2x2 multiplication by partial products: split the second factor into
    tens + units, two multiplications, one summing step."""
    for _ in range(500):
        a = rng.randint(12, 99)
        b = rng.randint(11, 99)
        if b % 10:  # a units digit, or the split is one trivial step
            break
    else:
        raise GenError("partial_products: no 2x2 pair with a units digit in 500 draws")
    bt, bu = (b // 10) * 10, b % 10
    v1, v2, tot = a * bt, a * bu, a * b
    return {
        "type": "steps",
        "method": "partial_products",
        "instruction": STEPS_INSTRUCTION,
        "problem": f"{a} × {b}",
        "answer": str(tot),
        "value": Fraction(tot),
        "steps": [
            {"n": 1, "expect": f"{a} × {bt}", "value": str(v1),
             "accept": [f"{a} * {bt}", f"{a} × {bt} = {v1}"],
             "error_class": "procedure",
             "why": f"Separa {b} en {bt} + {bu} i multiplica {a} × {bt}."},
            {"n": 2, "expect": f"{a} × {bu}", "value": str(v2),
             "accept": [f"{a} * {bu}", f"{a} × {bu} = {v2}"],
             "error_class": "calculation",
             "why": f"Ara les unitats: {a} × {bu}."},
            {"n": 3, "expect": f"{v1} + {v2}", "value": str(tot),
             "accept": [f"{v1} + {v2} = {tot}"],
             "error_class": "carrying",
             "why": "Suma els dos productes parcials."},
        ],
        "why": (f"{b} = {bt} + {bu}: {a} × {bt} = {v1} i {a} × {bu} = {v2}; "
                f"{v1} + {v2} = {tot}."),
    }


def partial_sums(rng: random.Random) -> dict:
    """2-digit addition with carrying, decomposed: tens, units, combine.
    The units column is required to carry (that is what the method teaches)."""
    for _ in range(500):
        a = rng.randint(13, 89)
        b = rng.randint(13, 89)
        if a % 10 + b % 10 >= 10 and a + b < 100:
            break
    else:
        raise GenError("partial_sums: no carrying pair under 100 in 500 draws")
    at, au = (a // 10) * 10, a % 10
    bt, bu = (b // 10) * 10, b % 10
    tens, units, tot = at + bt, au + bu, a + b
    return {
        "type": "steps",
        "method": "partial_sums",
        "instruction": STEPS_INSTRUCTION,
        "problem": f"{a} + {b}",
        "answer": str(tot),
        "value": Fraction(tot),
        "steps": [
            {"n": 1, "expect": f"{at} + {bt}", "value": str(tens),
             "accept": [f"{at} + {bt} = {tens}"],
             "error_class": "procedure",
             "why": f"Separa desenes i unitats: {a} = {at} + {au}, {b} = {bt} + {bu}."},
            {"n": 2, "expect": f"{au} + {bu}", "value": str(units),
             "accept": [f"{au} + {bu} = {units}"],
             "error_class": "carrying",
             "why": f"Suma les unitats: {au} + {bu} = {units}, que passa de 9 (transport)."},
            {"n": 3, "expect": f"{tens} + {units}", "value": str(tot),
             "accept": [f"{tens} + {units} = {tot}"],
             "error_class": "carrying",
             "why": "Ajunta les desenes amb les unitats."},
        ],
        "why": (f"{a} + {b}: desenes {at} + {bt} = {tens}, unitats {au} + {bu} = {units}; "
                f"{tens} + {units} = {tot}."),
    }


def common_denominator(rng: random.Random) -> dict:
    """Sum of unlike-denominator fractions as a trace: rewrite both over the
    common denominator, add numerators, and (when reducible) a third
    simplification step. Same draw rules as the compute family frac_add_unlike."""
    want_reducible = rng.random() < 0.5
    for _ in range(2000):
        d1 = rng.randint(2, 12)
        d2 = rng.randint(2, 12)
        if d1 == d2:
            continue
        if d1 > d2:
            d1, d2 = d2, d1
        n1 = rng.randint(1, d1 - 1)
        n2 = rng.randint(1, d2 - 1)
        L = _lcm(d1, d2)
        num = n1 * (L // d1) + n2 * (L // d2)
        if (math.gcd(num, L) > 1) != want_reducible:
            continue
        break
    else:
        raise GenError(f"common_denominator: no pair with reducible={want_reducible} in 2000 draws")
    s = Fraction(n1, d1) + Fraction(n2, d2)
    a1, a2 = n1 * (L // d1), n2 * (L // d2)
    g = math.gcd(num, L)
    steps = [
        {"n": 1, "expect": f"{a1}/{L} + {a2}/{L}", "value": _fmt_frac(s),
         "accept": [f"{a1}/{L}+{a2}/{L}", f"{a1}/{L} + {a2}/{L} = {_fmt_frac(s)}"],
         "error_class": "procedure",
         "why": f"Escriu {n1}/{d1} com a {a1}/{L} i {n2}/{d2} com a {a2}/{L} "
                f"(denominador comú {L})."},
        {"n": 2, "expect": f"{num}/{L}", "value": _fmt_frac(Fraction(num, L)),
         "accept": [f"{num}/{L} = {_fmt_frac(Fraction(num, L))}"],
         "error_class": "calculation",
         "why": "Suma els numeradors; el denominador no canvia."},
    ]
    why = (f"Denominador comú {L}: {n1}/{d1} = {a1}/{L} i {n2}/{d2} = {a2}/{L}; "
           f"suma els numeradors ({a1} + {a2} = {num}).")
    if g > 1:
        steps.append(
            {"n": 3, "expect": _fmt_frac(s), "value": _fmt_frac(s),
             "accept": [],
             "error_class": "simplification",
             "why": f"Simplifica {num}/{L} dividint numerador i denominador per {g}."})
        why += f" Simplifica {num}/{L} dividint per {g}."
    return {
        "type": "steps",
        "method": "common_denominator",
        "instruction": STEPS_INSTRUCTION,
        "problem": f"{n1}/{d1} + {n2}/{d2}",
        "answer": _fmt_frac(s),
        "value": s,
        "steps": steps,
        "why": why,
    }


def long_division(rng: random.Random) -> dict:
    """2÷1 division WITH remainder: biggest multiple not exceeding the
    dividend, the subtraction that leaves the remainder, and the result
    written as a mixed number (quotient + remainder/divisor) so the answer
    is the exact value of the problem."""
    for _ in range(500):
        a = rng.randint(12, 99)
        b = rng.randint(2, 9)
        q, r = divmod(a, b)
        if r and q >= 2 and math.gcd(r, b) == 1:
            break
    else:
        raise GenError("long_division: no 2x1 pair with a reduced remainder in 500 draws")
    m = b * q
    return {
        "type": "steps",
        "method": "long_division",
        "instruction": STEPS_INSTRUCTION,
        "problem": f"{a} ÷ {b}",
        "answer": _fmt_frac(Fraction(a, b)),
        "value": Fraction(a, b),
        "steps": [
            {"n": 1, "expect": f"{b} × {q}", "value": str(m),
             "accept": [f"{b} * {q}", f"{b} × {q} = {m}"],
             "error_class": "facts",
             "why": f"El múltiple de {b} més gran que no sobrepassi {a}: {b} × {q} = {m}."},
            {"n": 2, "expect": f"{a} - {m}", "value": str(r),
             "accept": [f"{a} - {m} = {r}"],
             "error_class": "calculation",
             "why": f"Resta'l a {a}: el que en sobra ({r}) és el residu."},
            {"n": 3, "expect": f"{q} {r}/{b}", "value": _fmt_frac(Fraction(a, b)),
             "accept": [f"{a}/{b}"],
             "error_class": "procedure",
             "why": f"Quocient {q} i residu {r}: {a} ÷ {b} = {q} {r}/{b}."},
        ],
        "why": (f"{b} × {q} = {m} és el múltiple de {b} que més s'acosta a {a} sense "
                f"sobrepassar-lo; {a} - {m} = {r} és el residu: {a} ÷ {b} = {q} {r}/{b}."),
    }


# --------------------------------------- m7 smart calculation (WP1.1) ---
# BLOC 1 of docs/AlgebraNumericaBasica.md ("El Joc dels Nombres"): the trace
# IS the method — regroup / deploy / extract, then the easy arithmetic. The
# first step's `expect` demands the transformed FORM (the regrouped pair, the
# deployed packet, the factored one); the later steps are the arithmetic that
# the transformation made trivial.

def props_grouping_numeric(rng: random.Random) -> dict:
    """Commutative + associative: find the pair that makes 10/20/…/100 and
    group it first. '13 + 25 + 7 -> (13 + 7) + 25 -> 20 + 25 -> 45' and the
    multiplication version '4 · 17 · 25 -> (4 · 25) · 17 -> 100 · 17 -> 1700'."""
    if rng.random() < 0.5:
        s = rng.choice([10, 20, 30, 40, 50])
        p = rng.randint(2, s - 2)
        q = s - p
        if p == q:
            p, q = p - 1, q + 1
        r = rng.randint(3, 40)
        total = s + r
        return {
            "type": "steps",
            "method": "grouping",
            "instruction": STEPS_INSTRUCTION,
            "problem": f"{p} + {r} + {q}",
            "answer": str(total),
            "value": Fraction(total),
            "steps": [
                {"n": 1, "expect": f"({p} + {q}) + {r}", "value": str(total),
                 "accept": [f"({p} + {q}) + {r} = {total}"],
                 "error_class": "procedure",
                 "why": f"{p} i {q} sumen {s}: agrupa'ls primer."},
                {"n": 2, "expect": f"{s} + {r}", "value": str(total),
                 "accept": [f"{s} + {r} = {total}"],
                 "error_class": "calculation",
                 "why": f"{p} + {q} = {s}."},
                {"n": 3, "expect": str(total), "value": str(total),
                 "accept": [],
                 "error_class": "calculation",
                 "why": f"{s} + {r} = {total}."},
            ],
            "why": (f"{p} + {q} = {s} (parella rodona), i {s} + {r} = {total}: "
                    "moure els sumands no canvia el resultat."),
        }
    pairs = [(2, 5, 10), (4, 25, 100), (2, 25, 50), (4, 5, 20), (8, 25, 200), (2, 50, 100)]
    p, q, prod = rng.choice(pairs)
    r = rng.randint(3, 40)
    total = prod * r
    return {
        "type": "steps",
        "method": "grouping",
        "instruction": STEPS_INSTRUCTION,
        "problem": f"{p} × {r} × {q}",
        "answer": str(total),
        "value": Fraction(total),
        "steps": [
            {"n": 1, "expect": f"({p} × {q}) × {r}", "value": str(total),
             "accept": [f"({p} × {q}) × {r} = {total}"],
             "error_class": "procedure",
             "why": f"{p} × {q} fa {prod}: agrupa-los primer."},
            {"n": 2, "expect": f"{prod} × {r}", "value": str(total),
             "accept": [f"{prod} × {r} = {total}"],
             "error_class": "facts",
             "why": f"{p} × {q} = {prod}."},
            {"n": 3, "expect": str(total), "value": str(total),
             "accept": [],
             "error_class": "calculation",
             "why": f"{prod} × {r} = {total}."},
        ],
        "why": (f"{p} × {q} = {prod} (producte rodó), i {prod} × {r} = {total}: "
                "reagrupar els factors no canvia el resultat."),
    }


def props_distributive_numeric(rng: random.Random) -> dict:
    """Distributive with numbers: break the hard factor into an easy pair.
    '5 · (10 + 3) -> 5 · 10 + 5 · 3 -> 50 + 15 -> 65'."""
    k = rng.randint(3, 9)
    a = rng.choice([10, 20, 30, 40, 50])
    b = rng.randint(2, 9)
    minus = rng.random() < 0.4
    total = k * (a - b) if minus else k * (a + b)
    op = "-" if minus else "+"
    return {
        "type": "steps",
        "method": "distributive",
        "instruction": STEPS_INSTRUCTION,
        "problem": f"{k} × ({a} {op} {b})",
        "answer": str(total),
        "value": Fraction(total),
        "steps": [
            {"n": 1, "expect": f"{k} × {a} {op} {k} × {b}", "value": str(total),
             "accept": [f"{k} × {a} {op} {k} × {b} = {total}"],
             "error_class": "procedure",
             "why": f"El {k} de fora multiplica els dos termes del parèntesi."},
            {"n": 2, "expect": f"{k * a} {op} {k * b}", "value": str(total),
             "accept": [f"{k * a} {op} {k * b} = {total}"],
             "error_class": "facts",
             "why": f"{k} × {a} = {k * a} i {k} × {b} = {k * b}."},
            {"n": 3, "expect": str(total), "value": str(total),
             "accept": [],
             "error_class": "calculation",
             "why": f"{k * a} {op} {k * b} = {total}."},
        ],
        "why": (f"{a} {op} {b} es trenca en dues multiplicacions fàcils: "
                f"{k} × {a} = {k * a} i {k} × {b} = {k * b}; {k * a} {op} {k * b} = {total}."),
    }


def props_factor_numeric(rng: random.Random) -> dict:
    """Common factor with numbers: the same multiplier in both products comes
    out. '7 · 8 + 7 · 2 -> 7 · (8 + 2) -> 7 · 10 -> 70'."""
    k = rng.randint(3, 9)
    a = rng.randint(2, 12)
    b = rng.randint(2, 12)
    if a == b:
        b = a + 1
    minus = rng.random() < 0.4
    c = a - b if minus else a + b
    if c <= 0:
        a, b = b, a
        c = a - b
    total = k * c
    op = "-" if minus else "+"
    return {
        "type": "steps",
        "method": "common_factor",
        "instruction": STEPS_INSTRUCTION,
        "problem": f"{k} × {a} {op} {k} × {b}",
        "answer": str(total),
        "value": Fraction(total),
        "steps": [
            {"n": 1, "expect": f"{k} × ({a} {op} {b})", "value": str(total),
             "accept": [f"{k} × ({a} {op} {b}) = {total}"],
             "error_class": "procedure",
             "why": f"El {k} es repeteix als dos productes: treu-lo fora."},
            {"n": 2, "expect": f"{k} × {c}", "value": str(total),
             "accept": [f"{k} × {c} = {total}"],
             "error_class": "calculation",
             "why": f"{a} {op} {b} = {c}."},
            {"n": 3, "expect": str(total), "value": str(total),
             "accept": [],
             "error_class": "facts",
             "why": f"{k} × {c} = {total}."},
        ],
        "why": (f"El factor comú {k} queda fora: {k} × ({a} {op} {b}) = {k} × {c} = {total} "
                "— estalvies dues multiplicacions."),
    }


def partial_products_3(rng: random.Random) -> dict:
    """3-digit x 2-digit by partial products (the m5 steps of m5.mult_3digit): split the
    2-digit factor into tens + units, two multiplications, one summing step."""
    for _ in range(500):
        a = rng.randint(100, 999)
        b = rng.randint(11, 99)
        if b % 10:  # a units digit, or the split is one trivial step
            break
    else:
        raise GenError("partial_products_3: no pair with a units digit in 500 draws")
    bt, bu = (b // 10) * 10, b % 10
    v1, v2, tot = a * bt, a * bu, a * b
    return {
        "type": "steps",
        "method": "partial_products",  # the same trace as the 2x2 family: same goals
        "instruction": STEPS_INSTRUCTION,
        "problem": f"{a} × {b}",
        "answer": str(tot),
        "value": Fraction(tot),
        "steps": [
            {"n": 1, "expect": f"{a} × {bt}", "value": str(v1),
             "accept": [f"{a} * {bt}", f"{a} × {bt} = {v1}"],
             "error_class": "procedure",
             "why": f"Separa {b} en {bt} + {bu} i multiplica {a} × {bt}."},
            {"n": 2, "expect": f"{a} × {bu}", "value": str(v2),
             "accept": [f"{a} * {bu}", f"{a} × {bu} = {v2}"],
             "error_class": "calculation",
             "why": f"Ara les unitats: {a} × {bu}."},
            {"n": 3, "expect": f"{v1} + {v2}", "value": str(tot),
             "accept": [f"{v1} + {v2} = {tot}"],
             "error_class": "carrying",
             "why": "Suma els dos productes parcials."},
        ],
        "why": (f"{b} = {bt} + {bu}: {a} × {bt} = {v1} i {a} × {bu} = {v2}; "
                f"{v1} + {v2} = {tot}."),
    }


def long_division_2(rng: random.Random) -> dict:
    """Exact division by a 2-digit divisor as a trace: the multiple for the tens of the
    quotient, the subtraction, the units of the quotient, and the sum of the two parts.
    The dividend is built as divisor x quotient, so the division is exact."""
    for _ in range(500):
        d = rng.randint(11, 99)
        q = rng.randint(11, 99)
        if q % 10:  # a units digit: the trace has a real units step
            break
    else:
        raise GenError("long_division_2: no divisor/quotient pair in 500 draws")
    a = d * q
    qt0, qu = (q // 10) * 10, q % 10
    p1 = d * qt0
    r1 = d * qu  # = a - p1
    return {
        "type": "steps",
        "method": "long_division_2",
        "instruction": STEPS_INSTRUCTION,
        "problem": f"{a} ÷ {d}",
        "answer": str(q),
        "value": Fraction(q),
        "steps": [
            {"n": 1, "expect": f"{d} × {qt0}", "value": str(p1),
             "accept": [f"{d} * {qt0}", f"{d} × {qt0} = {p1}"],
             "error_class": "facts",
             "why": f"Les desenes del quocient són {qt0}: {d} × {qt0} = {p1}, el múltiple de {d} que no passa de {a}."},
            {"n": 2, "expect": f"{a} - {p1}", "value": str(r1),
             "accept": [f"{a} - {p1} = {r1}"],
             "error_class": "calculation",
             "why": f"Resta: {a} − {p1} = {r1}; és el que queda per repartir."},
            {"n": 3, "expect": f"{r1} ÷ {d}", "value": str(qu),
             "accept": [f"{r1} / {d} = {qu}", f"{r1} ÷ {d} = {qu}"],
             "error_class": "facts",
             "why": f"Les unitats del quocient: {r1} ÷ {d} = {qu}."},
            {"n": 4, "expect": f"{qt0} + {qu}", "value": str(q),
             "accept": [f"{qt0} + {qu} = {q}"],
             "error_class": "calculation",
             "why": f"Ajunta les desenes i les unitats del quocient: {qt0} + {qu} = {q}."},
        ],
        "why": (f"{d} × {q} = {a}: el quocient és {qt0} + {qu} = {q}, i la divisió és exacta."),
    }


STEPS_FAMILIES = {
    "partial_products": partial_products,
    "partial_sums": partial_sums,
    "common_denominator": common_denominator,
    "long_division": long_division,
    "props_grouping_numeric": props_grouping_numeric,
    "props_distributive_numeric": props_distributive_numeric,
    "props_factor_numeric": props_factor_numeric,
    # m5 (E2)
    "partial_products_3": partial_products_3,
    "long_division_2": long_division_2,
}


# ------------------------------------------------------------- curriculum ---

_BANK_LINE = re.compile(r"^Bank:\s*(\S+)\s*$")
_HEAD = re.compile(r"^###\s+(\S+)\s+—")


def bank_family_for(curriculum_path: Path, competence_id: str) -> str:
    """The `Bank:` line of a competence, else the pilot fallback map, else error."""
    text = Path(curriculum_path).read_text(encoding="utf-8")
    in_comp = False
    for line in text.splitlines():
        m = _HEAD.match(line)
        if m:
            in_comp = m.group(1) == competence_id
            continue
        if in_comp:
            b = _BANK_LINE.match(line.strip())
            if b:
                return b.group(1)
    if competence_id in DEFAULT_FAMILY_BY_ID:
        return DEFAULT_FAMILY_BY_ID[competence_id]
    raise GenError(
        f"{competence_id}: no `Bank:` line in {curriculum_path.name} and no fallback. "
        f"Add a line like `Bank: mult_2digit` under the competence heading "
        f"(families: {', '.join(sorted(FAMILIES))}).")


def competence_exists(curriculum_path: Path, competence_id: str) -> bool:
    text = Path(curriculum_path).read_text(encoding="utf-8")
    return any((m := _HEAD.match(l)) and m.group(1) == competence_id
               for l in text.splitlines())


# ------------------------------------------------------------ validation ---

REQUIRED_FIELDS = ("id", "competence", "type", "instruction", "problem", "answer",
                   "also_accept", "options", "why", "status", "source")
ITEM_TYPES = ("compute", "choose", "compare", "steps")
_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+\.\d{3,}$")

STEPS_REQUIRED_FIELDS = ("id", "competence", "type", "instruction", "problem",
                         "method", "steps", "answer", "why", "status", "source")
STEP_REQUIRED_KEYS = ("n", "expect", "value", "accept", "error_class", "why", "goal")

# What to do at each step, per method (2026-10-08, Albert): the learner sees
# it BEFORE writing the step, so it names the property/technique and never the
# result. Keyed by (method, n); a "last" entry covers the final step.
STEP_GOALS: dict[str, dict] = {
    "partial_sums": {1: "Suma només les desenes (descompon cada nombre en desenes + unitats)",
                     2: "Suma només les unitats",
                     "last": "Ajunta la suma de les desenes amb la de les unitats"},
    "partial_products": {1: "Descompon el segon factor en desenes + unitats i multiplica el primer factor per les desenes",
                         2: "Multiplica el primer factor per les unitats",
                         "last": "Suma els dos productes parcials"},
    "long_division": {1: "Busca el múltiple del divisor més gran que no passi del dividend (escriu la multiplicació)",
                      2: "Resta aquest múltiple al dividend per trobar el residu",
                      "last": "Escriu el resultat: quocient i residu com a nombre mixt"},
    "common_denominator": {1: "Passa les dues fraccions a un denominador comú i escriu-ne la suma",
                           2: "Suma els numeradors (el denominador no canvia)",
                           "last": "Simplifica la fracció (nombre mixt si cal)"},
    "distributive": {1: "Propietat distributiva: multiplica el factor de fora per cada terme del parèntesi (escriu les dues multiplicacions)",
                     2: "Calcula cada multiplicació i escriu la suma o resta dels resultats",
                     "last": "Calcula el resultat final"},
    "common_factor": {1: "Factor comú: treu fora el nombre que es repeteix i escriu la suma o resta entre parèntesis",
                      2: "Calcula el parèntesi i escriu la multiplicació que en queda",
                      "last": "Calcula el resultat final"},
    "grouping": {1: "Propietat associativa i commutativa: agrupa primer els dos nombres que fan un resultat rodó (escriu-ho amb parèntesis)",
                 2: "Calcula el parèntesi i escriu l'operació que en queda",
                 "last": "Calcula el resultat final"},
    "long_division_2": {1: "Busca el múltiple del divisor per les desenes del quocient (escriu la multiplicació)",
                        2: "Resta aquest múltiple al dividend: el que queda s'ha de repartir",
                        3: "Divideix el que queda pel divisor per trobar les unitats del quocient",
                        "last": "Ajunta les desenes i les unitats del quocient"},
}


def default_goal(method: str, n: int, total: int) -> str | None:
    """The method's stock goal for step `n` of `total`, or None (unknown
    method: a hand-written item must carry its own goals)."""
    tbl = STEP_GOALS.get(method)
    if not tbl:
        return None
    if n == total and n > 1:
        return tbl["last"]
    return tbl.get(n) or tbl["last"]


def fill_goals(item: dict) -> dict:
    """Give every step of a steps item a `goal` it lacks (never overwrites)."""
    steps = item.get("steps", [])
    for st in steps:
        if not str(st.get("goal", "")).strip():
            g = default_goal(item.get("method", ""), st.get("n", 0), len(steps))
            if g:
                st["goal"] = g
    return item


def _accept_ok(acc, want: Fraction | None) -> bool:
    """An `accept` entry is an alternative line for a step: a bare expression
    or "lhs = rhs" (grade_step splits on the LAST '='). Every side must parse
    and equal the step's value — an accept that means something else is a
    template bug, not a learner variant."""
    if want is None:
        return False
    t = str(acc)
    if t.count("=") > 1:
        return False
    sides = t.rsplit("=", 1) if "=" in t else [t]
    for s in sides:
        try:
            if mathgrade.parse_expr(s).value != want:
                return False
        except mathgrade.ParseError:
            return False
    return True


def _validate_steps_item(item: dict) -> list[str]:
    """Invariants of a §4.2 steps item. Since WP2.3 (the per-line grader in
    hooks/bank.py) the status rule is the compute one: validated/reviewed —
    "generated" now means "not fit to serve", and validate refuses it."""
    errs: list[str] = []
    for f in STEPS_REQUIRED_FIELDS:
        if f not in item:
            errs.append(f"missing field {f!r}")
    if errs:
        return errs
    if item["status"] not in ("validated", "reviewed"):
        errs.append(f"steps status {item['status']!r} not validated/reviewed "
                    "(WP2.3 wired the steps grader; generated items are not served)")
    if not _ID_RE.match(item["id"]):
        errs.append(f"bad id {item['id']!r}")
    if not item["id"].startswith(item["competence"] + "."):
        errs.append(f"id {item['id']!r} does not start with competence {item['competence']!r}")
    steps = item["steps"]
    if not isinstance(steps, list) or not steps:
        errs.append("steps must be a non-empty list")
        return errs
    last_val: Fraction | None = None
    for i, st in enumerate(steps):
        tag = f"step {i + 1}"
        if not isinstance(st, dict):
            errs.append(f"{tag}: not an object")
            continue
        for k in STEP_REQUIRED_KEYS:
            if k not in st:
                errs.append(f"{tag}: missing {k!r}")
        if st.get("n") != i + 1:
            errs.append(f"{tag}: n is {st.get('n')!r}, expected {i + 1}")
        if st.get("error_class") not in db_schema.ERROR_CATEGORIES:
            errs.append(f"{tag}: error_class {st.get('error_class')!r} is not one of "
                        f"the §4.4 taxonomy {db_schema.ERROR_CATEGORIES}")
        if not str(st.get("why", "")).strip():
            errs.append(f"{tag}: empty why")
        if not str(st.get("goal", "")).strip():
            errs.append(f"{tag}: empty goal (what to do / which property — the learner sees it)")
        elif re.search(r"\d+\s*[=×x*+\-]\s*\d+", str(st["goal"])):
            errs.append(f"{tag}: goal must not contain a computation (it would give the step away)")
        ev = vv = None
        try:
            ev = mathgrade.parse_expr(st.get("expect")).value
        except mathgrade.ParseError as e:
            errs.append(f"{tag}: expect {st.get('expect')!r} does not parse: {e}")
        try:
            vv = mathgrade.parse_expr(st.get("value")).value
        except mathgrade.ParseError as e:
            errs.append(f"{tag}: value {st.get('value')!r} does not parse: {e}")
        if ev is not None and vv is not None and ev != vv:
            errs.append(f"{tag}: expect {st.get('expect')!r} -> {ev} != value {vv}")
        for acc in st.get("accept", []):
            if not _accept_ok(acc, vv):
                errs.append(f"{tag}: accept {acc!r} is not an alternative line "
                            f"for value {st.get('value')!r}")
        if vv is not None:
            last_val = vv
    try:
        aval = mathgrade.parse_expr(item["answer"]).value
    except mathgrade.ParseError as e:
        errs.append(f"answer does not parse: {e}")
        aval = None
    # A steps item with a story statement (m7.problems_generic, 2026-10-08)
    # carries its expression apart, like the WP3.2 word problems.
    try:
        pval = mathgrade.parse_expr(item.get("expression") or item["problem"]).value
    except mathgrade.ParseError as e:
        errs.append(f"problem does not parse: {e}")
        pval = None
    if aval is not None and pval is not None and pval != aval:
        errs.append(f"answer value {aval} != problem value {pval}")
    if aval is not None and last_val is not None and last_val != aval:
        errs.append(f"last step value {last_val} != answer value {aval}")
    return errs


def validate_item(item: dict) -> list[str]:
    """Every invariant an item must satisfy before it may be written. Returns
    a list of problems (empty = good). Never trusts the template."""
    if item.get("type") == "steps":
        return _validate_steps_item(item)
    errs: list[str] = []
    for f in REQUIRED_FIELDS:
        if f not in item:
            errs.append(f"missing field {f!r}")
    if errs:
        return errs
    if item["status"] not in ("validated", "reviewed"):
        errs.append(f"status {item['status']!r} not validated/reviewed")
    if item["type"] not in ITEM_TYPES:
        errs.append(f"type {item['type']!r} not in {ITEM_TYPES}")
    if not _ID_RE.match(item["id"]):
        errs.append(f"bad id {item['id']!r}")
    if not item["id"].startswith(item["competence"] + "."):
        errs.append(f"id {item['id']!r} does not start with competence {item['competence']!r}")
    for a in item["also_accept"]:
        try:
            mathgrade.parse_expr(a)
        except mathgrade.ParseError:
            try:  # WP1.1: an algebra item's variants are expressions, not values
                mathgrade.parse_poly(a)
            except mathgrade.ParseError as e:
                errs.append(f"also_accept {a!r} does not parse: {e}")

    if item["type"] == "compare":
        sides = item["problem"].split("?")
        if len(sides) != 2:
            errs.append(f"compare problem needs exactly one '?': {item['problem']!r}")
            return errs
        try:
            v1 = mathgrade.parse_expr(sides[0]).value
            v2 = mathgrade.parse_expr(sides[1]).value
        except mathgrade.ParseError as e:
            errs.append(f"compare side does not parse: {e}")
            return errs
        truth = "=" if v1 == v2 else (">" if v1 > v2 else "<")
        if item["answer"] != truth:
            errs.append(f"answer {item['answer']!r} contradicts the problem "
                        f"({v1} vs {v2} -> {truth!r})")
        if item["answer"] not in item["options"]:
            errs.append(f"answer {item['answer']!r} not in options {item['options']!r}")
        if set(item["options"]) != {">", "<", "="}:
            errs.append(f"compare options must be exactly >,<,=; got {item['options']!r}")
        return errs

    # WP1.1 algebra items: the answer is an EXPRESSION (it carries letters).
    # The two-path check is not "same value" but POLYNOMIAL EQUIVALENCE —
    # problem and answer must share the canonical form of the very normalizer
    # that will grade the learner (hooks/mathgrade.py parse_poly).
    if _ALG_LETTERS.search(str(item["answer"])) and not _is_unit_answer(item["answer"]):
        prob_src = item.get("expression") or item["problem"]
        try:
            ppoly = mathgrade.parse_poly(prob_src)
        except mathgrade.ParseError as e:
            errs.append(f"problem {prob_src!r} does not parse as an expression: {e}")
            ppoly = None
        try:
            apoly = mathgrade.parse_poly(item["answer"])
        except mathgrade.ParseError as e:
            errs.append(f"answer {item['answer']!r} does not parse as an expression: {e}")
            apoly = None
        if ppoly is not None and apoly is not None and ppoly != apoly:
            errs.append(f"answer {mathgrade.poly_form(apoly)!r} is not equivalent to "
                        f"the problem {mathgrade.poly_form(ppoly)!r}")
        if apoly is not None:
            for a in item["also_accept"]:
                try:
                    if mathgrade.parse_poly(a) != apoly:
                        errs.append(f"also_accept {a!r} is not equivalent to the answer")
                except mathgrade.ParseError:
                    pass  # already reported by the parse loop above
        return errs

    # m7 (E6): a linear equation 'lhs = rhs' in one letter, numeric answer: the answer
    # must solve it (both sides equal after substitution).
    if ("=" in str(item["problem"]) and _ALG_LETTERS.search(str(item["problem"]))
            and not item.get("expression")):  # a story with a formula has an expression
        return errs + _solves_equation(item)
    # compute / choose: the problem must parse, and its value must equal the
    # answer's value — the same evaluator that will grade the learner.
    # WP3.2 exception: a WORD PROBLEM's `problem` is a story, not an
    # expression; its arithmetic lives in `expression`, and that is what must
    # equal the answer. The story then has to contain every number the
    # expression uses (>= 2: the "1" of "1 - 2/5" is the whole pizza, which the
    # story names in words) — otherwise statement and answer are two different
    # problems and the item is a template bug.
    prob_src = item.get("expression") or item["problem"]
    if item.get("expression"):
        try:
            mathgrade.parse_expr(item["expression"])
        except mathgrade.ParseError as e:
            errs.append(f"expression {item['expression']!r} does not parse: {e}")
        text = f"{item['problem']} {item.get('why', '')}"
        for num in re.findall(r"\d+", str(item["expression"])):
            if int(num) >= 2 and not re.search(rf"(?<!\d){num}(?!\d)", text):
                errs.append(f"expression uses {num} but neither the story nor the why says it: "
                            f"{item['problem']!r}")
    try:
        pval = mathgrade.parse_expr(prob_src).value
    except mathgrade.ParseError as e:
        errs.append(f"problem does not parse: {e}")
        pval = None
    try:
        aval = _answer_value(item["answer"])
    except mathgrade.ParseError as e:
        errs.append(f"answer does not parse: {e}")
        aval = None
    if pval is not None and aval is not None and pval != aval:
        errs.append(f"answer value {aval} != problem value {pval}")
    if item["type"] == "choose":
        if item["answer"] not in item["options"]:
            errs.append(f"answer {item['answer']!r} not in options {item['options']!r}")
        for o in item["options"]:
            if o == item["answer"]:
                continue
            try:
                ov = mathgrade.parse_expr(o).value
            except mathgrade.ParseError:
                continue  # an unparseable distractor is wrong by construction
            if ov == aval:
                errs.append(f"distractor {o!r} is also correct")
    return errs


def validate_file(path: Path) -> list[str]:
    """Item-level + file-level invariants (ids sequential, no duplicate problems)."""
    errs: list[str] = []
    try:
        items = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"{path.name}: unreadable: {e}"]
    if not isinstance(items, list):
        return [f"{path.name}: top level must be a list"]
    seen_norm: dict[str, str] = {}
    seen_ids: set[str] = set()
    last_num = 0
    for i, it in enumerate(items):
        for e in validate_item(it):
            errs.append(f"{path.name}[{i}] {it.get('id', '?')}: {e}")
        iid = it.get("id", "")
        if iid in seen_ids:
            errs.append(f"{path.name}[{i}]: duplicate id {iid!r}")
        seen_ids.add(iid)
        m = re.search(r"\.(\d+)$", iid)
        if m:
            num = int(m.group(1))
            if num <= last_num:
                errs.append(f"{path.name}[{i}]: id {iid!r} not sequential after {last_num}")
            last_num = num
        key = norm_problem(it.get("problem", ""))
        if key in seen_norm:
            errs.append(f"{path.name}[{i}]: duplicate problem {it.get('problem')!r} "
                        f"(same as {seen_norm[key]})")
        seen_norm.setdefault(key, iid)
    return errs


# ------------------------------------------------------------- generation ---

def build_item(family: str, rng: random.Random, competence_id: str, seq: int,
               source: str) -> dict:
    """One candidate item: template value vs evaluator value must agree."""
    if family in STEPS_FAMILIES:
        return _build_steps_item(family, rng, competence_id, seq, source)
    if family not in FAMILIES:
        raise GenError(f"unknown template family {family!r} "
                       f"(known: {', '.join(sorted(FAMILIES))}, "
                       f"steps: {', '.join(sorted(STEPS_FAMILIES))})")
    cand = FAMILIES[family](rng)
    # The two independent computations must agree before anything is rendered.
    # A word problem's arithmetic is `expression`, not the story (§4.1/WP3.2).
    src = cand.get("expression") or cand["problem"]
    if cand["value"] is not None:
        try:
            pval = mathgrade.parse_expr(src).value
        except mathgrade.ParseError as e:
            raise GenError(f"{family}: generated problem {src!r} "
                           f"does not parse: {e}") from e
        if pval != cand["value"]:
            raise GenError(f"{family}: template value {cand['value']} != evaluator "
                           f"value {pval} for {src!r}")
        aval = _answer_value(cand["answer"])
        if aval != cand["value"]:
            raise GenError(f"{family}: answer {cand['answer']!r} -> {aval} != "
                           f"{cand['value']}")
    item = {
        "id": f"{competence_id}.{seq:03d}",
        "competence": competence_id,
        "type": cand["type"],
        "instruction": cand["instruction"],
        "problem": cand["problem"],
        "answer": cand["answer"],
        "also_accept": cand["also_accept"],
        "options": cand["options"],
        "why": cand["why"],
        "status": "validated",
        "source": source,
    }
    if cand.get("expression"):
        item["expression"] = cand["expression"]
    errs = validate_item(item)
    if errs:
        raise GenError(f"{family}: generated an invalid item: " + "; ".join(errs))
    return item


def _build_steps_item(family: str, rng: random.Random, competence_id: str, seq: int,
                      source: str) -> dict:
    """One candidate steps item. Same two-path rule as compute: the template's
    Fraction value is re-derived from the PROBLEM STRING by the evaluator; plus
    every step's expect/value/accept must be consistent (validate_item)."""
    cand = STEPS_FAMILIES[family](rng)
    try:
        pval = mathgrade.parse_expr(cand["problem"]).value
    except mathgrade.ParseError as e:
        raise GenError(f"{family}: generated problem {cand['problem']!r} "
                       f"does not parse: {e}") from e
    if pval != cand["value"]:
        raise GenError(f"{family}: template value {cand['value']} != evaluator "
                       f"value {pval} for {cand['problem']!r}")
    aval = mathgrade.parse_expr(cand["answer"]).value
    if aval != cand["value"]:
        raise GenError(f"{family}: answer {cand['answer']!r} -> {aval} != {cand['value']}")
    item = {
        "id": f"{competence_id}.{seq:03d}",
        "competence": competence_id,
        "type": "steps",
        "instruction": cand["instruction"],
        "problem": cand["problem"],
        "method": cand["method"],
        "steps": cand["steps"],
        "answer": cand["answer"],
        "why": cand["why"],
        # WP2.3 wired the per-line grader (hooks/bank.py `_grade_steps`), so
        # steps items are generator-verified like compute items and served.
        "status": "validated",
        "source": source,
    }
    fill_goals(item)
    errs = validate_item(item)
    if errs:
        raise GenError(f"{family}: generated an invalid item: " + "; ".join(errs))
    return item


def generate(curriculum_path: Path, competence_id: str, n: int, seed: int,
             out_dir: Path | None, day: str, family: str | None = None) -> tuple[Path, list[dict]]:
    """Append n new items to <out_dir>/<competence>.json (compute families) or
    <out_dir>/<competence>__steps.json (steps families — served since WP2.2/2.3,
    see the module docstring). `out_dir=None` means the curriculum's
    bank dir; steps families default into its `steps/` subdirectory. Ids
    continue the existing numbering; problems already in the file are never
    duplicated. With an explicit `family` the curriculum's `Bank:` line (and
    even the competence's presence in the .md) is not consulted — used for
    the steps pilots whose curriculum entries WP1.1 still has to add."""
    if family is None:
        if not competence_exists(curriculum_path, competence_id):
            raise GenError(f"{competence_id}: not a competence of {curriculum_path.name}")
        family = bank_family_for(curriculum_path, competence_id)
    if family not in FAMILIES and family not in STEPS_FAMILIES:
        raise GenError(f"unknown template family {family!r} "
                       f"(known: {', '.join(sorted(FAMILIES))}, "
                       f"steps: {', '.join(sorted(STEPS_FAMILIES))})")
    is_steps = family in STEPS_FAMILIES
    if out_dir is None:
        out_dir = _default_out(curriculum_path)
        if is_steps:
            out_dir = Path(out_dir) / "steps"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "__steps" if is_steps else ""
    path = out_dir / f"{competence_id}{suffix}.json"
    existing = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        errs = validate_file(path)
        if errs:
            raise GenError("refusing to append to an invalid file:\n" + "\n".join(errs))
    used = {norm_problem(it["problem"]) for it in existing}
    # Ids are the competence's, not the file's: bank.py merges `<cid>.json` and
    # `steps/<cid>__steps.json` into ONE item set addressed by id (progress,
    # the review queue, records), so the numbering continues across BOTH files
    # — a steps item and a compute item of one competence can never share an id.
    # The same rule covers the PROBLEMS: a competence never serves one exercise
    # twice, so a steps item cannot repeat a compute item of its own competence
    # (or the other way round). Both files are read, whichever one is written.
    last_num = 0
    siblings = [path, out_dir / f"{competence_id}.json", out_dir / f"{competence_id}__steps.json",
                out_dir / "steps" / f"{competence_id}__steps.json"]
    if out_dir.name == "steps":
        siblings.append(out_dir.parent / f"{competence_id}.json")
    seen_paths = set()
    for sp in siblings:
        if sp == path or sp in seen_paths or not sp.exists():
            seen_paths.add(sp)
            continue
        seen_paths.add(sp)
        for it in json.loads(sp.read_text(encoding="utf-8")):
            m = re.search(r"\.(\d+)$", it.get("id", ""))
            if m:
                last_num = max(last_num, int(m.group(1)))
            used.add(norm_problem(it.get("problem", "")))
    for it in existing:
        m = re.search(r"\.(\d+)$", it.get("id", ""))
        if m:
            last_num = max(last_num, int(m.group(1)))
    rng = random.Random(seed)
    source = f"mathbank · {day} · seed {seed}"
    new: list[dict] = []
    attempts = 0
    budget = max(2000, n * 200)
    while len(new) < n:
        attempts += 1
        if attempts > budget:
            raise GenError(f"{family}: only {len(new)}/{n} unique items in "
                           f"{budget} draws — template space too small for n={n}")
        cand = build_item(family, rng, competence_id, last_num + len(new) + 1, source)
        key = norm_problem(cand["problem"])
        if key in used:
            continue
        used.add(key)
        new.append(cand)
    items = existing + new
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    errs = validate_file(path)
    if errs:
        raise GenError(f"written file failed validation:\n" + "\n".join(errs))
    return path, new


# ------------------------------------------------------------------- CLI ---

def _default_out(curriculum_path: Path) -> Path:
    return REPO_ROOT / "curriculum" / "bank" / Path(curriculum_path).stem


def _rel(p: Path) -> str:
    try:
        return str(Path(p).relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mathbank.py",
                                 description="Parametric math bank generator (WP1.5)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="generate items for one competence")
    g.add_argument("--curriculum", required=True, type=Path)
    g.add_argument("--competence", required=True)
    g.add_argument("--n", type=int, required=True)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--family", default=None,
                   help="template family; default: the competence's `Bank:` line. "
                        "Steps families (partial_products, partial_sums, "
                        "common_denominator, long_division) must be named here "
                        "and write <competence>__steps.json with status generated.")
    g.add_argument("--out", type=Path, default=None)
    g.add_argument("--type", default=None, choices=["steps"],
                   help="steps items (type is otherwise inferred from --family)")
    g.add_argument("--date", default=None, help="YYYY-MM-DD stamped into source (default: today)")

    v = sub.add_parser("validate", help="re-check every written file of a curriculum")
    v.add_argument("--curriculum", required=True, type=Path)
    v.add_argument("--competence", default=None)
    v.add_argument("--out", type=Path, default=None)

    a = ap.parse_args(argv)
    try:
        if a.cmd == "gen":
            if a.n <= 0:
                raise GenError("--n must be positive")
            if a.type == "steps":
                if a.family is None:
                    raise GenError("--type steps needs --family "
                                   f"(steps families: {', '.join(sorted(STEPS_FAMILIES))})")
                if a.family not in STEPS_FAMILIES:
                    raise GenError(f"--type steps needs a steps family, not {a.family!r}")
            day = a.date or _date.today().isoformat()
            path, new = generate(a.curriculum, a.competence, a.n, a.seed,
                                 a.out, day, family=a.family)
            shown = _rel(path)
            fam = a.family or bank_family_for(a.curriculum, a.competence)
            print(f"{shown}: +{len(new)} items "
                  f"({new[0]['id']} … {new[-1]['id']}), family {fam}")
            return 0
        if a.cmd == "validate":
            out_dir = a.out or _default_out(a.curriculum)
            if a.competence:
                files = [f for f in (out_dir / f"{a.competence}.json",
                                     out_dir / "steps" / f"{a.competence}__steps.json")
                         if f.exists()]
            else:
                files = sorted(out_dir.glob("*.json")) if out_dir.is_dir() else []
                steps_dir = out_dir / "steps"
                if steps_dir.is_dir():
                    files += sorted(steps_dir.glob("*.json"))
            if not files:
                print(f"validate: no files under {out_dir}", file=sys.stderr)
                return 1
            bad = 0
            for f in files:
                errs = validate_file(f)
                if errs:
                    bad += 1
                    print(f"FAIL {_rel(f)}")
                    for e in errs:
                        print(f"  - {e}")
                else:
                    items = json.loads(f.read_text(encoding="utf-8"))
                    print(f"OK   {_rel(f)} ({len(items)} items)")
            return 1 if bad else 0
    except GenError as e:
        print(f"mathbank: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
