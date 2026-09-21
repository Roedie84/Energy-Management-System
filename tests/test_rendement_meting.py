"""Het accurendement werd gemeten op een dode reeks (v5.9).

De betrouwbaarheidskaart meldde al negen dagen hetzelfde:

    Accu-rendement - 7 laadcycli, bruikbaar als richting, betrouwbaar
    vanaf 20.

Die zeven komen uit `learned_efficiency_history`, en in de code staat
letterlijk: *"wordt sinds de invoering van de halve cycli NERGENS meer
bijgeschreven - hij staat alleen nog in de opslag en dient als
terugval"*. De kaart telde dus een reeks die nooit groeit. Hij blijft
voor altijd op zeven en kan nooit betrouwbaar worden.

Erger: het echte leren - laden en ontladen apart, sinds v1.32.0 - heeft
na negenenveertig dagen NUL metingen:

    charge_efficiency_history      0
    discharge_efficiency_history   0
    learned_efficiency_history     7  (bevroren)

Het retourrendement van 84,6% op het dashboard komt dus uit die bevroren
reeks - met waarden van 56,4% en 97,6% die de huidige grenzen als
onmogelijk afwijzen. En dat getal stuurt de reserve en de kostprijs.

Wat er is nagekeken: de logica WERKT. Over het echte dagverloop, met de
voorraad afgeleid uit de laadstand, levert hij tien ontlaad- en negen
laadmetingen op, rond de 84%. Dus het signaal is goed; wat er in bedrijf
misgaat, is uit een export niet te zien, want elke afwijzing werd
alleen op DEBUG-niveau gelogd.

Deze versie repareert dat blind niet. Ze maakt het zichtbaar: de kaart
telt de echte reeksen, elke afwijzing wordt geteld met de laatste reden
erbij, en na zeven dagen zonder meting komt er een aandachtspunt. De
volgende export laat dan zien waar het vastloopt.
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
