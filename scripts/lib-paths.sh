# shellcheck shell=bash
# Where the learners' profiles live — the shell twin of hooks/main_paths.py
# (profiles_root). Same rule, so both always agree:
#   1. $FLOWED_HOME, when set;
#   2. ~/.flowed, when it exists — or when neither folder exists yet;
#   3. ~/.fluent, while the old folder has not been moved.
# Sourced by the scripts; sets FLOWED_HOME_DIR.
flowed_home() {
  if [[ -n "${FLOWED_HOME:-}" ]]; then
    echo "${FLOWED_HOME/#\~/$HOME}"
  elif [[ -d "$HOME/.flowed" || ! -d "$HOME/.fluent" ]]; then
    echo "$HOME/.flowed"
  else
    echo "$HOME/.fluent"
  fi
}
# Load <root>/.env without overriding what the environment already sets
# (CLI/env > .env > config/fluent.json). One loader for every script: it used to
# be copied in four places.
#
# Names from before 0.5.0 (FLUENT_*) are read as their FLOWED_* twin, with a
# warning. Without this, an .env that was not converted is ignored in silence,
# and every value falls back to config/fluent.json — which describes railab
# (native backend, port 12322): on llvm the start then tried to bring the model
# up the railab way (2026-09-26).
# Sets FLOWED_ENV_FILE to the file loaded ("" when there is none).
flowed_load_env() {
  local file="$1/.env" _line _k _v _e _old=""
  FLOWED_ENV_FILE=""
  if [[ -f "$file" ]]; then
    FLOWED_ENV_FILE="$file"
    while IFS= read -r _line || [[ -n "$_line" ]]; do
      _line="${_line%%#*}"
      [[ "$_line" =~ ^[[:space:]]*$ ]] && continue
      [[ "$_line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
      _k="${BASH_REMATCH[1]}"; _v="${BASH_REMATCH[2]}"
      _v="${_v%\"}"; _v="${_v#\"}"; _v="${_v%\'}"; _v="${_v#\'}"
      if [[ "$_k" == FLUENT_* ]]; then _old+=" $_k"; _k="FLOWED_${_k#FLUENT_}"; fi
      if [[ -z "${!_k+x}" ]]; then export "$_k=$_v"; fi
    done < "$file"
  fi
  for _e in $(compgen -e | grep '^FLUENT_' || true); do
    _k="FLOWED_${_e#FLUENT_}"; _old+=" $_e"
    if [[ -z "${!_k+x}" ]]; then export "$_k=${!_e}"; fi
  done
  if [[ -n "$_old" && -z "${FLOWED_OLD_NAMES_WARNED:-}" ]]; then
    echo "avís: noms d'abans de la 0.5.0 (${_old# }) — es llegeixen com FLOWED_*." >&2
    if [[ -n "$FLOWED_ENV_FILE" ]]; then
      echo "      Per treure l'avís: sed -i 's/\\bFLUENT_/FLOWED_/g' $FLOWED_ENV_FILE" >&2
    else
      echo "      Per treure l'avís: canvia els export FLUENT_* de l'entorn per FLOWED_*" >&2
    fi
    export FLOWED_OLD_NAMES_WARNED=1
  fi
  export FLOWED_ENV_FILE
}

# Resolve the home AFTER loading <root>/.env. Before this, FLOWED_HOME_DIR was
# computed at source time — before any script called flowed_load_env — so a
# FLOWED_HOME set in .env was silently ignored (new-user.sh provisioned into
# ~/.flowed even with FLOWED_HOME pointing elsewhere). Scripts that call
# flowed_load_env again later are unaffected: it never overrides what the
# environment already sets.
flowed_load_env "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FLOWED_HOME_DIR="$(flowed_home)"
export FLOWED_HOME_DIR
