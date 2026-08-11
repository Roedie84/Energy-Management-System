"""Waar de live zoncorrectie op geijkt wordt (v1.27.0).

Gemeld met een screenshot van de kwartierplanning: "Hier gaat wat mis de
accu kan niet in 1 uur vol zijn. Vermogen zonnepanelen is W en niet kWh
dus hier gaat iets niet goed."

De eenheid klopte; de IJKING niet. De correctieverhouding is de live
Solcast-teller "rest van vandaag" gedeeld door onze eigen optelling voor
de rest van vandaag. Die deling geldt alleen vanaf NU - de teller telt af
vanaf het huidige moment.

Hij werd geijkt op het BEGIN VAN DE PERIODE die geschat werd. Voor een
kwartier van later vanmiddag krimpt de noemer terwijl de teller blijft
staan, dus loopt de factor op. Uit de gemelde planning na te rekenen:

    13:00  1,227 / 0,743 = 1,65x
    15:00  1,795 / 0,645 = 2,78x
    16:30  2,641 / 0,517 = 5,11x
    17:30  3,512 / 0,396 = 8,87x

Alle vier de keren komt de impliciete teller uit op 23,0 kWh - de
dagvoorspelling. Gevolg: 3,5 kWh zon in een kwartier, oftewel 14 kW uit
een installatie die op 2,9 kW piekt.

Deze fout raakte élke schatting vooruit, dus ook de reserve en de
verkooptoets.
"""
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from custom_components.energy_management_system.const import (
    CONF_SOLAR_REMAINING_TODAY_SENSOR,
)

# De vorm van 11 augustus: piek rond 13:00, dagtotaal 23 kWh.
VORM = {
    6: 0.05, 7: 0.20, 8: 0.45, 9: 0.75, 10: 0.95, 11: 1.22,
    12: 1.41, 13: 1.45, 14: 1.39, 15: 1.28, 16: 1.06, 17: 0.85,
    18: 0.60, 19: 0.35, 20: 0.15, 21: 0.04,
}


def _entries(dag):
    """Halfuurregels zoals Solcast ze levert."""
    regels = []
    for uur, per_half_uur in VORM.items():
        for minuut in (0, 30):
            start = dag.replace(hour=uur, minute=minuut, second=0, microsecond=0)
            regels.append((start, start + timedelta(minutes=30), per_half_uur))
    return regels


def _coordinator(make_coordinator, hass, nu, rest_kwh):
    c = make_coordinator(
        {CONF_SOLAR_REMAINING_TODAY_SENSOR: "sensor.solcast_rest"}
    )
    hass.states.set("sensor.solcast_rest", str(rest_kwh))
    regels = _entries(nu)
    c._get_pv_forecast_entries = lambda: regels
    c.learned_pv_hourly_ratio = lambda uur: None
    c.solar_tracker = None
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: nu
    return c


def _kwartier(c, dag, uur, minuut=0):
    start = dag.replace(hour=uur, minute=minuut, second=0, microsecond=0)
    return c._estimate_pv_kwh_for_period(start, start + timedelta(minutes=15))


def _nu(uur, minuut=0):
    return dt_util.now().replace(
        year=2026, month=8, day=11, hour=uur, minute=minuut,
        second=0, microsecond=0,
    )


# --- de fout zelf ----------------------------------------------------


def test_the_factor_does_not_grow_through_the_day(make_coordinator, hass):
    """De kern: dezelfde momentopname hoort elk toekomstig kwartier van
    vandaag met DEZELFDE factor te schalen. Liep die op, dan kwam er
    's middags een veelvoud uit."""
    nu = _nu(9)
    c = _coordinator(make_coordinator, hass, nu, rest_kwh=23.0)

    factoren = [
        _kwartier(c, nu, uur) / (VORM[uur] / 2) for uur in (11, 13, 15, 17)
    ]

    assert max(factoren) - min(factoren) < 0.01


def test_an_afternoon_quarter_stays_within_the_inverter(
    make_coordinator, hass
):
    """3,5 kWh in een kwartier is 14 kW; deze installatie piekt op 2,9
    kW. Het getal moet fysiek kunnen."""
    nu = _nu(9)
    c = _coordinator(make_coordinator, hass, nu, rest_kwh=23.0)

    zon = _kwartier(c, nu, 17, 30)

    assert zon < 0.75  # 3 kW gedurende een kwartier


def test_the_live_counter_still_scales_the_estimate(make_coordinator, hass):
    """De correctie mag niet zomaar verdwijnen: valt de dag tegen, dan
    hoort de schatting mee omlaag te gaan."""
    nu = _nu(9)
    ruw = VORM[13] / 2

    somber = _coordinator(make_coordinator, hass, nu, rest_kwh=11.5)
    laag = _kwartier(somber, nu, 13)
    helder = _coordinator(make_coordinator, hass, nu, rest_kwh=23.0)
    hoog = _kwartier(helder, nu, 13)

    # Vanaf 09:00 telt de eigen voorspelling nog 23,0 kWh, dus met een
    # teller van 23,0 verandert er niets en met 11,5 halveert alles.
    assert hoog == ruw
    assert round(laag, 4) == round(ruw / 2, 4)


def test_hours_already_past_do_not_get_the_correction(
    make_coordinator, hass
):
    """De teller gaat over wat er NOG komt. Een uur van vanochtend zit
    daar niet in en hoort de verhouding dus niet te krijgen."""
    nu = _nu(15)
    c = _coordinator(make_coordinator, hass, nu, rest_kwh=8.0)

    ochtend = _kwartier(c, nu, 9)

    assert ochtend == VORM[9] / 2


def test_tomorrow_is_untouched_by_todays_counter(make_coordinator, hass):
    """De teller gaat alleen over vandaag."""
    nu = _nu(9)
    c = _coordinator(make_coordinator, hass, nu, rest_kwh=23.0)
    morgen = nu + timedelta(days=1)
    regels = _entries(nu) + _entries(morgen)
    c._get_pv_forecast_entries = lambda: regels

    assert _kwartier(c, morgen, 13) == VORM[13] / 2


# --- wat het aanrichtte ----------------------------------------------


def test_the_reported_case_no_longer_reproduces(make_coordinator, hass):
    """De gemelde regel: 17:30 stond op 3,512 kWh terwijl de ruwe
    voorspelling 0,396 gaf - een factor 8,87."""
    nu = _nu(9)
    c = _coordinator(make_coordinator, hass, nu, rest_kwh=23.0)

    ruw = VORM[17] / 2
    factor = _kwartier(c, nu, 17, 30) / ruw

    assert factor < 2.0
