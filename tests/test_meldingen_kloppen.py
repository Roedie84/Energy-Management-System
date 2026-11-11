"""Meldingen zeggen wat het EMS werkelijk doet (v5.26.2).

Gemeld: "30 Sep 19:25 · Weinig-zunne-dag - Vandage wödt 11.15 kWh verwacht,
tegen 12.62 kWh op een typische dag (88%). Er wödt daarom buiten 't
goedkope blok bi-j-elaojen als de prijsmarge dat rechtvaardigt." Drie
fouten: het oordeel ging over MORGEN, de getallen over vandaag; 88% is geen
weinig zon; en die dipregel bestaat sinds v5.25.2 niet meer.

"Tevens staat het logboek van meldingen nu verkeerd om, nieuwste onderaan."
"""
from pathlib import Path

import jinja2
import yaml

import custom_components.energy_management_system as pkg
from tests._coordinator_bron import lees

BASIS = Path(pkg.__file__).parent


def test_de_weinig_zon_melding_noemt_morgen_met_dezelfde_getallen(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["solar_forecast_sensor_entity"] = "sensor.solcast_morgen"
    hass.states.set("sensor.solcast_morgen", "4.0")
    c.zonbias_percent = lambda: 0.0
    c._get_low_solar_relative_fraction = lambda: 0.6

    class Tracker:
        learned_typical_forecast_kwh = 12.62

    c.solar_tracker = Tracker()
    assert c._is_low_solar_expected() is True
    zon = c._zon_tegen_drempel(4.0)

    assert zon["verwacht_kwh"] == 4.0
    assert round(zon["drempel_kwh"], 2) == 7.57


def test_88_procent_is_geen_weinig_zon(make_coordinator, hass):
    """11,15 van 12,62 kWh: ruim boven de grens van 60%."""
    c = make_coordinator({})
    c.zonbias_percent = lambda: 0.0
    c._get_low_solar_relative_fraction = lambda: 0.6

    class Tracker:
        learned_typical_forecast_kwh = 12.62

    c.solar_tracker = Tracker()

    assert c._is_forecast_value_low(11.15) is False


def test_geen_melding_belooft_wat_niet_meer_gebeurt():
    """Laden buiten het blok "als de marge het rechtvaardigt" (v5.25.2
    vervallen) en "zo nodig bijladen" / "laadt eerder bij" (sinds v5.26.1
    alleen als het loont)."""
    for naam in ("coordinator.py", "const.py"):
        tekst = lees(BASIS / naam)
        for belofte in (
            "buiten het goedkope blok bijgeladen als de prijsmarge",
            "Er wordt zo nodig bijgeladen",
            "laadt eerder bij",
        ):
            assert belofte not in tekst, (naam, belofte)


