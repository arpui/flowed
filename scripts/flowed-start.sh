#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-paths.sh"   # FLOWED_HOME_DIR: where the profiles live
# Flowed START — puja tot segons .env (models + webs), a qualsevol màquina.
#
#   scripts/flowed-start.sh [--gpu 4090|3090] [--yes] [--dry-run]
#                           [--models-only] [--webs-only]
#
# Config: .env a l'arrel (cp .env.railab/.env.rapve segons la màquina).
# Totes les vars es poden sobreescriure per entorn o CLI.
# El deep es tria per FLOWED_DEEP_MODEL (mateix llançador per Q6 i Q4).
# El face només si FLOWED_FACE_ENABLED=1 (el deep el cobreix via fallback).
# Si FLOWED_DEEP_MANAGED=0 (p. ex. 4060 amb Docker extern), el model només
# es comprova (/health), no es llança.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

flowed_load_env "$ROOT"
if [[ -z "$FLOWED_ENV_FILE" ]]; then
  # Without it every value comes from config/fluent.json, which describes railab.
  echo "error: falta $ROOT/.env — cada màquina en té un: cp .env.rapve .env (llvm) · cp .env.railab .env (railab)"
  exit 1
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
FLOWED_DEEP_MODEL="${FLOWED_DEEP_MODEL:-/home/albert/aidev/models/Qwen3-14B-Q4_K_M.gguf}"
FLOWED_DEEP_PORT="${FLOWED_DEEP_PORT:-12322}"
FLOWED_DEEP_GPU="${FLOWED_DEEP_GPU:-1}"
FLOWED_DEEP_CTX="${FLOWED_DEEP_CTX:-32768}"
FLOWED_FACE_ENABLED="${FLOWED_FACE_ENABLED:-0}"
FLOWED_FACE_MODEL="${FLOWED_FACE_MODEL:-/home/albert/aidev/models/Qwen3-1.7B-UD-Q4_K_XL.gguf}"
FLOWED_FACE_PORT="${FLOWED_FACE_PORT:-12323}"
FLOWED_FACE_GPU="${FLOWED_FACE_GPU:-1}"
FLOWED_FACE_CTX="${FLOWED_FACE_CTX:-32768}"
FLOWED_WEBS="${FLOWED_WEBS:-alex-en:4100 sam-en:4101 demo-en:4102}"

GPU_CLI=""
YES=0
DRY=0
FORCE=0
MODELS_ONLY=0
WEBS_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpu) GPU_CLI="${2:-}"; shift ;;
    --yes) YES=1 ;;
    --force) FORCE=1 ;;
    --dry-run) DRY=1 ;;
    --models-only) MODELS_ONLY=1 ;;
    --webs-only) WEBS_ONLY=1 ;;
    *) echo "ús: $0 [--gpu 4090|3090] [--yes] [--force] [--dry-run] [--models-only] [--webs-only]"; exit 1 ;;
  esac
  shift
done

# --gpu 4090|3090 -> CUDA 0|1 pel deep (NOTA: ordre CUDA != nvidia-smi aquí:
# CUDA 0 = RTX 4090 = nvidia-smi 1 · CUDA 1 = RTX 3090 = nvidia-smi 0)
if [[ -n "$GPU_CLI" ]]; then
  case "$GPU_CLI" in
    4090) FLOWED_DEEP_GPU=0 ;;
    3090) FLOWED_DEEP_GPU=1 ;;
    *) echo "error: --gpu 4090|3090"; exit 1 ;;
  esac
elif [[ "$YES" == "0" && -t 0 && "$WEBS_ONLY" == "0" && "$DRY" == "0" && "$FLOWED_DEEP_BACKEND" != "docker" ]]; then
  cur="3090"; [[ "$FLOWED_DEEP_GPU" == "0" ]] && cur="4090"
  echo "GPU pel deep? (actual env: $cur)"
  echo "  1) 4090 (CUDA 0)   2) 3090 (CUDA 1)"
  read -rp "tria [1/2, defecte: env]: " ans
  case "${ans:-}" in
    1) FLOWED_DEEP_GPU=0 ;;
    2) FLOWED_DEEP_GPU=1 ;;
  esac
fi

port_up() { curl -sf -m 2 "http://127.0.0.1:$1/health" >/dev/null 2>&1; }
port_bound() { ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1$"; }
# Qui ocupa un port host? Nom de contenidor Docker (si el publica) o "".
# El Docker mostra el port del CONTENIDOR (8080), mai el del host: per això
# cal resoldre per published-port, no per cmdline.
docker_holder() {
  docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | while read -r name ports; do
    [[ "$ports" == *":$1->"* ]] && echo "$name"
  done || true
}
# PIDs host dels processos d'un contenidor (per excloure'ls d'aliens).
docker_pids() {
  docker top "$1" 2>/dev/null | awk 'NR>1 {print $2}' | grep -E '^[0-9]+$' | sort -u || true
}
# Descripció d'una línia del titular d'un port (display; mai avorta: sempre rc 0).
describe_holder() {
  local port="$1" names="" pid="" cmd=""
  names="$(docker_holder "$port" | tr '\n' ' ')"
  if [[ -n "${names// /}" ]]; then echo "contenidor '$names'"; return 0; fi
  pid="$(ss -tlnp 2>/dev/null | grep -E "[:.]$port " | grep -oP 'pid=\K[0-9]+' | head -1 || true)"
  if [[ -n "$pid" ]]; then cmd="$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | cut -c1-80)"; echo "procés $pid ($cmd)"; return 0; fi
  echo "port lliure"; return 0
}
wait_port_free() {
  for _ in $(seq 1 15); do
    port_bound "$1" || return 0
    sleep 1
  done
  echo "error: el port $1 continua ocupat 15 s després del stop — avorto"
  return 1
}
# pidfile ranci (procés mort): netejar abans de decidir (sense matar res viu)
clean_stale_pidfile() {
  local pf="$1"
  [[ -f "$pf" ]] || return 0
  local alive=0
  for pid in $(cat "$pf" 2>/dev/null); do kill -0 "$pid" 2>/dev/null && alive=1 && break; done
  if [[ "$alive" == "0" ]]; then
    echo "(netejant pidfile ranci $pf)"
    rm -f "$pf"
  fi
}

# --- detecció (només lectura) --------------------------------------------------
echo "=== flowed-start: detecció ==="
DEEP_UP=0; FACE_UP=0
if [[ "$WEBS_ONLY" == "0" ]]; then
  if port_up "$FLOWED_DEEP_PORT"; then DEEP_UP=1; echo "deep :$FLOWED_DEEP_PORT — respon /health"; else DEEP_UP=0; echo "deep :$FLOWED_DEEP_PORT — no respon"; fi
  echo "  deep :$FLOWED_DEEP_PORT — trobat: $(describe_holder "$FLOWED_DEEP_PORT")"
  if [[ "$FLOWED_FACE_ENABLED" == "1" ]]; then
    if port_up "$FLOWED_FACE_PORT"; then FACE_UP=1; echo "face :$FLOWED_FACE_PORT — JA PUJAT (es respecta)"; else echo "face :$FLOWED_FACE_PORT — aturat"; fi
  else
    echo "face — DESACTIVAT (el deep el cobreix)"
  fi
  nvidia-smi --query-gpu=index,name,memory.used,memory.free --format=csv 2>/dev/null || echo "(nvidia-smi no disponible)"
fi
echo "--- webs ---"
web_mode() {
  PROFILE_DIR="$FLOWED_HOME_DIR/$1" python3 -c \
    "import json,os;print(json.load(open(os.environ['PROFILE_DIR']+'/learner-profile.json')).get('preferences',{}).get('tutor_style','classic'))" \
    2>/dev/null || echo "classic"
}
for spec in $FLOWED_WEBS; do
  id="${spec%%:*}"; port="${spec##*:}"
  if [[ ! -f "$FLOWED_HOME_DIR/$id/learner-profile.json" ]]; then
    echo "web $id :$port — SENSE PERFIL (es salta)"
  else
    clean_stale_pidfile "/tmp/fluent-web-$port.pid"
    if [[ -f "/tmp/fluent-web-$port.pid" ]] || port_bound "$port"; then
      echo "web $id :$port — ACTIVA [mode: $(web_mode "$id")] (es farà stop + relleu)"
    else
      echo "web $id :$port — aturada [mode: $(web_mode "$id")]"
    fi
  fi
done

# --- guàrdia: processos estranys a les GPUs de destí -----------------------------
if [[ "$WEBS_ONLY" == "0" && "$DRY" == "0" && "$FLOWED_DEEP_MANAGED" == "1" ]]; then
  # Exclosos: contenidors Docker que publiquen els nostres ports (el seu
  # cmdline mostra el port del CONTENIDOR, mai el del host: sense això, el
  # nostre propi model semblaria aliè). Són candidats al swap, no intrusos.
  excluded=""
  if [[ "$FLOWED_DEEP_BACKEND" == "docker" ]]; then
    for p in "$FLOWED_DEEP_PORT" "$FLOWED_FACE_PORT"; do
      for c in $(docker_holder "$p"); do excluded="$excluded $(docker_pids "$c")"; done
    done
  fi
  mapfile -t GPUPIDS < <(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null || true)
  aliens=()
  if [[ "${#GPUPIDS[@]}" -gt 0 ]]; then
    echo "--- GPU ---"
    for rawpid in "${GPUPIDS[@]}"; do
      pid="$(echo "$rawpid" | tr -d '[:space:]')"
      [[ -n "$pid" ]] || continue
      if [[ " $excluded " == *" $pid "* ]]; then
        echo "  pid $pid — contenidor Docker als nostres ports (candidat swap, no intrús)"
        continue
      fi
      cmd="$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null || echo '?')"
      if [[ "$cmd" == *"llama-server"* && ( "$cmd" == *"$FLOWED_DEEP_PORT"* || "$cmd" == *"$FLOWED_FACE_PORT"* ) ]]; then
        echo "  pid $pid — nostre (:$FLOWED_DEEP_PORT/:$FLOWED_FACE_PORT, es respecta)"
      else
        aliens+=("$pid")
        echo "  pid $pid — ALIÈ: $(echo "$cmd" | cut -c1-120)"
      fi
    done
  fi
  if [[ "${#aliens[@]}" -gt 0 ]]; then
    echo "HI HA ${#aliens[@]} PROCÉS/OS ALIENS a la GPU."
    if [[ "$FORCE" == "1" ]]; then
      echo "(--force: continuo malgrat aliens — risc de contenció de VRAM)"
    else
      [[ "$YES" == "1" ]] && { echo "avorto (fes --force per continuar igualment)"; exit 1; }
      read -rp "Continuo igualment? [s/N]: " ans
      [[ "${ans:-N}" =~ ^[sS]$ ]] || { echo "avortat."; exit 1; }
    fi
  fi
fi

# --- pla -------------------------------------------------------------------------
echo
echo "Config: $FLOWED_ENV_FILE (la resta, de config/fluent.json)"
echo "Pla: deep=$(basename "$FLOWED_DEEP_MODEL") :$FLOWED_DEEP_PORT (backend=$FLOWED_DEEP_BACKEND, CUDA $FLOWED_DEEP_GPU, ctx $FLOWED_DEEP_CTX, managed=$FLOWED_DEEP_MANAGED)"
[[ "$FLOWED_FACE_ENABLED" == "1" ]] && echo "     face :$FLOWED_FACE_PORT (CUDA $FLOWED_FACE_GPU)" || echo "     face: off"
[[ "$MODELS_ONLY" == "0" ]] && echo "     webs: stop+releu [$FLOWED_WEBS]"
if [[ "$DRY" == "1" ]]; then echo "(dry-run: no s'executa res)"; exit 0; fi
if [[ "$YES" == "0" ]]; then
  read -rp "engego? [S/n]: " ans
  [[ "${ans:-S}" =~ ^[sS]$ ]] || { echo "avortat."; exit 1; }
fi

# --- models -----------------------------------------------------------------------
if [[ "$WEBS_ONLY" == "0" ]]; then
  echo
  if [[ "$FLOWED_DEEP_MANAGED" == "1" ]]; then
    if [[ "$FLOWED_DEEP_BACKEND" == "docker" ]]; then
      # Swap transparent 1:1 de port (agnòstic a noms: default i nostre poden
      # dir-se igual). Un port sa NO distingeix: només l'estat diu si és nostre.
      if [[ -f /tmp/fluent-deep-docker.state ]] && port_up "$FLOWED_DEEP_PORT"; then
        echo "(estat: el deep Docker és nostre i respon — es respecta)"
      else
        if port_bound "$FLOWED_DEEP_PORT"; then
          if [[ -n "${FLOWED_DEFAULT_MANAGER:-}" && -x "$FLOWED_DEFAULT_MANAGER" ]]; then
            echo "(swap: aturant default via $FLOWED_DEFAULT_MANAGER)"
            "$FLOWED_DEFAULT_MANAGER" stop 2>/dev/null || true
            wait_port_free "$FLOWED_DEEP_PORT" || exit 1
          else
            echo "error: port $FLOWED_DEEP_PORT ocupat per un altre i no hi ha FLOWED_DEFAULT_MANAGER — avorto (no robo ports)"
            exit 1
          fi
        fi
        # El docker-llama.sh llegeix FLOWED_DEEP_* del .env/entorn (mateixa font).
        scripts/models/docker-llama.sh && echo "docker" > /tmp/fluent-deep-docker.state
      fi
    elif [[ "$DEEP_UP" == "0" ]]; then
      LLAMA_DEEP_MODEL="$FLOWED_DEEP_MODEL" LLAMA_DEEP_GPU="$FLOWED_DEEP_GPU" \
        LLAMA_DEEP_CTX="$FLOWED_DEEP_CTX" \
        scripts/models/llama-deep.sh --port "$FLOWED_DEEP_PORT"
    fi
  fi
  if [[ "$FLOWED_FACE_ENABLED" == "1" && "$FACE_UP" == "0" ]]; then
    LLAMA_QWEN1_7B_Q4_MODEL="$FLOWED_FACE_MODEL" LLAMA_QWEN1_7B_Q4_GPU="$FLOWED_FACE_GPU" \
      LLAMA_QWEN1_7B_Q4_CTX="$FLOWED_FACE_CTX" \
      scripts/models/llama-qwen1.7b-q4.sh --port "$FLOWED_FACE_PORT" \
      || echo "(face no pujat — el deep el cobreix via fallback)"
  fi
  nvidia-smi --query-gpu=index,name,memory.used,memory.free --format=csv 2>/dev/null || true
fi

# --- webs -------------------------------------------------------------------------
# L'env mana també al servidor: derivar les URLs del port (amb 127.0.0.1) si
# l'usuari no les ha fixades explícitament (p. ex. model remot per IP).
export FLOWED_DEEP_BASE_URL="${FLOWED_DEEP_BASE_URL:-http://127.0.0.1:$FLOWED_DEEP_PORT/v1}"
export FLOWED_FACE_BASE_URL="${FLOWED_FACE_BASE_URL:-http://127.0.0.1:$FLOWED_FACE_PORT/v1}"
if [[ "$MODELS_ONLY" == "0" ]]; then
  echo
  export FLOWED_DEEP_PORT FLOWED_FACE_PORT
  for spec in $FLOWED_WEBS; do
    id="${spec%%:*}"; port="${spec##*:}"
    if [[ ! -f "$FLOWED_HOME_DIR/$id/learner-profile.json" ]]; then
      echo "(salto $id: sense perfil)"
      continue
    fi
    scripts/flowed-web.sh --stop --port "$port" 2>/dev/null || true
    wait_port_free "$port"
    scripts/flowed-web.sh --app "$id" --port "$port"
  done
fi

echo
echo "=== flowed-start: llest ==="
port_up "$FLOWED_DEEP_PORT" && echo "deep :$FLOWED_DEEP_PORT OK" || echo "deep :$FLOWED_DEEP_PORT ATURAT"
if [[ "$FLOWED_FACE_ENABLED" == "1" ]]; then
  port_up "$FLOWED_FACE_PORT" && echo "face :$FLOWED_FACE_PORT OK" || echo "face :$FLOWED_FACE_PORT aturat (fallback a deep)"
fi
for spec in $FLOWED_WEBS; do
  id="${spec%%:*}"; port="${spec##*:}"
  [[ -f "$FLOWED_HOME_DIR/$id/learner-profile.json" ]] && echo "web $id :$port — mode: $(web_mode "$id")" || true
done
