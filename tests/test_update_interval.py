"""Het interval tussen rondes is instelbaar (v2.2.0).

Gevraagd: "instelbaar maken", nadat de gemeten rondeduur uitkwam op
48,6 ms - 0,016% van de tijd bij vijf minuten.

De grenzen zijn niet willekeurig: bij 48,6 ms per ronde is tien seconden
0,5% belasting en een seconde 4,9% - dat laatste zit tegen de grens van
vijf procent aan waarboven Home Assistant merkbaar op deze integratie
staat te wachten.
"""
from custom_components.energy_management_system.const import (
    CONF_UPDATE_INTERVAL_SECONDS,
    UPDATE_INTERVAL_MAX_SECONDS,
    UPDATE_INTERVAL_MIN_SECONDS,
    UPDATE_INTERVAL_MINUTES,
)

STANDAARD = UPDATE_INTERVAL_MINUTES * 60


def test_without_a_setting_it_stays_five_minutes(make_coordinator, hass):
    """Wie niets instelt, merkt niets."""
    c = make_coordinator({})

    assert c.update_interval_seconds == STANDAARD


def test_a_shorter_interval_is_accepted(make_coordinator, hass):
    c = make_coordinator({CONF_UPDATE_INTERVAL_SECONDS: 30})

    assert c.update_interval_seconds == 30


def test_a_value_below_the_floor_falls_back(make_coordinator, hass):
    """Een interval van nul zou de integratie onafgebroken laten
    draaien; een verkeerd getal mag geen onbruikbaar systeem opleveren."""
    c = make_coordinator({CONF_UPDATE_INTERVAL_SECONDS: 0})

    assert c.update_interval_seconds == STANDAARD


def test_a_value_above_the_ceiling_falls_back(make_coordinator, hass):
    c = make_coordinator(
        {CONF_UPDATE_INTERVAL_SECONDS: UPDATE_INTERVAL_MAX_SECONDS + 1}
    )

    assert c.update_interval_seconds == STANDAARD


def test_nonsense_falls_back(make_coordinator, hass):
    c = make_coordinator({CONF_UPDATE_INTERVAL_SECONDS: "elke minuut"})

    assert c.update_interval_seconds == STANDAARD


def test_the_floor_leaves_room_for_a_slower_round():
    """Vijf seconden laat ruimte voor een tragere ronde op een dag met
    een volle prijsreeks, zonder dat de gebruiker daarop hoeft te
    letten."""
    from custom_components.energy_management_system.const import (
        TICK_MAX_DUTY_FRACTION,
    )

    gemeten_ronde_s = 0.0486
    belasting = gemeten_ronde_s / UPDATE_INTERVAL_MIN_SECONDS

    assert belasting < TICK_MAX_DUTY_FRACTION


def test_the_load_uses_the_configured_interval(make_coordinator, hass):
    """Anders klopt het percentage niet zodra iemand het interval
    aanpast."""
    c = make_coordinator({CONF_UPDATE_INTERVAL_SECONDS: 60})
    c.tick_duration_history = [
        {"wandklok_ms": 48.6, "rekentijd_ms": 48.6, "eerste": False}
    ] * 10

    p = c.get_tick_performance()

    assert p["huidige_interval_seconden"] == 60
    assert abs(p["belasting_procent"] - 100 * 0.0486 / 60) < 0.001


def test_the_tick_is_scheduled_with_the_configured_interval():
    """De instelling moet ook echt de timer bepalen - hem alleen
    opslaan verandert niets."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("async_track_time_interval(")
    blok = bron[kop : kop + 200]

    assert "self.update_interval_seconds" in blok
