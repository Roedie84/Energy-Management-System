"""Wat kost het dat de accu bijspringt bij een lage prijs? (v3.60.0)

Gevraagd naar aanleiding van de prijzen van 29 augustus:

    09:00 - 16:00    13 ct
    19:00 - 21:00    38 ct

    "Als ik de wasmachine aanzet kan het zijn dat de accu moet
    bijleveren, terwijl het beter is dat de accu bijlevert tijdens dure
    uren later op de dag."

Klopt. In `smart` springt de accu bij zodra het huis meer trekt dan de
zon levert - ook bij 13 ct. Die kilowattuur is er dan een die niet naar
de avond gaat:

    uit de accu nu        13 ct bespaard
    waard om 20:00        38 ct
    rendementsverlies    ~ 5 ct
    slijtage              10,9 ct
                          -------
    gemist                 9 ct per kWh

In v1.62.0 stond hier een tak die wél stuurde, en die is teruggedraaid.
Twee van de drie redenen blijven staan: bij zonoverschot is de keuze
zon-tegen-net en niet accu-tegen-net, en de som gebruikte de kostprijs
van wat er AL in zat in plaats van wat die kWh later waard is.

De derde reden klopte niet. Daar stond dat `smart_charging` de
piekbuffer uitzet; volgens de gebruiker is die modus juist "alleen
opladen uit PV, niet ontladen naar het huis" - en dat is geen bijwerking
maar precies wat er nodig is.

Deze meting rekent het uit. Ze stuurt niets.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    NIET_ONTLADEN_MIN_METINGEN,
    NIET_ONTLADEN_MIN_VERMOGEN_W,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 8, 29, 11, 0)


def _prijzen(c, prijzen, start=None):
    begin = start or NU
    c._get_forecast_entries = lambda **kw: [
        (
            begin + timedelta(hours=i),
            begin + timedelta(hours=i + 1),
            p * PRICE_SCALE_FACTOR,
        )
        for i, p in enumerate(prijzen)
    ]
    return c


def _opstelling(make_coordinator, vermogen=500.0, slijtage=10.9,
                rendement=94.0):
    c = make_coordinator({})
    c._read_corrected_battery_power = lambda: vermogen
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": slijtage}
    c.charge_efficiency_history = [rendement] * 7
    c.discharge_efficiency_history = [100.0] * 7
    return c


# --- de gemeten situatie ---------------------------------------------


def test_the_prices_of_29_august(make_coordinator, hass):
    """13 ct nu, 38 ct later. Die kWh had beter kunnen wachten."""
    c = _prijzen(_opstelling(make_coordinator), [0.13, 0.13, 0.20, 0.38])

    c._meet_niet_ontladen_bij_lage_prijs(NU, c._get_forecast_entries())

    meting = c.niet_ontladen_history[-1]
    assert meting["prijs_nu_ct"] == pytest.approx(13.0, abs=0.5)
    assert meting["duurste_later_ct"] == pytest.approx(38.0, abs=0.5)
    assert meting["voordeel_ct_per_kwh"] > 0


def test_an_expensive_moment_gives_no_benefit(make_coordinator, hass):
    """Levert de accu al in een duur kwartier, dan valt er niets te

    winnen door te wachten.
    """
    c = _prijzen(_opstelling(make_coordinator), [0.38, 0.30, 0.25])

    c._meet_niet_ontladen_bij_lage_prijs(NU, c._get_forecast_entries())

    assert c.niet_ontladen_history[-1]["voordeel_ct_per_kwh"] < 0


def test_wear_and_efficiency_are_subtracted(make_coordinator, hass):
    """Zonder die twee posten lijkt wachten altijd gunstig."""
    duur = _prijzen(_opstelling(make_coordinator, slijtage=10.9),
                    [0.13, 0.38])
    duur._meet_niet_ontladen_bij_lage_prijs(NU, duur._get_forecast_entries())

    goedkoop = _prijzen(_opstelling(make_coordinator, slijtage=0.0),
                        [0.13, 0.38])
    goedkoop._meet_niet_ontladen_bij_lage_prijs(
        NU, goedkoop._get_forecast_entries()
    )

    assert (
        duur.niet_ontladen_history[-1]["voordeel_ct_per_kwh"]
        < goedkoop.niet_ontladen_history[-1]["voordeel_ct_per_kwh"]
    )


# --- wanneer er niet gemeten wordt -----------------------------------


def test_it_only_measures_while_the_battery_delivers(
    make_coordinator, hass
):
    """Het gaat om de gevallen waarin het huis werkelijk meer trekt dan

    de zon geeft.
    """
    c = _prijzen(_opstelling(make_coordinator, vermogen=0.0), [0.13, 0.38])

    c._meet_niet_ontladen_bij_lage_prijs(NU, c._get_forecast_entries())

    assert c.niet_ontladen_history == []


def test_a_trickle_is_not_counted(make_coordinator, hass):
    """Een accu die vijftig watt levert is ruis van de meting."""
    c = _prijzen(
        _opstelling(
            make_coordinator, vermogen=NIET_ONTLADEN_MIN_VERMOGEN_W - 10
        ),
        [0.13, 0.38],
    )

    c._meet_niet_ontladen_bij_lage_prijs(NU, c._get_forecast_entries())

    assert c.niet_ontladen_history == []


def test_without_prices_nothing_is_measured(make_coordinator, hass):
    c = _opstelling(make_coordinator)
    c._get_forecast_entries = lambda **kw: []

    c._meet_niet_ontladen_bij_lage_prijs(NU, [])

    assert c.niet_ontladen_history == []


def test_only_today_counts_as_later(make_coordinator, hass):
    """Morgen is geen alternatief: dan is de accu allang weer gevuld

    door de zon.
    """
    c = _opstelling(make_coordinator)
    morgen = NU + timedelta(days=1)
    c._get_forecast_entries = lambda **kw: [
        (morgen, morgen + timedelta(hours=1), 0.50 * PRICE_SCALE_FACTOR)
    ]

    c._meet_niet_ontladen_bij_lage_prijs(NU, c._get_forecast_entries())

    assert c.niet_ontladen_history == []


# --- de kandidaat ----------------------------------------------------


def test_the_candidate_waits_for_enough_measurements(
    make_coordinator, hass
):
    c = make_coordinator({})
    c.niet_ontladen_history = [{"voordeel_ct_per_kwh": 9.0}] * 5

    kandidaat = c._kandidaat_niet_ontladen_bij_lage_prijs()

    assert kandidaat["status"] == "onvoldoende_data"
    assert str(NIET_ONTLADEN_MIN_METINGEN) in (
        kandidaat["zou_hebben_opgeleverd"]["reden"]
    )


def test_the_candidate_reports_the_median(make_coordinator, hass):
    c = make_coordinator({})
    c.niet_ontladen_history = [
        {"voordeel_ct_per_kwh": v}
        for v in ([9.0] * 150 + [-2.0] * 50)
    ]

    kandidaat = c._kandidaat_niet_ontladen_bij_lage_prijs()

    opbrengst = kandidaat["zou_hebben_opgeleverd"]
    assert opbrengst["mediaan_voordeel_ct_per_kwh"] == 9.0
    assert opbrengst["aandeel_gunstig_procent"] == 75.0


def test_the_candidate_steers_nothing(make_coordinator, hass):
    """In v1.62.0 stond hier een tak die wel stuurde. Die is

    teruggedraaid, en deze meting hoort dat niet stilletjes terug te
    draaien.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C._meet_niet_ontladen_bij_lage_prijs)

    assert "_async_apply_operation" not in bron
    assert "OPTION_SMART_CHARGING" not in bron


def test_it_is_on_the_bench(make_coordinator, hass):
    c = make_coordinator({})

    namen = [k["naam"] for k in c.get_proefstand()["kandidaten"]]

    assert "Niet ontladen bij een lage prijs" in namen
