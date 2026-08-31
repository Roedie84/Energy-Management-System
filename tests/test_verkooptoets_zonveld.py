"""De verkooptoets noemt gerealiseerde zon "verwacht" (v3.94.2).

Gemeten in de export van 31 augustus 21:02:

    sell_check.verwachte_zon_kwh   12,8
    solar_today.opgewekt_kwh       12,8
    solar_today.voorspeld_kwh      13,8

Om 21:02 is er niets meer te verwachten. Het getal is de HELE DAG: wat
er al is opgewekt plus wat er nog komt - en dat is precies goed voor
waar het voor gebruikt wordt. De zonarme-dagtoets van v1.24.2 kijkt
bewust naar de hele dag, want anders leest een avond als een zonarme dag
terwijl er 20 kWh in zat.

Alleen heet het veld in de uitvoer `verwachte_zon_kwh`, en dat leest 's
avonds als een voorspelling die nergens op slaat. Het cijfer klopt, de
naam niet.

Dit is geen rekenfout. Maar een naam die iets anders belooft dan hij
levert, is precies hoe `available_kwh` en `gemeten_kwh` maandenlang
verkeerd gelezen zijn.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 8, 31, 21, 2, tzinfo=timezone.utc)


def _toets(c, opgewekt=12.8, nog_te_komen=0.0):
    c.pv_production_today_kwh = opgewekt
    c._estimate_pv_kwh_for_period = lambda a, b: nog_te_komen
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 2.0
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.beschikbare_energie_kwh = lambda: 5.79
    c.last_cheap_block_start = NU.replace(hour=23)
    return c.may_sell_now(NU)


def _config():
    return {"solar_today_forecast_sensor_entity": "sensor.solcast"}


def test_het_veld_heet_niet_meer_verwacht(make_coordinator, hass):
    """Om 21:02 valt er niets meer te verwachten."""
    c = make_coordinator(_config())

    uitkomst = _toets(c)

    assert "verwachte_zon_kwh" not in uitkomst


def test_de_hele_dag_staat_er_onder_zijn_eigen_naam(make_coordinator, hass):
    c = make_coordinator(_config())

    uitkomst = _toets(c)

    assert uitkomst["zon_hele_dag_kwh"] == pytest.approx(12.8, abs=0.05)


def test_opgewekt_en_nog_te_komen_staan_apart(make_coordinator, hass):
    """Zonder die splitsing is niet te zien of 12,8 een voorspelling was

    of een meting - en dat was juist de verwarring.
    """
    c = make_coordinator(_config())

    uitkomst = _toets(c, opgewekt=8.0, nog_te_komen=4.8)

    assert uitkomst["zon_opgewekt_kwh"] == pytest.approx(8.0, abs=0.05)
    assert uitkomst["zon_nog_te_komen_kwh"] == pytest.approx(4.8, abs=0.05)
    assert uitkomst["zon_hele_dag_kwh"] == pytest.approx(12.8, abs=0.05)


def test_de_zonarme_dagtoets_rekent_nog_met_de_hele_dag(
    make_coordinator, hass
):
    """v1.24.2, gemeld: "Zonarme dag is natuurlijk raar om 20:23, de zon

    is zo goed als weg en de dagopbrengst was goed." Die reparatie mag
    niet sneuvelen bij een hernoeming.
    """
    c = make_coordinator(_config())

    uitkomst = _toets(c, opgewekt=12.8, nog_te_komen=0.1)

    assert uitkomst["mag_verkopen"] is not False or "Zonarme" not in (
        uitkomst.get("reden") or ""
    )


def test_een_echt_zonarme_dag_remt_nog_steeds(make_coordinator, hass):
    c = make_coordinator(_config())

    uitkomst = _toets(c, opgewekt=1.0, nog_te_komen=0.2)

    assert uitkomst["mag_verkopen"] is False
    assert "Zonarme" in uitkomst["reden"]
    assert uitkomst["zon_hele_dag_kwh"] == pytest.approx(1.2, abs=0.05)
