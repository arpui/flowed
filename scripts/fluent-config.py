#!/usr/bin/env python3
"""Fluent configuration resolver — one place that knows the whole picture.

Layers, lowest to highest:

  1. config/fluent.json     the project's configuration (committed)
  2. .env at the repo root  how THIS machine differs (not committed)
  3. the environment        exports and CLI wrappers

Usage:
    python3 scripts/fluent-config.py --json   # effective config, resolved
    python3 scripts/fluent-config.py --sh     # shell exports for the scripts
    python3 scripts/fluent-config.py --sh --missing-only
                                              # only vars not already set

The bash scripts source it AFTER their own .env loop, with --missing-only, so
the precedence above holds without either side having to parse the other's
format.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "fluent.json"
ENV_FILE = ROOT / ".env"


def read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}  # no canonical config: the defaults below still apply
    except (OSError, ValueError) as exc:
        # A config that exists but cannot be read IS worth shouting about.
        print(f"[Fluent] ⚠ could not read {path}: {exc}", file=sys.stderr)
        return {}


def read_env_file(path: Path) -> dict:
    """Parse a KEY=value file the same way the bash loaders do."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key.replace("_", "").isalnum():
            continue
        out[key] = value.strip().strip('"').strip("'")
    return out


def as_bool(value, default=False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def flatten(config: dict) -> dict:
    """config/fluent.json -> the FLUENT_* variables the scripts already use."""
    paths = config.get("paths", {}) or {}
    models = config.get("models", {}) or {}
    deep = models.get("deep", {}) or {}
    face = models.get("face", {}) or {}
    webs = config.get("webs", {}) or {}

    server = config.get("server", {}) or {}

    flat = {
        "FLUENT_STREAM": "1" if as_bool(server.get("stream"), False) else "0",
        "FLUENT_MODEL_DIR": paths.get("model_dir", ""),
        "FLUENT_DEFAULT_MANAGER": paths.get("default_manager", ""),
        "FLUENT_DEEP_BACKEND": deep.get("backend", "native"),
        "FLUENT_DEEP_MANAGED": "1" if as_bool(deep.get("managed"), True) else "0",
        "FLUENT_DEEP_MODEL": deep.get("model", ""),
        "FLUENT_DEEP_PORT": deep.get("port", 12322),
        "FLUENT_DEEP_GPU": deep.get("gpu", 1),
        "FLUENT_DEEP_CTX": deep.get("ctx", 32768),
        "FLUENT_DEEP_KV_TYPE": deep.get("kv_type", "f16"),
        "FLUENT_FACE_ENABLED": "1" if as_bool(face.get("enabled"), False) else "0",
        "FLUENT_FACE_MODEL": face.get("model", ""),
        "FLUENT_FACE_PORT": face.get("port", 12323),
        "FLUENT_FACE_GPU": face.get("gpu", 1),
        "FLUENT_FACE_CTX": face.get("ctx", 32768),
    }
    if webs:
        flat["FLUENT_WEBS"] = " ".join(f"{k}:{v}" for k, v in webs.items())
    return {k: ("" if v is None else str(v)) for k, v in flat.items() if v != ""}


def resolve(include_env_file=True, include_environ=True) -> dict:
    values = flatten(read_json(CONFIG))
    if include_env_file:
        for key, value in read_env_file(ENV_FILE).items():
            values[key] = value
    if include_environ:
        for key in list(values) + [k for k in os.environ if k.startswith("FLUENT_")]:
            if key in os.environ:
                values[key] = os.environ[key]
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Fluent's configuration")
    parser.add_argument("--json", action="store_true", help="print the effective config as JSON")
    parser.add_argument("--sh", action="store_true", help="print shell exports")
    parser.add_argument("--missing-only", action="store_true",
                        help="with --sh: only variables not already set in the environment")
    parser.add_argument("--no-env-file", action="store_true", help="ignore .env")
    args = parser.parse_args()

    values = resolve(include_env_file=not args.no_env_file)

    if args.json or not args.sh:
        print(json.dumps(values, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    for key in sorted(values):
        if args.missing_only and key in os.environ:
            continue
        print(f"export {key}={shlex.quote(values[key])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
