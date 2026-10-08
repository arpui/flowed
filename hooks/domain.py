#!/usr/bin/env python3
"""WP5.2 — the domain adapter (the Python twin of config/domain.json).

The core is domain-neutral; a domain is DATA + a thin adapter. This module is
the single authority for "which domain is this profile?": an explicit ``domain``
field in learner-profile.json wins; otherwise the level scale decides (A1..C2 →
language, m1..m7 → math). Everything the core needs per domain — command/skill
prefix, curriculum glob, bank dir, grader, taxonomy additions, TTS — comes from
the manifest, so a future domain plugs in by adding a manifest entry plus its
dirs (see docs/CORE-AND-DOMAINS.md).

Usage:
    from domain import domain_for_profile, manifest
    python3 hooks/domain.py            # print the resolved domain of each profile dir
"""
import json
import sys
from pathlib import Path

DOMAIN_FILE = Path(__file__).resolve().parent.parent / "config" / "domain.json"


def manifest() -> dict:
    try:
        return json.loads(DOMAIN_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"default": "math", "domains": {}}


def domain_for_level(level) -> str | None:
    """Infer the domain from the level scale — A1..C2 is language, m1..m7 math."""
    if not level:
        return None
    lv = str(level).strip()
    for name, spec in manifest().get("domains", {}).items():
        if lv in spec.get("level_scale", []):
            return name
    return None


def domain_for_profile(profile: dict) -> str:
    """The domain of a learner profile: explicit field first, level scale second,
    manifest default last. Never raises — a profile without clues gets the
    default, which is what every existing (math) profile expects."""
    explicit = str(profile.get("domain", "") or "").strip()
    if explicit and explicit in manifest().get("domains", {}):
        return explicit
    learner = profile.get("learner", {}) if isinstance(profile, dict) else {}
    inferred = domain_for_level(learner.get("current_level")) or domain_for_level(learner.get("target_level"))
    return inferred or manifest().get("default", "math")


def domain_for_dir(data_dir) -> str:
    """The domain of the profile in `data_dir` (reads learner-profile.json).
    Never raises: no profile, or one without clues, gets the manifest default."""
    try:
        prof = json.loads((Path(data_dir).expanduser() / "learner-profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        prof = {}
    return domain_for_profile(prof if isinstance(prof, dict) else {})


def spec(domain: str) -> dict:
    return manifest().get("domains", {}).get(domain, {})


if __name__ == "__main__":
    import os
    from main_paths import profiles_root  # sibling hook module
    for p in sorted(Path(profiles_root()).iterdir()) if Path(profiles_root()).exists() else []:
        prof = p / "learner-profile.json"
        if prof.exists():
            try:
                d = json.loads(prof.read_text(encoding="utf-8"))
            except ValueError:
                continue
            print(f"{p.name}: {domain_for_profile(d)}")
    sys.exit(0)
