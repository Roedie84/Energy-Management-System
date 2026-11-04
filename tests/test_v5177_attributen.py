"""v5.177.0 (A14) - zware attributen onder 16 kB."""
import json
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import sensor as S


def _pv():
    start = datetime(2026, 11, 4, tzinfo=timezone.utc)
    dagen = {}
    for d in range(7):
        datum = (start + timedelta(days=d + 1)).date().isoformat()
        dagen[datum] = {
            "gemiddeld_eur": 0.25, "vooruit_dagen": d + 1,
            "uren": [[f"{u:02d}", 25.123] for u in range(24)],
            "band": [[f"{u:02d}", 20.11, 30.22] for u in range(24)],
        }
    per_dag = [{"datum": f"2026-10-{i:02d}", "afwijking_ct": 2.123456, "zoals_gisteren_ct": 3.1} for i in range(1, 30)]
    return {
        "beschikbaar": True,
        "dagen": dagen,
        "kwartieren": {"start": "x", "stap_min": 15, "ct": [25.1234] * 736, "p10_ct": [20.1] * 736,
                       "p90_ct": [30.1] * 736, "verwacht_vanaf": 96},
        "band_voor_plan": [["2026-11-05T01", 20.1, 30.2]] * 160,
        "per_vooruit": [{"vooruit": 1}] * 7, "per_vooruit_basis": [{"vooruit": 1}] * 7,
        "nauwkeurigheid_live": {"d1": {"dagen": 20, "per_dag": per_dag}, "d2": {"dagen": 20, "per_dag": per_dag}},
        "backtest_21_dagen": {"dagen": 21, "per_dag": per_dag},
        "toelichting": "t" * 1200,
    }


def test_prijsverwachting_onder_16_kb():
    pv = _pv()
    voor = len(json.dumps(pv))
    na_attr = S.prijsverwachting_voor_de_sensor(pv)
    na = len(json.dumps(na_attr))
    assert voor > 30000 and na < 12000, (voor, na)
    # wat de cockpit leest blijft
    assert len(na_attr["kwartieren"]["ct"]) == 736 and na_attr["kwartieren"]["ct"][0] == 25.1
    assert len(na_attr["nauwkeurigheid_live"]["d1"]["per_dag"]) == 14
    assert na_attr["backtest_21_dagen"]["dagen"] == 21
    assert "gemiddeld_eur" in next(iter(na_attr["dagen"].values()))


def test_slank_rondt_af():
    assert S.slank({"a": [0.8403180511611329, {"b": 272.95900000000006}], "c": "x"}) == {
        "a": [0.84, {"b": 272.959}], "c": "x"}


def test_reservesprong_compact(make_coordinator, hass):
    c = make_coordinator({})
    r = {"tijd": "t", "ronde_oud": "a", "ronde_nieuw": "b", "total_percent": [25.0, 25.0],
         "reserve_kwh_after_margin": [9.356, 7.776], "bijdragen_kwh": {"x": 0.0, "y": 0.046}}
    kort = c._sprong_kort(r)
    assert kort == {"tijd": "t", "reserve_kwh_after_margin": [9.356, 7.776], "bijdragen_kwh": {"y": 0.046}}


def test_planregel_compact(make_coordinator, hass):
    c = make_coordinator({})
    r = c._compacte_planregel({"van": "08:00", "dag": "", "gewijzigd": False, "eerst_voorspeld": "smart",
                               "tekort": False, "modus": "smart"})
    assert r == {"van": "08:00", "modus": "smart"}
