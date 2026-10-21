"""v5.115.1 (L-EMS-027): verkoop per dag blijvend in het dagarchief, en een
"sprong" waarbij alleen de behoefte verandert telt niet als reservesprong.

Leerronde 21-10 19:40: de harde regel (nooit onder de verkoopreserve
verkopen) was voor 14..19-10 niet meer te toetsen, en `reserve_sprongen`
telde 29x terwijl de reserve gelijk bleef (10,37, afgekapt) en alle
bijdragen 0 waren.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import dagarchief as D

TZ = timezone.utc


def _kwartieren(n=96, verkoop=()):
    rijen = [{"tijd": f"{i // 4:02d}:{i % 4 * 15:02d}", "verkocht": False} for i in range(n)]
    for i, kwh, marge in verkoop:
        rijen[i].update(verkocht=True, export_uit_accu_kwh=kwh, marge_bij_export_min_kwh=marge)
    return rijen


def test_verkoop_van_dag():
    uit = D.verkoop_van_dag(_kwartieren(verkoop=[(70, 0.4, 1.2), (71, 0.5, -0.1), (72, 0.3, 0.6)]))
    assert uit == {"vk": 1.2, "vkm": -0.1, "vko": 1}


def test_geen_verkoop_is_nul_en_geen_marge():
    assert D.verkoop_van_dag(_kwartieren()) == {"vk": 0.0, "vkm": None, "vko": 0}


def test_regeloverschot_telt_niet():
    rijen = _kwartieren()
    rijen[50].update(verkocht=False, export_uit_accu_kwh=0.02, marge_bij_export_min_kwh=-0.5)
    assert D.verkoop_van_dag(rijen)["vko"] == 0


def test_oudere_kwartieren_zonder_vlag_tellen_op_de_marge():
    rijen = [{"tijd": str(i)} for i in range(96)]
    rijen[10]["marge_bij_export_min_kwh"] = -0.2
    rijen[10]["export_uit_accu_kwh"] = 0.3
    assert D.verkoop_van_dag(rijen) == {"vk": 0.3, "vkm": -0.2, "vko": 1}


def test_onvolledige_dag_geen_uitspraak():
    assert D.verkoop_van_dag(_kwartieren(n=40)) is None


def test_velden_overleven_een_nieuwe_meting_en_zijn_uitgeschreven():
    archief = D.leeg()
    D.zet(archief, "2026-10-20", {"v": 10.0, "b_": "m"})
    archief["dagen"]["2026-10-20"].update({"vk": 1.2, "vkm": -0.1, "vko": 1})
    D.zet(archief, "2026-10-20", {"v": 11.0, "b_": "m"})
    dag = archief["dagen"]["2026-10-20"]
    assert (dag["vk"], dag["vkm"], dag["vko"], dag["v"]) == (1.2, -0.1, 1, 11.0)
    uit = D.uitgeschreven(dag)
    assert uit["verkocht_kwh"] == 1.2 and uit["kwartieren_onder_verkoopreserve"] == 1


def _uits(reserve, nodig, lh=0.0):
    return {"ronde": 1, "reserve_kwh_after_margin": reserve,
            "needed_kwh_before_margin": nodig, "regelverschuiving_w": 0,
            "lange_horizon_extra_kwh": lh, "airco_ochtend_extra_kwh": 0.0,
            "airco_gebruik_extra_kwh": 0.0, "temperatuur_extra_kwh": 0.0}


def test_alleen_behoefte_sprong_apart_geteld(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 21, 20, 0, tzinfo=TZ)
    c._started_at = nu - timedelta(hours=2)
    # 21-10: reserve afgekapt op 10,37, behoefte springt 1,4 kWh, bijdragen 0.
    c._noteer_reserve_sprong(nu, None, _uits(10.37, 8.0), _uits(10.37, 9.4))
    s = c.reserve_sprongen[0]
    assert s["alleen_behoefte"] is True
    assert s["grootste_onderdeel"] == "basisbehoefte"
    attr = c.sturing_meetattributen()
    assert attr["reserve_sprongen_aantal"] == 0
    assert attr["reserve_sprongen_alleen_behoefte"] == 1


def test_echte_reservesprong_blijft_tellen(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 21, 20, 0, tzinfo=TZ)
    c._started_at = nu - timedelta(hours=2)
    c._noteer_reserve_sprong(nu, None, _uits(5.0, 4.0, lh=0.0), _uits(6.0, 5.0, lh=1.0))
    s = c.reserve_sprongen[0]
    assert "alleen_behoefte" not in s
    assert s["grootste_onderdeel"] == "lange_horizon_extra_kwh"
    assert c.sturing_meetattributen()["reserve_sprongen_aantal"] == 1


def test_dagarchief_vult_verkoop_uit_het_dagverloop(make_coordinator):
    import asyncio

    c = make_coordinator({})
    c._dagarchief_kwartierdagen = lambda vandaag: {}
    c.dagarchief = {"dagen": {"2026-10-14": {"v": 9.0, "b_": "m"}, "2026-10-21": {"v": 1.0}},
                    "gezaaid": True, "zaai_versie": D.ZAAI_VERSIE}
    c.dagverloop = {
        "2026-10-14": _kwartieren(verkoop=[(76, 0.8, 0.4)]),
        "2026-10-21": _kwartieren(verkoop=[(76, 0.8, -0.4)]),   # vandaag: nog niet
        "2026-10-15": _kwartieren(),                            # niet in het archief
    }
    asyncio.run(c._async_dagarchief("2026-10-21"))
    dagen = c.dagarchief["dagen"]
    assert (dagen["2026-10-14"]["vk"], dagen["2026-10-14"]["vkm"], dagen["2026-10-14"]["vko"]) == (0.8, 0.4, 0)
    assert "vk" not in dagen["2026-10-21"]
    assert "2026-10-15" not in dagen
