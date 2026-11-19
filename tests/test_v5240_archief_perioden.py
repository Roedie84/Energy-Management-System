"""v5.240.0: het dagarchief per week, maand en jaar.

Ruud 19-11: "Kunnen we hiervoor ook een week, maand en jaar archief maken".
"""
import time
from datetime import date, timedelta
from pathlib import Path

from custom_components.energy_management_system import dagarchief as D

BASIS = Path(__file__).parent.parent / "custom_components" / "energy_management_system"


def _archief(van: date, dagen: int, gat=()):
    uit = {"dagen": {}}
    for i in range(dagen):
        d = van + timedelta(days=i)
        if d in gat:
            continue
        uit["dagen"][d.isoformat()] = {"v": 10.0, "p": 4.0, "i": 7.0, "e": 1.0, "l": 3.0, "o": 2.5,
                                       "k": 2.0, "kz": 2.5, "b": 0.5, "pg": 30.0 + (i % 2), "t": 8.0, "b_": "m"}
    return uit


def test_week_loopt_van_maandag_tot_zondag():
    a = _archief(date(2026, 11, 2), 14)   # ma 2-11 t/m zo 15-11
    weken = D.per_periode(a, "week", date(2026, 11, 19))
    assert [w["periode"] for w in weken] == ["2026-W45", "2026-W46"]
    w = weken[0]
    assert w["van"] == "2026-11-02" and w["tot"] == "2026-11-08" and w["label"] == "wk 45 '26"
    assert w["dagen"] == 7 and w["dagen_mogelijk"] == 7 and w["lopend"] is False
    assert w["verbruik_kwh"] == 70.0 and w["zon_kwh"] == 28.0 and w["netafname_kwh"] == 49.0
    assert w["teruglevering_kwh"] == 7.0 and w["kosten_eur"] == 14.0 and w["accu_opbrengst_eur"] == 3.5
    assert w["kosten_zonder_accu_eur"] == 17.5 and w["accu_geladen_kwh"] == 21.0 and w["accu_ontladen_kwh"] == 17.5
    assert w["prijs_gem_ct"] in (30.4, 30.6) and w["temp_c"] == 8.0
    assert w["zelfvoorziening_procent"] == 30.0   # (4 - 1) / 10


def test_lopende_periode_telt_tot_en_met_gisteren():
    a = _archief(date(2026, 11, 1), 18)   # t/m 18-11
    maanden = D.per_periode(a, "maand", date(2026, 11, 19))
    m = maanden[-1]
    assert m["periode"] == "2026-11" and m["label"] == "nov '26" and m["lopend"] is True
    assert m["dagen"] == 18 and m["dagen_mogelijk"] == 18 and m["tot"] == "2026-11-30"
    week = D.per_periode(a, "week", date(2026, 11, 19))[-1]
    assert week["periode"] == "2026-W47" and week["dagen"] == 3 and week["dagen_mogelijk"] == 3


def test_gaten_zijn_te_zien():
    a = _archief(date(2026, 10, 1), 31, gat={date(2026, 10, 10), date(2026, 10, 11)})
    a["dagen"]["2026-10-20"] = {"b_": "m", "pg": 31.0}    # geen meting: telt niet
    m = D.per_periode(a, "maand", date(2026, 11, 19))[0]
    assert m["dagen"] == 28 and m["dagen_mogelijk"] == 31 and m["verbruik_kwh"] == 280.0


def test_jaar_en_de_jaarwissel():
    a = _archief(date(2025, 12, 22), 21)   # over de jaarwissel
    jaren = D.per_periode(a, "jaar", date(2026, 11, 19))
    assert [j["periode"] for j in jaren] == ["2025", "2026"]
    assert jaren[0]["dagen"] == 10 and jaren[0]["lopend"] is False and jaren[0]["dagen_mogelijk"] == 365
    assert jaren[1]["dagen"] == 11 and jaren[1]["lopend"] is True
    # ISO-week 1 van 2026 begint op maandag 29-12-2025
    weken = D.per_periode(a, "week", date(2026, 11, 19))
    assert weken[1]["periode"] == "2026-W01" and weken[1]["van"] == "2025-12-29" and weken[1]["dagen"] == 7


def test_aantallen_en_onbekende_soort():
    a = _archief(date(2024, 1, 1), 1050)
    assert len(D.per_periode(a, "week", date(2026, 11, 19))) == D.PERIODEN_WEKEN
    assert len(D.per_periode(a, "maand", date(2026, 11, 19))) == D.PERIODEN_MAANDEN
    assert len(D.per_periode(a, "jaar", date(2026, 11, 19))) == 3
    assert D.per_periode(a, "kwartaal") == [] and D.per_periode({}, "week") == []
    assert len(D.per_periode(a, "maand", aantal=3)) == 3


def test_ontbrekende_velden_breken_niets():
    a = {"dagen": {"2026-11-10": {"v": 9.0}, "kapot": {"v": 1.0}}}
    w = D.per_periode(a, "week", date(2026, 11, 19))[0]
    assert w["verbruik_kwh"] == 9.0 and w["prijs_gem_ct"] is None and "zon_kwh" not in w
    assert "zelfvoorziening_procent" not in w


def test_snel_genoeg_voor_elke_ronde():
    a = _archief(date(2017, 1, 1), 3600)
    t0 = time.perf_counter()
    for soort in ("week", "maand", "jaar"):
        D.per_periode(a, soort, date(2026, 11, 19))
    assert time.perf_counter() - t0 < 0.25


def test_in_de_sensor(make_coordinator):
    c = make_coordinator({})
    c.dagarchief = _archief(date(2026, 10, 1), 45)
    uit = c.get_dagarchief()
    assert set(uit["perioden"]) == {"week", "maand", "jaar"}
    assert uit["perioden"]["maand"][0]["periode"] == "2026-10"
    assert uit["per_maand"]   # het oude attribuut blijft


def test_cockpit_toont_het_archief():
    js = (BASIS / "www" / "ems-cockpit.js").read_text()
    assert "_archiefPerioden()" in js and 'data-archief="' in js
    assert '"Archief per week, maand en jaar"' in js
    assert all(ord(c) < 128 for c in js)


# --- v5.241.0: verbruik tegen vorig jaar ------------------------------------

def _twee_jaar():
    a = {"dagen": {}}
    for i in range(30):   # november 2025: 10 kWh per dag, kouder
        a["dagen"][(date(2025, 11, 1) + timedelta(days=i)).isoformat()] = {"v": 10.0, "gd": 12.0}
    for i in range(18):   # november 2026 t/m de 18e: 11 kWh per dag
        a["dagen"][(date(2026, 11, 1) + timedelta(days=i)).isoformat()] = {"v": 11.0, "gd": 10.0}
    return a


def test_lopende_maand_vergelijkt_dezelfde_dagen():
    m = D.per_periode(_twee_jaar(), "maand", date(2026, 11, 19))[-1]
    vj = m["vorig_jaar"]
    assert m["verbruik_kwh"] == 198.0
    assert vj["dagen"] == 18 and vj["verbruik_kwh"] == 180.0 and vj["verbruik_zelfde_dagen_kwh"] == 198.0
    assert vj["verschil_kwh"] == 18.0 and vj["verschil_procent"] == 10.0
    assert vj["graaddagen_verschil"] == -36.0   # dit jaar warmer


def test_week_vergelijkt_dezelfde_weekdagen():
    a = _twee_jaar()
    w = D.per_periode(a, "week", date(2026, 11, 19))[-2]   # wk 46: ma 9 t/m zo 15-11-2026
    assert w["periode"] == "2026-W46" and w["vorig_jaar"]["dagen"] == 7
    assert w["vorig_jaar"]["verbruik_kwh"] == 70.0 and w["vorig_jaar"]["verschil_procent"] == 10.0
    # 364 dagen terug: maandag 9-11-2026 hoort bij maandag 10-11-2025
    assert D._dag_vorig_jaar(date(2026, 11, 9), "week") == date(2025, 11, 10)
    assert D._dag_vorig_jaar(date(2026, 11, 9), "week").weekday() == 0


def test_jaar_en_ontbrekend_vorig_jaar():
    a = _twee_jaar()
    jaren = D.per_periode(a, "jaar", date(2026, 11, 19))
    assert "vorig_jaar" not in jaren[0]            # 2024 staat niet in het archief
    assert jaren[1]["vorig_jaar"]["dagen"] == 18 and jaren[1]["vorig_jaar"]["verschil_procent"] == 10.0
    assert D._dag_vorig_jaar(date(2024, 2, 29), "maand") is None


def test_gat_in_vorig_jaar_telt_alleen_de_gedeelde_dagen():
    a = _twee_jaar()
    del a["dagen"]["2025-11-05"]
    a["dagen"]["2025-11-06"] = {"gd": 12.0}    # geen meting
    vj = D.per_periode(a, "maand", date(2026, 11, 19))[-1]["vorig_jaar"]
    assert vj["dagen"] == 16 and vj["verbruik_kwh"] == 160.0 and vj["verbruik_zelfde_dagen_kwh"] == 176.0


def test_cockpit_toont_vorig_jaar():
    js = (BASIS / "www" / "ems-cockpit.js").read_text()
    assert "Vorig jaar</th>" in js and "Verschil</th>" in js and "r.vorig_jaar" in js
    assert all(ord(c) < 128 for c in js)
