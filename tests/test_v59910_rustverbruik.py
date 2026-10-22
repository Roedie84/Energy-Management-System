"""v5.99.10: één hoofdgetal voor de besparing, en het rustverbruik van de omvormer."""
from types import SimpleNamespace

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)
from custom_components.energy_management_system.sensor import (
    CounterfactualSavingsTotalSensor,
)


def _z(standen, eta=85.0):
    return SimpleNamespace(accu_tellerstanden=standen, learned_battery_efficiency_percent=eta,
                           huidige_prijs_eur_per_kwh=lambda: 0.30)


def test_rustverbruik_uit_dagstanden():
    # 10 dagen: 100 kWh erin, 80 eruit, inhoud gelijk; rondreisverlies 15 -> rust 5 kWh
    st = {f"2026-10-{d:02d}": [1000 + (d - 1) * 10.0, 800 + (d - 1) * 8.0, 5.0] for d in range(1, 12)}
    r = C.get_rustverbruik(_z(st))
    assert r["beschikbaar"] and r["dagen"] == 10
    assert r["kwh_per_dag"] == 0.5
    assert r["gemiddeld_w"] == 20.8
    assert r["eur_per_maand_bij_huidige_prijs"] == 4.5


def test_te_weinig_dagen():
    assert C.get_rustverbruik(_z({"2026-10-01": [1, 1, 1]}))["beschikbaar"] is False


def test_noteren_eens_per_dag_en_venster():
    z = SimpleNamespace(accu_tellerstanden={}, beschikbare_energie_kwh=lambda: 3.0,
                        _levenslang_geleverd_kwh=lambda: 1922.3,
                        _laadteller_entiteit=lambda: "sensor.x_aggr_charge",
                        _read_sensor_float=lambda e: 2377.2 if e else None)
    C._noteer_accu_tellers(z, "2026-10-17")
    z._levenslang_geleverd_kwh = lambda: 9999
    C._noteer_accu_tellers(z, "2026-10-17")
    assert z.accu_tellerstanden == {"2026-10-17": [2377.2, 1922.3, 3.0]}


def test_laadteller_naast_ontlaadteller():
    z = SimpleNamespace(config={"battery_discharge_energy_sensor_entity": "sensor.sf_aggr_discharge"},
                        hass=SimpleNamespace(states=SimpleNamespace(get=lambda e: object() if e == "sensor.sf_aggr_charge" else None)))
    assert C._laadteller_entiteit(z) == "sensor.sf_aggr_charge"


def test_totaalsensor():
    # v5.116.0: het totaal komt uit de coordinator (met de voorraadcorrectie);
    # zonder correctie is het het rauwe verschil.
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )
    c = object.__new__(C)
    c.counterfactual_cost_all_time_eur = -30.03
    c.actual_cost_all_time_eur = -70.87
    c.get_savings_correction = lambda: {"correctie_beschikbaar": False}
    s = CounterfactualSavingsTotalSensor(c, "e")
    assert s.native_value == 40.84
    assert s._attr_state_class == "total"
