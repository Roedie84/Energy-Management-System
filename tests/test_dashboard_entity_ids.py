"""Entiteit-ids op het dashboard bestaan echt (v3.27.2).

Gemeld met een schermafdruk: "Entiteit niet gevonden" op de zojuist
toegevoegde kalibratiekaart. De kaart wees naar
`switch.energy_management_system_kalibratie`, terwijl de entiteit
`switch.woonkamer_energy_management_system_kalibratie` heet.

De oorzaak is een gewoonte van Home Assistant, niet van deze
integratie. Entiteiten met `_attr_has_entity_name` krijgen hun id uit de
apparaatnaam. `force_manual` en `learning_only` zijn aangemaakt vóórdat
het apparaat in een gebied stond en hebben daarom geen voorvoegsel;
alles wat er later bij kwam - vakantiemodus, alle meldingsschakelaars -
heeft `woonkamer_` ervoor.

Ik heb de nieuwe kaart naar het patroon van `force_manual` gebouwd, en
dat is precies de verkeerde van de twee om te kopiëren. Deze test kijkt
naar de meerderheid: wijkt een schakelaarkaart af van het voorvoegsel
dat de rest van het dashboard gebruikt, dan is dat vrijwel zeker een
vergissing en geen keuze.
"""
import re
from collections import Counter
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent

# De drie oude entiteiten van vóór het gebied. Die staan zo in de
# draaiende installatie en mogen niet "gerepareerd" worden.
VAN_VOOR_HET_GEBIED = {
    "switch.energy_management_system_force_manual",
    "switch.energy_management_system_learning_only_no_control",
}


def _switch_ids(tekst: str) -> list[str]:
    return re.findall(r"switch\.[a-z0-9_]*energy_management_system_[a-z0-9_]+", tekst)


def test_new_switch_cards_follow_the_prefix_the_rest_uses():
    """Eén afwijkende kaart is een typefout; de meerderheid is de norm."""
    tekst = (PAKKET / "dashboard_template.yaml").read_text()
    ids = set(_switch_ids(tekst)) - VAN_VOOR_HET_GEBIED

    zonder_voorvoegsel = {
        e for e in ids if e.startswith("switch.energy_management_system_")
    }

    assert not zonder_voorvoegsel, (
        "deze schakelaars missen het voorvoegsel dat de rest wel heeft: "
        f"{sorted(zonder_voorvoegsel)}"
    )


def test_the_prefix_is_used_consistently():
    """Slaat de installatie ooit om naar een ander voorvoegsel, dan valt

    deze test om in plaats van dat er kaarten stilletjes leeg blijven.
    """
    tekst = (PAKKET / "dashboard_template.yaml").read_text()
    ids = set(_switch_ids(tekst)) - VAN_VOOR_HET_GEBIED

    voorvoegsels = Counter(
        e.split("energy_management_system")[0] for e in ids
    )

    assert len(voorvoegsels) == 1, f"gemengde voorvoegsels: {dict(voorvoegsels)}"


def test_the_calibration_switch_is_on_the_dashboard():
    """De aanleiding: de kaart stond er wel, maar wees naar niets."""
    tekst = (PAKKET / "dashboard_template.yaml").read_text()

    assert "switch.woonkamer_energy_management_system_kalibratie\n" in tekst
    assert (
        "switch.woonkamer_energy_management_system_melding_kalibratie_vol"
        in tekst
    )


def test_both_dashboard_copies_stay_equal():
    """De kopie in `dashboards/` is wat een nieuwe gebruiker importeert.

    Loopt die achter, dan mist die precies de kaarten die net zijn
    toegevoegd.
    """
    sjabloon = (PAKKET / "dashboard_template.yaml").read_text()
    kopie = (
        PAKKET.parent.parent
        / "dashboards"
        / "energy_management_system_dashboard.yaml"
    ).read_text()

    assert sjabloon == kopie
