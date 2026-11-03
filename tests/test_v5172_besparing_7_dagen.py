"""v5.172.0 punt 3 - de besparingscijfers over 7 dagen gelijkgetrokken.

Analyse 03-11 (27-10 t/m 02-11): `besparing_totaal` +EUR 0,90 (de sensor),
het kostprijsmodel +EUR 1,51, een eigen berekening EUR 1,99. Vermoeden:
alleen de sensor trekt het sluimerverbruik af. Gemeten: de kWh-meter van de
accu staat bij stilstand op ~0 W, dus dat is het niet. Wel: de sensor
waardeerde de voorraad met de modulesprong eraf (02-11 eindigde op 15-16 % =
0,58-0,69 kWh, geteld als 0,02) en tegen de prijs van elke dag apart, zodat
dagen niet op elkaar aansloten.
"""
from datetime import date

import pytest

from custom_components.energy_management_system.const import PERSISTED_FIELDS


def _c(make_coordinator, inhoud, waarde):
    c = make_coordinator({})
    c.voorraad_inhoud_kwh = lambda: inhoud["kwh"]
    c._voorraad_kwh_waarde = lambda: (waarde["eur"], "gemeten laadprijs van de voorraad")
    c.counterfactual_cost_today_eur = 0.0
    c.actual_cost_today_eur = 0.0
    return c


def test_boekwaarde_sluit_dagen_op_elkaar_aan(make_coordinator, hass):
    """Twee dagen met een andere laadprijs: opgeteld = in één keer gerekend."""
    inhoud, waarde = {"kwh": 3.0}, {"eur": 0.30}
    c = _c(make_coordinator, inhoud, waarde)
    c._begin_besparingsdag(None)  # dag 1 begint: 3 kWh x 0,30 = 0,90
    inhoud["kwh"], waarde["eur"] = 5.0, 0.25
    dag1 = c.get_savings_correction()
    c._begin_besparingsdag(dag1)  # dag 2 begint met de eindwaarde van dag 1
    inhoud["kwh"], waarde["eur"] = 1.0, 0.40
    dag2 = c.get_savings_correction()
    samen = dag1["voorraadwaarde_exact_eur"] + dag2["voorraadwaarde_exact_eur"]
    assert samen == pytest.approx(1.0 * 0.40 - 3.0 * 0.30)
    # de oude manier (verschil x prijs van de dag) kwam elders uit
    oud = (5.0 - 3.0) * 0.25 + (1.0 - 5.0) * 0.40
    assert abs(oud - samen) > 0.2


def test_voorraad_is_de_gemeten_inhoud_niet_de_sturingsinhoud(make_coordinator, hass):
    """02-11: dag eindigt op 0,6912 kWh gemeten, sturing rekent met 0,14."""
    c = make_coordinator({"available_energy_sensor_entity": "sensor.b"})
    hass.states.set("sensor.b", "0.6912", {"unit_of_measurement": "kWh"})
    c.module_leeg_correctie_kwh = lambda: 0.551
    assert c.beschikbare_energie_kwh() == pytest.approx(0.1402)
    assert c.voorraad_inhoud_kwh() == pytest.approx(0.6912)


def test_schijnverlies_02_11_verdwijnt(make_coordinator, hass):
    inhoud, waarde = {"kwh": 0.0}, {"eur": 0.43}
    c = _c(make_coordinator, inhoud, waarde)
    c._begin_besparingsdag(None)
    inhoud["kwh"] = 0.6912
    corr = c.get_savings_correction()
    assert corr["voorraadwaarde_exact_eur"] == pytest.approx(0.297, abs=0.001)
    # met 0,02 (de sturingsinhoud) was het 0,0086: ~EUR 0,29 verschil op één dag


def test_dag_afsluiten_en_vergelijken(make_coordinator, hass):
    inhoud, waarde = {"kwh": 1.0}, {"eur": 0.30}
    c = _c(make_coordinator, inhoud, waarde)
    c.total_battery_savings_eur = 66.0
    c._begin_besparingsdag(None)
    c.counterfactual_cost_today_eur, c.actual_cost_today_eur = 3.0, 2.5
    c.total_battery_savings_eur = 66.4
    c._tel_sluimer(-10.0, 24.0, 0.25)  # 10 W stilstand, een dag: 0,24 kWh
    inhoud["kwh"] = 1.0
    c._sluit_besparingsdag(date(2026, 11, 2), c.get_savings_correction())
    v = c.besparing_vergelijking()
    assert v["beschikbaar"] and v["dagen"] == 1
    assert v["hoofdgetal_incl_sluimer_eur"] == pytest.approx(0.50)
    assert v["sluimer_kwh"] == pytest.approx(0.24)
    assert v["sluimer_eur"] == pytest.approx(0.06)
    assert v["hoofdgetal_excl_sluimer_eur"] == pytest.approx(0.56)
    assert v["kostprijsmodel_excl_sluimer_excl_slijtage_eur"] == pytest.approx(0.40)
    assert v["verschil_met_kostprijsmodel_eur"] == pytest.approx(0.16)
    assert "incl. sluimer" in v["betekenis"] and "excl. slijtage" in v["betekenis"]


def test_ontladen_en_grote_stroom_zijn_geen_sluimer(make_coordinator, hass):
    c = make_coordinator({})
    c.sluimer_vandaag = {"kwh": 0.0, "eur": 0.0}
    c._tel_sluimer(300.0, 1.0, 0.3)
    c._tel_sluimer(-800.0, 1.0, 0.3)
    assert c.sluimer_vandaag == {"kwh": 0.0, "eur": 0.0}


def test_hoogstens_14_dagen_en_per_datum_een_regel(make_coordinator, hass):
    c = _c(make_coordinator, {"kwh": 0.0}, {"eur": 0.3})
    for d in range(1, 20):
        c._sluit_besparingsdag(date(2026, 10, d), {})
    c._sluit_besparingsdag(date(2026, 10, 19), {})
    assert len(c.besparing_dagen) == 14
    assert len({r["datum"] for r in c.besparing_dagen}) == 14
    assert c.besparing_vergelijking()["dagen"] == 7


def test_zonder_dagen_niets_te_vergelijken(make_coordinator, hass):
    assert make_coordinator({}).besparing_vergelijking()["beschikbaar"] is False


def test_velden_worden_bewaard():
    for veld in ("_savings_day_start_stock_eur", "_kostprijs_dagbegin_eur",
                 "sluimer_vandaag", "besparing_dagen", "ondergrens_waarnemingen"):
        assert veld in PERSISTED_FIELDS


def test_sensoren_tonen_de_vergelijking():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text(encoding="utf-8")
    assert bron.count('"vergelijking_7_dagen": _veilig_dict(c.besparing_vergelijking)') == 2
