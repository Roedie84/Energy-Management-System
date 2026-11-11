"""v5.226.0: prijsreeks en uurverbruik één keer per ronde, Monte Carlo eens per vijf minuten.

Uit het profiel van 11-11 18:30 (v5.225.0): `_get_forecast_entries` 42 keer
(149 ms), `verbruik_uur_kw` 1.461 keer (115 ms), 86.000 trekkingen per ronde.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_MIN_SOC_PERCENT,
    MONTE_CARLO_INTERVAL_S,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)


def _teller(c, naam):
    tel = {"n": 0}
    echt = getattr(c, naam)

    def _geteld(*a, **k):
        tel["n"] += 1
        return echt(*a, **k)

    setattr(c, naam, _geteld)
    return tel


# --- prijsreeks ------------------------------------------------------


def test_de_prijsreeks_een_keer_per_ronde_en_per_sleutel(make_coordinator, hass):
    c = make_coordinator({})
    tel = _teller(c, "_lees_forecast_entries")

    c._get_forecast_entries()
    c._get_forecast_entries()
    assert tel["n"] == 2  # buiten een ronde gewoon lezen

    c._begin_ronde_cache(NU)
    for _ in range(4):
        c._get_forecast_entries()
        c._get_forecast_entries("price_tax_excluded")
    assert tel["n"] == 4


def test_elke_aanroeper_krijgt_een_eigen_lijst(make_coordinator, hass):
    c = make_coordinator({})
    reeks = [(NU, NU + timedelta(minutes=15), 1.0)]
    c._lees_forecast_entries = lambda sleutel=None: list(reeks)
    c._begin_ronde_cache(NU)

    eerste = c._get_forecast_entries()
    eerste.clear()

    assert c._get_forecast_entries() == reeks


def test_de_bevindingen_horen_bij_de_laatst_gelezen_reeks(make_coordinator, hass):
    c = make_coordinator({})

    def _lees(sleutel=None):
        c.prijsreeks_bevindingen = {"reeks": sleutel or "belast"}
        return []

    c._lees_forecast_entries = _lees
    c._begin_ronde_cache(NU)

    c._get_forecast_entries()
    c._get_forecast_entries("kaal")
    assert c.prijsreeks_bevindingen == {"reeks": "kaal"}
    c._get_forecast_entries()  # uit het geheugen: de bevindingen gaan mee terug
    assert c.prijsreeks_bevindingen == {"reeks": "belast"}


# --- uurverbruik -----------------------------------------------------


def test_het_uurverbruik_een_keer_per_uur_en_dagtype(make_coordinator, hass):
    c = make_coordinator({})
    c.hourly_consumption_profile = {u: [0.3, 0.5] for u in range(24)}
    tel = _teller(c, "_bereken_verbruik_uur_kw")
    werkdag, weekend = NU, NU + timedelta(days=3)
    assert werkdag.weekday() < 5 <= weekend.weekday()

    buiten = c.verbruik_uur_kw(9, werkdag)
    c._begin_ronde_cache(NU)
    for _ in range(10):
        assert c.verbruik_uur_kw(9, werkdag) == buiten
        c.verbruik_uur_kw(9, weekend)
        c.verbruik_uur_kw(10, werkdag)

    assert tel["n"] == 1 + 3


# --- het plan blijft hetzelfde ---------------------------------------


def _plan_coordinator(make_coordinator, hass):
    c = make_coordinator({
        CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.cap",
        CONF_MIN_SOC_PERCENT: 15.0,
        CONF_MANUAL_DISCHARGE_POWER: 1600.0,
    })
    hass.states.set("sensor.cap", "8.6")
    c.last_available_kwh = 5.0
    c.last_expensive_price_threshold = 0.32
    c.hourly_consumption_profile = {u: [0.2 + 0.02 * u, 0.3 + 0.01 * u] for u in range(24)}
    entries = []
    for i in range(96):
        start = NU + timedelta(minutes=15 * i)
        prijs = (0.35 if start.hour < 11 else (0.15 if start.hour < 17 else 0.38)) * PRICE_SCALE_FACTOR
        entries.append((start, start + timedelta(minutes=15), prijs))
    c._lees_forecast_entries = lambda sleutel=None: list(entries)
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: (
        0.6 * (b - a).total_seconds() / 3600 if 9 <= a.hour < 16 else 0.0
    )
    return c


def test_het_kwartierplan_is_met_en_zonder_geheugen_gelijk(make_coordinator, hass):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    zonder = _plan_coordinator(make_coordinator, hass).get_quarter_plan(NU)
    c = _plan_coordinator(make_coordinator, hass)
    c._begin_ronde_cache(NU)
    met = c.get_quarter_plan(NU)

    assert zonder and len(zonder) == len(met)
    assert zonder == met
    assert c._ronde_memo  # het geheugen is echt gebruikt


# --- Monte Carlo -----------------------------------------------------


def test_monte_carlo_hooguit_eens_per_interval(make_coordinator, hass):
    c = make_coordinator({})
    keren = []
    c._run_monte_carlo_simulation = lambda now, blok: keren.append(now)
    blok = NU + timedelta(hours=5)

    c._monte_carlo_op_tijd(NU, blok)
    c._monte_carlo_op_tijd(NU + timedelta(seconds=60), blok)
    c._monte_carlo_op_tijd(NU + timedelta(seconds=MONTE_CARLO_INTERVAL_S - 1), blok)
    assert len(keren) == 1

    c._monte_carlo_op_tijd(NU + timedelta(seconds=MONTE_CARLO_INTERVAL_S), blok)
    assert len(keren) == 2


def test_een_ander_blok_of_een_teruggezette_klok_rekent_meteen(make_coordinator, hass):
    c = make_coordinator({})
    keren = []
    c._run_monte_carlo_simulation = lambda now, blok: keren.append(blok)
    blok = NU + timedelta(hours=5)

    c._monte_carlo_op_tijd(NU, blok)
    c._monte_carlo_op_tijd(NU + timedelta(seconds=30), blok + timedelta(hours=1))
    c._monte_carlo_op_tijd(NU - timedelta(hours=1), blok + timedelta(hours=1))

    assert len(keren) == 3
