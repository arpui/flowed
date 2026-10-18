#!/usr/bin/env python3
"""Audit: does any learner profile hold data from the OTHER domain (math vs language)?

    python3 scripts/flowed-audit-mix.py                    # every profile under the home
    python3 scripts/flowed-audit-mix.py alex-en test-math  # only these profile folders
    python3 scripts/flowed-audit-mix.py --home ~/.flowed   # an explicit profiles root

READ ONLY. The JSON files are opened for reading, the sessions.db with sqlite
`mode=ro`, the results files for reading. Nothing is created, changed or
removed, and no __pycache__ is written into the repo.

Per profile:
  1. its domain: the explicit `domain` field, else the level scale (the rule of
     hooks/domain.py), else the manifest default. A profile whose explicit
     domain contradicts its levels, or whose two levels belong to two domains,
     is suspicious by itself;
  2. every top-level *.json (the six databases, flash-db, certificates, ...):
     keys and string values that are ids of the other domain: error
     categories, pattern ids ("<category>_..."), skill keys, competence ids
     ("m5.area_perimeter", "a1.vocab_family"), level codes ("m5", "A1"), Flash
     list ids ("math-m5.flash.taules", "en-A1.flash.family");
  3. results/*.md: the file name (e.g. "-math-" in a language profile) and the
     first lines (the other domain's label, e.g. "Math Learning Session");
  4. sessions/sessions.db: session titles with the other domain's brand.

The vocabularies come from hooks/db_schema.py (categories, skill keys) and
config/domain.json (levels, Flash prefixes, labels): one source of truth, so
nothing here is a copy that can drift.

Exit codes: 0 every profile OK · 1 at least one suspicious entry or unreadable
file · 2 usage error (no profiles folder, unknown profile id).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

sys.dont_write_bytecode = True  # importing hooks/db_schema.py must not write a .pyc into the repo

REPO = Path(__file__).resolve().parent.parent
RESULTS_HEAD_BYTES = 4096
RESULTS_HEAD_LINES = 5
COMPETENCE_RE = re.compile(r"([a-z0-9]+)\.[a-z0-9_]+")

# The brand words a domain writes in session titles and results headers besides
# its manifest label (the legacy default title "FlowMath" is the math one).
EXTRA_BRAND_WORDS = {"math": ("FlowMath",)}


@dataclass(frozen=True)
class Finding:
    file: str
    path: str
    value: str
    why: str


@dataclass(frozen=True)
class Vocab:
    """What identifies one domain's data: its ids, and its words in titles and names."""
    name: str
    categories: frozenset
    skills: frozenset
    levels: frozenset          # lower-case level codes: "m1".."m7", "a1".."c2"
    flash_re: re.Pattern | None
    title_words: tuple         # words that must not appear in this domain's session titles or headers
    file_markers: tuple        # "-word-" that must not appear in this domain's results file names


# ---- sources of truth -------------------------------------------------------

def load_schema():
    """hooks/db_schema.py: the error categories and skill keys of each domain."""
    spec = importlib.util.spec_from_file_location("flowed_db_schema", REPO / "hooks" / "db_schema.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_manifest() -> dict:
    """config/domain.json: levels, Flash prefixes, labels per domain."""
    return json.loads((REPO / "config" / "domain.json").read_text(encoding="utf-8"))


def build_vocabs(manifest: dict, schema) -> dict[str, Vocab]:
    categories = {
        "math": tuple(schema.ERROR_CATEGORIES),
        "language": tuple(schema.LEGACY_ERROR_CATEGORIES) + tuple(schema.LANGUAGE_OLD_CATEGORIES),
    }
    skills = {
        "math": tuple(schema.SKILL_KEYS),
        "language": tuple(schema.LANGUAGE_SKILL_KEYS),
    }
    out: dict[str, Vocab] = {}
    for name, spec in manifest.get("domains", {}).items():
        if name not in categories:
            raise SystemExit(f"error: domain '{name}' has no vocabulary in scripts/flowed-audit-mix.py")
        flash_dir = str((spec.get("flash") or {}).get("dir") or "")
        prefix = Path(flash_dir).name.rstrip("*") if flash_dir else ""
        flash_re = re.compile(rf"{re.escape(prefix)}[a-z]{{0,2}}\d", re.IGNORECASE) if prefix else None
        labels = [spec.get("domain_label"), (spec.get("web_labels") or {}).get("subject")]
        words = [w for w in labels if w] + list(EXTRA_BRAND_WORDS.get(name, ()))
        markers = {name, str(spec.get("command_prefix") or "")} - {""}
        out[name] = Vocab(
            name=name,
            categories=frozenset(categories[name]),
            skills=frozenset(skills[name]),
            levels=frozenset(str(x).lower() for x in spec.get("level_scale", [])),
            flash_re=flash_re,
            title_words=tuple(words),
            file_markers=tuple(sorted(markers)),
        )
    return out


def level_index(manifest: dict) -> dict[str, str]:
    idx: dict[str, str] = {}
    for name, spec in manifest.get("domains", {}).items():
        for lv in spec.get("level_scale", []):
            idx[str(lv).lower()] = name
    return idx


# ---- classification ---------------------------------------------------------

def token_reason(s: str, foreign: Vocab, own: Vocab | None) -> str | None:
    """Why the string `s` is an id of the foreign domain, or None."""
    t = s.strip()
    if not t:
        return None
    if own is not None and (t in own.categories or t in own.skills):
        return None
    if t in foreign.categories:
        return f"{foreign.name} error category"
    if t in foreign.skills:
        return f"{foreign.name} skill key"
    if not re.search(r"\s", t):
        for c in foreign.categories:
            if t.startswith(c + "_"):
                return f"{foreign.name} pattern id (category {c})"
    low = t.lower()
    if low in foreign.levels:
        return f"{foreign.name} level"
    m = COMPETENCE_RE.fullmatch(low)
    if m and m.group(1) in foreign.levels:
        return f"{foreign.name} competence id"
    if foreign.flash_re is not None and foreign.flash_re.match(t):
        return f"{foreign.name} Flash list id"
    return None


def json_key_path(path: str, key: str) -> str:
    if re.fullmatch(r"[A-Za-z_]\w*", key):
        return f"{path}.{key}" if path else key
    return f'{path}["{key}"]'


def scan_json(node, path: str, fname: str, own, foreigns, out: list[Finding]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            kp = json_key_path(path, str(k))
            for f in foreigns:
                why = token_reason(str(k), f, own)
                if why:
                    out.append(Finding(fname, kp + " (key)", str(k), why))
                    break
            scan_json(v, kp, fname, own, foreigns, out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            scan_json(v, f"{path}[{i}]", fname, own, foreigns, out)
    elif isinstance(node, str):
        for f in foreigns:
            why = token_reason(node, f, own)
            if why:
                out.append(Finding(fname, path, node, why))
                break


# ---- files ------------------------------------------------------------------

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as e:
        return None, str(e)


def read_head(path: Path) -> str:
    with open(path, "rb") as fh:
        return fh.read(RESULTS_HEAD_BYTES).decode("utf-8", errors="replace")


def check_sessions(db: Path, title_re: re.Pattern | None, rel: str) -> list[Finding]:
    try:
        con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as e:
        return [Finding(rel, "-", "", f"unreadable: {e}")]
    out: list[Finding] = []
    try:
        rows = con.execute("SELECT id, title FROM session").fetchall()
    except sqlite3.Error as e:
        out.append(Finding(rel, "-", "", f"unreadable: {e}"))
        rows = []
    finally:
        con.close()
    for sid, title in rows:
        if title and title_re is not None and title_re.search(str(title)):
            out.append(Finding(rel, f"session[{sid}].title", str(title), "other domain's brand in a session title"))
    return out


def word_re(words) -> re.Pattern | None:
    words = [w for w in words if w]
    if not words:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)


def resolve_domain(profile: dict, manifest: dict, levels: dict[str, str]):
    """(domain, how it was decided, conflicts). Same rule as hooks/domain.py,
    plus the checks that catch a profile which disagrees with itself."""
    domains = manifest.get("domains", {})
    learner = profile.get("learner") if isinstance(profile.get("learner"), dict) else {}
    explicit = str(profile.get("domain") or "").strip().lower()
    cur = levels.get(str(learner.get("current_level") or "").strip().lower())
    tgt = levels.get(str(learner.get("target_level") or "").strip().lower())
    inferred = cur or tgt
    conflicts: list[Finding] = []
    if explicit:
        domain, how = explicit, "explicit field"
        if explicit not in domains:
            conflicts.append(Finding("learner-profile.json", "domain", explicit, "unknown domain"))
        elif inferred and inferred != explicit:
            conflicts.append(Finding("learner-profile.json", "domain", explicit,
                                     f"domain field says {explicit} but the levels say {inferred}"))
    else:
        domain = inferred or manifest.get("default", "math")
        how = "level scale" if inferred else "default"
    if cur and tgt and cur != tgt:
        conflicts.append(Finding("learner-profile.json", "learner.current_level / learner.target_level",
                                 f"{learner.get('current_level')} / {learner.get('target_level')}",
                                 "the two levels belong to two domains"))
    return domain, how, conflicts


def audit_profile(pdir: Path, manifest: dict, vocabs: dict[str, Vocab], levels: dict[str, str]):
    findings: list[Finding] = []
    profile, err = read_json(pdir / "learner-profile.json")
    if err is not None:
        findings.append(Finding("learner-profile.json", "-", "", f"unreadable: {err}"))
        profile = {}
    domain, how, conflicts = resolve_domain(profile, manifest, levels)
    findings += conflicts
    own = vocabs.get(domain)
    foreigns = [v for n, v in vocabs.items() if n != domain]

    for f in sorted(pdir.glob("*.json")):
        if f.name == "learner-profile.json":
            if err is None:  # already read above; its error, if any, is reported there
                scan_json(profile, "", f.name, own, foreigns, findings)
            continue
        data, jerr = read_json(f)
        if jerr is not None:
            findings.append(Finding(f.name, "-", "", f"unreadable: {jerr}"))
            continue
        scan_json(data, "", f.name, own, foreigns, findings)

    markers = {m for v in foreigns for m in v.file_markers}
    title_re = word_re([w for v in foreigns for w in v.title_words])
    results = pdir / "results"
    if results.is_dir():
        for f in sorted(results.glob("*.md")):
            rel = f"results/{f.name}"
            name = f.name.lower()
            for m in sorted(markers):
                if f"-{m}-" in name:
                    findings.append(Finding(rel, "(file name)", f.name, f"'-{m}-' is the other domain's file name"))
                    break
            try:
                head = read_head(f)
            except OSError as e:
                findings.append(Finding(rel, "-", "", f"unreadable: {e}"))
                continue
            lines = [l for l in head.splitlines() if l.strip()][:RESULTS_HEAD_LINES]
            for i, line in enumerate(lines, 1):
                if title_re is not None and title_re.search(line):
                    findings.append(Finding(rel, f"header line {i}", line.strip()[:160],
                                            "other domain's label in the header"))
                    break

    db = pdir / "sessions" / "sessions.db"
    if db.is_file():
        findings += check_sessions(db, title_re, "sessions/sessions.db")
    return domain, how, findings


def find_profiles(home: Path) -> tuple[list[Path], int]:
    """(profile folders, number of folders skipped for lacking learner-profile.json)."""
    if not home.is_dir():
        return [], 0
    profiles, skipped = [], 0
    for p in sorted(home.iterdir()):
        if not p.is_dir():
            continue
        if (p / "learner-profile.json").is_file():
            profiles.append(p)
        else:
            skipped += 1
    return profiles, skipped


def env_file_value(name: str) -> str | None:
    try:
        lines = (REPO / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        m = re.match(rf"\s*{name}\s*=\s*(.*)$", line)
        if m:
            return m.group(1).split("#", 1)[0].strip().strip("\"'")
    return None


def resolve_home(arg: str | None) -> Path:
    """--home, then FLOWED_HOME, FLOWED_HOME_DIR, the repo .env, then the default
    rule of scripts/lib-paths.sh (~/.flowed, or ~/.fluent while only that exists)."""
    raw = (arg or os.environ.get("FLOWED_HOME") or os.environ.get("FLOWED_HOME_DIR")
           or env_file_value("FLOWED_HOME") or env_file_value("FLOWED_HOME_DIR"))
    if raw:
        return Path(raw).expanduser()
    new, old = Path.home() / ".flowed", Path.home() / ".fluent"
    return new if new.exists() or not old.exists() else old


def fmt_value(v: str) -> str:
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 160 else s[:157] + '..."'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only audit: math data in language profiles, and the reverse.")
    ap.add_argument("profiles", nargs="*", metavar="ID", help="profile folder names (default: all)")
    ap.add_argument("--home", help="profiles root (default: FLOWED_HOME, FLOWED_HOME_DIR, .env, ~/.flowed)")
    args = ap.parse_args(argv)

    home = resolve_home(args.home)
    if not home.is_dir():
        print(f"error: no profiles folder at {home}", file=sys.stderr)
        return 2
    all_profiles, skipped = find_profiles(home)
    if args.profiles:
        by_name = {p.name: p for p in all_profiles}
        missing = [i for i in args.profiles if i not in by_name]
        if missing:
            print(f"error: no profile with learner-profile.json for: {', '.join(missing)} (in {home})", file=sys.stderr)
            return 2
        targets = list(dict.fromkeys(by_name[i] for i in args.profiles))
    else:
        targets = all_profiles

    schema = load_schema()
    manifest = load_manifest()
    vocabs = build_vocabs(manifest, schema)
    levels = level_index(manifest)

    print(f"home: {home}")
    bad = 0
    for pdir in targets:
        domain, how, findings = audit_profile(pdir, manifest, vocabs, levels)
        print(f"{pdir.name}  [domain: {domain}, from {how}]")
        if not findings:
            print("  OK")
            continue
        bad += 1
        print(f"  SUSPICIOUS ({len(findings)}):")
        for f in findings:
            print(f"    {f.file}  {f.path}  {fmt_value(f.value)}  ({f.why})")
    ok = len(targets) - bad
    print(f"checked {len(targets)} profile(s): {ok} OK, {bad} suspicious"
          + (f"; {skipped} folder(s) without learner-profile.json skipped" if skipped else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
