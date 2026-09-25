"""
Fluent path resolution — supports dual-mode (clone vs plugin install).

Data directory resolution precedence:
  1. $FLOWED_DATA_DIR if set (absolutized)
  2. $FLOWED_PROJECT_DIR/data if that dir holds learner-profile.json (clone mode, non-repo cwd)
  3. ./data if ./data/learner-profile.json exists (clone mode, in-repo cwd)
  4. ~/.claude/fluent-data (plugin-mode fallback)

Plugin-root resolution precedence:
  1. $FLOWED_ROOT if set (or the legacy $CLAUDE_PLUGIN_ROOT)
  2. $FLOWED_PROJECT_DIR if set (or the legacy $CLAUDE_PROJECT_DIR)
  3. parent of this file's hooks/ dir (dev-run fallback)

Pure resolvers (data_dir / plugin_root / backups_dir) do not create directories.
Call ensure_data_dir() before writing.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path


def force_utf8_io() -> None:
    """Make stdout/stderr UTF-8 so emoji/CJK output doesn't crash on Windows.

    Windows consoles default to a legacy code page (cp1252/gbk); printing the
    emoji in the hook summaries raises UnicodeEncodeError there. No-op on
    platforms whose streams are already UTF-8 or predate ``reconfigure``.
    Call once at the top of any hook that prints.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def profiles_root() -> Path:
    """Where the learners' profiles live: `<root>/<id>/learner-profile.json`.

    One place for it. It used to be `~/.fluent`, written by hand in 24 files;
    the project is now flowed (Albert, 2026-09-24). Resolution:
      1. $FLOWED_HOME, when set;
      2. ~/.flowed, when it exists — or when neither folder exists yet (a new machine);
      3. ~/.fluent, while the old folder has not been moved, so nothing breaks before it is.
    Pure: never creates anything.
    """
    env = os.environ.get("FLOWED_HOME")
    if env:
        return Path(env).expanduser()
    new, old = Path.home() / ".flowed", Path.home() / ".fluent"
    return new if new.exists() or not old.exists() else old


def profile_dir(profile_id: str) -> Path:
    """The folder of one learner's profile."""
    return profiles_root() / profile_id


@lru_cache(maxsize=1)
def data_dir() -> Path:
    """Resolve the runtime data directory (pure — does not create it)."""
    env = os.environ.get("FLOWED_DATA_DIR")
    if env:
        candidate = Path(env).expanduser().resolve()
        # Only honour an explicit data dir if it actually holds a learner
        # profile. This keeps dev clean when a stale FLOWED_DATA_DIR points at
        # an empty ./data, letting resolution fall through to the next rule.
        if (candidate / "learner-profile.json").exists():
            return candidate

    project = _first_env(PROJECT_ENV_VARS)
    if project:
        candidate = (Path(project) / "data").resolve()
        if (candidate / "learner-profile.json").exists():
            return candidate

    cwd_data = (Path.cwd() / "data").resolve()
    if (cwd_data / "learner-profile.json").exists():
        return cwd_data

    return (Path.home() / ".claude" / "fluent-data").resolve()


def ensure_data_dir() -> Path:
    """Resolve the data directory and create it if missing. Call before writing."""
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


# The server sets these when it spawns a hook. The CLAUDE_* spellings came from
# the tool this project was born inside; they are still read so an older
# checkout, or that tool itself, keeps working — but nothing writes them now.
ROOT_ENV_VARS = ("FLOWED_ROOT", "FLOWED_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR")
PROJECT_ENV_VARS = ("FLOWED_PROJECT_DIR", "CLAUDE_PROJECT_DIR")


def _first_env(names) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


@lru_cache(maxsize=1)
def plugin_root() -> Path:
    """Resolve the repo root directory."""
    env = _first_env(ROOT_ENV_VARS)
    if env:
        return Path(env).resolve()
    # hooks/ now sits at the repo root (it was .claude/hooks/ until the
    # directory was un-branded), so the root is one level up, not two.
    return Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def backups_dir() -> Path:
    """Resolve the backups directory. Always nested inside data_dir to avoid collisions
    when the fallback ~/.claude/fluent-data is used (the parent ~/.claude/ is shared
    across plugins)."""
    return data_dir() / ".backups"


def ensure_backups_dir() -> Path:
    """Resolve the backups directory and create it if missing."""
    b = backups_dir()
    b.mkdir(parents=True, exist_ok=True)
    return b


if __name__ == "__main__":
    # `python3 hooks/main_paths.py home` — the profiles root, for anything that is not Python.
    import sys as _sys
    if _sys.argv[1:] == ["home"]:
        print(profiles_root())
