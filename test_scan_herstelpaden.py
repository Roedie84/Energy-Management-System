"""Structuurscan 11: geen twee herstelpaden voor dezelfde gegevens
(v3.42.1).

Uit een echte fout voortgekomen, en niet voor het eerst. De opruiming
van de klimaatcellen in v3.41.0 werkte wél, maar had geen effect: de
klimaatsensor zette dezelfde cellen daarna terug uit zijn eigen
entiteit-attributen.

Dat is dezelfde vorm als v0.63.115, toen de NILM-apparaten bij elke
herstart op twintig bleven steken omdat de entiteit-attributen (die op
twintig zijn afgekapt) de volledige Store overschreven.

Een veld dat zowel in de Store staat als uit een entiteit wordt
teruggezet, heeft twee bronnen van waarheid. Dat mag - soms is het de
enige migratieweg - maar dan moet het bewust zijn en hier staan.
"""
import ast
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import (
    PERSISTED_DATE_FIELDS,
    PERSISTED_DATETIME_FIELDS,
    PERSISTED_INT_FIELDS,
    PERSISTED_PLAIN_FIELDS,
)

MAP = Path(pkg.__file__).parent
BEWAARD = set(
    PERSISTED_PLAIN_FIELDS
    + PERSISTED_INT_FIELDS
    + PERSISTED_DATE_FIELDS
    + PERSISTED_DATETIME_FIELDS
)

# Velden waarvan bewust twee paden bestaan, met de reden erbij.
BEWUST = {
    # De Store is leidend; de entiteit is er alleen voor gebruikers die
    # van vóór de Store komen. Zie v0.63.115.
    "nilm_confirmed_devices": "migratiepad van vóór de Store",
    "nilm_rejected_entities": "migratiepad van vóór de Store",
    # v3.42.1: hersteld pad, maar nu met een filter op het sleutelformaat
    # zodat een opruiming niet ongedaan wordt gemaakt.
    "climate_rate_history": "entiteit herstelt alleen het nieuwe formaat",
    "climate_forecast_bias_history": "staat los van de sleutelwijziging",
}


def _hersteld_uit_entiteit() -> set[str]:
    """Velden die een entiteit terugzet in `async_added_to_hass`."""
    gevonden = set()
    for pad in (MAP / "sensor.py", MAP / "switch.py", MAP / "button.py"):
        boom = ast.parse(pad.read_text())
        for knoop in ast.walk(boom):
            if not (
                isinstance(knoop, ast.AsyncFunctionDef)
                and knoop.name == "async_added_to_hass"
            ):
                continue
            for binnen in ast.walk(knoop):
                if (
                    isinstance(binnen, ast.Attribute)
                    and isinstance(binnen.ctx, ast.Store)
                    and isinstance(binnen.value, ast.Attribute)
                    and binnen.value.attr == "_coordinator"
                ):
                    gevonden.add(binnen.attr)
    return gevonden


def test_no_field_has_two_unacknowledged_restore_paths():
    """Een veld met twee bronnen van waarheid loopt uiteen zodra er aan

    één van de twee wordt gerepareerd - precies wat er met de
    klimaatcellen gebeurde.
    """
    dubbel = (_hersteld_uit_entiteit() & BEWAARD) - set(BEWUST)

    assert not dubbel, (
        "deze velden worden zowel uit de Store als uit een entiteit "
        f"teruggezet: {sorted(dubbel)}. Zet ze in BEWUST met de reden, of "
        "haal één van de twee paden weg."
    )


def test_the_acknowledged_list_stays_honest():
    """Staat er iets in de lijst dat allang niet meer uit een entiteit

    komt, dan beschrijft de lijst iets dat niet meer waar is.
    """
    uit_entiteit = _hersteld_uit_entiteit()

    verouderd = sorted(v for v in BEWUST if v not in uit_entiteit)

    assert not verouderd, (
        f"deze staan als bewust dubbel genoteerd maar worden nergens uit "
        f"een entiteit teruggezet: {verouderd}"
    )


def test_the_climate_cells_filter_on_the_key_format():
    """De reparatie zelf: het herstelpad mag alleen het nieuwe formaat

    terugzetten, anders is de opruiming zinloos.
    """
    bron = (MAP / "sensor.py").read_text()
    begin = bron.index('raw_cells = last_state.attributes')
    blok = bron[begin:][:1600]

    assert 'startswith("d")' in blok
