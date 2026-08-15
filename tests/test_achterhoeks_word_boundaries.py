"""De Achterhoekse vertaling op hele woorden (v2.0.7).

Gevraagd: "Verder nog fouten, textuele fouten of iets dergelijks
gevonden?" - en toen bleek dat de meldingsteksten twee echte fouten
droegen:

    "de diagnostiek-export hoort weer 'n JSON-bestand te gefkes"
    "1 onderdeel kan zichzelf neet berekenen: gezunnedheid"

De vervanging gebruikte `str.replace` zonder woordgrenzen. "geven" bevat
"even" en werd "g" + "efkes"; "gezondheid" bevat "zon" en werd "ge" +
"zunne" + "dheid".
"""
import pytest


@pytest.fixture
def vertaal(make_coordinator, hass):
    c = make_coordinator({})
    return c._naar_achterhoeks


def test_geven_is_not_mangled(vertaal):
    """"geven" bevat "even"; dat werd "gefkes"."""
    assert "gefkes" not in vertaal("Het hoort een bestand te geven.")


def test_gezondheid_is_not_mangled(vertaal):
    """"gezondheid" bevat "zon"; dat werd "gezunnedheid"."""
    assert "gezunnedheid" not in vertaal("De gezondheid van de accu.")


def test_the_real_words_are_still_replaced(vertaal):
    """De reparatie mag de vertaling niet uitschakelen."""
    assert "efkes" in vertaal("Wacht even.")
    assert "zunne" in vertaal("De zon schijnt.")


def test_a_word_at_the_start_and_end_still_counts(vertaal):
    """Woordgrenzen mogen het eerste en laatste woord niet overslaan."""
    assert "Zunne" in vertaal("Zon op het dak")
    assert "efkes" in vertaal("Wacht nog even")


def test_no_word_is_replaced_inside_another(make_coordinator, hass):
    """De brede toets: geen enkel woord uit de tabel mag MIDDENIN een
    ander woord worden vervangen.

    Niet de uitkomst toetsen maar het mechanisme - "vannacht" bevat
    terecht "nacht" in het Nederlandse origineel, dus daar valt niets
    over te zeggen. Wat wél moet gelden: een woord dat als deel van een
    langer woord voorkomt, blijft ongemoeid.
    """
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_WOORDEN,
    )

    c = make_coordinator({})

    # Voor elk woord uit de tabel: plak het in een langer woord en
    # controleer dat het daar niet wordt aangeraakt.
    for nl, _ach in ACHTERHOEKS_WOORDEN:
        if " " in nl or len(nl) < 3:
            continue
        langer = f"xx{nl}xx"
        assert c._naar_achterhoeks(f"Dit is {langer}.").count(langer) == 1, (
            f"{nl!r} werd vervangen binnen {langer!r}"
        )


def test_the_plural_in_t_is_correct_dialect():
    """Even stond hier "Alle onderdelen rekenen weer", omdat "rekent" als
    een meervoudsfout oogde. Dat is het niet: het Achterhoeks heeft een
    EENVORMIG MEERVOUD op -t, net als "Prieze gaot onder nul" twee regels
    verderop.
    """
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_TITELS,
    )

    assert ACHTERHOEKS_TITELS["interne_fout_hersteld"].endswith("rekent weer")
    assert "gaot" in ACHTERHOEKS_TITELS["negative_prices"]


def test_the_dutch_title_uses_the_right_participle():
    """"De stand is verandert" moet "veranderd" zijn - voltooid deelwoord
    na "is", geen persoonsvorm."""
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_TITELS,
    )

    assert ACHTERHOEKS_TITELS["mode_change"] == "De stand is veranderd"
