"""Alles wat nog niet bepaald is, met wat ervoor nodig is (v1.41.0).

Gevraagd, met een screenshot van de tegel "PV-installatieprofiel - nog
niet bepaald": "Als er zaken niet bepaald zijn of nog niet genoeg data,
wil ik dat graag zien."

"Nog niet bepaald" zegt niet of er iets stuk is, of er iets moet
gebeuren, of dat het gewoon wachten is - en dat verschil is precies wat
je wilt weten. Achter die tegel zat de reden al klaar: "0/5 heldere
dagen verzameld".
"""
from custom_components.energy_management_system.const import (
    RELIABILITY_NOT_CONFIGURED,
    RELIABILITY_RELIABLE,
    RELIABILITY_UNVERIFIABLE,
)


def _coordinator(make_coordinator, rijen):
    c = make_coordinator({})
    c.get_reliability_overview = lambda: rijen
    c.get_proefstand = lambda: {"kandidaten": []}
    return c


def test_what_is_ready_is_left_out(make_coordinator, hass):
    c = _coordinator(
        make_coordinator,
        [
            {
                "groep": "Adviesmodules",
                "naam": "kirchhoff",
                "niveau": RELIABILITY_RELIABLE,
                "reden": "Score 85,0% over 20 metingen.",
            }
        ],
    )

    overzicht = c.get_pending_overview()

    assert overzicht["aantal_wachten"] == 0
    assert overzicht["aantal_doen"] == 0


def test_waiting_and_doing_are_separated(make_coordinator, hass):
    """Wachten betekent: er is niets mis. Doen betekent: er ontbreekt
    een sensor of instelling, en wachten helpt niet."""
    c = _coordinator(
        make_coordinator,
        [
            {
                "groep": "Geleerde waarden",
                "naam": "PV-installatieprofiel",
                "niveau": "onvoldoende_data",
                "reden": "0/5 heldere dagen verzameld.",
            },
            {
                "groep": "Metingen",
                "naam": "Watermeter",
                "niveau": RELIABILITY_NOT_CONFIGURED,
                "reden": "Geen sensor gekozen.",
            },
        ],
    )

    overzicht = c.get_pending_overview()

    assert [r["naam"] for r in overzicht["wachten"]] == ["PV-installatieprofiel"]
    assert [r["naam"] for r in overzicht["doen"]] == ["Watermeter"]


def test_what_cannot_be_verified_is_not_a_waiting_item(
    make_coordinator, hass
):
    """Bij "niet toetsbaar" valt principieel niets tegen af te zetten;
    het in de wachtrij zetten zou suggereren dat het vanzelf goed komt.
    """
    c = _coordinator(
        make_coordinator,
        [
            {
                "groep": "Adviesmodules",
                "naam": "mpc",
                "niveau": RELIABILITY_UNVERIFIABLE,
                "reden": "Nauwkeurigheid wordt niet bijgehouden.",
            }
        ],
    )

    overzicht = c.get_pending_overview()

    assert overzicht["aantal_wachten"] == 0
    assert overzicht["aantal_doen"] == 0


def test_the_reason_is_carried_over(make_coordinator, hass):
    """Zonder de reden is het overzicht net zo nietszeggend als de tegel
    die de aanleiding was."""
    c = _coordinator(
        make_coordinator,
        [
            {
                "groep": "Geleerde waarden",
                "naam": "PV-installatieprofiel",
                "niveau": "onvoldoende_data",
                "reden": "0/5 heldere dagen verzameld.",
            }
        ],
    )

    overzicht = c.get_pending_overview()

    assert overzicht["wachten"][0]["wat_ontbreekt"] == "0/5 heldere dagen verzameld."


def test_the_test_bench_joins_the_list(make_coordinator, hass):
    c = _coordinator(make_coordinator, [])
    c.get_proefstand = lambda: {
        "kandidaten": [
            {
                "naam": "Accugezondheid over de tijd",
                "status": "onvoldoende_data",
                "betrouwbaarheid": "0 dagmetingen.",
            },
            {
                "naam": "Slijtagekosten per kWh",
                "status": RELIABILITY_RELIABLE,
                "betrouwbaarheid": "",
            },
        ]
    }

    overzicht = c.get_pending_overview()

    assert [r["naam"] for r in overzicht["wachten"]] == [
        "Accugezondheid over de tijd"
    ]
