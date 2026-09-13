"""Drift accepteren als nieuw normaal (v1.1.7).

Gevraagd: "1 apparaat/apparaten mogelijk defect: Koelkast schuur
Vermogen. Hoe kan dit als acceptabel worden gezien?"

Er was geen nette uitweg. De drift-detectie herstelt zichzelf alleen als
het verbruik vijf dagen op rij TERUGKEERT naar het oude niveau. Doet het
dat niet - omdat het apparaat werkelijk meer is gaan gebruiken, of omdat
het zomer is en een koelkast dan harder werkt - dan blijft de melding
weken staan tot de mediaan van de geschiedenis vanzelf is meegekropen.

De alternatieven waren bot: `unconfirm_nilm_device` wist de hele
leergeschiedenis en `reject_nilm_device` haalt het apparaat er helemaal
uit. Beide gooien maanden aan kennis weg voor iets wat eigenlijk "ja,
dit klopt" is.
"""
from custom_components.energy_management_system.const import (
    CUSUM_MIN_HISTORY_FOR_REFERENCE,
)


def _apparaat_met_alarm(c, entity_id="sensor.koelkast_schuur_vermogen"):
    c.nilm_confirmed_devices[entity_id] = {
        "friendly_name": "Koelkast schuur Vermogen",
        # Eerst een lang, laag verleden, daarna structureel hoger.
        "daily_avg_history": [8.0] * 20 + [14.0] * 7,
        "reference_avg_w": 8.3,
        "cusum_accumulator": 42.0,
        "anomaly_detected": True,
        "estimated_drift_percent": 68.0,
        "_normal_streak_days": 0,
    }
    return entity_id


def test_the_alarm_clears(make_coordinator, hass):
    c = make_coordinator({})
    eid = _apparaat_met_alarm(c)

    assert c.accept_nilm_device_drift(eid) is True
    assert c.nilm_confirmed_devices[eid]["anomaly_detected"] is False
    assert c.nilm_confirmed_devices[eid]["cusum_accumulator"] == 0.0
    assert c.nilm_confirmed_devices[eid]["estimated_drift_percent"] is None


def test_the_device_stays_confirmed(make_coordinator, hass):
    """Anders dan afwijzen: het apparaat blijft gewoon gevolgd."""
    c = make_coordinator({})
    eid = _apparaat_met_alarm(c)

    c.accept_nilm_device_drift(eid)

    assert eid in c.nilm_confirmed_devices
    assert eid not in c.nilm_rejected_entities


def test_the_history_is_re_anchored_on_the_recent_level(make_coordinator, hass):
    """De kern: de oude, lage dagen verdwijnen zodat de mediaan meteen
    het nieuwe normaal weerspiegelt in plaats van er dertig dagen over te
    doen."""
    c = make_coordinator({})
    eid = _apparaat_met_alarm(c)

    c.accept_nilm_device_drift(eid)

    geschiedenis = c.nilm_confirmed_devices[eid]["daily_avg_history"]
    assert len(geschiedenis) == CUSUM_MIN_HISTORY_FOR_REFERENCE
    # De oude 8,0-dagen mogen de nieuwe referentie niet meer omlaag
    # trekken; het zwaartepunt ligt nu op het recente niveau.
    assert sum(geschiedenis) / len(geschiedenis) > 10.0


def test_the_history_is_not_wiped(make_coordinator, hass):
    """Alles wissen zou tien dagen lang geen referentie opleveren - en in
    die periode kon een échte verslechtering ongemerkt blijven. Dat is
    precies waarom dit geen `unconfirm` is."""
    c = make_coordinator({})
    eid = _apparaat_met_alarm(c)

    c.accept_nilm_device_drift(eid)

    assert len(c.nilm_confirmed_devices[eid]["daily_avg_history"]) >= (
        CUSUM_MIN_HISTORY_FOR_REFERENCE
    )


def test_it_records_when_it_was_accepted(make_coordinator, hass):
    c = make_coordinator({})
    eid = _apparaat_met_alarm(c)

    c.accept_nilm_device_drift(eid)

    assert c.nilm_confirmed_devices[eid]["drift_accepted_at"]


def test_a_new_alarm_can_still_fire_afterwards(make_coordinator, hass):
    """Accepteren mag het apparaat niet doof maken: gaat het verbruik
    daarna nóg verder omhoog, dan hoort dat weer op te vallen."""
    c = make_coordinator({})
    eid = _apparaat_met_alarm(c)
    c.accept_nilm_device_drift(eid)

    device = c.nilm_confirmed_devices[eid]
    # Een flinke verdere stijging, ver boven het nieuwe niveau.
    # `_finalize_nilm_device_day` voegt de dagwaarde zelf toe.
    for _ in range(8):
        c._finalize_nilm_device_day(eid, device, 60.0)

    assert device["anomaly_detected"] is True


def test_an_unknown_device_returns_false(make_coordinator, hass):
    c = make_coordinator({})

    assert c.accept_nilm_device_drift("sensor.bestaat_niet") is False


def test_the_attention_point_explains_the_way_out():
    """De melding zei wél wat er aan de hand was, maar niet wat je ermee
    kunt - waardoor de enige zichtbare uitwegen buiten proportie waren."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("apparaat/apparaten mogelijk ")
    blok = bron[start : start + 700]

    assert "accept_nilm_device_drift" in blok


def test_the_service_is_registered_and_documented():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    map_ = Path(pkg.__file__).parent
    assert "accept_nilm_device_drift" in (map_ / "__init__.py").read_text()
    diensten = yaml.safe_load((map_ / "services.yaml").read_text())
    assert "accept_nilm_device_drift" in diensten
