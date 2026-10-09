"""v5.68.1: een vervangen accumodule begint met een schone lei.

Gemeld 09-10: "Accumelding dat hij afwijkt hoeft niet meer, gaat om de 996
accu die wordt vervangen". De melding staat uit; de nieuwe module mag niet
beoordeeld worden op de geschiedenis van de oude.
"""
from datetime import datetime, timezone

NU = datetime(2026, 10, 9, 19, 0, tzinfo=timezone.utc)


def _modules(naam1):
    return [
        {"module": i, "naam": n, "cel_delta_v": 0.01, "temperatuur_c": 20.0,
         "soc_percent": 50.0, "vermogen_w": 100.0, "cel_min_v": 3.3}
        for i, n in ((1, naam1), (2, "AB3000 00123"), (3, "AB3000 00456"))
    ]


def test_andere_apparaatnaam_wist_de_geschiedenis(make_coordinator):
    c = make_coordinator({})
    c._read_battery_modules = lambda: _modules("AB3000 00996")
    c._update_battery_module_health(NU)
    c.battery_module_health["1"]["geschiedenis"] = {"cel_delta_v": [0.03] * 5}
    c.battery_module_health["1"]["cusum"] = {"cel_delta_afwijking_v": {"drift": True}}
    c._update_battery_module_health(NU)
    assert c.battery_module_health["1"]["geschiedenis"]
    c._read_battery_modules = lambda: _modules("AB3000 01234")
    c._update_battery_module_health(NU)
    assert c.battery_module_health["1"]["apparaat"] == "AB3000 01234"
    assert not c.battery_module_health["1"]["geschiedenis"]
    assert not c.battery_module_health["1"]["cusum"]
    assert c.battery_module_health["2"]["apparaat"] == "AB3000 00123"


def test_melding_per_module_uit(make_coordinator):
    """v5.68.2: "Melding mag zeker aanblijven alleen niet voor het genoemde
    nummer"."""
    c = make_coordinator({})
    c._read_battery_modules = lambda: _modules("AB3000 00996")
    c._update_battery_module_health(NU)
    for staat in c.battery_module_health.values():
        staat["cusum"] = {"temperatuur_afwijking_c": {"drift": True}}
    verstuurd = []
    c._dispatch_notification = lambda **k: verstuurd.append(k.get("message") or "")
    c.zet_module_melding("AB3000 00996", False)
    c._evaluate_new_notifications(NU)
    drift = [m for m in verstuurd if "wijkt" in m and "Module" in m]
    assert drift and "1" not in drift[0].split("wijkt")[0]
    c.zet_module_melding("AB3000 00996", True)
    assert c.battery_module_stil == []


def test_dienst_is_beschreven():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    assert "accumodule_melding:" in (Path(pkg.__file__).parent / "services.yaml").read_text()


def test_fabrieksnaam_telt_niet_de_eigen_naam(make_coordinator):
    """v5.68.4: de modules heten in HA "Accu module 1"; de fabrieksnaam
    "AB3000 00996" is wat bij vervanging verandert. Een eerder bewaarde
    eigen naam is geen vervanging."""
    c = make_coordinator({})
    mods = _modules("Accu module 1")
    for m, fabriek in zip(mods, ("AB3000 00996", "AB3000 00917", "AB3000 02093")):
        m["apparaat_id"] = fabriek
    c._read_battery_modules = lambda: mods
    c.battery_module_health = {"1": {"apparaat": "Accu module 1", "dag_metingen": {}, "geschiedenis": {"cel_delta_v": [0.02]}, "cusum": {}, "soc_buckets": {}, "waarschuwingen": []}}
    c._update_battery_module_health(NU)
    assert c.battery_module_health["1"]["geschiedenis"]
    assert c.battery_module_health["1"]["apparaat"] == "AB3000 00996"
    c.zet_module_melding("AB3000 00996", False)
    for staat in c.battery_module_health.values():
        staat["cusum"] = {"temperatuur_afwijking_c": {"drift": True}}
    assert "1" not in c._modules_met_drift()
    nieuw = [dict(m) for m in mods]
    nieuw[0]["apparaat_id"] = "AB3000 05555"
    c._read_battery_modules = lambda: nieuw
    c._update_battery_module_health(NU)
    assert not c.battery_module_health["1"]["geschiedenis"]
