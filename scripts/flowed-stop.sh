#!/usr/bin/env bash
# Flowed STOP — atura tot segons .env (webs + models gestionats).
# No pregunta (aturar és segur). Tolera el que ja estigui aturat.
#
#   scripts/flowed-stop.sh [--webs-only] [--models-only]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  while IFS= read -r _line || [[ -n "$_line" ]]; do
    _line="${_line%%#*}"
    [[ "$_line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$_line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
    _k="${BASH_REMATCH[1]}"; _v="${BASH_REMATCH[2]}"
    _v="${_v%\"}"; _v="${_v#\"}"; _v="${_v%\'}"; _v="${_v#\'}"
    if [[ -z "${!_k+x}" ]]; then export "$_k=$_v"; fi
  done < "$ROOT/.env"
fi

# Capa de sota (P1-9): config/fluent.json. Només omple el que .env i l'entorn no
# hagin definit — precedència: CLI/entorn > .env > config/fluent.json.
if [[ -f "$ROOT/config/fluent.json" ]]; then
  eval "$(python3 "$ROOT/scripts/flowed-config.py" --sh --missing-only --no-env-file 2>/dev/null || true)"
fi
if [[ -z "${FLOWED_DEEP_MODEL:-}" ]]; then
  echo "error: no hi ha configuració — falta config/fluent.json i .env"
  exit 1
fi

FLOWED_DEEP_MANAGED="${FLOWED_DEEP_MANAGED:-1}"
FLOWED_DEEP_BACKEND="${FLOWED_DEEP_BACKEND:-native}"
FLOWED_DEEP_PORT="${FLOWED_DEEP_PORT:-12322}"
FLOWED_FACE_ENABLED="${FLOWED_FACE_ENABLED:-0}"
FLOWED_FACE_PORT="${FLOWED_FACE_PORT:-12323}"
FLOWED_WEBS="${FLOWED_WEBS:-alex-en:4100 sam-en:4101 demo-en:4102}"

WEBS_ONLY=0
MODELS_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --webs-only) WEBS_ONLY=1 ;;
    --models-only) MODELS_ONLY=1 ;;
    *) echo "ús: $0 [--webs-only] [--models-only]"; exit 1 ;;
  esac
  shift
done

if [[ "$MODELS_ONLY" == "0" ]]; then
  for spec in $FLOWED_WEBS; do
    port="${spec##*:}"
    scripts/flowed-web.sh --stop --port "$port" 2>/dev/null || true
  done
fi

if [[ "$WEBS_ONLY" == "0" && "$FLOWED_DEEP_MANAGED" == "1" ]]; then
  if [[ "$FLOWED_DEEP_BACKEND" == "docker" ]]; then
    scripts/models/docker-llama.sh --stop 2>/dev/null || true
    rm -f /tmp/fluent-deep-docker.state
    # Restore SEMPRE el default (si configurat): en parar Flowed, el port
    # torna al model d'ús general.
    if [[ -n "${FLOWED_DEFAULT_MANAGER:-}" && -x "$FLOWED_DEFAULT_MANAGER" ]]; then
      echo "(restore: pujant default via $FLOWED_DEFAULT_MANAGER)"
      "$FLOWED_DEFAULT_MANAGER" start 2>/dev/null || echo "(avís: el default no ha pujat — fes-ho a mà)"
      port_up() { curl -sf -m 2 "http://127.0.0.1:$FLOWED_DEEP_PORT/health" >/dev/null 2>&1; }
      port_up "$FLOWED_DEEP_PORT" && echo "default :$FLOWED_DEEP_PORT OK" || echo "default :$FLOWED_DEEP_PORT ATURAT (revisar)"
    fi
  else
    scripts/models/llama-deep.sh --stop --port "$FLOWED_DEEP_PORT" 2>/dev/null || true
  fi
  # face sempre (per si va quedar d'una config anterior amb ENABLED=1)
  scripts/models/llama-qwen1.7b-q4.sh --stop --port "$FLOWED_FACE_PORT" 2>/dev/null || true
fi

echo "flowed-stop: fet (webs [${FLOWED_WEBS}] + models gestionats)"
