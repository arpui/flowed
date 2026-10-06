#!/usr/bin/env bash
# La bateria estàndard: la mateixa cada vegada, perquè dos resultats es puguin
# comparar. Editar-la és decidir què vol dir "va bé"; canviar-la entre dues
# execucions és perdre la comparació.
#
#   scripts/flowed-bench.sh                      # bateria de temperatura
#   scripts/flowed-bench.sh --quick              # només la base, per mirar si tot rutlla
#   scripts/flowed-bench.sh --steps --quick     # una lliçó només de targetes de passos (traça anotada)
#   scripts/flowed-bench.sh --go --quick        # només targetes del banc a pràctica lliure
#   scripts/flowed-bench.sh --facts --quick     # només el drill de fets (model)
#   scripts/flowed-bench.sh --review --quick    # només la lliçó (cua sembrada)
#   scripts/flowed-bench.sh --days --quick --repeat 1   # 5 dies seguits: l'SM-2 fa tornar el fallat i allunya l'encertat
#   scripts/flowed-bench.sh --curriculum --quick --repeat 1   # 5 dies d'un alumne simulat A1→A2 en pràctica lliure: competència assignada, exercici, registre, camí
#   scripts/flowed-bench.sh --curriculum --quick --repeat 1 --span 12   # el mateix, 12 dies (per veure consolidar i el cicle d'oblit)
#   scripts/flowed-bench.sh --ladder --quick --repeat 1 --span 3   # A0→A1→prova de nivell→tall→A2 amb el tutor real (3 dies d'A1, 2 d'A2)
#   scripts/flowed-bench.sh --ladder-fail --quick --repeat 1 --span 3   # el mateix, però la prova es contesta tot malament: el curs NO es tanca
#   scripts/flowed-bench.sh --ladder-stop --quick --repeat 1 --span 3   # para just abans de la prova (~70-80%): la fas tu mateix a la web
#   scripts/flowed-bench.sh --port 4201 --repeat 5
#   scripts/flowed-bench.sh --keep-model         # no aturis el model encara que l'hagi aixecat el bench
#   scripts/flowed-bench.sh --no-start           # no aixequis res: si el model no hi és, avorta
#
# Abans de mesurar deixa a punt el que la prova necessita, i només això:
#   1. el perfil de proves (només si no existeix: es crea i es configura; un que ja hi és no es toca);
#   2. el model deep (si no respon, l'aixeca amb flowed-start.sh --models-only;
#      si ja corria, no el toca, i en acabar només atura el que ha aixecat ell).
# Per a cada configuració el sweep reinicia l'app amb el mostreig nou i
# comprova que l'app el fa servir de veritat. Res del repositori es reescriu;
# tot va a results/sweep-<data>/.
set -euo pipefail
cd "$(dirname "$0")/.."

PROFILE=test-math
PORT=4200
REPEAT=3
QUICK=0
KEEP_MODEL=0
NO_START=0
SCENARIOS=(--scenario lesson)
LEVEL=""
DUE=""
SPAN=""
TEST_MODE=""
STOP_BEFORE_TEST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --port)    PORT="$2";    shift 2 ;;
    --repeat)  REPEAT="$2";  shift 2 ;;
    --quick)   QUICK=1;      shift ;;
    --level)   LEVEL="$2";   shift 2 ;;
    --due)     DUE="$2";     shift 2 ;;
    --span)    SPAN="$2";    shift 2 ;;
    --keep-model) KEEP_MODEL=1; shift ;;
    --no-start)   NO_START=1;   shift ;;
    --lesson)  SCENARIOS=(--scenario lesson);  shift ;;
    --go)      SCENARIOS=(--scenario go);      shift ;;
    --steps)   SCENARIOS=(--scenario steps);   shift ;;
    --facts)   SCENARIOS=(--scenario facts);   shift ;;
    --review)  SCENARIOS=(--scenario review);  shift ;;
    --days)    SCENARIOS=(--scenario days);    shift ;;
    --curriculum) SCENARIOS=(--scenario curriculum); shift ;;
    --ladder)  SCENARIOS=(--scenario ladder);  shift ;;
    --ladder-fail) SCENARIOS=(--scenario ladder); TEST_MODE=fail; shift ;;
    --ladder-stop) SCENARIOS=(--scenario ladder); STOP_BEFORE_TEST=1; shift ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "opció desconeguda: $1" >&2; exit 2 ;;
  esac
done

# --level A1|B1: un perfil propi per nivell (test-en-a1, test-en-b1), creat la
# primera vegada; el nom només es canvia si no has triat tu el perfil.
if [[ -n "$LEVEL" && "$PROFILE" == "test-en" ]]; then
  PROFILE="test-en-$(echo "$LEVEL" | tr 'A-Z' 'a-z')"
fi

# Un perfil de proves i prou: la bateria sembra el perfil i el torna al punt de
# partida entre execucions.
case "$PROFILE" in
  test*|demo*|e2e*) ;;
  *) echo "❌ la bateria només corre en perfils de proves, no en $PROFILE" >&2; exit 2 ;;
esac

if [[ $QUICK -eq 1 ]]; then
  SETTINGS=(--setting "base:")
else
  # La línia base primer, sempre: sense ella els altres números no volen dir res.
  # Després, les tres hipòtesis per separat, perquè es pugui veure què fa cada
  # una — temperatura sola, penalització sola, i les dues juntes.
  SETTINGS=(
    --setting "base:"
    --setting "temp06:temperature=0.6"
    --setting "penal:temperature=0.2,presence_penalty=0.4,frequency_penalty=0.3,repeat_last_n=512"
    --setting "totes:temperature=0.6,presence_penalty=0.4,frequency_penalty=0.3,repeat_last_n=512"
  )
fi

# ---- 1. El perfil de proves i 2. el model deep ------------------------------
# Compartit amb flowed-testbase.sh (scripts/lib-testbed.sh): un sol lloc.
# shellcheck source=scripts/lib-testbed.sh
source scripts/lib-testbed.sh
tb_ensure_profile "$PROFILE" "$PORT" "${LEVEL:-A2}" || exit $?

cleanup() {
  if [[ $TB_STARTED_MODEL -eq 1 && $KEEP_MODEL -eq 0 ]]; then
    echo
    echo "aturo el model que havia aixecat el bench (flowed-stop.sh --models-only)"
    scripts/flowed-stop.sh --models-only || true
  fi
}
trap cleanup EXIT

if [[ $NO_START -eq 1 ]]; then
  tb_ensure_model --no-start || exit $?
else
  tb_ensure_model || exit $?
fi

echo "perfil $PROFILE · port $PORT · $REPEAT execucions per configuració"
echo "escenaris: ${SCENARIOS[*]}"
echo

# Sense `exec`: el trap d'aturada ha de poder córrer en acabar.
rc=0
python3 scripts/flowed-sweep.py "$PROFILE" \
  --port "$PORT" --repeat "$REPEAT" ${DUE:+--due "$DUE"} ${SPAN:+--span "$SPAN"} ${TEST_MODE:+--test-mode "$TEST_MODE"} ${STOP_BEFORE_TEST:+--stop-before-test} \
  "${SCENARIOS[@]}" "${SETTINGS[@]}" || rc=$?
exit "$rc"
