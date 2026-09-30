"""Onbekend = niet verkopen (v5.26.6).

Gemeld: "30 Sep 20:35 - De accu luisterde niet: het handmatig vermogen zou
op 1600 motten staan, maor steet op -2000." In de eerste ronde na de start
van v5.26.4 (20:34:02) stuurde het EMS een verkoop van 1600 W, terwijl de
regels zeiden: bewaren. De Zendure voerde hem niet uit; er is niets verkocht.

Twee terugvalpaden lieten de verkoop door zolang nog niet alles gemeten was:
de verkooptoets ("nog geen accustand - de reserve bewaakt de woning") en de
vermogensfunctie (terugval op de laadstand: 79%, dus vol vermogen). Niet
weten is iets anders dan weten dat er ruimte is.
"""
from datetime import datetime, timedelta, timezone

NU = datetime(2026, 9, 30, 20, 34, tzinfo=timezone(timedelta(hours=2)))


def _met_sensor(c, hass, waarde):
    c.config = dict(c.config or {})
    c.config["available_energy_sensor_entity"] = "sensor.beschikbaar"
    c.config["battery_soc_sensor_entity"] = "sensor.soc"
    hass.states.set("sensor.beschikbaar", waarde)
    hass.states.set("sensor.soc", "79")
    return c


def test_verkooptoets_sensor_ingesteld_maar_nog_geen_waarde(make_coordinator, hass):
    c = _met_sensor(make_coordinator({}), hass, "unavailable")
    c.beschikbare_energie_kwh = lambda: None

    uit = c.may_sell_now(NU)

    assert uit["mag_verkopen"] is False
    assert "niet gemeten" in uit["reden"]


def test_verkooptoets_zonder_sensor_zoals_voorheen(make_coordinator, hass):
    """Blokkeren zou een installatie zonder accusensor stilzetten."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config.pop("available_energy_sensor_entity", None)
    c.beschikbare_energie_kwh = lambda: None

    assert c.may_sell_now(NU)["mag_verkopen"] is True


def test_vermogen_sensor_ingesteld_maar_nog_geen_waarde(make_coordinator, hass):
    """De ronde van 20:34: geen beschikbare energie -> geen 1600 W."""
    c = _met_sensor(make_coordinator({}), hass, "unavailable")
    c._get_dynamic_discharge_reserve_kwh = lambda now, blok, **k: 3.7

    assert c._get_soc_scaled_discharge_power(1600.0, NU, None, []) is None
    assert c.last_discharge_power_applied is None


def test_vermogen_reserve_nog_niet_te_berekenen(make_coordinator, hass):
    c = _met_sensor(make_coordinator({}), hass, "6.1")
    c._get_dynamic_discharge_reserve_kwh = lambda now, blok, **k: None

    assert c._get_soc_scaled_discharge_power(1600.0, NU, None, []) is None


def test_vermogen_zonder_sensor_blijft_de_laadstand_gebruiken(make_coordinator, hass):
    """Voor installaties zonder sensor is de laadstand de manier om te
    verkopen - die blijft."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config.pop("available_energy_sensor_entity", None)
    c.config["battery_soc_sensor_entity"] = "sensor.soc"
    hass.states.set("sensor.soc", "79")
    c.effective_min_soc_percent = lambda: 10.0

    assert c._get_soc_scaled_discharge_power(1600.0, NU, None, []) == 1600.0
