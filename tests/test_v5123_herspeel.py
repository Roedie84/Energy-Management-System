"""v5.123.0 (23-10, punt 5): echte dagen opnieuw afspelen als regressietest.

Scoort per dag in euro's onder salderen en onder 2027: werkelijk, de
vastgelegde keuzes van de beslisboom door het accumodel, het scenarioplan
met kennis achteraf, best mogelijk (keuzeoordeel / repetitie) en gemist.
"""
import asyncio
import json
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system import herspeel as H


def _dag(stand_avond="smart", r27=0.06, met_soc=True):
    rijen = []
    for i in range(96):
        h = i // 4
        pv = 2400 if 10 <= h < 15 else 0
        accu = -1800 if 10 <= h < 14 else (700 if 17 <= h < 23 else 0)
        rijen.append({
            "tijd": f"{h:02d}:{(i % 4) * 15:02d}", "prijs_ct": 40 if 17 <= h < 21 else 22,
            "huis_w": 450, "pv_w": pv, "accu_w": accu, "soc": 40 if met_soc else None,
            "stand": stand_avond if h >= 17 else "smart", "reden": "x", "reserve_kwh": 2.0,
            "r27_export": r27,
        })
    return rijen


MODEL = dict(capaciteit_kwh=9.8, min_soc_procent=15, laad_kw=2.4, ontlaad_kw=2.4, rendement=0.85,
             slijtage_eur=0.03)


def test_modus_van_de_vastgelegde_stand():
    assert H.modus_van("manual", -0.4, 0.1) == "laden"
    assert H.modus_van("manual", 0.5, 0.1) == "verkopen"
    assert H.modus_van("smart_discharging", 0.1, 0.1) == "uitstellen"
    assert H.modus_van("smart_charging", 0.0, 0.1) == "sparen"
    assert H.modus_van(None, 0.0, 0.0) == "smart"


def test_score_dag_heeft_alle_strategieen_onder_beide_regimes():
    uit = H.herspeel({"2026-10-20": _dag()}, None, **MODEL)
    d = uit["dagen"][0]
    assert d["te_becijferen"] and d["met_2027"]
    for veld in H.SCOREVELDEN:
        assert d.get(veld) is not None, veld
    # met kennis achteraf is het scenarioplan nooit duurder dan de vastgelegde keuzes
    assert d["scenarioplan_salderen_eur"] <= d["beslisboom_salderen_eur"] + 1e-6
    assert d["scenarioplan_2027_eur"] <= d["beslisboom_2027_eur"] + 1e-6
    # 2027 is duurder dan salderen bij dezelfde dag (teruglevering is minder waard)
    assert d["werkelijk_2027_eur"] >= d["werkelijk_salderen_eur"]
    assert uit["samenvatting"]["dagen"] == 1


def test_zonder_teruglevertarief_alleen_salderen():
    uit = H.herspeel({"2026-10-20": _dag(r27=None)}, None, **MODEL)
    d = uit["dagen"][0]
    assert d["met_2027"] is False
    assert d.get("werkelijk_2027_eur") is None and d.get("werkelijk_salderen_eur") is not None


def test_te_korte_dag_telt_niet():
    uit = H.herspeel({"2026-10-20": _dag()[:40]}, None, **MODEL)
    assert uit["dagen"][0]["te_becijferen"] is False
    assert uit["samenvatting"]["dagen_overgeslagen"] == 1


def test_meetlaag_gaat_voor():
    gemeten = {"2026-10-20": {f"{h:02d}:{m:02d}": {"huis_kwh": 0.2, "pv_kwh": 0.0, "accu_kwh": 0.0}
                              for h in range(24) for m in (0, 15, 30, 45)}}
    d = H.herspeel({"2026-10-20": _dag()}, gemeten, **MODEL)["dagen"][0]
    assert d["uit_meetlaag"] == 96


def test_voor_en_na_vergelijken():
    """Een wijziging in de keuzes (de avond niet meer dekken) is per dag te zien."""
    oud = H.herspeel({"2026-10-20": _dag()}, None, **MODEL)
    nieuw = H.herspeel({"2026-10-20": _dag(stand_avond="smart_charging")}, None, **MODEL)
    v = H.vergelijk(oud, nieuw)
    assert v["dagen"] == 1
    assert v["verschil_per_veld_eur"]["beslisboom_salderen_eur"] > 0   # sparen in de dure avond kost geld
    assert v["grootste_verschillen"][0]["datum"] == "2026-10-20"


def test_tool_draait_zonder_home_assistant(tmp_path):
    import tools_herspeel as T

    bron = tmp_path / "opslag.json"
    bron.write_text(json.dumps({"data": {"dagverloop": {"2026-10-19": _dag(), "2026-10-20": _dag()}}}))
    oud = tmp_path / "oud.json"
    assert T.main([str(bron), "--uit", str(oud)]) == 0
    resultaat = json.loads(oud.read_text())
    assert resultaat["samenvatting"]["dagen"] == 2
    assert T.main([str(bron), "--vergelijk", str(oud)]) == 0


def test_tool_leest_de_meetlaag(tmp_path):
    import tools_herspeel as T
    from custom_components.energy_management_system import kwartierenergie

    start = datetime.fromisoformat("2026-10-20T00:00:00+02:00")
    regels = []
    for i in range(96):
        moment = start + timedelta(minutes=15 * i)
        rec = kwartierenergie.kwartier(
            moment,
            {t: {"waarde": 100.0, "vers": True, "leeftijd_s": 1} for t in kwartierenergie.TELLERS},
            {t: {"waarde": 100.1, "vers": True, "leeftijd_s": 1} for t in kwartierenergie.TELLERS},
            0.22,
        )
        regels.append(kwartierenergie.compact(rec))
    (tmp_path / "energy_management_system_meetlog_kwartier_20261020").write_text(
        json.dumps({"data": {"regels": regels}}))
    _H, K = T._laad_pure_modules()
    uit = T.meetlaag_uit_opslag(tmp_path, ["2026-10-20"], K)
    assert len(uit["2026-10-20"]) == 96


def test_coordinator_herspeelt_en_bewaart_per_versie(make_coordinator):
    c = make_coordinator({})
    from custom_components.energy_management_system import coordinator as mod

    gisteren = (mod.dt_util.now().date() - timedelta(days=1)).isoformat()   # dezelfde klok
    c.dagverloop = {gisteren: _dag()}
    c._gemeten_kwartieren = lambda d: {}
    c.bruikbare_capaciteit_kwh = lambda: 9.8
    c._manifest_versie = "5.123.0"
    asyncio.run(c._async_herspeel())
    assert c.herspeel_resultaat["samenvatting"]["dagen"] == 1
    assert "5.123.0" in c.herspeel_per_versie
    c._manifest_versie = "5.124.0"
    asyncio.run(c._async_herspeel())
    uit = c.get_herspeel()
    assert uit["laatste_twee_versies"]["oud"] == "5.123.0"
    assert uit["laatste_twee_versies"]["per_dag_verschil_eur"]["werkelijk_salderen_per_dag_eur"] == pytest.approx(0.0)
    assert c.get_zelfanalyse()["herspeel"]["versie"] == "5.124.0"
