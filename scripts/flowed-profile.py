#!/usr/bin/env python3
"""Fill in (or adjust) a learner profile from the command line — admin only.

Onboarding used to be an interview the learner ran themselves (/math-setup).
It no longer is: the profile says who someone is and how their sessions are
paced, which is the system owner's call, not a form a child should be filling
in mid-lesson. This script is that write, with the same validation the
`math_setup_profile` tool applies, and it also carries the pacing
preferences so a profile can be provisioned in one go.

    scripts/new-user.sh demo-math
    scripts/flowed-profile.py demo-math --name Nes --native Catalan \\
        --level m4 --goal m5 --minutes 20 --session-length 8

    scripts/flowed-profile.py demo-math --session-length 10 --stop soft   # adjust later
    scripts/flowed-profile.py demo-math --show

The subject is fixed ("Math"); --target exists only to override it explicitly.
Nothing here is interactive and nothing is guessed: a value you do not pass is
a value that does not change.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from main_paths import profiles_root  # noqa: E402  (where the profiles live)

M_LEVELS = ["m1", "m2", "m3", "m4", "m5", "m6", "m7"]  # math scale (D3: m1–m6 primària; WP1.1 afegeix m7 = 1r ESO; m8/m9 = 2n/3r ESO quan arribin)
MOTIVATIONS = ["school", "exam", "practice", "personal"]
PLACEHOLDER = lambda v: isinstance(v, str) and v.strip().startswith("{") and v.strip().endswith("}")


def profile_dir(profile_id: str) -> Path:
    if profile_id in (".", "data"):
        return Path(__file__).resolve().parent.parent / "data"
    if "/" in profile_id or profile_id.startswith("."):
        raise SystemExit(f"error: '{profile_id}' is not a profile id (letters, digits, hyphens)")
    return profiles_root() / profile_id


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise SystemExit(
            f"error: no learner-profile.json in {path.parent}\n"
            f"       create the profile first: scripts/new-user.sh {path.parent.name}"
        )
    except json.JSONDecodeError as e:
        raise SystemExit(f"error: {path} is not valid JSON ({e})")


def save(path: Path, data: dict) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if path.exists():
        shutil.copy2(path, f"{path}.backup-{stamp}")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def summarise(profile: dict) -> str:
    l = profile.get("learner", {})
    p = profile.get("preferences", {})
    return (
        f"  name            {l.get('name')}\n"
        f"  languages       {l.get('native_language')} → {l.get('target_language')}\n"
        f"  level           {l.get('current_level')} → {l.get('target_level')}\n"
        f"  daily minutes   {l.get('daily_goal_minutes')}\n"
        f"  daily_goal      {p.get('daily_goal', p.get('session_length', '(default 15)'))}\n"
        f"  session_stop    {p.get('session_stop', '(default soft)')}\n"
        f"  review_gate     {p.get('review_gate', '(default on)')}\n"
        f"  setup_complete  {p.get('setup_complete', False)}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile", help="profile id under the profile root (e.g. demo-math), or 'data' for the repo profile")
    ap.add_argument("--show", action="store_true", help="print the current values and exit")
    ap.add_argument("--name")
    ap.add_argument("--native", help="the language the tutor explains in, in English (e.g. Catalan)")
    ap.add_argument("--target", help='subject being learned — fixed "Math"; pass only to override')
    ap.add_argument("--level", help=f"math level now: {'|'.join(M_LEVELS)}")
    ap.add_argument("--goal", help=f"math level wanted: {'|'.join(M_LEVELS)}")
    ap.add_argument("--minutes", type=int, help="daily goal, 5-240")
    ap.add_argument("--motivation", choices=MOTIVATIONS)
    ap.add_argument("--interest", action="append", default=[], help="repeatable, up to 3")
    ap.add_argument("--focus", action="append", default=[], help="focus area / goal, repeatable, up to 5")
    ap.add_argument("--about", help="one line about the learner")
    ap.add_argument("--daily-goal", type=int, help="exercises a day for the happy face (1-100, 0 = no goal)")
    ap.add_argument("--session-length", type=int, help="(antic nom de --daily-goal)")
    ap.add_argument("--stop", choices=["soft", "hard"], help="what happens at the target")
    ap.add_argument("--review-gate", choices=["on", "off"], help="due reviews before new material")
    ap.add_argument("--incomplete", action="store_true", help="mark setup as NOT complete")
    args = ap.parse_args(argv)

    path = profile_dir(args.profile) / "learner-profile.json"
    profile = load(path)

    if args.show:
        print(f"{path}\n{summarise(profile)}")
        return 0

    learner = profile.setdefault("learner", {})
    prefs = profile.setdefault("preferences", {})
    changed: list[str] = []

    if args.name:
        if not 1 <= len(args.name.strip()) <= 60:
            raise SystemExit("error: --name must be 1-60 characters")
        learner["name"] = args.name.strip()
        changed.append("name")

    if args.native or args.target:
        native = (args.native or learner.get("native_language") or "").strip()
        # The subject is fixed: "Math". --target only exists to say so
        # explicitly; a template placeholder in the profile counts as absent.
        existing = (learner.get("target_language") or "").strip()
        if PLACEHOLDER(existing):
            existing = ""
        target = ((args.target or "").strip() or existing or "Math")
        if not native or not target:
            raise SystemExit("error: --native is needed the first time (the language the tutor explains in)")
        if native.lower() == target.lower():
            raise SystemExit(f"error: native and target cannot both be '{target}'")
        learner["native_language"], learner["target_language"] = native, target
        changed.append("languages")

    for opt, key in (("level", "current_level"), ("goal", "target_level")):
        value = getattr(args, opt)
        if value:
            if value.lower() not in M_LEVELS:
                raise SystemExit(f"error: --{opt} must be one of {', '.join(M_LEVELS)}")
            learner[key] = value.lower()  # m1..m6, stored lowercase
            changed.append(key)

    if args.minutes is not None:
        learner["daily_goal_minutes"] = max(5, min(240, args.minutes))
        changed.append("daily_goal_minutes")
    if args.motivation:
        learner["motivation"] = args.motivation
        changed.append("motivation")
    if args.interest:
        learner["interests"] = [i.strip() for i in args.interest if i.strip()][:3]
        changed.append("interests")
    if args.about:
        learner["about"] = args.about.strip()[:200]
        changed.append("about")
    if args.focus:
        profile["focus_areas"] = [f.strip() for f in args.focus if f.strip()][:5]
        changed.append("focus_areas")

    goal = args.daily_goal if args.daily_goal is not None else args.session_length
    if goal is not None:
        if not 0 <= goal <= 100:
            raise SystemExit("error: --daily-goal must be 0-100 (0 = no goal)")
        prefs["daily_goal"] = goal
        prefs.pop("session_length", None)  # one name, not two
        changed.append("daily_goal")
    if args.stop:
        prefs["session_stop"] = args.stop
        changed.append("session_stop")
    if args.review_gate:
        prefs["review_gate"] = args.review_gate == "on"
        changed.append("review_gate")

    # Placeholders from data-examples/ must never survive a real setup.
    if PLACEHOLDER(learner.get("motivation")):
        learner["motivation"] = "personal"
    if PLACEHOLDER(learner.get("learning_style")):
        learner["learning_style"] = "balanced"
    if isinstance(learner.get("other_languages"), list):
        learner["other_languages"] = [l for l in learner["other_languages"] if not PLACEHOLDER(l)]

    today = datetime.now().strftime("%Y-%m-%d")
    for achievement in profile.get("achievements") or []:
        if isinstance(achievement, dict) and PLACEHOLDER(achievement.get("earned_date")):
            achievement["earned_date"] = today

    required = ["name", "native_language", "target_language", "current_level", "target_level"]
    missing = [k for k in required if not learner.get(k) or PLACEHOLDER(learner.get(k))]
    prefs["setup_complete"] = not (args.incomplete or missing)
    if not PLACEHOLDER(profile.get("profile_created")) and profile.get("profile_created"):
        pass
    else:
        profile["profile_created"] = today
    profile["last_updated"] = today

    if not changed and not args.incomplete:
        print("nothing to change (pass --show to see the current values)")
        return 0

    save(path, profile)
    print(f"{path}\nupdated: {', '.join(changed) or '(flags only)'}\n{summarise(profile)}")
    if missing:
        print(f"\nstill missing, setup NOT complete: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
