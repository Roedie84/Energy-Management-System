"""De ijklijnkaart toont eisen en uitkomst (v4.9).

Gemeld met een schermafdruk:

    Gevulde bakjes zonnestand   0 van 3
    Dagen per bakje             9, 9, 9, 8, 8, 8, 8, 3
    Bruikbare paren forecast_thuis   300 van 300
    Bruikbare paren openweathermap   300 van 300
    Helderheid nu               102%

Drie dingen. "0 van 3" klopt, maar nergens staat dat een bakje pas
gevuld is bij zestig metingen over TIEN dagen - je ziet alleen een nul
naast rijen van acht en negen, en dat leest als stilstand terwijl het
morgen omslaat. "300 van 300" leest als een gehaalde eis, maar 300 is
de BEWAARGRENS; de eis is honderd paren. En de uitkomst - de
rangordescore per bron, waar deze hele meting voor is gebouwd - stond
er niet, terwijl hij wel wordt berekend.
"""
import pytest


def test_de_eisen_staan_in_het_overzicht(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        HELDERHEID_MIN_DAGEN_PER_BAKJE,
        HELDERHEID_MIN_PAREN,
    )

    c = make_coordinator({})

    uit = c.get_helderheid_ijking()

    assert uit["dagen_per_bakje_nodig"] == HELDERHEID_MIN_DAGEN_PER_BAKJE
    assert uit["paren_nodig"] == HELDERHEID_MIN_PAREN


def test_de_dagen_per_bakje_dragen_hun_eis(make_coordinator, hass):
    """Niet "9" maar "9 van 10" - dan is te zien hoe dicht het is."""
    c = make_coordinator({})
    c.helderheid_dagen = {"10.0": {"a"} | {f"d{i}" for i in range(8)}, "45.0": {"x"}}

    uit = c.get_helderheid_ijking()

    assert uit["dagen_per_bakje_met_eis"]["10.0"] == "9/10"
    assert uit["dagen_per_bakje_met_eis"]["45.0"] == "1/10"


def test_bijna_gevulde_bakjes_worden_genoemd(make_coordinator, hass):
    """"0 van 3" naast rijen van negen leest als stilstand."""
    c = make_coordinator({})
    c.helderheid_dagen = {
        f"{10 + i * 5}.0": {f"d{d}" for d in range(9)} for i in range(3)
    }

    uit = c.get_helderheid_ijking()

    assert uit["bakjes_bijna_gevuld"] == 3
    assert "1 dag" in uit["wat_ontbreekt"] or "morgen" in uit["wat_ontbreekt"]


def test_de_kaart_toont_de_scores():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    kaart = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    i = kaart.index("ijklijn")

    # v4.9: de kaart leest klaar opgemaakte regels uit de coordinator -
    # het sjabloon staat op de ratel voor logica.
    assert "voortgang_regels" in kaart
    assert "dagen_per_bakje_nodig" in kaart
