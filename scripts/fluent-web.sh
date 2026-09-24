#!/usr/bin/env bash
# Fluent web launcher — runs a Fluent learner profile's web UI.
#
# Usage:
#   scripts/fluent-web.sh --web [--port N] [profile-id]   ARXIVAT (UI d'opencode)
#   scripts/fluent-web.sh --app [--port N] [profile-id]   standalone Fluent web server (no opencode)
#   scripts/fluent-web.sh --stop [--port N]               stop an instance started by this script
#
# profile-id : name of a profile dir under ~/.fluent/<id>/ (default: the repo's own data/ dir)
# Password   : OPENCODE_SERVER_PASSWORD env var, or generated on the fly (shown once, never stored)
#
# Ports (defaults): --web 4097, --app 4100
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

# Configuració (P1-9): .env primer, config/fluent.json per a la resta. Aquest
# llançador no llegia cap de les dues, així que FLUENT_STREAM i els ports dels
# models li arribaven només si algú els exportava a mà.
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
if [[ -f "$ROOT/config/fluent.json" ]]; then
  eval "$(python3 "$ROOT/scripts/fluent-config.py" --sh --missing-only --no-env-file 2>/dev/null || true)"
fi

MODE=""
PORT=""
PROFILE=""
STOP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --web) MODE="web" ;;
    --app) MODE="app" ;;
    --stop) STOP=1 ;;
    --port) PORT="${2:-}"; shift ;;
    *) PROFILE="$1" ;;
  esac
  shift
done

if [[ "$STOP" == "1" ]]; then
  stop_pidfile() {
    local pf="$1"
    [[ -e "$pf" ]] || return 0
    # TERM, espera que mori/alliberi (bun pot trigar o ignorar el TERM si és
    # orfe), i KILL si cal. El pidfile conté el wrapper; el fill pot tenir un
    # altre PGID, per això es mata el pid exacte i es comprova la mort.
    for pid in $(cat "$pf"); do
      kill "$pid" 2>/dev/null || true
      for _ in $(seq 1 5); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
      done
      kill -9 "$pid" 2>/dev/null || true
    done
    rm -f "$pf"
  }

  if [[ -n "$PORT" ]]; then
    PIDFILE="/tmp/fluent-web-$PORT.pid"
    if [[ -f "$PIDFILE" ]]; then
      stop_pidfile "$PIDFILE"
      echo "stopped instance on port $PORT"
    else
      echo "no instance found on port $PORT"
    fi
  else
    # stop every instance this script knows about
    for pf in /tmp/fluent-web-*.pid; do
      [[ -e "$pf" ]] || continue
      stop_pidfile "$pf"
    done
    echo "stopped all fluent-web instances"
  fi
  exit 0
fi

if [[ -z "$MODE" ]]; then
  echo "usage: scripts/fluent-web.sh --web|--app [--port N] [profile-id]"
  echo "       scripts/fluent-web.sh --stop [--port N]"
  exit 1
fi

if [[ -z "$PORT" ]]; then
  case "$MODE" in
    web) PORT=4097 ;;
    app) PORT=4100 ;;
  esac
fi

# --- profile / data dir ----------------------------------------------------
if [[ -n "$PROFILE" ]]; then
  DATA_DIR="$HOME/.fluent/$PROFILE"
  if [[ ! -f "$DATA_DIR/learner-profile.json" ]]; then
    echo "error: profile '$PROFILE' not found (missing $DATA_DIR/learner-profile.json)"
    exit 1
  fi
  MDNS_DOMAIN="fluent-$PROFILE.local"
  PROFILE_LABEL="$PROFILE"
else
  DATA_DIR="$ROOT/data"
  MDNS_DOMAIN="fluent.local"
  PROFILE_LABEL="default (repo data/)"
fi

# --- preflight: fail fast (1 s, clear cause) instead of a 20 s mystery timeout
if [[ "$MODE" == "app" ]]; then
  if ! command -v bun >/dev/null 2>&1 && [[ ! -x "$HOME/.bun/bin/bun" ]]; then
    echo "error: bun no trobat — instal·la'l: curl -fsSL https://bun.sh/install | bash"
    exit 1
  fi
else
  echo "error: el mode --web (UI d'opencode) està arxivat des del renombrat de"
  echo "       2026-09-13: els agents i les comandes viuen a prompts/ i opencode"
  echo "       ja no els descobreix. El que hi havia és a obsolet/opencode-runtime/."
  echo "       Fes servir --app (servidor propi de Fluent)."
  exit 1
fi
command -v python3 >/dev/null 2>&1 || { echo "error: python3 no trobat"; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "error: openssl no trobat"; exit 1; }

# --- password ----------------------------------------------------------------
# Priority: FLUENT_WEB_PASSWORD env > stored per-profile file > generate+store.
# The stored file makes each user's password stable across restarts.
# Deliberately ignores an inherited OPENCODE_SERVER_PASSWORD so the fluent
# instance never silently shares the host opencode server's password.
if [[ -n "$PROFILE" ]]; then
  PWFILE="$HOME/.fluent/$PROFILE/.web-password"
else
  PWFILE="$HOME/.fluent/.web-password-default"
fi
if [[ -n "${FLUENT_WEB_PASSWORD:-}" ]]; then
  OPENCODE_SERVER_PASSWORD="$FLUENT_WEB_PASSWORD"
elif [[ -f "$PWFILE" ]]; then
  OPENCODE_SERVER_PASSWORD="$(tr -d '[:space:]' < "$PWFILE")"
else
  OPENCODE_SERVER_PASSWORD="$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | cut -c1-16)"
  (umask 077 && printf '%s\n' "$OPENCODE_SERVER_PASSWORD" > "$PWFILE")
fi
export OPENCODE_SERVER_PASSWORD
export FLUENT_DATA_DIR="$DATA_DIR"

# --- per-user session isolation ---------------------------------------------
# Each profile keeps its own sessions DB (now ~/.fluent/<id>/sessions/sessions.db;
# the server creates the directory). XDG_DATA_HOME is still exported for the
# archived opencode path and for the previous build of the app, which writes to
# ~/.fluent/<id>/.opencode/opencode/opencode.db — that file is never deleted.
if [[ -n "$PROFILE" ]]; then
  export XDG_DATA_HOME="$HOME/.fluent/$PROFILE/.opencode"
  mkdir -p "$XDG_DATA_HOME/opencode" "$HOME/.fluent/$PROFILE/sessions"
fi

# --- port / pidfile checks -----------------------------------------------------
port_bound() { ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1$"; }
if port_bound "$PORT"; then
  echo "error: port $PORT is already in use"
  exit 1
fi
PIDFILE="/tmp/fluent-web-$PORT.pid"
if [[ -f "$PIDFILE" ]]; then
  # pidfile ranci (procés mort + port lliure) → netejar i continuar, no bloquejar
  alive=0
  for pid in $(cat "$PIDFILE" 2>/dev/null); do kill -0 "$pid" 2>/dev/null && alive=1 && break; done
  if [[ "$alive" == "0" ]]; then
    echo "(netejant pidfile ranci $PIDFILE — cap procés viu, port lliure)"
    rm -f "$PIDFILE"
  else
    echo "error: pidfile $PIDFILE exists — run: scripts/fluent-web.sh --stop --port $PORT"
    exit 1
  fi
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
LOG="$DATA_DIR/fluent-web-$PORT.log"
PIDS=()

# The learner instance must keep the tutor prompt even when the launcher's
# shell belongs to the opencode desktop app (which exports OPENCODE_CLIENT=
# desktop / XDG_STATE_HOME=...ai.opencode.desktop and would flip the fluent
# plugin into dev mode, stripping AGENTS.md from the system prompt).
ENV_SANITIZED="env -u OPENCODE_CLIENT -u XDG_STATE_HOME FLUENT_DEV=0"

case "$MODE" in
  web)
    nohup $ENV_SANITIZED opencode web --port "$PORT" --hostname 0.0.0.0 --mdns --mdns-domain "$MDNS_DOMAIN" \
      >> "$LOG" 2>&1 &
    PIDS+=("$!")
    ;;
  app)
    BUN="$(command -v bun || echo "$HOME/.bun/bin/bun")"
    # Standalone server (no opencode, no proxy): serves the static UI + API +
    # auth + setup-state directly and writes sessions straight into
    # ~/.fluent/<id>/sessions/sessions.db (compatible schema, so the
    # Fluent Python hooks keep working unchanged).
    nohup $ENV_SANITIZED FLUENT_DATA_DIR="$DATA_DIR" PORT="$PORT" \
      FLUENT_WEB_PASSWORD="$OPENCODE_SERVER_PASSWORD" \
      "$BUN" "$ROOT/server/src/index.ts" >> "$LOG" 2>&1 &
    PIDS+=("$!")
    ;;
esac
echo "${PIDS[*]}" > "$PIDFILE"

# --- wait for health -------------------------------------------------------------
ok=0
case "$MODE" in
  web) HEALTH="http://127.0.0.1:$PORT/global/health" ;;
  app) HEALTH="http://127.0.0.1:$PORT/api/global/health" ;;
esac
for _ in $(seq 1 20); do
  if curl -sf -u "opencode:$OPENCODE_SERVER_PASSWORD" "$HEALTH" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done

echo
if [[ "$ok" == "1" ]]; then
  echo "Fluent web UP (mode=$MODE, profile=$PROFILE_LABEL, port=$PORT)"
  echo "  local:    http://localhost:$PORT"
  [[ -n "$IP" ]] && echo "  network:  http://$IP:$PORT"
  [[ "$MODE" == "web" ]] && echo "  mDNS:     http://$MDNS_DOMAIN:$PORT"
  # login user = learner first name (lowercased); legacy "opencode" also works
  LOGIN_NAME="$(python3 -c "import json;print(json.load(open('$DATA_DIR/learner-profile.json')).get('learner',{}).get('name','').strip().lower())" 2>/dev/null || true)"
  [[ -z "$LOGIN_NAME" ]] && LOGIN_NAME="opencode"
  if [[ -f "$PWFILE" ]]; then
    echo "  login:    $LOGIN_NAME / $OPENCODE_SERVER_PASSWORD   (basic auth, stored in $PWFILE — stable across restarts)"
  else
    echo "  login:    $LOGIN_NAME / $OPENCODE_SERVER_PASSWORD   (basic auth, shown once — not stored)"
  fi
  echo "  log:      $LOG"
  echo "  stop:     scripts/fluent-web.sh --stop --port $PORT"
  # --- model status (informational only — never starts or stops anything) --------
  model_status() {
    local port="$1" label="$2"
    if curl -sf -m 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
      echo "  model:    $label — OK (port $port)"
    else
      echo "  model:    $label — NOT RUNNING (port $port)"
    fi
  }
  model_status "${FLUENT_DEEP_PORT:-12322}" "deep  (tutor, chat, sessions)"
  model_status "${FLUENT_FACE_PORT:-12323}" "face  (vocab, review, progress, setup)"
else
  echo "ERROR: server did not become healthy in 20s — check $LOG"
  echo "(netejant el procés fallit per no deixar orfes ni pidfiles rancis...)"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 5); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -9 "$pid" 2>/dev/null || true
  done
  rm -f "$PIDFILE"
  exit 1
fi
