#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-paths.sh"   # FLOWED_HOME_DIR: where the profiles live
# Flowed text-to-speech setup — installs piper and one voice, then wires it into
# config/fluent.json so the 🔊 buttons appear in the web.
#
# Why a script and not an automatic download: the server must never fetch
# anything at runtime, and the machines that run Flowed are not always online.
# This is a deliberate, one-off, admin step.
#
# Usage:
#   scripts/flowed-tts.sh install en_GB-alba-medium   # binary + voice + config
#   scripts/flowed-tts.sh voice   de_DE-thorsten-low  # one more voice
#   scripts/flowed-tts.sh status                      # what is installed
#   scripts/flowed-tts.sh say "Good morning"          # try it from the terminal
#
# Voices: https://huggingface.co/rhasspy/piper-voices  (browse, then pass the
# name — e.g. en_US-lessac-medium, ca_ES-upc_ona-medium).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
TTS_DIR="${FLOWED_TTS_DIR:-$FLOWED_HOME_DIR/_tts}"
BIN="$TTS_DIR/piper/piper"
CONFIG="$ROOT/config/fluent.json"
PIPER_VERSION="${PIPER_VERSION:-2023.11.14-2}"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz"
VOICE_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"

die() { echo "error: $*" >&2; exit 1; }

# piper ships its own libespeak-ng and libonnxruntime next to the binary, so the
# loader has to be pointed at them. Doing it here (and in server/src/tts.ts)
# rather than in ~/.bashrc keeps it working when the server is started by
# something that never reads a shell profile — systemd, cron, another machine.
piper_env() {
  local dir; dir="$(dirname "$BIN")"
  LD_LIBRARY_PATH="$dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  ESPEAK_DATA_PATH="${ESPEAK_DATA_PATH:-$dir/espeak-ng-data}" \
  "$@"
}

# en_GB-alba-medium -> en/en_GB/alba/medium
voice_path() {
  local name="$1" lang_full quality speaker
  [[ "$name" =~ ^([a-z]{2})_([A-Z]{2})-([A-Za-z0-9_]+)-([a-z_]+)$ ]] \
    || die "voice name must look like en_GB-alba-medium (got '$name')"
  lang_full="${BASH_REMATCH[1]}_${BASH_REMATCH[2]}"
  speaker="${BASH_REMATCH[3]}"
  quality="${BASH_REMATCH[4]}"
  echo "${BASH_REMATCH[1]}/${lang_full}/${speaker}/${quality}"
}

# en_GB-alba-medium -> English   (what learner-profile.json calls it)
voice_language() {
  case "${1%%_*}" in
    en) echo "English" ;;  de) echo "German" ;;   fr) echo "French" ;;
    es) echo "Spanish" ;;  ca) echo "Catalan" ;;  it) echo "Italian" ;;
    pt) echo "Portuguese" ;; nl) echo "Dutch" ;;  *) echo "" ;;
  esac
}

fetch() {
  local url="$1" out="$2"
  echo "  ↓ $(basename "$out")"
  curl -fSL --retry 3 -o "$out" "$url" || die "download failed: $url"
}

install_binary() {
  if [[ -x "$BIN" ]]; then echo "piper already at $BIN"; return; fi
  mkdir -p "$TTS_DIR"
  echo "Installing piper $PIPER_VERSION into $TTS_DIR"
  fetch "$PIPER_URL" "$TTS_DIR/piper.tar.gz"
  tar -xzf "$TTS_DIR/piper.tar.gz" -C "$TTS_DIR"
  rm -f "$TTS_DIR/piper.tar.gz"
  [[ -x "$BIN" ]] || die "piper binary not where expected: $BIN"
  echo "piper installed."
}

install_voice() {
  local name="$1" rel onnx
  rel="$(voice_path "$name")"
  onnx="$TTS_DIR/voices/${name}.onnx"
  mkdir -p "$TTS_DIR/voices"
  if [[ -f "$onnx" && -f "${onnx}.json" ]]; then
    echo "voice $name already installed"
  else
    echo "Installing voice $name"
    fetch "${VOICE_BASE}/${rel}/${name}.onnx" "$onnx"
    fetch "${VOICE_BASE}/${rel}/${name}.onnx.json" "${onnx}.json"
  fi
  wire_config "$name" "$onnx"
}

wire_config() {
  local name="$1" onnx="$2" language
  language="$(voice_language "$name")"
  [[ -n "$language" ]] || die "I do not know which language '$name' is — the server will not offer it."
  # No paths go into config/fluent.json: it travels between machines and piper
  # does not. The server finds $TTS_DIR on its own; the config only says "on".
  python3 - "$CONFIG" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
data = json.loads(p.read_text())
tts = data.setdefault("tts", {})
changed = tts.get("enabled") is not True or "binary" in tts or "voices" in tts
tts["enabled"] = True
tts.pop("binary", None)
tts.pop("voices", None)
if changed:
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print("config/fluent.json: tts on (paths are found on disk)")
PY
  echo "$language -> $onnx"
  echo "Restart the web instance for it to pick this up."
}

status() {
  echo "tts dir : $TTS_DIR"
  echo "binary  : $([[ -x "$BIN" ]] && echo "$BIN ✅" || echo 'not installed ❌')"
  if [[ -x "$BIN" ]]; then
    if piper_env "$BIN" --help >/dev/null 2>&1; then
      echo "          (corre sense dependre del teu .bashrc ✅)"
    else
      echo "          ⚠ el binari no arrenca amb les seves pròpies llibreries;"
      echo "            mira-ho amb: piper_env ldd $BIN | grep 'not found'"
    fi
  fi
  echo "voices  :"
  ls -1 "$TTS_DIR/voices/"*.onnx 2>/dev/null | sed 's/^/  /' || echo "  (none)"
  echo "config  : tts.enabled = $(python3 -c "import json;print(json.load(open('$CONFIG')).get('tts',{}).get('enabled'))" 2>/dev/null || echo '?')"
}

case "${1:-}" in
  install)
    [[ -n "${2:-}" ]] || die "usage: scripts/flowed-tts.sh install <voice>  (e.g. en_GB-alba-medium)"
    install_binary
    install_voice "$2"
    ;;
  voice)
    [[ -n "${2:-}" ]] || die "usage: scripts/flowed-tts.sh voice <voice>"
    [[ -x "$BIN" ]] || die "piper is not installed yet — run 'install' first"
    install_voice "$2"
    ;;
  say)
    [[ -n "${2:-}" ]] || die "usage: scripts/flowed-tts.sh say \"text\""
    [[ -x "$BIN" ]] || die "piper is not installed yet"
    voice="$(ls -1 "$TTS_DIR/voices/"*.onnx 2>/dev/null | head -1)"
    [[ -n "$voice" ]] || die "no voice installed"
    out="$(mktemp --suffix=.wav)"
    printf '%s\n' "$2" | piper_env "$BIN" --model "$voice" --output_file "$out"
    echo "wrote $out  (play it with: aplay '$out')"
    ;;
  status|"") status ;;
  *) die "unknown command '$1' (install | voice | say | status)" ;;
esac
