"""NILM-keuzes overleven een herstart niet (v0.63.115).

Gerapporteerd, ná de knop-race-fix van v0.63.107: "Keuzes voor NILM
apparaten worden nog steeds niet opgeslagen, de onbevestigde lijst
blijft terug komen na een herstart."

Root cause (los van v0.63.107): in `async_setup_entry` werden de
platforms opgezet VOORDAT de NILM-Store van schijf werd gelezen.
Daardoor draaide `NilmConfirmedDevicesSensor.async_added_to_hass`
altijd met lege lijsten in het geheugen. Die methode gebruikte "leeg"
als bewijs dat de Store leeg was, viel dus bij ELKE herstart terug op
het eenmalig-bedoelde migratiepad vanuit de eigen herstelde
entiteit-state - en die attributen zijn met opzet afgekapt op
NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT (20). Daarna schreef ze dat
afgekapte resultaat onvoorwaardelijk terug naar de Store en
overschreef zo de volledige inhoud.

Netto per herstart: bevestigde apparaten hard afgekapt op 20, afgewezen
entiteiten óók op 20 - alles daarboven kwam terug als onbevestigde
kandidaat.
"""
import asyncio
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT,
)
from custom_components.energy_management_system.sensor import (
    NilmConfirmedDevicesSensor,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
STORE_KEY = "energy_management_system_nilm_confirmed_devices"


class _FakeLastState:
    """Herstelde entiteit-state met exact de attributen die de sensor
    zelf publiceert - dus AFGEKAPT, zoals in werkelijkheid."""

    def __init__(self, attributes):
        self.attributes = attributes


def _device(i):
    return {
        "friendly_name": f"Apparaat {i:03d}",
        "confirmed_at": "2026-06-01",
        "daily_avg_history": [10.0] * 30,
        "cusum_accumulator": 0.0,
        "anomaly_detected": False,
        "estimated_drift_percent": None,
        "reference_avg_w": 10.0,
        "_today_sum": 0.0,
        "_today_count": 0,
        "_check_date": None,
    }


def _seed_store(hass, device_count, rejected_count):
    """Zet een volle, gezonde Store op schijf neer - zoals na een
    sessie waarin de gebruiker veel apparaten heeft beoordeeld."""
    if not hasattr(hass, "_fake_store_backing"):
        hass._fake_store_backing = {}
    hass._fake_store_backing[STORE_KEY] = {
        "nilm_confirmed_devices": {
            f"sensor.apparaat_{i:03d}": _device(i) for i in range(device_count)
        },
        "nilm_rejected_entities": [
            f"sensor.genegeerd_{i:03d}" for i in range(rejected_count)
        ],
    }


def _simulate_restart(coordinator, sensor):
    """Bootst de ECHTE productievolgorde na zoals die na deze fix is:
    Store laden -> platforms opzetten (async_added_to_hass)."""

    async def run():
        await coordinator.async_load_persisted_nilm_state()
        await sensor.async_added_to_hass()

    asyncio.run(run())


def _attach_last_state(coordinator, sensor):
    """Hangt een herstelde state aan de sensor die precies is wat die
    sensor zelf zou hebben weggeschreven: afgekapt op 20."""
    attrs = sensor.extra_state_attributes
    last_state = _FakeLastState(
        {
            "apparaten": dict(attrs["apparaten"]),
            "rejected_entities": list(attrs["rejected_entities"]),
        }
    )

    async def get_last_state():
        return last_state

    sensor.async_get_last_state = get_last_state
    return last_state


def test_confirmed_devices_survive_a_restart_beyond_the_preview_limit(
    make_coordinator, hass
):
    """De kern van de klacht: 60 bevestigde apparaten mogen na een
    herstart geen 20 worden."""
    total = NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 40
    _seed_store(hass, device_count=total, rejected_count=0)

    coordinator = make_coordinator({})
    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")
    _attach_last_state(coordinator, sensor)

    _simulate_restart(coordinator, sensor)

    assert len(coordinator.nilm_confirmed_devices) == total
    assert len(hass._fake_store_backing[STORE_KEY]["nilm_confirmed_devices"]) == total


def test_rejected_entities_survive_a_restart_beyond_the_preview_limit(
    make_coordinator, hass
):
    """Afgewezen entiteiten die de afkap-grens overschrijden kwamen
    terug als onbevestigde kandidaat - precies wat de gebruiker zag."""
    total = NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 35
    _seed_store(hass, device_count=0, rejected_count=total)

    coordinator = make_coordinator({})
    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")
    _attach_last_state(coordinator, sensor)

    _simulate_restart(coordinator, sensor)

    assert len(coordinator.nilm_rejected_entities) == total


def test_rejected_entity_does_not_reappear_as_candidate_after_restart(
    make_coordinator, hass
):
    """End-to-end: een afgewezen entiteit die ver voorbij de afkap-grens
    staat mag na een herstart niet opnieuw als kandidaat opduiken."""
    rejected = [
        f"sensor.genegeerd_{i:03d}"
        for i in range(NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 10)
    ]
    if not hasattr(hass, "_fake_store_backing"):
        hass._fake_store_backing = {}
    hass._fake_store_backing[STORE_KEY] = {
        "nilm_confirmed_devices": {},
        "nilm_rejected_entities": rejected,
    }
    laatste = rejected[-1]
    hass.states.set(
        laatste, "12", {"unit_of_measurement": "W", "friendly_name": "Genegeerd apparaat"}
    )

    coordinator = make_coordinator({})
    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")
    _attach_last_state(coordinator, sensor)

    _simulate_restart(coordinator, sensor)
    coordinator._update_nilm_discovery(NOW)

    assert laatste not in coordinator.nilm_unconfirmed_candidates


def test_populated_store_is_never_overwritten_by_the_restored_state(
    make_coordinator, hass
):
    """De schrijfactie zelf was het schadelijke deel: een gevulde Store
    mag niet worden overschreven met de afgekapte entiteit-state."""
    _seed_store(hass, device_count=NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 5, rejected_count=3)
    before = {
        k: dict(v)
        for k, v in hass._fake_store_backing[STORE_KEY][
            "nilm_confirmed_devices"
        ].items()
    }

    coordinator = make_coordinator({})
    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")
    _attach_last_state(coordinator, sensor)

    _simulate_restart(coordinator, sensor)

    assert hass._fake_store_backing[STORE_KEY]["nilm_confirmed_devices"] == before


def test_learned_cusum_history_is_not_lost_for_devices_past_the_limit(
    make_coordinator, hass
):
    """De weggevallen apparaten namen hun maandenlange geleerde
    CUSUM-geschiedenis mee - dat is de duurste vorm van dataverlies
    hier."""
    total = NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 15
    _seed_store(hass, device_count=total, rejected_count=0)

    coordinator = make_coordinator({})
    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")
    _attach_last_state(coordinator, sensor)

    _simulate_restart(coordinator, sensor)

    laatste = f"sensor.apparaat_{total - 1:03d}"
    assert laatste in coordinator.nilm_confirmed_devices
    assert len(coordinator.nilm_confirmed_devices[laatste]["daily_avg_history"]) == 30


def test_repeated_restarts_do_not_erode_the_lists(make_coordinator, hass):
    """Het probleem was progressief: elke herstart kapte opnieuw af.
    Vijf herstarts achter elkaar mogen niets wegnemen."""
    total = NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 25
    _seed_store(hass, device_count=total, rejected_count=total)

    for _ in range(5):
        coordinator = make_coordinator({})
        sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")
        _attach_last_state(coordinator, sensor)
        _simulate_restart(coordinator, sensor)

    assert len(coordinator.nilm_confirmed_devices) == total
    assert len(coordinator.nilm_rejected_entities) == total


def test_genuine_first_time_migration_still_works(make_coordinator, hass):
    """Het migratiepad moet blijven werken voor een installatie die van
    vóór de Store komt: lege Store, wél een herstelde state."""

    class _OldState:
        attributes = {
            "apparaten": {"sensor.oud": {"friendly_name": "Oud apparaat"}},
            "rejected_entities": ["sensor.oud_genegeerd"],
        }

    coordinator = make_coordinator({})
    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")

    async def get_last_state():
        return _OldState()

    sensor.async_get_last_state = get_last_state
    _simulate_restart(coordinator, sensor)

    assert "sensor.oud" in coordinator.nilm_confirmed_devices
    assert "sensor.oud_genegeerd" in coordinator.nilm_rejected_entities
    stored = hass._fake_store_backing[STORE_KEY]
    assert "sensor.oud" in stored["nilm_confirmed_devices"]
    assert "sensor.oud_genegeerd" in stored["nilm_rejected_entities"]


def test_store_load_is_idempotent(make_coordinator, hass):
    """De load draait nu op twee plekken (vóór platform-setup en als
    vangnet in async_setup) - de tweede mag nooit over verser geheugen
    heen lezen."""
    _seed_store(hass, device_count=2, rejected_count=0)

    coordinator = make_coordinator({})

    async def run():
        await coordinator.async_load_persisted_nilm_state()
        # Gebruiker bevestigt daarna iets; dat mag een tweede load niet
        # wegvagen.
        coordinator.nilm_confirmed_devices["sensor.nieuw"] = {"friendly_name": "N"}
        await coordinator.async_load_persisted_nilm_state()

    asyncio.run(run())

    assert "sensor.nieuw" in coordinator.nilm_confirmed_devices
    assert len(coordinator.nilm_confirmed_devices) == 3


def test_nilm_store_had_data_flag_reflects_reality(make_coordinator, hass):
    """De vlag die het migratiepad nu stuurt moet kloppen - niet meer
    afgeleid uit 'de lijsten zijn leeg'."""
    coordinator_leeg = make_coordinator({})
    asyncio.run(coordinator_leeg.async_load_persisted_nilm_state())
    assert coordinator_leeg.nilm_store_had_data is False

    _seed_store(hass, device_count=1, rejected_count=0)
    coordinator_gevuld = make_coordinator({})
    asyncio.run(coordinator_gevuld.async_load_persisted_nilm_state())
    assert coordinator_gevuld.nilm_store_had_data is True


def test_rejected_list_only_ever_grows_during_migration(make_coordinator, hass):
    """Samenvoegen in plaats van vervangen: een afgekapte herstelde
    state mag nooit entries wégnemen."""
    coordinator = make_coordinator({})
    coordinator.nilm_rejected_entities = ["sensor.a", "sensor.b", "sensor.c"]

    class _PartialState:
        attributes = {"rejected_entities": ["sensor.b", "sensor.d"]}

    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")

    async def get_last_state():
        return _PartialState()

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert set(coordinator.nilm_rejected_entities) == {
        "sensor.a",
        "sensor.b",
        "sensor.c",
        "sensor.d",
    }


def test_setup_entry_loads_the_store_before_forwarding_platforms():
    """Structurele borging van de volgorde zelf (v0.63.115).

    De hele bug hing op één regel-volgorde in `async_setup_entry`. Een
    gedragstest kan die volgorde niet afdwingen (die bootst 'm juist
    na), dus wordt hier de bronvolgorde direct gecontroleerd - net als
    test_structural_integrity.py doet voor verplaatste methodes.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "__init__.py").read_text()
    load_pos = bron.index("async_load_persisted_nilm_state()")
    forward_pos = bron.index("async_forward_entry_setups(")

    assert load_pos < forward_pos, (
        "De NILM-Store moet geladen zijn VOORDAT de platforms worden "
        "opgezet - anders draait NilmConfirmedDevicesSensor."
        "async_added_to_hass met lege lijsten en kapt het migratiepad "
        "de opgeslagen data af op 20 items (v0.63.115)."
    )
