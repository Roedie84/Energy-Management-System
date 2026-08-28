"""Zijn alle bestanden van deze versie geïnstalleerd? (v3.63.0)

Gevraagd: "Tevens wil ik graag dat er altijd wordt gecontroleerd of de
meest actuele bestanden uit de integratie aanwezig zijn. Nu we niet elke
keer meer de volledige integratie in ZIP maar alleen de gewijzigde wil
ik hier een borging."

Terecht. Sinds v3.55.0 gaan er alleen nog gewijzigde bestanden de deur
uit, en dan is er precies één nieuwe manier om het mis te laten gaan: er
blijft een oud bestand staan. Dat breekt stil - de code draait, alleen
een deel ervan is van vorige week.

Een hash per bestand vangt dat. Niet een versienummer per bestand, want
dat moet je bijhouden en dan is de bewaking net zo betrouwbaar als de
discipline om eraan te denken.
"""
import hashlib
import json
from pathlib import Path

import custom_components.energy_management_system as pkg

MAP = Path(pkg.__file__).parent
LIJST = MAP / "bestandscontrole.json"


def _huidige_hashes() -> dict:
    uit = {}
    for pad in sorted(MAP.rglob("*")):
        if not pad.is_file() or "__pycache__" in pad.parts:
            continue
        naam = pad.relative_to(MAP).as_posix()
        if naam == "bestandscontrole.json":
            continue
        uit[naam] = hashlib.sha256(pad.read_bytes()).hexdigest()[:16]
    return uit


# --- de lijst zelf ---------------------------------------------------


def test_the_list_exists_and_is_shipped():
    assert LIJST.exists(), (
        "bestandscontrole.json hoort bij de integratie te zitten"
    )


def test_the_list_is_current():
    """DE belangrijkste toets van dit bestand.

    Zonder deze zou de lijst verouderen zodra er een bestand verandert,
    en dan bewaakt hij de vorige versie. Precies de vorm die deze week
    zes keer is voorgekomen: een controle die klopt met zichzelf en
    niets meer met de werkelijkheid.

    Loopt hij om: draai `python3 tools_maak_bestandslijst.py`.
    """
    verwacht = json.loads(LIJST.read_text())
    huidig = _huidige_hashes()

    ontbreekt = sorted(set(huidig) - set(verwacht))
    verdwenen = sorted(set(verwacht) - set(huidig))
    afwijkend = sorted(
        naam for naam in set(huidig) & set(verwacht)
        if huidig[naam] != verwacht[naam]
    )

    assert not ontbreekt, f"niet in de lijst: {ontbreekt}"
    assert not verdwenen, f"staat in de lijst maar bestaat niet: {verdwenen}"
    assert not afwijkend, (
        f"gewijzigd sinds de lijst: {afwijkend} - draai "
        "tools_maak_bestandslijst.py"
    )


def test_every_python_file_is_covered():
    verwacht = json.loads(LIJST.read_text())
    python_bestanden = {
        p.relative_to(MAP).as_posix()
        for p in MAP.rglob("*.py")
        if "__pycache__" not in p.parts
    }

    assert python_bestanden <= set(verwacht)


# --- de controle in bedrijf ------------------------------------------


def test_a_complete_installation_is_reported_as_such(
    make_coordinator, hass
):
    c = make_coordinator({})

    uitkomst = c.bereken_bestandscontrole()

    assert uitkomst["in_orde"] is True
    assert uitkomst["afwijkend"] == []
    assert uitkomst["ontbrekend"] == []


def test_a_stale_file_is_caught(make_coordinator, hass, tmp_path):
    """Het geval waar het om gaat: je kopieert coordinator.py maar

    vergeet sensor.py.
    """
    c = make_coordinator({})
    echt = json.loads(LIJST.read_text())
    vervalst = dict(echt)
    vervalst["sensor.py"] = "0000000000000000"
    LIJST.write_text(json.dumps(vervalst, indent=2, sort_keys=True) + "\n")
    try:
        uitkomst = c.bereken_bestandscontrole()
    finally:
        LIJST.write_text(json.dumps(echt, indent=2, sort_keys=True) + "\n")

    assert uitkomst["in_orde"] is False
    assert "sensor.py" in uitkomst["afwijkend"]
    assert "niet meegekopieerd" in uitkomst["uitleg"]


def test_the_reader_does_not_touch_the_disk(make_coordinator, hass):
    """`get_bestandscontrole` geeft de uitkomst van het opstarten terug.

    Bestanden lezen blokkeert de gebeurtenislus, en daar staat een eigen
    toets op sinds het logboekonderzoek. Die sloeg bij de eerste versie
    hiervan meteen aan - terecht.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C.get_bestandscontrole)

    assert "read_bytes" not in bron
    assert "read_text" not in bron


def test_before_startup_it_says_so(make_coordinator, hass):
    c = make_coordinator({})

    assert c.get_bestandscontrole()["beschikbaar"] is False


def test_it_lands_in_the_analysis(make_coordinator, hass):
    """Een onvolledige installatie hoort bovenaan te staan, niet ergens

    halverwege een export van 600 kB.
    """
    c = make_coordinator({})
    c.bestandscontrole = {
        "beschikbaar": True,
        "in_orde": False,
        "afwijkend": ["sensor.py"],
        "ontbrekend": [],
        "uitleg": "1 bestand(en) wijken af",
    }

    analyse = c.get_analyse()

    assert any(
        p["onderwerp"] == "Onvolledige installatie" for p in analyse["punten"]
    )
