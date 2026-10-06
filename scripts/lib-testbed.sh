source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-paths.sh"   # FLOWED_HOME_DIR: where the profiles live
# Peces compartides pel banc (flowed-bench.sh) i el banc manual (flowed-testbase.sh).
# Un sol lloc per "deixar a punt el perfil de proves i el model": si es canvia
# aquí, els dos ho fan igual. Es fa `source` des de l'arrel del repositori.
#
#   tb_ensure_profile PERFIL PORT [NIVELL]   crea i configura el perfil NOMÉS si no existeix
#                                   (NIVELL: A1|A2|B1|B2, per defecte A2; l'objectiu és el següent)
#   tb_model_port                   port del model deep (config/fluent.json < .env < entorn)
#   tb_model_up                     el model respon?
#   tb_ensure_model [--no-start]    si no respon, l'aixeca; TB_STARTED_MODEL=1 si l'ha aixecat ell
#                                   (retorna 3 si no hi és i no es pot/vol aixecar)

TB_STARTED_MODEL=0

tb_ensure_profile() {
  local profile="$1" port="$2" level="${3:-A2}" goal pdir="$FLOWED_HOME_DIR/$1"
  case "$level" in
    A1) goal=A2 ;; A2) goal=B1 ;; B1) goal=B2 ;; B2) goal=C1 ;;
    *) echo "❌ nivell desconegut: $level (A1, A2, B1 o B2)" >&2; return 2 ;;
  esac
  # Només si NO existeix: un perfil que ja hi és és seu i no es reescriu.
  if [[ ! -d "$pdir" ]]; then
    echo "perfil $profile: no existeix, el creo i el configuro"
    scripts/new-user.sh "$profile" --port "$port" >/dev/null
    python3 scripts/flowed-profile.py "$profile" --name Test --native Catalan \
      --target English --level "$level" --goal "$goal" --minutes 20 >/dev/null
  fi
}

tb_model_port() {
  python3 scripts/flowed-config.py --json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["FLOWED_DEEP_PORT"])'
}

tb_model_up() {
  # A remote or externally-managed model (FLOWED_DEEP_MANAGED=0, or a
  # FLOWED_DEEP_BASE_URL that is not the local llama): probe the endpoint the
  # app itself will use, and never start anything — the machine that hosts it
  # is not this one. (WP1.9: this fork's tutor runs against a remote llama;
  # the bench must never wake the local one.)
  local base="${FLOWED_DEEP_BASE_URL:-}"
  if [[ "${FLOWED_DEEP_MANAGED:-1}" == "0" || ( -n "$base" && "$base" != http://127.0.0.1:* && "$base" != http://localhost:* ) ]]; then
    [[ -n "$base" ]] || return 1
    curl -fsS -m 5 "${base%/}/models" >/dev/null 2>&1
    return $?
  fi
  curl -fsS -m 3 "http://127.0.0.1:$(tb_model_port)/health" >/dev/null 2>&1
}

tb_ensure_model() {
  local no_start=0 port
  [[ "${1:-}" == "--no-start" ]] && no_start=1
  port="$(tb_model_port)"
  if tb_model_up; then
    echo "model deep: ja corre, no el toco"
    return 0
  fi
  if [[ "${FLOWED_DEEP_MANAGED:-1}" == "0" ]]; then
    echo "❌ el model deep no respon (${FLOWED_DEEP_BASE_URL:-sense FLOWED_DEEP_BASE_URL}) —" \
         "és extern (FLOWED_DEEP_MANAGED=0) i no l'aixeco: no és d'aquesta màquina" >&2
    return 3
  fi
  if [[ $no_start -eq 1 ]]; then
    echo "❌ el model deep no respon a :$port i has demanat --no-start" >&2
    return 3
  fi
  echo "model deep :$port: no corre, l'aixeco (flowed-start.sh --models-only)"
  TB_STARTED_MODEL=1
  scripts/flowed-start.sh --models-only --yes
  # flowed-start ja espera el /health, però un model de 14B pot trigar; 5 min de marge.
  for _ in $(seq 1 100); do
    tb_model_up && return 0
    sleep 3
  done
  echo "❌ el model deep no respon a :$port després de 5 minuts" >&2
  return 3
}
