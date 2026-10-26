"""v5.127.4 - de uitleg bij `expensive_quarter_soc_protected` zegt wat er
echt gebeurde als de verkoopreserve ontbreekt (leerronde 26-10).

Gezien 25-10 23:30: duur kwartier (19,1 ct) in het lopende goedkope blok
21:30-06:00. De reserve wordt in het blok niet berekend (er wordt geladen),
dus verkocht de sturing terecht niet. De uitleg zei: "alle beschikbare
energie (2,30 kWh) is al nodig om de rest van de nacht te overbruggen".
Alleen de tekst verandert; de sturing niet.
"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 10, 25, 23, 30, tzinfo=TZ)


def _coord(make_coordinator):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar"})
    c._read_sensor_float = lambda *a, **k: 2.30
    c._na_module_leeg = lambda v: v
    return c


def test_in_het_lopende_blok_geen_verkoop_en_de_uitleg_zegt_blok(make_coordinator, hass):
    c = _coord(make_coordinator)
    c.last_price_priority_held_off = True  # oud, van een eerder kwartier
    blok = NU - timedelta(hours=2)
    assert c._get_soc_scaled_discharge_power(2400, NU, blok, []) is None
    assert c.last_verkoopreserve_onbekend == "in_blok"
    assert c.last_price_priority_held_off is False
    c.last_reason = "expensive_quarter_soc_protected"
    c.last_available_kwh = 2.30
    tekst = c._build_explanation()
    assert "goedkope blok" in tekst
    assert "rest van de nacht" not in tekst
    assert "prijs-prioriteit" not in tekst


def test_reserve_onbekend_buiten_het_blok(make_coordinator, hass):
    c = _coord(make_coordinator)
    c._get_dynamic_discharge_reserve_kwh = lambda *a, **k: None
    assert c._get_soc_scaled_discharge_power(2400, NU, NU + timedelta(hours=3), []) is None
    assert c.last_verkoopreserve_onbekend == "onbekend"
    c.last_reason = "expensive_quarter_soc_protected"
    tekst = c._build_explanation()
    assert "niet te berekenen" in tekst


def test_met_reserve_blijft_de_oude_uitleg(make_coordinator, hass):
    c = _coord(make_coordinator)
    c._get_dynamic_discharge_reserve_kwh = lambda *a, **k: 5.0
    c.verkoopreserve = lambda *a, **k: {"reserve_kwh": 5.0}
    c._geen_ruimte_boven_reserve = lambda *a, **k: None
    c._read_corrected_consumption_power = lambda: 300.0
    assert c._get_soc_scaled_discharge_power(2400, NU, NU + timedelta(hours=3), []) is None
    assert c.last_verkoopreserve_onbekend is None
    c.last_reason = "expensive_quarter_soc_protected"
    c.last_available_kwh = 2.30
    assert "nachtreserve" in c._build_explanation()
