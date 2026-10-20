# Minimal demo-admin API client for driving backend scenarios during the VVD test.
# usage: DONE_CREDENTIALS_FILE=/path/with/demo-admin-line python3 api.py <METHOD> <path> [json-body]
# The password is read from a local, uncommitted file ("demo-admin: <password>") and never printed.
import json, os, re, sys, uuid, urllib.error, urllib.request

BASE = os.environ.get("DONE_BASE", "https://100-49-183-59.sslip.io")
TOK = os.path.expanduser("~/.done_irl_demo_admin_token")  # session cache outside the repo


def creds():
    for line in open(os.environ["DONE_CREDENTIALS_FILE"], encoding="utf-8"):
        m = re.match(r"\s*demo-admin\s*:\s*(\S+)", line)
        if m:
            return m.group(1)
    sys.exit("no demo-admin line in DONE_CREDENTIALS_FILE")


def req(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    if method == "POST":
        h["Idempotency-Key"] = uuid.uuid4().hex
    data = json.dumps(body).encode() if body is not None else (b"{}" if method == "POST" else None)
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def login():
    st, b, hd = req("POST", "/api/auth/login", {"username": "demo-admin", "password": creds()})
    m = re.search(r"done_session=([^;]+)", hd.get("set-cookie", "") or "")
    if not m:
        sys.exit("login failed %s" % st)
    with open(TOK, "w") as f:
        f.write(m.group(1))
    os.chmod(TOK, 0o600)
    return m.group(1)


tok = open(TOK).read().strip() if os.path.exists(TOK) else login()
method, path = sys.argv[1], sys.argv[2]
body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
st, b, _ = req(method, path, body, tok)
if st == 401:
    tok = login()
    st, b, _ = req(method, path, body, tok)
out = os.environ.get("OUT")
if out:
    open(out, "wb").write(b)
print(st, ("saved %d bytes" % len(b)) if out else b[:400].decode("utf-8", "replace"))
