"""Een wasmachinecyclus van zes minuten bestaat niet (v3.99.1).

Gevonden bij de volledige doorlichting, in de export van 2 september:

    washing_machine_cycle_duration_history   16, 8, 6, 36, 6, 153, 6
    learned_washing_machine_cycle_duration   8 minuten

    dishwasher_cycle_duration_history        70, 50, 52, 51, 51, 51, 50
    learned_dishwasher_cycle_duration        51 minuten

De vaatwasser leert netjes. De wasmachine "leert" acht minuten, omdat
vijf van de zeven metingen geen wascyclus zijn: zes tot zestien minuten
is een spoel- of pompslag, of een machine die even aanslaat en weer
stilvalt. De ene echte cyclus - 153 minuten - verdwijnt in de mediaan.

En dát is waar "Klaor na ongeveer 8 minuten" vandaan kwam, de melding
waar op 31 augustus over geklaagd werd. Niet de titel was het probleem
(dat is in v3.93.1 opgelost), het GETAL was al fout.

Een cyclus korter dan een kwartier wordt niet meer als cyclus geleerd.
Wel gemeld - het apparaat is immers klaar - maar niet meegeteld in wat
"een cyclus" duurt.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    APPLIANCE_CYCLE_MIN_LEARN_MINUTES,
)

NU = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)


def _cyclus(c, duur_minuten):
    """Laat een cyclus van deze lengte eindigen."""
    c._washing_machine_cycle_started_at = NU - timedelta(minutes=duur_minuten)
    c._leer_cyclusduur(
        NU,
        cycle_started_attr="_washing_machine_cycle_started_at",
        duration_history_attr="washing_machine_cycle_duration_history",
    )
    return c.washing_machine_cycle_duration_history


def test_een_echte_cyclus_wordt_geleerd(make_coordinator, hass):
    c = make_coordinator({})
    c.washing_machine_cycle_duration_history = []

    assert _cyclus(c, 153) == [153.0]


def test_een_pompslag_wordt_niet_geleerd(make_coordinator, hass):
    """Zes minuten is geen was."""
    c = make_coordinator({})
    c.washing_machine_cycle_duration_history = []

    assert _cyclus(c, 6) == []


def test_de_grens_ligt_op_een_kwartier(make_coordinator, hass):
    c = make_coordinator({})
    c.washing_machine_cycle_duration_history = []

    _cyclus(c, APPLIANCE_CYCLE_MIN_LEARN_MINUTES - 1)
    assert c.washing_machine_cycle_duration_history == []

    _cyclus(c, APPLIANCE_CYCLE_MIN_LEARN_MINUTES + 1)
    assert len(c.washing_machine_cycle_duration_history) == 1


def test_de_bestaande_reeks_wordt_opgeschoond(make_coordinator, hass):
    """De zeven metingen van 2 september: na opschoning blijven 16, 36 en

    153 over. Sinds v3.99.3 is dat "onbekende tijd" tot er vijf echte
    cycli zijn die bij elkaar liggen.
    """
    c = make_coordinator({})
    c.washing_machine_cycle_duration_history = [16.0, 8.0, 6.0, 36.0, 6.0, 153.0, 6.0]

    c._schoon_cyclusduren_op()

    assert c.washing_machine_cycle_duration_history == [16.0, 36.0, 153.0]
    # v3.99.3: en drie losse getallen zijn nog geen duur.
    assert c.learned_washing_machine_cycle_duration_minutes is None


# --- pas melden als er genoeg echte cycli zijn (v3.99.3) ---------------


def test_met_te_weinig_cycli_is_de_duur_onbekend(make_coordinator, hass):
    """Na opschoning blijven 16, 36 en 153 over. Drie metingen die

    137 minuten uiteenlopen, met een mediaan van 36 - dat is nog geen
    wasmachine. "Onbekende tijd" is eerlijker dan 36.
    """
    c = make_coordinator({})
    c.washing_machine_cycle_duration_history = [16.0, 36.0, 153.0]

    assert c.learned_washing_machine_cycle_duration_minutes is None


def test_met_genoeg_cycli_die_bij_elkaar_liggen_wel(make_coordinator, hass):
    c = make_coordinator({})
    c.washing_machine_cycle_duration_history = [140.0, 153.0, 148.0]

    assert c.learned_washing_machine_cycle_duration_minutes == 148.0


def test_de_vaatwasser_blijft_gewoon_bekend(make_coordinator, hass):
    """70, 50, 52, 51, 51, 51, 50: zeven cycli dicht bij elkaar."""
    c = make_coordinator({})
    c.dishwasher_cycle_duration_history = [70.0, 50.0, 52.0, 51.0, 51.2, 51.0, 50.0]

    assert c.learned_dishwasher_cycle_duration_minutes == 51.0
