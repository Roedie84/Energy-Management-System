"""v5.255.0: knop 'iedereen weg' (Ruud 24-11).

"Omdat het lastig is om op snelle termijn te bepalen of er iemand aanwezig
is, is het misschien een optie om op het dashboard een knop
aanwezig/afwezig te zetten?" Geen telefoons: de knop gaat voor de sensoren.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import custom_components.energy_management_system as pkg

MAP = Path(pkg.__file__).parent
NU = datetime(2026, 11, 24, 8, 30, tzinfo=timezone(timedelta(hours=1)))
KNOP = "input_boolean.iedereen_weg"


def _c(make_coordinator, stand="on", **extra):
    c = make_coordinator({"afwezig_knop_entity": KNOP, **extra})
    c.hass.states.get = lambda e: SimpleNamespace(state=stand, attributes={}) if e == KNOP else None
    return c


def test_de_knop_wordt_gelezen(make_coordinator, hass):
    assert _c(make_coordinator, "on").afwezig_knop_aan() is True
    assert _c(make_coordinator, "off").afwezig_knop_aan() is False
    assert _c(make_coordinator, "unavailable").afwezig_knop_aan() is False
    assert make_coordinator({}).afwezig_knop_aan() is False


def test_de_knop_gaat_voor_de_sensoren(make_coordinator, hass):
    c = _c(make_coordinator, "on")
    c._update_presence = lambda now: setattr(c, "presence_state", "thuis")
    c._update_presence_met_knop(NU)
    assert c.presence_state == "weg"
    uit = _c(make_coordinator, "off")
    uit._update_presence = lambda now: setattr(uit, "presence_state", "thuis")
    uit._update_presence_met_knop(NU)
    assert uit.presence_state == "thuis"
    # zonder ingestelde sensoren blijft de aanwezigheid onbekend
    geen = _c(make_coordinator, "on")
    geen._update_presence = lambda now: setattr(geen, "presence_state", None)
    geen._update_presence_met_knop(NU)
    assert geen.presence_state is None


def test_de_airco_gaat_meteen_naar_de_lage_stand(make_coordinator, hass):
    c = _c(make_coordinator, "on")
    c.airco_door_ems = True
    c._weg_sinds = NU - timedelta(minutes=1)
    uit = c._airco_lang_weg_terugzetten(NU, {"actie": "niets"}, "heat", 21.0)
    assert uit["actie"] == "verwarmen" and uit["doel_c"] == 18.0
    assert "knop" in uit["tekst"].lower()
    # zonder knop pas na twee uur
    z = _c(make_coordinator, "off")
    z.airco_door_ems = True
    z._weg_sinds = NU - timedelta(minutes=1)
    assert z._airco_lang_weg_terugzetten(NU, {"actie": "niets"}, "heat", 21.0)["actie"] == "niets"
    # v5.255.1 (Ruud 24-11: knop aan, airco bleef op 23): de knop geldt ook
    # voor een airco die jullie zelf aanzetten; zonder knop blijft die staan
    z.airco_door_ems = False
    z._weg_sinds = NU - timedelta(hours=3)
    assert z._airco_lang_weg_terugzetten(NU, {"actie": "niets"}, "heat", 23.0)["actie"] == "niets"
    zelf = _c(make_coordinator, "on")
    zelf.airco_door_ems = False
    zelf._weg_sinds = NU - timedelta(minutes=1)
    assert zelf._airco_lang_weg_terugzetten(NU, {"actie": "niets"}, "heat", 23.0)["doel_c"] == 18.0


def test_de_ochtendverwarming_slaat_over(make_coordinator, hass):
    assert _c(make_coordinator, "on", airco_werkdag_warm_om="07:00")._airco_ritme()["vast_ochtend"] == {}
    assert _c(make_coordinator, "off", airco_werkdag_warm_om="07:00")._airco_ritme()["vast_ochtend"] != {}


def test_het_veld_staat_in_de_instellingen_en_de_vertalingen():
    assert "CONF_AFWEZIG_KNOP_ENTITY" in (MAP / "config_flow.py").read_text()
    for bestand in ("strings.json", "translations/nl.json", "translations/en.json"):
        assert json.dumps(json.loads((MAP / bestand).read_text())).count("afwezig_knop_entity") == 2


# --- v5.255.0: 's nachts vasthouden op 18 graden -----------------------------

def test_de_nachttemperatuur_uit_de_instelling(make_coordinator, hass):
    assert make_coordinator({"airco_nacht_c": 18.0})._airco_nacht_c() == 18.0
    assert make_coordinator({})._airco_nacht_c() is None
    assert make_coordinator({"airco_nacht_c": 0})._airco_nacht_c() is None
    assert make_coordinator({"airco_nacht_c": 30})._airco_nacht_c() is None


def test_de_nachtstand_wordt_herkend_zonder_geheugen(make_coordinator, hass):
    c = make_coordinator({"airco_nacht_c": 18.0})
    c.airco_door_ems = True
    assert c._airco_op_nachtstand("heat", 18.0) is True
    assert c._airco_op_nachtstand("heat", 18.5) is True       # halve graad voorverwarmen
    assert c._airco_op_nachtstand("heat", 21.0) is False
    assert c._airco_op_nachtstand("off", 18.0) is False
    c.airco_door_ems = False                                   # zelf op 18 gezet: niet van het EMS
    assert c._airco_op_nachtstand("heat", 18.0) is False
    assert make_coordinator({})._airco_op_nachtstand("heat", 18.0) is False


def _avond(make_coordinator, monkeypatch, opties, aanwezigheid="thuis", advies="airco"):
    from custom_components.energy_management_system import airco_ritme

    c = make_coordinator(opties)
    c.airco_automaat_aan = True
    c.presence_state = aanwezigheid
    c.get_verwarmingsadvies = lambda: {"advies": advies}
    c._noteer_airco_frequentie = lambda *a: None
    c._noteer_airco_verbruik = lambda *a: None
    c._airco_ochtend_tempo = lambda now: 3.0
    c._airco_kost_per_uur = lambda now, ritme: None
    monkeypatch.setattr(airco_ritme, "besluit", lambda *a, **k: {
        "actie": "uit", "markeer_uit": True, "altijd": True,
        "tekst": "Uitzetten: het is 22:00, dan gaat de airco uit.", "reden": "vaste uittijd 22:00"})
    return c._airco_ritme_ronde(NU.replace(hour=22, minute=0), {"actie": "niets", "redenen": []}, "heat")


def test_om_tien_uur_niet_uit_maar_naar_de_nachttemperatuur(make_coordinator, hass, monkeypatch):
    uit = _avond(make_coordinator, monkeypatch, {"airco_nacht_c": 18.0})
    assert uit["actie"] == "verwarmen" and uit["doel_c"] == 18.0
    assert "18" in uit["tekst"] and "nacht" in uit["redenen_tekst"]


def test_zonder_instelling_of_bij_een_leeg_huis_gewoon_uit(make_coordinator, hass, monkeypatch):
    assert _avond(make_coordinator, monkeypatch, {})["actie"] == "uit"
    assert _avond(make_coordinator, monkeypatch, {"airco_nacht_c": 18.0}, aanwezigheid="weg")["actie"] == "uit"
    assert _avond(make_coordinator, monkeypatch, {"airco_nacht_c": 18.0}, advies="cv")["actie"] == "uit"


def test_op_de_nachtstand_zet_iedereen_slaapt_hem_niet_uit():
    from custom_components.energy_management_system import airco_sturing

    basis = dict(woonkamer_c=18.2, aanwezigheid="slaapt", aanzet_c=19.5, doel_c=21.0, advies="airco",
                 handmatig=False, door_ems_aan=True, setpunten_gezien=6, setpunten_nodig=5, nachtrust=True)
    assert airco_sturing.besluit(airco_stand="heat", **basis)["actie"] == "uit"      # zo ging het
    assert airco_sturing.besluit(airco_stand="off", **basis)["actie"] == "niets"     # nachtstand
    # 's ochtends thuis en onder de aanzettemperatuur: gewoon verwarmen naar het doel
    ochtend = dict(basis, aanwezigheid="thuis", nachtrust=False)
    assert airco_sturing.besluit(airco_stand="off", **ochtend)["actie"] == "verwarmen"


def test_de_nachtinstelling_staat_in_de_instellingen_en_de_vertalingen():
    for bestand in ("strings.json", "translations/nl.json", "translations/en.json"):
        assert json.dumps(json.loads((MAP / bestand).read_text())).count("airco_nacht_c") == 2
