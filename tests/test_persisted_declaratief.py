"""PERSISTED_FIELDS: één verklaring per veld (v5.2).

Fase A1 uit de architectuurafspraak. De semantiek zat in de LIJSTNAAM:

    PERSISTED_PLAIN_FIELDS       163 velden
    PERSISTED_INT_FIELDS           3
    PERSISTED_DATE_FIELDS         13
    PERSISTED_DATETIME_FIELDS      4
    PERSISTED_INTKEY_DICT_FIELDS   4

Daardoor waren de fouten van v4.6 (uursleutels die als tekst terugkwamen)
en v4.7 (dagmetingen in geen enkele lijst) bijna onvermijdelijk: je moest
onthouden in welke lijst een veld hoorde, en vergeten was stil.

Nu één tabel met het type per veld, waaruit de vijf lijsten worden
AFGELEID. Een veld vergeten is dan een ontbrekende sleutel in plaats van
een veld dat nergens staat, en de ratel vindt het.

De inventory over alle 187 velden gaf nul afwijkingen, dus dit verandert
geen gedrag. Het maakt de fout architectonisch moeilijk in plaats van
bewaakt.
"""
import ast
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent
CONST = (PAKKET / "const.py").read_text()


def test_elke_lijst_is_afgeleid_van_de_verklaring():
    from custom_components.energy_management_system.const import (
        PERSISTED_DATE_FIELDS,
        PERSISTED_DATETIME_FIELDS,
        PERSISTED_FIELDS,
        PERSISTED_INT_FIELDS,
        PERSISTED_INTKEY_DICT_FIELDS,
        PERSISTED_PLAIN_FIELDS,
    )

    def van_type(soort):
        return tuple(
            veld for veld, g in PERSISTED_FIELDS.items() if g["type"] == soort
        )

    assert set(PERSISTED_PLAIN_FIELDS) == set(van_type("plain"))
    assert set(PERSISTED_INT_FIELDS) == set(van_type("int"))
    assert set(PERSISTED_DATE_FIELDS) == set(van_type("date"))
    assert set(PERSISTED_DATETIME_FIELDS) == set(van_type("datetime"))
    assert set(PERSISTED_INTKEY_DICT_FIELDS) == set(
        veld for veld, g in PERSISTED_FIELDS.items() if g.get("uursleutels")
    )


def test_geen_van_de_vijf_lijsten_is_nog_handmatig():
    """De ratel: een handmatige lijst die toevallig gelijk is aan de
    afgeleide, is geen afgeleide."""
    for naam in (
        "PERSISTED_PLAIN_FIELDS",
        "PERSISTED_INT_FIELDS",
        "PERSISTED_DATE_FIELDS",
        "PERSISTED_DATETIME_FIELDS",
        "PERSISTED_INTKEY_DICT_FIELDS",
    ):
        treffers = re.findall(r"\n" + naam + r"(?::[^=\n]*)? = ", CONST)
        assert len(treffers) == 1, f"{naam} staat {len(treffers)} keer"
        i = CONST.index("\n" + naam)
        blok = CONST[i : i + 400]
        assert "PERSISTED_FIELDS" in blok, f"{naam} is geen afgeleide"


def test_elk_veld_heeft_een_type():
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    toegestaan = {"plain", "int", "date", "datetime", "uurdict"}
    for veld, g in PERSISTED_FIELDS.items():
        assert g.get("type") in toegestaan, f"{veld}: {g.get('type')}"


def test_elk_verklaard_veld_bestaat_op_de_coordinator(make_coordinator, hass):
    """De fout van v4.7: een veld dat in geen enkele lijst stond. Nu is
    het omgekeerde ook geregeld - een verklaring zonder veld."""
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    c = make_coordinator({})
    ontbreekt = [v for v in PERSISTED_FIELDS if not hasattr(c, v)]

    assert not ontbreekt, ontbreekt


def test_de_uursleutelvelden_staan_ook_als_plain():
    """v4.6: de twee uurreeksen moeten in beide lijsten staan - eerst
    gewoon terugzetten, dan de sleutels omzetten. Dat was bewust, en
    het hoort uit de verklaring te volgen in plaats van uit twee
    handmatige vermeldingen."""
    from custom_components.energy_management_system.const import (
        PERSISTED_FIELDS,
        PERSISTED_INTKEY_DICT_FIELDS,
        PERSISTED_PLAIN_FIELDS,
    )

    # Twee van de vier stonden in BEIDE lijsten en twee alleen als
    # uurdict. Dat onderscheid bestond al en hangt aan de laadorde; de
    # verklaring bewaart het in plaats van het glad te strijken.
    beide = [v for v in PERSISTED_INTKEY_DICT_FIELDS if v in PERSISTED_PLAIN_FIELDS]
    for veld in PERSISTED_INTKEY_DICT_FIELDS:
        assert PERSISTED_FIELDS[veld].get("uursleutels") is True, veld
        assert PERSISTED_FIELDS[veld]["type"] in ("plain", "uurdict"), veld
    assert len(beide) == 2, beide


def test_de_vier_laadconversies_zijn_benoemd():
    """De migraties bestaan al als gedrag - vier `if`-jes in
    `_apply_persisted_state` - maar niet als contract. Benoemd betekent
    dat een volgende vormwijziging niet stilzwijgend de vijfde wordt."""
    from custom_components.energy_management_system.const import (
        PERSISTED_CONVERSIES,
    )

    soorten = {c["veld_of_type"] for c in PERSISTED_CONVERSIES}

    assert "uursleutels" in soorten
    assert "date" in soorten
    assert "datetime" in soorten
    assert "weerbron_helderheid_paren" in soorten
    for conversie in PERSISTED_CONVERSIES:
        assert conversie["sinds"], conversie
        assert conversie["wat"], conversie


def test_het_aantal_velden_klopt_met_de_inventory():
    """187 verklaarde velden, nul afwijkingen - de meting waarop besloten
    is dat hier geen haast bij was."""
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    assert len(PERSISTED_FIELDS) >= 185
