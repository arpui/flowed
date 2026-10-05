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

  CLI: python3 hooks/mathgrade.py eval "1 1/2 + 1/4"
       python3 hooks/mathgrade.py grade "3/4" "0,75"
       python3 hooks/mathgrade.py step "2/8 + 3/8" "1/4+3/8 = 2/8+3/8"

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


# -------------------------------------------------------------------- CLI ---

def _to_json(obj):
    if isinstance(obj, Fraction):
        return str(obj)
    raise TypeError(type(obj))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    usage = ('usage: mathgrade.py eval EXPR | grade EXPECTED GIVEN [--accept V]... [--unit U]'
             ' | step EXPECTED LINE [--strict-form]')
    if not argv:
        print(usage, file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "eval" and len(argv) >= 2:
            p = parse_expr(argv[1])
            print(json.dumps({"value": str(p.value), "form": p.form}))
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
