"""v5.31 - grootverbruikers herkennen aan hun eigen meting (schaduw).

Gevraagd: "Ik wil dat het EMS aan de hand van vermogensmetingen definieert of
iets een grootverbruiker is of niet, buiten de door mij aangegeven
grootverbruikers om." - "Alleen apparaten met een eigen vermogensmeting."

Schaduw: leert en laat zien, stuurt niets.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import grootverbruikers as gv

T0 = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
DROGER = "sensor.droger_vermogen"


def _cyclus(leer, start, minuten, watt, entiteit=DROGER, pauze_na=None, naam="Droger"):
    """Een gebruik van `minuten` lang, per minuut gemeten, daarna 15 min 2 W."""
    for m in range(minuten):
        w = 5.0 if pauze_na and m in pauze_na else watt
        gv.werk_bij(leer, entiteit, naam, w, start + timedelta(minutes=m))
    for m in range(minuten, minuten + 15):
        gv.werk_bij(leer, entiteit, naam, 2.0, start + timedelta(minutes=m))


# --- leren ----------------------------------------------------------------


def test_een_klein_apparaat_wordt_niet_onthouden():
    leer = {}
    for m in range(60):
        gv.werk_bij(leer, "sensor.lamp", "Lamp", 8.0, T0 + timedelta(minutes=m))
    assert leer == {}


def test_een_gebruik_wordt_gemeten_met_duur_en_energie():
    leer = {}
    _cyclus(leer, T0, 60, 2000.0)
    staat = leer[DROGER]
    assert staat["actief"] is None
    assert staat["duren_min"] == [59.0]
    assert 1.9 <= staat["energie_kwh"][0] <= 2.05   # 2000 W een uur
    assert staat["piek_w"] == [2000]


def test_een_korte_piek_is_geen_gebruik():
    leer = {}
    _cyclus(leer, T0, 2, 2200.0)
    assert leer[DROGER]["duren_min"] == []


def test_thermostaatpauzes_blijven_een_keer():
    leer = {}
    _cyclus(leer, T0, 60, 2000.0, pauze_na=set(range(20, 26)))
    assert len(leer[DROGER]["duren_min"]) == 1


def test_een_meetgat_telt_niet_als_verbruik():
    leer = {}
    gv.werk_bij(leer, DROGER, "Droger", 2000.0, T0)
    gv.werk_bij(leer, DROGER, "Droger", 2000.0, T0 + timedelta(hours=3))
    assert leer[DROGER]["actief"]["energie_wh"] == 0.0


def test_onbekend_vermogen_sluit_een_gebruik_pas_na_de_wachttijd():
    leer = {}
    gv.werk_bij(leer, DROGER, "Droger", 2000.0, T0)
    gv.werk_bij(leer, DROGER, "Droger", None, T0 + timedelta(minutes=5))
    assert leer[DROGER]["actief"] is not None


# --- indelen --------------------------------------------------------------


def test_na_drie_keer_kortlopend_of_aanhoudend():
    kort, lang = {}, {}
    for d in range(3):
        start = T0 + timedelta(days=d)
        _cyclus(kort, start, 45, 2000.0)
        _cyclus(lang, start, 180, 1200.0)
        if d < 2:
            assert gv.indeling(kort[DROGER]) == "lerend"
    assert gv.indeling(kort[DROGER]) == "kortlopend"
    assert gv.indeling(lang[DROGER]) == "aanhoudend"


def test_het_overzicht_zegt_wat_het_zou_doen():
    leer = {}
    for d in range(3):
        _cyclus(leer, T0 + timedelta(days=d), 45, 2000.0)
    rij = gv.overzicht(leer, set(), {DROGER: 3.0})[0]
    assert rij["indeling"] == "kortlopend"
    assert rij["keren"] == 3
    assert "één cyclus van" in rij["schaduwbesluit"]
    assert rij["al_ingesteld"] is False


def test_een_apparaat_uit_de_eigen_lijst_verandert_niets():
    leer = {}
    _cyclus(leer, T0, 45, 2000.0)
    rij = gv.overzicht(leer, {DROGER}, {})[0]
    assert rij["al_ingesteld"] is True
    assert "verandert niets" in rij["schaduwbesluit"]


def test_lerend_zegt_hoeveel_keer_nog():
    leer = {}
    _cyclus(leer, T0, 45, 2000.0)
    assert "Nog 2 keer" in gv.overzicht(leer, set(), {})[0]["schaduwbesluit"]


# --- in de coordinator ----------------------------------------------------


def _coordinator(make_coordinator, hass):
    c = make_coordinator(
        {
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen",
        }
    )
    c.nilm_confirmed_devices = {DROGER: {"friendly_name": "Droger"}}
    return c


def test_alleen_apparaten_met_een_eigen_meting(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set(DROGER, "2000")
    hass.states.set("sensor.vaatwasser_vermogen", "2100")
    hass.states.set("sensor.huis_vermogen", "5000")   # totaal, geen eigen meting
    c._leer_grootverbruikers(T0)
    assert set(c.grootverbruiker_leer) == {DROGER, "sensor.vaatwasser_vermogen"}


def test_de_eigen_lijst_wordt_herkend(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set(DROGER, "2000")
    hass.states.set("sensor.vaatwasser_vermogen", "2100")
    c._leer_grootverbruikers(T0)
    rijen = {r["entiteit"]: r for r in c.get_grootverbruikers_schaduw()["apparaten"]}
    assert rijen["sensor.vaatwasser_vermogen"]["al_ingesteld"] is True
    assert rijen[DROGER]["al_ingesteld"] is False
    assert rijen[DROGER]["actief"] is True
    assert c.get_grootverbruikers_schaduw()["stuurt"] is False


def test_schaduw_stuurt_niets(make_coordinator, hass):
    """Meetcode stuurt nooit: de leerstap verandert geen besluit en schrijft niets."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set(DROGER, "2500")
    hass.services.calls.clear()
    bron_voor = c.last_heavy_load_source
    for m in range(30):
        c._leer_grootverbruikers(T0 + timedelta(minutes=m))
    assert hass.services.calls == []
    assert c.last_heavy_load_source == bron_voor


def test_het_geleerde_wordt_bewaard(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set(DROGER, "2000")
    c._leer_grootverbruikers(T0)
    opgeslagen = c._collect_persisted_state()
    assert DROGER in opgeslagen["grootverbruiker_leer"]
    nieuw = _coordinator(make_coordinator, hass)
    nieuw._apply_persisted_state(opgeslagen)
    assert DROGER in nieuw.grootverbruiker_leer


def test_de_sensor_en_de_export_tonen_het(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import MeetlogSensor

    c = _coordinator(make_coordinator, hass)
    hass.states.set(DROGER, "2000")
    c._leer_grootverbruikers(T0)
    attrs = MeetlogSensor(c, "x").extra_state_attributes
    assert attrs["grootverbruikers"]["apparaten"][0]["naam"] == "Droger"


# --- de kaart (logica hoort niet in het sjabloon) --------------------------


def test_de_kaarttekst_zonder_apparaten():
    tekst = gv.als_tekst([], 1000.0, "uitleg")
    assert "Nog geen apparaat" in tekst and "1000 W" in tekst


def test_de_kaarttekst_met_apparaten():
    leer = {}
    for d in range(3):
        _cyclus(leer, T0 + timedelta(days=d), 45, 2000.0)
    _cyclus(leer, T0, 45, 2000.0, entiteit="sensor.vaatwasser_vermogen", naam="Vaatwasser")
    rijen = gv.overzicht(leer, {"sensor.vaatwasser_vermogen"}, {DROGER: 2101.6, "sensor.vaatwasser_vermogen": None})
    tekst = gv.als_tekst(rijen, 1000.0, "uitleg")
    assert "| Droger | 2102 W | 3 | 44 min |" in tekst
    assert "| Vaatwasser (eigen lijst) | – |" in tekst
    assert "**Droger**: Zou bij gebruik meetellen als één cyclus van" in tekst
    assert "**Vaatwasser" not in tekst   # eigen lijst: geen schaduwbesluit
    assert "kWh" in tekst and "," in tekst   # Nederlandse komma
