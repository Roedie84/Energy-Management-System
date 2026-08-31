"""Manifest, README en changelog zeggen hetzelfde (v3.4.1).

Gevonden dankzij de installatiegegevens die in v3.4.0 aan de export zijn
toegevoegd: er stond `"versie": "3.0.2"` terwijl de code aantoonbaar
v3.4.0 was - tien kruiscontroles, logopvang, installatiegegevens.

De oorzaak is een fout in de werkwijze, niet in de code. Elke oplevering
verhoogde het versienummer met een zoek-en-vervang op de OUDE waarde:

    sed -i 's/"version": "3.3.0"/"version": "3.4.0"/' manifest.json

Klopt die oude waarde niet, dan doet het commando NIETS - zonder
foutmelding. Vier opleveringen op rij zijn zo stilzwijgend mislukt.

De ironie: de verbetering die deze fout aan het licht bracht, was in
dezelfde oplevering gebouwd.
"""
import json
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent
WORTEL = PAKKET.parent.parent


def _manifest_versie() -> str:
    return json.loads((PAKKET / "manifest.json").read_text())["version"]


def _changelog_versies() -> list[str]:
    return re.findall(
        r"^## v(\d+\.\d+\.\d+)", (WORTEL / "CHANGELOG.md").read_text(), re.M
    )


def test_the_manifest_matches_the_changelog():
    """Het changelog is de bron: daar staat wat er is gebeurd."""
    assert _manifest_versie() == _changelog_versies()[-1]


def test_the_readme_badge_matches_the_manifest():
    tekst = (WORTEL / "README.md").read_text()
    badge = re.search(r"versie-(\d+\.\d+\.\d+)-blue", tekst)

    assert badge, "geen versiebadge in de README"
    assert badge.group(1) == _manifest_versie()


# Vijf nummers zijn in het verleden twee keer gebruikt: 1.46.0, 2.1.0,
# 2.2.0, 2.2.2 en 2.3.0. Dezelfde stilzwijgend mislukte zoek-en-vervang,
# eerder al opgetreden zonder dat iemand het zag.
#
# Die geschiedenis wordt NIET herschreven - dat zou verslaglegging
# vervalsen. De toets bewaakt alleen wat er vanaf hier bij komt.
BEKENDE_DUBBELEN = {"1.46.0", "2.1.0", "2.2.0", "2.2.2", "2.3.0"}


def test_the_changelog_only_goes_up():
    """Een teruglopend nummer betekent dat er iets is overgeschreven."""
    versies = _changelog_versies()
    paren = list(zip(versies, versies[1:]))

    fout = [
        (a, b)
        for a, b in paren
        if tuple(int(x) for x in b.split(".")) <= tuple(int(x) for x in a.split("."))
        and b not in BEKENDE_DUBBELEN
        and a not in BEKENDE_DUBBELEN
    ]

    assert not fout, fout


def test_no_new_version_appears_twice():
    """Twee opleveringen onder hetzelfde nummer is niet te herleiden."""
    versies = _changelog_versies()

    dubbel = {
        v
        for v in set(versies)
        if versies.count(v) > 1 and v not in BEKENDE_DUBBELEN
    }

    assert not dubbel, dubbel


def test_the_known_duplicates_do_not_grow():
    """Vangnet: komt er een zesde dubbel nummer bij, dan valt deze om."""
    versies = _changelog_versies()

    dubbel = {v for v in set(versies) if versies.count(v) > 1}

    assert dubbel == BEKENDE_DUBBELEN


def test_the_running_version_is_visible_in_the_export():
    """Zonder dit veld was deze fout onzichtbaar gebleven: om te bepalen
    welke code draaide moest worden afgeleid welke FUNCTIES aanwezig
    waren."""
    bron = (PAKKET / "diagnostics.py").read_text()

    assert '"installation"' in bron


def test_the_test_count_in_the_readme_is_plausible():
    """Het aantal stond ook scheef, om dezelfde reden: een
    zoek-en-vervang op een verouderde waarde doet niets.

    Het exacte aantal is hier niet te tellen zonder de suite te draaien,
    maar een getal dat honderden achterloopt is wél te zien.
    """
    tekst = (WORTEL / "README.md").read_text()
    genoemd = re.search(r"tests-(\d+)%20groen", tekst)

    assert genoemd, "geen testaantal in de README"

    # v3.92.0: geteld op de toetsFUNCTIES, niet op vijf per bestand.
    #
    # Die oude ondergrens - 330 bestanden maal vijf - lag op 1650,
    # terwijl de badge op 3161 stond en de suite er 3350 draaide. Een
    # verschil van bijna tweehonderd bleef zo staan, en dat is precies
    # waar deze toets voor gemaakt is.
    #
    # Een functie tellen kan statisch; een geparametriseerde functie
    # levert er meer dan één op, dus dit is een ONDERgrens die niet vals
    # kan afgaan.
    bestanden = list((WORTEL / "tests").glob("test_*.py"))
    ondergrens = sum(
        len(re.findall(r"^\s*def test_", pad.read_text(), re.MULTILINE))
        for pad in bestanden
    )

    assert int(genoemd.group(1)) >= ondergrens, (
        f"{genoemd.group(1)} genoemd bij {ondergrens} toetsfuncties in "
        f"{len(bestanden)} bestanden - dat loopt achter"
    )
