"""Aanwezigheid uit bewegingssensoren (v1.18.2).

Gevraagd: "Ook zijn er meerdere bewegingssensoren in huis aanwezig, ik
wil dat je daarmee analyseert of er iemand thuis is of niet. Ook daar kun
je van leren lijkt me."

Bewust een INSTELBARE lijst en geen automatische herkenning: van de
twintig bewegingsachtige entiteiten in deze installatie hangen er
meerdere buiten (deurbel, tuin, schuur). Die slaan aan als de kat
langsloopt en zeggen niets over of er iemand thuis is.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_PRESENCE_MOTION_SENSORS,
    PRESENCE_ABSENCE_AFTER_MINUTES,
    PRESENCE_MIN_OBSERVATIONS,
)

NU = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
SENSOREN = ["binary_sensor.gang", "binary_sensor.woonkamer"]


def _coordinator(make_coordinator, hass, sensoren=SENSOREN):
    c = make_coordinator({CONF_PRESENCE_MOTION_SENSORS: sensoren})
    for naam in SENSOREN:
        hass.states.set(naam, "off")
    return c


# --- de detectie -----------------------------------------------------


def test_motion_means_someone_is_home(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")

    c._update_presence(NU)

    assert c.presence_state == "thuis"


def test_a_short_quiet_period_is_still_home(make_coordinator, hass):
    """Stilzitten op de bank is geen afwezigheid."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(NU + timedelta(minutes=20))

    assert c.presence_state == "thuis"


def test_a_long_quiet_period_means_away(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(
        NU + timedelta(minutes=PRESENCE_ABSENCE_AFTER_MINUTES + 5)
    )

    assert c.presence_state == "weg"


def test_any_sensor_counts(make_coordinator, hass):
    """Beweging in de woonkamer telt net zo goed als in de gang."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.woonkamer", "on")

    c._update_presence(NU)

    assert c.presence_state == "thuis"


def test_the_threshold_is_generous():
    """Een korte drempel zou 's nachts elk uur "niemand thuis"
    melden."""
    assert PRESENCE_ABSENCE_AFTER_MINUTES >= 30


# --- het leren -------------------------------------------------------


def test_it_learns_per_half_hour_of_the_week(make_coordinator, hass):
    """Een week is de natuurlijke cyclus: werkdagen verschillen van het
    weekend, ochtend van avond."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")

    c._update_presence(NU)

    sleutel = f"{NU.weekday()}-0800"
    assert c.presence_week_profile[sleutel] == [1, 1]


def test_absence_is_learned_too(make_coordinator, hass):
    """Weten wanneer je NIET thuis bent is even bruikbaar."""
    c = _coordinator(make_coordinator, hass)
    c.last_motion_at = NU - timedelta(hours=3)

    c._update_presence(NU)

    sleutel = f"{NU.weekday()}-0800"
    assert c.presence_week_profile[sleutel] == [0, 1]


def test_the_overview_needs_enough_observations(make_coordinator, hass):
    """Twee weken zegt nog niets over een vast patroon."""
    c = _coordinator(make_coordinator, hass)
    c.presence_week_profile = {
        "0-0800": [2, PRESENCE_MIN_OBSERVATIONS - 1],
        "0-1800": [5, PRESENCE_MIN_OBSERVATIONS + 2],
    }

    profiel = c.get_presence_overview()["profiel"]

    assert "0-0800" not in profiel
    assert "0-1800" in profiel


def test_the_profile_stays_bounded(make_coordinator, hass):
    """Zonder begrenzing blijven oude gewoontes eeuwig meewegen."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")

    for minuut in range(0, 60 * 24 * 60, 30):
        c._update_presence(NU + timedelta(minutes=minuut))

    for aan, totaal in c.presence_week_profile.values():
        assert totaal <= 12, totaal


# --- zonder configuratie ---------------------------------------------


def test_without_sensors_it_says_what_to_do(make_coordinator, hass):
    """Buitensensoren zouden hier juist schade doen, dus het is een
    keuze - met uitleg waarom."""
    c = _coordinator(make_coordinator, hass, sensoren=[])

    overzicht = c.get_presence_overview()

    assert overzicht["beschikbaar"] is False
    assert "BINNEN" in overzicht["reden"]
    assert "voorbijgangers" in overzicht["reden"]


def test_without_sensors_no_state(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, sensoren=[])

    c._update_presence(NU)

    assert c.presence_state is None


# --- inbedding -------------------------------------------------------


def test_it_runs_every_tick():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "self._update_presence(now)" in bron


def test_it_is_in_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "presence_overview" in bron
    assert "presence_week_profile" in bron


def test_the_profile_survives_a_restart():
    import custom_components.energy_management_system.const as C

    bewaard = set()
    for naam in dir(C):
        if naam.startswith("PERSISTED_") and isinstance(getattr(C, naam), tuple):
            bewaard |= set(getattr(C, naam))

    assert "presence_week_profile" in bewaard


def test_the_config_field_allows_multiple():
    """Meerdere sensoren, want één ruimte dekt het huis niet."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "config_flow.py").read_text()
    start = bron.index("CONF_PRESENCE_MOTION_SENSORS,\n                default")

    assert "multiple=True" in bron[start : start + 400]
