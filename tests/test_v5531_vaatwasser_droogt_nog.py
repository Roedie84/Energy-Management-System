"""v5.53.1: een vaatwasser die droogt is niet klaar.

Gemeld op 8 oktober: "Ik krijg nu een melding dat de vaatwasser klaar is
maar dit klopt natuurlijk niet". Quick 65 liep tot 16:16; om 15:58 kwam
"klaar", want het droogdeel gebruikt ~2,5 W - meer dan 5 minuten onder de
drempel. De Home Connect-bedrijfstoestand stond nog op "run".
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 10, 8, 13, 6, tzinfo=timezone.utc)


def _run(c, hass, power_w, when):
    hass.states.set("sensor.vaatwasser_vermogen", str(power_w))
    c._update_appliance_state_machine(
        when,
        power_entity="sensor.vaatwasser_vermogen",
        state_attr="_dishwasher_state",
        cycle_started_attr="_dishwasher_cycle_started_at",
        below_threshold_since_attr="_dishwasher_below_threshold_since",
        duration_history_attr="dishwasher_cycle_duration_history",
    )


def test_niet_klaar_zolang_het_programma_loopt(make_coordinator, hass):
    c = make_coordinator({"dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen"})
    c.__dict__["_bedrijfstoestand_entiteit"] = {"vaatwasser": "sensor.vaatwasser_operation_state"}
    hass.states.set("sensor.vaatwasser_operation_state", "run")
    _run(c, hass, 1800, DAY0)
    _run(c, hass, 2.5, DAY0 + timedelta(minutes=40))
    _run(c, hass, 2.5, DAY0 + timedelta(minutes=52))
    assert c._dishwasher_state == "actief"
    # het programma is af: dan meteen klaar
    hass.states.set("sensor.vaatwasser_operation_state", "finished")
    _run(c, hass, 0.5, DAY0 + timedelta(minutes=70))
    assert c._dishwasher_state == "klaar"


def test_zonder_bedrijfstoestand_beslist_het_vermogen(make_coordinator, hass):
    c = make_coordinator({"dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen"})
    c.__dict__["_bedrijfstoestand_entiteit"] = {"vaatwasser": None}
    _run(c, hass, 1800, DAY0)
    _run(c, hass, 0, DAY0 + timedelta(minutes=40))
    _run(c, hass, 0, DAY0 + timedelta(minutes=46))
    assert c._dishwasher_state == "klaar"


def test_pauze_en_uitgestelde_start_lopen_nog():
    from custom_components.energy_management_system.const import APPARAAT_LOOPT_NOG
    assert {"run", "pause", "delayedstart"} <= APPARAAT_LOOPT_NOG
    assert "finished" not in APPARAAT_LOOPT_NOG and "ready" not in APPARAAT_LOOPT_NOG


def test_herkent_home_connect_ook_aan_de_unique_id():
    from pathlib import Path
    import custom_components.energy_management_system as pkg
    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    assert 'endswith(\n                            "BSH.Common.Status.OperationState"' in bron


def test_wasmachine_wacht_ook_op_het_programma(make_coordinator, hass):
    c = make_coordinator({"washing_machine_power_sensor_entity": "sensor.wasmachine_vermogen"})
    c.__dict__["_bedrijfstoestand_entiteit"] = {"wasmachine": "sensor.wasmachine_status"}
    hass.states.set("sensor.wasmachine_status", "run")

    def run(w, when):
        hass.states.set("sensor.wasmachine_vermogen", str(w))
        c._update_appliance_state_machine(
            when, power_entity="sensor.wasmachine_vermogen",
            state_attr="_washing_machine_state",
            cycle_started_attr="_washing_machine_cycle_started_at",
            below_threshold_since_attr="_washing_machine_below_threshold_since",
            duration_history_attr="washing_machine_cycle_duration_history",
        )

    run(2000, DAY0)
    run(1, DAY0 + timedelta(minutes=30))
    run(1, DAY0 + timedelta(minutes=40))
    assert c._washing_machine_state == "actief"
    hass.states.set("sensor.wasmachine_status", "finished")
    run(1, DAY0 + timedelta(minutes=45))
    assert c._washing_machine_state == "klaar"
