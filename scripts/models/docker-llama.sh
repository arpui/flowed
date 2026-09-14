#!/usr/bin/env bash
# Fluent llama.cpp server via Docker — recepta per a RTX 4060 Ti 16GB.
#
# Model: Qwen3-14B-Q4_K_M — pesos ~8.4 GB + KV ~5.2 GB (@ctx 32768) ≈ 14 GB,
# cap als 16 GB amb ~2 GB de marge (mesurat a 3090/4090).
# Paràmetres validats a fluent_dev2: vegeu docs/model-qwen14b-q4.md.
#
# Ús (a la màquina 4060):
#   scripts/models/docker-llama.sh                    # puja (llegeix .env si hi és)
#   scripts/models/docker-llama.sh --stop             # atura
#   MODEL_FILE=... HOST_PORT=12325 CTX=16384 scripts/models/docker-llama.sh
#
# Lligat a l'.env unificat: FLUENT_DEEP_* mana; HOST_PORT/MODEL_FILE/CTX queden
# com a fallback compatible.
set -euo pipefail

# Si hi ha .env a l'arrel del projecte, les seves vars fan de defaults
# (mai trepitgen variables ja exportades a l'entorn: CLI mana).
for _env in "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.env" ./.env; do
  if [[ -f "$_env" ]]; then
    while IFS= read -r _line || [[ -n "$_line" ]]; do
      _line="${_line%%#*}"
      [[ "$_line" =~ ^[[:space:]]*$ ]] && continue
      [[ "$_line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
      _k="${BASH_REMATCH[1]}"; _v="${BASH_REMATCH[2]}"
      _v="${_v%\"}"; _v="${_v#\"}"; _v="${_v%\'}"; _v="${_v#\'}"
      if [[ -z "${!_k+x}" ]]; then export "$_k=$_v"; fi
    done < "$_env"
    break
  fi
done

# Capa de sota (P1-9): el que .env i l'entorn no hagin definit surt de
# config/fluent.json, la configuració canònica del projecte.
_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -f "$_root/config/fluent.json" ]]; then
  eval "$(python3 "$_root/scripts/fluent-config.py" --sh --missing-only --no-env-file 2>/dev/null || true)"
fi

MODEL_DIR="${MODEL_DIR:-${FLUENT_MODEL_DIR:-/home/albert/aidev/models}}"
MODEL_FILE="${MODEL_FILE:-$(basename "${FLUENT_DEEP_MODEL:-Qwen3-14B-Q4_K_M.gguf}")}"
HOST_PORT="${HOST_PORT:-${APP_PORT:-${PORT:-${FLUENT_DEEP_PORT:-12322}}}}"
CTX="${CTX:-${LLAMA_CTX:-${FLUENT_DEEP_CTX:-32768}}}"   # NO baixar a 16384: els torns reals van a 12–25k tokens (overflow)
IMG="${LLAMA_IMAGE:-ghcr.io/ggml-org/llama.cpp:server-cuda}"
NAME="${CONTAINER_NAME:-qwen-fluent-server}"

if [[ "${1:-}" == "--stop" ]]; then
  # Stateful: només "stopped" si el contenidor existia/corra; si no, NOT RUNNING.
  # (docker stop imprimeix el nom en tenir èxit: redirigit, el missatge el posem nosaltres)
  if docker ps -q -f "name=^${NAME}$" 2>/dev/null | grep -q .; then
    docker stop "$NAME" >/dev/null 2>&1 || docker rm -f "$NAME" >/dev/null 2>&1 || true
    echo "stopped $NAME"
  else
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    echo "$NAME NOT RUNNING"
  fi
  exit 0
fi

if [[ ! -f "$MODEL_DIR/$MODEL_FILE" ]]; then
  echo "error: model no trobat: $MODEL_DIR/$MODEL_FILE (MODEL_DIR/MODEL_FILE)"
  exit 1
fi

# KV cache precision. f16 is what this recipe was measured with; q8_0 halves the
# KV cache (needs -fa 1, which is on) and so buys either ~2.6 GB back at ctx
# 32768 or twice the context for the same VRAM. It is a quality trade-off, so it
# is opt-in and must be MEASURED, not assumed: see docs/model-qwen14b-q4.md.
KV_TYPE="${FLUENT_DEEP_KV_TYPE:-f16}"
KV_ARGS=()
if [[ "$KV_TYPE" != "f16" ]]; then
  KV_ARGS=(-ctk "$KV_TYPE" -ctv "$KV_TYPE")
fi

# Imatge al dia: --reasoning off només existeix en builds recents.
docker pull "$IMG" 2>/dev/null || echo "(avís: no s'ha pogut actualitzar $IMG; si falla --reasoning, actualitza-la a mà)"

docker rm -f "$NAME" 2>/dev/null || true
docker run -d --rm --name "$NAME" \
  --gpus all \
  --shm-size=8g \
  -p "$HOST_PORT:8080" \
  -v "$MODEL_DIR:/models:ro" \
  "$IMG" \
  -m "/models/$MODEL_FILE" \
  --host 0.0.0.0 --port 8080 \
  -c "$CTX" -ngl 99 -fa 1 --parallel 1 "${KV_ARGS[@]}" \
  -b 4096 -ub 1024 \
  --jinja --reasoning off

ok=0
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$HOST_PORT/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
[[ "$ok" == "1" ]] && echo "llama.cpp Docker UP — $MODEL_FILE @ :$HOST_PORT (ctx $CTX, kv $KV_TYPE)" \
                   || { echo "ERROR: no respon en ~120 s — docker logs $NAME"; exit 1; }
