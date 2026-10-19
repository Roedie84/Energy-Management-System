import sys, json, time, subprocess
D = "/homeassistant/pv_tmp"
if len(sys.argv) < 2:
    subprocess.Popen([sys.executable, __file__, "kind"], start_new_session=True,
                     stdout=open(D + "/out2.txt", "w"), stderr=subprocess.STDOUT)
    print("gestart"); sys.exit()
sys.path.insert(0, D)
import keuzeoordeel as K
st = json.load(open("/homeassistant/.storage/energy_management_system_state"))
data = st.get("data", st)
dv = data.get("dagverloop") or {}
nab = {n.get("datum"): n for n in data.get("nabeschouwingen") or []}
print("dagen", sorted(dv)[-5:], flush=True)
for dag in sorted(dv)[-4:-1]:
    rijen = dv[dag]
    kw = [K.Kwartier(tijd=r["tijd"], huis_kwh=r["huis_w"] / 4000, pv_kwh=(r.get("pv_w") or 0) / 4000,
                     prijs_eur=r["prijs_ct"] / 100, accu_kwh=(r.get("accu_w") or 0) / 4000,
                     reden=r.get("reden"), stand=r.get("stand"))
          for r in rijen if r.get("huis_w") is not None and r.get("prijs_ct") is not None]
    socs = [r["soc"] for r in rijen if r.get("soc") is not None]
    begin = max(0.0, (socs[0] - 10) / 90 * 10.4)
    t0 = time.time()
    u = K.spijt_per_kwartier(kw, capaciteit_kwh=10.4, begin_kwh=begin, bodem_kwh=0, laad_kw=2.4, ontlaad_kw=2.4,
                             rendement=0.852, slijtage_eur_per_kwh=0.0)
    ks = K.keuzes(u["regels"])
    print(dag, "n", len(kw), "gemist", u["gemist_eur"], "nabeschouwing", (nab.get(dag) or {}).get("gemist_eur"),
          "keuzes", len(ks), "tijd", round(time.time() - t0, 2), flush=True)
    for k in sorted(ks, key=lambda k: -k["spijt_eur"])[:4]:
        print("   ", K.tekst(k), k["richting"], flush=True)
