"""v5.267.0: de ijking van het airco-vermogen op de P1-meter herkende geen
fase (27-11: 15 blokken, 'nog geen fase herkend'). De accu en de
zonnepanelen hangen op L1 en bewegen die fase met kilowatts; met de
regel 'beste fase >= 3x de rest' wint de airco-fase dan nooit. Blokken
waarin de accu of de zon meer dan 50 W doet, tellen niet meer."""
from datetime import timedelta

from custom_components.energy_management_system import airco_ritme as ar

from test_v5265_airco_ijking import T0, _dag


def _speel_coordinator(c, hass, accu_w):
    ritme = ar.leeg()
    for i, (hz, fasen) in enumerate(_dag()):
        a = accu_w(i, hz)
        # de accu ontlaadt op L1 (het net ziet minder afname op L1)
        l1 = fasen[0] - a
        for naam, w in zip(("sensor.l1", "sensor.l2", "sensor.l3"), (l1, fasen[1], fasen[2])):
            hass.states.set(naam, str(w), {})
        hass.states.set("sensor.quooker", "0", {})
        hass.states.set("sensor.accu", str(a), {})
        hass.states.set("sensor.pv", "0", {})
        c._airco_ijking_ronde(T0 + timedelta(minutes=i), ritme, hz)
    c.airco_ritme = ritme
    return ritme


def _coordinator(make_coordinator):
    c = make_coordinator({})
    c.config = dict(c.config or {}, phase_power_sensor_entities=["sensor.l1", "sensor.l2", "sensor.l3"],
                    quooker_power_sensor_entity="sensor.quooker",
                    battery_power_sensor_entity="sensor.accu", pv_power_sensor_entity="sensor.pv")
    return c


def test_accu_die_het_huis_volgt_verstoort_de_fase_niet_meer(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    # de eerste helft van de draaibeurt ontlaadt de accu 1,5 kW op L1, daarna staat hij stil
    _speel_coordinator(c, hass, lambda i, hz: 1500.0 if hz > 0 and i < 120 else 0.0)
    uit = c.get_airco_vermogen()["ijking_p1"]
    assert uit["fase"] == 2
    # alleen de blokken met een stille accu tellen (60 van de 120 minuten draaien)
    assert uit["blokken"] == 6


def test_zonder_de_regel_zou_l1_de_fase_overstemmen(make_coordinator, hass):
    """Gevoeligheid: met een accu onder 50 W blijven alle blokken staan."""
    c = _coordinator(make_coordinator)
    _speel_coordinator(c, hass, lambda i, hz: 30.0 if hz > 0 else 0.0)
    assert c.get_airco_vermogen()["ijking_p1"]["blokken"] == 12
