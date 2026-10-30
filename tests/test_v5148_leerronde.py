"""Leerronde 30-10 (v5.148.0).

1. L-EMS-045: een weerbron die uit de configuratie is gehaald, telt niet
   meer mee in de betrouwbaarheid, de vergelijking en 'Nog niet bepaald'.
   Gemeten 29-10 15:45: OWM weggehaald, toch "Weerbron
   weather.openweathermap - 79,0 % van 200" als wacht.

2. Zonvoorspelling 'klopt hij nog met de panelen?': de tekst "elke dag -
   geen goede dag ertussen ... vervuiling, een uitgevallen streng" alleen
   als er echt geen goede dag tussen zit. Gemeld 30-10 00:00 met de reeks
   -26,1 / +3,2 / -12,9 / -16,7 / -47,0 %.
"""
from custom_components.energy_management_system.const import (
    CONF_KNMI_WEATHER_ENTITY,
    CONF_OPENWEATHERMAP_WEATHER_ENTITY,
    RELIABILITY_INSUFFICIENT,
    RELIABILITY_UNRELIABLE,
)

METNO = "weather.forecast_thuis"
OWM = "weather.openweathermap"


# --- 1. L-EMS-045 ---------------------------------------------------


def _met_reeksen(make_coordinator, config):
    c = make_coordinator(config)
    c.weather_source_agreement = {
        METNO: [True] * 178 + [False] * 22,
        OWM: [True] * 158 + [False] * 42,
    }
    return c


def test_weggehaalde_bron_staat_niet_meer_in_de_betrouwbaarheid(make_coordinator, hass):
    c = _met_reeksen(make_coordinator, {CONF_KNMI_WEATHER_ENTITY: METNO})

    rapport = c.get_weather_source_reliability()

    assert METNO in rapport
    assert OWM not in rapport
    # met één bron valt er niets te vergelijken
    assert "_vergelijking" not in rapport
    # de reeks zelf blijft bewaard: komt de bron terug, dan telt hij door
    assert len(c.weather_source_agreement[OWM]) == 200


def test_weggehaalde_bron_staat_niet_in_nog_niet_bepaald(make_coordinator, hass):
    c = _met_reeksen(make_coordinator, {CONF_KNMI_WEATHER_ENTITY: METNO})

    overzicht = c.get_reliability_overview()
    namen = str(overzicht)

    assert f"Weerbron {OWM}" not in namen
    assert f"Weerbron {METNO}" in namen


def test_beide_ingesteld_blijft_ongewijzigd(make_coordinator, hass):
    c = _met_reeksen(
        make_coordinator,
        {CONF_KNMI_WEATHER_ENTITY: METNO, CONF_OPENWEATHERMAP_WEATHER_ENTITY: OWM},
    )

    rapport = c.get_weather_source_reliability()

    assert {METNO, OWM} <= set(rapport)
    assert "_vergelijking" in rapport


# --- 2. zonvoorspelling: geen installatie-oordeel met een goede dag -----


class _Tracker:
    def __init__(self, afwijkingen, bias=None):
        self.deviation_history = list(afwijkingen)
        self.learned_bias_percent = bias
        self.pending_predicted_kwh = None
        self.learned_typical_forecast_kwh = None
        self.deviation_stdev_percent = 8.0


def test_de_reeks_van_30_10_wijst_de_installatie_niet_aan(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = _Tracker([-26.1, 3.2, -12.9, -16.7, -47.0])

    gezondheid = c.get_solar_forecast_health()

    assert gezondheid["status"] == RELIABILITY_INSUFFICIENT
    assert gezondheid["soort"] == "wisselend"
    assert "streng" not in gezondheid["reden"].split("past niet")[0]
    assert "geen goede dag ertussen" not in gezondheid["reden"]
    assert "1 binnen 10%" in gezondheid["reden"]


def test_geen_melding_bij_een_wisselende_reeks(make_coordinator, hass):
    """De melding solar_underperforming gaat alleen uit bij 'onbetrouwbaar'."""
    c = make_coordinator({})
    c.solar_tracker = _Tracker([-26.1, 3.2, -12.9, -16.7, -47.0])

    assert c.get_solar_forecast_health()["status"] != RELIABILITY_UNRELIABLE


def test_echte_verschuiving_zonder_goede_dag_blijft_gemeld(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = _Tracker([-18.0, -22.0, -16.0, -30.0, -19.0])

    gezondheid = c.get_solar_forecast_health()

    assert gezondheid["status"] == RELIABILITY_UNRELIABLE
    assert gezondheid["soort"] == "verschuiving"
    assert "streng" in gezondheid["reden"]
