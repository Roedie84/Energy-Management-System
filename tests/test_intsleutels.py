"""Uursleutels overleven een herstart als int (v4.6).

Uit het logboek, twintig keer:

    File "sensor.py", line 3176, in native_value
      return len(self._coordinator.learned_appliance_usage_hours(...))
    File "coordinator.py", line 3472, in learned_appliance_usage_hours
      return sorted(typical_hours)
    TypeError: '<' not supported between instances of 'int' and 'str'

`dishwasher_usage_hourly_history` heeft uren als sleutel. In v4.1 is die
reeks naar de Store verhuisd, en JSON maakt van 13 een "13". Bij het
laden kwamen de oude uren terug als tekst; de nieuwe uren van vandaag
werden als int toegevoegd. Sorteren op een gemengde lijst werpt dan een
TypeError, en de sensor viel om.

Ik had dit voorzien - PERSISTED_INTKEY_DICT_FIELDS bestaat sinds v4.1 -
maar de scan waarmee ik de kandidaten zocht keek naar
`self.X.setdefault(now.hour`, en deze twee reeksen worden als PARAMETER
doorgegeven: `history.setdefault(now.hour, [])`. Een scan op de vorm van
de code miste dus precies het geval waar hij voor bedoeld was.

Nu twee dingen: de twee reeksen staan in de omzetlijst, en de scan kijkt
niet meer naar de aanroep maar naar de TYPE-ANNOTATIE in `__init__` -
`dict[int, ...]`. Die kan er niet omheen.
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import (
    PERSISTED_INTKEY_DICT_FIELDS,
    PERSISTED_PLAIN_FIELDS,
)


def _velden_met_intsleutels() -> set[str]:
    """Elk veld dat in `__init__` als `dict[int, ...]` is aangekondigd."""
    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    return set(re.findall(r"self\.(\w+):\s*dict\[int,", bron))


def test_elk_bewaard_veld_met_uursleutels_wordt_omgezet():
    """De ratel: een nieuw `dict[int, ...]` dat naar de Store gaat zonder
    omzetting laat deze toets omvallen."""
    met_intsleutels = _velden_met_intsleutels()

    vergeten = sorted(
        (met_intsleutels & set(PERSISTED_PLAIN_FIELDS)) - set(PERSISTED_INTKEY_DICT_FIELDS)
    )

    assert not vergeten, vergeten


def test_de_twee_apparaatreeksen_staan_erin():
    """Het geval uit het logboek."""
    assert "dishwasher_usage_hourly_history" in PERSISTED_INTKEY_DICT_FIELDS
    assert "washing_machine_usage_hourly_history" in PERSISTED_INTKEY_DICT_FIELDS


def test_de_omzetting_komt_na_het_gewone_laden():
    """Beide velden staan ook in PERSISTED_PLAIN_FIELDS; die zet de
    tekstversie terug. De omzetting moet daarna komen, anders wint de
    tekst."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    gewoon = bron.index("for veld in PERSISTED_PLAIN_FIELDS + PERSISTED_INT_FIELDS")
    # de eerste vermelding zit in het WEGSCHRIJVEN; die van het laden
    # komt daarna.
    omzetting = bron.index("for veld in PERSISTED_INTKEY_DICT_FIELDS", gewoon)

    assert gewoon < omzetting


def test_gemengde_sleutels_werpen_geen_fout(make_coordinator, hass):
    """Vangnet voor wat er al in de opslag staat: een reeks die half
    tekst is, mag de sensor niet omgooien."""
    c = make_coordinator({})

    uren = c.learned_appliance_usage_hours({"13": [1.0, 1.0], 14: [1.0], "9": [0.0]})

    assert uren == [13, 14]


def test_de_omzetting_bij_het_laden_werkt(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        PERSISTED_INTKEY_DICT_FIELDS as VELDEN,
    )

    c = make_coordinator({})
    for veld in VELDEN:
        setattr(c, veld, {})
    c._apply_persisted_state({v: {"13": [1.0]} for v in VELDEN})

    for veld in VELDEN:
        assert list(getattr(c, veld)) == [13], veld
