"""v5.132.0: de airco verwarmt op zonoverschot (Ruud 26-10).

"Vanmiddag heb ik de airco aangezet omdat er nog zonne-energie was en de accu
vol, kunnen we daar iets slims voor bedenken wanneer woonkamer onder 17 graden
is". Gekozen: ESP-sensor onder 17 °C, alleen als er iemand thuis is, tot 21 °C
en aan tot 21 °C (ook als de zon wegvalt). Werkt los van de knop Airco automaat.
"""
from datetime import timedelta

import pytest

from custom_components.energy_management_system import airco_sturing

from tests.test_airco_sturing import NU, _coordinator

KAAL = {"actie": "niets", "tekst": "Leert nog.", "redenen": ["woonkamer 16.7 °C"]}


def _zon(uit=None, **kw):
    args = dict(woonkamer_c=16.7, aanwezigheid="thuis", overschot_minuten=12,
                airco_stand="off", zon_aan=False, handmatig=False,
                onder_c=17.0, doel_c=21.0, minuten_nodig=10)
    args.update(kw)
    return airco_sturing.verwarm_op_zonoverschot(dict(uit or KAAL), **args)


def test_aan_bij_vol_overschot_en_koud():
    b, aan = _zon()
    assert aan is True
    assert b["actie"] == "verwarmen" and b["doel_c"] == 21.0 and b["altijd"] is True
    assert "zonoverschot" in b["tekst"]


@pytest.mark.parametrize("kw", [
    {"woonkamer_c": 17.0},            # niet onder 17 °C
    {"aanwezigheid": "weg"},
    {"overschot_minuten": None},       # geen overschot of accu niet vol
    {"overschot_minuten": 9},          # nog geen tien minuten
    {"airco_stand": "heat"},           # verwarmt al
    {"handmatig": True},               # iemand bedient hem zelf
])
def test_niet_aan(kw):
    b, aan = _zon(**kw)
    assert aan is False and b["actie"] == "niets"


def test_blijft_aan_als_de_zon_wegvalt_tot_21():
    b, aan = _zon(zon_aan=True, overschot_minuten=None, woonkamer_c=19.0,
                  uit=dict(KAAL, actie="uit", tekst="Niemand thuis."))
    assert aan is True and b["actie"] == "niets"
    assert "tot 21" in b["tekst"]


def test_uit_bij_21():
    b, aan = _zon(zon_aan=True, woonkamer_c=21.0)
    assert aan is False and b["actie"] == "uit" and b["altijd"] is True


def test_zelf_bediend_dan_laat_het_ems_los():
    b, aan = _zon(zon_aan=True, woonkamer_c=21.5, handmatig=True)
    assert aan is False and b["actie"] == "niets"


@pytest.mark.asyncio
async def test_in_de_ronde_ook_met_de_knop_uit(make_coordinator, hass):
    c, aanroepen, taken = _coordinator(make_coordinator, hass)
    c.living_room_current_temp_c = 16.7
    c._overschot_toestand = lambda: {"overschot_w": 1200.0, "accu_vol": True, "laadt_op_max": False}
    assert c.airco_automaat_aan is False

    c._airco_ronde(NU)
    assert c.last_airco_besluit["toegepast"] is False   # nog geen tien minuten
    c._airco_ronde(NU + timedelta(minutes=10))
    for taak in taken:
        await taak

    b = c.last_airco_besluit
    assert b["toegepast"] is True and b["zon"] is True
    assert aanroepen[-1] == ("climate", "set_temperature",
                             {"entity_id": "climate.woonkamer", "temperature": 21.0, "hvac_mode": "heat"})
    assert c._airco_zon_aan is True and c.airco_door_ems is True


@pytest.mark.asyncio
async def test_te_weinig_overschot_of_accu_niet_vol(make_coordinator, hass):
    c, aanroepen, taken = _coordinator(make_coordinator, hass)
    c.living_room_current_temp_c = 16.7
    c._overschot_toestand = lambda: {"overschot_w": 500.0, "accu_vol": True, "laadt_op_max": False}
    c._airco_ronde(NU)
    c._airco_ronde(NU + timedelta(minutes=15))
    c._overschot_toestand = lambda: {"overschot_w": 1500.0, "accu_vol": False, "laadt_op_max": True}
    c._airco_ronde(NU + timedelta(minutes=30))
    c._airco_ronde(NU + timedelta(minutes=45))
    for taak in taken:
        await taak
    assert aanroepen == []
