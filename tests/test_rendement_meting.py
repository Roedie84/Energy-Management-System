"""Het accurendement werd gemeten op een dode reeks (v5.9).

De betrouwbaarheidskaart meldde al negen dagen hetzelfde:

    Accu-rendement - 7 laadcycli, bruikbaar als richting, betrouwbaar
    vanaf 20.

Die zeven komen uit `learned_efficiency_history`, en in de code staat
letterlijk: *"wordt sinds de invoering van de halve cycli NERGENS meer
bijgeschreven - hij staat alleen nog in de opslag en dient als
terugval"*. De kaart telde dus een reeks die nooit groeit. Hij blijft
voor altijd op zeven en kan nooit betrouwbaar worden.

CORRECTIE (v5.10). In v5.9 stond hier dat het echte leren - laden en
ontladen apart - na negenenveertig dagen NUL metingen had. Dat was fout.
`charge_efficiency_history` stond niet in de export, en ik las afwezig
als leeg. De volgende export liet twintig per richting zien - het
plafond. Het leren werkte al die tijd, en het retourrendement van 84,6%
komt uit die echte metingen.

Wat wél klopte: de kaart telde de oude, dode reeks. Dat is hier
gerepareerd. De afwijzingsteller blijft staan, omdat afwijzingen alleen
naar DEBUG sturen hoe dan ook onzichtbaar is.
"""
import pytest


def test_de_kaart_telt_de_halve_cycli(make_coordinator, hass):
    c = make_coordinator({})
    c.learned_efficiency_history = [80.0] * 7
    c.charge_efficiency_history = [90.0] * 12
    c.discharge_efficiency_history = [88.0] * 12

    regel = next(
        r for r in c.get_reliability_overview() if r["naam"] == "Accu-rendement"
    )

    assert "12" in regel["reden"]
    assert "7 laadcycli" not in regel["reden"]


def test_zonder_halve_cycli_zegt_de_kaart_dat(make_coordinator, hass):
    """Niet stilzwijgend op de oude reeks terugvallen."""
    c = make_coordinator({})
    c.learned_efficiency_history = [80.0] * 7
    c.charge_efficiency_history = []
    c.discharge_efficiency_history = []

    regel = next(
        r for r in c.get_reliability_overview() if r["naam"] == "Accu-rendement"
    )

    assert "0" in regel["reden"]


def test_afwijzingen_worden_geteld(make_coordinator, hass):
    """Die gingen alleen naar DEBUG, en daardoor was 49 dagen niets zien
    niet van een werkende meting te onderscheiden."""
    c = make_coordinator({})
    c._efficiency_segment_direction = 1
    c._efficiency_segment_ac_kwh = 2.0
    c._efficiency_segment_start_kwh = 3.0
    c.rendement_afwijzingen = {}

    # 2,0 kWh eruit terwijl de voorraad maar 1,5 daalt: 133%, onmogelijk
    c._sluit_rendementsstuk(1.5)

    assert c.rendement_afwijzingen["te_hoog"] == 1
    assert c.rendement_afwijzingen["laatste"]["percentage"] > 100


def test_te_korte_stukken_worden_ook_geteld(make_coordinator, hass):
    c = make_coordinator({})
    c._efficiency_segment_direction = 1
    c._efficiency_segment_ac_kwh = 0.4
    c._efficiency_segment_start_kwh = 3.0
    c.rendement_afwijzingen = {}

    c._sluit_rendementsstuk(2.6)

    assert c.rendement_afwijzingen["te_kort"] == 1


def test_na_zeven_dagen_zonder_meting_een_aandachtspunt(make_coordinator, hass):
    """Stil falen hoort luid te worden."""
    c = make_coordinator({})
    c.charge_efficiency_history = []
    c.discharge_efficiency_history = []
    c.rendement_afwijzingen = {"te_hoog": 40, "te_kort": 300}
    c.bruikbare_capaciteit_kwh = lambda: 8.64

    regels = c._aandachtspunten_over_de_integratie()

    assert any("rendement" in r.lower() for r in regels)


def test_de_afwijzingen_staan_in_de_export(make_coordinator, hass):
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "rendement_afwijzingen" in bron
