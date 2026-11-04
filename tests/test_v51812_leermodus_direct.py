"""Leermodus blijft niet hangen door een herstart vlak na het uitzetten (v5.181.2).

Gemeten 04-11: 11:25:38 'Handmatig smart charge' uit, de coordinator zette de
leermodus uit en bewaarde de vlag, maar de pollende schakelaar stond nog 'aan'
in Home Assistant toen die herstartte. Het herstellen zette de leermodus terug
aan, zonder vlag, dus de opruiming deed niets en het EMS stuurde niet meer.
Omdat `leermodus_sinds` niet bewaard wordt, kwam ook de melding niet.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.energy_management_system import switch as mod


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Coordinator:
    def __init__(self):
        self.learning_only = False
        self.leermodus_sinds = None
        self.luisteraars = []

    def register_listener(self, fn):
        self.luisteraars.append(fn)

    def unregister_listener(self, fn):
        self.luisteraars.remove(fn)


def _knop(c, staat=None):
    knop = mod.LearningOnlySwitch(c, "entry")
    knop.async_write_ha_state = lambda: None

    async def laatste():
        return staat

    knop.async_get_last_state = laatste
    return knop


def test_schakelaar_luistert_en_meldt_zich_af():
    c = _Coordinator()
    knop = _knop(c)
    _run(knop.async_added_to_hass())
    assert knop.async_write_ha_state in c.luisteraars
    _run(knop.async_will_remove_from_hass())
    assert c.luisteraars == []


def test_herstel_op_aan_neemt_het_echte_begin_over():
    begin = datetime(2026, 11, 4, 10, 22, tzinfo=timezone.utc)
    c = _Coordinator()
    _run(_knop(c, SimpleNamespace(state="on", last_changed=begin)).async_added_to_hass())
    assert c.learning_only is True
    assert c.leermodus_sinds == begin


def test_herstel_op_uit_zet_geen_begin():
    begin = datetime(2026, 11, 4, 10, 22, tzinfo=timezone.utc)
    c = _Coordinator()
    _run(_knop(c, SimpleNamespace(state="off", last_changed=begin)).async_added_to_hass())
    assert c.learning_only is False
    assert c.leermodus_sinds is None


def test_bestaand_begin_blijft_staan():
    begin = datetime(2026, 11, 4, 10, 22, tzinfo=timezone.utc)
    eerder = begin - timedelta(hours=1)
    c = _Coordinator()
    c.leermodus_sinds = eerder
    _run(_knop(c, SimpleNamespace(state="on", last_changed=begin)).async_added_to_hass())
    assert c.leermodus_sinds == eerder


def test_uitzetten_meldt_de_stand_voor_er_iets_anders_gebeurt(make_coordinator):
    """De stand moet al uit zijn op het moment dat de luisteraar vuurt: de
    opslag en de ronde erna kunnen door een afsluiting niet meer aan de beurt
    komen."""
    c = make_coordinator({})
    c.learning_only = True
    gezien = []
    c.register_listener(lambda: gezien.append(c.learning_only))

    async def niets():
        return None

    c.async_update = niets
    c.async_save_persisted_state_now = niets
    _run(c.async_set_learning_only(False))
    assert gezien and gezien[0] is False
