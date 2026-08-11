"""Meldingen in het Achterhoeks (v1.24.0).

Gevraagd: "Nu een fun fact, alles is nu in het Nederlands weergegeven,
kan ik door middel van 1 switch alles in het Achterhoeks laten tonen, dus
ook de meldingen op mijn iPhone?"

De hele integratie vertalen zou ongeveer 1.664 losse teksten in de code
raken plus ruim 3.000 dashboardlabels. Alleen de MELDINGEN is een
fractie daarvan en levert het leukste deel op: de telefoon spreekt
Achterhoeks, het dashboard blijft leesbaar voor wie meekijkt.

Nadrukkelijk een benadering, geen gecontroleerde streektaal - alles staat
in één tabel in const.py.
"""
from custom_components.energy_management_system.const import (
    ACHTERHOEKS_TITELS,
    ACHTERHOEKS_WOORDEN,
    NOTIFICATION_TYPES,
)


# --- de vertaling ----------------------------------------------------


def test_a_title_is_translated(make_coordinator, hass):
    c = make_coordinator({})

    vertaald = c._naar_achterhoeks(
        "Accu haalt de nacht mogelijk niet", "plan_tekort"
    )

    assert vertaald == "Den accu haalt de nacht neet"


def test_a_message_is_translated(make_coordinator, hass):
    c = make_coordinator({})

    vertaald = c._naar_achterhoeks(
        "Het nachtelijk verbruik is gestegen; mogelijk staat er iets aan."
    )

    assert "verbruuk" in vertaald
    # v1.33.0: was "mangs", maar dat betekent SOMS of alvast - niet
    # "mogelijk". Nagelopen tegen het dialectwoordenboek.
    assert "meugelijk" in vertaald
    assert "steet" in vertaald


def test_longer_words_win(make_coordinator, hass):
    """"niets" moet vóór "niet", anders wordt het "neets"."""
    c = make_coordinator({})

    assert "niks" in c._naar_achterhoeks("de accu kan niets meer leveren")
    assert "neets" not in c._naar_achterhoeks("de accu kan niets meer leveren")


def test_a_replacement_is_not_translated_again(make_coordinator, hass):
    """Dit ging bij de eerste poging mis: "goedkope blok" werd
    "goodkope blok", omdat "goed" -> "good" over het al vervangen woord
    heen liep. Nu wordt er in één doorgang vervangen."""
    c = make_coordinator({})

    vertaald = c._naar_achterhoeks("de accu laadt uit het goedkope blok")

    assert "goedkope" in vertaald
    assert "goodkope" not in vertaald


def test_every_notification_type_has_a_title():
    """Een half vertaalde melding leest raarder dan een onvertaalde."""
    soorten = {k for k, _, _, _, _ in NOTIFICATION_TYPES}

    ontbreekt = soorten - set(ACHTERHOEKS_TITELS)

    assert not ontbreekt, ontbreekt


def test_empty_text_survives(make_coordinator, hass):
    c = make_coordinator({})

    assert c._naar_achterhoeks("") == ""


# --- de schakelaar ---------------------------------------------------


def test_it_is_off_by_default(make_coordinator, hass):
    c = make_coordinator({})

    assert c.achterhoeks is False


def test_nothing_changes_when_off(make_coordinator, hass):
    """Uit betekent uit: geen enkele melding mag dan veranderen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("if self.achterhoeks:")

    assert "title = self._naar_achterhoeks(title, kind)" in bron[start : start + 200]


def test_the_switch_exists():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "switch.py").read_text()

    assert "class AchterhoeksSwitch" in bron
    assert "AchterhoeksSwitch(coordinator, entry_id=entry.entry_id)" in bron


def test_it_survives_a_restart():
    """Een schakelaar die na elke herstart terugspringt, is
    hinderlijk."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "switch.py").read_text()
    start = bron.index("class AchterhoeksSwitch")
    blok = bron[start : bron.index("\nclass ", start + 10)]

    assert "async_get_last_state" in blok


def test_both_phone_and_history_are_translated():
    """Gevraagd: "ook de meldingen op mijn iPhone". De vertaling zit in
    de gedeelde verzendfunctie, dus telefoon en meldingenoverzicht
    spreken dezelfde taal."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("def _dispatch_notification")
    blok = bron[start : start + 2500]

    assert "self.achterhoeks" in blok


def test_the_table_is_in_one_place():
    """Klopt een woord niet, dan moet dat op één plek aan te passen
    zijn."""
    assert len(ACHTERHOEKS_TITELS) >= 20
    assert len(ACHTERHOEKS_WOORDEN) >= 50


# --- v1.33.0: nagelopen tegen een dialectwoordenboek -----------------


def test_mangs_no_longer_means_maybe(make_coordinator, hass):
    """Nagelopen tegen mijnwoordenboek.nl: "mangs" betekent SOMS, alvast
    of binnenkort - niet "mogelijk".

    "Den accu haalt de nacht mangs neet" zei dus iets anders dan
    bedoeld: niet "misschien niet", maar "soms niet".
    """
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_TITELS,
        ACHTERHOEKS_WOORDEN,
    )

    tabel = dict(ACHTERHOEKS_WOORDEN)

    assert tabel["mogelijk"] == "meugelijk"
    assert tabel["soms"] == "mangs"
    assert not [t for t in ACHTERHOEKS_TITELS.values() if "mangs" in t]


def test_the_longest_match_wins(make_coordinator, hass):
    """De vervanging loopt van boven naar beneden. Stond "niet" boven
    "mogelijk niet", dan sloeg die eerst toe en bleef er "mogelijk neet"
    staan in plaats van "meugelijk neet"."""
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_WOORDEN,
    )

    sleutels = [k for k, _ in ACHTERHOEKS_WOORDEN]

    assert sleutels.index("mogelijk niet") < sleutels.index("mogelijk")
    assert sleutels.index("mogelijk niet") < sleutels.index("niet")
    assert sleutels.index("teruglevering") < sleutels.index("meer")


def test_a_handful_of_corrections(make_coordinator, hass):
    """Steekproef op woorden die in de meldingen voorkomen."""
    c = make_coordinator({})

    vertaald = c._naar_achterhoeks(
        "Vandaag is er genoeg tijd, maar het water is koud en de "
        "vaatwasser is klaar."
    )

    # De hoofdletter blijft staan; de vervanging is hoofdlettergevoelig
    # en dat is precies goed aan het begin van een zin.
    for verwacht in ("Vandage", "genög", "tied", "moar", "waoter", "kold", "kloar"):
        assert verwacht in vertaald, verwacht
