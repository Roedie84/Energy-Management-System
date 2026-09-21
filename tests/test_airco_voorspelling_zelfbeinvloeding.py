"""De aircovoorspelling leerde van zijn eigen effect (v5.13).

Gevraagd, na de bewaking op de zonvoorspelling: *"Gaat dit misschien op
meerdere locaties in de integratie fout?"* - een voorspeller die leert van
iets wat hij zelf beïnvloedt.

De aircovoorspelling beantwoordt: "gaat de airco binnen een uur aan, bij
deze kamertemperatuur?" Elke ronde startte hij een nieuwe waarneming bij
de huidige temperatuur, en stond de airco al aan, dan kreeg die
waarneming meteen het label "aan":

    self._temp_prediction_pending.append({
        "bucket": bucket_key,                    # de temperatuur NU
        "airco_seen_active": airco_active_now,   # al aan -> meteen True
    })

Zet je aan bij 25 °C en koelt de airco naar 21 °C, dan vullen de bakjes
24, 23, 22 en 21 zich met "de airco ging aan". De voorspeller leert dat
je bij 21 °C aanzet - terwijl de airco die 21 °C zelf veroorzaakte. De
vraag "gaat hij aan?" bestaat niet meer zodra hij al aan staat.

In september zag je het niet: alle bakjes op 0%, de airco draaide niet.
Na een zomer had hij gezegd dat je bij 21 °C gaat koelen.

Nu start een waarneming alleen als de airco UIT staat. Een waarneming die
al liep, wordt nog steeds "aan" als de airco binnen het uur aangaat - dat
is het echte signaal.

Nagegaan en in orde: de klimaatprojectie heeft de aircostand in de
situatiesleutel, dus leert aan en uit apart. En de opgeslagen bakjes
bevatten geen enkele "aan" - opschonen hoeft niet.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)


def _kamer(c, hass, temp_c, airco_aan):
    c.config = dict(c.config or {})
    c.config["living_room_temperature_sensor_entity"] = "sensor.kamer"
    hass.states.set("sensor.kamer", str(temp_c), {"unit_of_measurement": "°C"})
    c.last_heavy_load_source = "airco" if airco_aan else None


def _ronde(c, hass, moment, temp_c, airco_aan):
    _kamer(c, hass, temp_c, airco_aan)
    c._update_living_room_airco_prediction(moment)


def test_terwijl_de_airco_draait_wordt_er_geen_aanzet_geleerd(make_coordinator, hass):
    """Het gemeten geval: de airco koelt van 25 naar 21 °C. Die lagere
    temperaturen horen NIET als "hier gaat hij aan" te worden geleerd."""
    from custom_components.energy_management_system.const import (
        AIRCO_PREDICTION_LOOKAHEAD_MINUTES,
    )

    c = make_coordinator({})
    c.living_room_temp_bucket_history = {}
    c._temp_prediction_pending = []

    # draait al, en koelt de kamer af
    moment = NU
    for temp in (24.0, 23.0, 22.0, 21.0):
        _ronde(c, hass, moment, temp, airco_aan=True)
        moment += timedelta(minutes=5)
    # ruim na de vooruitblik, zodat alle waarnemingen zijn afgesloten
    _ronde(c, hass, moment + timedelta(minutes=AIRCO_PREDICTION_LOOKAHEAD_MINUTES + 5), 21.0, airco_aan=False)

    geleerd_aan = {
        k: sum(1 for x in v if x)
        for k, v in c.living_room_temp_bucket_history.items()
    }
    assert geleerd_aan.get("21.0", 0) == 0
    assert geleerd_aan.get("22.0", 0) == 0


def test_de_echte_aanzettemperatuur_wordt_wel_geleerd(make_coordinator, hass):
    """Uit bij 25 °C, en binnen het uur aan: dat is het signaal."""
    from custom_components.energy_management_system.const import (
        AIRCO_PREDICTION_LOOKAHEAD_MINUTES,
    )

    c = make_coordinator({})
    c.living_room_temp_bucket_history = {}
    c._temp_prediction_pending = []

    _ronde(c, hass, NU, 25.0, airco_aan=False)
    _ronde(c, hass, NU + timedelta(minutes=10), 25.0, airco_aan=True)
    _ronde(
        c, hass,
        NU + timedelta(minutes=AIRCO_PREDICTION_LOOKAHEAD_MINUTES + 5),
        23.0, airco_aan=True,
    )

    assert any(c.living_room_temp_bucket_history.get("25.0", []))


def test_uit_blijven_telt_als_niet_aan(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        AIRCO_PREDICTION_LOOKAHEAD_MINUTES,
    )

    c = make_coordinator({})
    c.living_room_temp_bucket_history = {}
    c._temp_prediction_pending = []

    _ronde(c, hass, NU, 22.0, airco_aan=False)
    _ronde(
        c, hass,
        NU + timedelta(minutes=AIRCO_PREDICTION_LOOKAHEAD_MINUTES + 5),
        22.0, airco_aan=False,
    )

    assert c.living_room_temp_bucket_history.get("22.0") == [False]
