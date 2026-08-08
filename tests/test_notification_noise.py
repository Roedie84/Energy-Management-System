"""Meldingsruis rond drempels (v1.9.3).

Uit de meldingsgeschiedenis van één etmaal:

- Om 00:02 "Kostenberekening wijkt af van Zonneplan" (1,53 € verschil),
  om 00:04 alweer "klopt weer".
- "Accu haalt de nacht niet" ging zeven keer af met tekorten van 0,01 tot
  0,21 kWh, telkens gevolgd door "haalt de nacht weer".

Beide zijn geen storingen maar geruis rond een grens. Een melding die
zichzelf binnen twee minuten intrekt, leert je meldingen te negeren - en
dan mis je de keer dat het wél echt misgaat.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    BATTERY_NIGHT_SHORTFALL_MIN_KWH,
    CONF_APPLIANCE_NOTIFY_SERVICE,
    CONF_PRICE_SENSOR,
    RELIABILITY_INSUFFICIENT,
    ZONNEPLAN_ROLLOVER_GRACE_MINUTES,
)

PRIJS = "sensor.zonneplan_current_quarter_hourly_electricity_tariff"
AFNAME = "sensor.zonneplan_electricity_delivery_costs_today"


def _klok(c, moment):
    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: moment
    return mod


# --- 1. dagwissel bij de kostenvergelijking --------------------------


def test_no_comparison_just_after_midnight(make_coordinator, hass):
    """Onze dagteller springt om 00:00 naar nul, die van Zonneplan een
    paar minuten later. Zolang ze niet gelijk staan zegt een
    vergelijking niets."""
    from custom_components.energy_management_system import coordinator as mod

    c = make_coordinator({CONF_PRICE_SENSOR: PRIJS})
    hass.states.set(AFNAME, "1.53")
    c.actual_cost_today_eur = 0.0

    origineel = mod.dt_util.now
    try:
        _klok(c, datetime(2026, 8, 8, 0, 2, tzinfo=timezone.utc))
        vergelijking = c.get_zonneplan_cost_comparison()
    finally:
        mod.dt_util.now = origineel

    assert vergelijking["status"] == RELIABILITY_INSUFFICIENT
    assert "middernacht" in vergelijking["reden"]


def test_the_comparison_resumes_after_the_grace(make_coordinator, hass):
    from custom_components.energy_management_system import coordinator as mod

    c = make_coordinator({CONF_PRICE_SENSOR: PRIJS})
    hass.states.set(AFNAME, "1.00")
    c.actual_cost_today_eur = 1.00

    origineel = mod.dt_util.now
    try:
        _klok(
            c,
            datetime(
                2026, 8, 8, 0, ZONNEPLAN_ROLLOVER_GRACE_MINUTES + 5,
                tzinfo=timezone.utc,
            ),
        )
        vergelijking = c.get_zonneplan_cost_comparison()
    finally:
        mod.dt_util.now = origineel

    assert vergelijking["status"] != RELIABILITY_INSUFFICIENT


# --- 2. nachtreserve -------------------------------------------------


def _nacht(make_coordinator, hass, beschikbaar, nodig):
    c = make_coordinator({CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon"})
    c._get_forecast_entries = lambda: []
    c.set_notification_enabled("battery_wont_last_night", True)
    c.last_available_kwh = beschikbaar
    c.last_needed_kwh_to_bridge = nodig
    c._evaluate_new_notifications(datetime(2026, 8, 7, 22, 0, tzinfo=timezone.utc))
    return [m["titel"] for m in c.notification_history]


def test_a_hairline_shortfall_is_not_reported(make_coordinator, hass):
    """4,49 tegen 4,50 kWh - een tekort van 0,01 kWh, oftewel 0,2%. De
    schatting zelf is onnauwkeuriger dan dat."""
    titels = _nacht(make_coordinator, hass, 4.49, 4.50)

    assert not any("haalt de nacht" in t for t in titels)


def test_a_real_shortfall_is_still_reported(make_coordinator, hass):
    """De demping mag een echt tekort niet verbergen."""
    titels = _nacht(make_coordinator, hass, 3.0, 6.0)

    assert any("haalt de nacht" in t for t in titels)


def test_the_threshold_scales_with_the_need(make_coordinator, hass):
    """Een half kWh tekort is veel bij een behoefte van 2 kWh en weinig
    bij 20 kWh."""
    klein = _nacht(make_coordinator, hass, 1.4, 2.0)
    groot = _nacht(make_coordinator, hass, 19.4, 20.0)

    assert any("haalt de nacht" in t for t in klein)
    assert not any("haalt de nacht" in t for t in groot)


def test_the_absolute_floor_applies(make_coordinator, hass):
    """Onder de absolute ondergrens nooit melden, hoe klein de behoefte
    ook is."""
    tekort = BATTERY_NIGHT_SHORTFALL_MIN_KWH / 2
    titels = _nacht(make_coordinator, hass, 1.0 - tekort, 1.0)

    assert not any("haalt de nacht" in t for t in titels)
