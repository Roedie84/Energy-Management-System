"""Eén bron voor elke beslisreden (v4.20).

Gevraagd: "Ik wil dat je dit niet oplost met nóg een mapping. Ontwerp
een centrale REASON_REGISTRY als enige waarheid."

Terecht. De aanleiding was "Onbekende reden: solar_capture_deferred" in
de export: die reden zat in `REASON_TO_MODE` en in de woordenlijst, maar
niet in de uitleglaag. Vier kopieën van hetzelfde begrip:

    beslissing   zet de reden
    REASON_TO_MODE   welke accustand hoort erbij
    _build_explanation   de uitleg
    nl.json / MELDING_ADVIES   titel en advies

In v4.19 loste ik dat op met `REDEN_UITLEG` - een vijfde tabel. Dat was
het patroon vergroten in plaats van opheffen.

Nu is `REASON_REGISTRY` de enige bron, en `REASON_TO_MODE` wordt eruit
AFGELEID in plaats van los onderhouden. Een reden toevoegen is één
regel; vergeet je een veld, dan is het een typefout in plaats van een
stille misser.

`REDEN_UITLEG` bestaat niet meer.
"""
import ast
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
import pytest

PAKKET = Path(pkg.__file__).parent
COORD = (PAKKET / "coordinator.py").read_text()


def test_de_registry_is_de_bron_van_de_standvertaling():
    """`REASON_TO_MODE` mag geen eigen lijst meer zijn - hij komt uit de
    registry. Anders zijn er weer twee waarheden."""
    from custom_components.energy_management_system.const import (
        REASON_REGISTRY,
        REASON_TO_MODE,
    )

    # Redenen met `mode: None` passen niets toe en blijven buiten de
    # standvertaling - dat is wat REDENEN_ZONDER_STAND uitdrukt.
    assert REASON_TO_MODE == {
        reden: g["mode"]
        for reden, g in REASON_REGISTRY.items()
        if g["mode"] is not None
    }

    # De toewijzing zelf moet uit de registry komen - niet de eerste
    # vermelding in een opmerking.
    bron = (PAKKET / "const.py").read_text()
    i = bron.index("\nREASON_TO_MODE = ")
    blok = bron[i : bron.index("\n}\n", i)]
    assert "REASON_REGISTRY" in blok, f"niet afgeleid:\n{blok[:200]}"


def test_er_is_geen_tweede_uitlegtabel():
    """`REDEN_UITLEG` uit v4.19 was een vijfde kopie. Die hoort weg."""
    # Alleen de DEFINITIE mag weg zijn; de opmerkingen die uitleggen
    # waarom hij weg is, mogen blijven staan.
    bron = (PAKKET / "const.py").read_text()

    assert "REDEN_UITLEG: dict" not in bron
    assert "REDEN_UITLEG = {" not in bron
    assert "REDEN_UITLEG.get" not in COORD
    assert "REDEN_UITLEG," not in COORD


def test_elke_reden_heeft_alle_velden():
    """Vergeet je een veld, dan hoort dat een fout te zijn - niet een
    stille misser die in een export opduikt."""
    from custom_components.energy_management_system.const import REASON_REGISTRY

    verplicht = {"mode", "titel", "uitleg", "ernst"}
    for reden, gegevens in REASON_REGISTRY.items():
        ontbreekt = verplicht - set(gegevens)
        assert not ontbreekt, f"{reden}: {sorted(ontbreekt)}"
        assert gegevens["titel"], reden
        assert gegevens["uitleg"], reden
        assert gegevens["ernst"] in ("info", "aandacht", "ingrijpend"), reden


def test_all_reasons_registered():
    """De ratel die gevraagd is: elke reden die het systeem ERGENS zet,
    moet in de registry staan.

    Gevonden door de code te lezen in plaats van een lijst te
    onderhouden: elke `self.last_reason = "..."` in de coordinator.
    """
    from custom_components.energy_management_system.const import (
        REASON_REGISTRY,
        REDENEN_ZONDER_STAND,
    )

    gebruikt = set(re.findall(r'self\.last_reason = "(\w+)"', COORD))
    assert gebruikt, "geen enkele reden gevonden - is de vorm veranderd?"

    bekend = set(REASON_REGISTRY) | set(REDENEN_ZONDER_STAND)
    onbekend = sorted(gebruikt - bekend)
    assert not onbekend, onbekend


def test_geen_reden_in_de_registry_die_niemand_zet():
    """De andere kant: een reden in de registry die nergens wordt gezet,
    is dode uitleg die bij een hernoeming meeliegt."""
    from custom_components.energy_management_system.const import REASON_REGISTRY

    gebruikt = set(re.findall(r'self\.last_reason = "(\w+)"', COORD))
    # `kalibratie` en `force_manual` worden via de schakelaar gezet, niet
    # via een toewijzing - die staan apart.
    VIA_SCHAKELAAR = {"kalibratie", "force_manual"}
    # v4.21: niet-sturende toestanden worden nergens als reden gezet -
    # die worden gemeten en uitgelegd. Zie `stuurt: False`.
    NIET_STUREND = {
        r for r, g in REASON_REGISTRY.items() if g.get("stuurt") is False
    }
    ongebruikt = sorted(set(REASON_REGISTRY) - gebruikt - VIA_SCHAKELAAR - NIET_STUREND)
    assert not ongebruikt, ongebruikt


def test_elke_reden_komt_door_de_uitlegfunctie(make_coordinator, hass):
    """Het gedrag, niet de tekst: geen "Onbekende reden" meer mogelijk."""
    from custom_components.energy_management_system.const import REASON_REGISTRY

    c = make_coordinator({})
    SCHAKELAAR = {"force_manual": "force_manual", "kalibratie": "kalibratie"}
    zonder = []
    for reden in sorted(REASON_REGISTRY):
        for naam in SCHAKELAAR.values():
            setattr(c, naam, False)
        if reden in SCHAKELAAR:
            setattr(c, SCHAKELAAR[reden], True)
        c.last_reason = reden
        if "Onbekende reden" in c._build_explanation():
            zonder.append(reden)
    assert not zonder, zonder


def test_de_uitleg_van_de_registry_wordt_echt_gebruikt(make_coordinator, hass):
    """Niet alleen aanwezig, ook gebruikt: een reden zonder eigen tak
    krijgt de tekst uit de registry."""
    from custom_components.energy_management_system.const import REASON_REGISTRY

    c = make_coordinator({})
    c.force_manual = False
    c.kalibratie = False
    c.last_reason = "solar_capture_deferred"

    uitleg = c._build_explanation()

    assert REASON_REGISTRY["solar_capture_deferred"]["uitleg"] in uitleg


def test_de_registry_levert_de_titels_voor_het_dashboard():
    """Vijfde afgeleide: waar de kaart de reden toont, komt de titel uit
    dezelfde bron."""
    from custom_components.energy_management_system.const import REASON_REGISTRY

    assert hasattr(pkg, "__file__")
    for reden, g in REASON_REGISTRY.items():
        assert not g["titel"].startswith(reden), f"{reden}: titel is de sleutel"


# --- v4.21: de vier parallelle tabellen zijn nu afgeleiden -----------
#
# Uit de architectuuraudit: `REASON_REGISTRY` was zelf één van vijf
# tabellen die op dezelfde sleutel indexeerden.
#
#   DECISION_REASON_LABELS  16  "Zon opvangen uitgesteld (betere prijs nu)"
#   WHY_QUESTIONS           16  "Waarom laad je nu nog niet?"
#   REDEN_KORTE_NAAM        11  "huis dekken, zon later"
#   MODE_CHANGE_EMOJI       10  "⏳"
#
# Alle vier hadden 100% sleuteloverlap met de registry. Ze zijn nu
# comprehensies over de registry; uiteenlopen kan niet meer.
#
# Dat de eerste twee zestien sleutels hadden tegen vijftien in de
# registry was GEEN fout: ze indexeren verklaarbare toestanden, en
# `grid_cheaper_than_battery` is er wel een maar stuurt niet - daar
# staat sinds v1.x een toets op. Die staat nu in de registry met
# `stuurt: False`. Dat onderscheid vond ik pas bij het bouwen, niet bij
# het ontwerpen.


def test_de_vier_tabellen_zijn_afgeleiden():
    from custom_components.energy_management_system.const import (
        DECISION_REASON_LABELS,
        MODE_CHANGE_EMOJI,
        REASON_REGISTRY,
        REDEN_KORTE_NAAM,
        WHY_QUESTIONS,
    )

    assert DECISION_REASON_LABELS == {
        r: g["label"] for r, g in REASON_REGISTRY.items() if g.get("label")
    }
    assert WHY_QUESTIONS == {
        r: g["waarom_vraag"] for r, g in REASON_REGISTRY.items() if g.get("waarom_vraag")
    }
    assert REDEN_KORTE_NAAM == {
        r: g["korte_naam"] for r, g in REASON_REGISTRY.items() if g.get("korte_naam")
    }
    assert MODE_CHANGE_EMOJI == {
        r: g["emoji"] for r, g in REASON_REGISTRY.items() if g.get("emoji")
    }


def test_geen_van_de_vier_is_nog_een_eigen_lijst():
    """De ratel: een handmatige lijst die toevallig gelijk is aan de
    afgeleide, is geen afgeleide. Alleen de comprehensie telt."""
    bron = (PAKKET / "const.py").read_text()
    for naam in (
        "DECISION_REASON_LABELS",
        "WHY_QUESTIONS",
        "REDEN_KORTE_NAAM",
        "MODE_CHANGE_EMOJI",
    ):
        i = bron.index("\n" + naam + " = ")
        blok = bron[i : bron.index("\n}", i)]
        assert "REASON_REGISTRY" in blok, f"{naam} is geen afgeleide:\n{blok[:160]}"
        assert bron.count("\n" + naam + " = ") == 1, f"{naam} staat er twee keer"


def test_een_niet_sturende_toestand_komt_niet_in_de_standvertaling():
    """`grid_cheaper_than_battery` wordt gemeten en uitgelegd, maar mag
    nooit een accustand kiezen - daar staat sinds v1.x een toets op."""
    from custom_components.energy_management_system.const import (
        REASON_REGISTRY,
        REASON_TO_MODE,
    )

    assert REASON_REGISTRY["grid_cheaper_than_battery"]["stuurt"] is False
    assert "grid_cheaper_than_battery" not in REASON_TO_MODE
    assert "grid_cheaper_than_battery" in REASON_REGISTRY


def test_elke_sturende_reden_heeft_een_stand():
    """En de andere kant: wie stuurt, heeft een stand."""
    from custom_components.energy_management_system.const import REASON_REGISTRY

    for reden, g in REASON_REGISTRY.items():
        if g.get("stuurt") is False:
            continue
        if reden == "no_forecast_data":
            continue  # past bewust niets toe
        assert g["mode"] is not None, reden
