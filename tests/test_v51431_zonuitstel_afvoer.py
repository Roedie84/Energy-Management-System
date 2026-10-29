"""v5.143.1 - zonuitstel rekent met wat de accu tijdens het wachten levert.

Gemeld 29-10 06:31: "Ontladen" 06:30-14:00 (`solar_capture_deferred`) bij een
accu van 97%: de ruimte NU was 0,3 kWh en die vulde de middagzon makkelijk.
Maar in `smart_discharging` dekt de accu het huis; hij zakte naar 70% en de
verkoop van 17:00-19:30 (75-80 ct) verdween.
"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 10, 29, 6, 30, tzinfo=TZ)


def _uren(a, b):
    return (b - a).total_seconds() / 3600


def _zon(a, b, veilig=False):
    """0,1 kWh/u tot 10:00, daarna 0,7 kWh/u (per uur opgeteld)."""
    tot, t = 0.0, a
    while t < b:
        e = min(b, t + timedelta(minutes=15))
        tot += (0.1 if t.hour < 10 else 0.7) * _uren(t, e)
        t = e
    return tot


def _c(make_coordinator, hass):
    c = make_coordinator({})
    c.beschikbare_energie_kwh = lambda: 8.475 * 0.97 - 0.0   # bijna vol
    c.effective_min_soc_percent = lambda: 15.0               # bruikbaar 8,475
    c.nu_laden_actief = lambda now: False
    c.config = dict(c.config or {})
    c.config["manual_charge_power"] = -2000
    c.config["battery_total_capacity_sensor_entity"] = "sensor.cap"
    hass.states.set("sensor.cap", "9.97")
    c._estimate_pv_kwh_for_period = _zon
    c._estimate_consumption_kwh_for_period = lambda a, b: 0.5 * _uren(a, b)
    c.huidige_prijs_eur_per_kwh = lambda: 0.531
    c._price_at_hour = lambda now, uur: 0.437
    return c


def test_ruimte_bij_telt_de_afvoer_tot_het_omslaguur(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    # 06:30-10:00: 3,5 u x (0,5 - 0,1) = 1,4 kWh; 10:00-12:00 zon > verbruik: 0.
    r = c._zonuitstel_ruimte_bij(NU, NU.replace(hour=12, minute=0), 0.25, 8.475)
    assert abs(r - (0.25 + 1.4)) < 0.01


def test_begrensd_op_de_bruikbare_capaciteit(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    assert c._zonuitstel_ruimte_bij(NU, NU.replace(hour=14, minute=0), 8.0, 8.475) == 8.475


def test_casus_29_10_stelt_niet_meer_uit(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    assert c.plan_solar_capture_moment(NU)["uitstellen"] is False


def test_zonder_afvoer_was_het_wel_uitgesteld(make_coordinator, hass):
    """Het oude gedrag (ruimte van nu) stelde in dezelfde situatie uit."""
    c = _c(make_coordinator, hass)
    c._zonuitstel_ruimte_bij = lambda now, start, ruimte, bruikbaar: ruimte
    assert c.plan_solar_capture_moment(NU)["uitstellen"] is True


def test_veel_zon_stelt_nog_steeds_uit(make_coordinator, hass):
    """Zomerdag: zon boven verbruik vanaf de ochtend, dan geen afvoer."""
    c = _c(make_coordinator, hass)
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: 2.0 * _uren(a, b)
    assert c.plan_solar_capture_moment(NU)["uitstellen"] is True
