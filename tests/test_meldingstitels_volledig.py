"""Zes meldingen zonder Achterhoekse titel (v4.21).

Uit de architectuuraudit. De vier meldingstabellen leken fors uiteen te
lopen (39 / 39 / 43 / 42), maar na inspectie bleef er één echte
bevinding over:

    ACHTERHOEKS_TITELS mist zes meldingen:
      appliance_ready, appliance_cheap_moment, device_drift,
      handmatige_stand, mode_change, proefstand_rijp

Die vallen terug op de Nederlandse titel. `appliance_ready` gaat
zeventien keer per week naar de telefoon, dus dat is niet theoretisch -
het is alleen stil, want er gaat niets mis.

Dat was ook de les uit die audit: een verschillenrapport vertelt je waar
je moet kijken, niet hoe belangrijk het is. Van de drie "afwijkingen"
bleek er één functioneel: de drie extra logprioriteiten zijn
logcategorieën en geen meldingen, en MELDING_ADVIES sloot precies.
"""
import ast
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent


def _sleutels(naam: str) -> set[str]:
    boom = ast.parse((PAKKET / "const.py").read_text())
    for k in boom.body:
        d = None
        if isinstance(k, ast.Assign) and isinstance(k.targets[0], ast.Name):
            d = k.targets[0].id
        elif isinstance(k, ast.AnnAssign) and isinstance(k.target, ast.Name):
            d = k.target.id
        if d != naam:
            continue
        v = k.value
        if isinstance(v, ast.Dict):
            return {e.value for e in v.keys if isinstance(e, ast.Constant)}
        if isinstance(v, (ast.Tuple, ast.List, ast.Set)):
            uit = set()
            for e in v.elts:
                if isinstance(e, ast.Constant):
                    uit.add(e.value)
                elif isinstance(e, (ast.Tuple, ast.List)) and isinstance(
                    e.elts[0], ast.Constant
                ):
                    uit.add(e.elts[0].value)
            return uit
    return set()


def test_elke_melding_heeft_een_achterhoekse_titel_of_bouwt_hem_op():
    """De audit meldde zes ontbrekende titels, en ik heb ze er bijna
    ingezet. Maar die zes BOUWEN hun titel op uit wat er gebeurde -
    "Steelstofzuiger opgeladen" noemt het apparaat, `mode_change` noemt
    de stand - en een vaste titel gooit dat weg. Daar staat sinds v1.x
    een toets op, die mijn wijziging meteen afkeurde.

    Dat is de les van die audit, op mijzelf toegepast: een
    verschillenrapport zegt waar je moet kijken, niet hoe belangrijk het
    is. De zes staan nu in `TITEL_WORDT_OPGEBOUWD`, zodat een volgende
    audit ze niet opnieuw als gat leest.
    """
    from custom_components.energy_management_system.const import (
        TITEL_WORDT_OPGEBOUWD,
    )

    soorten = _sleutels("NOTIFICATION_TYPES")
    titels = _sleutels("ACHTERHOEKS_TITELS")

    zonder = sorted(soorten - titels - set(TITEL_WORDT_OPGEBOUWD))
    assert not zonder, zonder


def test_elke_melding_heeft_een_advies():
    """Die sloot al precies; de ratel houdt dat vast."""
    soorten = _sleutels("NOTIFICATION_TYPES")
    advies = _sleutels("MELDING_ADVIES")

    assert not sorted(soorten - advies)


def test_elke_melding_heeft_een_logprioriteit():
    soorten = _sleutels("NOTIFICATION_TYPES")
    prios = _sleutels("LOG_PRIORITEITEN")

    assert not sorted(soorten - prios)


def test_de_extra_logprioriteiten_zijn_geen_meldingen():
    """Drie sleutels in LOG_PRIORITEITEN zijn logCATEGORIEËN en geen
    meldingen: `besluit`, `energiebrug`, `terugval`. Die tabel indexeert
    dus twee dingen - dat mag, maar het hoort benoemd te zijn, anders
    leest een volgende audit het als divergentie.
    """
    from custom_components.energy_management_system.const import (
        LOG_CATEGORIEEN_GEEN_MELDING,
    )

    soorten = _sleutels("NOTIFICATION_TYPES")
    prios = _sleutels("LOG_PRIORITEITEN")

    extra = prios - soorten - {s + "_hersteld" for s in soorten}
    assert extra == set(LOG_CATEGORIEEN_GEEN_MELDING), sorted(extra)


def test_geen_titel_voor_een_melding_die_niet_bestaat():
    """De andere kant: een Achterhoekse titel voor iets dat geen melding
    is, is dode metadata die bij een hernoeming meeliegt."""
    soorten = _sleutels("NOTIFICATION_TYPES")
    titels = _sleutels("ACHTERHOEKS_TITELS")

    dood = sorted(
        t for t in titels - soorten if not t.endswith("_hersteld")
    )
    assert not dood, dood
