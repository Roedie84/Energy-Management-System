"""Dynamic "expensive quarter" price threshold (v0.27.0+).

A quarter is "expensive" if its price falls within the top fraction of
the day's own price range - no fixed count of quarters, self-adjusting
to however many quarters actually clear the bar each day.
"""
from datetime import datetime, timezone

from conftest import make_price_forecast

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_dynamic_threshold_uses_top_fraction_of_range(make_coordinator, hass):
    """Only quarters within the top 20% of today's price range should
    count as 'expensive' - not a fixed count."""

    def price_fn(hour, minute):
        if hour == 19:
            return 4_500_000  # 0.45 EUR/kWh - the day's peak
        if hour == 20:
            return 3_800_000  # 0.38 EUR/kWh - below the dynamic threshold
        if 9 <= hour < 12:
            return 1_500_000  # 0.15 EUR/kWh - today's cheapest
        return 2_500_000  # 0.25 EUR/kWh - a normal quarter

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})

    coordinator = make_coordinator(
        {"price_sensor_entity": "sensor.price", "price_attribute": "price_tax_included"}
    )
    entries = coordinator._get_forecast_entries()

    now_1915 = DAY0.replace(hour=19, minute=15)
    now_2015 = DAY0.replace(hour=20, minute=15)
    now_1300 = DAY0.replace(hour=13, minute=0)

    # threshold = max - 0.20 * (max - min) = 0.45 - 0.20*0.30 = 0.39
    assert coordinator._is_expensive_now(entries, now_1915) is True
    assert coordinator._is_expensive_now(entries, now_2015) is False  # 0.38 < 0.39
    assert coordinator._is_expensive_now(entries, now_1300) is False  # normal price


def test_effective_expensive_quarter_count_reflects_the_bar(make_coordinator, hass):
    """The informational count sensor should match how many quarters
    actually clear the dynamic threshold, not a hardcoded number."""

    def price_fn(hour, minute):
        if hour == 19:
            return 4_500_000
        if 9 <= hour < 12:
            return 1_500_000
        return 2_500_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})

    coordinator = make_coordinator(
        {"price_sensor_entity": "sensor.price", "price_attribute": "price_tax_included"}
    )
    entries = coordinator._get_forecast_entries()
    now = DAY0.replace(hour=19, minute=15)

    # Only hour 19 (4 quarters) clears the threshold in this price shape.
    assert coordinator._count_expensive_quarters_today(entries, now) == 4


# --- v1.54.0: één uitschieter mag de meetlat niet optillen -----------


def _eclipsdag(make_coordinator, hass):
    """De prijzen van 12 augustus 2026, de dag van de zonsverduistering.

    Gemeld: "De integratie geeft nu maar 2 dure kwartieren door de piek,
    maar waarschijnlijk kan er toch meer ontladen worden."
    """

    def price_fn(hour, minute):
        if hour == 19 and minute == 45:
            return 6_889_000  # 68,9 ct - de piek
        if hour == 20 and minute == 0:
            return 6_180_000  # 61,8 ct
        if hour == 20 and minute == 15:
            return 5_080_000  # 50,8 ct
        if hour == 19 and minute == 30:
            return 4_790_000  # 47,9 ct
        if hour in (21,):
            return 4_370_000  # 43,7 ct
        if 10 <= hour < 16:
            return 1_212_000  # 12,1 ct - het goedkope blok
        return 3_069_000  # 30,7 ct - de mediaan

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    c = make_coordinator(
        {"price_sensor_entity": "sensor.price", "price_attribute": "price_tax_included"}
    )
    return c, c._get_forecast_entries()


def test_an_outlier_no_longer_lifts_the_bar(make_coordinator, hass):
    """De oude drempel was 68,9 - 20% x (68,9 - 12,1) = 57,5 ct. Alleen
    de twee piekkwartieren zelf haalden dat; 50,8 en 47,9 ct vielen af,
    terwijl dat anderhalf keer de mediaan is.
    """
    c, entries = _eclipsdag(make_coordinator, hass)
    nu = DAY0.replace(hour=19, minute=30)

    # De drempel komt terug in rauwe eenheden, net als de prijzen zelf -
    # valkuil 3 uit de overdracht.
    drempel = c._get_expensive_price_threshold(entries, nu) / PRICE_SCALE_FACTOR

    assert drempel < 0.50
    assert c._is_expensive_now(entries, nu) is True
    assert c._is_expensive_now(entries, DAY0.replace(hour=20, minute=15)) is True


def test_a_normal_day_is_left_alone(make_coordinator, hass):
    """Zonder uitschieter blijft alles zoals het was - op 11 augustus
    (13-38 ct) wees de rangedrempel er terecht 17 aan."""

    def price_fn(hour, minute):
        if 18 <= hour < 22:
            return 3_780_000  # 37,8 ct
        if 10 <= hour < 16:
            return 1_300_000  # 13,0 ct
        return 3_020_000  # 30,2 ct

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    c = make_coordinator(
        {"price_sensor_entity": "sensor.price", "price_attribute": "price_tax_included"}
    )
    entries = c._get_forecast_entries()

    drempel = c._get_expensive_price_threshold(
        entries, DAY0.replace(hour=19)
    ) / PRICE_SCALE_FACTOR
    prijzen = [e[2] / PRICE_SCALE_FACTOR for e in entries]
    hoog, laag = max(prijzen), min(prijzen)

    # Precies de oude formule: piek 37,8 is maar 1,25x de mediaan, dus
    # geen uitschieter en geen ingreep.
    assert abs(drempel - (hoog - 0.20 * (hoog - laag))) < 0.0001


def test_the_bar_never_gets_stricter(make_coordinator, hass):
    """De mediaanmaat mag alleen versoepelen. Zou hij ook kunnen
    verstrengen, dan zou een dag met een diep dal ineens minder
    ontladen - en daar is niets mis mee gegaan."""
    c, entries = _eclipsdag(make_coordinator, hass)
    nu = DAY0.replace(hour=19, minute=45)

    prijzen = [e[2] / PRICE_SCALE_FACTOR for e in entries]
    oude_drempel = max(prijzen) - 0.20 * (max(prijzen) - min(prijzen))

    nieuwe = c._get_expensive_price_threshold(entries, nu) / PRICE_SCALE_FACTOR

    assert nieuwe <= oude_drempel
