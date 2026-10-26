"""v5.135.0 (akkoord Ruud 26-10): verbruik per dagtype, zonvoorspelling eerder
corrigeren, en het continu-verbruik verklaard."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import const

TZ = timezone(timedelta(hours=1))
ZATERDAG = datetime(2026, 10, 24, 10, 0, tzinfo=TZ)
MAANDAG = datetime(2026, 10, 26, 10, 0, tzinfo=TZ)


def _profiel(c):
    c.hourly_consumption_profile = {10: [0.40] * 7}
    c.daytype_consumption_profile = {"weekend-10": [0.60] * 4, "werkdag-10": [0.30] * 3}


def test_weekend_uur_met_genoeg_waarnemingen(make_coordinator):
    c = make_coordinator({})
    _profiel(c)
    assert c.verbruik_uur_kw(10, ZATERDAG) == 0.60


def test_te_weinig_waarnemingen_dan_het_gewone_profiel(make_coordinator):
    c = make_coordinator({})
    _profiel(c)
    assert c.verbruik_uur_kw(10, MAANDAG) == 0.40       # werkdag: 3 < 4
    assert c.learned_hourly_avg_kw(10) == 0.40          # ongewijzigd


def test_energiesom_rekent_per_dagtype(make_coordinator):
    c = make_coordinator({})
    c.hourly_consumption_profile = {h: [0.40] * 7 for h in range(24)}
    c.daytype_consumption_profile = {f"weekend-{h}": [0.60] * 5 for h in range(24)}
    zat = c._estimate_consumption_kwh_for_period(ZATERDAG, ZATERDAG + timedelta(hours=2))
    maa = c._estimate_consumption_kwh_for_period(MAANDAG, MAANDAG + timedelta(hours=2))
    assert round(zat, 2) == 1.20 and round(maa, 2) == 0.80


def test_proefstand_dagtype_stuurt_mee(make_coordinator):
    c = make_coordinator({})
    c.daytype_consumption_profile = {
        **{f"werkdag-{h}": [0.37] * 7 for h in range(24)},
        **{f"weekend-{h}": [0.40] * 7 for h in range(24)},
    }
    k = c._kandidaat_dagtype()
    assert k["stuurt_sinds"].startswith("v5.135.0")


def test_zon_eenzijdig_vanaf_70_procent():
    assert const.SOLAR_EENZIJDIG_AANDEEL == 0.7


def test_sluipverbruik_verklaring(make_coordinator, hass):
    c = make_coordinator({})
    nu = datetime(2026, 10, 26, 20, 0, tzinfo=TZ)
    c.baseline_load_history = [0.1336, 0.145]
    c.nachtlast_per_apparaat = {
        "2026-10-26": {"sensor.diepvries": 30.0, "sensor.cv": 8.0, "sensor.dubbel_groep": 50.0},
    }
    c.nilm_confirmed_devices = {"sensor.diepvries": {}, "sensor.cv": {}}
    hass.states.set("sensor.diepvries", "0", {"friendly_name": "Diepvries schuur"})
    v = c.get_sluipverbruik_verklaring(nu)
    assert v["beschikbaar"] is True
    assert v["huis_vloer_w"] == 145 and v["verklaard_w"] == 38.0 and v["onverklaard_w"] == 107
    assert [a["w"] for a in v["apparaten"]] == [30.0, 8.0]   # geen dubbeltelling
    assert v["apparaten"][0]["naam"].startswith("Diepvries schuur")


def test_sluipverbruik_lopende_nacht_telt_nog_niet(make_coordinator):
    c = make_coordinator({})
    c.baseline_load_history = [0.14]
    c.nachtlast_per_apparaat = {"2026-10-26": {"sensor.a": 5.0}}
    c.nilm_confirmed_devices = {"sensor.a": {}}
    v = c.get_sluipverbruik_verklaring(datetime(2026, 10, 26, 3, 0, tzinfo=TZ))
    assert v["beschikbaar"] is False


def test_cockpit_toont_continu_verbruik():
    js = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert 'sluip: "sluipverbruik"' in js and '"Continu-verbruik"' in js


def test_sluipverbruik_telt_losse_powercalc_mee(make_coordinator, hass):
    """v5.135.1: Powercalc-sensoren tellen mee, groepen en all_standby niet."""
    c = make_coordinator({})
    nu = datetime(2026, 10, 27, 20, 0, tzinfo=TZ)
    c.baseline_load_history = [0.145]
    c.nachtlast_per_apparaat = {"2026-10-27": {
        "sensor.eufy_homebase_s380_power": 6.0,
        "sensor.all_standby_power": 2.3,
        "sensor.groep_power": 9.0,
        "sensor.vreemd": 20.0,
    }}
    c.nilm_confirmed_devices = {}
    hass.states.set("sensor.groep_power", "9", {"entities": ["sensor.a"]})
    platform = {"sensor.eufy_homebase_s380_power": "powercalc", "sensor.all_standby_power": "powercalc",
                "sensor.groep_power": "powercalc", "sensor.vreemd": "template"}
    c._entiteitenregister = lambda: SimpleNamespace(
        async_get=lambda e: SimpleNamespace(platform=platform.get(e)))
    v = c.get_sluipverbruik_verklaring(nu)
    assert [a["entiteit"] for a in v["apparaten"]] == ["sensor.eufy_homebase_s380_power"]
    assert v["verklaard_w"] == 6.0
