"""Shared pytest fixtures and a lightweight `homeassistant` mock package.

Home Assistant itself isn't installed in this test environment (and isn't
a dependency of a HACS custom component), so this builds just enough of
the `homeassistant.*` module surface for
`custom_components.energy_management_system` to import and run normally
via its real (relative) imports - no source-rewriting hacks needed.

This must run before any `custom_components.energy_management_system`
import, so it's installed as a pytest plugin via conftest.py, which
pytest always imports first.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

# -- Make the repo root importable as a package -----------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_ha_mocks() -> None:
    if "homeassistant" in sys.modules:
        return  # already installed (e.g. re-running under the same process)

    homeassistant = types.ModuleType("homeassistant")

    # -- homeassistant.core --------------------------------------------
    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:  # noqa: D401 - minimal stand-in
        pass

    class Event:
        def __init__(self, event_type: str = "", data: dict | None = None):
            self.event_type = event_type
            self.data = data or {}

    class CoreState:
        not_running = "NOT_RUNNING"
        starting = "STARTING"
        running = "RUNNING"
        stopping = "STOPPING"
        final_write = "FINAL_WRITE"
        stopped = "STOPPED"

    def callback(func):
        """No-op decorator stand-in for @callback."""
        return func

    core.HomeAssistant = HomeAssistant
    core.Event = Event
    core.CoreState = CoreState
    core.callback = callback
    sys.modules["homeassistant.core"] = core

    # -- homeassistant.const ---------------------------------------------
    const = types.ModuleType("homeassistant.const")
    const.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
    sys.modules["homeassistant.const"] = const

    # -- homeassistant.config_entries -------------------------------------
    config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigEntry:
        def __init__(self, data=None, options=None, entry_id="test_entry"):
            self.data = data or {}
            self.options = options or {}
            self.entry_id = entry_id

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            pass

    class OptionsFlow:
        pass

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    sys.modules["homeassistant.config_entries"] = config_entries
    homeassistant.config_entries = config_entries

    # -- homeassistant.helpers (namespace package) ------------------------
    helpers = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers

    helpers_event = types.ModuleType("homeassistant.helpers.event")
    helpers_event.async_track_state_change_event = lambda *a, **k: (lambda: None)
    helpers_event.async_track_time_interval = lambda *a, **k: (lambda: None)
    helpers_event.async_track_time_change = lambda *a, **k: (lambda: None)
    sys.modules["homeassistant.helpers.event"] = helpers_event

    helpers_entity = types.ModuleType("homeassistant.helpers.entity")

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"
        CONFIG = "config"

    helpers_entity.EntityCategory = EntityCategory
    sys.modules["homeassistant.helpers.entity"] = helpers_entity

    helpers_entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

    class AddEntitiesCallback:
        pass

    helpers_entity_platform.AddEntitiesCallback = AddEntitiesCallback
    sys.modules["homeassistant.helpers.entity_platform"] = helpers_entity_platform

    helpers_restore = types.ModuleType("homeassistant.helpers.restore_state")

    class RestoreEntity:
        async def async_get_last_state(self):
            return None

        async def async_added_to_hass(self):
            pass

    helpers_restore.RestoreEntity = RestoreEntity
    sys.modules["homeassistant.helpers.restore_state"] = helpers_restore

    helpers_selector = types.ModuleType("homeassistant.helpers.selector")

    class _SelectorConfigStub:
        def __init__(self, *a, **k):
            self.args = a
            self.kwargs = k

    class _SelectorStub:
        def __init__(self, *a, **k):
            self.args = a
            self.kwargs = k

    helpers_selector.EntitySelector = _SelectorStub
    helpers_selector.EntitySelectorConfig = _SelectorConfigStub
    helpers_selector.NumberSelector = _SelectorStub
    helpers_selector.NumberSelectorConfig = _SelectorConfigStub

    class NumberSelectorMode:
        BOX = "box"
        SLIDER = "slider"

    helpers_selector.NumberSelectorMode = NumberSelectorMode
    sys.modules["homeassistant.helpers.selector"] = helpers_selector

    # -- homeassistant.components (namespace) + sensor/switch -------------
    components = types.ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = components

    components_sensor = types.ModuleType("homeassistant.components.sensor")

    class SensorEntity:
        pass

    class SensorDeviceClass:
        TIMESTAMP = "timestamp"
        MONETARY = "monetary"
        ENERGY = "energy"
        POWER = "power"

    components_sensor.SensorEntity = SensorEntity
    components_sensor.SensorDeviceClass = SensorDeviceClass
    sys.modules["homeassistant.components.sensor"] = components_sensor

    components_switch = types.ModuleType("homeassistant.components.switch")

    class SwitchEntity:
        pass

    components_switch.SwitchEntity = SwitchEntity
    sys.modules["homeassistant.components.switch"] = components_switch

    # -- homeassistant.util.dt --------------------------------------------
    util = types.ModuleType("homeassistant.util")
    sys.modules["homeassistant.util"] = util

    util_dt = types.ModuleType("homeassistant.util.dt")
    util_dt.UTC = timezone.utc

    def parse_datetime(value):
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def as_local(value):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    util_dt.parse_datetime = parse_datetime
    util_dt.as_local = as_local
    util_dt.now = lambda: datetime.now(tz=timezone.utc)
    sys.modules["homeassistant.util.dt"] = util_dt

    sys.modules["homeassistant"] = homeassistant


_install_ha_mocks()


# -- Shared fixtures -------------------------------------------------------


class FakeState:
    """Stand-in for a Home Assistant entity state."""

    def __init__(self, state, attributes: dict | None = None):
        self.state = state
        self.attributes = attributes or {}


class FakeStates:
    """Stand-in for hass.states."""

    def __init__(self):
        self._values: dict[str, FakeState] = {}

    def set(self, entity_id: str, state, attributes: dict | None = None) -> None:
        self._values[entity_id] = FakeState(state, attributes)

    def get(self, entity_id: str):
        return self._values.get(entity_id)

    def async_all(self):
        """Stand-in for hass.states.async_all() - used by diagnostics.py's
        system_scan. Real Home Assistant states carry an entity_id
        attribute; attach one here so callers can rely on it."""
        results = []
        for entity_id, state in self._values.items():
            state.entity_id = entity_id
            results.append(state)
        return results


class FakeServices:
    """Stand-in for hass.services - records every call made."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    async def async_call(self, domain, service, data, blocking=True):
        self.calls.append((domain, service, data))


class FakeBus:
    """Stand-in for hass.bus - only what's needed for the startup-timing
    test (async_listen_once)."""

    def __init__(self):
        self.listeners: list[tuple[str, object]] = []

    def async_listen_once(self, event_type, callback_fn):
        self.listeners.append((event_type, callback_fn))


class FakeHass:
    """Minimal stand-in for Home Assistant's core hass object."""

    def __init__(self, core_state: str = "RUNNING"):
        self.states = FakeStates()
        self.services = FakeServices()
        self.bus = FakeBus()
        self.state = core_state
        self.created_tasks: list = []

    def async_create_task(self, coro):
        # Actually schedule it (best-effort) so nothing is left as an
        # un-awaited coroutine; tests that need to assert on the result
        # can still inspect self.services.calls afterwards since the
        # scheduled task typically completes before the test finishes.
        import asyncio

        self.created_tasks.append(coro)
        try:
            return asyncio.ensure_future(coro)
        except RuntimeError:
            # No running loop (e.g. called from sync test code) - leave
            # it for the fixture's teardown to close.
            return coro


@pytest.fixture
def hass():
    instance = FakeHass()
    yield instance
    # Close any fire-and-forget coroutines created during the test (e.g.
    # the solar ramp task) that nothing awaited, to avoid
    # "coroutine was never awaited" warnings leaking between tests.
    for task in instance.created_tasks:
        if hasattr(task, "close") and not hasattr(task, "cancel"):
            task.close()


@pytest.fixture
def coordinator_cls():
    """Import lazily (after HA mocks are installed) and return the class."""
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator,
    )

    return EnergyManagementSystemCoordinator


@pytest.fixture
def make_coordinator(hass, coordinator_cls):
    """Factory fixture: make_coordinator(config) -> coordinator instance."""

    def _make(config: dict | None = None):
        return coordinator_cls(hass, config or {})

    return _make


def make_price_forecast(day0: datetime, price_fn) -> list[dict]:
    """Build a `forecast` attribute list of 15-minute price entries for one
    day, using price_fn(hour, minute) -> price in the integration's raw
    integer scale (e.g. 2500000 for 0.25 EUR/kWh).
    """
    from datetime import timedelta

    entries = []
    for hour in range(24):
        for minute in (0, 15, 30, 45):
            start = day0.replace(hour=hour, minute=minute, second=0, microsecond=0)
            end = start + timedelta(minutes=15)
            entries.append(
                {
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "price_tax_included": {"amount": price_fn(hour, minute)},
                }
            )
    return entries
