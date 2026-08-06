"""Werkelijk huishoudverbruik (v0.63.111, gevraagd na naamgevings-
verwarring: de bestaande "Huidig verbruik"-tegel toonde de kale
P1-meter-aflezing, die negatief kan zijn bij exporteren en dus niet
het werkelijke huishoudverbruik representeert.
"""


def test_reflects_the_corrected_consumption_calculation(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        HouseholdConsumptionSensor,
    )

    coordinator = make_coordinator(
        {
            "consumption_power_sensor_entity": "sensor.p1",
            "battery_power_sensor_entity": "sensor.battery",
            "pv_power_sensor_entity": "sensor.pv",
        }
    )
    # Exporting on P1 (-500W), but the household is genuinely drawing
    # 800W, covered by 1300W of PV production.
    hass.states.set("sensor.p1", "-500")
    hass.states.set("sensor.battery", "0")
    hass.states.set("sensor.pv", "1300")

    sensor = HouseholdConsumptionSensor(coordinator, "entry1")

    assert sensor.native_value == 800.0


def test_none_without_a_readable_p1_sensor(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        HouseholdConsumptionSensor,
    )

    coordinator = make_coordinator({})
    sensor = HouseholdConsumptionSensor(coordinator, "entry1")

    assert sensor.native_value is None
