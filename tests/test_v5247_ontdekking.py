"""v5.247.0 - nieuwe apparaten herkennen (Ruud 19-11).

Meten voegt het EMS zelf toe en meldt het; sturen vraagt het eerst; een
schakelaar wordt nooit vanzelf schakelbaar.
"""
from datetime import datetime
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import ontdekking as O

MODULE_1 = ["sensor.ab3000_01029_soc_level", "sensor.ab3000_01029_power", "sensor.ab3000_01029_max_temp",
            "sensor.ab3000_01029_max_vol", "sensor.ab3000_01029_min_vol"]
MODULE_2 = [e.replace("01029", "05555") for e in MODULE_1]
CONFIG = {
    "battery_module_soc_sensor_entities": [MODULE_1[0]],
    "battery_module_power_sensor_entities": [MODULE_1[1]],
    "battery_module_temperature_sensor_entities": [MODULE_1[2]],
    "battery_module_cell_voltage_max_sensor_entities": [MODULE_1[3]],
    "battery_module_cell_voltage_min_sensor_entities": [MODULE_1[4]],
    "airco_climate_entity": "climate.woonkamer",
}
NU = datetime(2026, 11, 19, 12, 30)


def _inv(*ids, **extra):
    return [{"entity_id": e, **extra} for e in ids]


def test_bekende_module_is_ingesteld_nieuwe_niet():
    m = {x["nummer"]: x for x in O.modules(MODULE_1 + MODULE_2, CONFIG)}
    assert m["01029"]["ingesteld"] is True and m["05555"]["ingesteld"] is False
    assert m["05555"]["volledig"] is True


def test_nieuwe_module_komt_achteraan_in_alle_vijf_lijsten():
    nieuw = [x for x in O.modules(MODULE_1 + MODULE_2, CONFIG) if not x["ingesteld"]]
    lijsten = O.instellingen_met_modules(CONFIG, nieuw)
    assert set(lijsten) == set(O.MODULE_INSTELLING.values())
    for sleutel, lijst in lijsten.items():
        assert len(lijst) == 2 and lijst[0] == CONFIG[sleutel][0] and "05555" in lijst[1]
    # twee keer toepassen verdubbelt niets
    assert O.instellingen_met_modules({**CONFIG, **lijsten}, nieuw) == lijsten


def test_onvolledige_module_wacht():
    uit = O.beoordeel(_inv(*MODULE_1, *MODULE_2[:2]), CONFIG, MODULE_1)
    [b] = uit["bevindingen"]
    assert b["actie"] == O.WACHT and "max_temp" in b["uitleg"]


def test_eerste_keer_geen_stortvloed_maar_wel_een_onbekende_module():
    inv = _inv(*MODULE_1, *MODULE_2) + _inv("climate.slaapkamer", "light.keuken")
    uit = O.beoordeel(inv, CONFIG, None)
    assert uit["eerste_keer"] is True
    assert [(b["soort"], b["actie"]) for b in uit["bevindingen"]] == [("accumodule", O.AUTOMATISCH)]
    assert "light.keuken" in uit["bekend"]


def test_nieuwe_airco_is_een_voorstel_en_wordt_niet_gestuurd():
    uit = O.beoordeel(_inv(*MODULE_1) + _inv("climate.woonkamer", "climate.zolder"), CONFIG, MODULE_1)
    [b] = uit["bevindingen"]
    assert b["soort"] == "airco of thermostaat" and b["actie"] == O.VOORSTEL and b["entiteiten"] == ["climate.zolder"]


def test_schakelaar_wordt_nooit_vanzelf_schakelbaar():
    soort, actie, uitleg = O.soort_van({"entity_id": "switch.vriezer_schuur"})
    assert actie == O.GEMELD and "nooit vanzelf schakelbaar" in uitleg
    bron = (Path(pkg.__file__).parent / "ontdekking.py").read_text(encoding="utf-8")
    for verboden in ("turn_on", "turn_off", "async_call", "switch_entity"):
        assert verboden not in bron, verboden


def test_lamp_meting_en_sensoren():
    assert O.soort_van({"entity_id": "light.nieuw"})[1] == O.GEMELD
    assert O.soort_van({"entity_id": "sensor.stekker_vermogen", "device_class": "power"})[0] == "vermogensmeting"
    assert O.soort_van({"entity_id": "binary_sensor.raam", "device_class": "window"})[1] == O.VOORSTEL
    assert O.soort_van({"entity_id": "binary_sensor.pir", "device_class": "motion"})[1] == O.VOORSTEL
    # eigen entiteiten van het EMS en losse tekstsensoren tellen niet
    assert O.soort_van({"entity_id": "sensor.x", "device_class": "power", "platform": "energy_management_system"}) is None
    assert O.soort_van({"entity_id": "sensor.iets", "device_class": None}) is None


def test_entiteiten_van_een_apparaat_worden_een_regel():
    inv = [{"entity_id": "sensor.stekker_vermogen", "device_class": "power", "apparaat": "Stekker kantoor"},
           {"entity_id": "sensor.stekker_piek", "device_class": "power", "apparaat": "Stekker kantoor"},
           {"entity_id": "switch.stekker", "apparaat": "Stekker kantoor"}]
    uit = O.beoordeel(inv, {}, [])
    assert sorted((b["soort"], len(b["entiteiten"])) for b in uit["bevindingen"]) == [
        ("schakelaar of stekker", 1), ("vermogensmeting", 2)]


def test_logboek_meldt_hetzelfde_niet_twee_keer():
    b = [{"soort": "lamp", "naam": "Lamp hal", "actie": O.GEMELD, "uitleg": "x", "entiteiten": ["light.hal"]}]
    log = O.log_bij([], b, "t1")
    assert len(O.log_bij(log, b, "t2")) == 1
    assert "Lamp hal" in O.bericht(log)


def _coordinator(make_coordinator, inventaris, config=None):
    c = make_coordinator(dict(config or CONFIG))
    c._ontdekking_inventaris = lambda: inventaris
    c._opstart_stuurstil = lambda: False
    c.meldingen = []
    c._dispatch_notification = lambda **kw: c.meldingen.append(kw)
    return c


def test_ronde_voegt_een_nieuwe_module_toe_en_meldt_hem(make_coordinator, hass):
    c = _coordinator(make_coordinator, _inv(*MODULE_1, *MODULE_2))
    toegepast = []
    c._ontdekking_pas_modules_toe = lambda nieuwe: toegepast.append(nieuwe) or True
    c._update_ontdekking(NU)
    assert len(toegepast) == 1 and toegepast[0][0]["nummer"] == "05555"
    assert len(c.meldingen) == 1 and "AB3000 05555" in c.meldingen[0]["message"]
    assert c.meldingen[0]["kind"] == "ontdekking"
    o = c.get_ontdekking()
    assert o["gevonden"] == 1 and o["laatste"][0]["actie"] == O.AUTOMATISCH
    # binnen tien minuten niet opnieuw, en daarna niet nog eens melden
    c._update_ontdekking(NU)
    c._ontdekking_laatst = None
    c._update_ontdekking(NU)
    assert len(c.meldingen) == 1


def test_lukt_toevoegen_niet_dan_wordt_het_een_voorstel(make_coordinator, hass):
    c = _coordinator(make_coordinator, _inv(*MODULE_1, *MODULE_2))
    c._ontdekking_pas_modules_toe = lambda nieuwe: False
    c._update_ontdekking(NU)
    assert c.get_ontdekking()["wacht_op_akkoord"][0]["naam"] == "AB3000 05555"


def test_leermodus_past_niets_toe(make_coordinator, hass):
    c = _coordinator(make_coordinator, _inv(*MODULE_1, *MODULE_2))
    c.learning_only = True
    aangeroepen = []
    c._ontdekking_pas_modules_toe = lambda nieuwe: aangeroepen.append(1) or True
    c._update_ontdekking(NU)
    assert aangeroepen == []


def test_tweede_ronde_ziet_een_nieuwe_airco(make_coordinator, hass):
    inv = _inv(*MODULE_1) + _inv("climate.woonkamer")
    c = _coordinator(make_coordinator, inv)
    c._update_ontdekking(NU)
    assert c.meldingen == [] and c.ontdekking_bekend
    inv.append({"entity_id": "climate.zolder", "apparaat": "Airco zolder"})
    c._ontdekking_laatst = None
    c._update_ontdekking(NU)
    assert len(c.meldingen) == 1 and "Airco zolder" in c.meldingen[0]["message"]
    assert c.get_ontdekking()["wacht_op_akkoord"][0]["soort"] == "airco of thermostaat"


def test_onleesbaar_home_assistant_breekt_de_ronde_niet(make_coordinator, hass):
    c = _coordinator(make_coordinator, [])

    def stuk():
        raise RuntimeError("geen register")
    c._ontdekking_inventaris = stuk
    c._update_ontdekking(NU)
    assert c.meldingen == [] and c.ontdekking_bekend is None
