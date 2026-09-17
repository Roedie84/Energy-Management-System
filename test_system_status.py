"""System status tracking (v0.50.0): a simple health indicator ('OK' /
'Fout' / 'Mogelijk vastgelopen') so a problem shows up directly on the
dashboard instead of only in the Home Assistant logs.
"""
import asyncio
from datetime import datetime, timedelta, timezone

T0 = datetime(2026, 8, 3, hour=10, minute=0, tzinfo=timezone.utc)


def test_ok_after_a_successful_update(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
        }
    )
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: T0
    asyncio.run(coordinator.async_update())

    assert coordinator.system_status == "OK"


def test_fout_after_an_unexpected_exception(make_coordinator, hass):
    coordinator = make_coordinator({})

    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: T0

    async def broken_update():
        raise ValueError("something went wrong")

    coordinator._async_update_locked = broken_update
    asyncio.run(coordinator.async_update())

    assert coordinator.system_status == "Fout"
    assert coordinator.last_error == "something went wrong"


def test_recovers_to_ok_after_a_later_successful_update(make_coordinator, hass):
    coordinator = make_coordinator({})
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: T0

    async def broken_update():
        raise ValueError("boom")

    coordinator._async_update_locked = broken_update
    asyncio.run(coordinator.async_update())
    assert coordinator.system_status == "Fout"

    coord_mod.dt_util.now = lambda: T0 + timedelta(minutes=5)

    async def fine_update():
        pass

    coordinator._async_update_locked = fine_update
    asyncio.run(coordinator.async_update())

    assert coordinator.system_status == "OK"


def test_flags_stale_when_no_successful_update_in_a_long_time(make_coordinator, hass):
    coordinator = make_coordinator({})
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: T0
    coordinator.last_successful_update = T0

    coord_mod.dt_util.now = lambda: T0 + timedelta(hours=2)

    assert coordinator.system_status == "Mogelijk vastgelopen"


def test_aandacht_gewenst_when_diagnostic_summary_has_items(make_coordinator, hass):
    """v0.63.109, gevraagd: "systeem status ok niet klopt eigenlijk kan
    zien" - system_status moet niet blind 'OK' tonen als
    get_diagnostic_summary() wél degelijk aandachtspunten heeft (bijv.
    veel onbevestigde NILM-kandidaten), ook al draait de integratie
    zelf technisch prima."""
    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
        }
    )
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: T0
    asyncio.run(coordinator.async_update())
    assert coordinator.system_status == "OK"

    coordinator.nilm_unconfirmed_candidates = {
        f"sensor.device_{i}": {"friendly_name": f"Device {i}"} for i in range(20)
    }

    assert coordinator.system_status == "Aandacht gewenst"


def test_an_old_recovered_error_alone_does_not_trigger_aandacht_gewenst(
    make_coordinator, hass
):
    """A stale 'last_error' field (kept only as a historical record,
    already covered more precisely by the 'Fout'/'Mogelijk
    vastgelopen' checks) must not, on its own, cause 'Aandacht
    gewenst' once the integration has genuinely recovered - avoids
    double-flagging the same underlying issue two different ways."""
    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
        }
    )
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: T0
    coordinator.last_error = "Iets ging ooit fout"
    coordinator.last_error_time = T0 - timedelta(hours=2)
    asyncio.run(coordinator.async_update())

    assert coordinator.system_status == "OK"


def test_diagnostic_summary_status_takes_priority_over_fout(make_coordinator, hass):
    """An active/recent error must still report 'Fout', not be
    downgraded to 'Aandacht gewenst' just because that status also
    happens to apply."""
    coordinator = make_coordinator({})
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: T0

    async def broken_update():
        raise ValueError("boom")

    coordinator._async_update_locked = broken_update
    asyncio.run(coordinator.async_update())

    assert coordinator.system_status == "Fout"
