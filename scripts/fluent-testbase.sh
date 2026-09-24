#!/usr/bin/env bash
# El banc de proves MANUAL: el mateix perfil i el mateix fons que fa servir la
# bateria, però amb l'app oberta perquè hi pugis provar coses a mà des del navegador.
#
#   scripts/fluent-testbase.sh                 # sembra el fons, aixeca el model i l'app
#   scripts/fluent-testbase.sh --keep          # NO sembris: continua on ho vas deixar
#   scripts/fluent-testbase.sh --port 4110     # port de l'app (per defecte 4105; la bateria fa servir 4103)
#   scripts/fluent-testbase.sh --due 3         # ítems per repassar avui (per defecte 6 = una lliçó)
#   scripts/fluent-testbase.sh --profile test-en
#   scripts/fluent-testbase.sh --stop          # atura l'app (el model es queda)
#   scripts/fluent-testbase.sh --stop --models # atura l'app i també el model
#
# Fa, per aquest ordre:
#   1. el perfil de proves (només si no existeix; un que ja hi és no es reescriu);
#   2. el fons: fluent-seed.py — 21 dies de passat, 32 ítems, 6 per repassar avui.
#      ATENCIÓ: això BUIDA el dia d'avui, la cua i els patrons del perfil. És el
#      mateix reset que fa la bateria, així que el que hi facis a mà es perd la
#      propera vegada que sembris (o que corri la bateria amb aquest perfil).
#   3. el model deep (si no respon, l'aixeca; en acabar NO l'atura: l'app el necessita);
#   4. l'app, amb l'usuari i la contrasenya que t'imprimeix.
#
# Mentre proves, el que fa el servidor és a:
#   ~/.fluent/<perfil>/.metrics/guards.jsonl   (quan el guard intervé)
#   ~/.fluent/<perfil>/.metrics/notes.jsonl    (què li diu el servidor al tutor a cada torn)
set -euo pipefail
cd "$(dirname "$0")/.."

PROFILE=test-en
PORT=4105
DUE=6
DAYS=21
KEEP=0
STOP=0
STOP_MODELS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --port)    PORT="$2";    shift 2 ;;
    --due)     DUE="$2";     shift 2 ;;
    --days)    DAYS="$2";    shift 2 ;;
    --keep)    KEEP=1;       shift ;;
    --stop)    STOP=1;       shift ;;
    --models)  STOP_MODELS=1; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "opció desconeguda: $1" >&2; exit 2 ;;
  esac
done

case "$PROFILE" in
  test*|demo*|e2e*) ;;
  *) echo "❌ el banc de proves només corre en perfils de proves, no en $PROFILE" >&2; exit 2 ;;
esac

if [[ $STOP -eq 1 ]]; then
  scripts/fluent-web.sh --stop --port "$PORT"
  if [[ $STOP_MODELS -eq 1 ]]; then
    scripts/fluent-stop.sh --models-only || true
  else
    echo "(el model continua corrent; per aturar-lo també: $0 --stop --models)"
  fi
  exit 0
fi

# shellcheck source=scripts/lib-testbed.sh
source scripts/lib-testbed.sh

tb_ensure_profile "$PROFILE" "$PORT"

# Si ja hi havia una app en aquest port, s'atura ABANS de sembrar: una app viva
# podria escriure sobre el perfil just després del reset.
if [[ -f "/tmp/fluent-web-$PORT.pid" ]]; then
  echo "(hi havia una app al port $PORT; l'aturo abans)"
  scripts/fluent-web.sh --stop --port "$PORT" >/dev/null || true
  sleep 3
fi


if [[ $KEEP -eq 1 ]]; then
  echo "fons: es queda com estava (--keep)"
else
  echo "fons: el sembro (això buida avui, la cua i els patrons de $PROFILE)"
  python3 scripts/fluent-seed.py "$PROFILE" --days "$DAYS" --due "$DUE"
fi
echo

tb_ensure_model || exit $?

# L'app ha de parlar amb el model que hem comprovat, no amb el del codi per defecte.
export FLUENT_DEEP_BASE_URL="http://127.0.0.1:$(tb_model_port)"
scripts/fluent-web.sh --app --port "$PORT" "$PROFILE"

echo
echo "banc de proves manual a punt. Què mirar mentre hi proves:"
echo "  tail -f ~/.fluent/$PROFILE/.metrics/guards.jsonl"
echo "  tail -f ~/.fluent/$PROFILE/.metrics/notes.jsonl"
echo "  atura'l amb: scripts/fluent-testbase.sh --stop --port $PORT"
