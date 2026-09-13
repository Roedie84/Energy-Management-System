"""Wanneer is een piek een waarschuwing waard? (v2.7.0)

Gemeld: drie keer dezelfde melding op één ochtend, en het "duurste blok"
schoof telkens op:

    05:15 -> "om 08:15 begint 't duurste blok"
    06:15 -> "om 09:15 begint het duurste blok"
    09:15 -> "om 09:30 begint het duurste blok"

Dat is geen vaste gebeurtenis maar een horizon die meebeweegt: het
duurste blok dat er nog RESTEERT.

En op 17 augustus liep de prijs van 29,7 tot 38,9 ct over de hele dag.
Bij zo'n vlak verloop is "het duurste blok" een dun begrip; 37,1 ct zat
nauwelijks boven de mediaan van 34,5.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    PEAK_ALERT_MIN_HOURS_AHEAD,
    PEAK_ALERT_MIN_OF_MEDIAN,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 8, 17, 6, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, piek_ct, basis_ct, uren_vooruit):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon"})
    c.set_notification_enabled("low_soc_before_peak", True)
    c.last_soc_percent = 15.0
    c.accustand_procent = lambda v=15.0: v
    start = NU + timedelta(hours=uren_vooruit)
    c.last_discharge_start = start

    prijzen = []
    for i in range(60):
        moment = NU + timedelta(minutes=15 * i)
        in_piek = start <= moment < start + timedelta(hours=1)
        prijzen.append(
            (moment, None, (piek_ct if in_piek else basis_ct) / 100 * PRICE_SCALE_FACTOR)
        )
    c._get_forecast_entries = lambda *a, **k: prijzen
    return c


def _gemeld(c):
    c._evaluate_new_notifications(NU)
    return any(
        m["soort"] == "low_soc_before_peak" for m in c.notification_history
    )


def test_a_real_peak_with_time_to_act_is_reported(make_coordinator, hass):
    """45 ct tegen een basis van 30, twee uur vooraf - dat is bruikbaar
    advies."""
    c = _coordinator(make_coordinator, hass, piek_ct=45, basis_ct=30, uren_vooruit=2)

    assert _gemeld(c) is True


def test_a_quarter_of_an_hour_beforehand_is_too_late(make_coordinator, hass):
    """Het gemelde geval: om 09:15 melden dat om 09:30 de piek begint,
    met de accu op 11%. Er valt niets meer bij te laden."""
    c = _coordinator(
        make_coordinator, hass, piek_ct=45, basis_ct=30, uren_vooruit=0.25
    )

    assert _gemeld(c) is False


def test_a_flat_day_is_not_a_peak(make_coordinator, hass):
    """17 augustus: 37,1 ct tegen een mediaan van 34,5. Dat is geen piek
    maar gewoon ochtend."""
    c = _coordinator(
        make_coordinator, hass, piek_ct=37, basis_ct=34, uren_vooruit=2
    )

    assert _gemeld(c) is False


def test_the_thresholds_match_the_reported_case():
    """Anderhalf uur zou een melding van 1 uur 28 vooraf wegfilteren, en
    die is wél bruikbaar: 2 kWh bij 2000 W is een kwart van de accu."""
    assert PEAK_ALERT_MIN_HOURS_AHEAD <= 1.5
    assert PEAK_ALERT_MIN_OF_MEDIAN >= 1.10


def test_the_message_names_both_prices_and_the_time_left():
    """Zonder die getallen kun je niet zelf beoordelen of het de moeite
    is - dezelfde reden als bij het goedkope blok (v2.5.0)."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index('"low_soc_before_peak",')
    blok = bron[kop : kop + 900]

    assert "dagmediaan" in blok
    assert "om bij te laden" in blok
