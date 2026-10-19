import sys, os, subprocess, json, urllib.request, time, socket, base64, struct
D = "/homeassistant/pv_tmp"
if len(sys.argv) < 2:
    subprocess.Popen([sys.executable, __file__, "kind"], start_new_session=True,
                     stdout=open(D + "/out.txt", "w"), stderr=subprocess.STDOUT)
    print("gestart")
    sys.exit()
sys.path.insert(0, D)
import prijsverwachting as P
t0 = time.time()

TOKEN = os.environ.get("SUPERVISOR_TOKEN")
if not TOKEN:
    sys.exit()

s = socket.create_connection(("supervisor", 80), timeout=5)
key = base64.b64encode(os.urandom(16)).decode()
s.sendall((f"GET /core/websocket HTTP/1.1\r\nHost: supervisor\r\nUpgrade: websocket\r\n"
           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
           f"Authorization: Bearer {TOKEN}\r\n\r\n").encode())
s.settimeout(60)
hdr = b""
while b"\r\n\r\n" not in hdr:
    hdr += s.recv(1)

buf = b""
def recv_exact(n):
    global buf
    while len(buf) < n:
        d = s.recv(65536)
        if not d:
            raise EOFError
        buf += d
    out, buf = buf[:n], buf[n:]
    return out

def recv():
    b1, b2 = recv_exact(2)
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack(">H", recv_exact(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", recv_exact(8))[0]
    data = recv_exact(n)
    if b1 & 0x0F == 1:
        return json.loads(data)
    return None

def send(obj):
    data = json.dumps(obj).encode()
    m = os.urandom(4)
    n = len(data)
    h = bytes([0x81])
    if n < 126:
        h += bytes([0x80 | n])
    elif n < 65536:
        h += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        h += bytes([0x80 | 127]) + struct.pack(">Q", n)
    s.sendall(h + m + bytes(b ^ m[i % 4] for i, b in enumerate(data)))

recv(); send({"type": "auth", "access_token": TOKEN}); recv()
import datetime as _dt
start = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=120)).isoformat()
send({"id": 1, "type": "recorder/statistics_during_period", "start_time": start, "statistic_ids": ["sensor.zonneplan_current_hourly_electricity_tariff"], "period": "hour", "types": ["mean"]})
while True:
    r = recv()
    if r and r.get("id") == 1:
        break
rijen = r["result"]["sensor.zonneplan_current_hourly_electricity_tariff"]
prijzen = P.prijzen_uit_statistiek(rijen)
print("uren prijs", len(prijzen), min(prijzen), max(prijzen), flush=True)
weer = P.weer_uit_open_meteo(json.load(urllib.request.urlopen(P.open_meteo_url(), timeout=20)))
print("uren weer", len(weer), flush=True)
for vooruit in (1, 2):
    print("vooruit", vooruit, P.backtest(prijzen, weer, dagen=28, vooruit=vooruit), flush=True)
rijen, doelen = P.dataset(prijzen, weer)
coefs = P.fit(rijen, doelen)
print("coefs", [round(x, 3) for x in coefs[:7]], flush=True)
import datetime as dt
vandaag = dt.datetime.now(P.TZ).date()
for d in (1, 2, 3):
    v = P.verwacht_dag(coefs, weer, prijzen, vandaag + dt.timedelta(days=d))
    if v:
        print(v["datum"], {k: v[k] for k in ("gemiddeld_eur", "avondpiek_eur", "goedkoopste_uur", "goedkoopste_eur", "duurste_uur", "duurste_eur")}, flush=True)
print("tijd", round(time.time() - t0, 1), flush=True)
