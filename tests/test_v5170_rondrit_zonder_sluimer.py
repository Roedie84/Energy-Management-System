"""v5.170.0 - de rondrit voor beslissingen zonder sluimerverbruik.

v5.169.0 rekende de rondrit uit de kWh-meter van de accu (HomeWizard):
AC eruit / (AC erin - Δinhoud/laden). Daar zit het sluimerverbruik in (wat
de accu gebruikt als hij stilstaat). Dat gebeurt ook zonder extra ronde, en
het EMS rekent het vasthouden al apart (`_sluimer_bij_sparen`). Voor de
beslissing "loont een extra ronde" hoort het er dus niet in.

Hier: een reeks met een echte omzetting van 86 % (laden 0,88 x ontladen
0,977) en 6 W sluimer uit de cellen tijdens sparen (10 uur per dag). Totaal
met sluimer ~84,3 %, de conversie ~86 %.
"""
import math
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system import rondrit as R
from custom_components.energy_management_system import waardeplan as W

STAP = 0.1152
DAG0 = datetime(2026, 10, 1, 0, 0)
ETA_L, CONVERSIE = 0.88, 0.86
ETA_O = CONVERSIE / ETA_L
SLUIMER_W = 6.0
MIN_SOC, BOVENGRENS = 10.0, 100.0


def _bouw(dagen, sluimer_w=SLUIMER_W, inhoud0=3.0):
    """Dagverloop, meetlaag, tellerstanden en inhoud zoals de coordinator ze ziet.

    Per dag: 14 kwartieren laden (1000 W), 40 kwartieren sparen (sluimer uit
    de cellen), 38 kwartieren ontladen (300 W), 4 kwartieren stil zonder
    verbruik."""
    patroon = [(14, -1000.0, "laden"), (40, 0.0, "sparen"), (38, 300.0, "ontladen"), (4, 0.0, "")]
    echt, t = inhoud0, DAG0
    regels, gemeten, erin, eruit, inhoud = {}, {}, {}, {}, {}
    som_in = som_uit = 0.0
    for _ in range(dagen):
        for n, accu_w, stand in patroon:
            for _ in range(n):
                ac = abs(accu_w) / 4000
                i = u = 0.0
                if accu_w > 0:
                    echt -= ac / ETA_O
                    u = ac
                elif accu_w < 0:
                    echt += ac * ETA_L
                    i = ac
                elif stand == "sparen":
                    echt -= sluimer_w / 4000
                som_in += i
                som_uit += u
                soc = math.floor(echt / STAP + 1e-9)
                dag, tijd = t.date().isoformat(), t.strftime("%H:%M")
                regels.setdefault(dag, []).append({
                    "tijd": tijd, "beschikbaar_kwh": round(soc * STAP, 4), "accu_w": accu_w, "soc": soc,
                    "stand": stand, "reden": ""})
                gemeten.setdefault(dag, {})[tijd] = {"accu_in_kwh": i, "accu_uit_kwh": u, "accu_kwh": u - i}
                eind = t + timedelta(minutes=15)
                inhoud[eind] = round(soc * STAP, 4)
                if eind.minute == 0:
                    erin[eind], eruit[eind] = som_in, som_uit
                t = eind
    return regels, gemeten, erin, eruit, inhoud


@pytest.fixture(scope="module")
def venster20():
    regels, gemeten, erin, eruit, inhoud = _bouw(20)
    reeks = A.kwartierreeks(regels, gemeten)
    sluimer = A.sluimerverbruik(reeks, MIN_SOC, BOVENGRENS)
    totaal = R.rondrit_uit_meter(erin, eruit, inhoud, ETA_L)
    return reeks, sluimer, totaal


def test_totaal_met_sluimer_conversie_zonder(venster20):
    reeks, sluimer, totaal = venster20
    assert totaal["reden"] == "ok"
    assert 0.83 <= totaal["rendement"] <= 0.85          # v5.169.0: sluimer zit erin
    m = R.met_sluimer(totaal, reeks, sluimer, MIN_SOC, BOVENGRENS)
    assert m["rendement_totaal"] == totaal["rendement"]
    assert m["rendement_conversie"] == pytest.approx(CONVERSIE, abs=0.006)
    assert m["rendement"] == m["rendement_conversie"]
    assert m["rendement_voor_beslissingen"].startswith("conversie")
    # 20 dagen x 10 uur x 6 W uit de cellen = 1,2 kWh inhoud = ~1,36 kWh AC
    assert m["sluimer_kwh"] == pytest.approx(20 * 10 * SLUIMER_W / 1000 / ETA_L, rel=0.2)
    assert m["sluimer"]["dekking"] > 0.99 and m["sluimer"]["per_stand"]["sparen"]["uren"] == pytest.approx(200, abs=1)
    # de lange blokken zien de SoC-stap; het kwartierfilter gooit die weg
    assert sluimer["zelfontlading_blokken"]["sparen"]["gemiddeld_w"] == pytest.approx(SLUIMER_W, abs=1.5)
    assert R.sluimer_vermogen(sluimer)["sparen"] == sluimer["zelfontlading_blokken"]["sparen"]["gemiddeld_w"]


def test_zonder_sluimer_vallen_totaal_en_conversie_samen():
    regels, gemeten, erin, eruit, inhoud = _bouw(20, sluimer_w=0.0)
    reeks = A.kwartierreeks(regels, gemeten)
    sluimer = A.sluimerverbruik(reeks, MIN_SOC, BOVENGRENS)
    m = R.met_sluimer(R.rondrit_uit_meter(erin, eruit, inhoud, ETA_L), reeks, sluimer, MIN_SOC, BOVENGRENS)
    assert m["rendement_totaal"] == pytest.approx(CONVERSIE, abs=0.006)
    assert m["rendement_conversie"] == pytest.approx(m["rendement_totaal"], abs=0.004)


def test_net_tegen_cellen_en_opschalen():
    van = datetime(2026, 10, 1)
    tot = van + timedelta(days=2)
    reeks = []
    for k in range(96):          # alleen de eerste dag: dekking 50 %
        t = van + timedelta(minutes=15 * k)
        reeks.append({"dag": t.date().isoformat(), "tijd": t.strftime("%H:%M"), "accu_kwh": 0.0,
                      "delta_kwh": 0.0, "soc": 5 if k < 48 else 50, "stand": "", "reden": ""})
    sluimer = {"per_stand": {"leeg": {"gemiddeld_w": 2.0, "betrouwbaar": True},
                             "overig": {"gemiddeld_w": 10.0, "betrouwbaar": True}}}
    s = R.sluimer_in_venster(reeks, van, tot, sluimer, 0.8, MIN_SOC, BOVENGRENS)
    assert s["dekking"] == pytest.approx(0.5)
    # leeg uit het net (1:1), overig uit de cellen (/ 0,8); x2 opgeschaald
    assert s["per_stand"]["leeg"]["kwh_ac"] == pytest.approx(12 * 2 / 1000 * 2, abs=1e-3)
    assert s["kwh"] == pytest.approx((12 * 0.002 + 12 * 0.010 / 0.8) * 2, abs=1e-3)
    # te weinig dekking of niets gemeten: geen correctie
    assert R.sluimer_in_venster(reeks[:10], van, tot, sluimer, 0.8, MIN_SOC, BOVENGRENS)["kwh"] is None
    assert R.sluimer_in_venster(reeks, van, tot, {}, 0.8, MIN_SOC, BOVENGRENS)["kwh"] is None


def test_terugval_op_het_totaal(venster20):
    reeks, sluimer, totaal = venster20
    # geen sluimermeting: rendement blijft het totaal (v5.169.0)
    m = R.met_sluimer(totaal, reeks, {}, MIN_SOC, BOVENGRENS)
    assert m["rendement"] == totaal["rendement"] and "rendement_conversie" not in m
    assert m["rendement_voor_beslissingen"].startswith("totaal")
    # geen reeks
    assert R.met_sluimer(totaal, [], sluimer, MIN_SOC, BOVENGRENS)["rendement"] == totaal["rendement"]
    # meting zonder rendement blijft ongemoeid
    leeg = {"rendement": None, "reden": "venster 3.0 dagen, minstens 14 nodig"}
    assert R.met_sluimer(leeg, reeks, sluimer, MIN_SOC, BOVENGRENS) == leeg
    # conversie buiten 60-95 %: het totaal
    hoog = {**totaal, "rendement": 0.94, "ac_eruit_kwh": totaal["ac_eruit_kwh"] * 0.94 / totaal["rendement"]}
    reuze = {"per_stand": {s: {"gemiddeld_w": 80.0, "betrouwbaar": True} for s in ("sparen", "overig")}}
    m = R.met_sluimer(hoog, reeks, reuze, MIN_SOC, BOVENGRENS)
    assert m["rendement"] == 0.94 and "buiten" in m["sluimer_reden"]


def _gekoppeld(make_coordinator, meting):
    c = make_coordinator({})
    c._rendement_uit_rondes = lambda: {"laden": 88.0, "ontladen": 96.0}
    c._rondrit_meter = meting
    return c


def test_beslissers_rekenen_met_de_conversie(make_coordinator, hass, venster20):
    reeks, sluimer, totaal = venster20
    meting = R.met_sluimer(totaal, reeks, sluimer, MIN_SOC, BOVENGRENS)
    c = _gekoppeld(make_coordinator, meting)
    conv = meting["rendement_conversie"]
    assert c._rondrit_anker()["rondrit"] == conv
    assert c.learned_battery_efficiency_percent == pytest.approx(conv * 100, abs=0.05)
    assert c.learned_discharge_efficiency_percent == pytest.approx(conv / 0.88 * 100, abs=0.06)
    wp = c._waardeplan_rendementen(DAG0 + timedelta(days=20))
    assert wp["rendement_laden"] * wp["rendement_ontladen"] == pytest.approx(conv, abs=0.001)
    accu = W.Accu(inhoud_kwh=5.0, bruikbaar_kwh=9.8, rendement=c.learned_battery_efficiency_percent / 100,
                  **{k: v for k, v in wp.items() if k != "netlaadmarge_eur"})
    eta_l, eta_o = W.rendementen(accu)
    assert eta_l * eta_o == pytest.approx(conv, abs=0.001)
    assert c._accu_ac_kwh("uit", 1.0) == pytest.approx(conv / 0.88, abs=0.001)
    # de sensor: toestand = conversie, totaal als kenmerk
    from custom_components.energy_management_system.sensor import _rondrit_weergave
    w = _rondrit_weergave(meting)
    assert w["rondrit_conversie_procent"] == round(conv * 100, 1)
    assert w["rondrit_totaal_procent"] == round(totaal["rendement"] * 100, 1)
    assert w["rondrit_sluimer_kwh"] == meting["sluimer_kwh"] and "conversie" in w["toestand_betekent"]
    assert _rondrit_weergave(None)["rondrit_conversie_procent"] is None


def test_geen_dubbeltelling_met_sluimer_bij_sparen(make_coordinator, hass, venster20):
    """Het vasthouden kost apart (`_sluimer_bij_sparen`); de conversie zonder
    sluimer laat dat ongemoeid en telt het niet nog eens in het rendement."""
    reeks, sluimer, totaal = venster20
    meting = R.met_sluimer(totaal, reeks, sluimer, MIN_SOC, BOVENGRENS)
    # de sluimer van het sparen zit niet meer in het rendement: de conversie
    # is de echte omzetting, niet omzetting x (1 - sluimerdeel)
    assert meting["rendement"] == pytest.approx(CONVERSIE, abs=0.006)
    assert totaal["rendement"] < CONVERSIE - 0.01
    c = make_coordinator({})
    c.get_sluimerverbruik = lambda now=None: {"per_stand": {
        "sparen": {"gemiddeld_w": 6.0, "betrouwbaar": True}, "leeg": {"gemiddeld_w": 0.5}}}
    now = datetime(2026, 11, 3, 12, 0)
    kwartieren = [(now + timedelta(hours=10), now + timedelta(hours=10, minutes=15), 0.40, 0.5)]
    s = c._sluimer_bij_sparen(now, kwartieren, {kwartieren[0][0]}, 0.30, 1.0)
    assert s["sluimer_w"] == 5.5 and s["verlies_kwh"] == pytest.approx(0.055, abs=1e-3)


@pytest.mark.asyncio
async def test_verversen_rekent_de_conversie(make_coordinator, hass):
    from datetime import timezone

    regels, gemeten, erin, eruit, _inhoud = _bouw(20)
    c = make_coordinator({"battery_charge_energy_sensor_entity": "sensor.accu_in",
                          "battery_discharge_energy_sensor_entity": "sensor.accu_uit"})
    c.dagverloop = regels
    c._rendement_uit_rondes = lambda: {"laden": 88.0}
    reeks = A.kwartierreeks(regels, gemeten)
    c._accu_meetreeks = lambda now=None: reeks
    c.effective_min_soc_percent = lambda: MIN_SOC
    c._bovengrens_procent = lambda: BOVENGRENS

    def rij(d):
        return [{"end": t.replace(tzinfo=timezone.utc).timestamp(), "sum": v} for t, v in d.items()]

    async def stat(now, ids):
        return {"sensor.accu_in": rij(erin), "sensor.accu_uit": rij(eruit)}, {}
    c._rondrit_statistiek = stat
    await c.async_ververs_rondrit_meter((DAG0 + timedelta(days=21)).replace(tzinfo=timezone.utc))
    m = c._rondrit_meter
    assert m["rendement_conversie"] == pytest.approx(CONVERSIE, abs=0.006)
    assert m["rendement_totaal"] < m["rendement_conversie"] - 0.01
    assert c._rondrit_anker()["rondrit"] == m["rendement_conversie"]

    # een fout in de sluimer laat de totale rondrit staan
    def stuk(now=None):
        raise RuntimeError("stuk")
    c._accu_meetreeks = stuk
    c._rondrit_meter_uur = None
    await c.async_ververs_rondrit_meter((DAG0 + timedelta(days=21, hours=1)).replace(tzinfo=timezone.utc))
    assert c._rondrit_meter["rendement"] == pytest.approx(0.843, abs=0.01)
    assert "rendement_conversie" not in c._rondrit_meter
