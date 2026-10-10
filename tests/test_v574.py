"""v5.74 (verbruiksaudit 30-09..10-10, akkoord Ruud).

1. Eerlijke besparingsmaatstaf per witgoedbeurt: tegen een gemiddeld en het
   goedkoopste haalbare moment (06:00-23:00), eigen zon niet gratis zolang
   salderen geldt. Het oude "uitstel leverde op" (tegen het duurste venster)
   is verouderd.
2. Het uurprofiel is voor energiesommen het gemiddelde, niet de mediaan -
   met de leave-one-day-out toets van de audit op de gemeten dagen.
3. Sluipverbruik: elke dag precies één keer afgesloten, ook na herstarts of
   een gemiste middernacht; de reeks uit de recorder aangevuld.
4. Tekortnachten: geen datumverschuiving, wel een definitiefout in de
   herbeoordeling van oude records (alle netafname in plaats van netafname
   met een lege accu).
"""
import asyncio
import json
import statistics
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.energy_management_system import coordinator as mod
from custom_components.energy_management_system.const import (
    CUSUM_MIN_HISTORY_FOR_REFERENCE,
    SLUIPVERBRUIK_METHODE_VERSIE,
)

TZ = timezone(timedelta(hours=2))
DAG = "2026-10-08"
FIXTURE = Path(__file__).parent / "fixtures" / "v574_uurprofiel.json"


# --- 1. de eerlijke maatstaf ---------------------------------------------


def _dagverloop(c, zon_uren=(11, 16)):
    """'s Nachts het goedkoopst (20 ct, maar niet haalbaar), ochtend 40 ct,
    middag 25 ct met zonoverschot, avond 35 ct."""
    regels = []
    for k in range(96):
        uur = k // 4
        prijs = 20.0 if uur < 6 else 40.0 if uur < 11 else 25.0 if uur < 17 else 35.0
        zon = 2500.0 if zon_uren[0] <= uur < zon_uren[1] else 0.0
        regels.append({
            "tijd": f"{uur:02d}:{(k % 4) * 15:02d}", "pv_w": zon, "huis_w": 300.0,
            "net_w": 300.0 - zon, "soc": 50.0, "prijs_ct": prijs,
        })
    c.dagverloop = {DAG: regels}


def _beurt(c, uur=13, salderen_tot="2026-12-31"):
    c.config = {**(c.config or {}), "salderen_end_date": salderen_tot}
    start = datetime(2026, 10, 8, uur, 0, tzinfo=TZ)
    return c.cycluskosten("wasmachine", start, start + timedelta(hours=1), 1.0)


def test_zon_is_niet_gratis_zolang_salderen_geldt(make_coordinator):
    c = make_coordinator({})
    _dagverloop(c)
    uit = _beurt(c)
    assert uit["salderen"] is True
    assert uit["netkosten_eur"] == pytest.approx(0.0, abs=0.001)
    assert uit["kosten_eur"] == pytest.approx(0.25, abs=0.001)  # zon tegen 25 ct
    assert uit["eigen_opwek_eur"] == pytest.approx(0.0, abs=0.001)


def test_na_salderen_telt_de_zon_tegen_de_terugleverwaarde(make_coordinator):
    c = make_coordinator({})
    _dagverloop(c)
    c._get_feedin_value_per_kwh = lambda entries, now: 0.07
    uit = _beurt(c, salderen_tot="2026-01-01")
    assert uit["salderen"] is False
    assert uit["kosten_eur"] == pytest.approx(0.07, abs=0.001)
    assert uit["eigen_opwek_eur"] == pytest.approx(0.18, abs=0.001)


def test_tegen_een_gemiddeld_en_het_goedkoopste_haalbare_moment(make_coordinator):
    """Haalbaar: start 06:00-23:00, klaar voor middernacht. De nacht van
    20 ct telt niet mee; het goedkoopste haalbare is de middag (25 ct)."""
    c = make_coordinator({})
    _dagverloop(c)
    uit = _beurt(c)
    # starts 06:00..23:00 met 4 kwartieren, klaar voor 24:00 (laatste 23:00)
    prijzen = [40.0] * 20 + [25.0] * 24 + [35.0] * 25
    vensters = []
    for i in range(24, 93):  # 06:00 .. 23:00
        venster = [
            (20.0 if j < 24 else 40.0 if j < 44 else 25.0 if j < 68 else 35.0)
            for j in range(i, i + 4)
        ]
        vensters.append(sum(venster) / 4 / 100)
    assert uit["gemiddeld_moment_eur"] == pytest.approx(statistics.mean(vensters), abs=0.001)
    assert uit["goedkoopste_haalbaar_moment"] == "11:00"
    assert uit["goedkoopste_haalbaar_eur"] == pytest.approx(0.25, abs=0.001)
    assert uit["verschil_tov_goedkoopste_eur"] == pytest.approx(0.0, abs=0.001)
    assert uit["besparing_tov_gemiddeld_eur"] == pytest.approx(
        statistics.mean(vensters) - 0.25, abs=0.002
    )
    # het oude getal blijft (verouderd) en is altijd positief
    assert uit["uitstel_leverde_op_eur"] == pytest.approx(0.40 - 0.25, abs=0.001)
    assert prijzen  # alleen ter documentatie


def test_een_beurt_op_een_duur_moment_toont_wat_er_gemist_is(make_coordinator):
    c = make_coordinator({})
    _dagverloop(c)
    uit = _beurt(c, uur=8)
    assert uit["kosten_eur"] == pytest.approx(0.40, abs=0.001)
    assert uit["verschil_tov_goedkoopste_eur"] == pytest.approx(-0.15, abs=0.001)
    assert uit["besparing_tov_gemiddeld_eur"] < 0


def test_overzicht_met_eerlijke_totalen_en_verouderd_veld(make_coordinator):
    c = make_coordinator({})
    _dagverloop(c)
    c.config = {"salderen_end_date": "2026-12-31"}
    c.cycluskosten_geschiedenis = {}
    start = datetime(2026, 10, 8, 8, 0, tzinfo=TZ)
    c.noteer_cycluskosten("wasmachine", start, start + timedelta(hours=1), 1.0)
    o = c.get_cycluskosten_overzicht()["wasmachine"]
    assert o["verschil_tov_goedkoopste_eur_totaal"] == pytest.approx(-0.15, abs=0.01)
    assert "besparing_tov_gemiddeld_eur_totaal" in o
    assert o["verouderd"] == ["uitstel_leverde_op_eur_totaal"]
    assert "uitstel_leverde_op_eur_totaal" in o


def test_een_oude_beurt_wordt_herberekend_uit_het_dagverloop(make_coordinator):
    c = make_coordinator({})
    _dagverloop(c)
    c.config = {"salderen_end_date": "2026-12-31"}
    start = datetime(2026, 10, 8, 10, 30, tzinfo=TZ)
    # een beurt van vóór v5.74: 45 minuten (40, 40 en 25 ct), zonder
    # eindtijd en maatstaf
    oud = {
        "te_becijferen": True, "apparaat": "vaatwasser", "moment": start.isoformat(),
        "kwh": 0.9, "kosten_eur": 0.315, "op_netstroom_eur": 0.315,
        "eigen_opwek_eur": 0.0, "uitstel_leverde_op_eur": 0.0,
    }
    weg = {**oud, "moment": "2026-09-01T08:00:00+02:00"}
    c.cycluskosten_geschiedenis = {"vaatwasser": [weg, oud]}

    assert c._herbereken_oude_cyclusbeurten() == 1

    nieuw = c.cycluskosten_geschiedenis["vaatwasser"][1]
    assert nieuw["maatstaf"] == "v5.74" and nieuw["herberekend"] == "v5.74"
    assert nieuw["einde"] == (start + timedelta(minutes=45)).isoformat()
    # geen dagverloop meer: blijft zoals hij was, gemarkeerd als oud
    assert c.cycluskosten_geschiedenis["vaatwasser"][0]["maatstaf"] == "oud"
    assert c._herbereken_oude_cyclusbeurten() == 0


def test_de_kaart_toont_de_eerlijke_maatstaf():
    import custom_components.energy_management_system as pkg

    kaart = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    assert "besparing_tov_gemiddeld_eur_totaal" in kaart
    assert "verschil_tov_goedkoopste_eur_totaal" in kaart


# --- 2. het uurprofiel: gemiddelde voor energiesommen ---------------------


def _lodo(make_coordinator, maat):
    """Leave-one-day-out zoals b5_profiel.py van de audit: per weggelaten dag
    het profiel uit de andere dagen, en de voorspelling van die dag en van de
    avond+nacht (17-07)."""
    data = json.loads(FIXTURE.read_text())
    dagen = sorted(data["dagen"])
    dagfout, avondfout = [], []
    for d in dagen:
        c = make_coordinator({})
        c.hourly_consumption_profile = {
            uur: [data["dagen"][x][uur] / 1000 for x in dagen if x != d]
            for uur in range(24)
        }
        profiel = [maat(c, uur) for uur in range(24)]
        dagfout.append(sum(data["dagen"][d]) / 1000 - sum(profiel))
        if d in data["avond_17_07_kwh"]:
            voorspeld = sum(profiel[(17 + k) % 24] for k in range(14))
            avondfout.append(data["avond_17_07_kwh"][d] - voorspeld)
    return dagfout, avondfout


def test_leave_one_day_out_gemiddelde_beter_dan_mediaan(make_coordinator):
    gem_dag, gem_avond = _lodo(make_coordinator, lambda c, u: c.learned_hourly_avg_kw(u))
    med_dag, med_avond = _lodo(make_coordinator, lambda c, u: c.learned_hourly_median_kw(u))

    mae = lambda fouten: sum(abs(f) for f in fouten) / len(fouten)  # noqa: E731
    bias = lambda fouten: sum(fouten) / len(fouten)  # noqa: E731
    # dagtotaal: de audit mat 0,84 -> 0,65 kWh, bias 0,53 -> 0,00
    assert mae(gem_dag) < mae(med_dag)
    assert mae(gem_dag) == pytest.approx(0.65, abs=0.02)
    assert abs(bias(gem_dag)) < 0.02
    assert bias(med_dag) == pytest.approx(0.53, abs=0.02)
    # avond en nacht (de basis van de reserve): nauwelijks anders. De
    # reserve stijgt hooguit ~0,07 kWh, binnen de spreiding (MAE ~0,4).
    assert bias(gem_avond) == pytest.approx(-0.088, abs=0.02)
    assert abs(bias(gem_avond) - bias(med_avond)) < 0.1
    assert mae(gem_avond) <= mae(med_avond) + 0.01


def test_monte_carlo_centrum_volgt_het_gemiddelde(make_coordinator):
    c = make_coordinator({})
    c.hourly_consumption_profile = {3: [0.2, 0.2, 0.2, 0.2, 0.8]}
    c._segmenten_verbruik_zon = lambda *a, **k: None
    c._estimate_pv_kwh_for_period = lambda *a, **k: 0.0
    eind = datetime(2026, 10, 9, 4, 0, tzinfo=TZ)
    _f, centrum, _w = c._monte_carlo_centrum(
        eind - timedelta(hours=1), eind, [(3, 1.0, eind)], 0.9
    )
    assert centrum[0][0] == pytest.approx(0.32)


def test_de_dagtype_proefstand_vergelijkt_mediaan_met_mediaan(make_coordinator):
    bron = Path(mod.__file__).read_text()
    assert "algemeen = self.learned_hourly_median_kw(uur)" in bron


# --- 3. sluipverbruik ----------------------------------------------------


def _coord(make_coordinator):
    c = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    c.sluipverbruik_methode_versie = SLUIPVERBRUIK_METHODE_VERSIE
    return c


def _kwartier(c, hass, moment, watt):
    hass.states.set("sensor.p1", str(watt))
    for m in range(6):
        c._update_anomaly_detection(moment + timedelta(minutes=m))


def test_een_gemiste_middernacht_sluit_de_dag_toch_af(make_coordinator, hass):
    """Geen ronde rond middernacht (herstart, lege prijsreeks): de volgende
    ronde sluit de vorige dag alsnog af - één keer."""
    c = _coord(make_coordinator)
    _kwartier(c, hass, datetime(2026, 10, 9, 3, 0, tzinfo=TZ), 145)
    _kwartier(c, hass, datetime(2026, 10, 9, 14, 0, tzinfo=TZ), 400)
    _kwartier(c, hass, datetime(2026, 10, 10, 8, 0, tzinfo=TZ), 300)
    assert c.baseline_load_history == [0.145]
    assert c.vloer_afgesloten_tot == "2026-10-09"
    _kwartier(c, hass, datetime(2026, 10, 10, 9, 0, tzinfo=TZ), 300)
    assert c.baseline_load_history == [0.145]


def test_een_herstart_met_een_oude_opslag_telt_geen_dag_dubbel(make_coordinator, hass):
    c = _coord(make_coordinator)
    _kwartier(c, hass, datetime(2026, 10, 9, 3, 0, tzinfo=TZ), 145)
    opslag = json.loads(json.dumps(c._collect_persisted_state(), default=str))
    _kwartier(c, hass, datetime(2026, 10, 10, 3, 0, tzinfo=TZ), 130)
    c._update_anomaly_detection(datetime(2026, 10, 10, 3, 15, tzinfo=TZ))
    assert c.baseline_load_history == [0.145]
    na = json.loads(json.dumps(c._collect_persisted_state(), default=str))

    verse = _coord(make_coordinator)
    verse._apply_persisted_state(na)
    # de opslag van vóór middernacht nog eens erover (herstel na de sensoren)
    verse._apply_persisted_state({**na, "baseline_load_history": [0.145]})
    _kwartier(verse, hass, datetime(2026, 10, 10, 4, 0, tzinfo=TZ), 300)
    assert verse.baseline_load_history == [0.145]
    _kwartier(verse, hass, datetime(2026, 10, 11, 4, 0, tzinfo=TZ), 300)
    assert verse.baseline_load_history == [0.145, 0.13]
    assert "vloer_afgesloten_tot" in opslag


def test_de_overgang_van_het_oude_model(make_coordinator, hass):
    """Een opslag van vóór v5.74: één datum en één minimum."""
    c = _coord(make_coordinator)
    c._cusum_check_date = date(2026, 10, 9)
    c._today_min_load_kw = 0.15
    c.vloer_dagminima = {}
    _kwartier(c, hass, datetime(2026, 10, 10, 3, 0, tzinfo=TZ), 140)
    assert c.baseline_load_history == [0.15]


def test_de_migratie_wist_ook_de_lopende_dag_uit_de_opslag(make_coordinator):
    c = make_coordinator({})
    c.sluipverbruik_methode_versie = 1
    c._geladen_opslag = {
        "_today_min_load_kw": -0.4, "_cusum_check_date": "2026-10-07",
        "vloer_dagminima": {"2026-10-07": -0.4}, "vloer_afgesloten_tot": "2026-10-06",
    }
    c._migreer_sluipverbruik_methode()
    for sleutel in ("_today_min_load_kw", "_cusum_check_date", "vloer_dagminima", "vloer_afgesloten_tot"):
        assert sleutel not in c._geladen_opslag
    assert c._cusum_check_date is None and c.vloer_dagminima == {}


def _statistieken(dagen=10, nacht_w=150.0, piek=True):
    """5-minutenstatistieken: P1, accu (omgekeerd teken) en zon."""
    rijen = {"sensor.p1": [], "sensor.accu": [], "sensor.zon": []}
    start = datetime(2026, 10, 10, 0, 0, tzinfo=TZ) - timedelta(days=dagen)
    t = start
    while t < datetime(2026, 10, 10, 0, 0, tzinfo=TZ):
        nacht = 2 <= t.hour < 5
        huis = nacht_w + (t.day % 3) * 5 if nacht else 400.0
        accu = 0.0
        if piek and nacht and t.minute == 10:
            accu = 2200.0  # een wisselpiek: 5-min gemiddelde zakt fors
        # huis = p1 + (-accu_sensor) + zon, met omgekeerd teken
        rijen["sensor.p1"].append({"start": t, "mean": huis - accu})
        rijen["sensor.accu"].append({"start": t, "mean": -accu})
        rijen["sensor.zon"].append({"start": t, "mean": 0.0})
        t += timedelta(minutes=5)
    return rijen


def test_vloer_uit_de_statistieken(make_coordinator):
    c = make_coordinator({"invert_battery_power_sign": True})
    dagen = c._vloer_uit_statistieken(
        _statistieken(), {}, "sensor.p1", "sensor.accu", "sensor.zon", date(2026, 10, 10)
    )
    assert len(dagen) == 10
    assert dagen[0][0] == "2026-09-30"
    assert all(0.149 <= w <= 0.161 for _d, w in dagen)


def test_vloer_bootstrap_uit_de_recorder(make_coordinator, monkeypatch):
    c = make_coordinator({
        "consumption_power_sensor_entity": "sensor.p1",
        "battery_power_sensor_entity": "sensor.accu",
        "pv_power_sensor_entity": "sensor.zon",
        "invert_battery_power_sign": True,
    })
    c.baseline_load_history = [0.1448, 0.1265]

    class _Instance:
        async def async_add_executor_job(self, func, *args):
            return func(*args)

    rijen = _statistieken()
    monkeypatch.setitem(sys.modules, "homeassistant.components.recorder", SimpleNamespace(
        get_instance=lambda hass: _Instance()))
    monkeypatch.setitem(sys.modules, "homeassistant.components.recorder.statistics", SimpleNamespace(
        get_metadata=lambda hass, statistic_ids=None: {},
        statistics_during_period=lambda *a, **k: rijen))
    monkeypatch.setattr(mod.dt_util, "now", lambda: datetime(2026, 10, 10, 13, 0, tzinfo=TZ))
    monkeypatch.setattr(mod.dt_util, "start_of_local_day",
                        lambda d: datetime.combine(d, time(), tzinfo=TZ), raising=False)

    aantal = asyncio.run(c.async_bootstrap_vloer_uit_recorder())

    assert aantal == 10
    assert len(c.baseline_load_history) == 10
    assert len(c.baseline_load_history) >= CUSUM_MIN_HISTORY_FOR_REFERENCE
    assert 149 <= c.sluipverbruik_reference_w <= 161
    assert c.vloer_afgesloten_tot == "2026-10-09"
    assert c.vloer_bootstrap["dagen"][-1] == "2026-10-09"
    # met een volle reeks doet hij niets meer
    assert asyncio.run(c.async_bootstrap_vloer_uit_recorder()) == 0


def test_zonder_recorder_niets(make_coordinator, monkeypatch):
    c = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    monkeypatch.setitem(sys.modules, "homeassistant.components.recorder", None)
    assert asyncio.run(c.async_bootstrap_vloer_uit_recorder()) == 0


# --- 4. tekortnachten ------------------------------------------------------


def _nacht(c, dag: str, rijen_avond, rijen_ochtend):
    vorige = (date.fromisoformat(dag) - timedelta(days=1)).isoformat()
    c.dagverloop = {vorige: rijen_avond, dag: rijen_ochtend}


def _rij(tijd, soc, net_w, reden="default_smart"):
    return {"tijd": tijd, "soc": soc, "net_w": net_w, "reden": reden}


def _kwartieren(van_uur, tot_uur):
    for uur in range(van_uur, tot_uur):
        for m in (0, 15, 30, 45):
            yield f"{uur:02d}:{m:02d}"


def test_03_10_geen_tekortnacht_netafname_was_niet_met_een_lege_accu(make_coordinator):
    """Het gemeten geval: 's nachts wat netafname met de accu boven de vloer,
    pas om 07:45 op de vloer en dan nauwelijks iets van het net."""
    c = make_coordinator({})
    c.effective_min_soc_percent = lambda: 10.0
    avond = [_rij(t, 30, 150) for t in _kwartieren(22, 24)]
    ochtend = [_rij(t, 20 if t < "07:45" else 9, 100 if t < "07:45" else 10) for t in _kwartieren(0, 9)]
    _nacht(c, "2026-10-03", avond, ochtend)
    c.reserve_daily_records = [{
        "date": "2026-10-03", "shortfall": True, "laagste_soc_ochtend": 9,
        "netimport_nacht_kwh": 0.68, "excess": False, "tekort_soort": "onbekend",
    }]

    c._herbeoordeel_tekortdagen()

    r = c.reserve_daily_records[0]
    assert r["shortfall"] is False
    assert r["herbeoordeeld"] == "v5.74"
    assert r["tekortnacht_kwh"] == pytest.approx(0.01, abs=0.01)
    assert c.get_tekortsoorten()["tekort_soort_per_nacht"] == [None]


def test_04_10_blijft_een_tekortnacht(make_coordinator):
    """Leeg vanaf 01:35, 1,4 kWh van het net: een echte tekortnacht."""
    c = make_coordinator({})
    c.effective_min_soc_percent = lambda: 10.0
    avond = [_rij(t, 25, 0) for t in _kwartieren(22, 24)]
    ochtend = [_rij(t, 9 if t >= "01:30" else 15, 190 if t >= "01:30" else 0) for t in _kwartieren(0, 9)]
    _nacht(c, "2026-10-04", avond, ochtend)
    c.reserve_daily_records = [{
        "date": "2026-10-04", "shortfall": True, "laagste_soc_ochtend": 9,
        "netimport_nacht_kwh": 1.68, "excess": False,
    }]

    c._herbeoordeel_tekortdagen()

    r = c.reserve_daily_records[0]
    assert r["shortfall"] is True
    assert r["tekortnacht_kwh"] == pytest.approx(1.4, abs=0.1)
    assert "herbeoordeeld" not in r


def test_bewuste_netafname_telt_niet(make_coordinator):
    c = make_coordinator({})
    c.effective_min_soc_percent = lambda: 10.0
    _nacht(c, "2026-10-05", [], [_rij(t, 9, 2000, "grid_charging_dip") for t in _kwartieren(0, 9)])
    assert c._tekortnacht_uit_verloop("2026-10-05", 13.0) == 0.0


def test_te_dun_dagverloop_dan_de_oude_benadering(make_coordinator):
    c = make_coordinator({})
    c.effective_min_soc_percent = lambda: 10.0
    c.dagverloop = {}
    c.reserve_daily_records = [{
        "date": "2026-10-02", "shortfall": False, "laagste_soc_ochtend": 9,
        "netimport_nacht_kwh": 2.4, "excess": False,
    }]
    c._herbeoordeel_tekortdagen()
    assert c.reserve_daily_records[0]["shortfall"] is True
    assert c.reserve_daily_records[0]["herbeoordeeld"] == "v5.33"


def test_de_datum_is_de_ochtend_van_de_nacht():
    """Geen datumverschuiving: het record van een dag is de nacht die op die
    ochtend om 09:00 afliep. De sensor zegt dat er nu bij."""
    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()
    assert '"datum_betekenis"' in bron
