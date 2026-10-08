"""v5.50: de Zendure-accu zelf meelezen - alleen lezen, nooit schrijven.

Gevraagd op 8 oktober: "Stap 1 uitvoeren" - het EMS leest de lokale
ZenSDK-API van de SolarFlow uit en vergelijkt dat met de Zendure-integratie,
zonder iets te sturen. Het rapport hieronder is een echte lezing van die dag.
"""
import asyncio
import inspect
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import zendure_lokaal as zl

MAP = Path(pkg.__file__).parent

RAPPORT = {
    "timestamp": 1791463474, "messageId": 220, "sn": "HOA1NPN4N230457", "version": 3,
    "product": "solarFlow2400AC",
    "properties": {
        "packInputPower": 0, "outputPackPower": 1745, "outputHomePower": 0, "electricLevel": 84,
        "gridInputPower": 1745, "solarInputPower": 0, "hyperTmp": 3051, "BatVolt": 5107,
        "acMode": 1, "inputLimit": 1745, "outputLimit": 0, "socSet": 1000, "minSoc": 100,
        "smartMode": 1, "packNum": 3, "rssi": -46,
    },
    "packData": [
        {"sn": "FO4NLN8N3400996", "packType": 5, "socLevel": 85, "state": 1, "power": 534,
         "maxTemp": 2991, "totalVol": 5090, "batcur": 105, "maxVol": 340, "minVol": 338},
        {"sn": "FO4NHN4N2900917", "packType": 5, "socLevel": 84, "state": 1, "power": 522,
         "maxTemp": 2961, "totalVol": 5070, "batcur": 103, "maxVol": 338, "minVol": 338},
    ],
}


def test_omrekenen_als_de_zendure_integratie():
    uit = zl.normaliseer(RAPPORT)
    a = uit["apparaat"]
    assert a["electricLevel"] == 84
    assert a["hyperTmp"] == 32.0          # (3051-2731)/10, zoals de integratie toonde
    assert a["BatVolt"] == 51.07
    assert a["socSet"] == 100.0 and a["minSoc"] == 10.0
    assert a["acMode"] == 1.0
    m = uit["modules"]["FO4NHN4N2900917"]
    assert m["maxTemp"] == 23.0           # de integratie toonde 23,0 °C
    assert m["totalVol"] == 50.7 and m["minVol"] == 3.38
    assert m["batcur"] == 10.3


def test_negatieve_stroom_met_teken():
    # 65535 is -1 als 16-bits getal met teken: -0,1 A
    uit = zl.normaliseer({"properties": {}, "packData": [{"sn": "X", "batcur": 65535}]})
    assert uit["modules"]["X"]["batcur"] == -0.1


def test_ontbrekend_is_niet_nul():
    uit = zl.normaliseer({"properties": {"electricLevel": None}, "packData": [{"state": 1}]})
    assert uit["apparaat"] == {} and uit["modules"] == {}


def test_hostnaam_als_de_zendure_integratie():
    assert zl.hostnaam("SolarFlow 2400 AC", "HOA1NPN4N230457") == "zendure-SolarFlow2400AC-HOA1NPN4N230457.local"
    assert zl.hostnaam(None, "x") is None


def test_snakecase_als_de_zendure_integratie():
    assert zl.snakecase("electricLevel") == "electric_level"
    assert zl.snakecase("BatVolt") == "bat_volt"
    assert zl.snakecase("hyperTmp") == "hyper_tmp"


def _toestanden(waarden):
    return lambda sn, veld: waarden.get((sn, veld))


def test_vergelijken_binnen_en_buiten_de_marge():
    lokaal = zl.normaliseer(RAPPORT)
    ha = {
        (None, "electricLevel"): "84",
        (None, "outputPackPower"): "1659",     # 86 W verschil, binnen 10% van 1745
        (None, "acMode"): "input",
        (None, "hyperTmp"): "32.0",
        (None, "socSet"): "100.0",
        ("FO4NHN4N2900917", "maxTemp"): "23.0",
        ("FO4NHN4N2900917", "socLevel"): "80",  # 4% verschil: buiten de marge
        ("FO4NHN4N2900917", "power"): "unavailable",
    }
    regels = {r["sleutel"]: r for r in zl.vergelijk(lokaal, _toestanden(ha))}
    assert regels["electricLevel"]["gelijk"]
    assert regels["outputPackPower"]["gelijk"]
    assert regels["acMode"]["gelijk"]
    assert regels["hyperTmp"]["gelijk"] and regels["socSet"]["gelijk"]
    assert regels["FO4NHN4N2900917.maxTemp"]["gelijk"]
    assert not regels["FO4NHN4N2900917.socLevel"]["gelijk"]
    # onbeschikbaar wordt niet vergeleken
    assert "FO4NHN4N2900917.power" not in regels
    # velden zonder Zendure-entiteit ook niet
    assert "packNum" not in regels


def test_oordeel_verloopt():
    t = zl.lege_tellingen()
    assert zl.oordeel(t) == "verzamelt"
    for i in range(zl.MIN_VERGELIJKINGEN):
        zl.verwerk_ronde(t, [{"sleutel": "electricLevel", "lokaal": 84, "zendure": 84, "verschil": 0, "gelijk": True}], 1000.0 + i, 120)
    assert zl.oordeel(t) == "gelijk"
    for i in range(5):
        zl.verwerk_ronde(t, [{"sleutel": "electricLevel", "lokaal": 84, "zendure": 70, "verschil": 14, "gelijk": False}], 2000.0 + i, 120)
    assert zl.oordeel(t) == "wijkt af"
    s = zl.samenvatting(t, "h.local")
    assert s["afwijkende_velden"][0]["veld"] == "electricLevel"
    assert s["latentie_mediaan_ms"] == 120
    for i in range(zl.MISLUKT_OP_RIJ_GEEN_VERBINDING):
        zl.verwerk_fout(t, "TimeoutError", 3000.0 + i)
    assert zl.oordeel(t) == "geen verbinding"
    assert zl.samenvatting(t, None)["laatste_fout"]["fout"] == "TimeoutError"


def test_latentiesteekproef_blijft_begrensd():
    t = zl.lege_tellingen()
    for i in range(zl.LATENTIE_STEEKPROEF + 50):
        zl.verwerk_ronde(t, [], float(i), float(i))
    assert len(t["latentie_ms"]) == zl.LATENTIE_STEEKPROEF


def test_schrijft_nooit_naar_de_accu():
    """De kern van stap 1: alleen lezen. Geen POST, geen write, geen dienst."""
    bron = (MAP / "zendure_lokaal.py").read_text()
    code = "\n".join(r for r in bron.splitlines() if not r.strip().startswith("#"))
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    for verboden in (".post(", ".put(", ".patch(", ".delete(", "properties/write",
                     "async_call", "services.call", "mqtt"):
        assert verboden not in code, f"{verboden} hoort niet in de meeleesmodule"
    assert "sessie.get(" in code


def test_de_sturing_leest_niets_uit_de_meelezer():
    coord = (MAP / "coordinator.py").read_text()
    assert "zendure_lokaal" not in coord


def test_ronde_vangt_elke_fout_af():
    class _Hass:
        pass

    m = zl.ZendureLokaalMeelezer(_Hass())
    m.host = "bestaat.niet.local"

    async def _boem():
        raise OSError("weg")

    m._ronde_binnen = _boem
    asyncio.run(m._ronde())
    assert m.tellingen["mislukt"] == 1
    assert m.status() == "verzamelt"


def test_sensor_en_diagnostiek_zijn_aangesloten():
    sensor = (MAP / "sensor.py").read_text()
    assert "ZendureLokaalSensor(coordinator, entry.entry_id)" in sensor
    assert '"zendure_lokaal"' in (MAP / "diagnostics.py").read_text()
    init = (MAP / "__init__.py").read_text()
    assert "meelezer.async_stop" in init
    assert inspect.iscoroutinefunction(zl.ZendureLokaalMeelezer.async_stop)


# --- afgeleid (idee uit Gielz1986/Zendure-HA-zenSDK) --------------------------


def test_celbalans_in_millivolt():
    assert zl.celbalans(340, 338) == {"verschil_mv": 20, "oordeel": "uitstekend"}
    assert zl.celbalans(345, 340)["oordeel"] == "goed"
    assert zl.celbalans(348, 340)["oordeel"] == "lichte onbalans"
    assert zl.celbalans(350, 340)["oordeel"] == "onbalans"
    assert zl.celbalans(None, 338) is None


def test_afgeleid_uit_het_echte_rapport():
    rapport = {**RAPPORT, "properties": {**RAPPORT["properties"], "socStatus": 0, "is_error": 0, "socLimit": 16}}
    a = zl.afgeleid(rapport)
    assert a["relais_stand"] == "laden"
    assert a["opslagmodus"] == "werkgeheugen (RAM)"
    assert a["soc_limiet"] == "normaal"
    assert not a["kalibreert"] and not a["foutmelding"]
    assert a["dc_laden_w"] == 534 + 522
    assert a["modules"]["FO4NLN8N3400996"]["celbalans"]["verschil_mv"] == 20
    # 1745 W van het net, 1056 W in de twee meegegeven modules: geen geldig
    # rendement buiten 0,5-1,05 wordt later weggefilterd; hier alleen de deling
    assert a["rendement_laden"] == round(1056 / 1745, 3)


def test_geen_rendement_met_zon_of_klein_vermogen():
    rapport = {"properties": {"solarInputPower": 400, "gridInputPower": 1000, "acMode": 1},
               "packData": [{"sn": "A", "state": 1, "power": 900}]}
    assert "rendement_laden" not in zl.afgeleid(rapport)
    rapport = {"properties": {"solarInputPower": 0, "gridInputPower": 200, "acMode": 1},
               "packData": [{"sn": "A", "state": 1, "power": 190}]}
    assert "rendement_laden" not in zl.afgeleid(rapport)


def test_relaisschakelingen_tellen_per_dag():
    t = zl.lege_tellingen()
    dag1 = 1791460000.0
    for stand in ("laden", "laden", "ontladen", "ontladen", "laden"):
        zl.verwerk_afgeleid(t, {"relais_stand": stand}, dag1)
    assert t["relais"]["vandaag"] == 2 and t["relais"]["totaal"] == 2
    zl.verwerk_afgeleid(t, {"relais_stand": "ontladen"}, dag1 + 86400)
    assert t["relais"]["vandaag"] == 1 and t["relais"]["totaal"] == 3
    assert list(t["relais"]["per_dag"].values()) == [2]


def test_rendement_mediaan_en_retour():
    t = zl.lege_tellingen()
    for w in (0.93, 0.94, 0.95):
        zl.verwerk_afgeleid(t, {"rendement_laden": w, "rendement_ontladen": w - 0.02}, 1791460000.0)
    zl.verwerk_afgeleid(t, {"rendement_laden": 0.2}, 1791460000.0)  # onzin, weg
    r = zl.rendement_samenvatting(t)
    assert r["laden"] == {"mediaan": 0.94, "n": 3}
    assert r["retour"] == round(0.94 * 0.92, 3)


def test_de_kaarttekst_komt_uit_de_module():
    t = zl.lege_tellingen()
    zl.verwerk_ronde(t, [], 1791460000.0, 150)
    a = zl.samenvatting(t, "h.local")
    a["accu"] = zl.afgeleid(RAPPORT)
    a["relaisschakelingen"] = {"vandaag": 2}
    a["omzetrendement"] = {"laden": {"mediaan": 0.94, "n": 3}, "ontladen": None}
    tekst = zl.tekst("verzamelt", a)
    assert tekst.startswith("**verzamelt**")
    assert "2 wissels vandaag" in tekst and "werkgeheugen" in tekst
    assert "laden 94,0%" in tekst and "ontladen -" in tekst
    assert "Module …00996" in tekst and "20 mV (uitstekend)" in tekst


# --- reactiesnelheid --------------------------------------------------------


def test_wie_ziet_een_sprong_het_eerst():
    r = zl.lege_reactie()
    t = 1791460000.0
    zl.reactie_waarneming(r, "lokaal", "gridInputPower", 100, t)
    zl.reactie_waarneming(r, "zendure", "gridInputPower", 110, t + 1)
    # lokaal ziet de sprong eerst
    zl.reactie_waarneming(r, "lokaal", "gridInputPower", 1700, t + 5)
    zl.reactie_waarneming(r, "zendure", "gridInputPower", 1690, t + 8.4)
    # daarna ziet Zendure een sprong eerst
    zl.reactie_waarneming(r, "zendure", "gridInputPower", 400, t + 20)
    zl.reactie_waarneming(r, "lokaal", "gridInputPower", 405, t + 25)
    s = zl.reactie_samenvatting(r, 5)
    assert s["wijzigingen"] == 2
    assert s["lokaal"]["eerst"] == 1 and s["lokaal"]["mediaan_voorsprong_s"] == 3.4
    assert s["zendure"]["eerst"] == 1 and s["zendure"]["mediaan_voorsprong_s"] == 5.0
    assert s["sneller"] == "gelijk op"


def test_kleine_schommeling_is_geen_wijziging():
    r = zl.lege_reactie()
    zl.reactie_waarneming(r, "lokaal", "gridInputPower", 1000, 0)
    zl.reactie_waarneming(r, "lokaal", "gridInputPower", 1100, 5)
    assert r["open"] == {}


def test_niet_gevolgde_wijziging_verloopt():
    r = zl.lege_reactie()
    zl.reactie_waarneming(r, "lokaal", "acMode", 1, 0)
    zl.reactie_waarneming(r, "lokaal", "acMode", 2, 5)
    assert "acMode" in r["open"]
    zl.reactie_waarneming(r, "lokaal", "outputLimit", 0, 5 + zl.REACTIE_MAX_WACHT_S + 1)
    assert r["open"] == {} and r["niet_gevolgd"] == 1


def test_lopende_wijziging_wordt_niet_vergeleken():
    r = zl.lege_reactie()
    r["open"]["gridInputPower"] = {"bron": "lokaal", "waarde": 1700, "t": 100.0}
    regels = [
        {"sleutel": "gridInputPower", "gelijk": False},
        {"sleutel": "electricLevel", "gelijk": True},
        {"sleutel": "SN1.power", "gelijk": False},
        {"sleutel": "SN1.socLevel", "gelijk": True},
    ]
    over = [x["sleutel"] for x in zl.zonder_lopende_wijzigingen(regels, r, 101.0)]
    assert over == ["electricLevel", "SN1.socLevel"]
    # verlopen: weer alles vergelijken
    assert len(zl.zonder_lopende_wijzigingen(regels, r, 100.0 + zl.REACTIE_MAX_WACHT_S + 1)) == 4


def test_de_race_tussen_bronnen_staat_niet_meer_in_de_kaart():
    """v5.52: wie de ander voor is zegt niet wie gelijk heeft; de kaart toont
    het oordeel tegen de stekker."""
    a = zl.samenvatting(zl.lege_tellingen(), None)
    r = zl.lege_reactie()
    zl.reactie_waarneming(r, "lokaal", "gridInputPower", 0, 0)
    zl.reactie_waarneming(r, "zendure", "gridInputPower", 0, 0)
    zl.reactie_waarneming(r, "lokaal", "gridInputPower", 1500, 10)
    zl.reactie_waarneming(r, "zendure", "gridInputPower", 1500, 14)
    a["reactiesnelheid"] = zl.reactie_samenvatting(r, 5)
    assert "Sneller:" not in zl.tekst("verzamelt", a)


# --- v5.51.1: opdrachten apart, één keer opnieuw tellen ---------------------


def test_opdracht_telt_niet_in_de_race_maar_als_bevestiging():
    r = zl.lege_reactie()
    zl.reactie_waarneming(r, "zendure", "outputLimit", 0, 0)
    zl.reactie_waarneming(r, "lokaal", "outputLimit", 0, 1)
    # EMS geeft via Zendure 549 W op; de accu laat het 3,1 s later zien
    zl.reactie_waarneming(r, "zendure", "outputLimit", 549, 10)
    zl.reactie_waarneming(r, "lokaal", "outputLimit", 549, 13.1)
    s = zl.reactie_samenvatting(r, 5)
    assert s["wijzigingen"] == 0
    assert s["opdracht_bevestigd"] == {"n": 1, "mediaan_s": 3.1}
    assert r["recent"][-1]["soort"] == "opdracht"


def test_oud_schema_begint_de_vergelijking_opnieuw():
    oud = {"rondes": 71, "gelukt": 71, "velden": {"x": {"n": 60, "gelijk": 50}},
           "reactie": {"eerst": {"zendure": 11}}, "relais": {"totaal": 4}, "rendement": {"laden": [0.9]}}
    uit = zl.herstel(oud)
    assert "velden" not in uit and "reactie" not in uit and "rondes" not in uit
    assert uit["relais"] == {"totaal": 4} and uit["rendement"] == {"laden": [0.9]}
    assert uit["schema"] == zl.SCHEMA
    nieuw = {**zl.lege_tellingen(), "rondes": 5}
    assert zl.herstel(nieuw)["rondes"] == 5


# --- v5.52: welke bron is de beste (tegen de HomeWizard-stekker) -------------


def test_netto_ac():
    assert zl.netto_ac({"outputHomePower": 541, "gridInputPower": 0}) == 541
    assert zl.netto_ac({"outputHomePower": 0, "gridInputPower": 1745}) == -1745
    assert zl.netto_ac({"outputHomePower": 0}) is None


def test_vertraging_na_een_sprong_van_de_stekker():
    ref = zl.lege_referentie()
    zl.ref_waarneming(ref, 0, 500)
    zl.ref_waarneming(ref, 10, -1600)          # sprong naar laden
    zl.bron_waarneming(ref, "zendure", 11, 500)   # nog oud
    zl.bron_waarneming(ref, "zendure", 13.5, -1580)
    zl.bron_waarneming(ref, "lokaal", 15, -1610)
    s = zl.referentie_samenvatting(ref, "sensor.stekker")
    assert s["sprongen"] == 1
    assert s["zendure"]["mediaan_vertraging_s"] == 3.5
    assert s["lokaal"]["mediaan_vertraging_s"] == 5.0
    assert ref["sprong"] is None


def test_gemiste_sprong():
    ref = zl.lege_referentie()
    zl.ref_waarneming(ref, 0, 0)
    zl.ref_waarneming(ref, 1, 1000)
    zl.bron_waarneming(ref, "lokaal", 3, 990)
    zl.ref_waarneming(ref, 1 + zl.REFERENTIE_MAX_WACHT_S + 1, 1000)
    assert ref["gemist"] == {"lokaal": 0, "zendure": 1}


def test_afwijking_alleen_als_de_stekker_stabiel_is():
    ref = zl.lege_referentie()
    zl.ref_waarneming(ref, 0, 500)
    zl.steekproef(ref, 10, {"lokaal": 510, "zendure": 600})
    assert ref["afwijking"] == {"lokaal": [10.0], "zendure": [100.0]}
    zl.ref_waarneming(ref, 20, 1500)
    zl.steekproef(ref, 22, {"lokaal": 1500, "zendure": 500})   # net versprongen: niet tellen
    assert len(ref["afwijking"]["lokaal"]) == 1


def test_beste_bron_oordeel():
    def s(a_l, a_z, v_l, v_z, n=40, sp=5):
        return {"lokaal": {"n": n, "gem_afwijking_w": a_l, "sprongen_gezien": sp, "mediaan_vertraging_s": v_l},
                "zendure": {"n": n, "gem_afwijking_w": a_z, "sprongen_gezien": sp, "mediaan_vertraging_s": v_z}}
    assert zl.beste_bron(s(10, 40, 2.5, 4.0))[0] == "lokaal"
    assert zl.beste_bron(s(40, 10, 4.0, 2.5))[0] == "zendure"
    assert zl.beste_bron(s(10, 40, 4.0, 2.5))[0] == "verschilt"
    assert zl.beste_bron(s(20, 21, 3.0, 3.4))[0] == "gelijkwaardig"
    assert zl.beste_bron(s(10, 40, 2.5, 4.0, n=5))[0] is None
    # te weinig sprongen: alleen nauwkeurigheid telt
    assert zl.beste_bron(s(10, 40, 9.0, 1.0, sp=1))[0] == "lokaal"


def test_beste_bron_in_de_kaarttekst():
    a = zl.samenvatting(zl.lege_tellingen(), None)
    a["beste_bron"] = {"meetpunt": "sensor.x", "beste": "lokaal", "toelichting": "nauwkeuriger",
                       "lokaal": {"gem_afwijking_w": 8.0, "n": 40}, "zendure": {"gem_afwijking_w": 30.0, "n": 40}}
    t = zl.tekst("gelijk", a)
    assert "Beste bron: **het EMS zelf**" in t and "gem. 8,0 W" in t
    a["beste_bron"] = {"meetpunt": None}
    assert "geen onafhankelijke meting" in zl.tekst("gelijk", a)


def test_de_stekker_is_de_referentie():
    init = (MAP / "__init__.py").read_text()
    assert "referentie=config.get(CONF_BATTERY_POWER_SENSOR)" in init
