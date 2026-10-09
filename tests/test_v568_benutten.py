"""v5.68: wat het EMS leert, ook gebruiken (akkoord Ruud 09-10).

1. Het temperatuurmodel in de nachtreserve op koude nachten.
2. De bewolking uit het weerensemble (gewogen, onbetrouwbare bronnen
   geweerd) in plaats van de kale mediaan van KNMI en OpenWeatherMap.
"""
from datetime import datetime, timedelta, timezone

NU = datetime(2026, 10, 9, 22, 0, tzinfo=timezone.utc)
TOT = NU + timedelta(hours=8)


def _coord(make_coordinator, model_kw, profiel_kwh, buiten=2.0):
    c = make_coordinator({})
    c._climate_cached_forecast = [(NU + timedelta(hours=i), buiten) for i in range(9)]
    c.climate_forecast_bias_history = []
    c._predict_temp_consumption_kw = lambda t: model_kw
    c._estimate_consumption_kwh_for_period = lambda a, b: profiel_kwh
    return c


def test_koude_nacht_tilt_de_reserve(make_coordinator):
    c = _coord(make_coordinator, 0.5, 3.0)
    uit = c._temperatuur_extra_kwh(NU, TOT)
    assert uit["extra_kwh"] == 1.0 and uit["model_kw"] == 0.5


def test_nooit_lager_dan_het_profiel(make_coordinator):
    assert _coord(make_coordinator, 0.2, 3.0)._temperatuur_extra_kwh(NU, TOT)["extra_kwh"] == 0.0


def test_geen_bruikbaar_model_geen_extra(make_coordinator):
    assert _coord(make_coordinator, None, 3.0)._temperatuur_extra_kwh(NU, TOT)["extra_kwh"] == 0.0


def test_ochtendverwarming_telt_niet_dubbel(make_coordinator):
    c = _coord(make_coordinator, 0.5, 3.0)
    assert c._temperatuur_extra_kwh(NU, TOT, 0.6)["extra_kwh"] == 0.4


def test_bewolking_uit_het_ensemble(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {}, knmi_weather_entity="weather.k", openweathermap_weather_entity="weather.o")
    hass.states.set("weather.k", "cloudy", {"cloud_coverage": 100})
    hass.states.set("weather.o", "sunny", {"cloud_coverage": 20})
    c.weather_ensemble_cloud_cover_percent = None
    assert c._weather_cloud_cover_percent() == 60.0
    c.weather_ensemble_cloud_cover_percent = 95.0
    assert c._weather_cloud_cover_percent() == 95.0
