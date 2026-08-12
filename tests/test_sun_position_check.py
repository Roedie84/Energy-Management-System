"""Klopt de uitgelezen zonstand? (v1.71.0)

Gevraagd: "Kunnen we op een of andere manier verifieren dat de azimuth
correct wordt uitgelezen?"

De zonstand is uit tijd en plaats te berekenen, en Home Assistant kent
de coordinaten. Dat geeft een onafhankelijke toets.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_SUN_AZIMUTH_SENSOR,
    RELIABILITY_RELIABLE,
    RELIABILITY_UNRELIABLE,
    RELIABILITY_UNVERIFIABLE,
)

# 12 augustus 2026, 17:30 in Lochem - het moment van de melding.
MOMENT = datetime(2026, 8, 12, 15, 30, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, azimut, lat=52.16, lon=6.41):
    c = make_coordinator({CONF_SUN_AZIMUTH_SENSOR: "sensor.azimut"})
    hass.states.set("sensor.azimut", str(azimut))
    _geef_coordinaten(hass, lat, lon)
    return c


def _geef_coordinaten(hass, lat, lon):
    """De testomgeving heeft geen `config`; die maken we hier na."""
    from types import SimpleNamespace

    hass.config = SimpleNamespace(latitude=lat, longitude=lon)


def test_the_real_reading_checks_out(make_coordinator, hass):
    """De gemelde 248,05° tegen 252,9° berekend voor Lochem: 4,9 graden,
    precies wat een aflezing van een paar minuten eerder oplevert."""
    c = _coordinator(make_coordinator, hass, 248.05)

    toets = c.get_sun_position_check(MOMENT)

    assert toets["status"] == RELIABILITY_RELIABLE
    assert 250 <= toets["berekend_azimut"] <= 256
    assert toets["verschil_graden"] < 5.0


def test_the_calculation_matches_the_known_position(make_coordinator, hass):
    """De hoogte hoort ook te kloppen - rond 31 graden op dat moment."""
    c = _coordinator(make_coordinator, hass, 248.05)

    toets = c.get_sun_position_check(MOMENT)

    assert 29 <= toets["berekende_hoogte"] <= 34


def test_a_wrong_sensor_is_caught(make_coordinator, hass):
    """Een sensor die iets anders geeft dan de azimut valt op."""
    c = _coordinator(make_coordinator, hass, 90.0)

    toets = c.get_sun_position_check(MOMENT)

    assert toets["status"] == RELIABILITY_UNRELIABLE
    assert "Controleer" in toets["reden"]


def test_radians_instead_of_degrees_is_caught(make_coordinator, hass):
    """Vangt een sensor die graden en radialen door elkaar haalt."""
    c = _coordinator(make_coordinator, hass, 4.33)

    toets = c.get_sun_position_check(MOMENT)

    assert toets["status"] == RELIABILITY_UNRELIABLE


def test_a_value_outside_the_circle_is_caught(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, 512.0)

    toets = c.get_sun_position_check(MOMENT)

    assert toets["status"] == RELIABILITY_UNRELIABLE
    assert "geen azimut" in toets["reden"]


def test_the_wrap_around_is_handled(make_coordinator, hass):
    """359 en 1 graad schelen twee graden, geen 358 - anders zou elke
    middernacht een alarm geven."""
    c = make_coordinator({CONF_SUN_AZIMUTH_SENSOR: "sensor.azimut"})
    _geef_coordinaten(hass, 52.16, 6.41)
    middernacht = datetime(2026, 8, 12, 22, 15, tzinfo=timezone.utc)
    berekend, _hoogte = c._bereken_zonstand(middernacht)
    # Een sensor die er twee graden naast zit, over de nul heen.
    hass.states.set("sensor.azimut", str((berekend - 2) % 360))

    toets = c.get_sun_position_check(middernacht)

    assert toets["verschil_graden"] < 3
    assert toets["status"] == RELIABILITY_RELIABLE


def test_without_coordinates_it_says_so(make_coordinator, hass):
    """Niet te toetsen is iets anders dan fout."""
    c = _coordinator(make_coordinator, hass, 248.05, lat=None, lon=None)

    toets = c.get_sun_position_check(MOMENT)

    assert toets["status"] == RELIABILITY_UNVERIFIABLE


def test_without_a_sensor_nothing_is_claimed(make_coordinator, hass):
    c = make_coordinator({})

    assert c.get_sun_position_check(MOMENT)["beschikbaar"] is False
