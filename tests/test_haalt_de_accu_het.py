"""Laagste 19% en toch eind 10% (v3.95.2).

Gemeld met een schermafdruk van de tegel "Haalt de accu het?":

    Ja, geen kwartier zonder accu. Laagste 19%, eind 10%, € 0.8 over 26
    uur.

Een eindstand die LAGER is dan de laagste stand kan niet. Tenzij je weet
dat het over twee verschillende vensters gaat, en dat staat er niet:

- `laagste_soc_tot_bijladen_procent` loopt tot het volgende goedkope
  blok. Dat is bewust zo sinds v1.48.0: "Laagste 10% op de landingstegel
  ging over morgenochtend laat, niet over vannacht - en dat is wel wat
  je erin leest."
- `eind_soc_procent` staat aan het eind van de HELE planning, hier 26
  uur verderop.

Allebei goed berekend. Naast elkaar op één regel spreken ze elkaar
tegen.

Daar komt bij dat die 10% de harde ondergrens zelf is. "Ja" met nul
marge aan het eind is een ander antwoord dan "Ja" met ruimte over.
"""
import pytest


def _samenvatting(c, **velden):
    basis = {
        "beschikbaar": True,
        "kwartieren": 104,
        "tekort_kwartieren": 0,
        "laagste_soc_tot_bijladen_procent": 19,
        "eind_soc_procent": 10,
        "min_soc_procent_hard": 10,
        "verwachte_opbrengst_eur": 0.8,
    }
    basis.update(velden)
    c.get_quarter_plan_summary = lambda now=None: basis
    return c.get_quarter_plan_summary()


def test_het_venster_van_de_laagste_stand_staat_erbij(make_coordinator, hass):
    """Zonder dat woord lijkt 19% de laagste van de hele 26 uur."""
    c = make_coordinator({})
    c.last_cheap_block_start = None

    zin = c.haalt_de_accu_het_zin(_samenvatting(c))

    assert "tot het bijladen" in zin


def test_het_eindvenster_staat_erbij(make_coordinator, hass):
    c = make_coordinator({})

    zin = c.haalt_de_accu_het_zin(_samenvatting(c))

    assert "na 26 uur" in zin


def test_op_de_ondergrens_eindigen_wordt_benoemd(make_coordinator, hass):
    """10% is de harde ondergrens. "Ja" met nul marge is een ander

    antwoord dan "Ja" met ruimte over.
    """
    c = make_coordinator({})

    zin = c.haalt_de_accu_het_zin(_samenvatting(c))

    assert "ondergrens" in zin


def test_met_ruimte_over_geen_waarschuwing(make_coordinator, hass):
    c = make_coordinator({})

    zin = c.haalt_de_accu_het_zin(
        _samenvatting(c, eind_soc_procent=34)
    )

    assert "ondergrens" not in zin
    assert "34%" in zin


def test_een_tekort_blijft_voorop_staan(make_coordinator, hass):
    """De vraag is "haalt de accu het", en dan is het aantal

    tekortkwartieren het antwoord - niet de eindstand.
    """
    c = make_coordinator({})

    zin = c.haalt_de_accu_het_zin(
        _samenvatting(
            c, tekort_kwartieren=3, tekort_perioden=["02:15-03:00"]
        )
    )

    assert zin.startswith("Nee")
    assert "02:15-03:00" in zin


def test_zonder_planning_geen_zin(make_coordinator, hass):
    c = make_coordinator({})

    assert c.haalt_de_accu_het_zin({"beschikbaar": False}) is None
