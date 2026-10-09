"""De airco-voorspelling leert per uur, niet per ronde (v5.58).

Tot v5.57 startte elke coordinator-ronde een nieuwe waarneming. "De laatste
20" in een bakje waren daardoor ~20 opeenvolgende minuten van één middag,
geen 20 losse momenten - en de luchtvochtigheid per bakje groeide ook per
ronde. Nu per bakje hooguit één start per uur, en de oude historie wordt
eenmalig gewist (AIRCO_LEER_VERSIE).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.airco_sturing import (
    temperatuurbakje,
)
from custom_components.energy_management_system.const import (
    AIRCO_LEER_VERSIE,
    AIRCO_PREDICTION_LOOKAHEAD_MINUTES,
)

NU = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
CONFIG = {
    "living_room_temperature_sensor_entity": "sensor.kamer",
    "living_room_humidity_sensor_entity": "sensor.vocht",
}


def _ronde(c, hass, moment, temp_c, airco_aan=False, vocht=50.0):
    hass.states.set("sensor.kamer", str(temp_c), {"unit_of_measurement": "°C"})
    hass.states.set("sensor.vocht", str(vocht), {"unit_of_measurement": "%"})
    c.last_heavy_load_source = "airco" if airco_aan else None
    c._update_living_room_airco_prediction(moment)


def _verse(make_coordinator):
    c = make_coordinator(dict(CONFIG))
    c.living_room_temp_bucket_history = {}
    c.living_room_temp_bucket_humidity = {}
    c._temp_prediction_pending = []
    c.airco_bakje_laatste_start = {}
    return c


def test_per_bakje_hooguit_een_start_per_uur(make_coordinator, hass):
    c = _verse(make_coordinator)
    # twee uur lang elke minuut 21 °C, airco uit
    for m in range(0, 121):
        _ronde(c, hass, NU + timedelta(minutes=m), 21.0)
    # starts op 0, 60 en 120 min; de eerste twee zijn afgesloten
    assert c.living_room_temp_bucket_history["21.0"] == [False, False]
    assert len(c._temp_prediction_pending) == 1
    # luchtvochtigheid één keer per waarneming, niet 121 keer
    assert len(c.living_room_temp_bucket_humidity["21.0"]) == 3


def test_geen_tweede_start_binnen_het_uur(make_coordinator, hass):
    c = _verse(make_coordinator)
    _ronde(c, hass, NU, 21.0)
    _ronde(c, hass, NU + timedelta(minutes=AIRCO_PREDICTION_LOOKAHEAD_MINUTES - 1), 21.0)
    assert [p["bucket"] for p in c._temp_prediction_pending] == ["21.0"]


def test_meerdere_bakjes_tegelijk(make_coordinator, hass):
    """Een ander bakje start meteen: de uurgrens geldt per bakje."""
    c = _verse(make_coordinator)
    _ronde(c, hass, NU, 22.0)
    _ronde(c, hass, NU + timedelta(minutes=5), 21.0)
    _ronde(c, hass, NU + timedelta(minutes=10), 22.0)
    _ronde(c, hass, NU + timedelta(minutes=15), 21.0)
    assert sorted(p["bucket"] for p in c._temp_prediction_pending) == ["21.0", "22.0"]


def test_afronding_half_naar_boven():
    assert temperatuurbakje(18.8) == "19.0"
    assert temperatuurbakje(18.4) == "18.0"
    assert temperatuurbakje(18.5) == "19.0"  # Python's round(18.5) gaf 18
    assert temperatuurbakje(19.5) == "20.0"
    assert temperatuurbakje(18.46) == "19.0"  # getoond als 18,5


def test_afronding_in_de_leerstap(make_coordinator, hass):
    c = _verse(make_coordinator)
    _ronde(c, hass, NU, 18.8)
    _ronde(c, hass, NU + timedelta(minutes=1), 18.4)
    assert sorted(p["bucket"] for p in c._temp_prediction_pending) == ["18.0", "19.0"]


def test_airco_al_aan_geen_start(make_coordinator, hass):
    """De v5.13-regel blijft: draait de airco al, dan geen waarneming."""
    c = _verse(make_coordinator)
    _ronde(c, hass, NU, 21.0, airco_aan=True)
    assert c._temp_prediction_pending == []
    assert c.airco_bakje_laatste_start == {}


def test_aan_binnen_het_uur_telt_nog_steeds(make_coordinator, hass):
    c = _verse(make_coordinator)
    _ronde(c, hass, NU, 18.0)
    _ronde(c, hass, NU + timedelta(minutes=20), 18.0, airco_aan=True)
    _ronde(c, hass, NU + timedelta(minutes=65), 20.0, airco_aan=True)
    assert c.living_room_temp_bucket_history["18.0"] == [True]


def test_migratie_wist_de_per_ronde_historie(make_coordinator, hass):
    c = make_coordinator({})
    c.airco_leer_versie = None
    c.living_room_temp_bucket_history = {"21.0": [False] * 20}
    c.living_room_temp_bucket_humidity = {"21.0": [50.0] * 20}
    c.living_room_temp_bucket_direction = {"21.0": ["verwarmen"]}
    c._geladen_opslag = {"living_room_temp_bucket_history": {"21.0": [True]}}

    c._migreer_airco_leren()

    assert c.living_room_temp_bucket_history == {}
    assert c.living_room_temp_bucket_humidity == {}
    assert c.living_room_temp_bucket_direction == {}
    assert c.airco_leer_versie == AIRCO_LEER_VERSIE
    assert "living_room_temp_bucket_history" not in c._geladen_opslag

    # eenmalig: wat daarna is geleerd blijft staan
    c.living_room_temp_bucket_history = {"21.0": [True]}
    c._migreer_airco_leren()
    assert c.living_room_temp_bucket_history == {"21.0": [True]}


def test_migratie_bij_een_herstart(make_coordinator, hass):
    bron = make_coordinator({})
    bron.airco_leer_versie = None
    bron.living_room_temp_bucket_history = {"21.0": [False] * 20}
    asyncio.run(bron.async_save_persisted_state_now())

    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())
    assert verse.living_room_temp_bucket_history == {}
    assert verse.airco_leer_versie == AIRCO_LEER_VERSIE

    # en een tweede herstart houdt wat er nieuw is geleerd
    verse.living_room_temp_bucket_history = {"19.0": [True]}
    verse.airco_bakje_laatste_start = {"19.0": NU.isoformat()}
    asyncio.run(verse.async_save_persisted_state_now())
    derde = make_coordinator({})
    asyncio.run(derde.async_load_persisted_state())
    assert derde.living_room_temp_bucket_history == {"19.0": [True]}
    assert derde.airco_bakje_laatste_start == {"19.0": NU.isoformat()}


def test_sensor_herstelt_geen_oude_historie():
    """De sensor zette de bakjes terug uit zijn attributen; zonder
    leerversie zou de gewiste historie zo terugkomen."""
    import inspect

    from custom_components.energy_management_system import sensor

    bron = inspect.getsource(sensor)
    assert 'last_state.attributes.get("leer_versie") != AIRCO_LEER_VERSIE' in bron
    assert '"leer_versie": self._coordinator.airco_leer_versie' in bron
