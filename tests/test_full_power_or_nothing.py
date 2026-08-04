"""'1600W of niets' (v0.63.18): zodra _is_worth_discharging_now een
kwartier als betaalbaar op vol vermogen aanmerkt, moet het toegepaste
vermogen ook echt het volle base_power zijn - niet nog eens doorlopend
afgeknepen door de per-tick headroom/interval-formule (die er in de
praktijk voor zorgde dat een "betaalbaar" kwartier soms toch maar een
trickle van bijv. 150W kreeg in plaats van de volle 1600W).
"""
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "available_energy_sensor_entity": "sensor.available_energy",
        "manual_discharge_power": 1600.0,
    }
    config.update(overrides)
    return config


def test_full_base_power_applied_once_deemed_affordable(make_coordinator, hass, monkeypatch):
    """Reproduces the reported scenario: the per-tick headroom formula
    alone would only allow ~150W (headroom_kwh very small relative to a
    single 5-min tick), but _is_worth_discharging_now says this quarter
    IS among the affordable top-priced ones at full base_power - the
    applied power must be the full 1600W, not the ~150W throttle."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "5.75")

    # Tiny headroom under the old per-tick formula (matches the
    # previously-reported ~12.5 Wh scenario), but _is_worth_discharging_now
    # is monkeypatched to confirm affordability regardless - isolating
    # exactly the mechanism under test.
    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 5.7375
    )
    monkeypatch.setattr(
        coordinator, "_is_worth_discharging_now", lambda *a, **k: True
    )

    now = DAY0.replace(hour=20, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(
        1600.0, now, None, entries=[]
    )

    assert scaled == 1600.0


def test_still_capped_by_what_is_physically_available(make_coordinator, hass, monkeypatch):
    """Full base_power is only granted up to what the battery physically
    holds this tick - can't discharge more than what's actually there."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "0.05")  # 0.05 kWh left

    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 0.0
    )
    monkeypatch.setattr(
        coordinator, "_is_worth_discharging_now", lambda *a, **k: True
    )

    now = DAY0.replace(hour=20, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(
        1600.0, now, None, entries=[]
    )

    # 0.05 kWh over a 5-minute tick = 600W physical ceiling
    assert scaled == 600.0


def test_still_returns_none_when_not_worth_it(make_coordinator, hass, monkeypatch):
    """The 'not affordable' side is unchanged: still holds off entirely
    (no trickle, no floor override) when _is_worth_discharging_now says
    this isn't among the quarters headroom can afford."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "5.75")

    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 5.7375
    )
    monkeypatch.setattr(
        coordinator, "_is_worth_discharging_now", lambda *a, **k: False
    )

    now = DAY0.replace(hour=20, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(
        1600.0, now, None, entries=[]
    )

    assert scaled is None
    assert coordinator.last_price_priority_held_off is True


def test_household_floor_still_applies_as_a_minimum(make_coordinator, hass, monkeypatch):
    """The household-consumption floor (v0.59.0) still works as a
    minimum underneath the new full-power behaviour. The floor itself
    was always capped at base_power (by design, since v0.59.0) - so
    with live load above base_power, the result is still base_power,
    not the (higher) live load."""
    coordinator = make_coordinator(
        _base_config(consumption_power_sensor_entity="sensor.p1")
    )
    hass.states.set("sensor.available_energy", "5.75")
    hass.states.set("sensor.p1", "1800")

    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 5.7375
    )
    monkeypatch.setattr(
        coordinator, "_is_worth_discharging_now", lambda *a, **k: True
    )

    now = DAY0.replace(hour=20, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(
        1600.0, now, None, entries=[]
    )

    assert scaled == 1600.0


def test_household_floor_covered_when_below_base_power(make_coordinator, hass, monkeypatch):
    """Genuine floor coverage: live load below base_power still comes
    through as the minimum, not silently dropped by the full-power path."""
    coordinator = make_coordinator(
        _base_config(consumption_power_sensor_entity="sensor.p1")
    )
    hass.states.set("sensor.available_energy", "0.6")
    hass.states.set("sensor.p1", "340")

    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 0.5
    )
    monkeypatch.setattr(
        coordinator, "_is_worth_discharging_now", lambda *a, **k: True
    )

    now = DAY0.replace(hour=20, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(
        1600.0, now, None, entries=[]
    )

    # Nonzero headroom (0.1 kWh) routes through the "worth it" full-power
    # path; physical ceiling (0.6 kWh / 5 min = 7200W) is well above both
    # 1600W base_power and the 340W floor - base_power wins here.
    assert scaled == 1600.0
