"""v5.169.0 - rondrit-rendement verankerd op de kWh-meter van de accu.

Audit 03-11: het waardeplan rekende laden 81,9 % x ontladen 95,8 % = 78,5 %
heen en terug, het geleerde rendement 83,3 % x 96,0 % = 80,0 %. De
kWh-meter van de accu (HomeWizard) gaf over oktober AC -> AC ~85 %. Oorzaak:
ontladen in inhoud-eenheden (laadstand x 11,52) komt boven 1,0 uit (de
laadstand onderschat de AC-kant), en de code kapte dat op 1,0 af.

Hier: een reeks waarin de laadstand de AC-kant ~4 % onderschat (ontladen
inhoud -> AC = 1,04). Oud: laden 0,82 x ontladen afgekapt 1,0 = 82 %. Nieuw:
rondrit uit de tellerstanden ~85,3 %, ontladen = rondrit / laden = 1,04.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system import rondrit as R
from custom_components.energy_management_system import waardeplan as W
from tests._v5167_reeks import DAG0, bouw

ETA_L, ETA_O = 0.82, 1.04          # echte rondrit 0,8528


def _seg(dagen):
    seg = []
    for _ in range(dagen):
        seg += [(4, 0.0, 0.0), (12, -1800.0, 0.0), (6, 0.0, 0.0), (40, 300.0, 0.0), (8, 0.0, 0.0),
                (6, 1600.0, 0.0), (20, 0.0, 0.0)]
    return seg


def _meter(regels, gemeten):
    """Tellerstanden per heel uur (cumulatief) en de inhoud per moment, zoals
    de coordinator ze uit de uurstatistiek en het dagverloop haalt."""
    erin, eruit, inhoud = {}, {}, {}
    som_in = som_uit = 0.0
    for dag in sorted(regels):
        for r in sorted(regels[dag], key=lambda x: x["tijd"]):
            eind = datetime.fromisoformat(f"{dag}T{r['tijd']}") + timedelta(minutes=15)
            m = gemeten[dag][r["tijd"]]
            som_in += m["accu_in_kwh"]
            som_uit += m["accu_uit_kwh"]
            inhoud[eind] = r["beschikbaar_kwh"]
            if eind.minute == 0:
                erin[eind], eruit[eind] = som_in, som_uit
    return erin, eruit, inhoud


@pytest.fixture(scope="module")
def reeks16():
    regels, gemeten, ac_in, ac_uit = bouw(_seg(16), inhoud0=0.5, eta_l=ETA_L, eta_o=ETA_O)
    return regels, gemeten, ac_in, ac_uit


def test_oude_methode_te_laag_nieuwe_klopt_met_de_meter(reeks16):
    regels, gemeten, *_ = reeks16
    reeks = A.kwartierreeks(regels, gemeten)
    rondes = A.rendement_over_rondes(reeks)
    eta_l = rondes["laden"]["rendement"]
    assert eta_l == pytest.approx(ETA_L, abs=0.01)
    # oud: ontladen afgekapt op 1,0 -> rondrit ~82 %
    oud = eta_l * min(1.0, rondes["ontladen"]["rendement"])
    assert oud == pytest.approx(0.82, abs=0.01)
    # nieuw: de rondes kappen ontladen niet meer op 1,0
    assert rondes["ontladen"]["rendement"] == pytest.approx(ETA_O, abs=0.01)
    erin, eruit, inhoud = _meter(regels, gemeten)
    m = R.rondrit_uit_meter(erin, eruit, inhoud, eta_l)
    assert m["reden"] == "ok" and m["dagen"] >= 14
    assert m["rendement"] == pytest.approx(ETA_L * ETA_O, abs=0.01)
    assert R.ontlaadrendement(m["rendement"], eta_l) == pytest.approx(ETA_O, abs=0.015)
    assert m["rendement"] - oud > 0.02


def test_ontladen_boven_1_toegestaan_binnen_grenzen():
    assert R.ontlaadrendement(0.85, 0.82) == pytest.approx(1.0366, abs=1e-4)
    assert R.ontlaadrendement(0.95, 0.70) == R.ONTLADEN_MAX == 1.20
    assert R.ontlaadrendement(0.60, 0.82) == R.ONTLADEN_MIN == 0.85


def test_plausibiliteit_per_ronde():
    ontladen = {"richting": "ontladen", "kwartieren": 8, "ac_kwh": 1.3, "delta_kwh": -1.0}
    assert A._ronde_meting(ontladen) == (1.3, 1.0)                     # 1,30 telt mee
    assert A._ronde_meting({**ontladen, "ac_kwh": 1.4}) is None        # 1,40: meetfout
    laden = {"richting": "laden", "kwartieren": 8, "ac_kwh": 1.0, "delta_kwh": 1.2}
    assert A._ronde_meting(laden) is None                              # laden > 1,15: meetfout
    assert A.rendement_max("laden") == 1.0 and A.rendement_max("ontladen") == 1.20


def test_te_kort_venster_geen_anker():
    regels, gemeten, *_ = bouw(_seg(10), inhoud0=0.5, eta_l=ETA_L, eta_o=ETA_O)
    m = R.rondrit_uit_meter(*_meter(regels, gemeten), 0.82)
    assert m["rendement"] is None and "minstens 14" in m["reden"]
    assert R.rondrit_uit_meter({}, {}, {}, 0.82)["rendement"] is None


def test_rondrit_buiten_de_grenzen_is_een_meetfout():
    t0 = datetime(2026, 10, 1)
    t1 = t0 + timedelta(days=20)
    m = R.rondrit_uit_meter({t0: 0.0, t1: 100.0}, {t0: 0.0, t1: 99.0}, {t0: 3.0, t1: 3.0}, 0.82)
    assert m["rendement"] is None and m["rendement_gemeten"] == pytest.approx(0.99)
    m = R.rondrit_uit_meter({t0: 0.0, t1: 10.0}, {t0: 0.0, t1: 8.5}, {t0: 3.0, t1: 3.0}, 0.82)
    assert m["rendement"] is None and "te weinig" in m["reden"]


def test_inhoudsverandering_wordt_naar_ac_teruggerekend():
    t0 = datetime(2026, 10, 1)
    t1 = t0 + timedelta(days=30)
    # 4,1 kWh inhoud erbij = 5 kWh AC erin die er nog in zit
    m = R.rondrit_uit_meter({t0: 0.0, t1: 205.0}, {t0: 0.0, t1: 170.0}, {t0: 2.0, t1: 6.1}, 0.82)
    assert m["rendement"] == pytest.approx(170 / 200, abs=1e-6)
    # een moment zonder inhoud ernaast schuift het venster op
    m = R.rondrit_uit_meter({t0 - timedelta(days=1): 0.0, t0: 0.0, t1: 205.0},
                            {t0 - timedelta(days=1): 0.0, t0: 0.0, t1: 170.0},
                            {t0 + timedelta(minutes=10): 2.0, t1: 6.1}, 0.82)
    assert m["van"] == t0.isoformat()


def test_banden_geschaald_verhouding_blijft():
    banden = {"laden": {}, "ontladen": {
        "<500 W": {"kwh": 96.75, "rendement_procent": 95.1, "betrouwbaar": True, "kwartieren": 957},
        "500-1500 W": {"kwh": 21.17, "rendement_procent": 98.5, "betrouwbaar": True, "kwartieren": 115},
        ">1500 W": {"kwh": 8.18, "rendement_procent": 99.8, "betrouwbaar": False, "kwartieren": 19}}}
    doel = 0.85 / 0.82
    uit = R.schaal_ontlaadbanden(banden, doel)
    o = uit["ontladen"]
    gemiddeld = sum(b["kwh"] * b["rendement_procent"] for b in o.values()) / sum(b["kwh"] for b in o.values()) / 100
    assert gemiddeld == pytest.approx(doel, abs=0.002)
    assert o["<500 W"]["rendement_procent"] > 100 and o["<500 W"]["rendement_gemeten_procent"] == 95.1
    assert o[">1500 W"]["rendement_procent"] / o["<500 W"]["rendement_procent"] == pytest.approx(99.8 / 95.1, abs=0.003)
    assert o[">1500 W"]["betrouwbaar"] is False
    assert banden["ontladen"]["<500 W"]["rendement_procent"] == 95.1      # origineel ongemoeid
    assert R.schaal_ontlaadbanden({"ontladen": {}}, doel) == {"ontladen": {}}


def test_waardeplan_ontladen_boven_1():
    accu = W.Accu(inhoud_kwh=5.0, bruikbaar_kwh=9.8, rendement=0.85, rendement_laden=0.82,
                  rendement_ontladen=0.85 / 0.82, ontlaadbanden=((500.0, 1.03), (1500.0, 1.065), (float("inf"), None)))
    eta_l, eta_o = W.rendementen(accu)
    assert eta_l * eta_o == pytest.approx(0.85)
    assert W.ontlaadrendement(300.0, accu, eta_o) == 1.03
    assert W.ontlaadrendement(2000.0, accu, eta_o) == pytest.approx(0.85 / 0.82)
    assert W.ontlaadrendement(300.0, W.Accu(5.0, 9.8, ontlaadbanden=((500.0, 1.5),)), 1.0) == W.ONTLADEN_MAX


def _gekoppeld(make_coordinator, reeks=None, meter=0.85):
    c = make_coordinator({})
    c._rendement_uit_rondes = lambda: {"laden": 82.0, "ontladen": 96.0}
    c._rondrit_meter = {"rendement": meter, "reden": "ok"} if meter else None
    if reeks is not None:
        c._accu_meetreeks = lambda now=None: reeks
    return c


def test_alle_gebruikers_rekenen_met_dezelfde_rondrit(make_coordinator, hass, reeks16):
    regels, gemeten, *_ = reeks16
    reeks = A.kwartierreeks(regels, gemeten)
    c = _gekoppeld(make_coordinator, reeks)
    doel = 0.85 / 0.82
    assert c.learned_charge_efficiency_percent == 82.0
    assert c.learned_discharge_efficiency_percent == pytest.approx(doel * 100, abs=0.06)
    assert c.learned_battery_efficiency_percent == pytest.approx(85.0, abs=0.05)
    assert c._plan_laadrendement(c.learned_battery_efficiency_percent) == pytest.approx(0.82)
    assert c._twin_laadfactor() == pytest.approx(0.82)
    now = DAG0 + timedelta(days=17)
    wp = c._waardeplan_rendementen(now)
    assert wp["rendement_laden"] == pytest.approx(0.82)
    assert wp["rendement_laden"] * wp["rendement_ontladen"] == pytest.approx(0.85, abs=0.001)
    accu = W.Accu(inhoud_kwh=5.0, bruikbaar_kwh=9.8, rendement=c.learned_battery_efficiency_percent / 100,
                  **{k: v for k, v in wp.items() if k != "netlaadmarge_eur"})
    eta_l, eta_o = W.rendementen(accu)
    assert eta_l * eta_o == pytest.approx(0.85, abs=0.001)
    banden = c.get_rendement_per_band(now)
    assert banden["ontladen_geschaald_met"] > 0
    o = [b for b in banden["ontladen"].values() if b.get("rendement_procent")]
    gem = sum(b["kwh"] * b["rendement_procent"] for b in o) / sum(b["kwh"] for b in o) / 100
    assert gem == pytest.approx(doel, abs=0.002)
    # energieboekhouding: AC eruit bij 1 kWh minder inhoud, en de balanscontrole
    c._accu_ac_in = c._accu_ac_uit = 0.0
    assert c._accu_ac_kwh("uit", 1.0) == pytest.approx(doel, abs=0.001)
    assert c._balans_verwacht_voorraadvermogen_w(1000.0) == pytest.approx(1000 / doel, rel=1e-3)
    assert c._balans_verwacht_voorraadvermogen_w(-1000.0) == pytest.approx(-820.0)
    ak = c.get_accukosten(now)
    assert ak["laadrendement_procent"] * ak["ontlaadrendement_procent"] / 100 == pytest.approx(85.0, abs=0.1)


def test_zonder_meter_de_oude_rekenwijze(make_coordinator, hass):
    c = _gekoppeld(make_coordinator, meter=None)
    assert c._rondrit_anker() is None
    assert c.learned_discharge_efficiency_percent == 96.0
    assert c.learned_battery_efficiency_percent == pytest.approx(82.0 * 0.96)
    c._rondrit_meter = {"rendement": None, "reden": "venster 3.0 dagen, minstens 14 nodig"}
    assert c.learned_discharge_efficiency_percent == 96.0
    c._rendement_uit_rondes = lambda: {}
    c.charge_efficiency_history = []
    c._rondrit_meter = {"rendement": 0.85}
    assert c._rondrit_anker() is None          # zonder laadrendement geen splitspunt


@pytest.mark.asyncio
async def test_verversen_uit_de_statistiek(make_coordinator, hass, reeks16):
    from datetime import timezone

    regels, gemeten, *_ = reeks16
    erin, eruit, _inhoud = _meter(regels, gemeten)
    c = make_coordinator({"battery_charge_energy_sensor_entity": "sensor.accu_in",
                          "battery_discharge_energy_sensor_entity": "sensor.accu_uit"})
    c.dagverloop = regels
    c._rendement_uit_rondes = lambda: {"laden": 82.0}

    def rij(d):
        return [{"end": t.replace(tzinfo=timezone.utc).timestamp(), "sum": v * 1000} for t, v in d.items()]

    async def stat(now, ids):
        assert ids == {"sensor.accu_in", "sensor.accu_uit"}
        return {"sensor.accu_in": rij(erin), "sensor.accu_uit": rij(eruit)}, {"sensor.accu_in": "Wh",
                                                                             "sensor.accu_uit": "Wh"}
    c._rondrit_statistiek = stat
    now = (DAG0 + timedelta(days=17)).replace(tzinfo=timezone.utc)
    await c.async_ververs_rondrit_meter(now)
    m = c._rondrit_meter
    assert m["rendement"] == pytest.approx(ETA_L * ETA_O, abs=0.01)
    assert m["ac_erin_kwh"] > 50 and m["dagen"] >= 14 and "kWh-meter" in m["bron"]
    assert c._rondrit_anker()["ontladen"] == pytest.approx(ETA_O, abs=0.015)
    # eens per uur
    c._rondrit_meter = {"rendement": None}
    await c.async_ververs_rondrit_meter(now)
    assert c._rondrit_meter == {"rendement": None}


@pytest.mark.asyncio
async def test_zonder_tellers_een_reden(make_coordinator, hass):
    c = make_coordinator({})
    await c.async_ververs_rondrit_meter(DAG0)
    assert c._rondrit_meter["rendement"] is None and "teller" in c._rondrit_meter["reden"]
    assert c._rondrit_anker() is None


@pytest.mark.asyncio
async def test_recorderfout_houdt_het_anker(make_coordinator, hass):
    c = make_coordinator({"battery_charge_energy_sensor_entity": "sensor.accu_in",
                          "battery_discharge_energy_sensor_entity": "sensor.accu_uit"})
    c._rondrit_meter = {"rendement": 0.85}

    async def stuk(now, ids):
        return None, None
    c._rondrit_statistiek = stuk
    await c._async_recorder_staartstappen(DAG0)
    assert c._rondrit_meter == {"rendement": 0.85}


def test_staartstap_zit_in_de_recorderstap():
    from pathlib import Path
    bron = (Path(A.__file__).parent / "coordinator.py").read_text(encoding="utf-8")
    assert '"dagverloop uit recorder", self._async_recorder_staartstappen(now)' in bron
