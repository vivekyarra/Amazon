# usage: python3 console.py "cmd1" "cmd2" ... -- Android-emulator console (port 5554) used by the VVD
import socket, sys, os, time
tokf = os.path.expanduser("~/.emulator_console_auth_token")
s = socket.create_connection(("127.0.0.1", 5554), timeout=20)
def rd(t=1.5):
    s.settimeout(t); buf = b""
    try:
        while True:
            d = s.recv(65536)
            if not d: break
            buf += d
    except socket.timeout: pass
    return buf.decode("utf-8", "replace")
print(rd())
if os.path.exists(tokf):
    s.sendall(b"auth " + open(tokf).read().strip().encode() + b"\n"); print(rd())
for c in sys.argv[1:]:
    s.sendall(c.encode() + b"\n"); print(">>", c); print(rd(float(os.environ.get("WAIT", "3"))))
s.sendall(b"quit\n")
