"""v5.63.1: open airco-waarnemingen overleven een herstart.

Gemeld 09-10: "vanmiddag is de airco bij 18,8 aangegaan" - en dat stond
nergens. Een waarneming wacht een uur of de airco aangaat; die wachtende
waarnemingen stonden alleen in het geheugen en verdwenen bij elke herstart.
"""
from datetime import datetime, timedelta, timezone

NU = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def _ronde(c, hass, moment, temp_c, airco_aan):
    c.config = dict(c.config or {})
    c.config["living_room_temperature_sensor_entity"] = "sensor.kamer"
    hass.states.set("sensor.kamer", str(temp_c), {"unit_of_measurement": "°C"})
    c.last_heavy_load_source = "airco" if airco_aan else None
    c._update_living_room_airco_prediction(moment)


def _herstart(oud, make_coordinator):
    """Nieuwe coordinator met alleen wat de opslag bewaart."""
    from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS

    nieuw = make_coordinator({})
    for veld in PERSISTED_PLAIN_FIELDS:
        if hasattr(oud, veld):
            setattr(nieuw, veld, getattr(oud, veld))
    nieuw._temp_prediction_pending = []
    nieuw._airco_waarnemingen_hersteld = False
    return nieuw


def test_veld_wordt_bewaard():
    from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS

    assert "airco_open_waarnemingen" in PERSISTED_PLAIN_FIELDS


def test_aanzetten_na_een_herstart_wordt_geleerd(make_coordinator, hass):
    c = make_coordinator({})
    c.living_room_temp_bucket_history = {}
    _ronde(c, hass, NU, 18.8, airco_aan=False)            # waarneming in bakje 19.0
    assert c.airco_open_waarnemingen and c.airco_open_waarnemingen[0]["bucket"] == "19.0"

    c2 = _herstart(c, make_coordinator)                     # herstart na 20 min
    _ronde(c2, hass, NU + timedelta(minutes=30), 18.8, airco_aan=True)   # airco gaat aan
    _ronde(c2, hass, NU + timedelta(minutes=65), 20.5, airco_aan=True)   # deadline voorbij
    assert c2.living_room_temp_bucket_history.get("19.0") == [True]


def test_gezien_voor_de_herstart_en_deadline_tijdens_herstart(make_coordinator, hass):
    c = make_coordinator({})
    c.living_room_temp_bucket_history = {}
    _ronde(c, hass, NU, 18.8, airco_aan=False)
    _ronde(c, hass, NU + timedelta(minutes=10), 18.8, airco_aan=True)
    c2 = _herstart(c, make_coordinator)
    _ronde(c2, hass, NU + timedelta(minutes=90), 21.0, airco_aan=True)
    assert c2.living_room_temp_bucket_history.get("19.0") == [True]


def test_niet_gezien_en_deadline_tijdens_herstart_vervalt(make_coordinator, hass):
    c = make_coordinator({})
    c.living_room_temp_bucket_history = {}
    _ronde(c, hass, NU, 18.8, airco_aan=False)
    c2 = _herstart(c, make_coordinator)
    _ronde(c2, hass, NU + timedelta(minutes=90), 18.8, airco_aan=False)
    # geen onterechte "niet aan": tijdens de herstart is niets te weten
    assert "19.0" not in c2.living_room_temp_bucket_history or c2.living_room_temp_bucket_history["19.0"] == []


def test_herstel_maar_een_keer(make_coordinator, hass):
    c = make_coordinator({})
    _ronde(c, hass, NU, 18.8, airco_aan=False)
    c2 = _herstart(c, make_coordinator)
    _ronde(c2, hass, NU + timedelta(minutes=5), 18.8, airco_aan=False)
    _ronde(c2, hass, NU + timedelta(minutes=6), 18.8, airco_aan=False)
    assert len([p for p in c2._temp_prediction_pending if p["bucket"] == "19.0"]) == 1
