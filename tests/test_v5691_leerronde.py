"""v5.69.1 - leerronde 10-10 (L-EMS-011, L-EMS-012).

Alleen rapportage en classificatie; sturing, reserve en marge ongewijzigd.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_DISHWASHER_POWER_SENSOR,
    CONF_QUOOKER_POWER_SENSOR,
    CONF_WASHING_MACHINE_POWER_SENSOR,
)

APPARATEN = ("sensor.vw", "sensor.wm", "sensor.qk")


def _water(make_coordinator, hass, **standen):
    c = make_coordinator(
        {
            CONF_DISHWASHER_POWER_SENSOR: "sensor.vw",
            CONF_WASHING_MACHINE_POWER_SENSOR: "sensor.wm",
            CONF_QUOOKER_POWER_SENSOR: "sensor.qk",
        }
    )
    for naam in APPARATEN:
        hass.states.set(naam, "0")
    for naam, waarde in standen.items():
        hass.states.set(naam, waarde)
    return c


# --- L-EMS-011 --------------------------------------------------------------


def test_de_regeneratie_van_09_10_krijgt_bron_waterontharder(make_coordinator, hass):
    """Gemeten 09-10 03:07: 154 L in 38 min, vlag true, maar bron null."""
    c = _water(make_coordinator, hass)
    uit = c.classify_water_session(154.0, 38.0, waterontharder=True)

    assert uit["bron"] == "waterontharder"
    assert uit["zekerheid"] == "waarschijnlijk"
    assert "154 liter" in uit["reden"] and "38 minuten" in uit["reden"]


def test_zonder_vlag_blijft_de_indeling_zoals_hij_was(make_coordinator, hass):
    c = _water(make_coordinator, hass)
    uit = c.classify_water_session(154.0, 38.0)

    assert uit["bron"] != "waterontharder"


def test_een_draaiende_vaatwasser_gaat_voor_de_ontharder(make_coordinator, hass):
    c = _water(make_coordinator, hass, **{"sensor.vw": "1800"})
    uit = c.classify_water_session(60.0, 30.0, waterontharder=True)

    assert uit["bron"] == "vaatwasser"


def test_ontharder_zonder_volume_heeft_toch_een_reden(make_coordinator, hass):
    c = _water(make_coordinator, hass)
    uit = c.classify_water_session(None, 25.0, waterontharder=True)

    assert uit["bron"] == "waterontharder"
    assert "25 minuten" in uit["reden"]


# --- L-EMS-012: horizon-reden ------------------------------------------------

NU = datetime(2026, 10, 9, 15, 42, tzinfo=timezone.utc)


def test_lopend_blok_heet_niet_prijzen_onbekend(make_coordinator, hass):
    c = make_coordinator({})
    c.last_cheap_block_end = NU + timedelta(hours=1)
    horizon = c._monte_carlo_horizon_kiezen(NU, NU - timedelta(hours=3))

    assert horizon.hour == 9
    assert "loopt nu" in c.monte_carlo_horizon_basis
    assert "onbekend" not in c.monte_carlo_horizon_basis


def test_geen_blok_blijft_prijzen_onbekend(make_coordinator, hass):
    c = make_coordinator({})
    c.last_cheap_block_end = None
    c._monte_carlo_horizon_kiezen(NU, None)

    assert "prijzen morgen nog onbekend" in c.monte_carlo_horizon_basis


def test_voorbij_blok_blijft_prijzen_onbekend(make_coordinator, hass):
    c = make_coordinator({})
    c.last_cheap_block_end = NU - timedelta(minutes=5)
    c._monte_carlo_horizon_kiezen(NU, NU - timedelta(hours=4))

    assert "prijzen morgen nog onbekend" in c.monte_carlo_horizon_basis


def test_toekomstig_blok_ongewijzigd(make_coordinator, hass):
    c = make_coordinator({})
    blok = NU + timedelta(hours=18)
    assert c._monte_carlo_horizon_kiezen(NU, blok) == blok
    assert c.monte_carlo_horizon_basis == "goedkoopste blok"


# --- L-EMS-012: Let op-zin per soort -----------------------------------------


def test_let_op_noemt_economisch_niet_als_onverwacht(make_coordinator, hass):
    """Stand 09-10: 1x economisch + 2x onbekend heette '3x onverwacht'."""
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"shortfall": True, "tekort_soort": "onbekend"},
        {"shortfall": True, "tekort_soort": "onbekend"},
        {"shortfall": True, "tekort_soort": "economisch"},
        {"shortfall": False},
    ]
    tekst = c._let_op_tekortnachten_tekst(3)

    assert "genoeg had moeten hebben" not in tekst
    assert "1x bewust" in tekst
    assert "2x niet meer na te gaan" in tekst
    assert "veiligheidsmarge" in tekst


def test_let_op_planning_blijft_onverwacht(make_coordinator, hass):
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"shortfall": True, "tekort_soort": "planning"},
        {"shortfall": True, "tekort_soort": "capaciteit"},
    ]
    tekst = c._let_op_tekortnachten_tekst(2)

    assert "2x onverwacht, terwijl de accu genoeg had moeten hebben" in tekst


def test_let_op_zonder_records_valt_terug(make_coordinator, hass):
    c = make_coordinator({})
    c.reserve_daily_records = []
    tekst = c._let_op_tekortnachten_tekst(1)

    assert tekst.startswith("Let op:")
    assert "1x" in tekst
