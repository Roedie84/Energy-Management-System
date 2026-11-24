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


# --- v5.248.0: omvormer, accu, laadpaal en verdwenen apparaten -------------


def test_laadpaal_omvormer_en_accu_zijn_een_voorstel():
    assert O.soort_van({"entity_id": "switch.easee_lader", "platform": "easee"}) [:2] == ("laadpaal", O.VOORSTEL)
    assert O.soort_van({"entity_id": "sensor.pv2_vermogen", "platform": "goodwe", "device_class": "power"})[:2] == (
        "omvormer of zonnepanelen", O.VOORSTEL)
    assert O.soort_van({"entity_id": "sensor.accu2_soc", "platform": "marstek", "device_class": "battery"})[:2] == (
        "thuisaccu", O.VOORSTEL)


def test_batterij_van_een_deurcontact_is_geen_thuisaccu():
    assert O.soort_van({"entity_id": "sensor.deur_batterij", "platform": "mqtt", "device_class": "battery"}) is None
    # en een gewone meetstekker blijft een vermogensmeting
    assert O.soort_van({"entity_id": "sensor.stekker_w", "platform": "homewizard", "device_class": "power"})[0] == "vermogensmeting"


def test_ingestelde_entiteiten_uit_tekst_en_lijsten():
    config = {"airco_climate_entity": "climate.woonkamer", "lijst": ["sensor.a", "sensor.b"], "getal": 21.0,
              "tijd": "22:00", "datum": "2026-12-31", "dienst": "notify.mobile_app_iphone", "leeg": None}
    assert O.ingestelde_entiteiten(config) == {
        "climate.woonkamer": "airco_climate_entity", "sensor.a": "lijst", "sensor.b": "lijst"}


def test_verdwenen_pas_na_drie_rondes_en_een_keer():
    config = {"x": "sensor.weg", "y": "sensor.blijft"}
    tellers = None
    gemeld = []
    for _ in range(5):
        b, tellers = O.verdwenen(config, ["sensor.blijft"], tellers)
        gemeld += b
    assert [g["naam"] for g in gemeld] == ["sensor.weg"] and "'x'" in gemeld[0]["uitleg"]
    # komt hij terug, dan begint het tellen opnieuw
    _, tellers = O.verdwenen(config, ["sensor.blijft", "sensor.weg"], tellers)
    assert tellers == {}


def test_ronde_meldt_een_verdwenen_ingesteld_apparaat(make_coordinator, hass):
    config = {**CONFIG, "slaapkamer_climate_entity": "climate.slaapkamer"}
    c = _coordinator(make_coordinator, _inv(*MODULE_1) + _inv("climate.woonkamer"), config)
    for _ in range(O.VERDWENEN_RONDES):
        c._ontdekking_laatst = None
        c._update_ontdekking(NU)
    assert len(c.meldingen) == 1 and "climate.slaapkamer" in c.meldingen[0]["message"]
    assert c.get_ontdekking()["laatste"][-1]["soort"] == "verdwenen"


def test_nieuwe_sensor_van_de_bestaande_accu_is_geen_tweede_accu():
    inv = [{"entity_id": "sensor.solarflow_soc", "platform": "zendure_ha", "device_class": "battery", "apparaat": "SolarFlow 2400 AC"},
           {"entity_id": "sensor.solarflow_nieuw", "platform": "zendure_ha", "device_class": "power", "apparaat": "SolarFlow 2400 AC"},
           {"entity_id": "sensor.tweede_soc", "platform": "zendure_ha", "device_class": "battery", "apparaat": "SolarFlow 800"}]
    uit = O.beoordeel(inv, {}, ["sensor.solarflow_soc"])
    assert [(b["soort"], b["naam"]) for b in uit["bevindingen"]] == [("thuisaccu", "SolarFlow 800")]


def test_cockpit_krijgt_een_korte_lijst(make_coordinator, hass):
    c = _coordinator(make_coordinator, _inv(*MODULE_1) + _inv("climate.woonkamer"))
    c._update_ontdekking(NU)
    assert c.get_ontdekking_kort() == {"wacht_op_akkoord": [], "recent": []}
    from homeassistant.util import dt as dt_util
    c.ontdekking_log = [{"moment": dt_util.now().isoformat(), "soort": "airco of thermostaat", "naam": "Airco zolder",
                         "actie": O.VOORSTEL, "uitleg": "x", "entiteiten": ["climate.zolder"]},
                        {"moment": "2026-01-01T00:00:00", "soort": "lamp", "naam": "Oud", "actie": O.GEMELD}]
    kort = c.get_ontdekking_kort()
    assert kort["wacht_op_akkoord"] == [{"naam": "Airco zolder", "soort": "airco of thermostaat", "actie": O.VOORSTEL}]
    assert [r["naam"] for r in kort["recent"]] == ["Airco zolder"]


def test_cockpit_toont_nieuw_gevonden():
    js = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert 'this._gacs("nieuw_gevonden")' in js and '"Nieuw gevonden"' in js
    js.encode("ascii")
    from custom_components.energy_management_system import sensor
    assert "nieuw_gevonden" in sensor.GACS_DASHBOARD_SLEUTELS


# --- v5.249.0: knoppen in de melding ---------------------------------------


def _log_met(soort, entiteiten, naam="Sensor gang"):
    return O.log_bij([], [{"soort": soort, "naam": naam, "actie": O.VOORSTEL, "uitleg": "x", "entiteiten": entiteiten}], "t")


def test_knoppen_per_soort():
    beweging = _log_met("bewegingssensor", ["binary_sensor.pir_gang"])[0]
    raam = _log_met("deur- of raamsensor", ["binary_sensor.raam_bad"])[0]
    airco = _log_met("airco of thermostaat", ["climate.zolder"])[0]
    assert [k["title"] for k in O.knoppen(beweging)] == ["Telt mee voor aanwezigheid", "Nee"]
    assert [k["title"] for k in O.knoppen(raam)] == ["Telt mee voor aanwezigheid", "Raam bij de airco", "Nee"]
    assert O.knoppen(airco) == []          # airco, omvormer, accu en laadpaal: geen knop
    assert O.knoppen(_log_met("laadpaal", ["switch.lader"])[0]) == []
    assert O.lees_actie(O.knoppen(raam)[1]["action"]) == (1, "raam")
    assert O.lees_actie("IETS_ANDERS") is None and O.lees_actie("EMS_ONTDEKKING_1_wissen") is None


def test_ja_zet_de_sensor_in_de_juiste_lijst():
    log = _log_met("deur- of raamsensor", ["binary_sensor.raam_bad", "sensor.raam_bad_batterij"])
    config = {"airco_raam_entities": ["binary_sensor.raam_wk"], "presence_motion_sensor_entities": ["binary_sensor.pir"]}
    uit = O.verwerk_antwoord(log, config, 1, "raam")
    assert uit["gedaan"] and uit["instelling"] == {"airco_raam_entities": ["binary_sensor.raam_wk", "binary_sensor.raam_bad"]}
    assert uit["log"][0]["actie"] == "ingesteld: raam bij de airco"
    # de tweede tik doet niets meer
    assert O.verwerk_antwoord(uit["log"], config, 1, "aanwezig")["gedaan"] is False


def test_nee_wijst_af_en_verandert_niets():
    uit = O.verwerk_antwoord(_log_met("bewegingssensor", ["binary_sensor.pir_gang"]), {}, 1, "nee")
    assert uit["gedaan"] and uit["instelling"] == {} and uit["log"][0]["actie"] == O.AFGEWEZEN


def test_verkeerde_keuze_of_onbekend_nummer_doet_niets():
    log = _log_met("bewegingssensor", ["binary_sensor.pir_gang"])
    assert O.verwerk_antwoord(log, {}, 1, "raam")["gedaan"] is False        # 'raam' hoort niet bij beweging
    assert O.verwerk_antwoord(log, {}, 9, "aanwezig")["gedaan"] is False
    # een airco kan nooit via een knop worden ingesteld
    assert O.verwerk_antwoord(_log_met("airco of thermostaat", ["climate.zolder"]), {}, 1, "aanwezig")["gedaan"] is False


def test_antwoord_op_de_coordinator(make_coordinator, hass):
    c = _coordinator(make_coordinator, [], {"presence_motion_sensor_entities": ["binary_sensor.pir"]})
    c.ontdekking_log = _log_met("bewegingssensor", ["binary_sensor.pir_gang"])
    geschreven, verstuurd = [], []
    c._ontdekking_zet_instelling = lambda lijsten: geschreven.append(lijsten) or True
    c._ontdekking_stuur = lambda titel, bericht, knoppen=None, tag="": verstuurd.append((titel, bericht))
    assert c.ontdekking_antwoord("iets van een andere app") is None
    uit = c.ontdekking_antwoord("EMS_ONTDEKKING_1_aanwezig")
    assert uit["gedaan"] and geschreven == [{"presence_motion_sensor_entities": ["binary_sensor.pir", "binary_sensor.pir_gang"]}]
    assert verstuurd and verstuurd[0][0] == "EMS: ingesteld"
    assert c.get_ontdekking()["wacht_op_akkoord"] == []
    # nog een keer tikken schrijft niet opnieuw
    c.ontdekking_antwoord("EMS_ONTDEKKING_1_aanwezig")
    assert len(geschreven) == 1


def test_leermodus_schrijft_niets_na_een_tik(make_coordinator, hass):
    c = _coordinator(make_coordinator, [], {})
    c.ontdekking_log = _log_met("bewegingssensor", ["binary_sensor.pir_gang"])
    c.learning_only = True
    geschreven = []
    c._ontdekking_zet_instelling = lambda lijsten: geschreven.append(lijsten) or True
    assert c.ontdekking_antwoord("EMS_ONTDEKKING_1_aanwezig")["gedaan"] is False and geschreven == []
    assert c.ontdekking_log[0]["actie"] == O.VOORSTEL


def test_nieuwe_bewegingssensor_krijgt_een_melding_met_knoppen(make_coordinator, hass):
    inv = _inv(*MODULE_1)
    c = _coordinator(make_coordinator, inv)
    c._update_ontdekking(NU)
    verstuurd = []
    c._ontdekking_stuur = lambda titel, bericht, knoppen=None, tag="": verstuurd.append((bericht, knoppen, tag))
    inv.append({"entity_id": "binary_sensor.pir_gang", "device_class": "motion", "apparaat": "Sensor gang"})
    c._ontdekking_laatst = None
    c._update_ontdekking(NU)
    assert len(verstuurd) == 1 and "Sensor gang" in verstuurd[0][0]
    assert [k["title"] for k in verstuurd[0][1]] == ["Telt mee voor aanwezigheid", "Nee"]
    assert c.meldingen == []        # niet ook nog de gewone melding


def test_de_luisteraar_staat_in_de_setup():
    bron = (Path(pkg.__file__).parent / "__init__.py").read_text(encoding="utf-8")
    assert 'async_listen("mobile_app_notification_action", _ontdekking_actie)' in bron


# --- v5.258.0: korter in beeld (Ruud 24-11) ---------------------------------

def test_een_vondst_blijft_twee_dagen_en_zonder_werk_een_dag(make_coordinator, hass):
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    c = _coordinator(make_coordinator, _inv(*MODULE_1))
    nu = dt_util.now()

    def rij(naam, uren, actie):
        return {"moment": (nu - timedelta(hours=uren)).isoformat(), "soort": "lamp", "naam": naam, "actie": actie}

    c.ontdekking_log = [
        rij("gemeld 30 u", 30, O.GEMELD), rij("gemeld 20 u", 20, O.GEMELD),
        rij("vanzelf 30 u", 30, O.AUTOMATISCH), rij("vanzelf 2 u", 2, O.AUTOMATISCH),
        rij("wacht-sensoren 40 u", 40, O.WACHT), rij("wacht-sensoren 50 u", 50, O.WACHT),
        rij("akkoord 200 u", 200, O.VOORSTEL),
    ]
    kort = c.get_ontdekking_kort()
    assert [r["naam"] for r in kort["recent"]] == ["gemeld 20 u", "vanzelf 2 u", "wacht-sensoren 40 u"]
    assert [r["naam"] for r in kort["wacht_op_akkoord"]] == ["akkoord 200 u"]
