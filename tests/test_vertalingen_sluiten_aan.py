"""De drie tekstbestanden dragen dezelfde sleutels (v3.42.0).

Gevonden bij het nalopen van de integratie op volledigheid:
`strings.json` miste 32 sleutels die wél in `nl.json` en `en.json`
stonden - de labels van de helft van de instelvelden. Nieuwe velden
waren bij de vertalingen gekomen en niet bij de bron.

Home Assistant gebruikt `strings.json` als bron voor het vertaalproces.
Het zichtbare effect is nul zolang de vertaalbestanden er staan, maar
het is precies het soort scheefgroei dat elders in deze codebase wél
bewaakt wordt - de dagreeks, de periodekaart, de reservemarge.
"""
import json
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg

MAP = Path(pkg.__file__).parent
BESTANDEN = {
    "strings.json": MAP / "strings.json",
    "nl.json": MAP / "translations" / "nl.json",
    "en.json": MAP / "translations" / "en.json",
}


def _sleutels(pad: Path) -> set[str]:
    def plat(knoop, voorvoegsel=""):
        for sleutel, waarde in knoop.items():
            if isinstance(waarde, dict):
                yield from plat(waarde, f"{voorvoegsel}{sleutel}.")
            else:
                yield voorvoegsel + sleutel

    return set(plat(json.loads(pad.read_text())))


def test_all_three_files_exist():
    for naam, pad in BESTANDEN.items():
        assert pad.exists(), naam


@pytest.mark.parametrize("naam", ["nl.json", "en.json"])
def test_the_source_carries_every_translated_key(naam):
    """Een sleutel die alleen in een vertaling staat, is bij het

    vertaalproces onbekend en valt daar buiten.
    """
    bron = _sleutels(BESTANDEN["strings.json"])
    vertaling = _sleutels(BESTANDEN[naam])

    ontbreekt = sorted(vertaling - bron)

    assert not ontbreekt, (
        f"{naam} heeft sleutels die niet in strings.json staan: "
        + ", ".join(ontbreekt[:8])
    )


@pytest.mark.parametrize("naam", ["nl.json", "en.json"])
def test_every_source_key_is_translated(naam):
    """En andersom: een veld zonder vertaling toont zijn interne naam."""
    bron = _sleutels(BESTANDEN["strings.json"])
    vertaling = _sleutels(BESTANDEN[naam])

    ontbreekt = sorted(bron - vertaling)

    assert not ontbreekt, (
        f"{naam} mist vertalingen voor: " + ", ".join(ontbreekt[:8])
    )


def test_the_two_languages_cover_the_same_ground():
    """Nederlands en Engels moeten dezelfde velden dekken; anders is één

    van de twee half af zonder dat het opvalt.
    """
    assert _sleutels(BESTANDEN["nl.json"]) == _sleutels(BESTANDEN["en.json"])


def test_no_translation_is_empty():
    """Een lege tekst toont in Home Assistant een leeg label."""
    for naam, pad in BESTANDEN.items():
        def plat(knoop, voorvoegsel=""):
            for sleutel, waarde in knoop.items():
                if isinstance(waarde, dict):
                    yield from plat(waarde, f"{voorvoegsel}{sleutel}.")
                else:
                    yield voorvoegsel + sleutel, waarde

        leeg = [
            s for s, w in plat(json.loads(pad.read_text()))
            if not str(w).strip()
        ]

        assert not leeg, f"{naam}: lege teksten bij {leeg[:5]}"
