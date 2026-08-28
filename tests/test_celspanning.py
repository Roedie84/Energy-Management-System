"""De laagste celspanning meten en beoordelen (v3.52.0).

Gevraagd: "Kan de integratie zelf beoordelen of bijladen noodzakelijk
is? In de winter moet hier immers wel rekening mee worden gehouden. Let
wel op: financieel moet het voor mij optimaal zijn."

De laadstand zegt daar weinig over. LiFePO4 heeft een vlakke
spanningskromme, dus onderin is 6% en 12% nauwelijks te onderscheiden -
en lang laag staan is bij LFP niet schadelijk, anders dan bij de accu's
in telefoons en auto's.

Wat wél telt is dat één cel de afschakelspanning raakt terwijl de rest
nog ruimte heeft. Gemeten op 27 augustus:

    module 1  laagste cel 3,08 V
    module 2  3,21          module 3  3,21

De pakketspanning oogt dan prima en de BMS grijpt in op die ene cel.

Deze code meet, oordeelt en rekent voor - maar stuurt niets. De keuze om
bij te laden blijft handmatig.
"""
from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.energy_management_system.const import (
    CELSPANNING_AANDACHT_V,
    CELSPANNING_DAGEN_VOOR_PATROON,
    CELSPANNING_KRITIEK_V,
    CELSPANNING_VENSTER_UREN,
    PRICE_SCALE_FACTOR,
)

def _nu():
    """De klok per toets opvragen, niet bij het importeren.

    Anders vriest hij vast op het moment dat de eerste toets werd
    ingeladen, en dan slagen ze los wél en samen niet - precies wat er
    bij het schrijven gebeurde.
    """
    return dt_util.now()


def _modules(c, spanningen):
    c.battery_module_live = [
        {"module": i + 1, "cel_min_v": v, "cel_max_v": v + 0.02}
        for i, v in enumerate(spanningen)
    ]
    return c


def _prijzen(c, prijzen):
    c._get_forecast_entries = lambda **kw: [
        (
            _nu() + timedelta(hours=i),
            _nu() + timedelta(hours=i + 1),
            p * PRICE_SCALE_FACTOR,
        )
        for i, p in enumerate(prijzen)
    ]
    return c


# --- het oordeel -----------------------------------------------------


def test_the_measured_situation_of_27_august(make_coordinator, hass):
    """Module 1 op 3,08 terwijl de rest op 3,21 staat."""
    c = _modules(make_coordinator({}), [3.08, 3.21, 3.21])

    oordeel = c.get_celspanning_oordeel()

    assert oordeel["oordeel"] == "aandacht"
    assert oordeel["module"] == 1
    assert oordeel["laagste_cel_v"] == 3.08


def test_a_healthy_pack_is_simply_fine(make_coordinator, hass):
    c = _modules(make_coordinator({}), [3.28, 3.29, 3.29])

    assert c.get_celspanning_oordeel()["oordeel"] == "ruim"


def test_below_the_bms_threshold_is_critical(make_coordinator, hass):
    """Onder 3,00 V grijpt de BMS in op deze ene cel terwijl de rest nog

    ruimte heeft.
    """
    c = _modules(make_coordinator({}), [2.95, 3.21, 3.21])

    oordeel = c.get_celspanning_oordeel()

    assert oordeel["oordeel"] == "kritiek"
    assert "ongeacht de prijs" in oordeel["advies"]


def test_the_lowest_cell_decides_not_the_average(make_coordinator, hass):
    """De pakketspanning oogt gemiddeld prima terwijl één cel bijna leeg

    is - dat is precies waarom dit op de laagste cel let.
    """
    c = _modules(make_coordinator({}), [3.05, 3.30, 3.30])

    assert c.get_celspanning_oordeel()["oordeel"] == "aandacht"


def test_without_cell_data_it_says_so(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = []

    assert c.get_celspanning_oordeel()["beschikbaar"] is False


# --- financieel optimaal ---------------------------------------------


def test_it_names_the_cheapest_moment_in_the_window(
    make_coordinator, hass
):
    """Een gezondheidsgrens mag geen aankoop afdwingen op het moment dat

    hij aanslaat - dat is bijna altijd een duur kwartier. De juiste vorm
    is een randvoorwaarde met een VENSTER.
    """
    c = _prijzen(_modules(make_coordinator({}), [3.05, 3.2, 3.2]),
                 [0.38, 0.31, 0.19, 0.24])

    oordeel = c.get_celspanning_oordeel()

    assert oordeel["goedkoopste_prijs_ct"] == pytest.approx(19.0, abs=0.5)
    verwacht = (_nu() + timedelta(hours=2)).strftime("%H")
    assert verwacht in oordeel["goedkoopste_moment"]


def test_the_wear_cost_is_included(make_coordinator, hass):
    """Bijladen kost de prijs én de slijtage; zonder die post lijkt het

    goedkoper dan het is.
    """
    c = _prijzen(_modules(make_coordinator({}), [3.05, 3.2, 3.2]), [0.20, 0.20])
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 10.9}

    oordeel = c.get_celspanning_oordeel()

    assert oordeel["kosten_per_kwh_ct"] == pytest.approx(30.9, abs=0.5)


def test_prices_beyond_the_window_are_ignored(make_coordinator, hass):
    """Zes uur is ruim genoeg om een goedkoop blok te vinden en kort

    genoeg om niet te lang onder de grens te blijven.
    """
    c = _modules(make_coordinator({}), [3.05, 3.2, 3.2])
    c._get_forecast_entries = lambda **kw: [
        (
            _nu() + timedelta(hours=1),
            _nu() + timedelta(hours=2),
            0.30 * PRICE_SCALE_FACTOR,
        ),
        (
            _nu() + timedelta(hours=CELSPANNING_VENSTER_UREN + 4),
            _nu() + timedelta(hours=CELSPANNING_VENSTER_UREN + 5),
            0.05 * PRICE_SCALE_FACTOR,
        ),
    ]

    oordeel = c.get_celspanning_oordeel()

    assert oordeel["goedkoopste_prijs_ct"] == pytest.approx(30.0, abs=0.5)


# --- de dagelijkse geschiedenis --------------------------------------


def test_the_daily_value_is_the_minimum_not_the_median(
    make_coordinator, hass
):
    """Elk ander veld wordt met de mediaan samengevat, en dat is hier

    precies verkeerd: een dieptepunt van een kwartier verdwijnt dan in
    het gemiddelde van een etmaal.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C._finalize_battery_module_day)

    assert "laagste_cel_v" in bron
    assert "laagste_cel_vandaag_v" in bron


def test_a_pattern_needs_several_days(make_coordinator, hass):
    """Eén dag laag is bij LiFePO4 geen probleem; meerdere dagen op rij

    betekent dat de zon het niet meer bijhoudt.
    """
    c = _modules(make_coordinator({}), [3.05, 3.2, 3.2])
    c.battery_module_health = {
        "1": {
            "geschiedenis": {
                "laagste_cel_v": [3.25, 3.20, 3.05, 3.04],
            }
        }
    }

    assert c.get_celspanning_oordeel()["dagen_onder_grens"] == 2
    assert CELSPANNING_DAGEN_VOOR_PATROON <= 2


def test_a_single_low_day_is_not_a_pattern(make_coordinator, hass):
    c = _modules(make_coordinator({}), [3.05, 3.2, 3.2])
    c.battery_module_health = {
        "1": {"geschiedenis": {"laagste_cel_v": [3.25, 3.22, 3.05]}}
    }

    assert c.get_celspanning_oordeel()["dagen_onder_grens"] == 1


# --- de grenzen zelf -------------------------------------------------


def test_the_thresholds_follow_the_lfp_curve():
    """Boven 3,20 ruim, 3,10 let op, 3,00 de BMS, 2,50 schade."""
    assert 3.05 <= CELSPANNING_AANDACHT_V <= 3.15
    assert 2.95 <= CELSPANNING_KRITIEK_V <= 3.05
    assert CELSPANNING_KRITIEK_V < CELSPANNING_AANDACHT_V
