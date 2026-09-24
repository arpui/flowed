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
from pathlib import Path

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


def load_bank(root: Path, curriculum_stem: str, competence_id: str) -> list[dict]:
    f = bank_dir(root, curriculum_stem) / f"{competence_id}.json"
    if not f.exists():
        return []
    items = json.loads(f.read_text(encoding="utf-8"))
    return [it for it in items if it.get("status") in ("validated", "reviewed")]


def has_bank(root: Path, curriculum_stem: str, competence_id: str) -> bool:
    return bool(load_bank(root, curriculum_stem, competence_id))


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
    d = bank_dir(root, curriculum_stem)
    prog = _load_progress(data_dir)
    out: dict[str, dict] = {}
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        items = load_bank(root, curriculum_stem, f.stem)
        if items:
            seen = prog.get(f.stem, {})
            out[f.stem] = {"unseen": sum(1 for it in items if it["id"] not in seen), "total": len(items)}
    return out


def pick_item(root: Path, curriculum_stem: str, competence_id: str, data_dir: str | os.PathLike,
              today: str) -> dict | None:
    """Wrong last time, first; then never seen; then the one not seen longest
    (>= 7 days preferred, else whichever is oldest — the bank never blocks a
    turn for lack of a fresh item)."""
    items = load_bank(root, curriculum_stem, competence_id)
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


def grade(item: dict, raw_answer: str, comp: dict | None = None) -> dict:
    """Deterministic verdict. Does not touch progress — the caller records it."""
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
    items = {it["id"]: it for it in load_bank(root, curriculum_stem, competence_id)}
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
