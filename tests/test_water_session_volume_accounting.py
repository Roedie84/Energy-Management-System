"""Waterverbruik: dagtotaal verklaard door gebruiksmomenten (v0.63.119).

Gerapporteerd (derde keer): "Waterverbruik: dagtotaal (85 L) is een stuk
hoger dan wat de geregistreerde gebruiksmomenten van vandaag verklaren
(5 L) - mogelijk worden nog steeds stoten gemist."

Drie afzonderlijk aantoonbare oorzaken, elk hier apart getest:

1. **Meterstand-resolutie.** De liters per moment kwamen uitsluitend uit
   het verschil van de cumulatieve meterstand. Bij een stand in m3 met
   twee decimalen is de kleinste waarneembare stap 10 liter, dus elke
   kraan-/toilet-/handen-was-stoot kwam uit op 0,0 L. De momenten werden
   wél gelogd, maar met volume nul. Nu wordt het debiet geïntegreerd.

2. **Weergavevenster als rekenbasis.** De diagnostiek telde de liters van
   vandaag op uit `water_session_history`, die maar de laatste 20
   momenten bewaart. Meer momenten op een dag => structureel te laag
   "verklaard" totaal, los van of de detectie werkte.

3. **Tijdzone.** `last_changed` komt in UTC binnen terwijl de tick lokale
   tijd doorgeeft. Een moment tussen middernacht en 02:00 lokaal kreeg
   de datum van gisteren (telde niet mee voor vandaag), en het
   waterontharder-venster (0-6 uur) verschoof mee.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_WATER_ACTIVE_USAGE_SENSOR,
    CONF_WATER_DAILY_TOTAL_SENSOR,
    CONF_WATER_TOTAL_USAGE_SENSOR,
    WATER_SESSION_HISTORY_LENGTH,
)

import pytest
from homeassistant.util import dt as dt_util

LOCAL = timezone(timedelta(hours=2))
DAY0 = datetime(2026, 8, 6, 9, 0, tzinfo=LOCAL)


@pytest.fixture(autouse=True)
def _local_timezone():
    """De gedeelde test-fake van `dt_util.as_local` laat een tz-bewuste
    waarde ongemoeid, waardoor een tijdzone-fout niet zichtbaar zou
    worden. Hier tijdelijk een echte omrekening naar NL-zomertijd, met
    expliciete opruiming - conform de les uit v0.63.108 over
    testbestanden die dt_util globaal patchen zonder cleanup.
    """
    origineel = dt_util.as_local
    dt_util.as_local = lambda value: (
        value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    ).astimezone(LOCAL)
    yield
    dt_util.as_local = origineel


def _config():
    return {
        CONF_WATER_ACTIVE_USAGE_SENSOR: "sensor.water_active",
        CONF_WATER_DAILY_TOTAL_SENSOR: "sensor.water_daily",
        CONF_WATER_TOTAL_USAGE_SENSOR: "sensor.water_total",
    }


class _FakeNewState:
    def __init__(self, state, last_changed):
        self.state = state
        self.last_changed = last_changed


class _FakeEvent:
    def __init__(self, new_state):
        self.data = {"new_state": new_state}


def _burst(coordinator, hass, start, flow, seconds, meter_step_m3=0.0):
    """Eén verbruiksstoot, live via de listener, gevolgd door de
    bevestigingsmarge. `meter_step_m3` bootst een grove meterstand na."""
    huidige = float(hass.states.get("sensor.water_total").state)
    coordinator._process_water_flow_sample(flow, start)
    einde = start + timedelta(seconds=seconds)
    hass.states.set("sensor.water_total", f"{huidige + meter_step_m3:.3f}")
    coordinator._process_water_flow_sample(0.0, einde)
    coordinator._process_water_flow_sample(0.0, einde + timedelta(minutes=3))
    return einde + timedelta(minutes=3)


# --- Oorzaak 1: meterstand-resolutie -------------------------------


def test_short_burst_gets_real_litres_despite_a_coarse_meter(
    make_coordinator, hass
):
    """De kern: een korte stoot moet echte liters opleveren, ook als de
    meterstand geen stap maakt."""
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")

    # 6 L/min gedurende 60 seconden = 6 liter. Meterstand beweegt NIET
    # (resolutie 10 L), precies zoals in de praktijk.
    _burst(coordinator, hass, DAY0, flow=6.0, seconds=60, meter_step_m3=0.0)

    sessie = coordinator.water_session_history[-1]
    assert sessie["liter"] == 6.0
    assert sessie["liter_uit_meterstand"] == 0.0


def test_many_small_bursts_add_up_to_the_daily_total(make_coordinator, hass):
    """Het gerapporteerde beeld: veel kleine stoten die samen het
    dagtotaal moeten verklaren in plaats van bijna nul."""
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")

    moment = DAY0
    for _ in range(12):
        moment = _burst(
            coordinator, hass, moment, flow=6.0, seconds=60, meter_step_m3=0.0
        )
        moment += timedelta(minutes=10)

    assert coordinator.water_sessions_today_count == 12
    assert coordinator.water_sessions_today_l == 72.0


def test_meter_reading_is_still_recorded_as_a_cross_check(
    make_coordinator, hass
):
    """De meterstand-methode verdwijnt niet - ze blijft naast het
    geïntegreerde debiet staan zodat afwijkingen zichtbaar zijn."""
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")

    _burst(coordinator, hass, DAY0, flow=6.0, seconds=60, meter_step_m3=0.010)

    sessie = coordinator.water_session_history[-1]
    assert sessie["liter"] == 6.0
    assert sessie["liter_uit_meterstand"] == 10.0


def test_a_long_gap_is_not_integrated(make_coordinator, hass):
    """Na een herstart mag een achtergebleven debiet niet urenlang
    worden doorgerekend."""
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")

    coordinator._process_water_flow_sample(6.0, DAY0)
    # Groot gat, ver voorbij MAX_HOUR_TRACKING_GAP_MINUTES.
    laat = DAY0 + timedelta(hours=5)
    coordinator._process_water_flow_sample(0.0, laat)
    coordinator._process_water_flow_sample(0.0, laat + timedelta(minutes=3))

    sessie = coordinator.water_session_history[-1]
    assert sessie["liter"] in (None, 0.0)


# --- Oorzaak 2: weergavevenster als rekenbasis ----------------------


def test_day_counter_is_not_capped_by_the_display_history(
    make_coordinator, hass
):
    """Meer momenten dan de weergavelijst lang is: de dagteller moet
    ze allemaal meenemen."""
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")

    aantal = WATER_SESSION_HISTORY_LENGTH + 15
    moment = DAY0
    for _ in range(aantal):
        moment = _burst(
            coordinator, hass, moment, flow=6.0, seconds=60, meter_step_m3=0.0
        )
        moment += timedelta(minutes=6)

    assert len(coordinator.water_session_history) == WATER_SESSION_HISTORY_LENGTH
    assert coordinator.water_sessions_today_count == aantal
    assert coordinator.water_sessions_today_l == aantal * 6.0


def test_day_counter_resets_on_a_new_day(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")

    _burst(coordinator, hass, DAY0, flow=6.0, seconds=60)
    assert coordinator.water_sessions_today_l == 6.0

    _burst(coordinator, hass, DAY0 + timedelta(days=1), flow=6.0, seconds=30)

    assert coordinator.water_sessions_today_count == 1
    assert coordinator.water_sessions_today_l == 3.0


# --- Oorzaak 3: tijdzone -------------------------------------------


def test_listener_timestamp_is_converted_to_local_time(make_coordinator, hass):
    """Een moment om 01:15 lokaal (23:15 UTC de dag ervoor) moet de
    LOKALE datum krijgen, anders telt het niet mee voor vandaag."""
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")

    utc_start = datetime(2026, 8, 5, 23, 15, tzinfo=timezone.utc)
    coordinator._handle_water_flow_change(_FakeEvent(_FakeNewState("6.0", utc_start)))
    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("0.0", utc_start + timedelta(minutes=1)))
    )
    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("0.0", utc_start + timedelta(minutes=4)))
    )

    sessie = coordinator.water_session_history[-1]
    # De opgeslagen tijd moet lokaal zijn, niet UTC.
    assert sessie["gestart"].startswith("2026-08-06T01:15")


def test_morning_shower_is_not_mistaken_for_the_water_softener(
    make_coordinator, hass
):
    """07:30 lokaal is 05:30 UTC - viel voorheen binnen het
    nachtvenster (0-6 uur) en werd onterecht als regeneratie
    aangemerkt."""
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")

    utc_start = datetime(2026, 8, 6, 5, 30, tzinfo=timezone.utc)  # 07:30 lokaal
    coordinator._handle_water_flow_change(_FakeEvent(_FakeNewState("8.0", utc_start)))
    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("0.0", utc_start + timedelta(minutes=5)))
    )
    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("0.0", utc_start + timedelta(minutes=8)))
    )

    sessie = coordinator.water_session_history[-1]
    assert sessie["waarschijnlijk_waterontharder"] is False


def test_night_regeneration_is_still_recognised(make_coordinator, hass):
    """01:15 lokaal (23:15 UTC) moet juist WEL als regeneratie tellen -
    voorheen viel dit er buiten.

    v1.18.0: de drempel is van 10 naar 40 liter EN 15 minuten gegaan.
    Deze opstelling gebruikte 6 L/min gedurende 2 minuten - twaalf liter
    in een paar minuten, wat eerder een bad of een kraan is dan een
    regeneratie. Nu een realistische spoeling: ruim een half uur, tegen
    de 100 liter.
    """
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")

    utc_start = datetime(2026, 8, 5, 23, 15, tzinfo=timezone.utc)
    coordinator._handle_water_flow_change(_FakeEvent(_FakeNewState("3.0", utc_start)))
    # De meterstand moet meelopen, anders is het volume nul en telt
    # alleen de duur - een regeneratie vraagt allebei.
    hass.states.set("sensor.water_total", "10.100")
    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("0.0", utc_start + timedelta(minutes=35)))
    )
    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("0.0", utc_start + timedelta(minutes=38)))
    )

    sessie = coordinator.water_session_history[-1]
    assert sessie["waarschijnlijk_waterontharder"] is True
    assert coordinator.water_softener_last_regeneration is not None


# --- End-to-end: het aandachtspunt zelf -----------------------------


def test_attention_point_disappears_once_sessions_explain_the_total(
    make_coordinator, hass
):
    """De melding moet verdwijnen zodra de momenten het dagtotaal wél
    verklaren - dat is waar dit hele onderzoek om begon."""
    coordinator = make_coordinator(_config())
    hass.states.set("sensor.water_total", "10.000")
    hass.states.set("sensor.water_daily", "85.0")
    coordinator.water_daily_total_l = 85.0

    moment = dt_now = __import__("homeassistant.util.dt", fromlist=["dt"]).now()
    for _ in range(14):
        moment = _burst(
            coordinator, hass, moment, flow=6.0, seconds=60, meter_step_m3=0.0
        )
        moment += timedelta(minutes=6)

    punten = coordinator.get_diagnostic_summary()["aandachtspunten"]
    assert not any("Waterverbruik" in p for p in punten)
    assert dt_now is not None


# --- v0.63.132: dagteller overleeft een herstart -------------------


def test_day_counter_is_rebuilt_from_restored_history(make_coordinator, hass):
    """In een diagnostiek-export stonden zes momenten van vandaag in de
    geschiedenis terwijl `water_sessions_today_count` op 0 stond: de
    teller is een gewoon geheugenveld en wordt bij elke herstart nul,
    terwijl de geschiedenis wél wordt hersteld. De check viel daardoor
    terug op de optelling over de weergavelijst - precies wat die teller
    moest vervangen.
    """
    coordinator = make_coordinator(_config())
    vandaag = dt_util.now().date().isoformat()
    coordinator.water_session_history = [
        {"gestart": f"{vandaag}T08:00:00+02:00", "liter": 12.2},
        {"gestart": f"{vandaag}T09:00:00+02:00", "liter": 9.6},
        {"gestart": f"{vandaag}T12:00:00+02:00", "liter": 0.5},
    ]

    coordinator.rebuild_water_session_day_counter()

    assert coordinator.water_sessions_today_count == 3
    assert coordinator.water_sessions_today_l == 22.3


def test_rebuild_ignores_other_days(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    vandaag = dt_util.now().date()
    gisteren = (vandaag - timedelta(days=1)).isoformat()
    coordinator.water_session_history = [
        {"gestart": f"{gisteren}T22:00:00+02:00", "liter": 40.0},
        {"gestart": f"{vandaag.isoformat()}T09:00:00+02:00", "liter": 5.0},
    ]

    coordinator.rebuild_water_session_day_counter()

    assert coordinator.water_sessions_today_count == 1
    assert coordinator.water_sessions_today_l == 5.0


def test_rebuild_leaves_an_empty_day_alone(make_coordinator, hass):
    """Zonder momenten van vandaag mag de dagsleutel niet op vandaag
    worden gezet - anders zou een lege teller de terugval op de
    geschiedenis blokkeren."""
    coordinator = make_coordinator(_config())
    coordinator.water_session_history = []

    coordinator.rebuild_water_session_day_counter()

    assert coordinator._water_sessions_day_key is None


def test_sensor_triggers_the_rebuild_on_restore():
    """De herbouw moet ook echt aangeroepen worden waar de geschiedenis
    wordt teruggezet."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()
    herstel = bron.index("water_session_history = list(reversed(raw_sessions))")
    vervolg = bron[herstel : herstel + 600]

    assert "rebuild_water_session_day_counter" in vervolg
