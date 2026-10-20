# Types text on the DONE/IRL on-screen D-pad keyboard using only official inputd-cli
# D-pad presses (KEY_UP/DOWN/LEFT/RIGHT/ENTER) on the Vega Virtual Device.
# Assumes the keyboard was just opened (focus on '1', row 0 col 0).
# usage: python3 tvtype.py --text STR | --password  (reads the demo-admin line from
#        $DONE_CREDENTIALS_FILE; never printed). Use CHUNK=1: one vda call per key (~1.7 s/key).
#        Batched modes (CHUNK=0/N) dropped or misplaced presses on the VVD in testing.
# ALWAYS screenshot first to confirm the Password keyboard (not Username) is open: typing a
# password into a non-secure field would display it on screen.
import sys, subprocess, re, os
VDA = os.environ.get("VDA", os.path.expanduser("~/vega/sdk/vega-sdk/main/0.24.12112/bin/tools/vda"))
GRID = ["1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm_./",
        [":", "@", "SHIFT", "SPACE", "DEL", "CLEAR", "+", "!", "#", "DONE"]]
CHUNK = int(os.environ.get("CHUNK", "0"))
GAP = os.environ.get("GAP", "0.5")
ENTER_GAP = os.environ.get("ENTER_GAP", "1.3")
def press(keys):
    if CHUNK == 0:
        # inputd-cli console mode fed from an on-device pipe, with a short gap per key.
        for i in range(0, len(keys), 60):
            body = "; ".join("echo 'button_press %s'; sleep %s" % (k, ENTER_GAP if k == "KEY_ENTER" else GAP) for k in keys[i:i+60])
            subprocess.run([VDA, "shell", "{ %s; echo exit; } | inputd-cli start" % body], stdout=subprocess.DEVNULL, check=True)
        return
    for i in range(0, len(keys), CHUNK):
        chunk = ",".join("button_press " + k for k in keys[i:i+CHUNK])
        subprocess.run([VDA, "shell", 'inputd-cli series "%s"' % chunk], stdout=subprocess.DEVNULL, check=True)
def find(name):
    for r, row in enumerate(GRID):
        if name in row: return r, list(row).index(name)
    raise SystemExit("unsupported character")
pos = [0, 0]; shift = False; seq = []
def hit(name):
    r, c = find(name)
    dr, dc = r - pos[0], c - pos[1]
    seq.extend(["KEY_DOWN" if dr > 0 else "KEY_UP"] * abs(dr))
    seq.extend(["KEY_RIGHT" if dc > 0 else "KEY_LEFT"] * abs(dc))
    seq.append("KEY_ENTER"); pos[:] = [r, c]
args = sys.argv[1:]; text = ""
if "--password" in args:
    for line in open(os.environ["DONE_CREDENTIALS_FILE"], encoding="utf-8"):
        m = re.match(r"\s*demo-admin\s*:\s*(\S+)", line)
        if m: text = m.group(1)
if "--text" in args: text = args[args.index("--text") + 1]
def anchor():
    # Edges clamp, so this deterministically lands on '1' (row 0, col 0).
    seq.extend(["KEY_UP"] * 5 + ["KEY_LEFT"] * 10); pos[:] = [0, 0]
anchor()
hit("CLEAR")
for ch in text:
    if ch.isalpha() and ch.isupper() != shift:
        hit("SHIFT"); shift = not shift
        seq.extend(["KEY_DOWN"] * 1 + ["KEY_LEFT"] * 3); pos[:] = [4, 0]  # re-anchor at ':' after relabel
    hit(ch.lower() if ch.isalpha() else ch)
if shift: hit("SHIFT")
if "--no-done" not in args: hit("DONE")
press(seq)
print("sent %d D-pad presses for %d characters (text not echoed)" % (len(seq), len(text)))
