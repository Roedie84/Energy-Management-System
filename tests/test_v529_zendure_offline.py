"""v5.29 - de accu stond stil en het EMS merkte het niet.

Gemeld op 5 oktober: vanaf 07:10 elke minuut "No devices online, not possible
to start the operation". De zekeringgroep van de SolarFlow stond op "unused";
de Zendure-integratie zette het apparaat op status 3 (offline) en weigerde
elke opdracht. De modus-select bleef beschikbaar, dus het EMS bleef schrijven
- elke minuut, ook als de stand al goed stond - en meldde niets.
"""
import asyncio
from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.energy_management_system import zendure_status as zs
from custom_components.energy_management_system.const import (
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
    CONF_SOC_SENSOR,
    OPTION_SMART,
    OPTION_SMART_DISCHARGING,
)

STATUS = "sensor.solarflow_2400_ac_connection_status"
CONFIG = {
    CONF_OPERATION_SELECT: "select.op",
    CONF_MANUAL_POWER_NUMBER: "number.pow",
    CONF_SOC_SENSOR: "sensor.solarflow_2400_ac_electric_level",
}


def _opzet(make_coordinator, hass, status, stand="smart", vermogen="0"):
    c = make_coordinator(dict(CONFIG))
    hass.states.set("select.op", stand)
    hass.states.set("number.pow", vermogen)
    hass.states.set("sensor.solarflow_2400_ac_electric_level", "30")
    if status is not None:
        hass.states.set(STATUS, status)
    hass.services.calls.clear()
    return c


def _schrijfacties(hass):
    return [x for x in hass.services.calls if x[0] in ("select", "number")]


# --- het oordeel zelf ---------------------------------------------------


def test_status_3_is_offline_met_de_zekeringgroep_als_reden():
    oordeel = zs.beoordeel({STATUS: "3"})
    assert oordeel["online"] is False
    assert "zekeringgroep" in oordeel["reden"]
    assert "owncircuit" in oordeel["oplossing"]


def test_elke_reden_onder_tien_is_offline_en_vanaf_tien_online():
    for status in (0, 1, 2, 3):
        assert zs.beoordeel({STATUS: str(status)})["online"] is False
    for status in (10, 11, 12):
        assert zs.beoordeel({STATUS: str(status)})["online"] is True


def test_nul_is_een_meting():
    assert zs.beoordeel({STATUS: "0"})["online"] is False


def test_onbekend_is_niet_offline():
    for stand in ("unavailable", "unknown", None, "geen getal"):
        oordeel = zs.beoordeel({STATUS: stand})
        assert oordeel["bekend"] is False
        assert oordeel["online"] is None
    assert zs.beoordeel({})["online"] is None


def test_een_apparaat_online_is_genoeg_zoals_de_zendure_manager():
    oordeel = zs.beoordeel({STATUS: "3", "sensor.hyper_2000_connection_status": "12"})
    assert oordeel["online"] is True


def test_alleen_statussensoren_van_de_eigen_accu():
    accu = ["sensor.solarflow_2400_ac_electric_level"]
    assert zs.hoort_bij_accu(STATUS, accu)
    assert not zs.hoort_bij_accu("sensor.router_connection_status", accu)
    assert not zs.is_statusentiteit("binary_sensor.solarflow_2400_ac_connection_status")


# --- de aansturing --------------------------------------------------------


def test_offline_bij_zendure_schrijft_niets_en_zegt_waarom(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "3")
    asyncio.run(c._async_apply_operation(OPTION_SMART_DISCHARGING))
    assert _schrijfacties(hass) == []
    assert "zekeringgroep" in c.aansturing_onbereikbaar["reden"]
    punten = c.get_analyse()["punten"]
    assert any(
        p["onderwerp"] == "Accu niet aanstuurbaar" and "zekeringgroep" in p["wat"]
        for p in punten
    )


def test_offline_blokkeert_ook_handmatig(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "3")
    asyncio.run(c._async_apply_manual(-2400))
    assert _schrijfacties(hass) == []


def test_online_schrijft_gewoon(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "12")
    asyncio.run(c._async_apply_operation(OPTION_SMART_DISCHARGING))
    assert _schrijfacties(hass) == [
        ("select", "select_option", {"entity_id": "select.op", "option": OPTION_SMART_DISCHARGING})
    ]
    assert c.aansturing_onbereikbaar["reden"] is None


def test_zonder_statussensor_verandert_er_niets(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, None)
    asyncio.run(c._async_apply_operation(OPTION_SMART_DISCHARGING))
    assert len(_schrijfacties(hass)) == 1


def test_een_vreemde_statussensor_blokkeert_niet(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, None)
    hass.states.set("sensor.router_connection_status", "3")
    asyncio.run(c._async_apply_operation(OPTION_SMART_DISCHARGING))
    assert len(_schrijfacties(hass)) == 1


def test_herstel_heft_de_blokkade_op(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "3")
    asyncio.run(c._async_apply_operation(OPTION_SMART_DISCHARGING))
    assert _schrijfacties(hass) == []
    hass.states.set(STATUS, "12")
    asyncio.run(c._async_apply_operation(OPTION_SMART_DISCHARGING))
    assert len(_schrijfacties(hass)) == 1
    assert c.aansturing_onbereikbaar["reden"] is None


# --- niet herhalen wat al staat -----------------------------------------


def test_dezelfde_stand_wordt_niet_opnieuw_geschreven(make_coordinator, hass):
    """v5.31.2: de eerste keer wordt altijd geschreven - ook als de select
    er al op staat. Daarna niet meer, zolang het EMS het zelf schreef."""
    c = _opzet(make_coordinator, hass, "12", stand=OPTION_SMART)
    for _ in range(5):
        asyncio.run(c._async_apply_operation(OPTION_SMART))
    assert len(_schrijfacties(hass)) == 1
    assert c.last_applied_operation == OPTION_SMART


def test_handmatig_schrijft_alleen_wat_verandert(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "12", stand="manual", vermogen="-2400")
    asyncio.run(c._async_apply_manual(-2400))
    assert [x[0] for x in _schrijfacties(hass)] == ["select", "number"]
    hass.services.calls.clear()
    asyncio.run(c._async_apply_manual(-2400))
    assert _schrijfacties(hass) == []
    asyncio.run(c._async_apply_manual(-1500))
    assert _schrijfacties(hass) == [
        ("number", "set_value", {"entity_id": "number.pow", "value": -1500})
    ]


def test_van_slim_naar_handmatig_schrijft_beide(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "12", stand="smart", vermogen="0")
    asyncio.run(c._async_apply_manual(2400))
    assert [x[0] for x in _schrijfacties(hass)] == ["select", "number"]


# --- een melding, na tien minuten, één keer -------------------------------


def test_melding_pas_na_tien_minuten_en_maar_een_keer(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "3")
    verstuurd = []
    c._dispatch_notification = lambda **kw: verstuurd.append(kw)

    asyncio.run(c._async_apply_operation(OPTION_SMART_DISCHARGING))
    assert verstuurd == []

    c.aansturing_onbereikbaar["sinds"] = (dt_util.now() - timedelta(minutes=11)).isoformat()
    for _ in range(3):
        asyncio.run(c._async_apply_operation(OPTION_SMART_DISCHARGING))
    assert len(verstuurd) == 1
    assert verstuurd[0]["kind"] == "accu_niet_aanstuurbaar"
    assert "zekeringgroep" in verstuurd[0]["message"]

    hass.states.set(STATUS, "12")
    asyncio.run(c._async_apply_operation(OPTION_SMART_DISCHARGING))
    assert "gemeld" not in c.aansturing_onbereikbaar
