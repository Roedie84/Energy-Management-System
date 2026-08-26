"""De planning overleeft een leeg uurprofiel (v3.45.1).

Gemeld direct na het indrukken van de resetknop bij thuiskomst van
vakantie. Elf onderdelen tegelijk:

    kwartierplanning, kwartier_samenvatting, overzichtsplaat,
    overzichtsecties, proefstand, ronde:bijkopen, en vijf
    diagnostiek-onderdelen

allemaal met dezelfde fout:

    TypeError: unsupported operand type(s) for -: 'float' and 'NoneType'

`_estimate_consumption_kwh_for_period` geeft bewust None zodra één uur
in het venster nog geen geleerde waarde heeft - de docstring zegt
letterlijk "so the caller can fall back to a simpler estimate". Zes van
de negen aanroepers doen dat ook, met `or 0.0`. De kwartierplanning niet,
en die rekende er rechtstreeks mee door.

Vóór de resetknop van v3.30.0 kwam een volledig leeg profiel in de
praktijk niet voor: er was altijd wel geschiedenis. Die knop maakte de
lege staat bereikbaar, en daarmee werd een sluimerende fout van jaren
oud opeens zichtbaar.

De sturing zelf bleef overigens draaien - alleen alles wat uit de
planning leest viel weg.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    DEFAULT_HOUSEHOLD_LOAD_KW,
)

START = datetime(2026, 8, 24, 16, 0)
EINDE = START + timedelta(hours=4)


def test_an_empty_profile_still_gives_a_number(make_coordinator, hass):
    """De kern: na de reset is er geen enkel geleerd uur."""
    c = make_coordinator({})
    c.hourly_consumption_profile = {}
    c.night_consumption_history = []

    uitkomst = c._verbruik_met_terugval(START, EINDE)

    assert isinstance(uitkomst, float)
    assert uitkomst > 0


def test_zero_is_never_the_fallback(make_coordinator, hass):
    """Nul zou betekenen dat het huis niets gebruikt, en dan belooft de

    planning een volle accu die er niet komt. Dat is erger dan een ruwe
    schatting.
    """
    c = make_coordinator({})
    c.hourly_consumption_profile = {}
    c.night_consumption_history = []
    c._read_corrected_consumption_power = lambda: None

    uitkomst = c._verbruik_met_terugval(START, EINDE)

    assert uitkomst == pytest.approx(DEFAULT_HOUSEHOLD_LOAD_KW * 4, abs=0.01)


def test_the_learned_night_baseline_comes_first(make_coordinator, hass):
    """Zodra er nachten geleerd zijn, zijn die beter dan een vaste

    aanname.
    """
    c = make_coordinator({})
    c.hourly_consumption_profile = {}
    c.night_consumption_history = [0.4, 0.4, 0.4, 0.4, 0.4]

    uitkomst = c._verbruik_met_terugval(START, EINDE)

    assert uitkomst == pytest.approx(0.4 * 4, abs=0.05)


def test_the_live_meter_beats_the_default(make_coordinator, hass):
    c = make_coordinator({})
    c.hourly_consumption_profile = {}
    c.night_consumption_history = []
    c._read_corrected_consumption_power = lambda: 800.0

    uitkomst = c._verbruik_met_terugval(START, EINDE)

    assert uitkomst == pytest.approx(0.8 * 4, abs=0.01)


def test_a_full_profile_is_used_unchanged(make_coordinator, hass):
    """De terugval mag het geleerde profiel niet verdringen."""
    c = make_coordinator({})
    c._estimate_consumption_kwh_for_period = lambda s, e: 1.234

    assert c._verbruik_met_terugval(START, EINDE) == 1.234


def test_the_quarter_plan_uses_the_fallback():
    """De aanleiding, als structuurtoets: deze aanroep mocht niet

    rechtstreeks op de schatter blijven staan.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C.get_quarter_plan)

    assert "_verbruik_met_terugval" in bron
    assert "self._estimate_consumption_kwh_for_period(start, einde)" not in bron


def test_a_reversed_window_is_zero(make_coordinator, hass):
    c = make_coordinator({})
    c.hourly_consumption_profile = {}

    assert c._verbruik_met_terugval(EINDE, START) == 0.0
