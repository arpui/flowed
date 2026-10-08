#!/usr/bin/env bash
# Desenvolupament a railab contra el model remot — UNA comanda, sense variables
# al terminal. Tot viu a ~/.flowed, però només es toquen perfils de prova
# (test*/demo*/e2e*); mai naia-en, iona-en ni nes-en (de nes-en només es llegeix
# per fer la còpia test-nes). ~/.flowmath ja no existeix.
#
#   scripts/flowed-dev.sh setup     # crea els perfils de prova que falten (test-nes, test-m7, test-lang)
#   scripts/flowed-dev.sh up        # (re)engega les webs de prova i mostra els logins
#   scripts/flowed-dev.sh status    # què respon (webs + model)
#   scripts/flowed-dev.sh down      # atura les webs de prova
#
# Perfils i ports per defecte: test-nes:4206 (language, còpia de nes-en) i test-m7:4201 (math).
# Altres: DEV_WEBS="test-lang:4205 test-nes:4206" scripts/flowed-dev.sh up
# Model: FLOWED_DEEP_BASE_URL (per defecte el remot 192.168.31.102:12321).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export FLOWED_HOME="${DEV_HOME:-$HOME/.flowed}"
export FLOWED_DEEP_BASE_URL="${FLOWED_DEEP_BASE_URL:-http://192.168.31.102:12321/v1}"
export FLOWED_DEEP_MANAGED=0
WEBS="${DEV_WEBS:-test-nes:4206 test-m7:4201}"

if [[ "${1:-}" == "setup" ]]; then
  mk() { echo "  creat $1"; }
  if [[ ! -d "$FLOWED_HOME/test-nes" ]]; then
    if [[ -d "$FLOWED_HOME/nes-en" ]]; then cp -a "$FLOWED_HOME/nes-en" "$FLOWED_HOME/test-nes" && mk "test-nes (còpia de nes-en; l'original no es toca)"
    else echo "  falta $FLOWED_HOME/nes-en: no puc fer test-nes"; fi
  fi
  if [[ ! -d "$FLOWED_HOME/test-m7" ]]; then
    bash scripts/new-user.sh test-m7 --port 4201 >/dev/null &&
      python3 scripts/flowed-profile.py test-m7 --name Test --native ca --level m7 --goal m7 --minutes 20 --motivation school >/dev/null && mk "test-m7 (math)"
  fi
  if [[ ! -d "$FLOWED_HOME/test-lang" ]]; then
    bash scripts/new-user.sh test-lang --domain language --port 4205 >/dev/null &&
      python3 scripts/flowed-profile.py test-lang --domain language --name Test --native Catalan --target English --level A1 --goal A2 --minutes 20 --motivation practice >/dev/null && mk "test-lang (language, net)"
  fi
  echo "home: $FLOWED_HOME"; ls -d "$FLOWED_HOME"/test-* 2>/dev/null
  exit 0
fi

for spec in $WEBS; do
  id="${spec%%:*}"
  [[ "$id" =~ ^(test|demo|e2e) ]] || { echo "error: $id no és un perfil de prova (test*/demo*/e2e*)" >&2; exit 2; }
  [[ -f "$FLOWED_HOME/$id/learner-profile.json" ]] || { echo "error: falta $FLOWED_HOME/$id (scripts/new-user.sh $id)" >&2; exit 2; }
done

case "${1:-status}" in
  up)
    for spec in $WEBS; do
      id="${spec%%:*}"; port="${spec##*:}"
      bash scripts/flowed-web.sh --stop --port "$port" >/dev/null 2>&1 || true
      bash scripts/flowed-web.sh --app "$id" --port "$port" 2>&1 | grep -E "UP|login|local:|FAIL|error" || echo "$id :$port — NO ha arrencat (mira $FLOWED_HOME/$id/*web-$port.log)"
    done ;;
  down)
    for spec in $WEBS; do
      bash scripts/flowed-web.sh --stop --port "${spec##*:}" 2>&1 | tail -1
    done ;;
  status)
    echo "home: $FLOWED_HOME"
    echo "model: $FLOWED_DEEP_BASE_URL → $(curl -s -m 3 -o /dev/null -w '%{http_code}' "${FLOWED_DEEP_BASE_URL%/v1}/health")"
    for spec in $WEBS; do
      echo "${spec%%:*} :${spec##*:} → $(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${spec##*:}/")"
    done ;;
  *) echo "ús: $0 setup|up|status|down" >&2; exit 1 ;;
esac
