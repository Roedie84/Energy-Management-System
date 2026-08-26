"""Financiële splitsing had dezelfde trage-sensorfout (v1.1.4).

Gevraagd na de vorige fix: "zitten er elders meer van dit soort zaken?"

Ja. Een audit op alle plekken die een TEMPO afleiden uit het verschil van
een niveaumeting leverde één extra treffer op: de kostprijs- en
besparingsboekhouding.

Die berekende het ontlaadtempo over de tick (vijf minuten) in plaats van
over de werkelijke beweging van de sensor. Stond de sensor vier ticks
stil en sprong hij daarna, dan was de opgebouwde energie over ~25 minuten
ontstaan terwijl er met vijf werd gerekend - een tempo dat tot vijf keer
te hoog uitkwam.

Dat tempo bepaalt hoeveel van een ontlading als EXPORT wordt geboekt (het
deel boven het huisverbruik). Te hoog tempo betekent dus: veel meer
"export" op papier dan er werkelijk het net op ging, en daarmee een
verkeerd geboekte terugleverpremie - en na saldering een verkeerde
waardering van die kWh.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_PV_POWER_SENSOR,
)

DAY0 = datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc)
PRIJZEN = [(DAY0 - timedelta(hours=1), DAY0 + timedelta(hours=2), 0.30)]


def _config():
    return {
        CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
        CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1",
        CONF_PV_POWER_SENSOR: "sensor.pv",
    }


def _coordinator(make_coordinator, hass):
    c = make_coordinator(_config())
    c.battery_cost_basis_eur_per_kwh = 0.10
    hass.states.set("sensor.pv", "0")
    hass.states.set("sensor.p1", "500")  # 500 W huisverbruik
    return c


def test_a_stale_tick_books_nothing(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.beschikbaar", "8.0")
    c._update_battery_cost_basis_and_savings(DAY0, PRIJZEN)

    voor = c.discharge_export_kwh_total
    c._update_battery_cost_basis_and_savings(DAY0 + timedelta(minutes=5), PRIJZEN)

    assert c.discharge_export_kwh_total == voor


def test_the_interval_runs_since_the_last_movement(make_coordinator, hass):
    """De kern: na vier stille ticks hoort de sprong over ~25 minuten te
    worden gerekend, niet over vijf.

    Bij 500 W huisverbruik en een werkelijk ontlaadtempo van 500 W is er
    NIETS geexporteerd. Rekent de code met vijf minuten, dan lijkt het
    tempo ~2500 W en wordt er ruim 2000 W als export geboekt.
    """
    c = _coordinator(make_coordinator, hass)
    now = DAY0
    hass.states.set("sensor.beschikbaar", "8.0")
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)

    for _ in range(4):
        now += timedelta(minutes=5)
        c._update_battery_cost_basis_and_savings(now, PRIJZEN)

    # 500 W gedurende 25 minuten = 0,2083 kWh.
    now += timedelta(minutes=5)
    hass.states.set("sensor.beschikbaar", f"{8.0 - 0.2083:.4f}")
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)

    assert c.discharge_export_kwh_total < 0.01


def test_genuine_export_is_still_booked(make_coordinator, hass):
    """De splitsing verliest zijn functie niet: ontlaadt de accu echt
    harder dan het huis verbruikt, dan hoort dat wel als export te
    tellen."""
    c = _coordinator(make_coordinator, hass)
    now = DAY0
    hass.states.set("sensor.beschikbaar", "8.0")
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)

    # 2000 W gedurende 5 minuten = 0,1667 kWh, bij 500 W huisverbruik.
    now += timedelta(minutes=5)
    hass.states.set("sensor.beschikbaar", f"{8.0 - 0.1667:.4f}")
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)

    assert c.discharge_export_kwh_total > 0.1


def test_the_time_anchor_is_kept_while_the_sensor_is_still(
    make_coordinator, hass
):
    """Zou het tijdijkpunt bij elke tick meeschuiven, dan was de fix
    zinloos - dan werd de sprong alsnog over vijf minuten gerekend."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.beschikbaar", "8.0")
    c._update_battery_cost_basis_and_savings(DAY0, PRIJZEN)
    ijkpunt = c._last_cost_basis_calc_time

    c._update_battery_cost_basis_and_savings(DAY0 + timedelta(minutes=5), PRIJZEN)

    assert c._last_cost_basis_calc_time == ijkpunt
