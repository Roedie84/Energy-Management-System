"""LiveNarrativeSensor (v0.63.97): stelt het lopende verhaal bloot als
sensor - state (afgekapt op 255 tekens, HA's limiet) + het volledige
verhaal als attribuut.
"""


def test_state_truncated_to_255_chars(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        LiveNarrativeSensor,
    )

    coordinator = make_coordinator({})
    coordinator.last_explanation = "A" * 400

    sensor = LiveNarrativeSensor(coordinator, "entry1")

    assert len(sensor.native_value) == 255


def test_full_narrative_available_as_attribute(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        LiveNarrativeSensor,
    )

    coordinator = make_coordinator({})
    coordinator.last_explanation = "A" * 400

    sensor = LiveNarrativeSensor(coordinator, "entry1")

    assert len(sensor.extra_state_attributes["verhaal"]) == 400
