"""Live beweging en gewogen bewolking (v1.20.2).

Twee meldingen:

1. "Beweging moet live gedetecteerd en weergegeven worden, ook voor
   melding indien vakantie. Aan/afwezigheid is natuurlijk vertraagd."

   De tick draaide elke vijf minuten en keek of een sensor op DAT MOMENT
   "on" stond. Een bewegingsmelder staat 30 tot 60 seconden aan - kans
   ongeveer één op vijf. In een echte export: 3 van de 15 sensoren ooit
   waargenomen, de laatste 550 minuten geleden, terwijl er die nacht
   gewoon geslapen en opgestaan was.

2. "De bewolking nakijken, het is nu bijna onbewolkt" - terwijl de
   integratie 62% toonde, het gemiddelde van 78,1% (forecast_thuis) en
   46,0% (openweathermap).
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_KNMI_WEATHER_ENTITY,
    CONF_OPENWEATHERMAP_WEATHER_ENTITY,
    CONF_PRESENCE_MOTION_SENSORS,
    CONF_PRESENCE_TV_ENTITY,
    WEATHER_BEST_SOURCE_MIN_LEAD_PP,
    WEATHER_DISAGREEMENT_PREFER_BEST_PP,
)

NU = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)


class _Staat:
    def __init__(self, entity_id, state):
        self.entity_id = entity_id
        self.state = state
        self.attributes = {}


class _Event:
    def __init__(self, entity_id, oud, nieuw):
        self.data = {
            "entity_id": entity_id,
            "old_state": _Staat(entity_id, oud) if oud is not None else None,
            "new_state": _Staat(entity_id, nieuw),
        }


# --- live beweging ---------------------------------------------------


def _bewegingscoordinator(make_coordinator):
    c = make_coordinator(
        {
            CONF_PRESENCE_MOTION_SENSORS: ["binary_sensor.gang"],
            CONF_PRESENCE_TV_ENTITY: "remote.tv",
        }
    )
    return c


def test_motion_is_recorded_immediately(make_coordinator, hass):
    """Niet wachten op de tick: die mist vier van de vijf bewegingen."""
    c = _bewegingscoordinator(make_coordinator)

    c._handle_motion_event(_Event("binary_sensor.gang", "off", "on"))

    assert "binary_sensor.gang" in c.presence_last_seen
    assert c.last_motion_at is not None


def test_only_the_transition_counts(make_coordinator, hass):
    """Blijft een sensor aan staan, dan is dat één beweging - geen
    stroom van gebeurtenissen."""
    c = _bewegingscoordinator(make_coordinator)
    c.vacation_mode = True
    c._handle_motion_event(_Event("binary_sensor.gang", "off", "on"))
    eerste = c._last_intrusion_alert_at

    c._handle_motion_event(_Event("binary_sensor.gang", "on", "on"))

    assert c._last_intrusion_alert_at == eerste


def test_switching_off_is_ignored(make_coordinator, hass):
    c = _bewegingscoordinator(make_coordinator)
    c.vacation_mode = True

    c._handle_motion_event(_Event("binary_sensor.gang", "on", "off"))

    assert c._last_intrusion_alert_at is None


def test_the_vacation_alert_is_immediate(make_coordinator, hass):
    """De kern van de melding: die kwam niet te laat maar meestal
    helemaal niet, omdat de sensor bij de tick al weer uit stond."""
    c = _bewegingscoordinator(make_coordinator)
    c.vacation_mode = True

    c._handle_motion_event(_Event("binary_sensor.gang", "off", "on"))

    assert c._last_intrusion_alert_at is not None


def test_the_listener_is_registered():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "self._handle_motion_event" in bron
    assert "_unsub_motion_state" in bron


def test_the_tick_remains_a_fallback():
    """Een herstart midden in een beweging mag die beweging niet
    kwijtraken."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("def _update_presence")
    blok = bron[start : start + 2500]

    assert "_registreer_beweging" in blok


# --- gewogen bewolking -----------------------------------------------


def _weercoordinator(make_coordinator, hass, knmi, owm, b_knmi, b_owm):
    c = make_coordinator(
        {
            CONF_KNMI_WEATHER_ENTITY: "weather.forecast_thuis",
            CONF_OPENWEATHERMAP_WEATHER_ENTITY: "weather.openweathermap",
        }
    )
    c.get_weather_source_reliability = lambda: {
        "weather.forecast_thuis": {
            "overeenstemming_percent": b_knmi,
            "aantal_waarnemingen": 200,
        },
        "weather.openweathermap": {
            "overeenstemming_percent": b_owm,
            "aantal_waarnemingen": 200,
        },
    }
    hass.states.set("weather.forecast_thuis", "cloudy", {"cloud_coverage": knmi})
    hass.states.set("weather.openweathermap", "sunny", {"cloud_coverage": owm})
    c._update_weather_ensemble_check(NU)
    return c


def test_strong_disagreement_picks_the_better_source(make_coordinator, hass):
    """Het gerapporteerde geval: 78,1% en 46,0% middelen tot 62% levert
    een getal op dat bij geen van beide past."""
    c = _weercoordinator(make_coordinator, hass, 78.1, 46.0, 81.5, 90.5)

    assert c.weather_ensemble_cloud_cover_percent == 46.0
    assert c.weather_ensemble_chosen_source == "weather.openweathermap"


def test_small_differences_are_still_averaged(make_coordinator, hass):
    """Bij kleine verschillen is middelen juist goed: dan is het ruis,
    geen onenigheid."""
    c = _weercoordinator(make_coordinator, hass, 52.0, 48.0, 81.5, 90.5)

    assert c.weather_ensemble_chosen_source is None
    assert 45 <= c.weather_ensemble_cloud_cover_percent <= 55


def test_an_equally_good_source_does_not_win(make_coordinator, hass):
    """Zonder aantoonbaar betere bron valt er niets te kiezen."""
    c = _weercoordinator(make_coordinator, hass, 78.1, 46.0, 85.0, 86.0)

    assert c.weather_ensemble_chosen_source is None


def test_without_reliability_data_it_averages(make_coordinator, hass):
    """De eerste dagen is er niets om op te wegen."""
    c = make_coordinator(
        {
            CONF_KNMI_WEATHER_ENTITY: "weather.forecast_thuis",
            CONF_OPENWEATHERMAP_WEATHER_ENTITY: "weather.openweathermap",
        }
    )
    c.get_weather_source_reliability = lambda: {}
    hass.states.set("weather.forecast_thuis", "cloudy", {"cloud_coverage": 78.1})
    hass.states.set("weather.openweathermap", "sunny", {"cloud_coverage": 46.0})

    c._update_weather_ensemble_check(NU)

    assert c.weather_ensemble_weighted is False
    assert c.weather_ensemble_cloud_cover_percent == 62.0


def test_the_thresholds_are_sensible():
    assert WEATHER_DISAGREEMENT_PREFER_BEST_PP >= 20
    assert WEATHER_BEST_SOURCE_MIN_LEAD_PP >= 3


def test_it_is_in_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "weather_ensemble_chosen_source" in bron


# --- v1.20.5: de status liep achter -------------------------------


def test_motion_sets_the_state_immediately(make_coordinator, hass):
    """Gemeld: "Er is gezien de sensoren weldegelijk iemand thuis,
    echter status onbekend?" - met een tabel waarin de bovenste sensor
    0,2 minuten geleden bewoog.

    De live gebeurtenis vulde wél de tabel en `last_motion_at`, maar
    herberekende de STATUS niet; die werd alleen op de vijf-minutentick
    gezet. Dat is precies de verkeerde kant op: afwezigheid mag
    vertraagd zijn, aanwezigheid niet.
    """
    c = _bewegingscoordinator(make_coordinator)

    c._handle_motion_event(_Event("binary_sensor.gang", "off", "on"))

    assert c.presence_state == "thuis"


def test_the_table_survives_a_restart():
    """Zonder bewaren is de tabel na elke herstart leeg, terwijl juist
    die tabel moet verklaren waarom de status is wat hij is."""
    import custom_components.energy_management_system.const as C

    bewaard = set()
    for naam in dir(C):
        if naam.startswith("PERSISTED_") and isinstance(getattr(C, naam), tuple):
            bewaard |= set(getattr(C, naam))

    assert "presence_last_seen" in bewaard


def test_after_a_restart_the_table_restores_the_state(
    make_coordinator, hass
):
    """`last_motion_at` is dan leeg maar de bewaarde tabel niet; de
    laatste regel daaruit is de beste schatting."""
    from datetime import datetime, timezone

    c = _bewegingscoordinator(make_coordinator)
    c.presence_last_seen = {
        "binary_sensor.gang": datetime.now(timezone.utc).isoformat()
    }
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(datetime.now(timezone.utc))

    assert c.presence_state == "thuis"


def test_a_truly_empty_system_still_says_unknown(make_coordinator, hass):
    """Zonder enige waarneming is "onbekend" het eerlijke antwoord."""
    from datetime import datetime, timezone

    c = _bewegingscoordinator(make_coordinator)
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(datetime.now(timezone.utc))

    assert c.presence_state == "onbekend"
