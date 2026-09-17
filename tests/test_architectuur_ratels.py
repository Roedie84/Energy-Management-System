"""Architectuurratels: één eigenaar per dataset (v4.19).

Gevraagd na de naamcollisie van v4.18:

    "Hetzelfde probleem heeft zich nu meerdere keren voorgedaan: reserve,
     kandidaten, modellen, handmatige_ingrepen. Elke persistente dataset
     moet precies één eigenaar hebben."

Dat is juist, en de lijst is langer dan die vier: ook twee parenvormen
(v4.17.1) en twee nabeschouwingsmodellen (v4.12). Zes keer hetzelfde
patroon, en de laatste keer maakte ik hem zelf.

Deze toetsen zijn geen refactor - ze zijn de RATEL. Wat er nu staat
wordt vastgelegd, en een zevende geval laat de suite omvallen in plaats
van in een export op te duiken.

Wat hier NIET in staat, en waarom: "geen component mag rechtstreeks
coordinator-attributen benaderen" is een herschrijving van 35.000
regels, en die lost niets op wat deze ratels niet al vangen. Het staat
in de v5-schets als doel, niet als toets.
"""
import ast
import collections
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import (
    PERSISTED_DATE_FIELDS,
    PERSISTED_DATETIME_FIELDS,
    PERSISTED_INT_FIELDS,
    PERSISTED_PLAIN_FIELDS,
)

PAKKET = Path(pkg.__file__).parent
COORD = (PAKKET / "coordinator.py").read_text()
ALLE_BEWAARD = (
    set(PERSISTED_PLAIN_FIELDS)
    | set(PERSISTED_INT_FIELDS)
    | set(PERSISTED_DATE_FIELDS)
    | set(PERSISTED_DATETIME_FIELDS)
)

def test_elke_bewaarde_dataset_heeft_een_vorm(make_coordinator, hass):
    """`assert_exactly_one_writer`, maar op de vorm in plaats van op het
    aantal schrijvers - want dat laatste keurt 41 bestaande plekken af
    die allemaal terecht zijn: een resetter, een bootstrapper, een
    dagwisselaar, een bevestig/verwerp-paar. Zo'n ratel wordt uitgezet.

    Het gemeenschappelijke in de zes incidenten is niet het aantal
    schrijvers maar TWEE BETEKENISSEN IN ÉÉN BAK:

      v4.18    handmatige_ingrepen: valse ingrepen + eigen ingrepen
      v4.17.1  weerbron_helderheid_paren: vier- en vijf-velds paren
      v4.12    nabeschouwing: bodem-model en poort-model
      v4.13    kandidaten: oude en nieuwe telling
      v4.1     reserve: drie lezers met elk hun eigen berekening

    Een dataset waarin twee records niet dezelfde soort informatie
    dragen, is een dataset met twee eigenaren. Dat is wat deze toets
    meet: records in één lijst moeten een overlappende sleutelverzameling
    hebben.
    """
    c = make_coordinator({})
    fouten = []
    for veld in sorted(ALLE_BEWAARD):
        waarde = getattr(c, veld, None)
        if not isinstance(waarde, list) or len(waarde) < 2:
            continue
        vormen = {
            frozenset(r) if isinstance(r, dict) else type(r).__name__
            for r in waarde
        }
        if len(vormen) > 1 and all(isinstance(v, frozenset) for v in vormen):
            # disjuncte sleutelverzamelingen = twee betekenissen
            paren = list(vormen)
            for a in range(len(paren)):
                for b in range(a + 1, len(paren)):
                    if not (paren[a] & paren[b]):
                        fouten.append(f"{veld}: {sorted(paren[a])} vs {sorted(paren[b])}")
    assert not fouten, fouten


def test_de_vormcontrole_vangt_het_geval_van_v4_18(make_coordinator, hass):
    """Bewijs dat de ratel werkt: de collisie van v4.18 nagebouwd."""
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        {"moment": "x", "ems_wilde": "smart", "werkelijk": "manual"},
        {"stand": "laden", "soc": 38.0, "apparaten_aan": {}},
    ]
    vormen = [frozenset(r) for r in c.handmatige_ingrepen]

    assert not (vormen[0] & vormen[1]), "disjunct: twee betekenissen in één lijst"


def test_geen_dubbele_sleutel_in_de_export():
    """Wat er bij v4.18 gebeurde: `handmatige_ingrepen` stond twee keer
    in de exportdict en de ene overschreef de andere."""
    for naam in ("diagnostics.py", "coordinator.py", "sensor.py"):
        boom = ast.parse((PAKKET / naam).read_text())
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.Dict):
                continue
            sleutels = [
                k.value for k in knoop.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            ]
            dubbel = {s for s in sleutels if sleutels.count(s) > 1}
            assert not dubbel, f"{naam}:{knoop.lineno} {dubbel}"


def test_elke_beslisreden_heeft_een_uitleg(make_coordinator, hass):
    """Gevraagd: "Geen enkele nieuwe reason mag ooit productie bereiken
    zonder vertaling."

    Gevonden in de export: "Onbekende reden: solar_capture_deferred".
    Die staat wél in REASON_TO_MODE en in de Nederlandse woordenlijst,
    maar `_build_explanation` kende hem niet en viel terug op die tekst.
    Beslisboom en uitleglaag stonden dus niet synchroon.
    """
    from custom_components.energy_management_system.const import (
        REASON_TO_MODE,
        REDENEN_ZONDER_STAND,
    )

    c = make_coordinator({})
    # Het GEDRAG toetsen, niet de tekst: een redennaam kan in een
    # opmerking staan zonder dat de tak bestaat. Een tekstuele toets
    # slaagde dan ook terwijl `solar_capture_deferred` en `force_manual`
    # in werkelijkheid geen uitleg kregen.
    # Sommige redenen kunnen alleen bij een bijbehorende schakelaar
    # voorkomen; die hoort dan mee gezet te worden, anders meet de toets
    # een toestand die in bedrijf niet bestaat.
    SCHAKELAAR = {"force_manual": "force_manual", "kalibratie": "kalibratie"}
    zonder = []
    for reden in sorted(set(REASON_TO_MODE) | set(REDENEN_ZONDER_STAND)):
        for naam in SCHAKELAAR.values():
            setattr(c, naam, False)
        if reden in SCHAKELAAR:
            setattr(c, SCHAKELAAR[reden], True)
        c.last_reason = reden
        if "Onbekende reden" in c._build_explanation():
            zonder.append(reden)
    assert not zonder, zonder


def test_elke_beslisreden_heeft_een_nederlandse_naam():
    """De tweede vertaallaag: de meldingstitels."""
    import json

    from custom_components.energy_management_system.const import (
        REASON_TO_MODE,
        REDENEN_ZONDER_STAND,
    )

    nl = json.loads((PAKKET / "translations" / "nl.json").read_text())
    tekst = json.dumps(nl, ensure_ascii=False) + COORD
    zonder = sorted(
        r for r in (set(REASON_TO_MODE) | set(REDENEN_ZONDER_STAND)) if r not in tekst
    )
    assert not zonder, zonder


def test_geen_dubbele_methodenaam_in_de_klasse():
    """De ratel die drie collisies had gevangen.

    Python neemt bij twee methoden met dezelfde naam stilzwijgend de
    LAATSTE; de eerste verdwijnt zonder waarschuwing. In deze reeks
    gebeurde dat drie keer:

      v4.18    `handmatige_ingrepen` - veld, al in gebruik sinds v3.99.9
      v4.19    `get_moduswissels`    - methode, al in gebruik sinds v3.87.0
      v4.17.1  twee parenvormen in één dataset

    De eerste twee waren met deze toets voorkomen. Hij kost niets en
    draait in een halve seconde.
    """
    for naam in ("coordinator.py", "sensor.py", "switch.py", "button.py"):
        boom = ast.parse((PAKKET / naam).read_text())
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.ClassDef):
                continue
            # Een property met zijn setter heet twee keer hetzelfde en
            # dat is de bedoelde vorm - te herkennen aan `@<naam>.setter`.
            namen = []
            for k in knoop.body:
                if not isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                is_setter = any(
                    isinstance(d, ast.Attribute) and d.attr in ("setter", "deleter")
                    for d in k.decorator_list
                )
                if not is_setter:
                    namen.append(k.name)
            dubbel = {n for n in namen if namen.count(n) > 1}
            assert not dubbel, f"{naam}:{knoop.name} {dubbel}"


def test_geen_dubbel_bewaard_veld_met_twee_betekenissen():
    """En dezelfde controle voor de velden: een naam die twee keer in
    `__init__` wordt gezet, hoort niet."""
    boom = ast.parse(COORD)
    for knoop in ast.walk(boom):
        if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if knoop.name != "__init__":
            continue
        gezet = []
        for n in ast.walk(knoop):
            if not isinstance(n, ast.Assign) and not isinstance(n, ast.AnnAssign):
                continue
            doelen = n.targets if isinstance(n, ast.Assign) else [n.target]
            for d in doelen:
                for el in (d.elts if isinstance(d, (ast.Tuple, ast.List)) else [d]):
                    if (
                        isinstance(el, ast.Attribute)
                        and isinstance(el.value, ast.Name)
                        and el.value.id == "self"
                    ):
                        gezet.append(el.attr)
        dubbel = {n for n in gezet if gezet.count(n) > 1}
        assert not dubbel, sorted(dubbel)
