"""v5.118.0: de punten waarop Ruud 22-10 16:45 akkoord gaf, plus de dag bij
tijden die niet vandaag vallen (22-10 16:49).

1. L-EMS-025: zonvoorspelling corrigeren als de dagen aan één kant liggen.
2. L-EMS-026: 's nachts de ochtendpiek vrijhouden (spaarplan met marge).
3. Dagbesparing: bij een even weggevallen accustand de laatste correctie.
4. Prijsbron: tot wanneer de bewaarde prijzen reiken.
5. Sensor-gezondheid: fouten uit een storing verlopen.
6. Plantekort-melding over de mediaan van 15 minuten.
7. Tijden met de dag erbij ("morgen 21:15", "vr 21:15").
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.energy_management_system.const import (
    DIP_MARGE,
    PRICE_SCALE_FACTOR,
    ENERGY_BALANCE_FOUT_VERLOOPT_UUR,
    SOLAR_EENZIJDIG_MAX_PERCENT,
)
from custom_components.energy_management_system.solar_forecast import SolarForecastAccuracyTracker
from custom_components.energy_management_system.tijdtekst import (
    periode_met_dag,
    tijd_met_dag,
)

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 22, 16, 49, tzinfo=TZ)  # donderdag
MAP = Path(__file__).resolve().parents[1] / "custom_components" / "energy_management_system"


# --- 7. tijden met de dag ----------------------------------------------------

def test_tijd_vandaag_alleen_de_tijd():
    assert tijd_met_dag(NU.replace(hour=21, minute=15), NU) == "21:15"


def test_tijd_morgen_en_verder_weg():
    morgen = NU.replace(hour=21, minute=15) + timedelta(days=1)
    assert tijd_met_dag(morgen, NU) == "morgen 21:15"
    assert tijd_met_dag(morgen + timedelta(days=1), NU) == "za 21:15"
    assert tijd_met_dag(NU - timedelta(days=1), NU) == "gisteren 16:49"
    assert tijd_met_dag(NU + timedelta(days=10), NU) == "01-11 16:49"


def test_eindtijd_middernacht_hoort_bij_de_dag_die_afloopt():
    middernacht = (NU + timedelta(days=1)).replace(hour=0, minute=0)
    assert tijd_met_dag(middernacht, NU, eind=True) == "24:00"
    assert periode_met_dag(NU.replace(hour=21, minute=15), middernacht, NU) == "21:15-24:00"
    van = NU.replace(hour=21, minute=15) + timedelta(days=1)
    assert periode_met_dag(van, van + timedelta(hours=2), NU) == "morgen 21:15-23:15"
    laat = NU.replace(hour=23, minute=0)
    assert periode_met_dag(laat, laat + timedelta(hours=2), NU) == "23:00-morgen 01:00"


def test_plan_tijd_tekst_gebruikt_de_weekdag(make_coordinator):
    c = make_coordinator({})
    overmorgen = NU + timedelta(days=2)
    assert c._plan_tijd_tekst(overmorgen, NU.date()) == "za 16:49"
    assert c._plan_tijd_tekst(NU + timedelta(days=1), NU.date()) == "morgen 16:49"


def test_teksten_met_blok_noemen_de_dag():
    bron = (MAP / "coordinator.py").read_text(encoding="utf-8")
    for oud in ("blok van {blok:%H:%M}", "Om {cheap_block_start:%H:%M}", "om {om:%H:%M} laadt",
                '"tot_tekst": dt_util.as_local(tot).strftime("%H:%M")'):
        assert oud not in bron


def test_cockpit_klok_met_dag_en_ascii():
    js = (MAP / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert "const klokDag = " in js and "const klokEind = " in js
    assert "klokDag(blok.start)" in js and "klokEind(start, eind)" in js
    assert all(ord(t) < 128 for t in js)


# --- 1. L-EMS-025 ---------------------------------------------------------------

def _tracker(reeks):
    t = SolarForecastAccuracyTracker.__new__(SolarForecastAccuracyTracker)
    t.deviation_history = list(reeks)
    t.deviation_context = []
    return t


GEMETEN_22_10 = [-6.1, -48.2, -6.5, -17.4, -7.9, -26.4, -8.6, -13.8, -2, -40.3, -39.6, -8.1, -9.6, -35.7]


def test_eenzijdig_te_hoog_geeft_correctie():
    t = _tracker([9.6, 8.2] + GEMETEN_22_10)
    e = t.eenzijdige_correctie
    assert e["richting"] == "te hoog" and e["dagen"] == 14 and e["aan_een_kant"] == 14
    # mediaan van de dagen die niet ver mis zijn (< 25 %): -8,1
    assert e["bias_percent"] == -8.1
    assert t.bias_ingehouden_reden is not None      # de vlakke correctie houdt zich in


def test_eenzijdig_begrensd():
    e = _tracker([-20.0] * 14).eenzijdige_correctie
    assert e["bias_percent"] == -SOLAR_EENZIJDIG_MAX_PERCENT and e["begrensd"]


def test_gemengd_of_te_kort_geen_correctie():
    assert _tracker([-10, 10] * 7).eenzijdige_correctie is None
    assert _tracker([-10] * 9).eenzijdige_correctie is None
    # 11 van 14 = 79 % aan een kant: niet genoeg
    assert _tracker([-10] * 11 + [5] * 3).eenzijdige_correctie is None
    assert _tracker([-10] * 12 + [5] * 2).eenzijdige_correctie is not None


def test_zonbias_gebruikt_eenzijdige_ondergrens(make_coordinator):
    c = make_coordinator({})
    tracker = _tracker(GEMETEN_22_10)
    tracker.bias_voor_bewolking = lambda b: -3.7
    c.solar_tracker = tracker
    c._weather_cloud_cover_percent = lambda: 50.0
    assert c.zonbias_percent() == -8.1
    tracker.bias_voor_bewolking = lambda b: -12.0      # verder dezelfde kant op: wint
    assert c.zonbias_percent() == -12.0
    tracker.bias_voor_bewolking = lambda b: 4.0        # andere kant: ondergrens
    assert c.zonbias_percent() == -8.1


# --- 2. L-EMS-026 ---------------------------------------------------------------

def _nacht(c, prijs_nu=0.24, ochtend=0.35):
    c.huidige_prijs_eur_per_kwh = lambda: prijs_nu
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 3.0}
    nu = datetime(2026, 10, 22, 2, 0, tzinfo=TZ)
    t = nu.replace(hour=0)
    entries = []
    while t < nu.replace(hour=12):
        prijs = ochtend if 7 <= t.hour < 10 else prijs_nu
        entries.append((t, t + timedelta(minutes=15), prijs * PRICE_SCALE_FACTOR))
        t += timedelta(minutes=15)
    return nu, entries, nu.replace(hour=11)


def _rendement(monkeypatch, c):
    monkeypatch.setattr(type(c), "learned_battery_efficiency_percent", property(lambda s: 85.0))


def test_nacht_actief_als_ochtendpiek_duur_genoeg(make_coordinator, monkeypatch):
    c = make_coordinator({})
    _rendement(monkeypatch, c)
    c.instelling = lambda k, d=None: d
    nu, entries, blok = _nacht(c)
    uit = c._nacht_voor_ochtendpiek(nu, entries, blok)
    # 0,24 / 0,85 + 0,03 = 0,312 <= 0,35
    assert uit["actief"] is True and uit["marge"] == DIP_MARGE
    assert abs(uit["drempel_eur"] - 0.3124) < 0.001


def test_nacht_niet_actief_bij_kleine_piek_of_overdag(make_coordinator, monkeypatch):
    c = make_coordinator({})
    _rendement(monkeypatch, c)
    c.instelling = lambda k, d=None: d
    nu, entries, blok = _nacht(c, ochtend=0.30)
    assert c._nacht_voor_ochtendpiek(nu, entries, blok)["actief"] is False
    nu2, entries2, blok2 = _nacht(c)
    assert c._nacht_voor_ochtendpiek(nu2.replace(hour=8), entries2, blok2)["actief"] is False
    assert c._nacht_voor_ochtendpiek(nu2, entries2, None)["actief"] is False


def test_spaarbesluit_rekent_met_de_nachtmarge():
    bron = (MAP / "coordinator.py").read_text(encoding="utf-8")
    assert 'marge = DIP_MARGE if nacht.get("actief") else 1.0' in bron
    assert "plan = self.spaarplan(now, entries, cheap_block_start, marge=marge)" in bron


# --- 3. dagbesparing ------------------------------------------------------------

def test_besparing_valt_terug_op_laatste_correctie(make_coordinator):
    c = make_coordinator({})
    c._counterfactual_day_key = NU.date()
    c._savings_day_start_available_kwh = 6.0
    c.counterfactual_cost_today_eur = 2.0
    c.actual_cost_today_eur = 1.0
    c._voorraad_kwh_waarde = lambda: (0.25, "test")
    c.beschikbare_energie_kwh = lambda: 2.0
    eerst = c.get_savings_correction()
    assert eerst["besparing_gecorrigeerd_eur"] == 0.0           # 1,00 - 4 x 0,25
    c.beschikbare_energie_kwh = lambda: None                    # Zendure even weg
    daarna = c.get_savings_correction()
    assert daarna["correctie_beschikbaar"] and daarna["uit_laatste_meting"]
    assert daarna["besparing_gecorrigeerd_eur"] == 0.0
    c._counterfactual_day_key = NU.date() + timedelta(days=1)    # andere dag: niet
    assert c.get_savings_correction()["correctie_beschikbaar"] is False


# --- 4. prijsbron ---------------------------------------------------------------

def test_prijsbron_tot_wanneer_bekend(make_coordinator, monkeypatch):
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 14, 0, tzinfo=timezone.utc)
    import custom_components.energy_management_system.coordinator as mod
    monkeypatch.setattr(mod.dt_util, "now", lambda: nu)
    eind = datetime(2026, 10, 23, 22, 0, tzinfo=timezone.utc)
    c.prijs_forecast_cache = {
        "om": (nu - timedelta(hours=2)).isoformat(),
        "forecast": [{"start_date": (eind - timedelta(minutes=15)).isoformat(), "end_date": eind.isoformat()}],
    }
    c._prijsbron_weg_sinds = (nu - timedelta(minutes=45)).isoformat()
    c._prijsbron_terugval = "bewaarde reeks"
    pb = c.get_prijsbron(nu)
    assert pb["bewaarde_prijzen_tot"] == eind.isoformat()
    punt = c._prijsbron_aandachtspunt(nu)
    assert "1 kwartieren vooruit, tot morgen 22:00" in punt


# --- 5. sensor-gezondheid -------------------------------------------------------

def _gezondheid(c, monsters):
    c.energy_balance_error_history = [m[0] for m in monsters]
    c.energy_balance_sample_tijden = [m[1] for m in monsters]


def test_fouten_uit_een_storing_verlopen(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 16, 0, tzinfo=timezone.utc)
    oud = (nu - timedelta(hours=ENERGY_BALANCE_FOUT_VERLOOPT_UUR + 1)).isoformat()
    recent = (nu - timedelta(minutes=30)).isoformat()
    _gezondheid(c, [(50.0, oud)] * 16 + [(900.0, oud)] * 3 + [(None, oud)])
    c._verloop_balansmonsters(nu)
    assert c.energy_balance_error_history == [50.0] * 16
    assert c.sensor_health_score == 100.0
    # een recente fout blijft staan
    _gezondheid(c, [(50.0, oud)] * 16 + [(900.0, recent)] * 4)
    c._verloop_balansmonsters(nu)
    assert len(c.energy_balance_error_history) == 20 and c.sensor_health_score == 80.0


def test_fouten_tijdens_niet_aanstuurbaar_vervallen(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 11, 20, tzinfo=timezone.utc)
    c.aansturing_onbereikbaar = {"reden": "time-out", "sinds": (nu - timedelta(minutes=20)).isoformat()}
    voor = (nu - timedelta(minutes=30)).isoformat()     # 10 min voor de melding: aanloop
    ruim_voor = (nu - timedelta(hours=1)).isoformat()
    _gezondheid(c, [(50.0, ruim_voor)] * 16 + [(900.0, ruim_voor)] + [(900.0, voor)] * 3)
    c._verloop_balansmonsters(nu)
    assert c.energy_balance_error_history == [50.0] * 16 + [900.0]


def test_oude_monsters_zonder_moment(make_coordinator):
    """Opslag van voor v5.118.0: de monsters krijgen het eerste moment dat ze
    gezien worden en verlopen daarna zoals de rest."""
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 16, 0, tzinfo=timezone.utc)
    c.energy_balance_error_history = [50.0] * 16 + [900.0] * 4
    c.energy_balance_sample_tijden = []
    c._verloop_balansmonsters(nu)
    assert len(c.energy_balance_error_history) == 20
    assert c.energy_balance_sample_tijden == [nu.isoformat()] * 20
    c._verloop_balansmonsters(nu + timedelta(hours=ENERGY_BALANCE_FOUT_VERLOOPT_UUR, minutes=1))
    assert c.energy_balance_error_history == [50.0] * 16


def test_nieuw_monster_krijgt_moment(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 16, 0, tzinfo=timezone.utc)
    c._record_balance_sample(40.0, nu)
    assert c.energy_balance_sample_tijden == [nu.isoformat()]


# --- 6. plantekort --------------------------------------------------------------

def test_plantekort_mediaan_dempt_een_uitschieter(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 8, 50, tzinfo=timezone.utc)
    reeks = [0, 0, 0, 4, 0, 0]
    uit = [c._plan_tekort_gedempt(nu + timedelta(minutes=i), t) for i, t in enumerate(reeks)]
    assert max(uit) == 0
    # een kwartier aanhoudend: wel
    for i in range(6, 20):
        laatste = c._plan_tekort_gedempt(nu + timedelta(minutes=i), 4)
    assert laatste == 4


def test_melding_gebruikt_gedempt_aantal(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 8, 50, tzinfo=timezone.utc)
    verstuurd = []
    c._dispatch_notification = lambda *a, **k: verstuurd.append(k.get("kind"))
    c.get_quarter_plan_summary = lambda now=None: {
        "beschikbaar": True, "tekort_kwartieren": 4, "tekort_perioden": ["09:00-10:00"],
        "laagste_soc_procent": 10,
    }
    c._plan_tekort_monsters = [(nu - timedelta(minutes=m), 0) for m in range(1, 10)]
    c.last_solar_defer_plan = {}
    c._meld_planningswijzigingen(nu)
    assert "plan_tekort" not in verstuurd
    assert c.last_plan_shortfall["kwartieren"] == 4          # de verkooprem ziet het wel


def test_spaarmelding_noemt_morgen(make_coordinator):
    c = make_coordinator({})
    blok = (NU + timedelta(days=1)).replace(hour=21, minute=15)
    assert c._spaarplan_bloktijd(blok, {"berekend_om": NU.isoformat()}) == "morgen 21:15"
    assert c._spaarplan_bloktijd(blok, {}) == "21:15"           # zonder moment: als voorheen
