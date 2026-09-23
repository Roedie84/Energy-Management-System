"""Een apparaat dat uit staat, is geen weggevallen sensor (v5.15.1).

Uit de export van 23 september:

    08:31  sensor_unavailable | sensor.kookplaat_operation_state (Kookplaat
           status-sensor) geeft al minstens 15 minuten geen waarde.

De kookplaat stond uit. Home Connect meldt dan niets - dat is normaal, en
de configuratiecontrole noemt het sinds v3.95.0 ook zo: "slaapt", niet
kapot. Maar de MELDING gebruikt die kennis niet en stuurde een
waarschuwing. Twee oordelen over dezelfde toestand.

Zelfde soort als v5.14.6, waar de omvormer zonder zon nog als kapot
telde, en als v5.14.5 met de opstartfase: het verschil tussen "nu even
niet" en "kapot".

Wat WEL een melding blijft: een sensor die hoort te leveren. De
prijssensor, de P1-meter, de accu - die slapen niet.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 23, 8, 31, tzinfo=timezone.utc)


def _weg(c, entity_id, gebruikt_voor, sinds_minuten=30):
    c._sensor_unavailable_since = {entity_id: NU - timedelta(minutes=sinds_minuten)}
    c._invoer_gebruik = {entity_id: gebruikt_voor}
    c._invoer_instelling = {entity_id: "kookplaat_state_sensor_entity"}
    c.is_sensor_genuinely_unavailable = lambda now, eid: True
    return c


def test_een_apparaat_dat_uit_staat_geeft_geen_melding(make_coordinator, hass):
    """Het gemeten geval van 08:31."""
    c = _weg(make_coordinator({}), "sensor.kookplaat_operation_state", "Kookplaat status-sensor")

    assert c.weggevallen_invoer(NU) == []


def test_de_omvormer_zonder_zon_ook_niet(make_coordinator, hass):
    c = _weg(make_coordinator({}), "sensor.solaredge_production_energy", "PV-opbrengst")
    c._invoer_instelling = {"sensor.solaredge_production_energy": "pv_energy_sensor_entity"}
    c.get_sun_elevation_degrees = lambda: -5.0

    assert c.weggevallen_invoer(NU) == []


def test_overdag_meldt_de_omvormer_wel(make_coordinator, hass):
    c = _weg(make_coordinator({}), "sensor.solaredge_production_energy", "PV-opbrengst")
    c._invoer_instelling = {"sensor.solaredge_production_energy": "pv_energy_sensor_entity"}
    c.get_sun_elevation_degrees = lambda: 30.0

    assert len(c.weggevallen_invoer(NU)) == 1


def test_een_sensor_die_hoort_te_leveren_meldt_wel(make_coordinator, hass):
    """De prijssensor slaapt niet."""
    c = _weg(make_coordinator({}), "sensor.prijs", "Prijssensor")
    c._invoer_instelling = {"sensor.prijs": "price_sensor_entity"}

    assert len(c.weggevallen_invoer(NU)) == 1


def test_de_trage_gacs_keren_staan_in_de_export():
    """Mijn eigen gat uit v5.14.3: `gacs_traag` en `gacs_traagste` worden
    wel BEWAARD maar stonden niet in de export - dus juist de verdeling
    die ik nodig had, was niet te lezen. Hetzelfde gat dat v5.10 voor
    andere velden dichtte."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "get_gacs_traagheid" in bron


def test_een_onbekende_zonstand_is_geen_nacht(make_coordinator, hass):
    """Mijn eerste versie schreef `(zonhoogte or 0) <= 0`, en dan gold een
    ONBEKENDE zonstand als nacht - dus werd een echt weggevallen omvormer
    stilgehouden. Een bestaande toets ving dat. Onbekend is geen nacht."""
    c = _weg(make_coordinator({}), "sensor.solaredge_production_energy", "PV-opbrengst")
    c._invoer_instelling = {"sensor.solaredge_production_energy": "pv_energy_sensor_entity"}
    c.get_sun_elevation_degrees = lambda: None

    assert len(c.weggevallen_invoer(NU)) == 1


def test_de_configuratiecontrole_maakt_datzelfde_onderscheid(make_coordinator, hass):
    """Dezelfde fout zat in v5.14.6."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["pv_energy_sensor_entity"] = "sensor.pv"
    hass.states.set("sensor.pv", "unknown", {})
    c.get_sun_elevation_degrees = lambda: None

    regel = next(
        r for r in c.get_configuratiecontrole()["entiteiten"]
        if r["instelling"] == "pv_energy_sensor_entity"
    )

    assert regel["oordeel"] == "geen_waarde"
