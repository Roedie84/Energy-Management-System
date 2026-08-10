"""Zonopvang uitstellen naar een goedkoper uur (v1.22.0).

Gevraagd na een dag waarop de accu 's ochtends vol liep bij hoge prijzen,
en het overschot 's middags tegen 13,6 ct werd teruggeleverd:

    "Ik had dus beter mijn inziens tot 11:30 smart_discharge kunnen
    doen? Dan had in de uren daarvoor mij meer geld opgeleverd."

Het mechanisme: de accu neemt een vast aantal kilowattuur op; WELKE dat
zijn bepaalt welke je exporteert. Laadt hij vroeg, dan slurpt hij de dure
ochtendzon op (26,8 ct) en exporteer je de goedkope middagzon (13,6 ct).
Laadt hij laat, dan andersom - zelfde eind-SoC, zelfde totale export,
andere prijzen.

Gesimuleerd op de werkelijke dag van 10 augustus:

    nu (altijd smart) : 1,657 EUR
    omslag 11:00      : 1,884 EUR   (+0,23)
    omslag 13:00      : 2,152 EUR   (+0,49)
    omslag 15:00      : 2,053 EUR   (+0,40, maar accu niet meer vol)

Die laatste regel is de reden voor de marge: het optimum ligt vlak vóór
de rand waarop de accu niet meer vol raakt.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_MIN_SOC_PERCENT,
    SOLAR_DEFER_LATEST_HOUR,
    SOLAR_DEFER_MIN_PRICE_GAIN_EUR,
    SOLAR_DEFER_MIN_SOC_PERCENT,
    SOLAR_DEFER_SAFETY_FACTOR,
    SOLAR_DEFER_TARGET_FULL_HOUR,
)

OCHTEND = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)


def _coordinator(
    make_coordinator,
    hass,
    beschikbaar=2.85,
    zon_per_uur=2.2,
    verbruik_per_uur=0.3,
    prijs_nu=0.2676,
    prijs_later=0.1456,
):
    c = make_coordinator(
        {
            CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.cap",
            CONF_MIN_SOC_PERCENT: 15.0,
        }
    )
    hass.states.set("sensor.cap", "8.6")
    c.last_available_kwh = beschikbaar
    c.last_current_price_per_kwh = prijs_nu

    uren = lambda a, b: max(0.0, (b - a).total_seconds() / 3600)
    c._estimate_pv_kwh_for_period = lambda a, b: uren(a, b) * zon_per_uur
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: uren(a, b) * verbruik_per_uur
    )
    c._price_at_hour = lambda now, uur: prijs_later
    return c


# --- het gerapporteerde geval ----------------------------------------


def test_a_sunny_morning_defers(make_coordinator, hass):
    """4,46 kWh ruimte, ruim zes uur zon tot 16:00 en 12 ct
    prijsverschil - dan is wachten de juiste keuze."""
    c = _coordinator(make_coordinator, hass)

    plan = c.plan_solar_capture_moment(OCHTEND)

    assert plan["uitstellen"] is True
    assert plan["omslag_uur"] > OCHTEND.hour
    assert plan["geschatte_winst_eur"] > 0


def test_the_plan_explains_itself(make_coordinator, hass):
    """Een stille moduswissel is niet te beoordelen; de reden hoort de
    prijzen te noemen."""
    plan = _coordinator(make_coordinator, hass).plan_solar_capture_moment(
        OCHTEND
    )

    assert "ct" in plan["reden"]
    assert str(SOLAR_DEFER_TARGET_FULL_HOUR) in plan["reden"]


# --- de rem: wanneer NIET uitstellen ---------------------------------


def test_too_little_sun_does_not_defer(make_coordinator, hass):
    """Het optimum ligt vlak vóór de rand waarop de accu niet meer vol
    raakt; te weinig zon betekent niet wachten."""
    c = _coordinator(make_coordinator, hass, zon_per_uur=0.4)

    plan = c.plan_solar_capture_moment(OCHTEND)

    assert plan["uitstellen"] is False
    assert "Te weinig zon" in plan["reden"]


def test_a_small_price_gain_does_not_defer(make_coordinator, hass):
    """Onder de drempel weegt het risico van een tegenvallende middag
    zwaarder dan de winst."""
    c = _coordinator(make_coordinator, hass, prijs_later=0.2600)

    plan = c.plan_solar_capture_moment(OCHTEND)

    assert plan["uitstellen"] is False
    assert "te klein" in plan["reden"]


def test_an_almost_empty_battery_does_not_defer(make_coordinator, hass):
    """Vullen gaat dan voor optimaliseren."""
    c = _coordinator(make_coordinator, hass, beschikbaar=1.0)

    plan = c.plan_solar_capture_moment(OCHTEND)

    assert plan["uitstellen"] is False
    assert "vullen gaat nu voor" in plan["reden"].lower()


def test_a_full_battery_has_nothing_to_plan(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, beschikbaar=7.3)

    plan = c.plan_solar_capture_moment(OCHTEND)

    assert plan["uitstellen"] is False
    assert "al vol" in plan["reden"]


def test_late_in_the_day_it_stops(make_coordinator, hass):
    """Na de deadline hoort de accu vol te zijn; wachten heeft dan geen
    zin meer."""
    c = _coordinator(make_coordinator, hass)
    laat = OCHTEND.replace(hour=SOLAR_DEFER_TARGET_FULL_HOUR + 1)

    plan = c.plan_solar_capture_moment(laat)

    assert plan["uitstellen"] is False


def test_missing_data_does_not_defer(make_coordinator, hass):
    """Zonder capaciteit of beschikbare energie valt er niets te
    plannen - dan het beproefde gedrag houden."""
    c = make_coordinator({})

    plan = c.plan_solar_capture_moment(OCHTEND)

    assert plan["uitstellen"] is False
    assert "onbekend" in plan["reden"]


# --- de marge --------------------------------------------------------


def test_the_deadline_makes_late_sun_a_safety_net():
    """Gevraagd: "een soort kans zodat we zeker weten dat de accu rond
    16:00 zo goed als vol is".

    Door tot 16:00 te rekenen wordt de late middagzon het vangnet in
    plaats van onderdeel van het plan.
    """
    assert SOLAR_DEFER_TARGET_FULL_HOUR == 16
    assert SOLAR_DEFER_LATEST_HOUR <= SOLAR_DEFER_TARGET_FULL_HOUR


def test_the_margin_covers_the_forecast_error():
    """De PV-voorspelling zit gemiddeld 15% naast; 25% marge dekt dat
    ruim zonder de kans te verspelen."""
    assert SOLAR_DEFER_SAFETY_FACTOR >= 1.2
    assert SOLAR_DEFER_MIN_PRICE_GAIN_EUR >= 0.03
    assert SOLAR_DEFER_MIN_SOC_PERCENT >= 20


def test_the_reason_has_a_dutch_label():
    """Elke beslisreden hoort leesbaar te zijn op het dashboard."""
    from custom_components.energy_management_system.const import (
        DECISION_REASON_LABELS,
    )

    assert "solar_capture_deferred" in DECISION_REASON_LABELS


def test_it_is_wired_into_the_decision():
    """Plannen zonder toepassen zou niets opleveren."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "plan_solar_capture_moment(now)" in bron
    assert 'self.last_reason = "solar_capture_deferred"' in bron
