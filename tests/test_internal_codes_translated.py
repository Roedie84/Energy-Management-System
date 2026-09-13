"""Interne codes worden vertaald op het dashboard (v1.16.2).

Gevraagd na een reeks kapotte kaarten: "Vooral kijken of er nog meer
zaken gerepareerd dienen te worden, ik baal dat er zoveel kapot is nu."

Een systematische controle van alle zeventien kaarten die een rauwe
sensortoestand toonden, leverde vier gevallen op:

- "Laatste reden: expensive_quarter"
- "Steelstofzuiger: wacht_op_goedkoop_blok"
- "Fietsladers: wacht_op_goedkoop_blok"
- "Kandidaten: 0" (een getal zonder context)

Dezelfde fout als bij de energie-check in v1.15.9. De codes zelf blijven
ongewijzigd - daar wordt in de logica op vergeleken; alleen de weergave
vertaalt.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml
from custom_components.energy_management_system.const import (
    APPLIANCE_STATE_LABELS,
    DECISION_REASON_LABELS,
)

PAKKET = Path(pkg.__file__).parent


def _kaarten():
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    alle = []
    for view in data["views"]:
        kaarten = list(view.get("cards") or [])
        for sectie in view.get("sections") or []:
            kaarten += sectie.get("cards") or []
        for kaart in list(kaarten):
            kaarten += kaart.get("cards") or []
        alle += kaarten
    return alle


def _kaart_voor(sleutel: str) -> dict:
    return next(k for k in _kaarten() if sleutel in str(k.get("entity", "")))


# --- de vier gevallen ------------------------------------------------


def test_the_decision_reason_is_translated():
    kaart = str(_kaart_voor("last_decision_reason"))

    assert "duur kwartier" in kaart
    assert "nog geen beslissing" in kaart


def test_the_appliance_states_are_translated():
    for sleutel in ("steelstofzuiger_status", "fietsladers_status"):
        kaart = str(_kaart_voor(sleutel))
        assert "wacht op goedkoop blok" in kaart, sleutel


def test_the_candidate_count_has_context():
    """"0" zegt niet waarover het gaat."""
    kaart = str(_kaart_voor("nilm_onbevestigde_kandidaten"))

    assert "geen nieuwe kandidaten" in kaart
    assert "te beoordelen" in kaart


# --- volledigheid ----------------------------------------------------


def test_every_decision_reason_has_a_label():
    """Een reden zonder vertaling valt terug op de code, en dan staat er
    alsnog `expensive_quarter_soc_protected` op het scherm."""
    import re

    bron = (PAKKET / "coordinator.py").read_text()
    gebruikt = set(re.findall(r'last_reason = "([a-z_]+)"', bron))

    ontbreekt = sorted(gebruikt - set(DECISION_REASON_LABELS))

    assert not ontbreekt, f"geen vertaling voor: {ontbreekt}"


def test_the_labels_are_dutch_and_readable():
    """Een vertaling met een underscore erin is geen vertaling."""
    for tabel in (DECISION_REASON_LABELS, APPLIANCE_STATE_LABELS):
        for code, label in tabel.items():
            assert "_" not in label, code
            assert label != code, code


def test_the_codes_themselves_are_unchanged():
    """De logica vergelijkt op deze waarden; ze vertalen in de sensor zou
    elke vergelijking breken."""
    bron = (PAKKET / "coordinator.py").read_text()

    assert 'last_reason = "expensive_quarter"' in bron
    assert '"wacht_op_goedkoop_blok"' in bron
