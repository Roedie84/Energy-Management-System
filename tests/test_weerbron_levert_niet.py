"""Een ingestelde weerbron die geen bewolking levert, viel stil af
(v5.12).

Gevraagd: *"Kloppen alle sensoren nog met de EMS-integratie?"* In de
export van 21 september 14:18:

    weerbron_keuze:  gebruikt: ["weather.openweathermap"]   geweerd: []

`weather.forecast_thuis` was uit het ensemble verdwenen - niet geweerd,
gewoon weg. Tussen 18 september 11:15 (nog twee bronnen) en 21 september
06:53 (één bron).

En de configuratiecontrole noemde hem IN ORDE:

    knmi_weather_entity   weather.forecast_thuis   waarde=partlycloudy   in_orde

Hij bestaat, hij heeft een toestand. Maar de integratie gebruikt hem voor
zijn `cloud_coverage`-attribuut, en dat levert hij niet meer. De controle
keek of een entiteit bestaat, niet of hij levert waarvoor hij is
ingesteld - de tekst-tegen-gedrag-les, nu op de configuratie.

In het verzamelen stond het stil:

    cloud_pct = state.attributes.get("cloud_coverage")
    if cloud_pct is None:
        continue

Geen spoor van waarom een bron niet meedeed. Zo verdween een van twee
weerbronnen drie dagen lang zonder dat iemand het zag - het ensemble was
er stilzwijgend een eenmansensemble van geworden.

Dit waarschuwde ik al eerder: *"levert een bron het ooit niet meer, dan
verdwijnt hij stilzwijgend uit sources_used zonder dat er iets over wordt
gezegd."* Nu gebeurde het.
"""
from datetime import datetime, timezone

import pytest


def _bron(hass, entity_id, state="partlycloudy", **attrs):
    hass.states.set(entity_id, state, attrs)


def test_de_configuratiecontrole_ziet_een_bron_zonder_bewolking(make_coordinator, hass):
    """Het gemeten geval: bestaat, heeft een toestand, levert geen
    bewolking."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["knmi_weather_entity"] = "weather.forecast_thuis"
    _bron(hass, "weather.forecast_thuis", "partlycloudy", temperature=18.0)

    regels = c.get_configuratiecontrole()["entiteiten"]
    regel = next(r for r in regels if r["entiteit"] == "weather.forecast_thuis")

    assert regel["oordeel"] == "levert_niet"
    assert "cloud_coverage" in regel["uitleg"]


def test_een_bron_met_bewolking_is_in_orde(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["openweathermap_weather_entity"] = "weather.openweathermap"
    _bron(hass, "weather.openweathermap", "cloudy", cloud_coverage=83)

    regels = c.get_configuratiecontrole()["entiteiten"]
    regel = next(r for r in regels if r["entiteit"] == "weather.openweathermap")

    assert regel["oordeel"] == "in_orde"


def test_levert_niet_telt_als_kapot(make_coordinator, hass):
    """Anders staat hij bij "in orde" en ziet niemand hem - precies wat er
    drie dagen gebeurde."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["knmi_weather_entity"] = "weather.forecast_thuis"
    _bron(hass, "weather.forecast_thuis", "partlycloudy")

    assert c.get_configuratiecontrole()["aantal_stuk"] >= 1


def test_het_verzamelen_legt_vast_waarom_een_bron_niet_meedoet(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["knmi_weather_entity"] = "weather.forecast_thuis"
    c.config["openweathermap_weather_entity"] = "weather.openweathermap"
    _bron(hass, "weather.forecast_thuis", "partlycloudy")
    _bron(hass, "weather.openweathermap", "cloudy", cloud_coverage=83)

    c._update_weather_ensemble_check(datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc))
    levering = c.get_weerbron_levering()

    assert levering["bronnen"]["weather.forecast_thuis"] == "geen_cloud_coverage"
    assert levering["bronnen"]["weather.openweathermap"] == "levert"
    assert levering["aantal_leverend"] == 1


def test_een_verdwenen_bron_heet_zo(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["knmi_weather_entity"] = "weather.bestaat_niet"
    c.config["openweathermap_weather_entity"] = "weather.openweathermap"
    _bron(hass, "weather.openweathermap", "cloudy", cloud_coverage=50)

    c._update_weather_ensemble_check(datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc))

    assert c.get_weerbron_levering()["bronnen"]["weather.bestaat_niet"] == "bestaat_niet"


def test_de_levering_staat_in_de_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "get_weerbron_levering" in bron
