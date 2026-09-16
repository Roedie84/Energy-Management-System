"""De oude helderheidsparen blokkeerden de ijklijn (v4.17.1).

Gemeld met de diagnostiek van 16 september, die zichzelf tegenspreekt:

    gevulde bakjes      7 van 3 nodig
    dagen per bakje     14/10 (zeven keer gehaald)
    bruikbare paren     300 van 100 nodig
    rangordescore       nog niet te becijferen
    wat ontbreekt       "de paren beslaan pas 1 dag; 10 nodig"

Alles gehaald, en toch geen oordeel.

In v4.13 heb ik de INSTROOM van paren teruggebracht van één per ronde
naar één per uur, en de bewaargrens naar 480 gezet. Maar de
driehonderd OUDE paren zijn niet opgeruimd, en die zijn allemaal van
één dag - het per-minuut-tijdperk. Er komen twaalf nieuwe per dag bij,
dus die driehonderd schuiven er pas na vijfentwintig dagen uit. Tot die
tijd blijft "de paren beslaan 1 dag" staan, hoe lang je ook wacht.

Ik heb de instroom gerepareerd en de voorraad laten staan. Dezelfde
fout als de kandidaten die oude en nieuwe modellen mengden - in
diezelfde versie wél gescheiden.

De oude paren zijn te herkennen: vier velden, want het uur is er in
v4.13 als vijfde bij gekomen. Die gaan bij het laden weg.
"""
import pytest


def test_paren_zonder_uur_gaan_weg_bij_het_laden(make_coordinator, hass):
    c = make_coordinator({})
    c._apply_persisted_state(
        {
            "weerbron_helderheid_paren": {
                "weather.a": (
                    [[40.0, 1800.0, "30.0", "2026-09-15"]] * 300
                    + [[42.0, 1900.0, "30.0", "2026-09-16", "2026-09-16T10"]]
                )
            }
        }
    )

    paren = c.weerbron_helderheid_paren["weather.a"]

    assert len(paren) == 1
    assert paren[0][4] == "2026-09-16T10"


def test_een_bron_zonder_bruikbare_paren_verdwijnt_niet(make_coordinator, hass):
    """De bron blijft bestaan met een lege lijst - anders lijkt hij weg
    in plaats van leeg."""
    c = make_coordinator({})
    c._apply_persisted_state(
        {
            "weerbron_helderheid_paren": {
                "weather.a": [[40.0, 1800.0, "30.0", "2026-09-15"]] * 12
            }
        }
    )

    assert c.weerbron_helderheid_paren == {"weather.a": []}


def test_nieuwe_paren_blijven_ongemoeid(make_coordinator, hass):
    c = make_coordinator({})
    nieuw = [
        [40.0, 1800.0, "30.0", f"2026-09-{d:02d}", f"2026-09-{d:02d}T{u:02d}"]
        for d in range(1, 13)
        for u in range(8, 20)
    ]
    c._apply_persisted_state({"weerbron_helderheid_paren": {"weather.a": nieuw}})

    assert len(c.weerbron_helderheid_paren["weather.a"]) == len(nieuw)


def test_de_uitleg_noemt_het_opruimen(make_coordinator, hass):
    """Zodat de teller die op nul begint geen nieuw raadsel wordt."""
    c = make_coordinator({})
    c.helderheid_ijklijn = {
        b: [1500.0 + i for i in range(60)] for b in ("20.0", "30.0", "40.0")
    }
    c.helderheid_dagen = {
        b: [f"2026-09-{d:02d}" for d in range(1, 15)] for b in ("20.0", "30.0", "40.0")
    }
    c.weerbron_helderheid_paren = {"weather.a": []}

    uit = c.get_helderheid_ijking()

    assert "paren" in uit["wat_ontbreekt"].lower()


def test_geen_lezer_laat_twee_vormen_toe():
    """De ratel, en de les van dit geval.

    Toen de vorm van een bewaard veld veranderde, heb ik de lezers
    tolerant gemaakt voor BEIDE vormen. Dat leek voorzichtig, maar het
    verborg juist dat er driehonderd oude in de voorraad zaten - en die
    blokkeerden de meting wekenlang zonder dat er iets over klaagde.

    Een vormwijziging hoort bij het LADEN te worden opgeruimd, niet bij
    het lezen te worden getolereerd. Dan valt het op als het misgaat.
    """
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    tolerant = re.findall(r"len\(\w+\)\s*(?:not )?in \([\d, ]+\)", bron)

    assert not tolerant, tolerant
