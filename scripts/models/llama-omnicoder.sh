#!/usr/bin/env bash
# Fluent "omnicoder" LEGACY — fast small model (omnicoder-9b-q4_k_m), kept as a
# face/fast CANDIDATE (see docs/dual-model/PLAN.md for the original dual-model design).
#
# Candidats face actuals (tots comparteixen el port 12323; només un pot estar
# pujat alhora): qwen1.7-q4 (actiu, scripts/models/llama-qwen1.7b-q4.sh), qwen1.7-bf16
# (scripts/models/llama-qwen1.7b-bf16.sh) i aquest omnicoder legacy.
#
# NO cal per operar: si no hi ha res al 12323, el servidor Fluent fa fallback
# automàtic al tutor (deep, 12322) — vegeu server/src/agent.ts (resolveModel).
#
# Usage:
#   scripts/models/llama-omnicoder.sh [--model PATH] [--port N] [--gpu N] [--ctx N]
#   scripts/models/llama-omnicoder.sh --stop [--port N]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$ROOT"

MODEL="${LLAMA_FACE_MODEL:-/home/albert/aidev/models/omnicoder-9b-q4_k_m.gguf}"
PORT="${LLAMA_FACE_PORT:-12323}"
# NOTE: CUDA device index != nvidia-smi index on this machine!
#   CUDA 0 = RTX 4090 (busy: deep model 27B)   CUDA 1 = RTX 3090 (free)
GPU="${LLAMA_FACE_GPU:-1}"
CTX="${LLAMA_FACE_CTX:-65536}"
BIN="${LLAMA_FACE_BIN:-/home/albert/aidev/tools/llama.cpp-27342/build/bin/llama-server}"
STOP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    --gpu) GPU="$2"; shift ;;
    --ctx) CTX="$2"; shift ;;
    --stop) STOP=1 ;;
    *) echo "unknown arg: $1"; exit 1 ;;
  esac
  shift
done

PIDFILE="/tmp/fluent-face-$PORT.pid"

if [[ "$STOP" == "1" ]]; then
  ran=0
  if [[ -f "$PIDFILE" ]]; then
    ran=1
    for pid in $(cat "$PIDFILE"); do kill "$pid" 2>/dev/null || true; done
    rm -f "$PIDFILE"
  fi
  orphans=$(ss -tlnp 2>/dev/null | grep -E "[:.]$PORT " | grep -oP "pid=\K[0-9]+" | sort -u || true)
  [[ -n "$orphans" ]] && ran=1 || true
  for pid in $orphans; do
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 5); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -9 "$pid" 2>/dev/null || true
  done
  if [[ "$ran" == "1" ]]; then
    echo "stopped face server on port $PORT"
  else
    echo "face NOT RUNNING (port $PORT)"
  fi
  exit 0
fi

if [[ ! -x "$BIN" ]]; then
  echo "error: llama-server not found at $BIN (set LLAMA_FACE_BIN)"
  exit 1
fi
if [[ ! -f "$MODEL" ]]; then
  echo "error: model file not found: $MODEL"
  exit 1
fi
if ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORT$"; then
  echo "error: port $PORT is already in use (face server already running?)"
  exit 1
fi

LOG="/tmp/fluent-face-$PORT.log"
CUDA_VISIBLE_DEVICES="$GPU" nohup "$BIN" \
  -m "$MODEL" -ngl 999 -fa on -c "$CTX" \
  --port "$PORT" --host 127.0.0.1 \
  >> "$LOG" 2>&1 &
echo "$!" > "$PIDFILE"

ok=0
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done

echo
if [[ "$ok" == "1" ]]; then
  echo "Fluent face server UP"
  echo "  model:  $MODEL"
  echo "  url:    http://127.0.0.1:$PORT (loopback only)"
  echo "  gpu:    $GPU (ctx $CTX)"
  echo "  log:    $LOG"
  echo "  stop:   scripts/models/llama-omnicoder.sh --stop --port $PORT"
  echo
  echo "Next step (to use it as the tutor 'fast' role):"
  echo "  edit .opencode/agent/tutor.md and learner.md → model: llama-face/$MODEL"
else
  echo "ERROR: face server did not become healthy in 60s — check $LOG"
  exit 1
fi
