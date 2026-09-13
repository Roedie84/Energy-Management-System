"""De proefstand telt wat er staat, en wie al stuurt (v4.9).

Gemeld met de proefstandpagina:

    Van de 11 kandidaten meten er 3 nog; bij 1 klopt de meting maar is
    niet becijferd wat meesturen oplevert.
    ...
    ⚪ Verder vooruitkijken bij de reserve — voldoet nog niet aan de eis

Twee dingen. De samenvatting had zijn EIGEN lijst met elf aanroepen,
naast de veertien van `_bereken_proefstand`; de drie kandidaten van
v4.1, v4.5 en v4.7 stonden er niet in. Twee lijsten van hetzelfde, en de
ene liep achter - hetzelfde patroon als de reserves.

En "Verder vooruitkijken bij de reserve" STUURT sinds v3.99.18, op
verzoek. Een kandidaat die al meestuurt en tegelijk meldt dat hij niet
aan de eis voldoet, is het tegenovergestelde van wat de proefstand moet
doen. `stuurt_sinds` staat er wel in, maar de gereedheidstekst keek er
niet naar.
"""
import pytest


def test_de_samenvatting_telt_alle_kandidaten(make_coordinator, hass):
    c = make_coordinator({})

    proefstand = c.get_proefstand()
    samenvatting = proefstand["samenvatting"]

    assert samenvatting["aantal"] == len(proefstand["kandidaten"])


def test_de_samenvatting_heeft_geen_eigen_lijst():
    """De ratel: één lijst. Twee lijsten van hetzelfde liepen uiteen."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("def _proefstand_samenvatting")
    j = bron.index("\n    def ", i + 10)

    assert not re.search(r"self\._kandidaat_\w+\(", bron[i:j])


def test_een_kandidaat_die_stuurt_zegt_dat(make_coordinator, hass):
    c = make_coordinator({})

    gereed = c._met_gereedheid(
        {
            "naam": "Verder vooruitkijken bij de reserve",
            "status": "betrouwbaar",
            "stuurt_sinds": "v3.99.18",
            "mag_regelen": True,
            "zou_hebben_opgeleverd": {"te_becijferen": True, "eur": 1.48},
        }
    )

    assert gereed["gereedheid"] == "stuurt mee"
    assert "v3.99.18" in gereed["gereedheid_uitleg"]
    assert gereed.get("mag_meesturen") is not True


def test_wie_stuurt_telt_niet_als_wachtend(make_coordinator, hass):
    """De samenvatting gaat over wat er nog te beslissen valt."""
    c = make_coordinator({})
    c._bereken_proefstand = lambda: {
        "samenvatting": None,
        "kandidaten": [
            c._met_gereedheid({"naam": "A", "status": "betrouwbaar", "stuurt_sinds": "v1",
                               "zou_hebben_opgeleverd": {"te_becijferen": True}}),
            c._met_gereedheid({"naam": "B", "status": "indicatief",
                               "zou_hebben_opgeleverd": {}}),
        ],
    }
    c._proefstand_cache = None

    uit = c._proefstand_samenvatting(c._bereken_proefstand()["kandidaten"])

    assert uit["aantal"] == 2
    assert uit["stuurt_mee"] == 1
    assert uit["meet_nog"] == 1


def test_een_kandidaat_zonder_sturing_blijft_gewoon(make_coordinator, hass):
    c = make_coordinator({})

    gereed = c._met_gereedheid(
        {"naam": "B", "status": "indicatief", "zou_hebben_opgeleverd": {}}
    )

    assert gereed["gereedheid"] == "meet nog"
