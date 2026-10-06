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


STEPS_FAMILIES = {
    "partial_products": partial_products,
    "partial_sums": partial_sums,
    "common_denominator": common_denominator,
    "long_division": long_division,
    "props_grouping_numeric": props_grouping_numeric,
    "props_distributive_numeric": props_distributive_numeric,
    "props_factor_numeric": props_factor_numeric,
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
STEP_REQUIRED_KEYS = ("n", "expect", "value", "accept", "error_class", "why")


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
    try:
        pval = mathgrade.parse_expr(item["problem"]).value
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
    if _ALG_LETTERS.search(str(item["answer"])):
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
        aval = mathgrade.parse_expr(item["answer"]).value
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
        aval = mathgrade.parse_expr(cand["answer"]).value
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
    last_num = 0
    siblings = [path, out_dir / f"{competence_id}.json", out_dir / f"{competence_id}__steps.json"]
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
