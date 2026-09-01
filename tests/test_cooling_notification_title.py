"""De koelmelding zegt WAT er gebeurt (v3.1.0).

Gemeld met een melding van 17 augustus 14:34:

    Accukoeling an of uut
    Accu 30.0°C, buiten 20.4°C, delta 9.6°C, vermogen 1080W - accu
    30.0°C, nog maor 9.6°C boven buiten en 1080W belasting

"Maar het is of hij is aan (koelen) of hij is uit (niet koelen)."

Terecht. De Nederlandse titel maakte dat onderscheid wel ("koeling AAN" /
"koeling UIT"), maar de Achterhoekse vertaling gooide het weg: die
gebruikte één vaste titel voor de hele soort.
"""
from custom_components.energy_management_system.const import (
    ACHTERHOEKS_TITELS,
    ACHTERHOEKS_TITELS_PER_ACTIE,
)


def test_the_dutch_title_already_said_it():
    """Ter herinnering waar de informatie zat - en dus wat de vertaling
    weggooide."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "koeling AAN" in bron
    assert "koeling UIT" in bron


def test_switching_on_and_off_get_their_own_title():
    aan = ACHTERHOEKS_TITELS_PER_ACTIE[("battery_cooling", "aan")]
    uit = ACHTERHOEKS_TITELS_PER_ACTIE[("battery_cooling", "uit")]

    assert aan != uit
    assert "an" in aan
    assert "uut" in uit


def test_no_fixed_title_says_both_at_once():
    """"an of uut" laat de lezer raden. Een vaste titel per soort werkt
    alleen als die soort altijd hetzelfde betekent."""
    assert "an of uut" not in ACHTERHOEKS_TITELS.get("battery_cooling", "")


def test_the_translation_picks_on_the_action(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_ACHTERHOEKS,
    )

    c = make_coordinator({CONF_ACHTERHOEKS: True})

    aan = c._naar_achterhoeks("🔋 Accu: koeling AAN", "battery_cooling", "aan")
    uit = c._naar_achterhoeks("🔋 Accu: koeling UIT", "battery_cooling", "uit")

    assert aan != uit


def test_without_an_action_it_falls_back(make_coordinator, hass):
    """Andere soorten hebben geen actie en houden hun vaste titel."""
    from custom_components.energy_management_system.const import (
        CONF_ACHTERHOEKS,
    )

    c = make_coordinator({CONF_ACHTERHOEKS: True})

    # v3.95.0: `mode_change` heeft geen vaste titel meer - die bouwt de
    # stand er zelf in. Een soort die er nog WEL een heeft, doet het
    # hier voor.
    titel = c._naar_achterhoeks("Iets anders", "battery_wont_last_night")

    assert titel == ACHTERHOEKS_TITELS["battery_wont_last_night"]


def test_the_action_is_derived_from_the_dutch_title():
    """Zodat er geen extra parameter door de hele meldingsketen hoeft."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("if self.achterhoeks:")
    blok = bron[kop : kop + 900]

    assert '"AAN" in title' in blok
    assert '"UIT" in title' in blok


def test_every_kind_with_opposite_actions_is_covered():
    """Vangnet: komt er een soort bij waarvan de titel twee kanten op
    kan, dan hoort die hier te staan in plaats van in een vage vaste
    titel."""
    verdacht = [
        soort
        for soort, titel in ACHTERHOEKS_TITELS.items()
        if " of " in titel and soort != "sluipverbruik"
    ]

    assert not verdacht, (
        "deze soorten hebben een titel die twee kanten op kan - zet ze in "
        f"ACHTERHOEKS_TITELS_PER_ACTIE: {verdacht}"
    )
