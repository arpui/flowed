#!/usr/bin/env python3
"""Print the resolved data directory, creating it if missing.

Thin CLI wrapper around main_paths.ensure_data_dir() so shell callers can do:

    FLOWED_DATA="$(python3 .../hooks/ensure_data_dir.py)"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from main_paths import ensure_data_dir  # noqa: E402


if __name__ == "__main__":
    print(ensure_data_dir())
