"""De proefpagina: beide modi naast elkaar (v3.61.0).

Gevraagd: "Ik wil ook een planning zien waarin smart_charging is
meegenomen zodat ik het zelf ook kan beoordelen, een soort van test
pagina dus."

Per kwartier: is er een tekort, en wat is die kilowattuur later waard
tegenover wat hij nu bespaart? Rekent op de kwartierplanning die er al
is en verandert niets aan de aansturing.

De aanvulling die het scherp maakt: "Tenzij er natuurlijk ruim
voldoende PV energie is, dan is bovenstaande niet nodig." Dekt de zon
het huis, dan doen `smart` en `smart_charging` hetzelfde en valt er
niets te kiezen - die kwartieren tellen dus niet mee.
"""
import pytest


def _plan(c, rijen):
    c.get_quarter_plan = lambda now=None: rijen
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 10.9}
    c.charge_efficiency_history = [94.0] * 7
    c.discharge_efficiency_history = [100.0] * 7
    return c


def _rij(van, prijs, zon, verbruik):
    return {
        "van": van,
        "prijs_ct": prijs,
        "zon_kwh": zon,
        "verbruik_kwh": verbruik,
    }


# --- de prijzen van 29 augustus --------------------------------------


def test_the_cheap_block_shows_a_benefit(make_coordinator, hass):
    """13 ct met een tekort, terwijl er 's avonds 38 ct komt."""
    c = _plan(
        make_coordinator({}),
        [
            _rij("11:00", 13.0, 0.10, 0.60),
            _rij("20:00", 38.0, 0.0, 0.15),
        ],
    )

    uit = c.get_smart_charging_proefplanning()

    goedkoop = uit["rijen"][0]
    assert goedkoop["tekort_kwh"] == pytest.approx(0.50)
    assert goedkoop["smart_charging_beter"] is True
    assert uit["duurste_prijs_ct"] == 38.0


def test_ample_sun_is_not_counted(make_coordinator, hass):
    """De aanvulling: dekt de zon het huis, dan valt er niets te kiezen."""
    c = _plan(
        make_coordinator({}),
        [_rij("12:00", 13.0, 2.00, 0.20), _rij("20:00", 38.0, 0.0, 0.15)],
    )

    rij = c.get_smart_charging_proefplanning()["rijen"][0]

    assert rij["tekort_kwh"] == 0
    assert rij["smart_charging_beter"] is False
    assert rij["voordeel_eur"] == 0


def test_an_expensive_quarter_shows_no_benefit(make_coordinator, hass):
    """Levert de accu al in het duurste kwartier, dan is wachten zinloos."""
    c = _plan(
        make_coordinator({}),
        [_rij("20:00", 38.0, 0.0, 0.50), _rij("21:00", 30.0, 0.0, 0.20)],
    )

    assert c.get_smart_charging_proefplanning()["rijen"][0][
        "smart_charging_beter"
    ] is False


# --- de samenvatting -------------------------------------------------


def test_the_summary_counts_the_quarters(make_coordinator, hass):
    c = _plan(
        make_coordinator({}),
        [
            _rij("11:00", 13.0, 0.10, 0.60),
            _rij("12:00", 13.0, 2.00, 0.20),
            _rij("13:00", 13.0, 0.10, 0.50),
            _rij("20:00", 38.0, 0.0, 0.15),
        ],
    )

    uit = c.get_smart_charging_proefplanning()

    assert uit["kwartieren"] == 4
    assert uit["kwartieren_met_tekort"] == 3
    assert uit["kwartieren_smart_charging_beter"] == 2
    assert uit["totaal_voordeel_eur"] > 0


def test_wear_and_efficiency_are_in_the_sum(make_coordinator, hass):
    """Zonder die twee posten lijkt wachten altijd gunstig."""
    c = _plan(
        make_coordinator({}),
        [_rij("11:00", 13.0, 0.0, 0.50), _rij("20:00", 38.0, 0.0, 0.15)],
    )

    uit = c.get_smart_charging_proefplanning()

    # 38 x 0,94 - 10,9 = 24,8 ct
    assert uit["waarde_later_ct_per_kwh"] == pytest.approx(24.8, abs=0.5)
    assert uit["slijtage_ct_per_kwh"] == 10.9


def test_without_a_plan_it_says_so(make_coordinator, hass):
    c = make_coordinator({})
    c.get_quarter_plan = lambda now=None: []

    assert c.get_smart_charging_proefplanning()["beschikbaar"] is False


def test_it_steers_nothing(make_coordinator, hass):
    """Een proefpagina die stuurt is geen proefpagina."""
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C.get_smart_charging_proefplanning)

    assert "_async_apply_operation" not in bron
    assert "OPTION_" not in bron


def test_it_reaches_the_export_and_the_dashboard():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    map_ = Path(pkg.__file__).parent

    assert '"smart_charging_proefplanning"' in (
        map_ / "diagnostics.py"
    ).read_text()
    assert '"smart_charging_proef"' in (map_ / "sensor.py").read_text()


# --- de kaart op het dashboard (v3.67.0) -----------------------------


def test_the_card_lives_on_the_planning_page():
    """Gevraagd: "Graag toch nog een dashboard ergens onder de

    planningspagina (verder onzichtbaar net als de rest) met de test
    planning voor smart charge."

    Op de kwartierpagina, want het gaat om de planning - en die pagina
    is `subview`, dus hij verschijnt niet in de navigatie.
    """
    from pathlib import Path

    import yaml

    import custom_components.energy_management_system as pkg

    sjabloon = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    pagina = next(
        v for v in sjabloon["views"] if v.get("path") == "detail-kwartier"
    )

    assert pagina.get("subview") is True

    titels = [k.get("title") for k in pagina["sections"][0]["cards"]]
    assert "Proef - zou smart_charging lonen?" in titels


def test_the_card_reads_the_right_attribute():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    map_ = Path(pkg.__file__).parent
    sjabloon = (map_ / "dashboard_template.yaml").read_text()

    assert "smart_charging_proef" in sjabloon
    # En de kopie die de gebruiker installeert loopt niet achter.
    kopie = (map_.parent.parent / "dashboards"
             / "energy_management_system_dashboard.yaml").read_text()
    assert kopie == sjabloon


def test_only_quarters_with_a_deficit_are_listed():
    """Zonder tekort doen beide modi hetzelfde; die rijen zouden de

    tabel alleen langer maken.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    sjabloon = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()

    assert "{% if r.tekort_kwh > 0 %}" in sjabloon
