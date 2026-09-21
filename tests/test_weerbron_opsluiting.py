"""Een geweerde weerbron kwam nooit meer terug (v5.13).

In v5.12 schreef ik dat `weather.forecast_thuis` uit het ensemble viel
omdat hij geen `cloud_coverage` meer leverde. De eerste export met v5.12
- met de nieuwe `weerbron_levering` - liet zien dat dat niet klopte:

    weerbron_levering:  forecast_thuis levert,  openweathermap levert
    sources_used:       alleen openweathermap

Hij leverde wél. De poort van v5.4 weerde hem. Twee fouten, allebei van
mij, uit v5.3:

1. EEN GEWEERDE BRON WERD NOOIT MEER GEMETEN. De metingen werden NA de
   poort vastgelegd, en de overeenstemming werd bijgewerkt over die
   metingen. Een geweerde bron kreeg dus geen nieuwe waarnemingen meer -
   zijn score bevroor op de 58% van 18 september, terwijl de overgebleven
   bron gewoon doorleerde en zijn voorsprong zag groeien. Eén slechte
   meetperiode werd zo een permanente buitensluiting.

2. DE EXPORT VERBORG HET. Na het weren werd `weerbron_keuze` opnieuw
   berekend over de al gefilterde lijst. Met één bron over valt er niets
   te weren, dus zei de export altijd "geweerd: [], alle bronnen halen de
   grens". De echte beslissing werd weggegooid - en daardoor zocht ik in
   v5.12 op de verkeerde plek.

De `weerbron_levering` van v5.12 was dus nuttig, alleen niet om de reden
die ik noemde: hij liet zien dat de bron wél leverde.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 9, 21, 19, 15, tzinfo=timezone.utc)


def _twee_bronnen(c, hass, knmi=40.0, owm=45.0):
    c.config = dict(c.config or {})
    c.config["knmi_weather_entity"] = "weather.forecast_thuis"
    c.config["openweathermap_weather_entity"] = "weather.openweathermap"
    hass.states.set("weather.forecast_thuis", "partlycloudy", {"cloud_coverage": knmi})
    hass.states.set("weather.openweathermap", "cloudy", {"cloud_coverage": owm})


def test_de_export_toont_de_echte_weerbeslissing(make_coordinator, hass):
    """Het gemeten geval: een bron geweerd, en de export zei "geweerd: []"."""
    c = make_coordinator({})
    c.weather_source_agreement = {
        "weather.forecast_thuis": [True] * 58 + [False] * 142,
        "weather.openweathermap": [True] * 170 + [False] * 30,
    }

    c._weer_de_slechte_bronnen(
        ["weather.forecast_thuis", "weather.openweathermap"], [40.0, 45.0]
    )

    assert c.weerbron_keuze["geweerd"] == ["weather.forecast_thuis"]
    assert "weather.openweathermap" in c.weerbron_keuze["gebruikt"]


def test_een_geweerde_bron_wordt_nog_steeds_gemeten(make_coordinator, hass):
    """Anders bevriest zijn score en kan hij zich nooit terugverdienen."""
    c = make_coordinator({})
    _twee_bronnen(c, hass)
    c.weather_source_agreement = {
        "weather.forecast_thuis": [True] * 58 + [False] * 142,
        "weather.openweathermap": [True] * 170 + [False] * 30,
    }

    c._update_weather_ensemble_check(NU)

    # hij doet niet mee aan de ensemblewaarde...
    assert "weather.forecast_thuis" not in c.weather_ensemble_sources_used
    # ...maar zijn meting is er wel, zodat zijn overeenstemming doorleert
    assert "weather.forecast_thuis" in c.weather_ensemble_readings_alle


def test_de_overeenstemming_leert_door_voor_een_geweerde_bron(make_coordinator, hass):
    """Het GEDRAG, niet de tekst: krijgt een geweerde bron nog een nieuwe
    waarneming? De eerste versie van deze toets zocht de variabelenaam op
    de regel van de `for` - en viel om zodra die over twee regels liep.
    Precies de tekst-tegen-gedrag-fout waar dit hele bestand over gaat."""
    c = make_coordinator({})
    c.weather_ensemble_agreement_history = []
    c.weather_source_agreement = {
        "weather.forecast_thuis": [True] * 58,
        "weather.openweathermap": [True] * 170,
    }
    # alleen openweathermap mag meedoen, maar beide leveren
    c.weather_ensemble_readings = {"weather.openweathermap": 45.0}
    c.weather_ensemble_readings_alle = {
        "weather.forecast_thuis": 40.0,
        "weather.openweathermap": 45.0,
    }

    c._record_weather_ensemble_agreement(avg_cloud_pct=45.0, ratio=1.0)

    assert len(c.weather_source_agreement["weather.forecast_thuis"]) == 59


def test_een_bron_die_weer_goed_meet_komt_terug(make_coordinator, hass):
    """Waar het om gaat: de buitensluiting is niet meer permanent."""
    c = make_coordinator({})
    c.weather_source_agreement = {
        "weather.forecast_thuis": [True] * 180 + [False] * 20,
        "weather.openweathermap": [True] * 170 + [False] * 30,
    }

    c._weer_de_slechte_bronnen(
        ["weather.forecast_thuis", "weather.openweathermap"], [40.0, 45.0]
    )

    assert c.weerbron_keuze["geweerd"] == []
