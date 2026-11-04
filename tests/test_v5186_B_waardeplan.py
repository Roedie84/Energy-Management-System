"""v5.186.0 track B: de uitvoering van het waardeplan.

B11 na een herplanning midden in het kwartier geen andere stand, tenzij die
    duidelijk beter is of de veiligheid erom vraagt; herplanningen geteld.
B12 zon_export laadt niet meer dan het zonoverschot van nu.
B23 inhalen aan het eind van het kwartier begrensd; ronde na elke kwartiergrens.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_MANUAL_CHARGE_POWER,
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
    WAARDEPLAN_INHAAL_FACTOR,
)

SELECT = "select.op"
NUMBER = "number.pow"
T0 = datetime(2026, 11, 4, 17, 0, 30, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _c(make_coordinator, hass, **extra):
    c = make_coordinator({CONF_OPERATION_SELECT: SELECT, CONF_MANUAL_POWER_NUMBER: NUMBER,
                          CONF_MANUAL_CHARGE_POWER: 2400, **extra})
    hass.states.set(SELECT, "smart", {"options": ["smart", "manual", "smart_charging"]})
    hass.states.set(NUMBER, "0")
    c._is_emergency_low_battery = lambda: False
    c._update_financial_tracking = lambda *a, **k: None
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda now: None
    c._overschot_toestand = lambda: {"overschot_w": 500.0, "accu_vol": False}
    c._waardeplan_accu_leeg = lambda now: False
    return c


def _plan(berekend, actie, accu_kwh=-0.2, uren=0.24, prijs=0.25, eind=0.26):
    return {"beschikbaar": True, "berekend_om": berekend.isoformat(), "inhoud_kwh": 3.0,
            "eindwaarde_eur_per_kwh": eind,
            "nu": {"actie": actie, "kwh": abs(accu_kwh), "accu_kwh": accu_kwh, "uren": uren,
                   "rekenprijs_eur": prijs}}


def _ronde(c, plan, now):
    c._waardeplan_nu = lambda n, e: plan
    # v5.186.0 (A20): het plan komt async uit de executor.
    async def _async_plan(n, e):
        return plan
    c._async_waardeplan_nu = _async_plan
    _run(c._waardeplan_als_nodig(now, []))
    return c.last_waardeplan


def test_geen_standwissel_na_herplanning_midden_in_het_kwartier(make_coordinator, hass):
    """Live 04-11 17:02: smart -> smart_charging -> smart binnen 23 s."""
    c = _c(make_coordinator, hass)
    _ronde(c, _plan(T0, "huis"), T0)
    assert c.last_reason == "waardeplan_huis"
    later = T0 + timedelta(minutes=2)
    uit = _ronde(c, _plan(later, "houden", accu_kwh=0.0, uren=0.2), later)
    assert c.last_reason == "waardeplan_huis"
    assert uit["uitgevoerd"] == "huis"
    assert uit["midkwartier"]["gewisseld"] is False
    assert not any(x[2].get("option") == "smart_charging" for x in hass.services.calls)
    # Elke ronde opnieuw vastgehouden, maar één keer geteld.
    _ronde(c, _plan(later, "houden", accu_kwh=0.0, uren=0.2), later + timedelta(seconds=30))
    assert c.waardeplan_herplanningen["wissel_tegengehouden"] == 1


def test_nieuw_kwartier_mag_wel_wisselen(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _ronde(c, _plan(T0, "huis"), T0)
    volgend = T0 + timedelta(minutes=15)
    uit = _ronde(c, _plan(volgend, "houden", accu_kwh=0.0), volgend)
    assert uit["uitgevoerd"] == "houden"
    assert "midkwartier" not in uit


def test_duidelijk_beter_mag_wel_wisselen(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _ronde(c, _plan(T0, "huis", accu_kwh=-0.5, prijs=0.60, eind=0.10), T0)
    later = T0 + timedelta(minutes=1)
    uit = _ronde(c, _plan(later, "houden", accu_kwh=0.0, uren=0.22, prijs=0.60, eind=0.10), later)
    assert uit["uitgevoerd"] == "houden"
    assert uit["midkwartier"]["gewisseld"] is True
    assert "duidelijk beter" in uit["midkwartier"]["reden"]


def test_veiligheid_gaat_voor_vasthouden(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c._overschot_toestand = lambda: {"overschot_w": 1500.0, "accu_vol": False}
    _ronde(c, _plan(T0, "zon_export", accu_kwh=0.0), T0)
    c._overschot_toestand = lambda: {"overschot_w": -300.0, "accu_vol": False}
    later = T0 + timedelta(minutes=3)
    uit = _ronde(c, _plan(later, "huis", accu_kwh=-0.1), later)
    assert uit["uitgevoerd"] == "huis"
    assert "veiligheid" in uit["midkwartier"]["reden"]


def test_zelfde_stand_alleen_vermogen_bijstellen(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.beschikbare_energie_kwh = lambda: 3.0
    _ronde(c, _plan(T0, "laden_net", accu_kwh=0.5, uren=0.24), T0)
    later = T0 + timedelta(minutes=2)
    uit = _ronde(c, _plan(later, "laden_net", accu_kwh=0.3, uren=0.2), later)
    assert uit["uitgevoerd"] == "laden_net"
    assert "midkwartier" not in uit


def test_herplanning_midden_in_het_kwartier_wordt_geteld(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    inhoud = {"kwh": 3.0}
    c.beschikbare_energie_kwh = lambda: inhoud["kwh"]
    c.bereken_waardeplan = lambda now, entries: _plan(now, "huis")
    c._opstart_stuurstil = lambda now=None: False
    c._waardeplan_nu(T0, [])
    inhoud["kwh"] = 4.0
    c._waardeplan_nu(T0 + timedelta(minutes=1), [])
    assert c.waardeplan_herplanningen["midkwartier"] == 1


# --- B12 ---------------------------------------------------------------------


def test_zon_export_laadt_niet_meer_dan_het_overschot(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c._overschot_toestand = lambda: {"overschot_w": 550.0, "accu_vol": False}
    c._waardeplan_cache = ("x", {})
    nu = {"actie": "zon_export", "kwh": 0.3, "accu_kwh": 0.3, "uren": 0.25}  # 1200 W gepland
    actie, laden, _ = c._waardeplan_opdracht(T0, {}, nu)
    assert laden == -550
    assert c._waardeplan_cache is None  # sterk afwijkend: opnieuw plannen
    assert c.waardeplan_herplanningen["zon_afwijking"] == 1


def test_zon_export_zonder_overschot_laadt_niet(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c._overschot_toestand = lambda: {"overschot_w": 100.0, "accu_vol": False}
    nu = {"actie": "zon_export", "kwh": 0.3, "accu_kwh": 0.3, "uren": 0.25}
    actie, laden, _ = c._waardeplan_opdracht(T0, {}, nu)
    assert actie == "zon_export" and laden is None


def test_zon_export_zonder_meting_als_gepland(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c._overschot_toestand = lambda: {"overschot_w": None}
    nu = {"actie": "zon_export", "kwh": 0.3, "accu_kwh": 0.3, "uren": 0.25}
    assert c._waardeplan_opdracht(T0, {}, nu)[1] == -1200


# --- B23 ---------------------------------------------------------------------


def test_inhalen_aan_het_eind_van_het_kwartier_begrensd(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.beschikbare_energie_kwh = lambda: 3.0  # nog niets geladen
    berekend = datetime(2026, 11, 4, 17, 0, 0, tzinfo=timezone.utc)
    rij = {"actie": "laden_net", "accu_kwh": 0.15, "uren": 0.25, "vol_vermogen": False}
    plan = {"berekend_om": berekend.isoformat(), "inhoud_kwh": 3.0, "laadrendement_procent": 100, "nu": rij}
    basis = 0.15 * 1000 / 0.25  # 600 W
    vlak_voor_eind = berekend + timedelta(minutes=14)
    assert c._waardeplan_laadvermogen_nu_w(rij, plan, vlak_voor_eind) == basis * WAARDEPLAN_INHAAL_FACTOR


def test_kwartierronde_wordt_geregistreerd(make_coordinator, hass, monkeypatch):
    from custom_components.energy_management_system import coordinator as mod

    geregistreerd = []
    monkeypatch.setattr(mod, "async_track_time_change",
                        lambda h, f, **k: geregistreerd.append((f.__name__, k)) or (lambda: None))
    c = make_coordinator({})
    c._registreer_kwartierklokken()
    namen = {n: k for n, k in geregistreerd}
    assert namen["_kwartierronde"]["minute"] == [0, 15, 30, 45]
    assert namen["_kwartierronde"]["second"] > 0
    assert c._unsub_kwartierronde is not None
