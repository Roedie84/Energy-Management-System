"""v5.175.3 - 'houden' met een lege accu heet 'Accu leeg - huis op het net'.

Gemeld 03-11 19:00: "Waarom spaart de accu nu? Leeg gaat hij toch" - stand
'bewaren (waardeplan)' terwijl er 0,00 kWh bruikbaar was. Akkoord Ruud 19:02.
"""
import asyncio

from custom_components.energy_management_system.const import (
    NACHT_BEWUST_NIET_ONTLADEN_REDENEN,
    OPTION_SMART_CHARGING,
    REDENEN_BEWUSTE_NETAFNAME,
)
from tests.test_v5158_waardeplan import NU, _c, _plan


def _met_inhoud(c, soc, inhoud):
    c.accustand_procent = lambda: soc
    c.beschikbare_energie_kwh = lambda: inhoud
    c.effectieve_ondergrens_procent = lambda now: 10.0
    return c


def test_lege_accu_heet_leeg(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("houden", 0.0, 0.0, inhoud=0.0))
    _met_inhoud(c, 12, 0.0)
    assert asyncio.run(c._waardeplan_als_nodig(NU, [])) is True
    assert c.last_reason == "waardeplan_leeg"
    assert t[-1] == ("stand", OPTION_SMART_CHARGING)


def test_volle_accu_blijft_houden(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("houden", 0.0, 0.0))
    _met_inhoud(c, 60, 5.0)
    asyncio.run(c._waardeplan_als_nodig(NU, []))
    assert c.last_reason == "waardeplan_houden"


def test_zelfde_behandeling_als_houden():
    assert "waardeplan_leeg" in NACHT_BEWUST_NIET_ONTLADEN_REDENEN
    assert "waardeplan_leeg" not in REDENEN_BEWUSTE_NETAFNAME


def test_geen_moduswisselmelding_bij_lege_accu(make_coordinator, hass):
    c, _t = _c(make_coordinator, _plan("houden", 0.0, 0.0))
    c.config["appliance_notify_service"] = "notify.x"
    verstuurd = []
    c._dispatch_notification = lambda **kw: verstuurd.append(kw)
    c.learning_only = False
    c._last_notified_mode_signature = ("waardeplan_huis", None, None)
    c.last_reason = "waardeplan_leeg"
    c._maybe_notify_mode_change(NU)
    assert verstuurd == []
    assert c.mode_change_log[-1]["reason"] == "waardeplan_leeg"


def test_uitleg_leeg_belooft_geen_nul():
    """v5.176.2: bij 0,17 kWh en zwakste module op 11 % zei de tekst
    'geen bruikbare energie' en 'op de ondergrens' - dat klopte niet."""
    from custom_components.energy_management_system.const import REASON_REGISTRY
    uitleg = REASON_REGISTRY["waardeplan_leeg"]["uitleg"]
    assert "geen bruikbare" not in uitleg
    assert "staat op de ondergrens" not in uitleg
    assert "boven de ondergrens" in uitleg
