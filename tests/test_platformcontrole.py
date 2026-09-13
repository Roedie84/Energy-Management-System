"""Zijn alle onderdelen overeind gebleven? (v3.79.0)

Gevraagd na een storing die van binnenuit onzichtbaar was: op 30
augustus werd `HANDMATIGE_STAND_LADEN` in `switch.py` gebruikt maar
nooit geïmporteerd. Dat werpt een NameError bij het opzetten van de
schakelaars, en dan wordt dat hele platform stil overgeslagen.

Gevolg: TIEN schakelaars verdwenen - Force manual, Learning only,
Vakantiemodus, de apparaatknoppen. En de integratie zag er van binnenuit
precies zo uit als een gezonde:

    bestandscontrole   alle bestanden kloppen
    entiteiten         59 in orde, 0 stuk
    analyse            geen bijzonderheden
    logboek            geen melding

Dat klopte allemaal. De BESTANDEN waren compleet, en de sensoren die de
configuratiecontrole nakijkt zijn andermans entiteiten. Wat er ontbrak
waren de EIGEN entiteiten, en daar keek niets naar.
"""
import pytest


def _echte_controle(c):
    """De fixture zet hem uit; deze toetsen willen hem juist aan."""
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    return C.get_platformcontrole(c)


def _entiteiten(hass, platform, aantal):
    for i in range(aantal):
        hass.states.set(
            f"{platform}.woonkamer_energy_management_system_test_{i}", "1"
        )


def test_a_healthy_installation_reports_nothing(make_coordinator, hass):
    c = make_coordinator({})
    from custom_components.energy_management_system.const import (
        PLATFORM_MINIMUM_ENTITEITEN,
    )

    for platform, minimum in PLATFORM_MINIMUM_ENTITEITEN.items():
        _entiteiten(hass, platform, minimum)

    uitkomst = _echte_controle(c)

    assert uitkomst["in_orde"] is True
    assert uitkomst["omgevallen"] == []


def test_a_collapsed_platform_is_caught(make_coordinator, hass):
    """Het geval van 30 augustus: de schakelaars zijn er niet, de rest

    wel.
    """
    c = make_coordinator({})
    _entiteiten(hass, "sensor", 20)
    _entiteiten(hass, "button", 1)

    uitkomst = _echte_controle(c)

    assert uitkomst["in_orde"] is False
    assert "switch" in uitkomst["omgevallen"]
    assert "vastloopt" in uitkomst["uitleg"]


def test_it_counts_per_platform(make_coordinator, hass):
    c = make_coordinator({})
    _entiteiten(hass, "switch", 7)

    uitkomst = _echte_controle(c)

    assert uitkomst["gevonden"]["switch"] == 7


def test_other_integrations_do_not_count(make_coordinator, hass):
    """Andermans entiteiten zeggen niets over de eigen platforms - dat

    is precies waarom de configuratiecontrole dit niet ving.
    """
    c = make_coordinator({})
    for i in range(20):
        hass.states.set(f"switch.zendure_manager_iets_{i}", "on")

    uitkomst = _echte_controle(c)

    assert "switch" in uitkomst["omgevallen"]


def test_the_minimums_leave_room_to_grow():
    """Ruim onder het werkelijke aantal: het gaat erom of een platform

    HELEMAAL niets heeft aangemaakt. Anders breekt deze controle bij
    elke nieuwe entiteit.
    """
    from custom_components.energy_management_system.const import (
        PLATFORM_MINIMUM_ENTITEITEN,
    )

    # De installatie draagt 59 entiteiten; de drempels samen ver daaronder.
    assert sum(PLATFORM_MINIMUM_ENTITEITEN.values()) < 40


def test_a_collapsed_platform_lands_in_the_analysis(
    make_coordinator, hass
):
    """Bovenaan, niet ergens halverwege een export van 600 kB - want dat

    is precies waarom het een halve dag onopgemerkt bleef.
    """
    c = make_coordinator({})
    c.get_platformcontrole = lambda: {
        "beschikbaar": True,
        "in_orde": False,
        "omgevallen": ["switch"],
        "uitleg": "Deze onderdelen hebben geen entiteiten: switch.",
    }

    analyse = c.get_analyse()

    assert any(
        p["onderwerp"] == "Onderdeel niet geladen" for p in analyse["punten"]
    )


def test_only_platforms_the_integration_sets_up_are_checked():
    """De eerste versie noemde er vijf, waaronder `number` en `select`.

    Die maakt deze integratie helemaal niet aan - er is geen number.py
    en geen select.py - en dus meldde de controle meteen twee omgevallen
    onderdelen die er nooit waren geweest.

    Vals alarm van eigen makelij, en dezelfde fout als die hij moest
    vangen: een controle schrijven op grond van wat je DENKT dat er
    hoort te staan.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    from custom_components.energy_management_system.const import (
        PLATFORMS,
        PLATFORM_MINIMUM_ENTITEITEN,
    )

    map_ = Path(pkg.__file__).parent

    # Elk platform in de lijst heeft ook een bestand.
    for platform in PLATFORMS:
        assert (map_ / f"{platform}.py").exists(), platform

    # En de drempels gaan over precies die platforms.
    assert set(PLATFORM_MINIMUM_ENTITEITEN) == set(PLATFORMS)


def test_the_platform_list_has_one_source():
    """Twee lijsten met dezelfde inhoud is precies de vorm die op 26

    augustus fout bleek bij de cyclusverwachting: 4000 naast 6000, en de
    ene helft van de integratie rekende anders dan de andere.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "__init__.py").read_text()

    assert 'PLATFORMS = [' not in bron
    assert "from .const import DOMAIN, PLATFORMS" in bron
