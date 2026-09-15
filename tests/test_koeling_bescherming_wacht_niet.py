"""De rusttijd blokkeerde ook de bescherming (v4.17).

Gemeld: "zag net dat de accu 39 graden was, waarom was de koeling niet
aan?" Buiten was 26,1 °C, dus een verschil van 12,9 graden - ruim boven
de aanzetdrempel van 5. De ventilator had aan moeten staan.

Van alle poorten in `evaluate_battery_cooling` past er dan één: de
minimale RUSTTIJD van dertig minuten na het uitzetten. Die is bedoeld
tegen pendelen, en onder de 35 graden is dat precies goed. Maar boven
die grens gaat het om bescherming, en de opmerking in de code zegt dat
zelf al: "boven die grens gaat het om bescherming van de omvormer, en
die wacht nergens op". De code liet hem wel wachten.

Dezelfde vorm als de dagrantsoenering in v4.15: een rem tegen pendelen
die ook de bescherming remde. Daar liep de accu op tot 35 voordat de
bescherming het overnam; hier stond hij op 39 terwijl de ventilator uit
bleef.

Boven `BATTERY_COOLING_PROTECT_ALWAYS_C` geldt de rusttijd niet meer.
Eronder ongewijzigd.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)


def _net_uitgezet(c, minuten_geleden=5):
    c.battery_cooling_last_change = NU - timedelta(minutes=minuten_geleden)


def test_boven_de_beschermingsgrens_wacht_de_koeling_niet(make_coordinator, hass):
    """Het gemelde geval: 39 °C, buiten 26,1, ventilator net uit."""
    c = make_coordinator({})
    _net_uitgezet(c)

    assert c._cooling_switch_too_recent(NU, aanzetten=True, accu_c=39.0) is False


def test_onder_de_grens_wacht_hij_wel(make_coordinator, hass):
    """Daar is de rusttijd juist de bedoeling: anders klappert hij."""
    c = make_coordinator({})
    _net_uitgezet(c)

    assert c._cooling_switch_too_recent(NU, aanzetten=True, accu_c=30.0) is True


def test_zonder_temperatuur_blijft_de_rusttijd_gelden(make_coordinator, hass):
    """Geen meting is geen vrijbrief."""
    c = make_coordinator({})
    _net_uitgezet(c)

    assert c._cooling_switch_too_recent(NU, aanzetten=True) is True


def test_uitzetten_houdt_zijn_minimale_looptijd(make_coordinator, hass):
    """De uitzonderingregel geldt alleen voor AANzetten. Een ventilator
    die net aan is, mag niet meteen weer uit - ook niet bij 39 graden,
    want dan koelt hij nooit iets weg."""
    c = make_coordinator({})
    _net_uitgezet(c)

    assert c._cooling_switch_too_recent(NU, aanzetten=False, accu_c=39.0) is True


def test_het_besluit_zet_hem_aan_bij_39_graden(make_coordinator, hass):
    """End-to-end: het besluit zelf, met een ventilator die net uit is."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["battery_cooling_fan_switch_entity"] = "switch.koeling"
    c.config["battery_temperature_sensor_entity"] = "sensor.accu_temp"
    c.config["battery_cooling_outdoor_sensor_entity"] = "sensor.buiten"
    c.config["battery_power_sensor_entity"] = "sensor.accu_vermogen"
    hass.states.set("switch.koeling", "off")
    hass.states.set("sensor.accu_temp", "39.0", {"unit_of_measurement": "°C"})
    hass.states.set("sensor.buiten", "26.1", {"unit_of_measurement": "°C"})
    hass.states.set("sensor.accu_vermogen", "500", {"unit_of_measurement": "W"})
    _net_uitgezet(c)

    besluit = c.evaluate_battery_cooling()

    assert besluit["actie"] == "aan", besluit["reden"]
    assert "wachten om pendelen" not in besluit["reden"]
