"""Extra-dip laden op weinig-zon-dagen (v0.63.87, uitgebreid besproken en
ontworpen door de gebruiker).

Sinds v0.63.77 laadt het systeem tijdens een weinig-zon-dag alleen nog
gedwongen bij binnen het ene, hoofd-goedkope blok van de dag
(`should_force_charge`) - een aparte, losse prijsdip elders die dag
werd volledig genegeerd, ook al zou bijladen daar aantoonbaar
voordeliger zijn dan wachten. Dit her-introduceert dat idee, maar
sterk begrensd: alleen actief wanneer het al een weinig-zon-dag is
(dezelfde genuine behoefte als het hoofdblok), met een rendement-
gecorrigeerde marge-check (net als het oude, verwijderde arbitrage-
mechanisme) - géén algemene, altijd-actieve comeback.

Belangrijke test-subtiliteit: `_cheapest_block_range()` kijkt alleen
naar *toekomstige* prijzen vanaf "nu" en kiest simpelweg de goedkoopste
resterende stretch. Zodra "nu" voorbij het oorspronkelijke hoofdblok is
verstreken, telt dat blok niet meer mee als "upcoming" - dus als er
géén nóg-goedkopere stretch later die dag bestaat, wordt het huidige
testmoment zélf als (nieuw) hoofdblok herkend (`should_force_charge`
vuurt dan, niet het nieuwe extra-dip-mechanisme). Elke prijsreeks
hieronder bevat daarom bewust een latere, nóg goedkopere stretch dan
het testmoment zelf, zodat `in_cheap_block` op het testmoment correct
`False` blijft en specifiek de nieuwe marge-check wordt beproefd.
"""
import asyncio
from datetime import datetime, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 1, 11, tzinfo=timezone.utc)


def with_now(coordinator, when: datetime) -> None:
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def _price_with_extra_dip(hour, minute):
    """Hoofdblok 03:00-06:00 (€0,08, de dag-absolute goedkoopste - geldt
    zo als hoofdblok bij de vroege warmup-tick), een latere, nóg
    goedkopere stretch om 21:00-22:00 (€0,10) die na 06:00 als (nieuw)
    hoofdblok geldt, een los, apart testmoment om 13:00-14:00 (€0,15,
    dus geen hoofdblok, maar wel een dip t.o.v. de rest) en een duur
    moment om 17:00-19:00 (€0,35)."""
    if 3 <= hour < 6:
        return 800_000
    if 21 <= hour < 22:
        return 1_000_000
    if 13 <= hour < 14:
        return 1_500_000
    if 17 <= hour < 19:
        return 3_500_000
    return 2_000_000


def _price_flat_outside_main_block(hour, minute):
    """Zelfde structuur (hoofdblok + latere-nóg-goedkopere stretch, om
    diezelfde reden), maar het testmoment (13:00-14:00, €0,19) ligt nu
    nauwelijks onder de rest van de dag (€0,20) - onvoldoende marge na
    rendementsverlies, ook al is het wél een lokale dip."""
    if 3 <= hour < 6:
        return 800_000
    if 21 <= hour < 22:
        return 1_000_000
    if 13 <= hour < 14:
        return 1_900_000
    return 2_000_000


def _base_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "manual_discharge_power": 1600,
        "manual_charge_power": -2000,
        "solar_forecast_sensor_entity": "sensor.solcast",
        "consumption_power_sensor_entity": "sensor.p1",
        "low_solar_threshold_kwh": 5.0,
        "battery_round_trip_efficiency_percent": 88,
    }
    config.update(overrides)
    return config


def test_extra_dip_fires_with_sufficient_margin(make_coordinator, hass):
    """A separate, distinct cheap dip outside the main block, with a
    large enough efficiency-corrected margin against today's remaining
    peak price, must trigger extra-dip charging - on a low-solar day."""
    forecast = make_price_forecast(DAY0, _price_with_extra_dip)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "2.0")  # low solar
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())

    async def run():
        with_now(coordinator, DAY0.replace(hour=4, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason == "grid_charging_low_solar"

        with_now(coordinator, DAY0.replace(hour=13, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason == "grid_charging_low_solar_extra_dip"
        assert coordinator._grid_charged_today is True
        assert coordinator.last_extra_dip_margin_eur_per_kwh > 0.03

    asyncio.run(run())


def test_extra_dip_sets_winter_guard_suppressing_later_sale(make_coordinator, hass):
    """Energy bought via the extra-dip charge must not be resold later
    that same day - the winter guard must engage exactly like it does
    for the main block."""
    forecast = make_price_forecast(DAY0, _price_with_extra_dip)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "2.0")
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())

    async def run():
        with_now(coordinator, DAY0.replace(hour=4, minute=0))
        await coordinator._async_update_locked()

        with_now(coordinator, DAY0.replace(hour=13, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason == "grid_charging_low_solar_extra_dip"

        with_now(coordinator, DAY0.replace(hour=18, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason != "expensive_quarter"
        assert coordinator.last_winter_guard_suppressed_today is True

    asyncio.run(run())


def test_extra_dip_does_not_fire_without_sufficient_margin(make_coordinator, hass):
    """A local dip that isn't meaningfully cheaper than the rest of
    the day (outside the main block) must not trigger extra-dip
    charging - the round-trip loss would make it a net loss, not a
    gain."""
    forecast = make_price_forecast(DAY0, _price_flat_outside_main_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "2.0")
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())

    async def run():
        with_now(coordinator, DAY0.replace(hour=4, minute=0))
        await coordinator._async_update_locked()

        with_now(coordinator, DAY0.replace(hour=13, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason != "grid_charging_low_solar_extra_dip"

    asyncio.run(run())


def test_extra_dip_never_fires_on_a_normal_solar_day(make_coordinator, hass):
    """Even with a large price margin available, extra-dip charging
    must never fire on a day with sufficient solar expected - this is
    not a general arbitrage comeback."""
    forecast = make_price_forecast(DAY0, _price_with_extra_dip)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "20.0")  # plenty of solar expected
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())

    async def run():
        with_now(coordinator, DAY0.replace(hour=4, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason != "grid_charging_low_solar"

        with_now(coordinator, DAY0.replace(hour=13, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason != "grid_charging_low_solar_extra_dip"

    asyncio.run(run())


def test_extra_dip_still_fires_even_after_main_block_already_charged(
    make_coordinator, hass
):
    """Corrected design point: the winter-guard flag being already set
    (from the main block, earlier that day) must NOT prevent the
    extra-dip mechanism from firing later - on any low-solar day the
    main block will have essentially always already set that flag, so
    gating the extra-dip check on "not yet charged today" would make
    it unreachable in practice. The flag is meant to suppress SELLING
    later, not additional LEGITIMATE charging."""
    forecast = make_price_forecast(DAY0, _price_with_extra_dip)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "2.0")
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())

    async def run():
        # Main block first.
        with_now(coordinator, DAY0.replace(hour=4, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason == "grid_charging_low_solar"
        assert coordinator._grid_charged_today is True

        # The separate dip later - must still fire, despite the flag
        # already being set.
        with_now(coordinator, DAY0.replace(hour=13, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason == "grid_charging_low_solar_extra_dip"

    asyncio.run(run())


def test_extra_dip_uses_learned_efficiency_when_available(make_coordinator, hass):
    """The margin calculation must prefer the learned battery
    efficiency over the configured fallback, once enough samples
    exist."""
    forecast = make_price_forecast(DAY0, _price_with_extra_dip)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "2.0")
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(
        _base_config(battery_round_trip_efficiency_percent=50)
    )
    coordinator.learned_efficiency_history = [90.0, 91.0, 89.0]

    async def run():
        with_now(coordinator, DAY0.replace(hour=4, minute=0))
        await coordinator._async_update_locked()

        with_now(coordinator, DAY0.replace(hour=13, minute=0))
        await coordinator._async_update_locked()
        # With the configured 50% fallback the margin would have been
        # 0.5*0.35 - 0.15 = 0.025, just BELOW the 0.03 threshold (so it
        # would NOT have fired) - so a clean pass here demonstrates the
        # *learned* (much higher, ~90%) efficiency was actually used:
        # 0.9*0.35 - 0.15 = 0.165, comfortably above threshold.
        assert coordinator.last_reason == "grid_charging_low_solar_extra_dip"
        assert coordinator.last_extra_dip_margin_eur_per_kwh > 0.1

    asyncio.run(run())
