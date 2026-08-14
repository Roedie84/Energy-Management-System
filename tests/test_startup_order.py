"""De volgorde bij het opstarten (v1.95.0).

Gemeld na v1.94.0: dezelfde 131548 kWh per week. De opruiming van foute
ingelezen dagen stond VOOR het terugzetten van de bewaarde toestand, dus
ruimde hij een lege lijst op waarna de bewaarde reeks er overheen kwam.

Exact dezelfde volgordefout als v1.49.0, waar
`_recompute_measurement_quality()` vóór het terugzetten stond en de
meetkwaliteit daardoor altijd leeg bleef. Toen is er geen test gemaakt
die de VOLGORDE bewaakt - vandaar dit bestand.
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

BRON = (Path(pkg.__file__).parent / "coordinator.py").read_text()


def _setup_blok() -> str:
    kop = BRON.index("    async def async_setup(self) -> None:")
    staart = BRON.index("\n    async def ", kop + 40)
    return BRON[kop:staart]


def _volgorde(*namen) -> list[int]:
    blok = _setup_blok()
    return [blok.index(naam) for naam in namen]


def test_the_persisted_state_is_restored_first():
    """Alles wat de bewaarde reeksen LEEST of OPRUIMT moet daarna komen.
    Anders werkt het op een lege lijst en wordt het resultaat meteen
    overschreven."""
    laden, opruimen = _volgorde(
        "async_load_persisted_nilm_state()",
        "async_bootstrap_energy_history()",
    )

    assert laden < opruimen


def test_the_tick_starts_after_everything_is_loaded():
    """Een tick die begint voordat de toestand terug is, rekent met lege
    reeksen en schrijft die uitkomst weg."""
    laden, tick = _volgorde(
        "async_load_persisted_nilm_state()",
        "async_track_time_interval(",
    )

    assert laden < tick


def test_every_bootstrap_is_named_in_this_test():
    """Vangnet: komt er een nieuwe opstartroutine bij, dan hoort iemand
    te bepalen waar die in de volgorde staat. Deze toets valt om zodra er
    een `async_bootstrap_...` bij komt die hier niet genoemd is.
    """
    blok = _setup_blok()
    gevonden = set(re.findall(r"await self\.(async_bootstrap_\w+)\(", blok))

    bekend = {
        "async_bootstrap_night_consumption_from_history",
        "async_bootstrap_energy_history",
    }

    assert gevonden == bekend, (
        "nieuwe opstartroutine gevonden - bepaal eerst of hij voor of na "
        f"het terugzetten van de toestand hoort: {gevonden - bekend}"
    )
