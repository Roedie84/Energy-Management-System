"""v5.136.0: NILM-kandidaten die al gevolgd, bevestigd of afgewezen zijn,
verdwijnen vanzelf uit de lijst (punt 16, akkoord 26-10).

Gemeld 26-10: de cockpit gaf "15 onbevestigde NILM-kandidaten". Daaronder
de Quooker (al ingesteld), de batterijlader (sinds v5.129.0 ingesteld) en
een houten lamp die al bevestigd was. De uitsluitingen golden alleen bij
het ontdekken.
"""
from datetime import datetime, timezone

DAY0 = datetime(2026, 10, 26, tzinfo=timezone.utc)


def _kandidaat(c, eid):
    c.nilm_unconfirmed_candidates[eid] = {"friendly_name": eid, "current_power_w": 1.0, "first_seen": "2026-10-07"}


def test_ingestelde_bevestigde_en_afgewezen_kandidaten_verdwijnen(make_coordinator, hass):
    c = make_coordinator({
        "quooker_power_sensor_entity": "sensor.quooker_active_power",
        "batterijlader_power_sensor_entity": "sensor.opladers_batterijen_power",
    })
    for eid in ("sensor.quooker_active_power", "sensor.opladers_batterijen_power",
                "sensor.houten_lamp", "sensor.oud_afgewezen", "sensor.echt_nieuw"):
        _kandidaat(c, eid)
    c.nilm_confirmed_devices["sensor.houten_lamp"] = {"friendly_name": "Houten lamp"}
    c.nilm_rejected_entities.append("sensor.oud_afgewezen")

    c._update_nilm_discovery(DAY0)

    assert set(c.nilm_unconfirmed_candidates) == {"sensor.echt_nieuw"}
    # het bevestigde apparaat blijft bevestigd
    assert "sensor.houten_lamp" in c.nilm_confirmed_devices


def test_nieuwe_kandidaat_wordt_nog_gewoon_gevonden(make_coordinator, hass):
    c = make_coordinator({})
    hass.states.set("sensor.nieuwe_stekker", "12", {"unit_of_measurement": "W", "friendly_name": "Nieuwe stekker"})
    c._update_nilm_discovery(DAY0)
    assert "sensor.nieuwe_stekker" in c.nilm_unconfirmed_candidates
