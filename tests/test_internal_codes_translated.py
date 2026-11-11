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
from tests._coordinator_bron import coordinator_bron

PAKKET = Path(pkg.__file__).parent


# --- de vier gevallen ------------------------------------------------


# --- volledigheid ----------------------------------------------------


def test_every_decision_reason_has_a_label():
    """Een reden zonder vertaling valt terug op de code, en dan staat er
    alsnog `expensive_quarter_soc_protected` op het scherm."""
    import re

    bron = coordinator_bron()
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
    bron = coordinator_bron()

    assert 'last_reason = "expensive_quarter"' in bron
    assert '"wacht_op_goedkoop_blok"' in bron
