"""v5.233.0: twee accumeldingen zonder grond (dagcontrole 13/14-11, L-EMS-078 en L-EMS-079)."""

from datetime import datetime, timezone

NU = datetime(2026, 11, 14, 19, 0, tzinfo=timezone.utc)
NAMEN = ("AB3000 01029", "AB3000 00917", "AB3000 02093")


def _modules(namen=NAMEN, cellen=(3.3, 3.3, 3.3)):
    return [
        {"module": i + 1, "naam": f"Accu module {i + 1}", "apparaat_id": n, "cel_delta_v": 0.01,
         "temperatuur_c": 20.0, "soc_percent": 50.0, "vermogen_w": 100.0, "cel_min_v": cellen[i]}
        for i, n in enumerate(namen)
    ]


def _met_geschiedenis(c):
    for staat in c.battery_module_health.values():
        staat["geschiedenis"] = {"temperatuur_afwijking_c": [-1.0] * 5, "cel_delta_afwijking_v": [0.0] * 5,
                                 "soc_afwijking_percent": [0.0] * 5, "cel_delta_v": [0.01] * 5, "laagste_cel_v": [3.2] * 5}
        staat["cusum"] = {"temperatuur_afwijking_c": {"drift": True, "accumulator": 4.0}}
        staat["dag_metingen"] = {"temperatuur_afwijking_c": [2.0], "temperatuur_c": [20.0]}


# --- L-EMS-078 ---------------------------------------------------------------


def test_na_een_wissel_beginnen_de_relatieve_velden_van_alle_modules_opnieuw(make_coordinator):
    c = make_coordinator({})
    c._read_battery_modules = lambda: _modules()
    c._update_battery_module_health(NU)
    _met_geschiedenis(c)
    c._read_battery_modules = lambda: _modules(("AB3000 01029", "AB3000 00917", "AB3000 09999"))
    c._update_battery_module_health(NU)
    for sleutel in ("1", "2"):
        g = c.battery_module_health[sleutel]["geschiedenis"]
        assert "temperatuur_afwijking_c" not in g and "cel_delta_afwijking_v" not in g and "soc_afwijking_percent" not in g
        assert g["cel_delta_v"] == [0.01] * 5 and g["laagste_cel_v"] == [3.2] * 5      # absoluut blijft
        assert "temperatuur_afwijking_c" not in c.battery_module_health[sleutel]["cusum"]
    assert c.battery_module_identiteiten == sorted(("AB3000 01029", "AB3000 00917", "AB3000 09999"))


def test_dezelfde_modules_laten_alles_staan(make_coordinator):
    c = make_coordinator({})
    c._read_battery_modules = lambda: _modules()
    c._update_battery_module_health(NU)
    _met_geschiedenis(c)
    c._update_battery_module_health(NU)
    assert c.battery_module_health["1"]["geschiedenis"]["temperatuur_afwijking_c"] == [-1.0] * 5
    assert c.battery_module_health["1"]["cusum"]["temperatuur_afwijking_c"]["drift"] is True


def test_de_eerste_keer_begint_opnieuw_want_de_wissel_van_0711_viel_ervoor(make_coordinator):
    c = make_coordinator({})
    c._read_battery_modules = lambda: _modules()
    c._update_battery_module_health(NU)
    _met_geschiedenis(c)
    c.battery_module_identiteiten = None          # zoals na het bijwerken naar deze versie
    assert c._herstart_relatief_na_modulewissel(_modules()) is True
    assert "temperatuur_afwijking_c" not in c.battery_module_health["1"]["geschiedenis"]
    assert c._herstart_relatief_na_modulewissel(_modules()) is False


def test_een_module_die_even_niet_meldt_is_geen_wissel(make_coordinator):
    c = make_coordinator({})
    c._read_battery_modules = lambda: _modules()
    c._update_battery_module_health(NU)
    _met_geschiedenis(c)
    assert c._herstart_relatief_na_modulewissel(_modules()[:2]) is False
    assert c._herstart_relatief_na_modulewissel(_modules()) is False
    assert c.battery_module_health["1"]["geschiedenis"]["temperatuur_afwijking_c"] == [-1.0] * 5
    geen_naam = _modules()
    geen_naam[0]["apparaat_id"] = None
    geen_naam[0]["naam"] = None
    assert c._herstart_relatief_na_modulewissel(geen_naam) is False


def test_de_set_wordt_bewaard():
    from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS
    assert "battery_module_identiteiten" in PERSISTED_PLAIN_FIELDS


# --- L-EMS-079 ---------------------------------------------------------------


def _c_met_cellen(make_coordinator, cellen, dagen_laag=3):
    c = make_coordinator({})
    c._read_battery_modules = lambda: _modules(cellen=cellen)
    c._celspanning_bijlaadkosten = lambda: {}
    c._update_battery_module_health(NU)
    for staat in c.battery_module_health.values():
        staat.setdefault("geschiedenis", {})["laagste_cel_v"] = [3.07] * dagen_laag
    return c


def test_alle_cellen_samen_laag_is_geen_achterblijvende_cel(make_coordinator):
    c = _c_met_cellen(make_coordinator, (3.07, 3.08, 3.09))
    o = c.get_celspanning_oordeel()
    assert o["oordeel"] == "aandacht" and o["achterstand_v"] == 0.01 and o["achterblijvend"] is False
    assert "blijft geen cel achter" in o["advies"]
    verstuurd = []
    c._dispatch_notification = lambda **k: verstuurd.append(k)
    c._meld_lage_celspanning()
    assert verstuurd == []


def test_een_echt_achterblijvende_cel_wordt_nog_gemeld(make_coordinator):
    c = _c_met_cellen(make_coordinator, (3.02, 3.21, 3.21))
    o = c.get_celspanning_oordeel()
    assert o["achterstand_v"] == 0.19 and o["achterblijvend"] is True
    assert "eerder dan de rest" in o["advies"]
    verstuurd = []
    c._dispatch_notification = lambda **k: verstuurd.append(k)
    c._meld_lage_celspanning()
    assert len(verstuurd) == 1 and verstuurd[0]["kind"] == "celspanning_laag"


def test_kritiek_meldt_altijd_ook_als_alle_cellen_laag_staan(make_coordinator):
    c = _c_met_cellen(make_coordinator, (2.95, 2.96, 2.97), dagen_laag=0)
    assert c.get_celspanning_oordeel()["oordeel"] == "kritiek"
    verstuurd = []
    c._dispatch_notification = lambda **k: verstuurd.append(k)
    c._meld_lage_celspanning()
    assert len(verstuurd) == 1


def test_de_grens_is_vijf_honderdste_volt(make_coordinator):
    assert _c_met_cellen(make_coordinator, (3.04, 3.09, 3.09)).get_celspanning_oordeel()["achterblijvend"] is True
    assert _c_met_cellen(make_coordinator, (3.05, 3.09, 3.09)).get_celspanning_oordeel()["achterblijvend"] is False


def test_een_enkele_module_telt_als_vroeger(make_coordinator):
    c = make_coordinator({})
    c._celspanning_bijlaadkosten = lambda: {}
    c.battery_module_live = [{"module": 1, "cel_min_v": 3.05}]
    o = c.get_celspanning_oordeel()
    assert o["achterstand_v"] is None and o["achterblijvend"] is True
