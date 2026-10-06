"""Offline exercise bank: pick + deterministic grading, no model.

See PLA-EXERCICIS-TANCATS.md (project). One JSON file per competence at
curriculum/bank/<curriculum-stem>/<competence_id>.json (list of items, schema
there). Progress (what a learner has seen, and whether they got it right) is
tracked separately per learner at <data>/bank-progress.json so the bank files
themselves stay read-only content, shareable across learners.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mathgrade  # noqa: E402

NUMBERS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
           "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


def canon(a: str) -> str:
    a = str(a or "").strip().lower().replace("’", "'").replace("‘", "'")
    a = a.strip(" \t\"“”«».,;:!?")
    a = re.sub(r"\bo\s*'?\s*clock\b", "o'clock", a)
    a = re.sub(r"\bcan't\b|\bcan not\b", "cannot", a)
    a = re.sub(r"\bwon't\b", "will not", a)
    a = re.sub(r"n't\b", " not", a)
    a = re.sub(r"\b(i)'m\b", r"\1 am", a)
    a = re.sub(r"\b(you|we|they)'re\b", r"\1 are", a)
    a = re.sub(r"\b(he|she|it|there|what|where|who|how|that)'s\b", r"\1 is", a)
    if re.fullmatch(r"\d+", a) and int(a) < len(NUMBERS):
        a = NUMBERS[int(a)]
    return re.sub(r"\s+", " ", a).strip()


def osa_distance(a: str, b: str, cap: int = 2) -> int:
    """Optimal string alignment (restricted Damerau-Levenshtein): Levenshtein
    plus adjacent-transposition as one edit. Capped for speed; a return value
    of `cap` means "at least cap", never used past a <=1 check."""
    a, b = a.strip(), b.strip()
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


def _min_distance(got: str, answer: str) -> int:
    """The smaller of the distance computed on the raw (lowered, trimmed)
    forms and on the canon() forms — "dont" vs "don't" is 1 via canon."""
    raw_d = osa_distance(got.strip().lower(), answer.strip().lower())
    can_d = osa_distance(canon(got), canon(answer))
    return min(raw_d, can_d)


BLANK = re.compile(r"_{3,}")


def extract_gap(sentence: str, got: str) -> str:
    """If she typed the whole sentence instead of just the gap, keep the gap.

    Compared on canon() forms, and a part of the sentence is only stripped
    when it is really there, as whole words. The first version stripped the
    RAW length of the suffix whenever canon(suffix) matched — and canon(".")
    is "", which every string ends with: "Ten plus ten is ___." graded the
    exact answer "twenty" as "twent" -> 7/10 (found 2026-09-24, 8 bank items).
    """
    m = BLANK.search(sentence)
    if not m:
        return got
    # Word by word, punctuation aside: "This is my father. ___ car is red."
    # has a full stop INSIDE the part before the gap.
    words = lambda t: re.findall(r"[a-z0-9']+", canon(t))
    # A hint in brackets ("It ___ (rain).") is not part of the sentence she
    # writes: left in, "is going to rain" lost its "rain" as if it were the
    # sentence's own ending (a2.future_going_to_will).
    hintless = lambda t: re.sub(r"\([^()]*\)", " ", t)
    pre, suf, g = words(hintless(sentence[: m.start()])), words(hintless(sentence[m.end():])), words(got)
    if pre and len(g) > len(pre) and g[: len(pre)] == pre:
        g = g[len(pre):]
    if suf and len(g) > len(suf) and g[-len(suf):] == suf:
        g = g[: -len(suf)]
    return " ".join(g) or canon(got)


def bank_dir(root: Path, curriculum_stem: str) -> Path:
    return root / "curriculum" / "bank" / curriculum_stem


def profile_bank_dir(data_dir: str | os.PathLike) -> Path:
    """The learner's own exercises, for the competences in her `extra.md`
    (hooks/curriculum.py add_profile_extras)."""
    return Path(data_dir) / "bank"


def _bank_base_dirs(root: Path, curriculum_stem: str,
                    data_dir: str | os.PathLike | None = None) -> list[Path]:
    """The bank dirs themselves (not their `steps/` subdirs): the level's bank,
    then the learner's."""
    dirs = [bank_dir(root, curriculum_stem)]
    if data_dir:
        dirs.append(profile_bank_dir(data_dir))
    return [d for d in dirs if d.is_dir()]


def bank_dirs(root: Path, curriculum_stem: str, data_dir: str | os.PathLike | None = None) -> list[Path]:
    """Where a competence's items can live: the level's bank, then the learner's.
    WP2.2: each bank dir's `steps/` subdir (worked solutions, `<cid>__steps.json`)
    is part of the walk, so the file-enumerating consumers (bank_left,
    curriculum.py's _bank_index) see them too. They stay OUT of
    `curriculum/bank/*/*.json` — the one-level glob tests/test_bank_review.py's
    TheWholeBank uses — on purpose."""
    out: list[Path] = []
    for d in _bank_base_dirs(root, curriculum_stem, data_dir):
        out.append(d)
        if (d / "steps").is_dir():
            out.append(d / "steps")
    return out


def load_bank(root: Path, curriculum_stem: str, competence_id: str,
              data_dir: str | os.PathLike | None = None) -> list[dict]:
    """A competence's servable items: its `<cid>.json` plus, since WP2.2, the
    worked solutions in `steps/<cid>__steps.json`. The status filter is the
    gate: `generated` items (a steps family before WP2.3 validated it) are
    never served."""
    for d in _bank_base_dirs(root, curriculum_stem, data_dir):
        items: list[dict] = []
        for f in (d / f"{competence_id}.json", d / "steps" / f"{competence_id}__steps.json"):
            if f.exists():
                items += json.loads(f.read_text(encoding="utf-8"))
        if items:
            return [it for it in items if it.get("status") in ("validated", "reviewed")]
    return []


def has_bank(root: Path, curriculum_stem: str, competence_id: str,
             data_dir: str | os.PathLike | None = None) -> bool:
    return bool(load_bank(root, curriculum_stem, competence_id, data_dir))


def _progress_path(data_dir: str | os.PathLike) -> Path:
    return Path(data_dir) / "bank-progress.json"


def _load_progress(data_dir: str | os.PathLike) -> dict:
    p = _progress_path(data_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_progress(data_dir: str | os.PathLike, prog: dict) -> None:
    p = _progress_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(prog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


BANK_LOW = 3   # unseen items at or below which the bank is "running out" for her


def bank_left(root: Path, curriculum_stem: str, data_dir: str | os.PathLike) -> dict[str, dict]:
    """{competence: {"unseen": n, "total": m}} for one learner. Once `unseen`
    reaches 0 the bank recycles her oldest items — it never blocks a turn —
    so this is the number that says it is time to add some."""
    prog = _load_progress(data_dir)
    out: dict[str, dict] = {}
    files = [f for d in bank_dirs(root, curriculum_stem, data_dir) for f in sorted(d.glob("*.json"))]
    for f in files:
        # WP2.2: a steps file is named `<cid>__steps.json` — it counts towards
        # its competence, not a phantom "<cid>__steps" one. load_bank already
        # merges the main file and the steps file, so the first sighting wins.
        cid = f.stem[: -len("__steps")] if f.stem.endswith("__steps") else f.stem
        if cid in out:
            continue
        items = load_bank(root, curriculum_stem, cid, data_dir)
        if items:
            seen = prog.get(cid, {})
            out[cid] = {"unseen": sum(1 for it in items if it["id"] not in seen), "total": len(items)}
    return out


def pick_item(root: Path, curriculum_stem: str, competence_id: str, data_dir: str | os.PathLike,
              today: str) -> dict | None:
    """Wrong last time, first; then never seen; then the one not seen longest
    (>= 7 days preferred, else whichever is oldest — the bank never blocks a
    turn for lack of a fresh item)."""
    items = load_bank(root, curriculum_stem, competence_id, data_dir)
    if not items:
        return None
    prog = _load_progress(data_dir).get(competence_id, {})
    from datetime import date as _date
    def days_since(iso: str) -> int:
        try:
            return (_date.fromisoformat(today) - _date.fromisoformat(iso)).days
        except ValueError:
            return 9999
    wrong, unseen, seen = [], [], []
    for it in items:
        rec = prog.get(it["id"])
        if not rec:
            unseen.append(it)
        elif not rec.get("correct", True):
            wrong.append((it, days_since(rec["date"])))
        else:
            seen.append((it, days_since(rec["date"])))
    if wrong:
        wrong.sort(key=lambda t: -t[1])
        return wrong[0][0]
    if unseen:
        return unseen[0]
    seen.sort(key=lambda t: -t[1])
    return seen[0][0] if seen else items[0]


def _is_inflection(a: str, b: str) -> bool:
    """play/plays, watch/watches, like/liked, work/working, study/studies,
    have/has: another FORM of the same word, not a slip of the finger. In a
    grammar exercise that difference is the whole point — "He play" for "He
    plays" is exactly the mistake present simple is teaching, and it came out
    as a 7/10 "almost" because the two are one letter apart (2026-09-24)."""
    a, b = a.strip().lower(), b.strip().lower()
    if a == b:
        return False
    short, long_ = sorted((a, b), key=len)
    for suf in ("s", "es", "d", "ed", "ing", "'s"):
        if long_ == short + suf:
            return True
    if short.endswith("e") and long_ == short[:-1] + "ing":
        return True
    if short.endswith("y") and long_ == short[:-1] + "ies":
        return True
    return {a, b} in ({"have", "has"}, {"do", "does"}, {"is", "are"}, {"am", "is"}, {"was", "were"})


def _same_lesson_other_word(candidate: str, item: dict, comp: dict | None) -> bool:
    """A different valid word from the lesson (there/three, those/these) —
    not a spelling slip, a mix-up. 🔴 even at distance <= 1."""
    pool = set(item.get("options") or [])
    if comp:
        pool |= set(comp.get("words") or [])
        pool |= {t for t in comp.get("tags", []) if not t.startswith("#")}
    cand = canon(candidate)
    ans = canon(item["answer"])
    return any(canon(w) == cand and canon(w) != ans for w in pool)


def _full_sentence(item: dict) -> str:
    """"Correct version:" always shows the whole sentence, filled in — a bare
    answer word ("plays") is not what the learner is meant to check against."""
    if item["type"] in ("meaning", "translate", "correct"):
        return item["answer"]
    m = BLANK.search(item["sentence"])
    if not m:
        return item["answer"]
    whole = item["sentence"][: m.start()] + item["answer"] + item["sentence"][m.end():]
    # The hint in brackets is scaffolding, not part of the sentence: the
    # correct version read "There are five children (child) in the park."
    whole = re.sub(r"\s*\([^()]*\)", "", whole)
    return re.sub(r"\s+([.,!?])", r"\1", whole).strip()


# ---- math bank types (DISSENY-MATEMATIQUES §4.1/§4.3, WP1.3) -----------------
# compute/choose/compare items carry a `problem` instead of a `sentence` and are
# graded by hooks/mathgrade.py (exact rational arithmetic), not by canon/OSA.
# `choose` exists in BOTH domains: the language one blanks a "___" in a
# sentence, the math one offers options for a problem — the presence of
# `problem` (and absence of `sentence`) is what tells them apart.

MATH_TYPES = ("compute", "choose", "compare")

_MATH_EMPTY = set(mathgrade.EMPTY_ANSWERS) | {"no se", "no ho se", "no sé", "no ho sé", "i don't know"}

# v1 (deliberate, §4.3): the three symbols plus the Catalan words a nine-year-old
# writes. ">=" and friends are NOT accepted — the item's options are >, <, =.
_COMPARE_WORDS = {
    ">": ">", "major que": ">", "major": ">", "més gran que": ">", "mes gran que": ">", "gran que": ">",
    "<": "<", "menor que": "<", "menor": "<", "menys que": "<", "petit que": "<", "petita que": "<",
    "=": "=", "igual": "=", "igual que": "=", "igual a": "=",
}


def _is_math_item(item: dict) -> bool:
    t = item.get("type")
    if t in ("compute", "compare", "steps"):
        return True
    return t == "choose" and "problem" in item and "sentence" not in item


def _math_is_empty(text: str) -> bool:
    t = str(text or "").strip().lower().strip("?!.").strip()
    return t in _MATH_EMPTY


def _normalize_compare(text: str) -> str | None:
    t = re.sub(r"\s+", " ", str(text or "").strip().lower().replace("’", "'").strip(".,;:!? "))
    return _COMPARE_WORDS.get(t)


def _math_correct_version(item: dict) -> str:
    """"Correct version:" for a math item: the problem with the answer filled in.

    WP3.2 word problems: `problem` is a story and the arithmetic is in
    `expression` — the canonical version shows both, "story → 24 ÷ 6 = 4", so
    the learner sees the setup the story called for, not just the number."""
    prob = str(item.get("problem", ""))
    ans = str(item["answer"])
    if item.get("type") == "compute" and item.get("expression"):
        return f"{prob} → {item['expression']} = {ans}"
    if item.get("type") == "compare":
        for ph in ("○", "◯", "⃝", "…"):
            if ph in prob:
                return prob.replace(ph, ans)
        return f"{prob} {ans}".strip()
    if item.get("type") == "choose":
        # a pick from options, not an equation: "Quina operació…? → 5×2"
        return f"{prob} → {ans}"
    try:
        mathgrade._parse_with_unit(ans)  # "12 cm" is still a value: use "="
        return f"{prob} = {ans}"
    except mathgrade.ParseError:
        return f"{prob} → {ans}"


# ---- steps items (DISSENY-MATEMATIQUES §4.2, WP2.3) --------------------------
# v1 "all-at-once": the learner types the WHOLE worked solution, one operation
# per line. Lines align to item.steps IN ORDER — line i (blank lines skipped)
# is step i; extra lines are ignored; a step with no line is missing. Each
# line must match the step's expected FORM (when the step expects one, i.e.
# `expect` is not a bare value) AND its VALUE; `accept` lists alternate ways of
# writing the same step. The FIRST step that is not fully correct decides the
# reported error (its error_class); every later step is marked `propagated`
# and NOT graded independently — one slip is never counted several times
# (§4.2, and the §7 risk row "error propagat com a diversos errors").

def _split_assertion(text: str) -> tuple[str, str | None]:
    """('expression side', 'value side or None') of a step line or candidate,
    split on the LAST '='. More than one '=' is a ParseError (mathgrade's
    rule for step lines)."""
    s = str(text or "").strip()
    if s.count("=") > 1:
        raise mathgrade.ParseError("a step line may contain at most one '='")
    if "=" in s:
        left, right = s.rsplit("=", 1)
        return left.strip(), right.strip()
    return s, None


def _is_pure_value(text: str) -> bool:
    """True when `text` is a bare value ("5/8", "43", "8 3/5"), not a form —
    the same test mathgrade.grade_step uses to choose value-vs-form matching."""
    try:
        s = mathgrade._normalize(text)
    except mathgrade.ParseError:
        return False
    return bool(mathgrade._PURE_VALUE.match(re.sub(r"\s+", "", s)))


def _grade_step_line(step: dict, line: str) -> dict:
    """One learner line against one expected step. Verdicts parallel
    mathgrade's: correct / near (the step's operation is right but its
    written value is a one-edit digit slip of the expected value — the
    transposition rule of §4.3) / wrong. Returns {"verdict", "got", "note"}."""
    exp_form = str(step.get("expect", ""))
    exp_val_txt = str(step.get("value", "")) or exp_form
    try:
        exp_val = mathgrade.parse_expr(exp_val_txt).value
    except mathgrade.ParseError:
        exp_val = None
    try:
        _, l_val_txt = _split_assertion(line)
        l_val = mathgrade.parse_expr(l_val_txt if l_val_txt is not None else line).value
    except mathgrade.ParseError:
        return {"verdict": "wrong", "got": str(line).strip(), "note": "no s'ha entès l'operació"}
    form_ok_value_off = False
    for cand in [exp_form, *[str(a) for a in step.get("accept", [])]]:
        try:
            c_form_txt, c_val_txt = _split_assertion(cand)
            c_val = mathgrade.parse_expr(c_val_txt if c_val_txt is not None else cand).value
        except mathgrade.ParseError:
            continue
        try:
            r = mathgrade.grade_step(c_form_txt, line)
        except mathgrade.ParseError:
            continue
        if r["verdict"] != "correct":
            continue
        if l_val == c_val:
            return {"verdict": "correct", "got": str(line).strip(), "note": ""}
        # the operation matched but the asserted result did not: a slip here
        # is "near", a different number is wrong.
        form_ok_value_off = True
    if exp_val is not None and (form_ok_value_off or _is_pure_value(exp_form)):
        slip_txt = l_val_txt if l_val_txt is not None else str(line).strip()
        if mathgrade._near_slip(slip_txt, exp_val_txt):
            return {"verdict": "near", "got": str(line).strip(),
                    "note": f"gairebé: aquest pas dona «{exp_val_txt}»"}
    return {"verdict": "wrong", "got": str(line).strip(), "note": ""}


def _steps_correct_version(item: dict) -> str:
    """The full correct trace: one "expect = value" line per step (a step
    whose value IS its expect — the final bare result — is just that)."""
    lines = []
    for s in item.get("steps", []):
        exp, val = str(s.get("expect", "")), str(s.get("value", ""))
        lines.append(f"{exp} = {val}" if val and val != exp else exp)
    return "\n".join(lines)


def _grade_steps(item: dict, raw_answer: str) -> dict:
    """Grade a whole worked solution (WP2.3). The result carries `steps`:
    one entry per EXPECTED step — {n, ok, got} plus `propagated: true` on
    every step after the first failure — and `error_class`/`failed_step`
    naming the first failure, so the server can file one pattern and paint
    the annotated trace."""
    full = _steps_correct_version(item)
    steps = item.get("steps", [])
    lines = [ln.strip() for ln in str(raw_answer or "").splitlines() if ln.strip()]
    if not lines or (len(lines) == 1 and _math_is_empty(lines[0])):
        return {"score": 0, "verdict": "empty", "note": str(item.get("why", "")),
                "correct_version": full, "got": "",
                "steps": [{"n": s.get("n"), "ok": False, "got": None} for s in steps]}
    trace: list[dict] = []
    first_fail: int | None = None
    first_verdict = ""      # "near" | "wrong"
    first_cat = ""          # the pattern category
    first_note = ""
    for i, s in enumerate(steps):
        n = s.get("n")
        line = lines[i] if i < len(lines) else None
        if first_fail is not None:
            # failed by propagation: NOT graded on its own merits.
            trace.append({"n": n, "ok": False, "got": line, "propagated": True})
            continue
        if line is None:
            first_fail, first_verdict = n, "wrong"
            first_cat, first_note = "incomplete", "has deixat aquest pas sense fer"
            trace.append({"n": n, "ok": False, "got": None})
            continue
        r = _grade_step_line(s, line)
        if r["verdict"] == "correct":
            trace.append({"n": n, "ok": True, "got": line})
            continue
        first_fail, first_verdict = n, r["verdict"]
        # a digit slip is a calculation error whatever the step's class is;
        # a real wrong step is filed under the step's own error_class (§4.2).
        first_cat = "calculation" if r["verdict"] == "near" else str(s.get("error_class") or "calculation")
        first_note = r["note"] or str(s.get("why", ""))
        trace.append({"n": n, "ok": False, "got": line})
    if first_fail is None:
        return {"score": 10, "verdict": "correct", "note": "", "correct_version": full, "steps": trace}
    got_line = next((t["got"] for t in trace if t["n"] == first_fail), None)
    return {"score": 7 if first_verdict == "near" else 3, "verdict": first_verdict,
            "note": first_note, "correct_version": full, "got": got_line or "",
            "error_class": first_cat, "failed_step": first_fail, "steps": trace}


# ---- v2 incremental steps (WP2.5, §4.2 "v2 pas a pas") -----------------------
# The learner solves a steps item ONE STEP PER MESSAGE. The session state —
# which item, which step pending, failed attempts on it — lives in the server
# (server/src/agent.ts + server/src/steps.ts); these two functions are the
# stateless half:
#
#   grade_step(item, n, line)      one line against step n, reusing
#                                  `_grade_step_line` verbatim (form AND value,
#                                  `accept` alternates, near-slip). Writes NO
#                                  progress: the item is only recorded when the
#                                  trace is complete.
#   finalize_steps(item, results)  the record payload from the per-step
#                                  results, in `_grade_steps`' shape so the
#                                  feedback renderer, the .records writer and
#                                  SM-2 read a v2 record exactly like a v1 one.
#
# v2 has NO propagation — every step was attempted on its own merits — so the
# trace entries carry no `propagated` flag. The score mirrors v1's scale
# exactly (the §7 "one slip, not three" rule survives):
#   every step right on the first try            → 10 ("correct")
#   every step right, but one needed a retry     → 7  ("near")
#   a step had to be revealed (2 failed tries)   → 3  ("wrong")
# `failed_step`/`error_class` name the first step that FAILED outright (a
# revealed one) when there is one, else the first step that needed a retry;
# a revealed step's category is its own error_class, a retried step's is
# "calculation" when its first slip was a digit slip (the v1 near rule).

def grade_step(item: dict, step_n, line: str) -> dict:
    """Grade ONE learner line against step `step_n` of a steps item (v2)."""
    step = next((s for s in item.get("steps", []) if s.get("n") == step_n), None)
    if step is None:
        return {"error": f"step {step_n!r} not in item {item.get('id')!r}"}
    r = _grade_step_line(step, str(line or ""))
    exp, val = str(step.get("expect", "")), str(step.get("value", ""))
    r["error_class"] = ("calculation" if r["verdict"] == "near"
                        else str(step.get("error_class") or "calculation"))
    r["why"] = str(step.get("why", ""))
    r["expect_line"] = f"{exp} = {val}" if val and val != exp else exp
    return r


def finalize_steps(item: dict, results: list[dict]) -> dict:
    """The v2 record payload (see the block above). `results` is one entry per
    step, in order: {n, ok, got, attempts, revealed?, first_wrong?, near?}."""
    full = _steps_correct_version(item)
    steps = item.get("steps", [])
    by_n = {r.get("n"): r for r in results}
    trace = [{"n": s.get("n"), "ok": bool((by_n.get(s.get("n")) or {}).get("ok")),
              "got": (by_n.get(s.get("n")) or {}).get("got")} for s in steps]
    revealed = next((s for s in steps if not (by_n.get(s.get("n")) or {}).get("ok")), None)
    retried = next((s for s in steps
                    if (by_n.get(s.get("n")) or {}).get("ok")
                    and int((by_n.get(s.get("n")) or {}).get("attempts") or 1) > 1), None)
    if revealed is None and retried is None:
        return {"score": 10, "verdict": "correct", "note": "", "correct_version": full,
                "steps": trace, "mode": "v2"}
    bad = revealed if revealed is not None else retried
    r = by_n.get(bad.get("n")) or {}
    near = bool(r.get("near")) and revealed is None
    cat = "calculation" if near else str(bad.get("error_class") or "calculation")
    if revealed is None:
        return {"score": 7, "verdict": "near",
                "note": f"el pas {bad.get('n')} va necessitar un segon intent",
                "correct_version": full, "got": str(r.get("first_wrong") or ""),
                "error_class": cat, "failed_step": bad.get("n"), "steps": trace, "mode": "v2"}
    return {"score": 3, "verdict": "wrong",
            "note": f"el pas {bad.get('n')} no et sortia; te'l vaig haver de revelar",
            "correct_version": full, "got": str(r.get("first_wrong") or r.get("got") or ""),
            "error_class": cat, "failed_step": bad.get("n"), "steps": trace, "mode": "v2"}


def answer_and_record_steps(root: Path, curriculum_stem: str, item_id: str, competence_id: str,
                            results: list[dict], data_dir: str | os.PathLike, today: str,
                            comp: dict | None = None) -> dict:
    """finalize_steps + the progress write answer_and_record does (v2: the
    item is recorded once, when its trace is complete)."""
    items = {it["id"]: it for it in load_bank(root, curriculum_stem, competence_id, data_dir)}
    item = items.get(item_id)
    if not item:
        return {"error": f"item {item_id!r} not found in bank for {competence_id}"}
    result = finalize_steps(item, results)
    prog = _load_progress(data_dir)
    prog.setdefault(competence_id, {})[item_id] = {"date": today, "correct": result["score"] >= 8}
    _save_progress(data_dir, prog)
    return {**result, "item": item}


def _grade_math(item: dict, raw_answer: str) -> dict:
    full = _math_correct_version(item)
    t = item.get("type")
    if t == "steps":
        return _grade_steps(item, raw_answer)
    if t == "compare":
        if _math_is_empty(raw_answer):
            return {"score": 0, "verdict": "empty", "note": item.get("why", ""), "correct_version": full}
        got = _normalize_compare(raw_answer)
        if got == str(item["answer"]).strip():
            return {"score": 10, "verdict": "correct", "note": "", "correct_version": full}
        return {"score": 3, "verdict": "wrong", "note": item.get("why", ""), "correct_version": full,
                "got": str(raw_answer).strip()}
    given = str(raw_answer or "").strip()
    if t == "choose":
        # Options can be non-numeric ("5×2" as a CHOICE of operation, not an
        # evaluation): exact text first, then mathgrade for numeric variants.
        norm = {str(a).strip().lower() for a in [item["answer"], *item.get("also_accept", [])]}
        if given.lower() in norm:
            return {"score": 10, "verdict": "correct", "note": "", "correct_version": full}
        r = mathgrade.grade_single(item["answer"], given, item.get("also_accept", []))
        # A discrete choice has no "almost": picking a DIFFERENT option is wrong
        # even when it is one digit off (the language path's same-lesson-other-
        # word rule, in math clothes).
        if r["verdict"] == "near":
            r = {"score": 3, "verdict": "wrong", "note": item.get("why", ""), "expected": r.get("expected"),
                 "got": r.get("got")}
        r["correct_version"] = full
        return r
    # compute: "1/4 + 3/8 = 5/8" typed as a full equation grades the result.
    if given.count("=") == 1:
        given = given.rsplit("=", 1)[1]
    r = mathgrade.grade_single(item["answer"], given, item.get("also_accept", []))
    if r["verdict"] in ("wrong", "empty") and not r.get("note"):
        r["note"] = item.get("why", "")  # the language path's rule: wrong explains
    r["correct_version"] = full
    return r


def grade(item: dict, raw_answer: str, comp: dict | None = None) -> dict:
    """Deterministic verdict. Does not touch progress — the caller records it."""
    if _is_math_item(item):
        return _grade_math(item, raw_answer)
    answers = [item["answer"], *item.get("also_accept", [])]
    full = _full_sentence(item)
    if item["type"] == "correct":
        got_w = re.findall(r"[a-z0-9']+", canon(raw_answer))
        for target in answers:
            want_w = re.findall(r"[a-z0-9']+", canon(target))
            if got_w == want_w:
                return {"score": 10, "verdict": "correct", "note": "", "correct_version": full}
        # One letter off in ONE word of the sentence is "almost", not wrong —
        # the same rule as a gap (OSA <= 1, words of 5+ letters, never another
        # word of the lesson). A whole sentence retyped for one slip was 3/10.
        for target in answers:
            want_w = re.findall(r"[a-z0-9']+", canon(target))
            if len(got_w) != len(want_w):
                continue
            diff = [(g, w) for g, w in zip(got_w, want_w) if g != w]
            if len(diff) == 1:
                g, w = diff[0]
                if (len(w) >= 5 and osa_distance(g, w) <= 1 and not _is_inflection(g, w)
                        and not _same_lesson_other_word(g, {**item, "answer": w}, comp)):
                    return {"score": 7, "verdict": "typo", "note": f'gairebé: s\'escriu "{w}"', "correct_version": full}
        return {"score": 3, "verdict": "wrong", "note": item.get("why", ""), "correct_version": full}
    got = extract_gap(item["sentence"], raw_answer)
    if not got.strip() or canon(got) in ("i don't know", "no se", "no ho se"):
        return {"score": 0, "verdict": "empty", "note": item.get("why", ""), "correct_version": full}
    if canon(got) in {canon(a) for a in answers}:
        return {"score": 10, "verdict": "correct", "note": "", "correct_version": full}
    if _same_lesson_other_word(got, item, comp):
        return {"score": 3, "verdict": "wrong", "note": item.get("why", ""), "correct_version": full}
    if len(item["answer"]) >= 5 and not any(_is_inflection(canon(got), canon(a)) for a in answers):
        d = min(_min_distance(got, a) for a in answers)
        if d <= 1:
            return {"score": 7, "verdict": "typo", "note": f'gairebé: s\'escriu "{item["answer"]}"',
                    "correct_version": full}
    return {"score": 3, "verdict": "wrong", "note": item.get("why", ""), "correct_version": full}


def answer_and_record(root: Path, curriculum_stem: str, item_id: str, competence_id: str, raw_answer: str,
                       data_dir: str | os.PathLike, today: str, comp: dict | None = None) -> dict:
    items = {it["id"]: it for it in load_bank(root, curriculum_stem, competence_id, data_dir)}
    item = items.get(item_id)
    if not item:
        return {"error": f"item {item_id!r} not found in bank for {competence_id}"}
    result = grade(item, raw_answer, comp)
    prog = _load_progress(data_dir)
    # KNOWN_SCORE (server/src/pacing.ts) is 8: a 7/10 "almost" does not count as known,
    # so it keeps coming back until she gets it exactly right.
    prog.setdefault(competence_id, {})[item_id] = {"date": today, "correct": result["score"] >= 8}
    _save_progress(data_dir, prog)
    return {**result, "item": item}
