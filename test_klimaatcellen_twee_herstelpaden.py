"""Twee herstelpaden voor dezelfde gegevens (v3.42.1).

Gemeten in de export van 20 augustus 14:10, ná het installeren van
v3.41.0: veertig klimaatcellen, allemaal nog met de oude sleutel op
buitentemperatuur, en geen enkele met de nieuwe.

De opruiming werkte wel degelijk - er staat een toets op die aantoont
dat hij de oude sleutels weggooit. Maar hij draait bij het terugzetten
van de OPSLAG, en daarna komt de klimaatsensor langs die dezelfde cellen
uit zijn eigen entiteit-attributen terugzet. Twee paden voor dezelfde
gegevens, en de tweede won.

Precies de klasse fout die deze codebase eerder zag bij de
NILM-apparaten (v0.63.115): entiteit-attributen die de Store
overschrijven, met als gevolg dat een reparatie in de opslag geen effect
heeft.
"""
import asyncio

from custom_components.energy_management_system import sensor as S


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _VorigeStand:
    def __init__(self, attributen):
        self.state = "on"
        self.attributes = attributen


def _sensor(coordinator, attributen):
    entiteit = S.ClimateForecastSensor(coordinator, entry_id="entry1")
    entiteit.async_write_ha_state = lambda: None
    entiteit.async_get_last_state = lambda: _klaar(_VorigeStand(attributen))
    return entiteit


async def _klaar(waarde):
    return waarde


def test_the_sensor_no_longer_restores_the_old_keys(make_coordinator, hass):
    """De aanleiding: veertig oude cellen die na elke herstart terugkwamen

    ondanks de opruiming.
    """
    c = make_coordinator({})
    c.climate_rate_history = {}
    entiteit = _sensor(
        c,
        {
            "geleerde_cellen": {
                "26.0|beide_open|uit": [-0.284, 0.137],
                "22.0|beide_dicht|uit": [-0.102],
            }
        },
    )

    _run(entiteit.async_added_to_hass())

    assert c.climate_rate_history == {}


def test_the_new_keys_are_still_restored(make_coordinator, hass):
    """Het herstelpad zelf moet blijven werken - anders raakt de

    projectie zijn geheugen kwijt bij elke herstart.
    """
    c = make_coordinator({})
    c.climate_rate_history = {}
    entiteit = _sensor(
        c,
        {"geleerde_cellen": {"d-4.0|beide_dicht|uit": [-0.1, -0.12]}},
    )

    _run(entiteit.async_added_to_hass())

    assert c.climate_rate_history == {"d-4.0|beide_dicht|uit": [-0.1, -0.12]}


def test_a_mixed_set_keeps_only_the_new(make_coordinator, hass):
    c = make_coordinator({})
    c.climate_rate_history = {}
    entiteit = _sensor(
        c,
        {
            "geleerde_cellen": {
                "26.0|beide_open|uit": [-0.284],
                "d2.0|beide_open|uit": [0.15],
            }
        },
    )

    _run(entiteit.async_added_to_hass())

    assert list(c.climate_rate_history) == ["d2.0|beide_open|uit"]


def test_the_bias_history_still_comes_back(make_coordinator, hass):
    """Die reeks staat los van de sleutelwijziging en hoort ongemoeid te

    blijven - hij is honderd metingen lang en netjes geconvergeerd.
    """
    c = make_coordinator({})
    c.climate_forecast_bias_history = []
    entiteit = _sensor(
        c, {"voorspelling_bias_geschiedenis": [-1.3, 0.2, 0.1]}
    )

    _run(entiteit.async_added_to_hass())

    assert c.climate_forecast_bias_history == [-1.3, 0.2, 0.1]
