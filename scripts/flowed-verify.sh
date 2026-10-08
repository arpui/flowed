#!/usr/bin/env bash
# Verificació d'una versió del core abans de producció — UNA comanda, un informe.
#
#   scripts/flowed-verify.sh                 # suites + e2e en directe (language + algebra)
#   TUTORBENCH=1 scripts/flowed-verify.sh    # + tutor bench de les pràctiques obertes (lent)
#
# Escriu results/verify-<data>/summary.md (+ un .log per pas) per analitzar-lo
# després (skill flowed-verify). No puja cap model: fa servir el remot.
#
# Seguretat: tot va a ~/.flowed però només amb perfils de prova (test*/demo*/e2e*);
# mai el llegat (~/.fluent).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export FLOWED_HOME="${FLOWED_HOME:-$HOME/.flowed}"
export FLOWED_DEEP_BASE_URL="${FLOWED_DEEP_BASE_URL:-http://192.168.31.102:12321/v1}"
export FLOWED_DEEP_MANAGED=0
LANG_PROFILE="${LANG_PROFILE:-test-lang}"; LANG_PORT="${LANG_PORT:-4205}"
MATH_PROFILE="${MATH_PROFILE:-test-m7}";   MATH_PORT="${MATH_PORT:-4201}"
BUN="$(command -v bun || echo "$HOME/.bun/bin/bun")"

home_real="$(readlink -f "$FLOWED_HOME")"
for forbidden in "$HOME/.fluent"; do
  if [[ "$home_real" == "$(readlink -f "$forbidden")" ]]; then
    echo "error: FLOWED_HOME=$FLOWED_HOME és el home llegat — fes servir ~/.flowed (només perfils test*/demo*/e2e*)" >&2
    exit 2
  fi
done
for p in "$LANG_PROFILE" "$MATH_PROFILE"; do
  [[ "$p" =~ ^(test|demo|e2e) ]] || { echo "error: $p no és un perfil de prova" >&2; exit 2; }
  [[ -f "$FLOWED_HOME/$p/learner-profile.json" ]] || { echo "error: falta $FLOWED_HOME/$p (scripts/new-user.sh)" >&2; exit 2; }
done

OUT="results/verify-$(date +%Y%m%d-%H%M)"
mkdir -p "$OUT"
SUM="$OUT/summary.md"
FAILED=()
{
  echo "# Verificació — $(date '+%Y-%m-%d %H:%M')"
  echo
  echo "- versió: $(grep -o 'VERSION = "[^"]*"' server/src/index.ts | cut -d'"' -f2) · commit $(git rev-parse --short HEAD 2>/dev/null) · branca $(git branch --show-current 2>/dev/null)"
  echo "- canvis sense commit: $(git status --short 2>/dev/null | wc -l)"
  echo "- FLOWED_HOME: $FLOWED_HOME · model: $FLOWED_DEEP_BASE_URL"
  echo "- perfils: $LANG_PROFILE:$LANG_PORT (language) · $MATH_PROFILE:$MATH_PORT (math)"
  echo
  echo "| pas | resultat | temps |"
  echo "|---|---|---|"
} > "$SUM"

run() {  # run <name> <cmd…>  → <name>.log, una fila a la taula
  local name="$1"; shift
  local t0=$SECONDS rc
  "$@" > "$OUT/$name.log" 2>&1; rc=$?
  printf '| %s | %s | %ss |\n' "$name" "$([[ $rc == 0 ]] && echo OK || echo "**FALLA** (rc $rc)")" "$((SECONDS - t0))" >> "$SUM"
  [[ $rc == 0 ]] || FAILED+=("$name")
  return $rc
}

ts_harnesses() {
  local bad=0
  for t in server/test/*.test.ts; do
    echo "== $t"
    (cd server && "$BUN" "test/$(basename "$t")") || { echo "!! FALLA $t"; bad=1; }
  done
  return $bad
}

live() {  # live <profile> <port> <scenario>
  local profile="$1" port="$2" scenario="$3"
  scripts/flowed-web.sh --stop --port "$port" > /dev/null 2>&1 || true
  run "web-$profile" scripts/flowed-web.sh --app "$profile" --port "$port" || return 1
  run "e2e-$scenario" python3 scripts/flowed-e2e.py "$profile" --port "$port" --scenario "$scenario" \
      --transcript "$OUT/e2e-$scenario.md"
  if [[ -n "${TUTORBENCH:-}" ]]; then
    # The bench picks the profile's domain (fluent-* or math-* practices).
    run "tutorbench-$scenario" python3 scripts/flowed-tutorbench.py run --port "$port" \
        --name "verify-$scenario-$(date +%Y%m%d)" --host "$(hostname)" "$profile"
  fi
  scripts/flowed-web.sh --stop --port "$port" > /dev/null 2>&1 || true
}

run model-health curl -sf -m 10 "${FLOWED_DEEP_BASE_URL%/v1}/health"
run unittest python3 -m unittest discover -s tests
run ts-harnesses ts_harnesses
run tsc bash -c "cd server && '$BUN' x tsc --noEmit"
live "$LANG_PROFILE" "$LANG_PORT" language
live "$MATH_PROFILE" "$MATH_PORT" algebra

{
  echo
  if (( ${#FAILED[@]} == 0 )); then
    echo "**Resultat: tot OK.**"
  else
    echo "**Resultat: falla ${FAILED[*]}.**"
    for n in "${FAILED[@]}"; do
      echo; echo "## $n (últimes 30 línies)"; echo; echo '```'; tail -30 "$OUT/$n.log"; echo '```'
    done
  fi
} >> "$SUM"
cat "$SUM"
echo; echo "→ $ROOT/$OUT"
(( ${#FAILED[@]} == 0 ))
