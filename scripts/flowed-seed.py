#!/usr/bin/env python3
"""Give a test profile a believable past.

`test-en` is empty, so every live test so far has exercised the one path a real
learner almost never takes: a lesson with nothing due and nothing to drill. The
review queue, the spacing, the "what she got wrong last Tuesday comes back
today" — none of it has ever run against the model.

This builds that past with the real pipeline (`update-db.py`, the real SM-2),
day by day, so the profile that comes out is one the app itself could have
produced: some words mastered and far away, some due today, some patterns still
weak.

    python3 scripts/flowed-seed.py test-en --days 21
    python3 scripts/flowed-seed.py test-en --days 21 --due 4   # 6 per defecte = una lliçó

Refuses anything that is not a scratch profile: the answers here are invented,
and a learner's real history is not a thing to invent.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from main_paths import profiles_root  # noqa: E402  (where the profiles live)

REPO = Path(__file__).resolve().parent.parent
SCRATCH = re.compile(r"^(test|demo|e2e)", re.I)

# Plausible A1 English for a Catalan speaker, with the mistake a beginner makes.
#
# Big on purpose. The bench answers fifteen times across a Lesson and two
# Vocabulary visits; with ten items the same few concepts came round again and
# every repeat was ambiguous — the tutor's, or the rig running out of things to
# ask? With thirty distinct ones, six due and the rest waiting or weak, a repeat
# is the tutor's.
#
#   VOCAB    (english, catalan): the item's `content` is the CATALAN prompt and
#            its `answer` the English word, so "What is the English for 'casa'?"
#            is a real exercise. Seeded as content "house" (the answer itself) it
#            was not: the tutor asked for the English word for "because".
#   GRAMMAR  (category, right, wrong): `right` is a whole sentence, so an
#            exercise built from it has something to change.
VOCAB = [
    ("house", "casa"), ("water", "aigua"), ("bread", "pa"), ("school", "escola"),
    ("morning", "matí"), ("window", "finestra"), ("kitchen", "cuina"),
    ("friend", "amic"), ("dog", "gos"), ("rain", "pluja"), ("book", "llibre"),
    ("street", "carrer"), ("breakfast", "esmorzar"), ("weather", "temps"),
]
GRAMMAR = [
    ("agreement", "She goes to school", "She go to school"),
    ("agreement", "He has two brothers", "He have two brothers"),
    ("agreement", "They are happy", "They is happy"),
    ("tenses", "I woke up at seven yesterday", "I wake up at seven yesterday"),
    ("tenses", "We visited Paris last year", "We visit Paris last year"),
    ("tenses", "She has lived here for two years", "She lives here since two years"),
    ("capitalization", "I speak English on Mondays", "i speak english on mondays"),
    ("capitalization", "My birthday is in July", "my birthday is in july"),
    ("spelling", "because", "becouse"),
    ("spelling", "tomorrow", "tomorow"),
    ("spelling", "friend", "freind"),
    ("articles", "I eat an apple every day", "I eat a apple every day"),
    ("articles", "I have a dog", "I have dog"),
    ("articles", "The sun is hot", "Sun is hot"),
    ("prepositions", "I am interested in music", "I am interested on music"),
    ("prepositions", "She arrived at the station", "She arrived to the station"),
    ("grammar", "two children", "two childs"),
    ("word_order", "I always drink coffee", "I drink always coffee"),
]
# What is due TODAY, in this order, when `--due N`: a mix, never six of a kind.
DUE_ORDER = ["vocabulary:morning", "agreement:She goes to school",
             "tenses:I woke up at seven yesterday", "capitalization:I speak English on Mondays",
             "articles:I eat an apple every day", "vocabulary:window", "spelling:because",
             "prepositions:I am interested in music"]


def due_order(items: list[dict]) -> list[str]:
    """Every item, in the order `--due N` makes them due.

    The first eight are the hand-picked mix. Past those a big lesson (15
    pending) takes what is left alternating vocabulary and grammar, so no
    request is ever fifteen of a kind."""
    rest = [m for m in items if m["key"] not in DUE_ORDER]
    vocab = [m["key"] for m in rest if m["kind"] == "vocab"]
    gram = [m["key"] for m in rest if m["kind"] != "vocab"]
    mixed: list[str] = []
    for i in range(max(len(vocab), len(gram))):
        mixed += [lst[i] for lst in (gram, vocab) if i < len(lst)]
    return DUE_ORDER + mixed


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:28]


def material() -> list[dict]:
    """Every item as one dict: id, kind, and what the hook needs."""
    out = []
    for en, ca in VOCAB:
        out.append({"key": f"vocabulary:{en}", "id": f"vocabulary_{slug(en)}", "kind": "vocab",
                    "category": "vocabulary", "content": ca, "answer": en})
    for cat, right, wrong in GRAMMAR:
        out.append({"key": f"{cat}:{right}", "id": f"{cat}_{slug(right)}", "kind": "error",
                    "category": cat, "right": right, "wrong": wrong})
    return out


def introduce(item: dict) -> dict:
    """The payload fragment that makes the hook create this item."""
    if item["kind"] == "vocab":
        return {"new_vocabulary": [{"item_id": item["id"], "item_type": "vocabulary",
                                    "content": item["content"], "answer": item["answer"],
                                    "category": "vocabulary", "priority": "medium"}]}
    return {"errors": [{"pattern_id": item["id"], "category": item["category"],
                        "your_answer": item["wrong"], "correct_answer": item["right"],
                        "context": "", "severity": "moderate"}]}


def update(prof: Path, payload: dict) -> None:
    p = subprocess.run(
        [sys.executable, str(REPO / "hooks" / "update-db.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env={"FLOWED_DATA_DIR": str(prof), "FLOWED_ROOT": str(REPO),
             "PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
        cwd=REPO, timeout=60)
    if p.returncode != 0:
        raise SystemExit(f"update-db.py ha fallat: {p.stderr.strip()[:300]}")


def archive(d: Path) -> int:
    """Move a directory's live files into `_archive/`, once.

    The old scheme renamed each file to `.<name>.bak-seed` IN PLACE, and the
    glob that found them matched the archives too. Twelve sweeps later the
    names looked like

        ................lesson-2026-09-16.json.bak-20260919-122651.bak-…

    and the thirteenth died with ENAMETOOLONG **before seeding anything**. The
    bench ran three executions on a profile with 14 stale items and nothing due,
    and reported them as if they had been seeded. An archive is a place, not a
    suffix.
    """
    if not d.is_dir():
        return 0
    out = d / "_archive"
    moved = 0
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in d.iterdir():
        # A day archived by flowed-advance-day.py (".<name>.day-<stamp>") is history of a
        # run that is over: leaving it makes the next run's "yesterday" checks read it.
        if f.is_dir() or (f.name.startswith(".") and ".day-" not in f.name):
            continue  # already archived by an older version of this script
        out.mkdir(exist_ok=True)
        f.rename(out / f"{stamp}-{f.name}")
        moved += 1
    return moved


def due_on(prof: Path, day: str) -> list[str]:
    try:
        sr = json.loads((prof / "spaced-repetition.json").read_text())
    except Exception:
        return []
    return [k for k, v in (sr.get("items") or {}).items()
            if isinstance(v.get("due_date"), str) and v["due_date"] <= day]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("profile", nargs="?", default="test-en")
    ap.add_argument("--dir", help="directori de perfil explícit")
    ap.add_argument("--days", type=int, default=21, help="quants dies de passat")
    ap.add_argument("--due", type=int, default=6,
                    help="quants ítems han de quedar per repassar AVUI")
    args = ap.parse_args()

    prof = Path(args.dir).expanduser() if args.dir else profiles_root() / args.profile
    if not (prof / "learner-profile.json").exists():
        print(f"❌ perfil no trobat: {prof}", file=sys.stderr)
        return 2
    if not SCRATCH.match(prof.name):
        print(f"❌ només en perfils de proves (test*/demo*/e2e*), no en {prof.name}", file=sys.stderr)
        return 2

    # A past is a past: today has to start empty. Leaving this morning's plan in
    # place made a seeded run look like a catastrophe — the lesson was already
    # 6 of 6 before the first question, so the tutor correctly said "complete",
    # asked nothing, and every check that counts exercises reported zero.
    stamp = date.today().isoformat()
    archive(prof / ".daily")
    archive(prof / ".records")
    # Same reason: a T0 left behind rolls the seeded profile back the moment a
    # session with a colliding id is finalised.
    archive(prof / ".update-state")
    draft = prof / "session-draft.json"
    if draft.exists():
        draft.rename(prof / "session-draft.json.bak-seed")
    print(f"avui ({stamp}) buidat abans de sembrar")

    # And the PAST too. This script used to build its 21 days on top of whatever
    # the last test left behind, so the second sweep of the day seeded a profile
    # that already had those items scheduled weeks away: `--due 3` produced 0 due,
    # the lesson ran with nothing to review, and every record came back without an
    # item_id. The rig was quietly measuring a different profile each time — the
    # same family of bug as `--repeat` consuming the day. A seeded past is one this
    # script built, start to finish.
    blanked = []
    for name, keys in (("spaced-repetition.json", ("items", "review_queue")),
                       ("mistakes-db.json", ("error_patterns",))):
        f = prof / name
        if not f.exists():
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        f.with_suffix(f.suffix + ".bak-seed").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for k in keys:
            if isinstance(doc.get(k), dict):
                doc[k] = {k2: ([] if isinstance(v2, list) else {})
                          for k2, v2 in doc[k].items()} if k == "review_queue" else {}
        f.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        blanked.append(name)
    if blanked:
        print(f"cua i patrons reiniciats ({', '.join(blanked)}; còpia a *.bak-seed)")

    start = date.today() - timedelta(days=args.days)
    items = material()
    by_key = {m["key"]: m for m in items}
    order = due_order(items)
    # Leave the rest of the material to be introduced earlier: the seed needs
    # some items that are NOT due, or "what did not come back" has no meaning.
    if args.due > len(order) - 6:
        print(f"❌ --due com a màxim {len(order) - 6}", file=sys.stderr)
        return 2
    late = [by_key[k] for k in order[:args.due]]
    late_ids = {m["id"] for m in late}
    early = [m for m in items if m["id"] not in late_ids]
    # Spread the rest over the past. The SM-2 intervals are 1, 1, 6, then 16
    # days: an item needs THREE correct reviews to be scheduled far away, and the
    # third lands eight days after it was introduced. Introduce one later than
    # `days - 9` and it comes back due today — `--due 6` produced eight, measured.
    # (With --days under about 12 that cannot be avoided: expect extra due items.)
    last_intro = max(0, args.days - 9)
    intro_day = {m["id"]: (j * last_intro) // max(1, len(early)) for j, m in enumerate(early)}

    for n in range(args.days):
        day = (start + timedelta(days=n)).isoformat()
        payload = {"session_id": f"seed-{n:02d}", "date": day, "duration_minutes": 12,
                   "exercises": [], "errors": [], "review_results": [], "new_vocabulary": []}
        for m in early:
            if intro_day[m["id"]] == n:
                frag = introduce(m)
                for k, v in frag.items():
                    payload[k].extend(v)
        # The late ones arrive two days ago and are never answered: still due.
        if args.due and n == args.days - 2:
            for m in late:
                frag = introduce(m)
                for k, v in frag.items():
                    payload[k].extend(v)
        for item in due_on(prof, day):
            if item in late_ids:
                continue  # leave these still due
            payload["review_results"].append({"item_id": item, "quality": 5})
            payload["exercises"].append({"type": "vocabulary", "question": item,
                                         "learner_answer": "ok", "correct_answer": "ok", "score": 10})
        update(prof, payload)

    today = date.today().isoformat()
    sr = json.loads((prof / "spaced-repetition.json").read_text())
    mis = json.loads((prof / "mistakes-db.json").read_text())
    pats = mis.get("error_patterns", {})
    healed = [k for k, v in pats.items() if (v.get("mastery_level") or 0) >= 4]
    print(f"perfil {prof.name}: {args.days} dies de passat")
    print(f"  ítems SM-2      : {len(sr.get('items', {}))}")
    print(f"  per repassar avui: {len(due_on(prof, today))}  → {due_on(prof, today)}")
    print(f"  patrons          : {len(pats)}  ({len(healed)} ja dominats)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
