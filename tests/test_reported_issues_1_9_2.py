"""Vier gemelde punten (v1.9.2).

1. "zelfconsumptie klopt niet -200" - stond op -244,6%
2. Melding "Lage accustand vlak voor de avondpiek" om 05:47, terwijl het
   duurste blok om 07:15 begon
3. "Was geen regeneratie van die zie ruim >10 liter zijn" - 3,1 L om
   00:28 werd als regeneratie aangemerkt
4. Weerbronnen: de meting spreekt de indruk tegen
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    WATER_SOFTENER_MIN_LITERS,
)

NOW = datetime(2026, 8, 8, 5, 47, tzinfo=timezone.utc)


# --- 1. zelfconsumptie -----------------------------------------------


def test_self_consumption_is_never_negative(make_coordinator, hass):
    """Een aandeel ligt per definitie tussen 0 en 100%. De export via P1
    telt ook wat de ACCU teruglevert - energie die gisteren is geladen -
    en zodra die de dagopwek overstijgt werd de uitkomst negatief."""
    c = make_coordinator({})
    c.pv_production_today_kwh = 2.0
    c.pv_export_today_kwh = 6.9   # deels uit de accu

    assert c.self_consumption_ratio_percent == 0.0


def test_normal_self_consumption_is_unchanged(make_coordinator, hass):
    """De correctie mag het gewone geval niet raken."""
    c = make_coordinator({})
    c.pv_production_today_kwh = 10.0
    c.pv_export_today_kwh = 4.0

    assert c.self_consumption_ratio_percent == 60.0


def test_no_production_gives_no_ratio(make_coordinator, hass):
    c = make_coordinator({})
    c.pv_production_today_kwh = 0.0

    assert c.self_consumption_ratio_percent is None


def test_full_self_consumption(make_coordinator, hass):
    c = make_coordinator({})
    c.pv_production_today_kwh = 8.0
    c.pv_export_today_kwh = 0.0

    assert c.self_consumption_ratio_percent == 100.0


# --- 2. dagdeel in de melding ----------------------------------------


def test_the_time_of_day_is_derived(make_coordinator, hass):
    """"Avondpiek" om 07:15 is gewoon onjuist."""
    c = make_coordinator({})

    assert c._dagdeel(datetime(2026, 8, 8, 3, 0)) == "nacht"
    assert c._dagdeel(datetime(2026, 8, 8, 7, 15)) == "ochtend"
    assert c._dagdeel(datetime(2026, 8, 8, 14, 0)) == "middag"
    assert c._dagdeel(datetime(2026, 8, 8, 20, 15)) == "avond"


def test_the_notification_uses_the_real_time_of_day(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_APPLIANCE_NOTIFY_SERVICE,
    )

    c = make_coordinator({CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon"})
    # v2.7.0: de melding komt alleen nog als het blok er WERKELIJK
    # uitspringt en er nog tijd is om bij te laden. Zonder prijzen valt
    # dat niet te beoordelen, dus hier een dag met een echte piek: 30 ct
    # overdag, 45 ct in het blok van 07:15.
    from custom_components.energy_management_system.const import (
        PRICE_SCALE_FACTOR,
    )

    _prijzen = [
        (
            NOW + timedelta(minutes=15 * i),
            None,
            (0.45 if 5 <= i <= 9 else 0.30) * PRICE_SCALE_FACTOR,
        )
        for i in range(40)
    ]
    c._get_forecast_entries = lambda *a, **k: _prijzen
    c.set_notification_enabled("low_soc_before_peak", True)
    c.last_soc_percent = 23.0
    c.accustand_procent = lambda: 23.0
    c.last_discharge_start = NOW + timedelta(hours=1, minutes=28)  # 07:15

    from custom_components.energy_management_system import coordinator as mod

    origineel = mod.dt_util.now
    try:
        mod.dt_util.now = lambda: NOW
        c._evaluate_new_notifications(NOW)
    finally:
        mod.dt_util.now = origineel

    titel = next(
        m["titel"] for m in c.notification_history if "accustand" in m["titel"]
    )
    assert "ochtendpiek" in titel
    assert "avondpiek" not in titel


# --- 3. waterontharder -----------------------------------------------


def test_a_small_night_session_is_not_a_regeneration(make_coordinator, hass):
    """3,1 liter om 00:28 is doorspoelen of een glas water, geen
    regeneratie."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("WATER_SOFTENER_NIGHT_WINDOW_START_HOUR\n")
    # v1.18.0: niet op een vast aantal tekens zoeken - het
    # toelichtingsblok groeit mee met elke correctie en schoof de
    # constante er twee keer uit. Zoeken tot het einde van de
    # if-voorwaarde is stabiel.
    einde = bron.index("):", start)
    blok = bron[start:einde]

    assert "WATER_SOFTENER_MIN_LITERS" in blok
    assert "WATER_SOFTENER_MIN_DURATION_MINUTES" in blok


def test_the_threshold_matches_a_real_regeneration():
    """v1.18.0, gemeld: "Ik weet zeker dat de waterontharder nog niet
    heeft geregenereerd, misschien de drempel anders leggen?"

    Tien liter haalt een wc-spoeling plus een kraan al. Een echte
    regeneratie spoelt de harslaag met pekel en spoelt na: 50 tot 200
    liter over 20 tot 60 minuten.
    """
    from custom_components.energy_management_system.const import (
        WATER_SOFTENER_MIN_DURATION_MINUTES,
    )

    assert WATER_SOFTENER_MIN_LITERS >= 40.0
    assert WATER_SOFTENER_MIN_DURATION_MINUTES >= 15.0


# --- 4. weerbronnen --------------------------------------------------


def test_comparable_sources_are_reported_on_the_weather_page(
    make_coordinator, hass
):
    """v1.67.0: deze melding stond op de LANDINGSPAGINA, en is daar
    weggehaald.

    Gemeld: "Deze zie ik altijd op de landingspagina, nu niet meer nodig
    toch?" In v1.9.2 kwam hij erbij om een verkeerde conclusie voor te
    zijn - stilte was dubbelzinnig. Maar die boodschap heb je één keer
    nodig, op het moment dat je die vraag hebt. Permanent wordt hij
    behang.

    De cijfers blijven, alleen op de weerpagina.
    """
    c = make_coordinator({})
    c.weather_source_agreement = {
        "weather.forecast_thuis": [True] * 149 + [False] * 31,
        "weather.openweathermap": [True] * 143 + [False] * 37,
    }

    landing = [
        p for p in c.get_diagnostic_summary()["informatief"] if "Weerbronnen" in p
    ]
    vergelijking = c.get_weather_source_reliability()["_vergelijking"]

    assert landing == []
    assert "vergelijkbaar" in vergelijking["advies"]
    assert vergelijking["verschil_procentpunt"] < 20


def test_a_real_difference_still_advises(make_coordinator, hass):
    c = make_coordinator({})
    c.weather_source_agreement = {
        "weather.forecast_thuis": [False] * 150 + [True] * 30,
        "weather.openweathermap": [True] * 170 + [False] * 10,
    }

    melding = next(
        p
        for p in c.get_diagnostic_summary()["informatief"]
        if "Weerbronnen" in p
    )

    assert "structureel" in melding
    assert "uit de configuratie" in melding
