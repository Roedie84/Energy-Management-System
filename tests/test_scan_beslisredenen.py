"""Structuurscan 8: elke beslisreden heeft een onderbouwing (v3.29.0).

Uit een echte fout voortgekomen. Op 19 augustus meldde de kaart bij een
lopende kalibratie de kop "Waarom doet de aansturing niets?" met daaronder
het gewone verhaal over prijsdrempels: de prijs is nu 30,8 ct, de drempel
voor duur ligt op 37,6 ct, geen bijzondere reden om iets anders te doen.

De kop kwam uit `WHY_QUESTIONS` en klopte. De regels eronder kwamen uit
`_waarom_regels`, en die kende `kalibratie` niet - dus viel hij door naar
de terugval van `default_smart`.

Twee tabellen die naast elkaar moeten lopen en dat niet afdwingen. Deze
scan doet dat wel: elke sleutel in `WHY_QUESTIONS` moet in
`_waarom_regels` een eigen tak hebben, of uitdrukkelijk de terugval zijn.

Nagegaan bij het schrijven: op dit moment hebben alle zestien redenen een
tak. De scan is er om dat zo te houden - de volgende reden die erbij komt
valt anders opnieuw stilletjes door.
"""
import inspect
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import WHY_QUESTIONS
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

# De reden die per ontwerp GEEN eigen tak heeft: dat is de terugval zelf.
TERUGVAL = {"default_smart"}


def _takken() -> set[str]:
    bron = inspect.getsource(C._waarom_regels)
    gevonden = set(re.findall(r'reden == "([a-z_]+)"', bron))
    for groep in re.findall(r"reden in \(([^)]+)\)", bron):
        gevonden |= set(re.findall(r'"([a-z_]+)"', groep))
    return gevonden


def test_every_reason_has_its_own_lines():
    """Zonder eigen tak krijgt de gebruiker het verhaal van een andere

    beslissing te lezen - precies wat er bij de kalibratie gebeurde.
    """
    ontbreekt = sorted(set(WHY_QUESTIONS) - _takken() - TERUGVAL)

    assert not ontbreekt, (
        "deze redenen vallen door naar de terugval van default_smart: "
        f"{ontbreekt}"
    )


def test_no_branch_exists_for_a_reason_nobody_knows():
    """Andersom net zo goed: een tak voor een reden die niet meer bestaat

    is dode code die bij het lezen de indruk wekt dat hij nog kan vuren.
    """
    onbekend = sorted(_takken() - set(WHY_QUESTIONS))

    assert not onbekend, f"tak zonder reden in WHY_QUESTIONS: {onbekend}"


def test_both_explanation_builders_cover_the_same_reasons():
    """`_build_explanation` en `_waarom_regels` bouwen allebei een uitleg.

    Ze hoeven niet gelijk te zijn - de eerste schrijft proza, de tweede
    losse regels - maar een reden die de ene apart behandelt en de andere
    niet, is precies het gat van 19 augustus.
    """
    proza = inspect.getsource(C._build_explanation)

    for reden in ("force_manual", "kalibratie"):
        assert reden in proza, f"{reden} ontbreekt in _build_explanation"


def test_the_labels_are_translated_too():
    """Een reden zonder Nederlands label toont zijn interne code op het

    dashboard.
    """
    from custom_components.energy_management_system.const import (
        DECISION_REASON_LABELS,
    )

    ontbreekt = sorted(set(WHY_QUESTIONS) - set(DECISION_REASON_LABELS))

    assert not ontbreekt, f"geen label voor: {ontbreekt}"
