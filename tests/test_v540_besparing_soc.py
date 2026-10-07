"""Dagbesparing gecorrigeerd voor de accu-inhoud (v5.40).

Gemeld: "besparing t.o.v. zonder accu-sturing" stond 's avonds op -0,70
euro, deels omdat energie die eerder geladen was en nog in de accu zat niet
gewaardeerd werd. De sensor toont nu de gecorrigeerde dagbesparing:

    rauw + (beschikbaar nu - beschikbaar bij dagbegin) x waarde per kWh nu

met het rauwe cijfer en de correctie als attributen.
"""
from datetime import datetime, timezone

import pytest

from custom_components.energy_management_system.sensor import (
    CounterfactualSavingsSensor,
)


def _c(make_coordinator, begin=1.2, nu_kwh=7.6, waarde=0.30):
    c = make_coordinator({})
    c._savings_day_start_available_kwh = begin
    c.beschikbare_energie_kwh = lambda: nu_kwh
    c.current_feedin_value_eur_per_kwh = waarde
    c.counterfactual_cost_today_eur = 1.00
    c.actual_cost_today_eur = 1.70
    return c


def test_de_toestand_is_gecorrigeerd(make_coordinator, hass):
    c = _c(make_coordinator)
    sensor = CounterfactualSavingsSensor(c, "x")

    # -0,70 rauw + 6,4 kWh x 0,30 = +1,22
    assert sensor.native_value == pytest.approx(1.22, abs=0.01)
    attrs = sensor.extra_state_attributes
    assert attrs["besparing_ongecorrigeerd"] == -0.70
    assert attrs["soc_correctie_eur"] == pytest.approx(1.92, abs=0.01)
    assert attrs["opgeslagen_kwh_verschil"] == pytest.approx(6.4)
    assert attrs["kwh_waarde_nu_eur"] == 0.30
    assert attrs["soc_correctie_toegepast"] is True
    assert "accu-inhoud" in attrs["note"]


def test_een_leeggelopen_accu_verlaagt_de_besparing(make_coordinator, hass):
    c = _c(make_coordinator, begin=7.0, nu_kwh=1.0)

    assert CounterfactualSavingsSensor(c, "x").native_value < -0.70


def test_zonder_beginstand_het_rauwe_cijfer(make_coordinator, hass):
    c = _c(make_coordinator, begin=None)
    sensor = CounterfactualSavingsSensor(c, "x")

    assert sensor.native_value == -0.70
    attrs = sensor.extra_state_attributes
    assert attrs["soc_correctie_toegepast"] is False
    assert attrs["soc_correctie_eur"] is None
    assert attrs["besparing_ongecorrigeerd"] == -0.70


def test_zonder_kwh_waarde_het_rauwe_cijfer(make_coordinator, hass):
    c = _c(make_coordinator, waarde=None)

    assert CounterfactualSavingsSensor(c, "x").native_value == -0.70


def test_dagwissel_legt_de_beginstand_vast(make_coordinator, hass):
    c = make_coordinator(
        {
            "consumption_power_sensor_entity": "sensor.p1",
            "available_energy_sensor_entity": "sensor.beschikbaar",
        }
    )
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.beschikbaar", "4.2")
    c.huidige_prijs_eur_per_kwh = lambda: 0.25

    c._update_counterfactual_savings(datetime(2026, 10, 8, 0, 0, 30, tzinfo=timezone.utc))

    assert c._savings_day_start_available_kwh == 4.2


def test_beginstand_alsnog_in_het_eerste_uur(make_coordinator, hass):
    c = make_coordinator(
        {
            "consumption_power_sensor_entity": "sensor.p1",
            "available_energy_sensor_entity": "sensor.beschikbaar",
        }
    )
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.beschikbaar", "unavailable")
    c.huidige_prijs_eur_per_kwh = lambda: 0.25
    c.beschikbare_energie_kwh = lambda: None
    c._update_counterfactual_savings(datetime(2026, 10, 8, 0, 0, 30, tzinfo=timezone.utc))
    assert c._savings_day_start_available_kwh is None

    c.beschikbare_energie_kwh = lambda: 4.0
    c._update_counterfactual_savings(datetime(2026, 10, 8, 0, 5, tzinfo=timezone.utc))
    assert c._savings_day_start_available_kwh == 4.0

    # later op de dag geen dagbegin meer
    c._savings_day_start_available_kwh = None
    c._update_counterfactual_savings(datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc))
    assert c._savings_day_start_available_kwh is None


def test_de_beginstand_overleeft_een_herstart():
    from custom_components.energy_management_system.const import (
        PERSISTED_DATE_FIELDS,
        PERSISTED_PLAIN_FIELDS,
    )

    assert "_savings_day_start_available_kwh" in PERSISTED_PLAIN_FIELDS
    assert "_counterfactual_day_key" in PERSISTED_DATE_FIELDS
