"""v5.46: robuust vloerverbruik voor de sluipverbruik-detectie (L-EMS-004).

Gemeten in de uuranalyse van 8 oktober: referentie -225 W, 21 van de 30
dagminima negatief. Het dagminimum van losse monsters ving de wisselpieken
van de accu: de P1-meter en het accuvermogen werken niet tegelijk bij, en
elke ~25 minuten zag een monster -2,1 tot -2,2 kW op de P1-meter terwijl
het accuvermogen nog de vorige waarde had. Nu: het laagste KWARTIER als
mediaan van zijn monsters, nooit onder 0 W, en de oude reeks eenmalig weg.
"""
import copy
from datetime import datetime, timezone

import pytest

from custom_components.energy_management_system.const import (
    CUSUM_VLOER_MIN_MONSTERS,
    PERSISTED_FIELDS,
    SLUIPVERBRUIK_METHODE_VERSIE,
)

DAG = datetime(2026, 10, 7, tzinfo=timezone.utc)


def _coord(make_coordinator):
    return make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})


def _kwartier(c, hass, uur, waarden, dag=DAG):
    for minuut, w in enumerate(waarden):
        hass.states.set("sensor.p1", str(w))
        c._update_anomaly_detection(dag.replace(hour=uur, minute=minuut))


def test_een_wisselpiek_telt_niet_als_vloer(make_coordinator, hass):
    """Het gemeten geval: 14 monsters huislast, één monster -2,2 kW."""
    c = _coord(make_coordinator)
    _kwartier(c, hass, 3, [250] * 7 + [-2200] + [250] * 7)
    c._update_anomaly_detection(DAG.replace(hour=3, minute=15))

    assert c._today_min_load_kw == pytest.approx(0.25)


def test_het_oude_dagminimum_zou_de_piek_hebben_gepakt(make_coordinator, hass):
    """Ter vergelijking: het minimum van de monsters is de piek."""
    assert min([250] * 7 + [-2200] + [250] * 7) == -2200


def test_vloer_is_nooit_negatief(make_coordinator, hass):
    c = _coord(make_coordinator)
    _kwartier(c, hass, 3, [-80] * 10)
    c._update_anomaly_detection(DAG.replace(hour=3, minute=15))

    assert c._today_min_load_kw == 0.0


def test_een_te_kort_kwartier_telt_niet(make_coordinator, hass):
    """Herstart midden in een kwartier: te weinig monsters, geen oordeel."""
    c = _coord(make_coordinator)
    _kwartier(c, hass, 3, [90] * (CUSUM_VLOER_MIN_MONSTERS - 1))
    c._update_anomaly_detection(DAG.replace(hour=3, minute=15))

    assert c._today_min_load_kw is None


def test_het_laatste_kwartier_hoort_bij_de_oude_dag(make_coordinator, hass):
    """Het kwartier 23:45 wordt pas na middernacht gesloten, maar telt
    voor de dag waarin het begon."""
    c = _coord(make_coordinator)
    _kwartier(c, hass, 12, [400] * 6)
    hass.states.set("sensor.p1", "150")
    for minuut in range(45, 51):
        c._update_anomaly_detection(DAG.replace(hour=23, minute=minuut))
    c._update_anomaly_detection(DAG.replace(day=8, hour=0, minute=0))

    assert c.baseline_load_history == [0.15]
    assert c._today_min_load_kw is None


def test_finalize_begrenst_ook_een_oude_negatieve_waarde(make_coordinator):
    c = _coord(make_coordinator)
    c._finalize_baseline_load_day(-0.225)

    assert c.baseline_load_history == [0.0]


# --- migratie ---------------------------------------------------------

OUDE_REEKS = [0.1531, -1.0032, 0.0061, -0.025, -0.6324, -0.3489, -0.6989]


def test_de_vervuilde_reeks_wordt_gewist(make_coordinator):
    c = _coord(make_coordinator)
    c.baseline_load_history = list(OUDE_REEKS)
    c.cusum_accumulator_kw = 0.3734
    c.sluipverbruik_detected = True
    c.sluipverbruik_reference_w = -225.0

    c._migreer_sluipverbruik_methode()

    assert c.baseline_load_history == []
    assert c.cusum_accumulator_kw == 0.0
    assert c.sluipverbruik_detected is False
    assert c.sluipverbruik_reference_w is None
    assert c.sluipverbruik_methode_versie == SLUIPVERBRUIK_METHODE_VERSIE


def test_de_migratie_gebeurt_maar_een_keer(make_coordinator):
    c = _coord(make_coordinator)
    c._migreer_sluipverbruik_methode()
    c.baseline_load_history = [0.21, 0.22]
    c._migreer_sluipverbruik_methode()

    assert c.baseline_load_history == [0.21, 0.22]


def test_de_oude_reeks_komt_niet_terug_via_de_herstelstap(make_coordinator):
    """De opslag wordt na de sensoren nog een keer toegepast (v5.9); de
    oude reeks mag daar niet alsnog terugkomen."""
    c = _coord(make_coordinator)
    opgeslagen = {
        "baseline_load_history": list(OUDE_REEKS),
        "cusum_accumulator_kw": 0.3734,
        "sluipverbruik_detected": True,
    }
    c._apply_persisted_state(copy.deepcopy(opgeslagen))
    c._bewaar_geladen_opslag(copy.deepcopy(opgeslagen))
    c._migreer_sluipverbruik_methode()

    c.herstel_de_opslag_na_de_sensoren()

    assert c.baseline_load_history == []
    assert c.sluipverbruik_detected is False
    assert c.sluipverbruik_methode_versie == SLUIPVERBRUIK_METHODE_VERSIE


def test_de_versie_wordt_bewaard():
    assert "sluipverbruik_methode_versie" in PERSISTED_FIELDS


def test_een_reeks_van_de_nieuwe_methode_blijft_staan(make_coordinator):
    c = _coord(make_coordinator)
    opgeslagen = {
        "baseline_load_history": [0.21, 0.22],
        "sluipverbruik_methode_versie": SLUIPVERBRUIK_METHODE_VERSIE,
    }
    c._apply_persisted_state(copy.deepcopy(opgeslagen))
    c._migreer_sluipverbruik_methode()

    assert c.baseline_load_history == [0.21, 0.22]


def test_de_sensor_zet_geen_oude_reeks_terug():
    """De sensor herstelt alleen een reeks die hetzelfde versienummer
    draagt; de attributen van vóór v5.46 hebben er geen."""
    import inspect

    from custom_components.energy_management_system.sensor import (
        SluipverbruikSensor,
    )

    bron = inspect.getsource(SluipverbruikSensor.async_added_to_hass)
    assert 'attrs.get("methode_versie") != SLUIPVERBRUIK_METHODE_VERSIE' in bron


# --- L-EMS-003: andere opwekmeter -------------------------------------


def test_een_andere_opwekmeter_ijkt_opnieuw(make_coordinator, hass):
    """Cloud-dagteller (11,868 kWh) naar Modbus-levensteller (23.426 kWh):
    de dagopwek blijft staan en telt vanaf hier door."""
    c = make_coordinator({})
    c._verwerk_pv_meterstand(11.0, "sensor.solaredge_production_energy")
    c._verwerk_pv_meterstand(11.868, "sensor.solaredge_production_energy")
    assert c.pv_production_today_kwh == pytest.approx(0.868)

    c._verwerk_pv_meterstand(23426.364, "sensor.solaredge_i1_ac_energy")
    assert c.pv_production_today_kwh == pytest.approx(0.868)

    c._verwerk_pv_meterstand(23427.364, "sensor.solaredge_i1_ac_energy")
    assert c.pv_production_today_kwh == pytest.approx(1.868)


def test_opslag_van_voor_v546_ijkt_ook_opnieuw(make_coordinator, hass):
    """Onbekend welke meter het dagbegin hoort: veilig opnieuw ijken."""
    c = make_coordinator({})
    c._pv_energy_meter_day_start = 11.0
    c._pv_energy_meter_last = 11.868
    c.pv_production_today_kwh = 0.868

    c._verwerk_pv_meterstand(23426.364, "sensor.solaredge_i1_ac_energy")

    assert c.pv_production_today_kwh == pytest.approx(0.868)
    assert c._pv_energy_meter_entity == "sensor.solaredge_i1_ac_energy"


def test_de_meter_wordt_bewaard():
    assert "_pv_energy_meter_entity" in PERSISTED_FIELDS


def test_wh_meter_wordt_omgerekend(make_coordinator, hass):
    """De eenheid werd al afgehandeld; dit legt het vast."""
    c = make_coordinator({})
    hass.states.set(
        "sensor.wh", "11868", {"unit_of_measurement": "Wh"}
    )
    assert c._read_sensor_float("sensor.wh") == pytest.approx(11.868)
