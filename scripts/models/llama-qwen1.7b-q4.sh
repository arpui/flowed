#!/usr/bin/env bash
# Fluent "face/fast" actiu — petit i ràpid (Qwen3-1.7B-UD-Q4_K_XL) al port 12323.
# És UN dels candidats face (amb el bf16 i l'omnicoder legacy): tots comparteixen
# el 12323 i només un pot estar pujat alhora (l'script rebutja el port ocupat).
#
# Usage:
#   scripts/models/llama-qwen1.7b-q4.sh [--model PATH] [--port N] [--gpu N] [--ctx N]
#   scripts/models/llama-qwen1.7b-q4.sh --stop [--port N]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$ROOT"

MODEL="${LLAMA_QWEN1_7B_Q4_MODEL:-/home/albert/aidev/models/Qwen3-1.7B-UD-Q4_K_XL.gguf}"
PORT="${LLAMA_QWEN1_7B_Q4_PORT:-12323}"
GPU="${LLAMA_QWEN1_7B_Q4_GPU:-1}"    # CUDA 1 = RTX 3090 (free)
CTX="${LLAMA_QWEN1_7B_Q4_CTX:-32768}"
BIN="${LLAMA_QWEN1_7B_Q4_BIN:-/home/albert/aidev/tools/llama.cpp/build/bin/llama-server}"
STOP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL="$2"; shift ;;
    --port)  PORT="$2"; shift ;;
    --gpu)   GPU="$2"; shift ;;
    --ctx)   CTX="$2"; shift ;;
    --stop)  STOP=1 ;;
    *) echo "unknown arg: $1"; exit 1 ;;
  esac
  shift
done

PIDFILE="/tmp/fluent-qwen1.7b-q4-$PORT.pid"
LOG="/tmp/fluent-qwen1.7b-q4-$PORT.log"

if [[ "$STOP" == "1" ]]; then
  ran=0
  [[ -f "$PIDFILE" ]] && { ran=1; for pid in $(cat "$PIDFILE"); do kill "$pid" 2>/dev/null || true; done; } || true
  rm -f "$PIDFILE"
  orphans=$(ss -tlnp 2>/dev/null | grep -E "[:.]$PORT " | grep -oP "pid=\K[0-9]+" | sort -u || true)
  [[ -n "$orphans" ]] && ran=1
  for pid in $orphans; do
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 5); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -9 "$pid" 2>/dev/null || true
  done
  [[ "$ran" == "1" ]] && echo "stopped qwen1.7b-q4 server on port $PORT" || echo "qwen1.7b-q4 NOT RUNNING (port $PORT)"
  exit 0
fi

[[ ! -x "$BIN" ]] && { echo "error: llama-server not found at $BIN"; exit 1; }
[[ ! -f "$MODEL" ]] && { echo "error: model not found: $MODEL"; exit 1; }
if ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORT$"; then
  echo "error: port $PORT in use"; exit 1
fi

LOG="/tmp/fluent-qwen1.7b-q4-$PORT.log"
CUDA_VISIBLE_DEVICES="$GPU" nohup "$BIN" \
  -m "$MODEL" -ngl 999 -fa on -c "$CTX" \
  --port "$PORT" --host 127.0.0.1 \
  >> "$LOG" 2>&1 &
echo "$!" > "$PIDFILE"

ok=0
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done
[[ "$ok" == "1" ]] && echo "Qwen1.7B-Q4 UP — $MODEL @ :$PORT (cuda $GPU, ctx $CTX)" || { echo "ERROR: not healthy — $LOG"; exit 1; }