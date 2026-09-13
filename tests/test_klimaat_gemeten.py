"""De gemeten woonkamertemperatuur naast de projectie (v4.9).

Gemeld met een schermafdruk van "Woonkamertemperatuur per uur":

    Uur    Snel      Betrouwbaar   Buiten    Basis   Metingen
    10:00  21.0 °C   21.0 °C       14.6 °C   exact   20

Wat er staat is wat de projectie VOORSPELT. Wat er niet staat is wat de
thermometer aanwees. Zonder die kolom is de projectie niet te
beoordelen: je kunt niet zien of 21,0 °C om 10:00 ook 21,0 °C was.

De projectie loopt vooruit én terug - de uren tot nu zijn verleden en
daarvan bestaat de meting. Die wordt nu per uur bewaard en in het
traject gezet, met de afwijking erbij. Daarmee is het een leerbron in
plaats van een tabel, en kan de klimaatmodule net als de andere
modules zeggen hoe goed hij is.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def _meet(c, hass, temp, wanneer):
    c.config = dict(c.config or {})
    c.config["living_room_temperature_sensor_entity"] = "sensor.woonkamer"
    hass.states.set("sensor.woonkamer", str(temp), {"unit_of_measurement": "°C"})
    c._meet_woonkamertemperatuur(wanneer)


def test_de_meting_wordt_per_uur_bewaard(make_coordinator, hass):
    c = make_coordinator({})
    c.woonkamertemp_gemeten_per_uur = {}

    _meet(c, hass, 21.0, NU)
    _meet(c, hass, 21.4, NU + timedelta(minutes=20))
    _meet(c, hass, 22.0, NU + timedelta(hours=1))

    assert c.woonkamertemp_gemeten_per_uur["2026-09-10T12"] == 21.2
    assert c.woonkamertemp_gemeten_per_uur["2026-09-10T13"] == 22.0


def test_de_mediaan_van_het_uur_wint(make_coordinator, hass):
    """Een deur die opengaat mag het uur niet bepalen."""
    c = make_coordinator({})
    c.woonkamertemp_gemeten_per_uur = {}
    for i, t in enumerate([21.0, 21.1, 17.0, 21.0, 21.2]):
        _meet(c, hass, t, NU + timedelta(minutes=2 * i))

    # mediaan van 17,0 / 21,0 / 21,0 / 21,1 / 21,2
    assert c.woonkamertemp_gemeten_per_uur["2026-09-10T12"] == 21.0


def test_het_traject_draagt_de_meting_en_de_afwijking(make_coordinator, hass):
    c = make_coordinator({})
    c.woonkamertemp_gemeten_per_uur = {"2026-09-10T12": 20.4}
    traject = [
        {"tijd": NU.isoformat(), "kort_termijn_temp_c": 21.0, "betrouwbaar_temp_c": 21.0},
        {"tijd": (NU + timedelta(hours=1)).isoformat(), "kort_termijn_temp_c": 21.1,
         "betrouwbaar_temp_c": 21.1},
    ]

    verrijkt = c._traject_met_metingen(traject)

    assert verrijkt[0]["gemeten_temp_c"] == 20.4
    assert verrijkt[0]["afwijking_c"] == pytest.approx(0.6, abs=0.01)
    assert verrijkt[1]["gemeten_temp_c"] is None
    assert verrijkt[1]["afwijking_c"] is None


def test_de_projectie_krijgt_een_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    c.woonkamertemp_gemeten_per_uur = {
        f"2026-09-10T{u:02d}": 20.0 + u * 0.1 for u in range(8)
    }
    c.climate_forecast_trajectory = [
        {"tijd": f"2026-09-10T{u:02d}:00:00+00:00", "kort_termijn_temp_c": 20.0 + u * 0.1 + 0.3,
         "betrouwbaar_temp_c": 20.0 + u * 0.1}
        for u in range(8)
    ]

    uit = c.get_klimaat_projectie_kwaliteit()

    assert uit["beschikbaar"] is True
    assert uit["uren"] == 8
    assert uit["gemiddelde_afwijking_c"] == pytest.approx(0.3, abs=0.05)
    assert "0.3" in uit["oordeel"] or "betrouwbaar" in uit["oordeel"].lower()


def test_te_weinig_uren_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    c.woonkamertemp_gemeten_per_uur = {"2026-09-10T12": 20.4}
    c.climate_forecast_trajectory = [
        {"tijd": NU.isoformat(), "kort_termijn_temp_c": 21.0, "betrouwbaar_temp_c": 21.0}
    ]

    assert c.get_klimaat_projectie_kwaliteit()["beschikbaar"] is False
