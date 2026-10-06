"""Deterministic arithmetic grader for the math exercise bank (DISSENY-MATEMATIQUES §4.3).

The language bank grades answers with `canon()` + OSA distance (hooks/bank.py);
this is its arithmetic counterpart: exact rational arithmetic via
`fractions.Fraction`, an `ast.parse(mode="eval")` evaluator restricted to
numbers and `+ - * / ^ ( )` with unary minus, and verdicts parallel to the
language ones: correct=10 / near=7 / wrong=3 / empty=0.

STDLIB ONLY — the hooks are stdlib-pure and CI byte-compiles them. No sympy.

Public API (WP1.3 will wire this into hooks/bank.py; nothing is wired yet):

  parse_expr(text) -> Parsed(value: Fraction, form: str)
      Raises ParseError (a ValueError) on anything it cannot understand.

  grade_single(expected, given, also_accept=(), unit=None) -> verdict dict
      {"score", "verdict", "note", "expected", "got", ...} — same shape as
      bank.grade's verdicts.

  grade_step(expected, line, strict_form=False) -> verdict dict
      One line of a worked solution: "expr", "expr = value" or "value".

  parse_poly(text) -> dict {monomial -> Fraction}      (WP1.1, algebraic)
  poly_form(poly) -> str                               readable canonical form
  grade_algebraic(expected, given, also_accept=(), problem=None) -> verdict
      Expression answers graded by POLYNOMIAL EQUIVALENCE (5x+5 == 5+5x ==
      5(x+1)), with a §4.4 error category on wrong answers. See the
      "algebraic (WP1.1)" section for the accepted notation and the mapping.

  CLI: python3 hooks/mathgrade.py eval "1 1/2 + 1/4"
       python3 hooks/mathgrade.py grade "3/4" "0,75"
       python3 hooks/mathgrade.py step "2/8 + 3/8" "1/4+3/8 = 2/8+3/8"
       python3 hooks/mathgrade.py poly "3x + 5 + 2x"
       python3 hooks/mathgrade.py agrade "5x + 5" "5 + 5x"

Notation decisions (v1, deliberate):
  * Decimal comma "3,5" and decimal point "3.5" both work; "×", "·", "÷",
    unicode minus, and "^" (also "**") are accepted.
  * Thousand separators are NOT accepted: "1.000.000" / "1,000,000" (two or
    more groups of exactly three digits after a separator) -> ParseError.
    A single group like "1.000" is read as the decimal 1.0 — ambiguous by
    nature, documented limitation.
  * Mixed numbers "1 1/2" -> 1 + 1/2. A leading minus applies to the whole
    mixed number: "-1 1/2" -> -(1 + 1/2).
  * Canonical FORM: commutative operands (+ chains, * chains) are sorted,
    decimal constants render as exact fractions ("0,75" -> "3/4"), but a
    WRITTEN division keeps its structure ("2/8" stays "2/8", it is not
    reduced to "1/4"). So forms compare notation, values compare math.
  * "near" (7): a transcription slip of the expected ANSWER only — given and
    expected are both plain numbers (no operators, no fractions), both digit
    strings have length >= 2, and their Damerau-OSA distance is exactly 1
    (substitute / insert / delete / adjacent transposition): 324 vs 342,
    324 vs 3240, 12 vs 21. A sign flip ("324" vs "-324") is NOT near (the
    digit strings are equal — that is a real math error). Matching a
    different also_accept is "correct", never "near".
  * Units: compared loosely (lower + strip + a small Catalan/Spanish alias
    table). Value right + unit wrong or missing when a unit was expected ->
    near (7) with a note. An extra unit when none was expected is tolerated.
  * Exponents must be integers with |exp| <= 10000 (guards "9^9^9" hangs).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from fractions import Fraction

__all__ = [
    "ParseError", "Parsed", "parse_expr",
    "grade_single", "grade_step",
    "parse_poly", "poly_form", "grade_algebraic",
    "EMPTY_ANSWERS",
]


class ParseError(ValueError):
    """The text is not a math expression this grader understands."""


class Parsed(tuple):
    """Result of parse_expr: exact value + canonical form. NamedTuple-like."""
    __slots__ = ()
    _fields = ("value", "form")

    def __new__(cls, value, form):
        return tuple.__new__(cls, (value, form))

    @property
    def value(self):
        return self[0]

    @property
    def form(self):
        return self[1]

    def __repr__(self):
        return f"Parsed(value={self[0]!r}, form={self[1]!r})"


# ---------------------------------------------------------------- parsing ---

# Unicode notation -> ASCII operators.
_OPS = str.maketrans({
    "×": "*", "·": "*", "∗": "*", "⋅": "*",
    "÷": "/", "⁄": "/",
    "−": "-", "–": "-", "—": "-",
})

# "1.000.000" / "1,000,000": two or more groups of exactly 3 digits after a
# separator are thousand separators -> rejected in v1 (see module docstring).
_THOUSANDS = re.compile(r"\d{1,3}(?:\.\d{3}){2,}")

# Mixed number: "1 1/2" -> "1+1/2" (and "-1 1/2" -> "-(1+1/2)").
_MIXED_NEG = re.compile(r"(-\s*)(\d+)\s+(\d+)\s*/\s*(\d+)")
_MIXED = re.compile(r"(?<![\d./])(\d+)\s+(\d+)\s*/\s*(\d+)")

# A bare number as written: int, decimal, fraction or mixed number. Used to
# decide whether `expected` is a value or a form, and for the "near" rule.
# Matched against the normalized text with ALL spaces removed, so "6 / 2"
# and "6/2" are both pure values while "2/8 + 3/8" is a form.
_PURE_VALUE = re.compile(
    r"^[+-]?(\d+(\.\d+)?|\d+/\d+|\d+\+\d+/\d+|\(\d+\+\d+/\d+\))$")
# "near" is stricter: plain decimal digits only, no fractions.
_PLAIN_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?$")

_ALLOWED_BIN = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
_MAX_EXPONENT = 10000


def _normalize(text) -> str:
    """Notation normalization: unicode operators, decimal comma, mixed
    numbers, whitespace. Raises ParseError on thousand separators."""
    if text is None:
        return ""
    s = str(text).strip().translate(_OPS)
    s = s.replace("^", "**")  # "^" is BitXor in Python's AST; we mean power
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)  # decimal comma
    if _THOUSANDS.search(s):
        raise ParseError("thousand separators are not accepted (write 1000000)")
    s = _MIXED_NEG.sub(r"-(\2+\3/\4)", s)
    s = _MIXED.sub(r"\1+\2/\3", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_expr(text) -> Parsed:
    """Parse a math expression into an exact Fraction value + canonical form.

    Accepts integers, decimals ("3.5" / "3,5"), fractions "3/4", mixed
    numbers "1 1/2", the operators + - * / × ÷ · ^ (and **), parentheses,
    unary minus and whitespace. Anything else (names, calls, subscripts,
    comparisons, division by zero, bad syntax) raises ParseError.
    """
    s = _normalize(text)
    if not s:
        raise ParseError("empty expression")
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError as e:
        raise ParseError(f"cannot parse {text!r}") from e
    _validate(tree.body)
    return Parsed(_eval(tree.body), _form(tree.body))


def _validate(node):
    """Reject every AST node that is not a number, an allowed operator, or a
    parenthesized/unary combination of those."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ParseError(f"only plain numbers are allowed, got {node.value!r}")
        return
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BIN):
            raise ParseError(f"operator {type(node.op).__name__} is not allowed")
        _validate(node.left)
        _validate(node.right)
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.UAdd, ast.USub)):
            raise ParseError(f"operator {type(node.op).__name__} is not allowed")
        _validate(node.operand)
        return
    raise ParseError(f"{type(node).__name__} is not allowed")


def _eval(node) -> Fraction:
    """Evaluate the validated AST with exact rational arithmetic."""
    if isinstance(node, ast.Constant):
        # str() of a float round-trips, so Fraction(str(...)) is the exact
        # decimal the learner wrote ("0.1" -> 1/10, not the binary float).
        return Fraction(node.value) if isinstance(node.value, int) else Fraction(str(node.value))
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand)
        return v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp):
        l, r = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Add):
            return l + r
        if isinstance(node.op, ast.Sub):
            return l - r
        if isinstance(node.op, ast.Mult):
            return l * r
        if isinstance(node.op, ast.Div):
            if r == 0:
                raise ParseError("division by zero")
            return l / r
        if isinstance(node.op, ast.Pow):
            if r.denominator != 1:
                raise ParseError("only integer exponents are allowed")
            if abs(r) > _MAX_EXPONENT:
                raise ParseError("exponent too large")
            if l == 0 and r < 0:
                raise ParseError("division by zero")
            return l ** int(r)
    raise ParseError(f"cannot evaluate {type(node).__name__}")


# ------------------------------------------------------------ form render ---

def _fmt_frac(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def _flatten(node, op):
    if isinstance(node, ast.BinOp) and isinstance(node.op, op):
        return _flatten(node.left, op) + _flatten(node.right, op)
    return [node]


def _wrap(rendered, min_prec):
    text, prec = rendered
    return text if prec >= min_prec else f"({text})"


def _int_const(node):
    """The integer written as a plain constant or a signed constant, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd))
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, int) and not isinstance(node.operand.value, bool)):
        v = node.operand.value
        return -v if isinstance(node.op, ast.USub) else v
    return None


def _render(node):
    """(canonical text, precedence) — 0 add/sub, 1 mul/div, 2 atom/unary, 3 pow."""
    if isinstance(node, ast.Constant):
        v = Fraction(node.value) if isinstance(node.value, int) else Fraction(str(node.value))
        return _fmt_frac(v), 2
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.UAdd):
            return _render(node.operand)
        text, prec = _render(node.operand)
        return ("-" + (text if prec >= 2 else f"({text})")), 2
    if isinstance(node, ast.BinOp):
        op = node.op
        if isinstance(op, ast.Add):
            terms = sorted(_wrap(_render(n), 1) for n in _flatten(node, ast.Add))
            return " + ".join(terms), 0
        if isinstance(op, ast.Sub):
            return f"{_wrap(_render(node.left), 0)} - {_wrap(_render(node.right), 1)}", 0
        if isinstance(op, ast.Mult):
            factors = sorted(_wrap(_render(n), 2) for n in _flatten(node, ast.Mult))
            return " * ".join(factors), 1
        if isinstance(op, ast.Div):
            # A WRITTEN fraction (two integer constants) is an atom "a/b",
            # kept unreduced: "2/8" stays "2/8". Any other division renders
            # as an operator "a / b".
            a, b = _int_const(node.left), _int_const(node.right)
            if a is not None and b is not None:
                return f"{a}/{b}", 2
            right, rprec = _render(node.right)
            if isinstance(node.right, ast.BinOp) and isinstance(node.right.op, ast.Div):
                right = f"({right})"  # "6 / (2/8)", never "6 / 2/8"
            return f"{_wrap(_render(node.left), 1)} / {right}", 1  # right already parenthesized if needed
        if isinstance(op, ast.Pow):
            base, bprec = _render(node.left)
            if isinstance(node.left, ast.BinOp) and isinstance(node.left.op, ast.Div):
                base = f"({base})"  # "2/3" as a base needs parens: (2/3)^2
            elif bprec < 2:
                base = f"({base})"
            return f"{base}^{_wrap(_render(node.right), 2)}", 3
    raise ParseError(f"cannot render {type(node).__name__}")


def _form(node) -> str:
    return _render(node)[0]


# ---------------------------------------------------------------- units -----

EMPTY_ANSWERS = frozenset({"", "?", "no ho sé", "no sé", "ns"})

_UNIT_ALIASES = {
    "m": ("m", "metre", "metres", "meter", "meters"),
    "cm": ("cm", "centimetre", "centimetres", "centímetre", "centímetres"),
    "km": ("km", "quilometre", "quilometres", "quilòmetre", "quilòmetres",
           "kilometre", "kilometres"),
    "mm": ("mm", "mil·limetre", "mil·limetres"),
    "kg": ("kg", "quilogram", "quilograms", "quilògram", "quilògrams",
           "kilogram", "kilograms"),
    "g": ("g", "gram", "grams", "gramm"),
    "l": ("l", "litre", "litres", "liter", "liters"),
    "s": ("s", "segon", "segons", "second", "seconds"),
    "min": ("min", "minut", "minuts"),
    "h": ("h", "hora", "hores", "hour", "hours"),
    "€": ("€", "euros"),
}
_UNIT_CANON = {a: canon for canon, aliases in _UNIT_ALIASES.items() for a in aliases}

# Trailing unit after a value that ends in a digit: "12 cm", "12cm", "1 1/2 m".
_TRAILING_UNIT = re.compile(r"^(?P<val>.*?\d)\s*(?P<unit>[^\d\s.,*/^()+-]+)$")


def _unit_norm(u):
    if u is None:
        return None
    u = str(u).strip().lower().rstrip(".")
    return _UNIT_CANON.get(u, u)


def _parse_with_unit(text):
    """parse_expr, falling back to splitting a trailing unit off.
    Returns (Parsed, unit_or_None)."""
    try:
        return parse_expr(text), None
    except ParseError:
        m = _TRAILING_UNIT.match(str(text or "").strip())
        if m:
            return parse_expr(m["val"]), m["unit"]
        raise


def _is_empty(text) -> bool:
    t = str(text or "").strip().lower().strip("?!.").strip()
    return t in EMPTY_ANSWERS


def _digits_of(text):
    """Digit string of a plain written number, or None if it is not one."""
    try:
        s = _normalize(text)
    except ParseError:
        return None
    if not _PLAIN_NUMBER.match(s):
        return None
    return re.sub(r"\D", "", s)


def _osa(a: str, b: str, cap: int = 2) -> int:
    """Optimal string alignment (restricted Damerau-Levenshtein): Levenshtein
    plus adjacent transposition as one edit. Capped; `cap` means 'at least'."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > cap:
        return cap + 1
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def _value_part(text):
    """The number part of a written answer, unit stripped if present."""
    m = _TRAILING_UNIT.match(str(text or "").strip())
    return m["val"] if m else str(text or "")


def _near_slip(given_text, expected_text) -> bool:
    """One Damerau-OSA edit on the digit string of two plain numbers, both of
    length >= 2 (324/342, 324/3240, 12/21). See the module docstring."""
    dg, de = _digits_of(given_text), _digits_of(expected_text)
    if dg is None or de is None or len(dg) < 2 or len(de) < 2:
        return False
    if dg == de:
        return False  # same digits, different value: a sign/separator error, not a slip
    return _osa(dg, de, cap=2) == 1


def _verdict(score, verdict, note="", expected=None, got=None, **extra):
    d = {"score": score, "verdict": verdict, "note": note, "expected": expected, "got": got}
    d.update(extra)
    return d


# ------------------------------------------------------------ grade_single ---

def grade_single(expected, given, also_accept=(), unit=None) -> dict:
    """Grade a one-value answer. Verdicts: correct 10 / near 7 / wrong 3 /
    empty 0 (parallel to the language bank's correct/typo/wrong/empty).

    `expected` may be a string ("3/4", "12 cm"), a Fraction or an int;
    `also_accept` is a list of further accepted values; `unit` overrides the
    unit found in `expected`.
    """
    if _is_empty(given):
        return _verdict(0, "empty", "resposta buida")

    exp, exp_unit = _parse_with_unit(expected)
    if unit is not None:
        exp_unit = unit
    accepts = []
    for a in also_accept:
        p, _ = _parse_with_unit(a)
        accepts.append(p.value)

    try:
        got, got_unit = _parse_with_unit(given)
    except ParseError as e:
        return _verdict(3, "wrong", f"no s'ha entès l'expressió ({e})",
                        expected=exp.form, got=str(given).strip())

    unit_ok = exp_unit is None or _unit_norm(got_unit) == _unit_norm(exp_unit)
    value_ok = got.value == exp.value or got.value in accepts

    if value_ok and unit_ok:
        return _verdict(10, "correct", "", expected=exp.form, got=got.form)
    if value_ok and not unit_ok:
        return _verdict(7, "near",
                        f"valor correct, unitat {'que falta' if got_unit is None else f'errònia ({got_unit})'}"
                        f" — escriu «{exp_unit}»",
                        expected=exp.form, got=got.form, unit_ok=False)
    if _near_slip(_value_part(given), _value_part(expected)):
        return _verdict(7, "near", f"gairebé: s'escriu «{exp.form}»",
                        expected=exp.form, got=got.form)
    return _verdict(3, "wrong", "", expected=exp.form, got=got.form)


# --------------------------------------------------------------- grade_step ---

def grade_step(expected, line, strict_form=False) -> dict:
    """Grade one line of a worked solution: "expr", "expr = value" or "value".
    Split on the LAST '='. A line with two '=' raises ParseError.

    Matches when either side's VALUE equals the expected step value, or — when
    `strict_form` is set or `expected` is itself a form (not a bare number) —
    when a side's canonical FORM equals the expected form. The verdict reports
    which side(s) matched and the parsed values so the caller can build
    feedback.
    """
    exp, _ = _parse_with_unit(expected)
    exp_is_form = strict_form or not _PURE_VALUE.match(re.sub(r"\s+", "", _normalize(expected)))

    if _is_empty(line):
        return _verdict(0, "empty", "línia buida", expected=exp.form, got=None)

    text = str(line).strip()
    if text.count("=") >= 2:
        raise ParseError("a step line may contain at most one '='")

    sides = {}
    if "=" in text:
        left, right = text.rsplit("=", 1)
        sides["left"] = parse_expr(left)
        sides["right"] = parse_expr(right)
    else:
        sides["line"] = parse_expr(text)

    def matches(p):
        return p.form == exp.form if exp_is_form else p.value == exp.value

    matched = [name for name, p in sides.items() if matches(p)]
    detail = {name: {"value": str(p.value), "form": p.form} for name, p in sides.items()}
    if matched:
        return _verdict(10, "correct", "", expected=exp.form,
                        got=sides[matched[0]].form,
                        matched_sides=matched, sides=detail, form_mode=exp_is_form)
    return _verdict(3, "wrong",
                    "cap costat no coincideix" + (" amb la forma esperada" if exp_is_form else ""),
                    expected=exp.form, got=None,
                    matched_sides=[], sides=detail, form_mode=exp_is_form)


# ------------------------------------------------- algebraic (WP1.1) ---------
# The polynomial counterpart of parse_expr, for the m7 "Joc de les Propietats"
# (docs/competencies1eso.md, docs/AlgebraNumericaBasica.md): the learner
# manipulates EXPRESSIONS ("3x + 5 + 2x" -> "5x + 5"), so the answer is not a
# value but an equivalence class of writings.
#
# Accepted notation (deliberately close to parse_expr's):
#   * single-letter variables (x, y, z, a, b...); multi-letter names are a
#     ParseError ("cm" is a unit, not a variable);
#   * + - * ( ) and unary minus, integer coefficients; a division of two
#     constants is a coefficient ("x/2", "6x ÷ 3") — dividing by an expression
#     is a ParseError (fractions coefficients only when trivial);
#   * powers with a non-negative integer exponent <= 6, expanded: x^2, x²,
#     x·x, (x+1)^2;
#   * juxtaposition: "3x", "2(x+1)", "x(x+5)", "xy", "(x+1)(x+2)" all insert
#     an implicit *. NEVER a digit after a variable: "x5" stays invalid.
#
# Canonical form: the EXPANDED dict {monomial -> Fraction}, monomial = sorted
# tuple of (var, exponent) pairs, () = constant. Two expressions are
# equivalent iff their canonical forms match: 5x+5 == 5+5x == 5(x+1),
# x(x+5) == x^2+5x, -2(x+4) == -2x-8.
#
# grade_algebraic verdicts (parallel to grade_single):
#   correct 10  — canonical forms match (or an also_accept does)
#   near     7  — the forms differ in EXACTLY ONE monomial coefficient and
#                 that coefficient is a one-digit Damerau-OSA slip of the
#                 expected one (the _near_slip rule, on the coefficient)
#   wrong    3  — with a `category` from the §4.4 taxonomy:
#                 * "procedure"     — the learner retyped the problem verbatim
#                                     (with `problem` given): nothing was
#                                     transformed; an extra term the answer
#                                     has no trace of (6y+8z+x); or several
#                                     monomials off
#                 * "sign"          — one coefficient differs and is exactly
#                                     the negation of the expected one
#                                     (-2x+8 for -2x-8)
#                 * "incomplete"    — the learner dropped a whole term and
#                                     changed nothing else (6y for 6y+8z)
#                 * "wrong_operation" — exactly one coefficient differs, is
#                                     not a sign flip nor a digit slip
#                                     (3(x+4) -> 3x+4: the constant kept a
#                                     wrong value — the operation applied to
#                                     the packet was the wrong one)
#   empty    0
# The category is reported in the verdict ("category" and "error_class", the
# steps path's key) so the caller can file one mistake pattern per answer.
# KNOWN LIMITATION (documented, WP1.1): equivalence grading accepts ANY
# equivalent writing, so a learner who reorders without simplifying ("2x + 5
# + 3x" for "3x + 5 + 2x") scores 10; only the verbatim retype is caught.
# Requiring a shorter form (fewer terms than the problem) is a possible
# refinement, not wired.

_ALG_VAR = re.compile(r"^[a-zA-Z]$")
_SUPS = str.maketrans({"²": "^2", "³": "^3", "⁴": "^4"})
_MAX_POLY_POW = 6


def _normalize_alg(text) -> str:
    """Notation normalization for algebraic input: parse_expr's operators
    plus superscripts and juxtaposition. Raises ParseError on thousand
    separators (same guard as _normalize)."""
    if text is None:
        return ""
    s = str(text).strip().translate(_OPS).translate(_SUPS)
    s = s.replace("^", "**")
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)
    if _THOUSANDS.search(s):
        raise ParseError("thousand separators are not accepted (write 1000000)")
    # implicit multiplication; a digit AFTER a variable is never joined ("x5"
    # stays a syntax error — the draft's notation is 3x, 4·x, x(x+5)).
    s = re.sub(r"(\d)\s*(?=[a-zA-Z(])", r"\1*", s)
    s = re.sub(r"([a-zA-Z)])\s*(?=\()", r"\1*", s)
    s = re.sub(r"([a-zA-Z)])\s*(?=[a-zA-Z(])", r"\1*", s)
    return re.sub(r"\s+", " ", s).strip()


def _mono_mul(m1: tuple, m2: tuple) -> tuple:
    d = dict(m1)
    for v, e in m2:
        d[v] = d.get(v, 0) + e
    return tuple(sorted((v, e) for v, e in d.items() if e))


def _poly_add(a: dict, b: dict, sign=1) -> dict:
    out = dict(a)
    for k, c in b.items():
        out[k] = out.get(k, Fraction(0)) + sign * c
    return {k: v for k, v in out.items() if v}


def _poly_mul(a: dict, b: dict) -> dict:
    out: dict = {}
    for ma, ca in a.items():
        for mb, cb in b.items():
            k = _mono_mul(ma, mb)
            out[k] = out.get(k, Fraction(0)) + ca * cb
    return {k: v for k, v in out.items() if v}


def _poly_eval(node) -> dict:
    """Evaluate a node to the expanded dict {monomial -> Fraction}."""
    if isinstance(node, ast.Constant):
        v = Fraction(node.value) if isinstance(node.value, int) else Fraction(str(node.value))
        if isinstance(node.value, bool):
            raise ParseError("only plain numbers are allowed")
        return {(): v} if v else {}
    if isinstance(node, ast.Name):
        if not _ALG_VAR.match(node.id):
            raise ParseError(f"only single-letter variables are allowed, got {node.id!r}")
        return {((node.id, 1),): Fraction(1)}
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.UAdd, ast.USub)):
            raise ParseError(f"operator {type(node.op).__name__} is not allowed")
        p = _poly_eval(node.operand)
        return p if isinstance(node.op, ast.UAdd) else {k: -c for k, c in p.items()}
    if isinstance(node, ast.BinOp):
        op = node.op
        if isinstance(op, ast.Add):
            return _poly_add(_poly_eval(node.left), _poly_eval(node.right))
        if isinstance(op, ast.Sub):
            return _poly_add(_poly_eval(node.left), _poly_eval(node.right), sign=-1)
        if isinstance(op, ast.Mult):
            return _poly_mul(_poly_eval(node.left), _poly_eval(node.right))
        if isinstance(op, ast.Div):
            right = _poly_eval(node.right)
            if list(right) != [()]:
                raise ParseError("can only divide by a number, not by an expression")
            if right[()] == 0:
                raise ParseError("division by zero")
            return {k: c / right[()] for k, c in _poly_eval(node.left).items()}
        if isinstance(op, ast.Pow):
            base = _poly_eval(node.left)
            exp = _poly_eval(node.right)
            if list(exp) != [()] or exp[()].denominator != 1:
                raise ParseError("only integer exponents are allowed")
            n = int(exp[()])
            if n < 0:
                raise ParseError("negative exponents are not allowed")
            if n > _MAX_POLY_POW:
                raise ParseError(f"exponent too large (max {_MAX_POLY_POW})")
            out: dict = {(): Fraction(1)}
            for _ in range(n):
                out = _poly_mul(out, base)
            return out
    raise ParseError(f"{type(node).__name__} is not allowed")


def parse_poly(text) -> dict:
    """Parse an algebraic expression into its canonical expanded polynomial
    {monomial -> Fraction}. Raises ParseError on anything unsupported."""
    s = _normalize_alg(text)
    if not s:
        raise ParseError("empty expression")
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError as e:
        raise ParseError(f"cannot parse {text!r}") from e
    return _poly_eval(tree.body)


def _mono_render(m: tuple) -> str:
    return "".join(v if e == 1 else f"{v}^{e}" for v, e in m)


def poly_form(poly: dict) -> str:
    """Readable rendering of a canonical polynomial: highest total degree
    first, variables alphabetical within a monomial."""
    items = sorted(((k, v) for k, v in poly.items() if v),
                   key=lambda kv: (-sum(e for _, e in kv[0]), kv[0]))
    if not items:
        return "0"
    out = []
    for i, (m, c) in enumerate(items):
        mp = _mono_render(m)
        if not mp:
            t = _fmt_frac(abs(c))
        elif c in (1, -1):
            t = mp
        else:
            t = f"{_fmt_frac(abs(c))}{mp}"
        out.append(("-" if c < 0 else "") + t if i == 0
                   else (" - " if c < 0 else " + ") + t)
    return "".join(out)


def _algebraic_category(exp: dict, got: dict) -> tuple[str, str]:
    """The §4.4 category of a wrong algebraic answer (see the block comment).
    Returns ("near", "") when it is a one-coefficient digit slip instead."""
    only_e = [k for k in exp if k not in got]
    only_g = [k for k in got if k not in exp]
    diff = [k for k in exp if k in got and exp[k] != got[k]]
    if len(only_e) + len(only_g) + len(diff) == 1:
        if diff:
            k = diff[0]
            ce, cg = exp[k], got[k]
            if _near_slip(_fmt_frac(cg), _fmt_frac(ce)):
                return "near", ""
            if cg == -ce:
                return "sign", f"el signe del terme «{poly_form({k: ce})}» està canviat"
            return "wrong_operation", (f"el terme «{poly_form({k: ce})}» surt com a "
                                       f"«{poly_form({k: cg})}»")
        if only_e:
            return "incomplete", f"falta el terme «{poly_form({only_e[0]: exp[only_e[0]]})}»"
        return "procedure", f"hi ha un terme de més: «{poly_form({only_g[0]: got[only_g[0]]})}»"
    return "procedure", "l'expressió no és equivalent a la resposta"


def grade_algebraic(expected, given, also_accept=(), problem=None) -> dict:
    """Grade an expression answer by POLYNOMIAL equivalence (see the block
    comment above). `problem`, when given, is the exercise's own expression:
    an answer that just retypes it verbatim is "procedure" — the task was to
    TRANSFORM the expression, and equivalence alone cannot see that."""
    if _is_empty(given):
        return _verdict(0, "empty", "resposta buida")
    exp = parse_poly(expected)
    accepts = [parse_poly(a) for a in also_accept]
    try:
        got = parse_poly(given)
    except ParseError as e:
        return _verdict(3, "wrong", f"no s'ha entès l'expressió ({e})",
                        expected=poly_form(exp), got=str(given).strip())
    if problem is not None:
        try:
            if (re.sub(r"\s+", "", _normalize_alg(given))
                    == re.sub(r"\s+", "", _normalize_alg(problem))):
                return _verdict(3, "wrong",
                                "has tornat a escriure l'enunciat tal com era: "
                                "l'objectiu és TRANSFORMAR l'expressió",
                                expected=poly_form(exp), got=poly_form(got),
                                category="procedure", error_class="procedure")
        except ParseError:
            pass
    if got == exp or any(got == a for a in accepts):
        return _verdict(10, "correct", "", expected=poly_form(exp), got=poly_form(got))
    cat, note = _algebraic_category(exp, got)
    if cat == "near":
        return _verdict(7, "near", f"gairebé: s'escriu «{poly_form(exp)}»",
                        expected=poly_form(exp), got=poly_form(got))
    return _verdict(3, "wrong", note, expected=poly_form(exp), got=poly_form(got),
                    category=cat, error_class=cat)


# -------------------------------------------------------------------- CLI ---

def _to_json(obj):
    if isinstance(obj, Fraction):
        return str(obj)
    raise TypeError(type(obj))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    usage = ('usage: mathgrade.py eval EXPR | grade EXPECTED GIVEN [--accept V]... [--unit U]'
             ' | step EXPECTED LINE [--strict-form]'
             ' | poly EXPR | agrade EXPECTED GIVEN [--accept V]... [--problem P]')
    if not argv:
        print(usage, file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "eval" and len(argv) >= 2:
            p = parse_expr(argv[1])
            print(json.dumps({"value": str(p.value), "form": p.form}))
            return 0
        if cmd == "poly" and len(argv) >= 2:
            p = parse_poly(argv[1])
            print(json.dumps({"form": poly_form(p),
                              "terms": {_mono_render(k): str(v) for k, v in p.items()}}))
            return 0
        if cmd == "agrade" and len(argv) >= 3:
            rest = argv[3:]
            accepts, prob = [], None
            i = 0
            while i < len(rest):
                if rest[i] == "--accept" and i + 1 < len(rest):
                    accepts.append(rest[i + 1]); i += 2
                elif rest[i] == "--problem" and i + 1 < len(rest):
                    prob = rest[i + 1]; i += 2
                else:
                    print(usage, file=sys.stderr); return 2
            print(json.dumps(grade_algebraic(argv[1], argv[2], accepts, prob), default=_to_json))
            return 0
        if cmd == "grade" and len(argv) >= 3:
            rest = argv[3:]
            accepts, unit = [], None
            i = 0
            while i < len(rest):
                if rest[i] == "--accept" and i + 1 < len(rest):
                    accepts.append(rest[i + 1]); i += 2
                elif rest[i] == "--unit" and i + 1 < len(rest):
                    unit = rest[i + 1]; i += 2
                else:
                    print(usage, file=sys.stderr); return 2
            print(json.dumps(grade_single(argv[1], argv[2], accepts, unit), default=_to_json))
            return 0
        if cmd == "step" and len(argv) >= 3:
            strict = "--strict-form" in argv[3:]
            print(json.dumps(grade_step(argv[1], argv[2], strict), default=_to_json))
            return 0
    except ParseError as e:
        print(json.dumps({"error": str(e), "verdict": "wrong", "score": 3}))
        return 1
    print(usage, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
