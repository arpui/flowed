#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-paths.sh"   # FLOWED_HOME_DIR: where the profiles live
# Flowed friend-mode toggle — per-profile tutor_style flag, no code involved.
#
#   scripts/flowed-friend.sh <profile-id> [on|off|status]
#
#   on     -> preferences.tutor_style = "friend" (warmer tutor: last-session
#             callbacks, learner interests in examples)
#   off    -> removes the key (profile back to byte-original default classic)
#   status -> shows current mode + interests (default when no 2nd arg)
#
# Portable: pure bash + python3, works here and on the 4060 box.
# Atomic write (tmp+rename) so an interrupt never corrupts the profile.
set -euo pipefail

ID="${1:-}"
ACTION="${2:-status}"

if [[ -z "$ID" ]]; then
  echo "ús: $0 <profile-id> [on|off|status]"
  exit 2
fi
if [[ ! "$ACTION" =~ ^(on|off|status)$ ]]; then
  echo "ús: $0 <profile-id> [on|off|status]"
  exit 2
fi

PROFILE="$FLOWED_HOME_DIR/$ID/learner-profile.json"
if [[ ! -f "$PROFILE" ]]; then
  echo "error: perfil inexistent: $PROFILE"
  exit 1
fi

export FLOWED_FRIEND_PROFILE="$PROFILE" FLOWED_FRIEND_ACTION="$ACTION"
python3 - <<'EOF'
import json, os, tempfile

path = os.environ["FLOWED_FRIEND_PROFILE"]
action = os.environ["FLOWED_FRIEND_ACTION"]

try:
    with open(path, "rb") as f:
        raw = f.read()
    d = json.loads(raw.decode("utf-8"))
except (OSError, ValueError) as e:
    print(f"error: no es pot llegir el perfil: {e}")
    raise SystemExit(1)

had_newline = raw.endswith(b"\n")


def save(data):
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if had_newline:
        text += "\n"
    tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(path),
                                      delete=False, encoding="utf-8",
                                      newline="")
    try:
        tmp.write(text)
        tmp.close()
        os.replace(tmp.name, path)
    except BaseException:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise

prefs = d.setdefault("preferences", {})
mode = prefs.get("tutor_style", "classic")
learner = d.get("learner", {})
name = learner.get("name", "?")

if action == "status":
    print(f"{name}: tutor_style={mode}  interests={learner.get('interests', [])}")
elif action == "on":
    if mode == "friend":
        print(f"{name}: ja estava en friend")
    else:
        prefs["tutor_style"] = "friend"
        save(d)
        print(f"{name}: friend ACTIVAT")
elif action == "off":
    if "tutor_style" not in prefs:
        print(f"{name}: ja estava en classic (sense flag)")
    else:
        del prefs["tutor_style"]
        save(d)
        print(f"{name}: friend DESACTIVAT (clàssic)")
EOF
