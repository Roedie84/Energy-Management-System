"""De README als visitekaartje (v1.77.0).

Gevraagd: "Ik wil een readme die er professioneel uitziet. Mogelijk
willen anderen in de toekomst de integratie ook gaan gebruiken."

Hij was 12.389 regels: een dagboek waarin per versie het verhaal was
aangeplakt. Dat is waardevol, maar niet als eerste indruk - iemand die
overweegt de integratie te gebruiken haakt af voordat hij bij de
installatie is.

Deze tests bewaken de vorm, niet de inhoud: dat de README kort blijft en
dat de dingen erin staan die iemand nodig heeft om te beginnen.
"""
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent


def _readme() -> str:
    return (WORTEL / "README.md").read_text()


def test_the_readme_stays_readable():
    """Een README die weer een dagboek wordt, wordt weer ongelezen. De
    versieverhalen horen in docs/ONTWIKKELING.md."""
    regels = _readme().splitlines()

    assert len(regels) < 600, f"{len(regels)} regels - te lang voor een README"


def test_the_development_history_is_kept_somewhere():
    """Niet weggooien: die verhalen leggen vast waaróm een regel er is,
    en dat is vaak nuttiger dan wat er staat."""
    pad = WORTEL / "docs" / "ONTWIKKELING.md"

    assert pad.exists()
    assert len(pad.read_text().splitlines()) > 1000


def test_a_newcomer_can_get_started():
    """Wat iemand nodig heeft die de integratie nog niet kent."""
    inhoud = _readme()

    for kop in (
        "## Wat doet het",
        "## Vereisten",
        "## Installatie",
        "## Configuratie",
        "## Diagnostiek",
    ):
        assert kop in inhoud, kop


def test_the_limits_are_stated_up_front():
    """Eerlijk zijn over waar dit op getest is. Iemand met een andere
    accu of leverancier moet dat weten vóór de installatie, niet erna."""
    inhoud = _readme()

    assert "niet getest" in inhoud
    assert "Learning only" in inhoud


def test_it_links_to_the_changelog_and_history():
    inhoud = _readme()

    assert "CHANGELOG.md" in inhoud
    assert "docs/ONTWIKKELING.md" in inhoud


def test_there_is_a_licence():
    """Zonder licentie mag niemand het gebruiken, en dat is precies niet
    de bedoeling."""
    pad = WORTEL / "LICENSE"

    assert pad.exists()
    assert "MIT" in pad.read_text()
    assert "MIT" in _readme()


def test_the_version_badge_matches_the_manifest():
    """Een badge die achterloopt is erger dan geen badge."""
    import json

    manifest = json.loads(
        (
            WORTEL
            / "custom_components"
            / "energy_management_system"
            / "manifest.json"
        ).read_text()
    )

    assert f"versie-{manifest['version']}" in _readme()
