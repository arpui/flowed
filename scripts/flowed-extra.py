#!/usr/bin/env python3
"""Add a learner-only competence (a song, a class topic) to one profile.

    python3 scripts/flowed-extra.py add <perfil|camí> curriculum/extras/<id>
    python3 scripts/flowed-extra.py list <perfil|camí>

An extra lives in the profile, not in the level's curriculum:
  <profile>/extra.md          same format as curriculum/en-A1.md; `[extra]` =
                              practised in Go, never counted in the level bar
  <profile>/bank/<id>.json    its exercises, graded like the level's bank
The source folder (curriculum/extras/<id>/) holds one extra.md block and its
<id>.json. `add` only adds: a competence already in the profile is left alone.
See docs/ARQUITECTURA.md G.17.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))
import curriculum as cu  # noqa: E402
from main_paths import profiles_root  # noqa: E402


def profile_dir(arg: str) -> Path:
    p = Path(arg).expanduser()
    return p if p.is_dir() else profiles_root() / arg


def add(profile: Path, src: Path) -> int:
    if not (profile / "learner-profile.json").is_file():
        print(f"error: {profile} is not a profile (no learner-profile.json)", file=sys.stderr)
        return 1
    block = (src / "extra.md").read_text(encoding="utf-8")
    new = cu.parse_curriculum(block)["competencies"]
    if not new:
        print(f"error: no competence in {src / 'extra.md'}", file=sys.stderr)
        return 1
    target = profile / cu.EXTRA_FILE
    have = {c["id"] for c in cu.parse_curriculum(target.read_text(encoding="utf-8"))["competencies"]} \
        if target.is_file() else set()
    todo = [c for c in new if c["id"] not in have]
    if todo:
        text = target.read_text(encoding="utf-8") if target.is_file() else ""
        body = block if not text else "\n".join(l for l in block.splitlines() if not l.startswith("## ")).strip() + "\n"
        target.write_text((text.rstrip() + "\n\n" if text else "") + body, encoding="utf-8")
    (profile / "bank").mkdir(exist_ok=True)
    for c in new:
        f = src / f"{c['id']}.json"
        if f.is_file():
            shutil.copy2(f, profile / "bank" / f.name)
        print(f"{c['id']}: {'added' if c in todo else 'already there'}"
              f"{' + bank' if f.is_file() else ' (no bank file!)'} → {profile.name}")
    return 0


def show(profile: Path) -> int:
    f = profile / cu.EXTRA_FILE
    comps = cu.parse_curriculum(f.read_text(encoding="utf-8"))["competencies"] if f.is_file() else []
    for c in comps:
        bank = profile / "bank" / f"{c['id']}.json"
        print(f"{c['id']:30s} {'core' if c['core'] else 'extra':5s} {c['name']}"
              f"{'' if bank.is_file() else '  (sense banc)'}")
    if not comps:
        print("(cap extra)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("profile"); a.add_argument("src")
    l = sub.add_parser("list"); l.add_argument("profile")
    args = ap.parse_args()
    if args.cmd == "add":
        return add(profile_dir(args.profile), Path(args.src))
    return show(profile_dir(args.profile))


if __name__ == "__main__":
    sys.exit(main())
