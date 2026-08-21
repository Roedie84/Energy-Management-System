"""Elke tak van de koelbeslissing geeft een dict terug (v3.44.1).

Gemeld met drie meldingen op een rij:

    21 Aug 19:34  De koeling geet te vaak an
                  De ventilator sloeg vandaag al 4 keer aan
    21 Aug 19:36  1 onderde(e)l(en) kan zichzelf neet berekenen:
                  ronde:accukoeling

Twee minuten na het aanslaan van de dagportie van v3.33.0 lag de
koelronde eruit. De oorzaak: de tak deed een kale `return` in een
functie die `-> dict` belooft, en gaf dus None terug. Elke andere vroege
terugkeer in die functie geeft `resultaat` terug.

De toetsen op die dagportie keken naar wat hij BESLIST -
`_goedkope_koeling_op_slot` geeft True of False - en niet naar wat de
omliggende functie teruggeeft. Daardoor bleef de suite groen terwijl de
ronde in de praktijk omviel.
"""
import inspect

import pytest

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


def test_every_return_in_the_cooling_decision_carries_a_value():
    """De aanleiding, als structuurtoets: een kale `return` in deze

    functie levert None op waar een dict wordt verwacht.
    """
    bron = inspect.getsource(C.evaluate_battery_cooling)

    kaal = [
        regel.strip()
        for regel in bron.split("\n")
        if regel.strip() == "return"
    ]

    assert not kaal, (
        f"{len(kaal)} kale return(s) in evaluate_battery_cooling - "
        "die geven None terug uit een functie die een dict belooft"
    )


def test_the_ration_branch_returns_the_result(make_coordinator, hass):
    """De tak die de dagportie afdwingt, met een echte coordinator."""
    from datetime import date, datetime

    c = make_coordinator({})
    c.goedkope_koeling_teller = 9
    c.goedkope_koeling_teldag = date(2026, 8, 21)
    c._goedkope_koeling_gemeld = True

    uitkomst = c.evaluate_battery_cooling()

    assert isinstance(uitkomst, dict)
    assert "reden" in uitkomst


@pytest.mark.parametrize(
    "naam",
    [
        "evaluate_battery_cooling",
        "may_sell_now",
        "get_wear_cost_overview",
        "get_climate_rate",
        "get_temp_consumption_bruikbaarheid",
    ],
)
def test_functions_that_promise_a_dict_never_return_bare(naam):
    """Dezelfde fout ligt overal op de loer waar een functie een dict

    belooft en ergens halverwege afhaakt.
    """
    functie = getattr(C, naam)
    bron = inspect.getsource(functie)

    if "-> dict" not in bron.split("\n")[0] and "-> dict" not in bron[:400]:
        pytest.skip(f"{naam} belooft geen dict")

    kaal = [r.strip() for r in bron.split("\n") if r.strip() == "return"]

    assert not kaal, f"{naam} heeft {len(kaal)} kale return(s)"
