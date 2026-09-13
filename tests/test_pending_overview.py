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
    # v1.47.0: de ingangscontrole is een eigen onderwerp met eigen
    # tests; hier gaat het om het scheiden van wachten en doen.
    c.get_input_health = lambda: []
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


# --- v1.47.0: ingangen die er zijn maar niets leveren ----------------


def _met_ingangen(make_coordinator, hass, **config):
    c = make_coordinator(config)
    c.get_reliability_overview = lambda: []
    c.get_proefstand = lambda: {"kandidaten": []}
    return c


def test_a_sensor_without_the_needed_attribute_is_reported(
    make_coordinator, hass
):
    """Gevraagd: "Meer van dit soort zaken in de integratie?"

    Dat is een soort fout, geen incident: een onderdeel leest een
    attribuut, krijgt None, keert netjes terug - en niemand merkt het.
    Een ONTBREKENDE sensor werd al gemeld; een sensor die er wél is maar
    het gevraagde attribuut niet heeft, glipte ertussendoor.
    """
    from custom_components.energy_management_system.const import (
        CONF_PRICE_SENSOR,
    )

    c = _met_ingangen(make_coordinator, hass, **{CONF_PRICE_SENSOR: "sensor.prijs"})
    # De sensor bestaat, maar zonder forecast-attribuut.
    hass.states.set("sensor.prijs", "0.30")

    gebreken = [g["naam"] for g in c.get_input_health()]

    assert "Prijsvoorspelling" in gebreken


def test_a_working_input_is_not_reported(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_PRICE_SENSOR,
    )

    c = _met_ingangen(make_coordinator, hass, **{CONF_PRICE_SENSOR: "sensor.prijs"})
    hass.states.set("sensor.prijs", "0.30", {"forecast": [{"x": 1}]})

    assert "Prijsvoorspelling" not in [g["naam"] for g in c.get_input_health()]


def test_uninstalled_things_stay_silent(make_coordinator, hass):
    """Wie geen airco heeft moet daar niets over horen."""
    c = _met_ingangen(make_coordinator, hass)

    assert not [g for g in c.get_input_health() if "Airco" in g["naam"]]


def test_the_azimuth_case_is_covered(make_coordinator, hass):
    """De aanleiding zelf: sun.sun zonder azimuth-attribuut."""
    c = _met_ingangen(make_coordinator, hass)
    hass.states.set("sun.sun", "above_horizon", {"elevation": 39.5})

    gebreken = {g["naam"]: g for g in c.get_input_health()}

    assert "Stand van de zon (azimut)" in gebreken
    assert "Hoogte van de zon" not in gebreken
    assert "profiel" in gebreken["Stand van de zon (azimut)"]["blokkeert"]


def test_a_broken_input_lands_in_the_doing_pile(make_coordinator, hass):
    """Wachten helpt hier niet: er moet iets gebeuren."""
    c = _met_ingangen(make_coordinator, hass)
    hass.states.set("sun.sun", "above_horizon", {"elevation": 39.5})

    overzicht = c.get_pending_overview()

    assert overzicht["aantal_doen"] > 0
    assert any(
        "azimut" in r["naam"].lower() for r in overzicht["doen"]
    )


def test_every_defect_says_what_stalls(make_coordinator, hass):
    """Zonder te zeggen wát er stilvalt, is het net zo nietszeggend als
    "0/5 heldere dagen"."""
    c = _met_ingangen(make_coordinator, hass)

    for gebrek in c.get_input_health():
        assert gebrek["blokkeert"]
        assert gebrek["advies"]


# --- v1.51.0: een stille sensor is geen instelprobleem ---------------


def _zonder_uitkomst(make_coordinator, hass, ingesteld=True):
    from custom_components.energy_management_system.const import (
        CONF_AVAILABLE_ENERGY_SENSOR,
    )

    config = {CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar"} if ingesteld else {}
    c = make_coordinator(config)
    c.mpc_horizon_quarters_used = 0
    c.mpc_note = "Beschikbare-energie-sensor niet uitleesbaar."
    c.digital_twin_trajectory = []
    c.digital_twin_note = "Beschikbare-energie-sensor niet uitleesbaar."
    return c


def test_a_sensor_that_briefly_stayed_silent_is_waiting_not_doing(
    make_coordinator, hass
):
    """Gemeld met screenshot: onder "Vraagt een handeling" stonden `mpc`
    en `digital_twin` met "Beschikbare-energie-sensor niet uitleesbaar"
    - terwijl die sensor gewoon is ingesteld en het meestal doet.

    Zonder uitkomst was de status altijd "niet geconfigureerd", en dat
    is de enige status die in de doen-stapel belandt. Het overzicht
    vroeg dus om een handeling die er niet is.
    """
    from datetime import datetime, timezone

    c = _zonder_uitkomst(make_coordinator, hass)
    c._update_advisory_readiness(datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc))

    assert c.advisory_readiness["mpc"]["status"] == "onvoldoende_data"
    assert c.advisory_readiness["digital_twin"]["status"] == "onvoldoende_data"


def test_a_missing_sensor_is_still_a_doing_item(make_coordinator, hass):
    """Ontbreekt de entiteit echt, dan valt er wél iets in te stellen."""
    from datetime import datetime, timezone

    c = _zonder_uitkomst(make_coordinator, hass, ingesteld=False)
    c._update_advisory_readiness(datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc))

    assert c.advisory_readiness["mpc"]["status"] == "niet_geconfigureerd"


def test_a_sensor_that_stays_away_becomes_a_doing_item(
    make_coordinator, hass
):
    """Een enkele gemiste uitlezing hoort niemand wakker te maken, maar
    een sensor die minutenlang zwijgt wel."""
    from datetime import datetime, timedelta, timezone

    nu = datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc)
    c = _zonder_uitkomst(make_coordinator, hass)
    c._sensor_unavailable_since["sensor.beschikbaar"] = nu - timedelta(hours=1)

    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: nu
    c._update_advisory_readiness(nu)

    assert c.advisory_readiness["mpc"]["status"] == "niet_geconfigureerd"
    assert "controleer de sensor" in c.advisory_readiness["mpc"]["reden"]
