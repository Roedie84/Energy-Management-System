import sys, os, subprocess, json, sqlite3, urllib.request, time
D = "/homeassistant/pv_tmp"
if len(sys.argv) < 2:
    subprocess.Popen([sys.executable, __file__, "kind"], start_new_session=True,
                     stdout=open(D + "/out.txt", "w"), stderr=subprocess.STDOUT)
    print("gestart")
    sys.exit()
sys.path.insert(0, D)
import prijsverwachting as P
t0 = time.time()
c = sqlite3.connect("file:/homeassistant/home-assistant_v2.db?mode=ro", uri=True)
mid = c.execute("select id from statistics_meta where statistic_id='sensor.zonneplan_current_hourly_electricity_tariff'").fetchone()[0]
rijen = [{"start": r[0], "mean": r[1]} for r in c.execute("select start_ts, mean from statistics where metadata_id=? order by start_ts", (mid,))]
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
