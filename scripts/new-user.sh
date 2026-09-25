#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-paths.sh"   # FLOWED_HOME_DIR: where the profiles live
# Flowed new-user bootstrap — provisions a fresh learner profile under ~/.flowed/<id>/.
#
# Usage:
#   scripts/new-user.sh <id> [--port N]
#
#   <id>   : safe profile id (lowercase letters, digits, hyphens), e.g. test-en
#   --port : web port for the launch command hint (default 4100)
#
# What it does:
#   1. Validates <id> (no paths/spaces/uppercase — must be a safe dir name).
#   2. Refuses to overwrite an existing profile dir.
#   3. Creates ~/.flowed/<id>/ and seeds the 6 JSON DBs from data-examples/ so
#      that scripts/flowed-web.sh --app <id> will accept the profile.
#   4. Generates a per-profile web password (.web-password, mode 600).
#   5. Prints how to launch and finish the FIRST real setup (the /fluent-setup
#      interview inside the web instance fills learner-profile.json properly).
#
# This is the "script, no admin web" path: provisioning is a deterministic copy,
# and the learner's actual identity/level is captured live by /fluent-setup.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE_DIR="$ROOT/data-examples"

PORT=4100
ID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="${2:-}"; shift ;;
    -*) echo "error: unknown option $1"; exit 2 ;;
    *) ID="$1" ;;
  esac
  shift
done

if [[ -z "$ID" ]]; then
  echo "usage: scripts/new-user.sh <id> [--port N]"
  exit 2
fi

# 1) Validate the id — safe directory name.
if ! [[ "$ID" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "error: id '$ID' must be lowercase letters/digits/hyphens, no spaces or paths"
  exit 2
fi

DATA_DIR="$FLOWED_HOME_DIR/$ID"

# 2) Never overwrite an existing profile.
if [[ -d "$DATA_DIR" ]]; then
  echo "error: profile directory already exists: $DATA_DIR"
  echo "       refusing to overwrite. If this is a reset, do it via /fluent-setup."
  exit 1
fi

# 3) Seed the 6 DBs from the examples.
mkdir -p "$DATA_DIR" "$DATA_DIR/sessions"
for tpl in learner-profile mastery-db mistakes-db progress-db session-log spaced-repetition; do
  cp "$TEMPLATE_DIR/$tpl-template.json" "$DATA_DIR/$tpl.json"
done
# Mark the profile as "pending setup" so the web knows to auto-start /fluent-setup
# on first open. /fluent-setup flips it to true after the initial interview.
python3 -c "
import json
p = '$DATA_DIR/learner-profile.json'
d = json.load(open(p))
d.setdefault('preferences', {})['setup_complete'] = False
json.dump(d, open(p, 'w'), indent=2, ensure_ascii=False)
"

# 4) Per-profile web password (same scheme as flowed-web.sh).
PWFILE="$DATA_DIR/.web-password"
PASS="$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | cut -c1-16)"
(umask 077 && printf '%s\n' "$PASS" > "$PWFILE")

echo
echo "✅ New Flowed profile created: $DATA_DIR"
echo "   Password: $PASS   (also saved in $PWFILE)"
echo
echo "   Seeded 6 DBs from data-examples/. learner-profile.json is a TEMPLATE"
echo "   placeholder — the learner completes their real identity/level on first"
echo "   login via the /fluent-setup interview inside the web app."
echo
echo "Launch it:"
echo "   scripts/flowed-web.sh --app $ID --port $PORT"
echo
echo "Then open http://localhost:$PORT and the learner runs /fluent-setup first."
