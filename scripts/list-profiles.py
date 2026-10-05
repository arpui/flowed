#!/usr/bin/env python3
"""List Flowed learner profiles for /math-use.

Scans the repo's data/ directory plus the multi-learner convention
~/.flowed/<id>/learner-profile.json. Prints one line per profile:

    <id>  <nom>  (<llengua>, nivell <CEFR>, racha <N>d)

`<id>` is the directory name, or "data" for the repo default.
Pure stdlib; always exits 0.
"""
import glob
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from main_paths import profiles_root  # noqa: E402  (where the profiles live)

REPO = Path(__file__).resolve().parents[2]


def summarize(data_dir):
    profile = data_dir / "learner-profile.json"
    if not profile.exists():
        return None
    try:
        data = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    learner = data.get("learner") or {}
    name = learner.get("name") or "?"
    lang = learner.get("target_language") or "?"
    level = learner.get("current_level") or "?"
    streak = data.get("current_streak_days", 0)
    return "{}  ({}, nivell {}, racha {}d)".format(name, lang, level, streak)


def main():
    rows = []
    repo_data = REPO / "data"
    summary = summarize(repo_data)
    if summary is not None:
        rows.append("data  " + summary)
    pattern = str(profiles_root() / "*" / "learner-profile.json")
    for path in sorted(glob.glob(pattern)):
        data_dir = Path(path).expanduser().parent
        if data_dir.resolve() == repo_data.resolve():
            continue
        summary = summarize(data_dir)
        if summary is not None:
            rows.append(data_dir.name + "  " + summary)
    if rows:
        print("\n".join(rows))
    else:
        print("(cap perfil — fes /math-setup per crear-ne un)")


if __name__ == "__main__":
    main()
