"""Gepland witgoed telt mee in de reserve (v1.61.0).

Gevraagd: "Nu weet ik zelf dat er morgen 2 wasmachines en een vaatwasser
zullen draaien, hoe gaat de integratie daar mee om?"

Niet - en dat is een gat van 4 a 5 kWh, meer dan de helft van de
bruikbare accu. Het geleerde uurprofiel staat op 0,20 tot 0,51 kW.

Home Connect weet het wél. Uitlezen, niet bedienen.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_DISHWASHER_START_IN,
    CONF_WASHING_MACHINE_END_AT,
)

NU = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, **config):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    return make_coordinator(config)


def test_a_delayed_dishwasher_is_seen(make_coordinator, hass):
    c = _coordinator(
        make_coordinator, hass, **{CONF_DISHWASHER_START_IN: "number.start_in"}
    )
    hass.states.set("number.start_in", str(6 * 3600))  # over zes uur

    plan = c.get_planned_appliance_load(NU)

    assert plan["beschikbaar"] is True
    assert plan["apparaten"][0]["start_kort"] == "02:00"
    assert plan["totaal_kwh"] > 0


def test_a_planned_end_time_is_seen(make_coordinator, hass):
    c = _coordinator(
        make_coordinator, hass, **{CONF_WASHING_MACHINE_END_AT: "sensor.einde"}
    )
    hass.states.set("sensor.einde", (NU + timedelta(hours=8)).isoformat())

    plan = c.get_planned_appliance_load(NU)

    assert plan["apparaten"][0]["apparaat"] == "wasmachine"
    assert "starttijd niet" in plan["apparaten"][0]["let_op"]


def test_it_reaches_the_consumption_estimate(make_coordinator, hass):
    """Dit is het hele punt: zonder deze regel rekenen de reserve, de
    energiebrug en de verkooptoets te laag."""
    c = _coordinator(
        make_coordinator, hass, **{CONF_DISHWASHER_START_IN: "number.start_in"}
    )
    c.learned_hourly_avg_kw = lambda uur: 0.3
    c._get_smoothed_consumption_correction_ratio = lambda uur: 1.0
    zonder = c._estimate_consumption_kwh_for_period(NU, NU + timedelta(hours=8))

    hass.states.set("number.start_in", str(6 * 3600))
    met = c._estimate_consumption_kwh_for_period(NU, NU + timedelta(hours=8))

    assert met > zonder
    assert round(met - zonder, 2) == 1.0


def test_a_cycle_outside_the_period_does_not_count(make_coordinator, hass):
    c = _coordinator(
        make_coordinator, hass, **{CONF_DISHWASHER_START_IN: "number.start_in"}
    )
    hass.states.set("number.start_in", str(10 * 3600))

    assert c.geplande_witgoed_kwh_in_periode(NU, NU + timedelta(hours=4)) == 0


def test_nothing_planned_changes_nothing(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    assert c.get_planned_appliance_load(NU)["beschikbaar"] is False
    assert c.geplande_witgoed_kwh_in_periode(NU, NU + timedelta(hours=12)) == 0


def test_a_start_far_in_the_future_is_ignored(make_coordinator, hass):
    """Verder vooruit dan een dag is de planning zelf niet betrouwbaar
    genoeg om er een cyclus in te hangen."""
    c = _coordinator(
        make_coordinator, hass, **{CONF_DISHWASHER_START_IN: "number.start_in"}
    )
    hass.states.set("number.start_in", str(40 * 3600))

    assert c.get_planned_appliance_load(NU)["beschikbaar"] is False


def test_a_measured_cycle_replaces_the_estimate(make_coordinator, hass):
    """Schatten is een noodgreep; zodra een hele cyclus gemeten is, is
    dat de waarde."""
    c = _coordinator(
        make_coordinator, hass, **{CONF_DISHWASHER_START_IN: "number.start_in"}
    )
    hass.states.set("number.start_in", str(3 * 3600))

    geschat = c.get_planned_appliance_load(NU)["apparaten"][0]
    c._leer_cyclusverbruik("vaatwasser", 1.42)
    gemeten = c.get_planned_appliance_load(NU)["apparaten"][0]

    assert geschat["herkomst"] == "schatting"
    assert gemeten["herkomst"] == "gemeten"
    assert gemeten["kwh"] == 1.42


def test_one_odd_cycle_does_not_set_the_norm(make_coordinator, hass):
    """Een halve lading of een eco-programma hoort het beeld niet te
    bepalen - vandaar de mediaan."""
    c = _coordinator(make_coordinator, hass)

    for kwh in (1.0, 1.1, 0.2, 1.05):
        c._leer_cyclusverbruik("vaatwasser", kwh)

    assert 1.0 <= c.appliance_cycle_kwh["vaatwasser"] <= 1.1


def test_the_measured_value_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "appliance_cycle_kwh" in PERSISTED_PLAIN_FIELDS


def test_it_reads_but_never_starts():
    """De grens die we eerder trokken: uitlezen wat jij hebt ingesteld,
    niet zelf de startknop indrukken."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_planned_appliance_load")
    staart = bron[kop : bron.index("def _leer_cyclusverbruik")]
    code = "\n".join(r.split("#")[0] for r in staart.splitlines())

    for verboden in ("async_call", "set_value", "press", "turn_on"):
        assert verboden not in code, verboden
