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
        "Accu komt tekort", "plan_tekort"
    )

    assert vertaald == "Den accu kump tekort"


def test_a_message_is_translated(make_coordinator, hass):
    c = make_coordinator({})

    vertaald = c._naar_achterhoeks(
        "Het nachtelijk verbruik is gestegen; mogelijk staat er iets aan."
    )

    assert "verbruuk" in vertaald
    # v1.33.0: was "mangs", maar dat betekent SOMS of alvast - niet
    # "mogelijk". Nagelopen tegen het dialectwoordenboek.
    assert "meugelek" in vertaald
    assert "steet" in vertaald


def test_longer_words_win(make_coordinator, hass):
    """"niets" moet vóór "niet", anders wordt het "neets"."""
    c = make_coordinator({})

    assert "niks" in c._naar_achterhoeks("de accu kan niets meer leveren")
    assert "neets" not in c._naar_achterhoeks("de accu kan niets meer leveren")


# v3.93.1: soorten waaronder meer dan één boodschap valt, en die dus
# geen vaste titel per soort kunnen hebben.
MEERDERE_BOODSCHAPPEN = {"appliance_ready", "handmatige_stand"}


def test_a_replacement_is_not_translated_again(make_coordinator, hass):
    """Dit ging bij de eerste poging mis: "goedkope blok" werd
    "goodkope blok", omdat "goed" -> "good" over het al vervangen woord
    heen liep. Nu wordt er in één doorgang vervangen."""
    c = make_coordinator({})

    vertaald = c._naar_achterhoeks("de accu laadt uit het goedkope blok")

    assert "goedkope" in vertaald
    assert "goodkope" not in vertaald


def test_every_notification_type_has_a_title():
    """Een half vertaalde melding leest raarder dan een onvertaalde.

    v3.93.1: behalve de soorten waaronder MEER DAN ÉÉN boodschap valt.

    Gemeld: "'n Apparaat is klaor - Klaor na ongeveer 8 minuten (...)
    Maar kan dan niet zien welk apparaat." Onder `appliance_ready`
    vallen vier titels (vaatwasser, wasmachine, steelstofzuiger,
    fietsen) en onder `handmatige_stand` twee. Eén vaste titel maakte
    die onherkenbaar.

    Voor die soorten is de vertaling woord voor woord juist het goede
    antwoord: die laat de naam staan. Dat is geen half vertaalde melding
    maar een volledig vertaalde met behoud van het onderwerp.
    """
    soorten = {k for k, _, _, _, _ in NOTIFICATION_TYPES}

    ontbreekt = soorten - set(ACHTERHOEKS_TITELS) - MEERDERE_BOODSCHAPPEN

    assert not ontbreekt, ontbreekt


def test_a_kind_with_several_messages_has_no_fixed_title():
    """En andersom: staat er wél een vaste titel voor zo'n soort, dan is

    de oude fout stilletjes teruggezet.
    """
    dubbel = MEERDERE_BOODSCHAPPEN & set(ACHTERHOEKS_TITELS)

    assert not dubbel, dubbel


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

    # v1.46.0: de titel wordt opgezocht op `kind`, of - bij een
    # herstelmelding, waar `kind` bewust leeg is - op de soort waarmee
    # hij in de geschiedenis komt.
    # v3.0.2: de aanroep geeft ook de ACTIE mee, want bij de accukoeling
    # zijn aan en uit tegenovergesteld en verdient elk zijn eigen titel.
    venster = bron[start : start + 900]
    assert "title = self._naar_achterhoeks(" in venster
    assert "kind or geschiedenis_soort" in venster


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

    assert tabel["mogelijk"] == "meugelek"
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
    for verwacht in ("Vandage", "genög", "tied", "maor", "waoter", "kold", "klaor"):
        assert verwacht in vertaald, verwacht


# --- v1.35.0: gespeld volgens de WALD-spelling -----------------------


def _tabel():
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_TITELS,
        ACHTERHOEKS_WOORDEN,
    )

    return [v for _, v in ACHTERHOEKS_WOORDEN] + list(ACHTERHOEKS_TITELS.values())


def test_ao_and_never_oa():
    """De WALD-spelling kent "ao" als zelfstandig teken; "oa" bestaat
    niet. Er stond goan, moar, noar, oaver, doar en kloar.
    """
    fout = [w for w in _tabel() if "oa" in w.lower()]

    assert not fout, fout


def test_unstressed_e_is_written_as_e():
    """De e zonder klemtoon schrijf je altijd als e. Daarmee wordt -lijk
    dus -lek en -ig wordt -eg - en juist dat verschil onderscheidt het
    Achterhoeks van het Liemers, dat -ig houdt.
    """
    fout = [w for w in _tabel() if w.endswith("lijk") or w.endswith("ig")]

    assert not fout, fout


def test_the_i_j_diphthong_uses_a_hyphen():
    """i-j is een tweeklank en krijgt een streepje. De apostrof is voor
    samengetrokken woorden: he'j, da'k, lao'w.
    """
    fout = [w for w in _tabel() if "i'j" in w]

    assert not fout, fout


def test_a_separable_participle_keeps_its_hyphen():
    """Bij een scheidbaar werkwoord komt in het voltooid deelwoord een
    streepje tussen de delen: an-egeven, weg-enommen."""
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_WOORDEN,
    )

    tabel = dict(ACHTERHOEKS_WOORDEN)

    assert tabel["opgewekt"] == "op-ewekt"
    assert tabel["uitgesteld"] == "uut-esteld"
    assert tabel["bijgeladen"] == "bi-j-elaojen"


# --- v1.46.0: ook de herstelmeldingen --------------------------------


def test_a_recovery_notification_is_translated(make_coordinator, hass):
    """Gemeld: "Niet in het achterhoeks?" bij "✅ Accu haalt de nacht
    weer".

    De vertaling zelf klopte - alles wat de deur uitgaat gaat er
    doorheen. Maar de herstelmeldingen schreven daarna ZELF een regel in
    de geschiedenis, met hun eigen onvertaalde tekst. Op de telefoon
    stond dus Achterhoeks en in het meldingenoverzicht Nederlands.
    """
    c = make_coordinator({})
    c.achterhoeks = True

    c._meld_herstel(
        "plan_tekort",
        "✅ Accu komt niet meer tekort",
        "Er is weer genoeg opgeslagen om tot het goedkope blok te overbruggen.",
    )

    regel = c.notification_history[-1]
    assert regel["soort"] == "plan_tekort_hersteld"
    assert "genög" in regel["bericht"]


def test_the_recovery_title_is_translated_too(make_coordinator, hass):
    """Woordvervanging alleen maakt van "Accu haalt de nacht weer" niets
    Achterhoeks: geen van die woorden staat in de tabel. De titels van
    de PROBLEEMmeldingen stonden er wel in, die van het herstel niet."""
    c = make_coordinator({})
    c.achterhoeks = True

    c._meld_herstel("plan_tekort", "✅ Accu komt niet meer tekort", "x")

    assert c.notification_history[-1]["titel"] == "Den accu kump neet meer tekort"


def test_every_recovery_kind_has_an_achterhoeks_title():
    """Anders valt er stilzwijgend weer een terug op Nederlands."""
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_TITELS,
        NOTIFICATION_RECOVERY_KINDS,
    )

    for kind in NOTIFICATION_RECOVERY_KINDS:
        assert f"{kind}_hersteld" in ACHTERHOEKS_TITELS, kind


def test_dutch_stays_dutch_when_the_switch_is_off(make_coordinator, hass):
    c = make_coordinator({})
    c.achterhoeks = False

    c._meld_herstel("plan_tekort", "✅ Accu komt niet meer tekort", "Er is weer genoeg.")

    assert c.notification_history[-1]["titel"] == "✅ Accu komt niet meer tekort"


def test_a_varying_title_keeps_its_distinction(make_coordinator, hass):
    """Gemeld: "Melding accu koeling aan/uit is niet goed (...) Maar het
    is of hij is aan (koelen) of hij is uit (niet koelen)."

    De Nederlandse titel zei wel "koeling AAN" of "koeling UIT", maar de
    vertaling verving de hele titel door "Accukoeling an of uut" - en
    daarmee verdween precies de informatie waar het om ging.
    """
    c = make_coordinator({})

    aan = c._naar_achterhoeks("🔋 Accu: koeling AAN", "battery_cooling", "aan")
    uit = c._naar_achterhoeks("🔋 Accu: koeling UIT", "battery_cooling", "uit")

    assert aan != uit
    assert "an" in aan and "uut" in uit


def test_every_varying_title_has_both_actions():
    """Bij het nazoeken bleken er VIER meldingen met een wisselende
    titel, niet één. Elk hoort zijn onderscheid te houden."""
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_TITELS_PER_ACTIE,
    )

    soorten = {soort for soort, _actie in ACHTERHOEKS_TITELS_PER_ACTIE}

    for soort in (
        "battery_cooling",
        "appliance_ready",
        "appliance_cheap_moment",
        "device_drift",
    ):
        assert soort in soorten, soort


def test_the_action_also_appears_in_the_message():
    """Staat de actie ook in het bericht, dan gaat hij niet verloren als
    de titel wordt vervangen of afgekapt."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index('kind="battery_cooling"')
    blok = bron[kop - 1200 : kop]

    assert "De ventilator gaat" in blok
