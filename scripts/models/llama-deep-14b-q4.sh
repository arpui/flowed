#!/usr/bin/env bash
# Flowed "deep-14b-q4" model server — Qwen3-14B-Q4_K_M, candidat a deep lleuger.
#
# Mateixa arquitectura que el deep Q6_K (mateix raonament), menys VRAM:
#   pesos ~8.4GB + KV ~5.2GB (@ctx 32768) ≈ 14GB → cap a 24GB amb marge i
#   a 16GB (4060 Ti) just.
# Comparativa pendent vs Q6_K (E2: vocab 9s, review 5s, progress 15s @3090).
# Si la qualitat aguanta, candidat a substituir el Q6 o a servir targues 16GB.
#
# Els mateixos flags crítics que llama-deep.sh:
#   --reasoning off, --parallel 1, sense KV-quant (-ctk/-ctv), -c 32768.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$ROOT"

MODEL="${LLAMA_DEEP_Q4_MODEL:-/home/albert/aidev/models/Qwen3-14B-Q4_K_M.gguf}"
PORT="${LLAMA_DEEP_Q4_PORT:-12325}"
GPU="${LLAMA_DEEP_Q4_GPU:-0}"    # CUDA 0 = RTX 4090 (nvidia-smi GPU1) en aquesta màquina
CTX="${LLAMA_DEEP_Q4_CTX:-32768}"
BIN="${LLAMA_DEEP_Q4_BIN:-/home/albert/aidev/tools/llama.cpp/build/bin/llama-server}"
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

PIDFILE="/tmp/fluent-deep-q4-$PORT.pid"
LOG="/tmp/fluent-deep-q4-$PORT.log"

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
  [[ "$ran" == "1" ]] && echo "stopped deep-q4 server on port $PORT" || echo "deep-q4 NOT RUNNING (port $PORT)"; exit 0
fi

if [[ ! -x "$BIN" ]]; then echo "error: llama-server not found at $BIN"; exit 1; fi
if [[ ! -f "$MODEL" ]]; then echo "error: model not found: $MODEL"; exit 1; fi
if ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORT$"; then
  echo "error: port $PORT in use"; exit 1
fi

# KV cache precision. f16 is what this recipe was measured with; q8_0 halves the
# KV cache (needs -fa 1, which is on) and so buys either ~2.6 GB back at ctx
# 32768 or twice the context for the same VRAM. It is a quality trade-off, so it
# is opt-in and must be MEASURED, not assumed: see docs/model-qwen14b-q4.md.
KV_TYPE="${FLOWED_DEEP_KV_TYPE:-f16}"
KV_ARGS=()
if [[ "$KV_TYPE" != "f16" ]]; then
  KV_ARGS=(-ctk "$KV_TYPE" -ctv "$KV_TYPE")
fi

# Sense --device: es fa servir CUDA_VISIBLE_DEVICES.
# NEVER --reasoning off (causa deadlock del model).
CUDA_VISIBLE_DEVICES="$GPU" nohup "$BIN" \
  -m "$MODEL" -ngl 99 -fa 1 --parallel 1 -c "$CTX" "${KV_ARGS[@]}" --reasoning off \
  -b 4096 -ub 1024 -t 12 -tb 12 \
  --jinja \
  --port "$PORT" --host 0.0.0.0 \
  >> "$LOG" 2>&1 &
echo "$!" > "$PIDFILE"

ok=0
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done
[[ "$ok" == "1" ]] && echo "Flowed deep-q4 server UP — $MODEL @ :$PORT (cuda $GPU, ctx $CTX, kv $KV_TYPE)" \
                   || { echo "ERROR: not healthy in 60s — $LOG"; exit 1; }
