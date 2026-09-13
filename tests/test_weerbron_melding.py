"""De melding noemt een gemiddelde dat er geen is (v3.93.2).

Gemeld:

    "Weerbronnen lopen 41 procentpunt uiteen over de bewolking
    (weather.forecast_thuis: 93%, weather.openweathermap: 52%). Het
    gemiddelde (52.0%) zegt dan weinig - controleer welke bron klopt met
    wat je buiten ziet."

Twee dingen kloppen niet, en ze wijzen dezelfde kant op.

1. 52,0 is geen gemiddelde. Van 93 en 52 is dat 72,5. Uit de export van
   dezelfde dag:

       weather_ensemble_readings        thuis 82,0   owm 44,0
       weather_ensemble_cloud_cover     44,0
       weather_ensemble_chosen_source   weather.openweathermap

   Bij een verschil van 25 procentpunt of meer middelt de code niet
   meer, maar KIEST de bron die het aantoonbaar vaker bij het rechte
   eind heeft. Dat is precies de bedoeling - alleen heet het in de
   melding nog steeds "het gemiddelde".

2. "Controleer welke bron klopt met wat je buiten ziet" geeft het werk
   terug aan de gebruiker, terwijl het antwoord er al ligt: openweathermap
   komt in 82,0% van 200 waarnemingen overeen met wat de panelen deden,
   forecast_thuis in 76,5%. Dat is meer bewijs dan één blik naar buiten.
"""
import pytest

BRONNEN = {
    "weather.forecast_thuis": {
        "overeenstemming_percent": 76.5,
        "aantal_waarnemingen": 200,
        "status": "indicatief",
        "reden": "",
    },
    "weather.openweathermap": {
        "overeenstemming_percent": 82.0,
        "aantal_waarnemingen": 200,
        "status": "betrouwbaar",
        "reden": "",
    },
    "_vergelijking": {
        "beste_bron": "weather.openweathermap",
        "slechtste_bron": "weather.forecast_thuis",
        "verschil_procentpunt": 5.5,
        "advies": "Beide bronnen presteren vergelijkbaar.",
    },
}


def _situatie(c, gekozen="weather.openweathermap", spreiding=38.0):
    c.weather_ensemble_readings = {
        "weather.forecast_thuis": 82.0,
        "weather.openweathermap": 44.0,
    }
    c.weather_ensemble_spread_percent = spreiding
    c.weather_ensemble_cloud_cover_percent = 44.0
    c.weather_ensemble_weighted = True
    c.weather_ensemble_chosen_source = gekozen
    c.get_weather_source_reliability = lambda: BRONNEN


def _melding(c):
    regels = c.get_diagnostic_summary()["informatief"]
    return next((r for r in regels if "Weerbronnen lopen" in r), None)


def test_de_melding_noemt_de_gekozen_bron(make_coordinator, hass):
    """Er wordt niet gemiddeld maar gekozen; dan hoort er te staan wie."""
    c = make_coordinator({})
    _situatie(c)

    regel = _melding(c)

    assert regel
    assert "weather.openweathermap" in regel


def test_het_woord_gemiddelde_staat_er_niet_meer_in(make_coordinator, hass):
    """44,0 is de meting van één bron, niet het gemiddelde van twee."""
    c = make_coordinator({})
    _situatie(c)

    assert "gemiddelde" not in _melding(c)


def test_de_melding_geeft_het_werk_niet_terug(make_coordinator, hass):
    """"Controleer welke bron klopt met wat je buiten ziet" - terwijl er

    200 waarnemingen liggen die dat al beantwoorden.
    """
    c = make_coordinator({})
    _situatie(c)

    assert "buiten ziet" not in _melding(c)


def test_de_onderbouwing_staat_erbij(make_coordinator, hass):
    """Waarom die bron? Omdat hij het vaker bij het rechte eind had.

    Zonder dat cijfer is het een mededeling in plaats van een reden.
    """
    c = make_coordinator({})
    _situatie(c)

    regel = _melding(c)

    assert "82" in regel
    assert "200" in regel


def test_zonder_gekozen_bron_wordt_er_wel_gemiddeld(make_coordinator, hass):
    """Is er geen duidelijke winnaar, dan is het wél een gemiddelde - en

    dan is "kijk zelf even" ook een eerlijk advies.
    """
    c = make_coordinator({})
    _situatie(c, gekozen=None, spreiding=41.0)
    c.weather_ensemble_cloud_cover_percent = 63.0

    regel = _melding(c)

    assert regel
    assert "gemiddelde" in regel
    # De metingen staan er nog wel bij; wat er NIET mag staan is dat er
    # met één van beide gerekend wordt.
    assert "gerekend met" not in regel


def test_onder_de_drempel_geen_melding(make_coordinator, hass):
    """Een klein verschil is geen nieuws."""
    c = make_coordinator({})
    _situatie(c, gekozen=None, spreiding=10.0)

    assert _melding(c) is None
