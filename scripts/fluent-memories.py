#!/usr/bin/env python3
"""Look through a day's sessions for things the learner said about herself.

    scripts/fluent-memories.py --profile demo-en --since 1 --dry-run
    scripts/fluent-memories.py --all --since 1
    scripts/fluent-memories.py --profile demo-en --show

Writes candidates to <profile>/.memories/pending.jsonl and **nothing else**.
Nothing here reaches the tutor: connecting the approved ones to the prompt is a
separate, later decision. Run it for a week first and read what comes out — that
tells you whether the idea is worth building, and no benchmark can.

Why offline, at night, in a batch:

  * Nobody is waiting, so model size stops being a trade-off — use the big one.
  * It can be run through TWO models and keep only what both agree on. Agreement
    costs nothing when latency does not matter, and buys precision that no
    single model of any size gives you.
  * The tutor never writes here. The whole project's lesson is that the model
    must not author what it later reads back.

The hard part is NOT extraction, it is abstention: most turns are answers to
exercises. "I have a dog" as a translation answer is not a fact about her, and a
model eager to be useful will file it anyway. The exercise is passed as context
precisely so it can be ruled out.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIRNAME = ".memories"
PENDING = "pending.jsonl"
MIN_CHARS = 12          # shorter than this is an exercise answer, not a confidence
MAX_CHARS = 600
TIMEOUT_S = 120

SYSTEM = """You read one exchange from a language lesson and decide whether the
LEARNER said something durable about their own life.

A FACT is something still true next month: a pet, a sibling, a hobby, a sport
they play, a place they go, something they love or fear.

NOT a fact — answer null for all of these:
- An answer to the exercise. If the tutor asked them to translate, complete or
  rewrite something, whatever they wrote is exercise material, NOT their life,
  even when it is in the first person.
- Anything about the lesson itself ("this is hard", "can we do vocabulary").
- A feeling right now ("I'm tired"). Only durable things count.
- Anything you inferred rather than read. If they did not say it, it is not there.

Answer with JSON and nothing else:
  {"fact": null}
  {"fact": "has a dog called Rex", "quote": "my dog is called Rex"}

`quote` must be copied VERBATIM from the learner's message. `fact` must be one
short third-person clause. When unsure, answer null: a wrong fact about a child
is far worse than a missed one."""


def profile_dirs(args) -> list[Path]:
    out: list[Path] = []
    if args.dir:
        out.append(Path(args.dir).expanduser())
    if args.profile:
        out.append(Path.home() / ".fluent" / args.profile)
    if args.all:
        root = Path.home() / ".fluent"
        out += sorted(p for p in root.iterdir()
                      if p.is_dir() and (p / "learner-profile.json").exists())
    return out


def learner_turns(db: Path, since_ms: int) -> list[dict]:
    """(exercise, answer) pairs: the tutor's message and the learner's reply."""
    if not db.exists():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT id, session_id, time_created, data FROM message "
            "WHERE time_created > ? ORDER BY time_created", (since_ms,)
        ).fetchall()

        def body(mid: str) -> str:
            parts = conn.execute(
                "SELECT data FROM part WHERE message_id = ? ORDER BY time_created", (mid,)
            ).fetchall()
            out = []
            for (pd,) in parts:
                try:
                    p = json.loads(pd or "{}")
                except ValueError:
                    continue
                if p.get("type") == "text" and p.get("text"):
                    out.append(p["text"])
            return "\n".join(out).strip()

        turns, last_tutor = [], ""
        for mid, sid, ts, data in rows:
            try:
                role = json.loads(data or "{}").get("role")
            except ValueError:
                continue
            text = body(mid)
            if not text:
                continue
            if role == "assistant":
                last_tutor = text
                continue
            # A command arrives as user text carrying the whole expanded prompt.
            if text.lstrip().startswith("/") or len(text) > MAX_CHARS:
                continue
            if len(text) < MIN_CHARS:
                continue
            turns.append({"session_id": sid, "ts": ts, "exercise": last_tutor[-700:],
                          "answer": text})
        return turns
    finally:
        conn.close()


def ask(base_url: str, model: str, exercise: str, answer: str) -> dict | None:
    """One extraction call. Returns the parsed object, or None if it failed."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content":
                f"TUTOR ASKED:\n{exercise or '(nothing — they wrote unprompted)'}\n\n"
                f"LEARNER WROTE:\n{answer}"},
        ],
        "temperature": 0,
        "max_tokens": 200,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            body = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  ⚠ {model}: {e}", file=sys.stderr)
        return None
    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def normalise(fact: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(fact or "").lower()).strip()


def agree(results: list[dict | None]) -> dict | None:
    """Keep a fact only when every model found one and they mean the same thing.

    Cheap overlap, not semantics: two models describing the same fact share most
    of their content words. Offline, demanding agreement costs a second pass and
    removes the single-model confident mistake, which is the error that matters.
    """
    facts = [r for r in results if r and r.get("fact")]
    if len(facts) != len(results) or not facts:
        return None
    if len(facts) == 1:
        return facts[0]
    words = [set(normalise(f["fact"]).split()) for f in facts]
    base = words[0]
    for other in words[1:]:
        if not base or not other:
            return None
        overlap = len(base & other) / max(1, min(len(base), len(other)))
        if overlap < 0.5:
            return None
    return facts[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Candidates for things the learner said about herself",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--profile")
    ap.add_argument("--dir")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--since", type=float, default=1, metavar="DIES",
                    help="mira els torns dels últims N dies (per defecte 1)")
    ap.add_argument("--model", action="append", default=[], metavar="URL=NOM",
                    help="repetible; per defecte el deep de l'.env. Dos models = intersecció")
    ap.add_argument("--limit", type=int, default=200, help="màxim de torns per perfil")
    ap.add_argument("--dry-run", action="store_true", help="no escriu pending.jsonl")
    ap.add_argument("--show", action="store_true", help="ensenya el pending i surt")
    args = ap.parse_args(argv)

    targets = profile_dirs(args)
    if not targets:
        ap.error("dona --profile, --dir o --all")

    if args.show:
        for d in targets:
            f = d / MEMORY_DIRNAME / PENDING
            print(f"=== {d.name} ===")
            if not f.exists():
                print("  (cap candidat encara)\n")
                continue
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                when = rec.get("date", "?")
                print(f"  • {rec.get('fact')}")
                print(f"    ← «{rec.get('quote')}» · {when} · {rec.get('session_id', '')[:16]}")
                print(f"      models: {', '.join(rec.get('models', []))}")
            print()
        return 0

    models = []
    for spec in args.model:
        url, _, name = spec.partition("=")
        models.append((url, name or "deep"))
    if not models:
        port = os.environ.get("FLUENT_DEEP_PORT", "12322")
        url = os.environ.get("FLUENT_DEEP_BASE_URL", f"http://127.0.0.1:{port}/v1")
        models.append((url, "deep"))

    since_ms = int((datetime.now() - timedelta(days=args.since)).timestamp() * 1000)
    print(f"torns des de {datetime.fromtimestamp(since_ms / 1000):%Y-%m-%d %H:%M} · "
          f"models: {', '.join(n for _, n in models)}"
          f"{'  (SIMULACIÓ)' if args.dry_run else ''}\n")

    for d in targets:
        print(f"=== {d.name} ===")
        if not d.exists():
            print(f"  ❌ no existeix: {d}", file=sys.stderr)
            continue
        turns = learner_turns(d / "sessions" / "sessions.db", since_ms)[: args.limit]
        print(f"  {len(turns)} torn(s) de l'alumna a mirar")
        if not turns:
            print()
            continue

        found = []
        for i, t in enumerate(turns, 1):
            results = [ask(url, name, t["exercise"], t["answer"]) for url, name in models]
            hit = agree(results)
            if not hit:
                continue
            quote = str(hit.get("quote") or "").strip()
            # The quote must really be in what she wrote: it is the whole point
            # of the record, and an invented one makes review worthless.
            if quote and quote.lower() not in t["answer"].lower():
                print(f"  ⚠ descartat (cita inventada): {hit.get('fact')!r} ← {quote!r}")
                continue
            rec = {
                "fact": str(hit["fact"]).strip()[:200],
                "quote": quote or t["answer"][:200],
                "session_id": t["session_id"],
                "date": datetime.fromtimestamp(t["ts"] / 1000).strftime("%Y-%m-%d %H:%M"),
                "models": [n for _, n in models],
                "status": "pending",
            }
            found.append(rec)
            print(f"  • {rec['fact']}")
            print(f"    ← «{rec['quote']}»")

        print(f"  → {len(found)} candidat(s) de {len(turns)} torns")
        if found and not args.dry_run:
            out = d / MEMORY_DIRNAME / PENDING
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "a", encoding="utf-8") as f:
                for rec in found:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"  escrits a {out}")
        print()

    print("Res d'això arriba al tutor. Mira-ho uns dies abans de connectar-hi res.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
