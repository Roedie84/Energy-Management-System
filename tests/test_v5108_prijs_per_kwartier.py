"""v5.108.0: prijsverwachting per kwartier, en "bekend tot" klopt weer.

Gevraagd 20-10: "Waar zie ik nu de prijs voorspelling per kWh?" en daarna
"Graag maar wel per kwartier ik heb immers kwartierprijzen". Bij het
nakijken bleek "prijzen bekend tot" leeg: morgen werd voorspeld terwijl die
prijzen al gepubliceerd waren.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from custom_components.energy_management_system import prijsverwachting as P
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator

JS = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
      / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _kwartieren(dagen=7, begin=datetime(2026, 10, 1, tzinfo=P.TZ)):
    """Elk uur: 0,30 met een vast patroon -2, -1, +1, +2 ct."""
    uit = []
    t = begin.astimezone(timezone.utc)
    for _ in range(dagen * 96):
        k = t.astimezone(P.TZ).minute // 15
        uit.append((t, 0.30 + (-0.02, -0.01, 0.01, 0.02)[k]))
        t += timedelta(minutes=15)
    return uit


def test_kwartiervorm_leert_het_patroon_binnen_het_uur():
    vorm = P.kwartiervorm(_kwartieren())
    assert vorm["08:0"] == -0.02 and vorm["08:3"] == 0.02
    assert abs(vorm["19:1"] + 0.01) < 1e-9


def test_te_weinig_uren_telt_niet():
    assert P.kwartiervorm(_kwartieren(dagen=2)) == {}


def test_kwartieren_houden_het_uurgemiddelde_gelijk():
    vorm = {"08:0": -0.02, "08:1": -0.01, "08:2": 0.01, "08:3": 0.03}   # som niet 0
    model = {"uren": [{"uur": "08:00", "sleutel": "2026-10-22T06", "prijs_eur": 0.40}]}
    kw = P.kwartieren_van_dag(model, vorm)
    assert len(kw) == 4 and kw[0][0] == datetime(2026, 10, 22, 6, tzinfo=timezone.utc)
    assert abs(sum(p for _t, p in kw) / 4 - 0.40) < 1e-9
    assert kw[0][1] < kw[1][1] < kw[2][1] < kw[3][1]
    # zonder patroon: vier keer de uurprijs
    assert [p for _t, p in P.kwartieren_van_dag(model, None)] == [0.40] * 4


def test_reeks_eerst_bekend_dan_verwacht():
    t0 = datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)
    bekend = [(t0 + timedelta(minutes=15 * i), 0.30) for i in range(8)]
    verwacht = [(t0 + timedelta(minutes=15 * i), 0.50) for i in range(6, 12)]   # overlap: bekend wint
    r = P.kwartierreeks(bekend, verwacht, t0 + timedelta(minutes=37))
    assert r["start"] == (t0 + timedelta(minutes=30)).isoformat()
    assert r["ct"] == [30.0] * 6 + [50.0] * 4
    assert r["verwacht_vanaf"] == 6 and r["stap_min"] == 15


def test_reeks_met_gat_en_leeg():
    t0 = datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)
    r = P.kwartierreeks([(t0, 0.3)], [(t0 + timedelta(minutes=45), 0.4)], t0)
    assert r["ct"] == [30.0, None, None, 40.0] and r["verwacht_vanaf"] == 3
    assert P.kwartierreeks([], [], t0) is None


def test_bekend_tot_volgt_de_prijsreeks_niet_de_meetlog():
    c = object.__new__(EnergyManagementSystemCoordinator)
    morgen = date(2026, 10, 21)
    begin = datetime.combine(date(2026, 10, 20), datetime.min.time(), P.TZ)
    entries = [(begin + timedelta(minutes=15 * i), begin + timedelta(minutes=15 * (i + 1)), 3_000_000)
               for i in range(2 * 96)]
    c._get_forecast_entries = lambda *a, **k: entries
    # de meetlog heeft vandaag (half vol) als laatste dag
    c._meetlaag = SimpleNamespace(log=SimpleNamespace(_dagen={("kwartier", "2026-10-20"): {"regels": []}}))
    c.prijsgeschiedenis = {}
    assert c._werk_prijsgeschiedenis_bij(begin + timedelta(hours=19)) == morgen
    assert isinstance(c._prijs_kwartiervorm, dict)


def test_cockpit_tekent_de_kwartiergrafiek():
    assert "_prijsGrafiek()" in JS and 'attr(this._s("prijsverwachting"), "kwartieren")' in JS
    assert ".pv-verwacht" in JS and "stroke-dasharray" in JS
    assert all(ord(ch) < 128 for ch in JS[JS.index("_prijsGrafiek() {"):JS.index("/* ---- bediening ---- */")])
