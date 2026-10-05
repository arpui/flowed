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

`status: "validated"` means generator-verified; a human review flips it to
"reviewed" later. bank.py serves validated/reviewed, so generated items are
live — intended for the pilot.

Template families are selected per competence by a `Bank: <family>` line in the
curriculum .md (a key `hooks/curriculum.py` ignores; this script reads it).
Fallback for the pilot ids: DEFAULT_FAMILY_BY_ID.

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
  python3 scripts/mathbank.py validate --curriculum curriculum/math-m4.md [--competence ID] [--out DIR]

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

import mathgrade  # noqa: E402  (hooks/mathgrade.py — the grader itself)

__all__ = ["FAMILIES", "build_item", "validate_item", "validate_file", "GenError"]


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


FAMILIES = {
    "mult_2digit": mult_2digit,
    "frac_add_unlike": frac_add_unlike,
    "dec_add": dec_add,
    "compare_fracs": compare_fracs,
}

# Fallback when the curriculum .md has no `Bank:` line (the pilot ids).
DEFAULT_FAMILY_BY_ID = {
    "m4.mult_2digit": "mult_2digit",
    "m4.frac_add_unlike": "frac_add_unlike",
    "m4.dec_add": "dec_add",
    "m4.compare_fracs": "compare_fracs",
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
ITEM_TYPES = ("compute", "choose", "compare")
_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+\.\d{3,}$")


def validate_item(item: dict) -> list[str]:
    """Every invariant an item must satisfy before it may be written. Returns
    a list of problems (empty = good). Never trusts the template."""
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

    # compute / choose: the problem must parse, and its value must equal the
    # answer's value — the same evaluator that will grade the learner.
    try:
        pval = mathgrade.parse_expr(item["problem"]).value
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
    if family not in FAMILIES:
        raise GenError(f"unknown template family {family!r} "
                       f"(known: {', '.join(sorted(FAMILIES))})")
    cand = FAMILIES[family](rng)
    # The two independent computations must agree before anything is rendered.
    if cand["value"] is not None:
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
    errs = validate_item(item)
    if errs:
        raise GenError(f"{family}: generated an invalid item: " + "; ".join(errs))
    return item


def generate(curriculum_path: Path, competence_id: str, n: int, seed: int,
             out_dir: Path, day: str) -> tuple[Path, list[dict]]:
    """Append n new validated items to <out_dir>/<competence>.json. Ids continue
    the existing numbering; problems already in the file are never duplicated."""
    if not competence_exists(curriculum_path, competence_id):
        raise GenError(f"{competence_id}: not a competence of {curriculum_path.name}")
    family = bank_family_for(curriculum_path, competence_id)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{competence_id}.json"
    existing = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        errs = validate_file(path)
        if errs:
            raise GenError("refusing to append to an invalid file:\n" + "\n".join(errs))
    used = {norm_problem(it["problem"]) for it in existing}
    last_num = 0
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
    g.add_argument("--out", type=Path, default=None)
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
            day = a.date or _date.today().isoformat()
            path, new = generate(a.curriculum, a.competence, a.n, a.seed,
                                 a.out or _default_out(a.curriculum), day)
            shown = _rel(path)
            print(f"{shown}: +{len(new)} items "
                  f"({new[0]['id']} … {new[-1]['id']}), family "
                  f"{bank_family_for(a.curriculum, a.competence)}")
            return 0
        if a.cmd == "validate":
            out_dir = a.out or _default_out(a.curriculum)
            if a.competence:
                files = [out_dir / f"{a.competence}.json"]
            else:
                files = sorted(out_dir.glob("*.json")) if out_dir.is_dir() else []
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
