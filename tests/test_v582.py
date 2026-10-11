"""v5.82: terugval bij lezen - de eigen Zendure-lezing vervangt een
onbeschikbare Zendure-entiteit.

Akkoord Ruud 11-10 10:22, na het advies op basis van 2,7 dagen meelezen
(99,996% geslaagde rondes, 99,9% overeenkomst, gelijkwaardig tegen de
stekker). Alleen lezen: het schrijven blijft bij de Zendure-integratie.
"""
import re
import time
from pathlib import Path
from types import SimpleNamespace

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import zendure_lokaal as zl

MAP = Path(pkg.__file__).parent

LAATSTE = {
    "sn": "HOA1NPN4N230457",
    "apparaat": {"electricLevel": 22.0, "hyperTmp": 23.0, "acMode": 1.0, "smartMode": 1.0},
    "modules": {"FO4NLN8N3400996": {"socLevel": 21.0, "maxVol": 3.27}},
}
ENTITEITEN = {
    (None, "electricLevel"): "sensor.solarflow_2400_ac_electric_level",
    (None, "hyperTmp"): "sensor.solarflow_2400_ac_hyper_tmp",
    (None, "acMode"): "select.solarflow_2400_ac_ac_mode",
    (None, "smartMode"): "sensor.solarflow_2400_ac_smart_mode",
    ("FO4NLN8N3400996", "socLevel"): "sensor.ab3000_00996_soc_level",
}


def _meelezer(leeftijd_s: float = 1.0) -> zl.ZendureLokaalMeelezer:
    m = zl.ZendureLokaalMeelezer(SimpleNamespace())
    m.laatste = LAATSTE
    m.laatste_t = time.monotonic() - leeftijd_s
    m._entiteiten = dict(ENTITEITEN)
    return m


def test_verse_lezing_vervangt_apparaat_en_module():
    m = _meelezer()
    assert m.vervanging("sensor.solarflow_2400_ac_electric_level") == 22.0
    assert m.vervanging("sensor.ab3000_00996_soc_level") == 21.0
    assert m.terugval["keer"] == 2
    assert m.terugval["per_entiteit"]["sensor.ab3000_00996_soc_level"] == 1


def test_te_oude_lezing_vervangt_niet():
    m = _meelezer(leeftijd_s=zl.VERVANG_MAX_LEEFTIJD_S + 1)
    assert m.vervanging("sensor.solarflow_2400_ac_electric_level") is None
    assert m.terugval["keer"] == 0 and m.terugval["geweigerd_te_oud"] == 1


def test_onbekende_entiteit_en_tekstvelden_niet():
    m = _meelezer()
    assert m.vervanging("sensor.zendure_batterij_vermogen") is None   # de stekker
    assert m.vervanging("select.solarflow_2400_ac_ac_mode") is None
    assert m.vervanging("sensor.solarflow_2400_ac_smart_mode") is None
    assert m.vervanging(None) is None


def test_zonder_lezing_niets():
    m = zl.ZendureLokaalMeelezer(SimpleNamespace())
    assert m.vervanging("sensor.solarflow_2400_ac_electric_level") is None


def test_vervanging_geeft_nooit_een_fout():
    m = _meelezer()
    m._entiteiten = None  # kapot
    assert m.vervanging("sensor.solarflow_2400_ac_electric_level") is None


def test_coordinator_valt_terug_alleen_bij_onbeschikbaar(hass, make_coordinator):
    c = make_coordinator({})
    c.zendure_lokaal = _meelezer()
    eid = "sensor.solarflow_2400_ac_electric_level"
    hass.states.set(eid, "unavailable")
    assert c._read_sensor_float(eid) == 22.0
    hass.states.set(eid, "35")
    assert c._read_sensor_float(eid) == 35.0          # Zendure blijft leidend
    assert c.zendure_lokaal.terugval["keer"] == 1


def test_coordinator_zonder_meelezer_zoals_voorheen(hass, make_coordinator):
    c = make_coordinator({})
    hass.states.set("sensor.solarflow_2400_ac_electric_level", "unavailable")
    assert c._read_sensor_float("sensor.solarflow_2400_ac_electric_level") is None


def test_terugval_in_attributen_en_kaart():
    m = _meelezer()
    m.vervanging("sensor.solarflow_2400_ac_electric_level")
    s = zl.terugval_samenvatting(m.terugval, time.time())
    assert s["actief"] and s["keer"] == 1
    tekst = zl.tekst("gelijk", {"terugval": s})
    assert "Terugval: **actief**" in tekst
    assert "nog niet nodig" in zl.tekst("gelijk", {"terugval": zl.terugval_samenvatting(zl.lege_terugval(), time.time())})


def test_meeleesmodule_schrijft_nog_steeds_niet():
    bron = (MAP / "zendure_lokaal.py").read_text()
    code = re.sub(r'"""[\s\S]*?"""', "", bron)
    for verboden in (".post(", ".put(", "properties/write", "async_call", "services.call"):
        assert verboden not in code
