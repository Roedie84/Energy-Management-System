"""Het cyclusverbruik uit de energiemeter (v3.57.0).

Gedeeld op 28 augustus, uit de entiteitenlijst:

    sensor.wasmachine_energy_import   582,7 kWh
    sensor.vaatwasser_energy_import   639,0 kWh

Tot nu toe schatte de integratie het cyclusverbruik uit het VERMOGEN:
het gemiddelde over de metingen maal de duur. De toelichting bij
`_cyclus_energie_kwh` zegt waarom:

    "Uit het VERMOGEN geintegreerd en niet uit de energieteller: die
    teller is cumulatief en de stand bij het begin van de cyclus is niet
    bewaard."

Die stand valt wel te bewaren. Dan is het geen benadering meer maar een
meting: eindstand min beginstand, precies wat er doorheen ging.

Waarom dat uitmaakt: het geleerde cyclusverbruik gaat de reserve in. Een
vaatwasser die 1,1 kWh gebruikt terwijl er 0,8 wordt geschat, betekent
elke keer 0,3 kWh te weinig achtergehouden.
"""
import pytest

from custom_components.energy_management_system.const import (
    APPLIANCE_CYCLE_MAX_KWH,
    CONF_DISHWASHER_ENERGY_SENSOR,
    CONF_WASHING_MACHINE_ENERGY_SENSOR,
)

VAATWASSER = "_dishwasher_state"
WASMACHINE = "_washing_machine_state"


def _coordinator(make_coordinator, meter="sensor.vaatwasser_energy_import"):
    return make_coordinator({CONF_DISHWASHER_ENERGY_SENSOR: meter})


# --- de meting -------------------------------------------------------


def test_the_meter_difference_is_the_consumption(make_coordinator, hass):
    """De gemeten werkelijkheid: 639,02 aan het begin, 640,12 aan het

    eind is 1,10 kWh.
    """
    c = _coordinator(make_coordinator)
    hass.states.set("sensor.vaatwasser_energy_import", "639.02")
    c._onthoud_meterstand_bij_start(VAATWASSER)

    hass.states.set("sensor.vaatwasser_energy_import", "640.12")

    assert c._cyclus_uit_de_meter_kwh(VAATWASSER) == pytest.approx(1.10)


def test_each_appliance_has_its_own_meter(make_coordinator, hass):
    """De vaatwasser en de wasmachine mogen elkaars stand niet gebruiken."""
    c = make_coordinator(
        {
            CONF_DISHWASHER_ENERGY_SENSOR: "sensor.vaatwasser_energy_import",
            CONF_WASHING_MACHINE_ENERGY_SENSOR: "sensor.wasmachine_energy_import",
        }
    )
    hass.states.set("sensor.vaatwasser_energy_import", "639.0")
    hass.states.set("sensor.wasmachine_energy_import", "582.0")
    c._onthoud_meterstand_bij_start(VAATWASSER)
    c._onthoud_meterstand_bij_start(WASMACHINE)

    hass.states.set("sensor.vaatwasser_energy_import", "640.0")
    hass.states.set("sensor.wasmachine_energy_import", "582.6")

    assert c._cyclus_uit_de_meter_kwh(VAATWASSER) == pytest.approx(1.0)
    assert c._cyclus_uit_de_meter_kwh(WASMACHINE) == pytest.approx(0.6)


# --- wanneer de meter niets zegt -------------------------------------


def test_without_a_meter_it_returns_nothing(make_coordinator, hass):
    """Dan valt de aanroeper terug op de schatting uit het vermogen, en

    dat is beter dan een verzonnen getal.
    """
    c = make_coordinator({})
    c._onthoud_meterstand_bij_start(VAATWASSER)

    assert c._cyclus_uit_de_meter_kwh(VAATWASSER) is None


def test_without_a_start_reading_it_returns_nothing(make_coordinator, hass):
    """Bijvoorbeeld na een herstart midden in een cyclus."""
    c = _coordinator(make_coordinator)
    hass.states.set("sensor.vaatwasser_energy_import", "640.0")

    assert c._cyclus_uit_de_meter_kwh(VAATWASSER) is None


def test_a_counter_that_jumped_back_is_refused(make_coordinator, hass):
    """Een teller die terugspringt - na een herstart van het apparaat of

    een reset - levert een negatief verschil op.
    """
    c = _coordinator(make_coordinator)
    hass.states.set("sensor.vaatwasser_energy_import", "639.0")
    c._onthoud_meterstand_bij_start(VAATWASSER)

    hass.states.set("sensor.vaatwasser_energy_import", "0.0")

    assert c._cyclus_uit_de_meter_kwh(VAATWASSER) is None


def test_an_absurd_jump_is_refused(make_coordinator, hass):
    """Een wasmachine gebruikt hooguit een paar kWh per cyclus."""
    c = _coordinator(make_coordinator)
    hass.states.set("sensor.vaatwasser_energy_import", "639.0")
    c._onthoud_meterstand_bij_start(VAATWASSER)

    hass.states.set(
        "sensor.vaatwasser_energy_import", str(639.0 + APPLIANCE_CYCLE_MAX_KWH + 1)
    )

    assert c._cyclus_uit_de_meter_kwh(VAATWASSER) is None


def test_the_reading_is_used_only_once(make_coordinator, hass):
    """De beginstand hoort bij één cyclus; blijft hij staan, dan meet de

    volgende cyclus vanaf een verkeerd punt.
    """
    c = _coordinator(make_coordinator)
    hass.states.set("sensor.vaatwasser_energy_import", "639.0")
    c._onthoud_meterstand_bij_start(VAATWASSER)
    hass.states.set("sensor.vaatwasser_energy_import", "640.0")

    assert c._cyclus_uit_de_meter_kwh(VAATWASSER) == pytest.approx(1.0)
    assert c._cyclus_uit_de_meter_kwh(VAATWASSER) is None


def test_an_unreadable_meter_at_the_start(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    hass.states.set("sensor.vaatwasser_energy_import", "unavailable")
    c._onthoud_meterstand_bij_start(VAATWASSER)
    hass.states.set("sensor.vaatwasser_energy_import", "640.0")

    assert c._cyclus_uit_de_meter_kwh(VAATWASSER) is None


# --- de voorrang -----------------------------------------------------


def test_the_meter_wins_over_the_estimate():
    """Eerst de meter, dan pas de schatting - anders blijft de

    benadering staan terwijl er een meting beschikbaar is.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C._update_appliance_state_machine)
    uit_meter = bron.index("_cyclus_uit_de_meter_kwh")
    schatting = bron.index("_cyclus_energie_kwh")

    assert uit_meter < schatting
