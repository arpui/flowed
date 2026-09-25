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
FLOWED_HOME_DIR="$(flowed_home)"
export FLOWED_HOME_DIR
