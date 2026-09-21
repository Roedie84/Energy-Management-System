"""Elk bewaard veld staat in de export, met hoeveel erin zit (v5.10).

In v5.9 concludeerde ik dat het rendementsleren na negenenveertig dagen
NUL metingen had. Ik las `charge_efficiency_history` uit de export, kreeg
niets terug, en schreef een diagnose. De volgende export liet zien:

    metingen_laden     20
    metingen_ontladen  20

Twintig per richting, het plafond. Het leren werkte al die tijd. Het
veld stond gewoon niet in de export.

Dat bleek geen uitzondering. Van de 193 bewaarde velden stonden er 119
NIET in de coordinator-dump - waaronder beide rendementsreeksen, de
capaciteitstrend, de cycluskosten en de kostentellers. Afwezig in de
export was dus niet van leeg te onderscheiden, en dat is precies waar ik
op struikelde.

Nu staat elk bewaard veld in `opslag_overzicht`, met het type en hoeveel
erin zit. Niet de volledige inhoud - het dagverloop alleen al is duizenden
regels - maar genoeg om te zien dat een veld bestaat en gevuld is.
"""
import pytest


def test_elk_bewaard_veld_staat_in_het_overzicht(make_coordinator, hass):
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    c = make_coordinator({})
    uit = c.get_opslag_overzicht()

    ontbreekt = sorted(set(PERSISTED_FIELDS) - set(uit["velden"]))
    assert not ontbreekt, ontbreekt


def test_een_lijst_toont_zijn_lengte(make_coordinator, hass):
    """Het geval van v5.9: 20 metingen, en de export zei niets."""
    c = make_coordinator({})
    c.charge_efficiency_history = [90.0] * 20

    veld = c.get_opslag_overzicht()["velden"]["charge_efficiency_history"]

    assert veld["aantal"] == 20
    assert veld["soort"] == "lijst"


def test_een_leeg_veld_is_te_onderscheiden_van_een_ontbrekend(make_coordinator, hass):
    """Waar het om ging: leeg is iets anders dan niet geëxporteerd."""
    c = make_coordinator({})
    c.charge_efficiency_history = []

    veld = c.get_opslag_overzicht()["velden"]["charge_efficiency_history"]

    assert veld["aantal"] == 0
    assert veld["leeg"] is True


def test_een_getal_toont_zijn_waarde(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_cumulative_discharged_kwh = 123.4

    veld = c.get_opslag_overzicht()["velden"]["battery_cumulative_discharged_kwh"]

    assert veld["waarde"] == 123.4


def test_het_overzicht_staat_in_de_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "opslag_overzicht" in bron


def test_de_rendementsreeksen_staan_ook_volledig_in_de_export(make_coordinator, hass):
    """Die stuurden de reserve en de kostprijs, en ontbraken. Twintig
    getallen per richting is klein genoeg om volledig mee te sturen.

    Het GEDRAG getoetst, niet de tekst: de eerste versie van deze toets
    zocht de naam in diagnostics.py, terwijl de reeksen via
    `get_rendement_afwijzingen` in de export komen. Dat is de les van
    v4.19 die ik hier bijna opnieuw overtrad."""
    c = make_coordinator({})
    c.charge_efficiency_history = [90.0, 91.0]
    c.discharge_efficiency_history = [88.0, 89.0]

    uit = c.get_rendement_afwijzingen()

    assert uit["charge_efficiency_history"] == [90.0, 91.0]
    assert uit["discharge_efficiency_history"] == [88.0, 89.0]
