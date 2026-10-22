#!/usr/bin/env bash
# Vega Virtual Device driver used for the recorded test session.
#   D-pad keys: the official inputd-cli on the VVD, through the SDK's vda tool.
#   Screenshots: the VVD's bundled emulator console (port 5554), command "screenrecord screenshot".
# usage: tv.sh key KEY_DOWN [count] | tv.sh shot <name>
source ~/vega/env
VDA=${VDA:-$HOME/vega/sdk/vega-sdk/main/0.24.12112/bin/tools/vda}
EV=${EVIDENCE_DIR:-$(cd "$(dirname "$0")/../../.." && pwd)/artifacts/vega}
mkdir -p "$EV" /tmp/vshots
case "$1" in
  key) n=${3:-1}; for i in $(seq 1 "$n"); do "$VDA" shell "inputd-cli button_press $2" >/dev/null; sleep 0.4; done; echo "key $2 x$n";;
  shot) rm -f /tmp/vshots/*.png
        python3 "$(dirname "$0")/console.py" "screenrecord screenshot /tmp/vshots" >/dev/null; sleep 1
        f=$(ls -t /tmp/vshots/*.png | head -1)
        convert "$f" -resize 1280x720 -quality 85 "$EV/$2.jpg"; rm -f "$f"; echo "shot $EV/$2.jpg";;
  *) echo "usage: $0 key KEY_X [n] | shot NAME"; exit 2;;
esac
