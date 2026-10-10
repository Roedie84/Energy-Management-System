"""v5.72.1: gepland witgoed telt één keer, ook in een lange wandeling.

Gemeten in de leerronde van 10-10 11:18: vaatwasser gepland om 12:16
(1,14 kWh, start over 59 minuten). De wandeling van de reserve en Monte
Carlo liep 22 uur (tot morgen 09:00). `geplande_witgoed_kwh_in_periode`
rekende de start per uursegment opnieuw uit vanaf het BEGIN van dat segment
(`nu + seconden`), dus de start schoof mee en viel in elk segment: vaste
extra 1,9 -> 25,8 kWh, diepste tekort 6,3 -> 30,0 kWh.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_DISHWASHER_START_IN,
)

NU = datetime(2026, 10, 10, 9, 17, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, seconden):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({CONF_DISHWASHER_START_IN: "number.start_in"})
    hass.states.set("number.start_in", str(seconden))
    c.appliance_cycle_kwh = {"vaatwasser": 1.14}
    return c


def _uursegmenten(begin, uren):
    cursor = begin
    eind = begin + timedelta(hours=uren)
    while cursor < eind:
        volgend = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        yield cursor, min(volgend, eind)
        cursor = min(volgend, eind)


def test_start_binnen_het_uur_telt_een_keer_over_22_uur(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, 59 * 60)

    totaal = sum(
        c.geplande_witgoed_kwh_in_periode(a, b) for a, b in _uursegmenten(NU, 22)
    )

    assert round(totaal, 2) == 1.14


def test_alleen_het_segment_met_de_start(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, 59 * 60)

    per_segment = [
        c.geplande_witgoed_kwh_in_periode(a, b) for a, b in _uursegmenten(NU, 22)
    ]

    # 09:17 + 59 min = 10:16 UTC: het tweede segment (10:00-11:00).
    assert per_segment[0] == 0
    assert per_segment[1] == 1.14
    assert sum(1 for k in per_segment if k) == 1


def test_een_latere_periode_rekent_vanaf_nu(make_coordinator, hass):
    """Start over 6 uur; een periode die over 3 uur begint, mag de start
    niet naar 9 uur verschuiven."""
    c = _coordinator(make_coordinator, hass, 6 * 3600)

    later = NU + timedelta(hours=3)
    assert c.geplande_witgoed_kwh_in_periode(later, later + timedelta(hours=4)) == 1.14
    assert c.geplande_witgoed_kwh_in_periode(NU + timedelta(hours=7), NU + timedelta(hours=12)) == 0


def test_de_wandeling_telt_hem_een_keer(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, 59 * 60)
    c.learned_hourly_avg_kw = lambda uur: 0.3
    c._get_smoothed_consumption_correction_ratio = lambda uur: 1.0
    c.regelverschuiving_kw = lambda: 0.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=True: 0.0

    wandeling = c._segmenten_verbruik_zon(NU, NU + timedelta(hours=22))

    verbruik = sum(v for v, _z in wandeling)
    assert round(verbruik, 2) == round(22 * 0.3 + 1.14, 2)


def test_een_start_over_zes_uur_telt_in_de_wandeling(make_coordinator, hass):
    """Voorheen telde een start op meer dan een uur in de uurwandeling nooit:
    begin segment + seconden lag altijd voorbij het segment."""
    c = _coordinator(make_coordinator, hass, 6 * 3600)
    c.learned_hourly_avg_kw = lambda uur: 0.3
    c._get_smoothed_consumption_correction_ratio = lambda uur: 1.0
    c.regelverschuiving_kw = lambda: 0.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=True: 0.0

    wandeling = c._segmenten_verbruik_zon(NU, NU + timedelta(hours=12))

    verbruik = [v for v, _z in wandeling]
    assert round(sum(verbruik), 2) == round(12 * 0.3 + 1.14, 2)
    # 09:17 + 6 u = 15:17 UTC: segment 15:00-16:00 (index 6).
    assert round(verbruik[6] - verbruik[5], 2) == 1.14
