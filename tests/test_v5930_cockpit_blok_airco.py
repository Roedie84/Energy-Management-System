"""v5.93.0: cockpit tijdens het laadblok, apparaatstanden en airco-verwachting.

Gemeld 12-10 11:32 met een schermafdruk van "Verkopen en reserve": tijdens het
goedkope blok (11:30-16:15) stonden "Tot het blok", "Na het blok" en "Vrij te
verkopen" leeg en sprong de tekortkans van 0% naar 99% terwijl er 3,72 kWh
beschikbaar was tegen 1,30 nodig. Bij "Huis en apparaten" stond de ruwe stand
"Test aan". Gevraagd 11:39: op dezelfde kaart zien of de airco verwacht wordt,
omdat dat de accu raakt.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRON = ROOT / "custom_components" / "energy_management_system"
JS = (BRON / "www" / "ems-cockpit.js").read_text(encoding="utf-8")

NU = datetime(2026, 10, 12, 9, 40, tzinfo=timezone.utc)  # 11:40 lokaal
BLOK_BEGIN = datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc)
BLOK_EIND = datetime(2026, 10, 12, 14, 15, tzinfo=timezone.utc)


def _plan(soc_eind=100.0):
    rijen = []
    t = BLOK_BEGIN
    soc = 55.0
    while t < BLOK_EIND + timedelta(hours=2):
        if t < BLOK_EIND:
            soc = min(soc_eind, soc + 2.5)
        rijen.append({"start": t.isoformat(), "soc_procent": soc})
        t += timedelta(minutes=15)
    return rijen


# --- Monte Carlo begint aan het einde van een lopend blok ---------------


def test_buiten_het_blok_begint_monte_carlo_nu(make_coordinator):
    c = make_coordinator({})
    c.last_cheap_block_end = None
    assert c._monte_carlo_start(NU, NU + timedelta(hours=8)) == (NU, 0.0)


def test_tijdens_het_blok_vanaf_het_blokeinde_met_de_geplande_stand(make_coordinator):
    c = make_coordinator({})
    c.last_cheap_block_end = BLOK_EIND
    c.accustand_procent = lambda: 55.0
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.get_quarter_plan = lambda now=None: _plan(100.0)

    start, extra = c._monte_carlo_start(NU, BLOK_BEGIN)

    assert start == BLOK_EIND
    # 55% -> 100% van 8,64 kWh
    assert abs(extra - 0.45 * 8.64) < 0.01


def test_zonder_plan_of_capaciteit_blijft_het_nu(make_coordinator):
    c = make_coordinator({})
    c.last_cheap_block_end = BLOK_EIND
    c.accustand_procent = lambda: 55.0
    c.bruikbare_capaciteit_kwh = lambda: None
    c.get_quarter_plan = lambda now=None: _plan()
    assert c._monte_carlo_start(NU, BLOK_BEGIN) == (NU, 0.0)
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.get_quarter_plan = lambda now=None: []
    assert c._monte_carlo_start(NU, BLOK_BEGIN) == (NU, 0.0)


def test_geplande_ontlading_in_het_blok_telt_niet_negatief(make_coordinator):
    c = make_coordinator({})
    c.last_cheap_block_end = BLOK_EIND
    c.accustand_procent = lambda: 80.0
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.get_quarter_plan = lambda now=None: [
        {"start": (BLOK_EIND - timedelta(minutes=15)).isoformat(), "soc_procent": 70.0}
    ]
    assert c._monte_carlo_start(NU, BLOK_BEGIN) == (BLOK_EIND, 0.0)


def test_simulatie_gebruikt_het_startmoment():
    bron = (BRON / "coordinator.py").read_text(encoding="utf-8")
    i = bron.index("start, extra_beschikbaar, cheap_block_start = self._monte_carlo_vanaf(")
    stuk = bron[i:i + 6000]
    assert "cursor = start" in stuk
    assert "self._monte_carlo_centrum(\n            start, cursor" in stuk
    assert "available_kwh += extra_beschikbaar" in stuk
    # tijdens een blok wel bewaren, maar met een eigen basis (v5.141.0, L-EMS-041)
    assert "MC_KANS_BASIS_TOT_BLOK if start <= now else MC_KANS_BASIS_IN_BLOK" in stuk


# --- Airco-verwachting ---------------------------------------------------


def test_airco_verwachting_met_uren(make_coordinator):
    c = make_coordinator({})
    c.last_cheap_block_start = NU + timedelta(hours=20)
    c._airco_ochtend_extra_kwh = lambda now, tot: {"extra_kwh": 0.0, "verwacht_kwh": 0.0}
    c._airco_gebruik_extra_kwh = lambda now, tot: {
        "extra_kwh": 0.84, "verwacht_kwh": 1.6,
        "uren": [{"uur": "18:00", "kans": 0.6, "kwh": 0.4, "zeker": False},
                 {"uur": "20:00", "kans": 0.4, "kwh": 0.44, "zeker": False}],
    }
    v = c.get_airco_verwachting(NU)
    assert v["beschikbaar"] and v["verwacht"]
    assert v["in_reserve_kwh"] == 0.84
    assert v["tekst"] == "verwacht rond 18-21 u (kans 60%)"
    assert v["tot"] == (NU + timedelta(hours=20)).isoformat()


def test_airco_niet_verwacht_en_terugval_horizon(make_coordinator):
    c = make_coordinator({})
    c.last_cheap_block_start = BLOK_BEGIN  # loopt al: tot 09:00
    c._airco_ochtend_extra_kwh = lambda now, tot: {"extra_kwh": 0.0, "verwacht_kwh": 0.0}
    c._airco_gebruik_extra_kwh = lambda now, tot: {"extra_kwh": 0.0, "verwacht_kwh": 0.0, "uren": []}
    v = c.get_airco_verwachting(NU)
    assert v["verwacht"] is False and v["tekst"] == "niet verwacht"
    assert datetime.fromisoformat(v["tot"]).hour == 9


def test_airco_draait(make_coordinator):
    c = make_coordinator({})
    c.last_cheap_block_start = NU + timedelta(hours=20)
    c._airco_ochtend_extra_kwh = lambda now, tot: {"extra_kwh": 0.0, "verwacht_kwh": 0.0}
    c._airco_gebruik_extra_kwh = lambda now, tot: {
        "extra_kwh": 1.2, "verwacht_kwh": 1.2,
        "uren": [{"uur": "12:00", "kans": 1.0, "kwh": 0.6, "zeker": True}],
    }
    assert c.get_airco_verwachting(NU)["tekst"] == "airco draait"


def test_airco_sensor_geeft_de_verwachting_mee():
    sensor = (BRON / "sensor.py").read_text(encoding="utf-8")
    assert 'uit["verwachting"] = self._coordinator.get_airco_verwachting()' in sensor


# --- Cockpit (JS) ---------------------------------------------------------


def test_vrij_te_verkopen_valt_terug_op_het_veld_van_de_verkooptoets():
    # v5.96.2: het totaal uit de verkooptoets, niet alleen het deel na het blok.
    assert "const vrij = num(toets.vrij_te_verkopen_kwh)" in JS


def test_tijdens_het_blok_een_tekst_in_plaats_van_streepjes():
    assert "_blokLoopt()" in JS and "laadblok loopt" in JS
    assert 'verkoop: ["gacs", "mc", "tekort", "uitleg", "blok"]' in JS


def test_apparaatstanden_hebben_een_label():
    for stand in ("test_aan", "wacht_op_apparaat", "aan_het_laden", "voltooid",
                  "voltooid_vandaag", "overruled"):
        assert f"  {stand}: " in JS
    # v5.93.0: een kleur per stand (12-10 11:50)
    assert "const APPARAAT_KLEUR = [" in JS and "apparaatKleur(s)" in JS
    for stand, kleur in (("aan_het_laden", "groen"), ("test_aan", "cyaan"),
                         ("wacht_op_goedkoop_blok", "amber"), ("klaar", "blauw"),
                         ("overruled", "violet"), ("wacht_op_apparaat", "tekst3")):
        assert _kleur(stand) == f"var(--{kleur})", stand
    from custom_components.energy_management_system.const import APPLIANCE_STATE_LABELS

    assert APPLIANCE_STATE_LABELS["test_aan"] == "kijkt of er iets aan hangt"


def test_airco_regel_op_huis_en_apparaten():
    assert 'regel("airco", "Airco"' in JS
    assert 'attr(besluit, "verwachting")' in JS


def test_js_alleen_ascii():
    assert all(ord(t) < 128 for t in JS)


def _kleur(stand: str) -> str:
    """Speel APPARAAT_KLEUR na: eerste regel die past."""
    import re

    blok = JS[JS.index("const APPARAAT_KLEUR = ["):JS.index("const apparaatKleur")]
    for patroon, kleur in re.findall(r'\[/(.+?)/, "([^"]+)"\]', blok):
        if re.search(patroon, stand):
            return kleur
    return ""
