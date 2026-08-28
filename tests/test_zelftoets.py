"""De integratie toetst haar eigen uitkomsten (v3.65.0).

Gemeld: "Dus je hebt toch fouten gevonden, dan heb je niet grondig
genoeg gezocht."

Terecht. Op 28 augustus stond in de export:

    vergelijkingen  60
    zonder zon      60
    met zon          0

Zestig van de zestig als nacht, terwijl de zon die dag geschenen had.
Dat stond er gewoon, en het is een dag lang gelezen zonder dat het
opviel.

De spiegelcontrole bewaakt de SENSOREN - een intern getal tegen de
meting waar het vandaan komt. Maar deze fout zat in een AFGELEID cijfer,
en daar keek niets naar.

Deze toets kijkt naar uitkomsten die logisch niet kunnen. Elke bevinding
is een fout in de integratie zelf, niet in de meetopstelling.
"""
import pytest

from custom_components.energy_management_system.const import (
    ZELFTOETS_MIN_REEKS,
)


def _namen(c):
    return [b["naam"] for b in c.get_zelftoets()]


# --- de fout van 28 augustus -----------------------------------------


def test_a_one_sided_split_is_caught(make_coordinator, hass):
    """Zestig vergelijkingen, allemaal nacht. Over meerdere dagen horen

    beide voor te komen.
    """
    c = make_coordinator({})
    c.digital_twin_accuracy_history = [
        {"fout_kwh": 1.0, "met_zon": False} for _ in range(60)
    ]

    namen = _namen(c)

    assert "Tweeling: splitsing eenzijdig" in namen


def test_a_balanced_split_is_fine(make_coordinator, hass):
    c = make_coordinator({})
    c.digital_twin_accuracy_history = [
        {"fout_kwh": 1.0, "met_zon": i % 3 == 0} for i in range(60)
    ]

    assert "Tweeling: splitsing eenzijdig" not in _namen(c)


def test_a_short_series_says_nothing(make_coordinator, hass):
    """Vlak na een herstart is één kant nog leeg, en dat is normaal."""
    c = make_coordinator({})
    c.digital_twin_accuracy_history = [
        {"fout_kwh": 1.0, "met_zon": False}
        for _ in range(ZELFTOETS_MIN_REEKS - 1)
    ]

    assert "Tweeling: splitsing eenzijdig" not in _namen(c)


# --- reeksen die stilstaan -------------------------------------------


def test_a_flat_series_is_caught(make_coordinator, hass):
    """Een bron die stilstaat levert een reeks op die er gevuld uitziet

    en niets meet.
    """
    c = make_coordinator({})
    c.night_consumption_history = [0.23] * ZELFTOETS_MIN_REEKS

    assert "Nachtverbruik: elke waarde gelijk" in _namen(c)


def test_a_varying_series_is_fine(make_coordinator, hass):
    c = make_coordinator({})
    c.night_consumption_history = [
        0.20 + i * 0.01 for i in range(ZELFTOETS_MIN_REEKS)
    ]

    assert "Nachtverbruik: elke waarde gelijk" not in _namen(c)


# --- percentages buiten hun bereik -----------------------------------


@pytest.mark.parametrize("waarde", [-5.0, 130.0])
def test_an_impossible_percentage_is_caught(
    make_coordinator, hass, waarde
):
    """Zo'n waarde kan niet uit een geldige berekening komen."""
    c = make_coordinator({})
    c.accustand_procent = lambda: waarde

    assert "Accustand buiten bereik" in _namen(c)


def test_a_normal_percentage_is_fine(make_coordinator, hass):
    c = make_coordinator({})
    c.accustand_procent = lambda: 47.0

    assert "Accustand buiten bereik" not in _namen(c)


# --- klimaatcellen die niets zeggen ----------------------------------


def test_all_zero_climate_cells_are_caught(make_coordinator, hass):
    """Een kamer die nooit van temperatuur verandert bestaat niet."""
    c = make_coordinator({})
    c.climate_rate_history = {
        f"d{i}.0|beide_dicht|uit": [0.0] * 5
        for i in range(ZELFTOETS_MIN_REEKS)
    }

    assert "Klimaatcellen: alles nul" in _namen(c)


def test_real_climate_cells_are_fine(make_coordinator, hass):
    c = make_coordinator({})
    c.climate_rate_history = {
        f"d-{i}.0|beide_dicht|uit": [-0.05 * i] * 5
        for i in range(1, ZELFTOETS_MIN_REEKS + 1)
    }

    assert "Klimaatcellen: alles nul" not in _namen(c)


# --- en het komt bovenaan te staan -----------------------------------


def test_a_finding_lands_in_the_analysis(make_coordinator, hass):
    """Onderaan een export van 600 kB zou het net zo goed worden

    overgeslagen als de rest - en dat is precies wat er op 28 augustus
    gebeurde.
    """
    c = make_coordinator({})
    c.digital_twin_accuracy_history = [
        {"fout_kwh": 1.0, "met_zon": False} for _ in range(60)
    ]

    analyse = c.get_analyse()

    assert analyse["aantal_fouten"] >= 1
    assert any(
        p["onderwerp"] == "Tweeling: splitsing eenzijdig"
        for p in analyse["punten"]
    )


def test_a_healthy_system_reports_nothing(make_coordinator, hass):
    c = make_coordinator({})

    assert c.get_zelftoets() == []


def test_it_would_have_caught_the_export_of_28_august(
    make_coordinator, hass
):
    """De toets die telt: had dit de fout van gisteren gevangen?

    De cijfers komen letterlijk uit de export van 28 augustus 17:58. Ik
    heb die dag "geen bevindingen" gemeld terwijl dit erin stond.
    """
    c = make_coordinator({})
    c.digital_twin_accuracy_history = [
        {"fout_kwh": 1.346, "met_zon": False} for _ in range(60)
    ]

    analyse = c.get_analyse()

    assert analyse["samenvatting"] != "Geen bijzonderheden."
    punt = next(
        p for p in analyse["punten"]
        if p["onderwerp"] == "Tweeling: splitsing eenzijdig"
    )
    assert "60" in punt["wat"]
