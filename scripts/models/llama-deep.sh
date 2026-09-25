#!/usr/bin/env bash
# Flowed "deep" model server — tutor principal (Qwen3-14B-Q6_K).
#
# IMPORTANT (2026-08-28): el 14B HA d'anar a la RTX 4090 (CUDA0), NO a la 3090.
# Mesura: prompt ~1400 tokens → 3090 = 146 s, 4090 = 14 s (~10× més ràpida).
# A la 3090 l'AGENTS.md (~4096 tokens) triga 165–427 s i venç els timeouts.
# L'omnicoder legacy sí que pot estar a la 3090 (scripts/models/llama-omnicoder.sh, GPU=1).
#
# ⚠️ CRÍTIC (si no, 502 / lent >300s / [object Object] a la UI):
#   - --reasoning off: elimina reasoning_content (la UI web pinta [object Object] si el rep).
#     El deadlock anterior (CPU ~700%) ERA el KV-spill (n_slots=4 + -c gran), NO el --reasoning off;
#     amb --parallel 1 + sense KV-quant és segur i accelera les respostes.
#   - --parallel 1 (sinó n_slots=4 + -c gran → KV cache no cap a la VRAM → spill a RAM → gen a 2 t/s)
#   - NO posar -ctk/-ctv (KV-quant): fa el prefill de prompts llargs ~30× més lent (144→36 t/s),
#     que és el coll d'ampolla real de /fluent-learn (prompt ~12k tokens). Sense quant, prefill ~4300 t/s.
#   - -c 49152: Cal prou per a un torn sencer (AGENTS.md + SKILL.md + scaffold + històric).
#     Amb -c 24576 el model rebia "request (25399 tokens) exceeds context" → error d'opencode →
#     la UI pintava [object Object] i el model reintentava fins que encaixava. 49152 (un slot, f16)
#     cap a la 4090 sense spill (pesos ~11.5GB + KV ~9GB + overhead ~3GB ≈ 23.5GB < 24GB).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$ROOT"

MODEL="${LLAMA_DEEP_MODEL:-/home/albert/aidev/models/Qwen3-14B-Q6_K.gguf}"
PORT="${LLAMA_DEEP_PORT:-12322}"
GPU="${LLAMA_DEEP_GPU:-0}"    # CUDA 0 = RTX 4090 (nvidia-smi GPU1) en aquesta màquina
CTX="${LLAMA_DEEP_CTX:-49152}"
BIN="${LLAMA_DEEP_BIN:-/home/albert/aidev/tools/llama.cpp/build/bin/llama-server}"
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

PIDFILE="/tmp/fluent-deep-$PORT.pid"
LOG="/tmp/fluent-deep-$PORT.log"

if [[ "$STOP" == "1" ]]; then
  ran=0
  [[ -f "$PIDFILE" ]] && { ran=1; for pid in $(cat "$PIDFILE"); do kill "$pid" 2>/dev/null || true; done; } || true
  rm -f "$PIDFILE"
  # + qualsevol orfe escoltant el port (sense pidfile): TERM, espera, KILL
  orphans=$(ss -tlnp 2>/dev/null | grep -E "[:.]$PORT " | grep -oP "pid=\K[0-9]+" | sort -u || true)
  [[ -n "$orphans" ]] && ran=1
  for pid in $orphans; do
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 5); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -9 "$pid" 2>/dev/null || true
  done
  [[ "$ran" == "1" ]] && echo "stopped deep server on port $PORT" || echo "deep NOT RUNNING (port $PORT)"; exit 0
fi

if [[ ! -x "$BIN" ]]; then echo "error: llama-server not found at $BIN"; exit 1; fi
if [[ ! -f "$MODEL" ]]; then echo "error: model not found: $MODEL"; exit 1; fi
if ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORT$"; then
  echo "error: port $PORT in use"; exit 1
fi

# Sense --device: es fa servir CUDA_VISIBLE_DEVICES (coincideix amb la resta de scripts).
# NEVER --reasoning off (causa deadlock del model).
CUDA_VISIBLE_DEVICES="$GPU" nohup "$BIN" \
  -m "$MODEL" -ngl 99 -fa 1 --parallel 1 -c "$CTX" --reasoning off \
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
[[ "$ok" == "1" ]] && echo "Flowed deep server UP — $MODEL @ :$PORT (cuda $GPU, ctx $CTX)" \
                   || { echo "ERROR: not healthy in 60s — $LOG"; exit 1; }
