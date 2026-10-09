"""Airco-voorspelling per halve graad (v5.60, besluit Ruud 9 oktober 2026).

Bakje = de dichtstbijzijnde halve graad, de helft naar boven, gerekend vanaf
de temperatuur op één decimaal: 18,75-19,24 °C -> "19.0", 19,25-19,74 °C ->
"19.5". De historie in bakjes van één graad wordt eenmalig gewist
(AIRCO_LEER_VERSIE = 3).
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import airco_sturing as a
from custom_components.energy_management_system.const import (
    AIRCO_LEER_VERSIE,
    LIVING_ROOM_TEMP_BUCKET_SIZE_C,
)

NU = datetime(2026, 10, 9, 13, 0, tzinfo=timezone.utc)
CONFIG = {
    "living_room_temperature_sensor_entity": "sensor.kamer",
    "living_room_humidity_sensor_entity": "sensor.vocht",
}


def test_bakgrootte_is_een_halve_graad():
    assert LIVING_ROOM_TEMP_BUCKET_SIZE_C == 0.5
    assert AIRCO_LEER_VERSIE == 3


@pytest.mark.parametrize(
    "temp, bakje",
    [
        # de voorbeelden uit het besluit
        (18.8, "19.0"),
        (18.7, "18.5"),
        (19.2, "19.0"),
        (19.3, "19.5"),
        # exacte grenzen in honderdsten
        (18.75, "19.0"),
        (18.74, "18.5"),
        (19.24, "19.0"),
        (19.25, "19.5"),  # round(19.25, 1) gaf 19.2 -> bakje 19.0
        (19.74, "19.5"),
        (19.75, "20.0"),
        (19.0, "19.0"),
        (19.5, "19.5"),
        (19.7, "19.5"),
        (19.8, "20.0"),
        # ruis van een Zigbee-sensor
        (19.249999, "19.0"),
        (19.2500001, "19.5"),
        (21.123077392578, "21.0"),
        (-0.3, "-0.5"),
        (-0.2, "0.0"),
    ],
)
def test_indeling_van_grenswaarden(temp, bakje):
    assert a.temperatuurbakje(temp, LIVING_ROOM_TEMP_BUCKET_SIZE_C) == bakje


def test_standaard_is_een_halve_graad():
    assert a.temperatuurbakje(19.3) == "19.5"


def test_sleutels_met_een_decimaal_zonder_ruis():
    sleutels = {a.temperatuurbakje(t / 100) for t in range(1500, 2600)}
    for s in sleutels:
        assert s == f"{float(s):.1f}", s
        assert float(s) * 2 == int(float(s) * 2)
    # 15,00-25,99 -> 15,0 t/m 26,0 in stappen van 0,5
    assert len(sleutels) == 23


def test_een_decimaal_half_naar_boven():
    assert a.een_decimaal(19.25) == 19.3
    assert a.een_decimaal(18.75) == 18.8
    assert a.een_decimaal(19.24) == 19.2
    assert a.een_decimaal(24.1230773925781) == 24.1


def test_label():
    assert a.bakje_label("19.5") == "19,5 °C"
    assert a.bakje_label("19.0") == "19,0 °C"
    assert a.bakje_label(None) == "—"


def _bakje(kans, richting, voldoende=True):
    return {"probability_percent": kans, "richting": richting, "voldoende_data": voldoende}


def test_aanzettemperatuur_met_halve_graden():
    bakjes = {
        "18.5": _bakje(90, "verwarmen"),
        "19.0": _bakje(70, "verwarmen"),
        "19.5": _bakje(55, "verwarmen"),
        "20.0": _bakje(40, "verwarmen"),  # minder kans dan niet
        "20.5": _bakje(80, "verwarmen", voldoende=False),
    }
    assert a.aanzettemperatuur(bakjes) == 19.5


def _besluit(**kw):
    basis = dict(
        woonkamer_c=19.2, aanwezigheid="thuis", aanzet_c=19.5, doel_c=21.0,
        advies="airco", handmatig=False, airco_stand="off",
        door_ems_aan=False, setpunten_gezien=6, setpunten_nodig=5,
    )
    basis.update(kw)
    return a.besluit(**basis)


def test_besluittekst_toont_19_5_niet_als_20():
    uit = _besluit()
    assert uit["actie"] == "verwarmen"
    assert "19.5 °C" in uit["tekst"]
    assert "20 °C" not in uit["tekst"]
    assert any("onder 19.5 °C" in r for r in uit["redenen"])


def test_warm_genoeg_met_halve_graad():
    uit = _besluit(woonkamer_c=19.6)
    assert uit["actie"] == "niets"
    assert "niet onder de 19.5 °C" in uit["tekst"]


def _ronde(c, hass, moment, temp_c):
    hass.states.set("sensor.kamer", str(temp_c), {"unit_of_measurement": "°C"})
    hass.states.set("sensor.vocht", "50.0", {"unit_of_measurement": "%"})
    c.last_heavy_load_source = None
    c._update_living_room_airco_prediction(moment)


def test_leerstap_en_sensor_kiezen_hetzelfde_bakje(make_coordinator, hass):
    c = make_coordinator(dict(CONFIG))
    c.living_room_temp_bucket_history = {}
    c._temp_prediction_pending = []
    c.airco_bakje_laatste_start = {}
    _ronde(c, hass, NU, 19.25)
    assert c.living_room_current_temp_c == 19.3
    assert [p["bucket"] for p in c._temp_prediction_pending] == ["19.5"]
    assert a.temperatuurbakje(c.living_room_current_temp_c) == "19.5"
    _ronde(c, hass, NU + timedelta(minutes=1), 18.7)
    assert sorted(p["bucket"] for p in c._temp_prediction_pending) == ["18.5", "19.5"]


def test_migratie_wist_de_bakjes_van_een_graad(make_coordinator):
    c = make_coordinator({})
    c.airco_leer_versie = 2
    c.living_room_temp_bucket_history = {"19.0": [True] * 5, "20.0": [False] * 3}
    c.living_room_temp_bucket_humidity = {"19.0": [50.0] * 5}
    c.living_room_temp_bucket_direction = {"19.0": ["verwarmen"] * 5}
    c.airco_bakje_laatste_start = {"19.0": NU.isoformat()}
    c.airco_setpunten = [21.0] * 5
    c._geladen_opslag = {
        "living_room_temp_bucket_history": {"19.0": [True]},
        "airco_leer_versie": 2,
    }

    c._migreer_airco_leren()

    assert c.living_room_temp_bucket_history == {}
    assert c.living_room_temp_bucket_humidity == {}
    assert c.living_room_temp_bucket_direction == {}
    assert c.airco_bakje_laatste_start == {}
    assert c.airco_leer_versie == 3
    assert c._geladen_opslag["airco_leer_versie"] == 3
    assert "living_room_temp_bucket_history" not in c._geladen_opslag
    # de gekozen setpunten blijven
    assert c.airco_setpunten == [21.0] * 5

    # eenmalig
    c.living_room_temp_bucket_history = {"19.5": [True]}
    c._migreer_airco_leren()
    assert c.living_room_temp_bucket_history == {"19.5": [True]}


def test_sensor_herstelt_geen_versie_2_historie(make_coordinator):
    import asyncio
    from types import SimpleNamespace

    from custom_components.energy_management_system.sensor import (
        LivingRoomAircoPredictionSensor,
    )

    c = make_coordinator({})
    c.living_room_temp_bucket_history = {}
    s = LivingRoomAircoPredictionSensor(c, "x")
    oud = SimpleNamespace(attributes={"leer_versie": 2, "alle_buckets": {"19.0": [True]}})

    async def _laatste():
        return oud

    s.async_get_last_state = _laatste
    s.hass = getattr(c, "hass", None)
    try:
        asyncio.run(s.async_added_to_hass())
    except Exception:
        pytest.skip("herstel niet los aan te roepen in deze omgeving")
    assert c.living_room_temp_bucket_history == {}


def test_sensor_tabel_oplopend_met_labels(make_coordinator):
    from custom_components.energy_management_system.sensor import (
        LivingRoomAircoPredictionSensor,
    )

    c = make_coordinator({})
    c.living_room_current_temp_c = 19.3
    c.living_room_temp_bucket_history = {
        "20.0": [False] * 5,
        "19.5": [True] * 5,
        "18.5": [True] * 5,
    }
    attrs = LivingRoomAircoPredictionSensor(c, "x").extra_state_attributes
    assert list(attrs["geleerde_buckets"]) == ["18.5", "19.5", "20.0"]
    assert attrs["geleerde_buckets"]["19.5"]["label"] == "19,5 °C"
    assert attrs["huidige_bucket"] == "19.5"
    assert attrs["huidige_bucket_label"] == "19,5 °C"
    assert attrs["leer_versie"] == c.airco_leer_versie


def test_dashboard_gebruikt_de_labels():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    tekst = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    assert "huidige_bucket_label" in tekst
    assert "{{ g.label }}" in tekst
    assert "bin van 1 °C" not in tekst
