"""Melding zodra een kandidaat rijp wordt (v3.12.0).

Gevraagd: "Houd je dit zelf bij middels diagnostiek?"

Het eerlijke antwoord was nee. Er is geen geheugen tussen gesprekken en
geen toegang tot dit systeem; elke diagnostiek wordt op dat moment
gelezen en is daarna weg.

Wat er wél bijhoudt is de integratie zelf. Maar dan moet de gebruiker
onthouden dat hij over drie weken moet kijken - en drie weken is lang.
Nu komt het naar hem toe.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
)

NU = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, gereedheden):
    c = make_coordinator({CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon"})
    c.set_notification_enabled("proefstand_rijp", True)
    c.get_proefstand = lambda *a, **k: {
        "kandidaten": [
            {
                "naam": naam,
                "gereedheid": g,
                "waarde": "+3.2 ct/kWh",
                "zou_hebben_opgeleverd": {"reden": "bij 40 van de 50 gunstig"},
            }
            for naam, g in gereedheden.items()
        ]
    }
    return c


def _soorten(c):
    return [m["soort"] for m in c.notification_history]


def test_a_candidate_becoming_ready_is_reported(make_coordinator, hass):
    c = _coordinator(
        make_coordinator, hass, {"Bijkopen bij een tekort": "meet nog"}
    )
    c._meld_rijpe_kandidaten(NU)

    c.get_proefstand = lambda *a, **k: {
        "kandidaten": [
            {
                "naam": "Bijkopen bij een tekort",
                "gereedheid": "klaar om mee te doen",
                "waarde": "+3.2 ct/kWh",
                "zou_hebben_opgeleverd": {"reden": "bij 40 van de 50 gunstig"},
            }
        ]
    }
    c._meld_rijpe_kandidaten(NU)

    assert "proefstand_rijp" in _soorten(c)


def test_an_already_ready_candidate_is_no_news(make_coordinator, hass):
    """Een kandidaat die al maanden klaar staat is geen nieuws - alleen
    bij de OMSLAG."""
    c = _coordinator(
        make_coordinator, hass, {"Slijtagekosten": "klaar om mee te doen"}
    )

    c._meld_rijpe_kandidaten(NU)
    aantal_na_eerste = len(_soorten(c))
    c._meld_rijpe_kandidaten(NU)

    assert len(_soorten(c)) == aantal_na_eerste


def test_a_candidate_that_is_still_measuring_says_nothing(
    make_coordinator, hass
):
    c = _coordinator(make_coordinator, hass, {"Regressiewoud": "meet nog"})

    c._meld_rijpe_kandidaten(NU)

    assert "proefstand_rijp" not in _soorten(c)


def test_winst_onbekend_is_not_ready_either(make_coordinator, hass):
    """"Winst onbekend" betekent dat de meting klopt maar niet becijferd
    is wat meesturen oplevert. Dan is meedoen een gok."""
    c = _coordinator(make_coordinator, hass, {"Prijsvorm": "winst onbekend"})

    c._meld_rijpe_kandidaten(NU)

    assert "proefstand_rijp" not in _soorten(c)


def test_the_message_names_the_value_and_the_reason(
    make_coordinator, hass
):
    """Zonder getal is de melding niet te beoordelen."""
    c = _coordinator(make_coordinator, hass, {"Iets": "meet nog"})
    c._meld_rijpe_kandidaten(NU)

    c.get_proefstand = lambda *a, **k: {
        "kandidaten": [
            {
                "naam": "Iets",
                "gereedheid": "klaar om mee te doen",
                "waarde": "+3.2 ct/kWh",
                "zou_hebben_opgeleverd": {"reden": "bij 40 van de 50 gunstig"},
            }
        ]
    }
    c._meld_rijpe_kandidaten(NU)

    bericht = next(
        m["bericht"] for m in c.notification_history if m["soort"] == "proefstand_rijp"
    )
    assert "+3.2 ct/kWh" in bericht
    assert "40 van de 50" in bericht


def test_it_survives_a_restart():
    """Anders wordt na elke herstart alles opnieuw gemeld."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "_eerder_rijpe_kandidaten" in PERSISTED_PLAIN_FIELDS


def test_a_broken_proefstand_does_not_break_the_tick(
    make_coordinator, hass
):
    """Een melding mag nooit de ronde meenemen - de fout die v3.8.0
    opleverde."""
    c = _coordinator(make_coordinator, hass, {})

    def _valt_om(*a, **k):
        raise RuntimeError("stuk")

    c.get_proefstand = _valt_om

    c._meld_rijpe_kandidaten(NU)  # mag niet opgooien


# --- v3.12.1: de melding was leeg en incompleet ----------------------


def test_a_candidate_with_toelichting_is_not_empty(make_coordinator, hass):
    """Gemeld: "4.2 ct/kWh —" met niets erachter.

    De slijtagekandidaat gebruikt `toelichting`, de andere `reden`. De
    melding las alleen `reden`, en dan blijft er een gedachtestreepje
    over zonder onderbouwing.
    """
    c = _coordinator(make_coordinator, hass, {"Slijtage": "meet nog"})
    c._meld_rijpe_kandidaten(NU)

    c.get_proefstand = lambda *a, **k: {
        "kandidaten": [
            {
                "naam": "Slijtage",
                "gereedheid": "klaar om mee te doen",
                "waarde": "4.2 ct/kWh",
                "zou_hebben_opgeleverd": {
                    "toelichting": "Over 7 dagen € 17,61 aan slijtage."
                },
            }
        ]
    }
    c._meld_rijpe_kandidaten(NU)

    bericht = next(
        m["bericht"] for m in c.notification_history if m["soort"] == "proefstand_rijp"
    )
    assert "17,61" in bericht


def test_two_candidates_at_once_are_both_named(make_coordinator, hass):
    """Er werden twee kandidaten tegelijk rijp en er kwam één bericht;
    de demping van een dag filterde de tweede weg.

    Een demping per SOORT werkt hier verkeerd: dit is geen herhaling maar
    een tweede gebeurtenis.
    """
    c = _coordinator(
        make_coordinator,
        hass,
        {"Slijtage": "meet nog", "Vasthouden": "meet nog"},
    )
    c._meld_rijpe_kandidaten(NU)

    c.get_proefstand = lambda *a, **k: {
        "kandidaten": [
            {
                "naam": "Slijtage",
                "gereedheid": "klaar om mee te doen",
                "waarde": "4.2 ct/kWh",
                "zou_hebben_opgeleverd": {"toelichting": "zeven dagen"},
            },
            {
                "naam": "Vasthouden",
                "gereedheid": "klaar om mee te doen",
                "waarde": "-8.0 ct/kWh",
                "zou_hebben_opgeleverd": {"reden": "0 van de 200 gunstig"},
            },
        ]
    }
    c._meld_rijpe_kandidaten(NU)

    berichten = [
        m["bericht"] for m in c.notification_history if m["soort"] == "proefstand_rijp"
    ]
    assert berichten
    assert "Slijtage" in berichten[-1]
    assert "Vasthouden" in berichten[-1]


def test_the_value_is_never_orphaned(make_coordinator, hass):
    """Een waarde met een gedachtestreepje en niets erachter is erger dan
    geen melding: je weet dat er iets is maar niet wat."""
    c = _coordinator(make_coordinator, hass, {"Iets": "meet nog"})
    c._meld_rijpe_kandidaten(NU)

    c.get_proefstand = lambda *a, **k: {
        "kandidaten": [
            {
                "naam": "Iets",
                "gereedheid": "klaar om mee te doen",
                "waarde": "1.0 ct",
                "zou_hebben_opgeleverd": {},
                "betrouwbaarheid": "laatste terugval",
            }
        ]
    }
    c._meld_rijpe_kandidaten(NU)

    bericht = next(
        m["bericht"] for m in c.notification_history if m["soort"] == "proefstand_rijp"
    )
    assert "laatste terugval" in bericht
    assert "— \n" not in bericht
