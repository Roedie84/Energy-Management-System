"""Een correctie mag niet leren van zijn eigen gecorrigeerde uitkomst
(v5.13, bewaking).

Gevraagd, na mijn opmerking dat de PV-bias tegen de ruwe voorspelling
leert: *"Dit is een belangrijke, nu met 5.13 opgelost?"*

Er was niets kapot. Maar mijn eerste controle was een tekstscan - zoeken
naar woorden als "bias" en "correct" in de functie - en dat is precies het
soort controle dat deze week steeds tekortschoot. Dus nu op gedrag, voor
alle vier de leerders:

    PV-uurbias          leert tegen de ruwe voorspelling
    PV-dagbias          leest de Solcast-sensor rechtstreeks
    bewolkingsvakken    gebruikt dezelfde afwijking als de dagbias
    klimaatbias         weather.get_forecasts, ruw

Waarom dit ertoe doet: een correctie die leert van zijn eigen
gecorrigeerde uitkomst, jaagt zichzelf na. Leert hij dat de zon 10% te
hoog voorspeld wordt, dan wordt de volgende vergelijking al met de
gecorrigeerde waarde gemaakt - en ziet hij een kleinere afwijking, en
corrigeert hij minder, en zo verder. Het loopt naar een willekeurig punt
in plaats van naar de waarheid.

Deze toetsen houden dat dicht: ze stellen een sterke bias in en kijken of
de leerbron daardoor verandert. Dat hoort niet.
"""
from datetime import datetime, timezone

DAG = datetime(2026, 9, 21, tzinfo=timezone.utc)


def test_de_uurbias_leert_tegen_de_ruwe_voorspelling(make_coordinator, hass):
    """Een sterke uurbias mag de voorspelling waartegen hij leert niet
    veranderen."""
    c = make_coordinator({})
    ruw = [(DAG.replace(hour=12), DAG.replace(hour=13), 2.0)]
    c._get_pv_forecast_entries = lambda: ruw

    voor = c._get_forecast_kwh_for_hour(DAG.date(), 12)
    c.pv_hourly_bias_history = {h: [0.5] * 30 for h in range(24)}
    na = c._get_forecast_kwh_for_hour(DAG.date(), 12)

    assert voor == na == 2.0


def test_de_dagbias_leest_de_voorspelsensor_zelf(make_coordinator, hass):
    """De dagbias neemt zijn voorspelling rechtstreeks van de Solcast-
    sensor. Zou hij de gecorrigeerde schatting van de integratie nemen, dan
    leerde hij van zichzelf."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "solar_forecast.py").read_text()
    i = bron.index("forecast_value = _read_float(")
    blok = bron[i : i + 120]

    assert "CONF_SOLAR_FORECAST_SENSOR" in blok


def test_de_klimaatbias_leert_tegen_de_ruwe_weervoorspelling():
    """De klimaatbias vergelijkt de gemeten buitentemperatuur met wat
    `weather.get_forecasts` teruggeeft - niet met de gecorrigeerde
    projectie."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("async def _async_fetch_hourly_outdoor_forecast")
    j = bron.index("\n    async def ", i + 10) if "\n    async def " in bron[i + 10 :] else len(bron)
    j = min(j, bron.index("\n    def ", i + 10))
    functie = bron[i:j]

    assert "get_forecasts" in functie
    assert "climate_forecast_bias" not in functie
