"""v5.187.0 economische schaduw - de lijm in de coordinator (plantoetsen 3, 4, 7, 9, 10, 11).

3  geen schaduwsturing: 0 dienstaanroepen en 0 schrijfacties in 96 schaduwkwartieren;
   productie-opdrachten gelijk met en zonder schaduw
4  productie ongewijzigd: zelfde productieplan met schaduw aan en uit
7  midkwartier: een geweigerde wissel gelogd met beide voordelen, gedrag gelijk
8  zon morgen: alleen het huidige gedrag vastleggen (geen wijziging)
9  fout in de schaduw: geen_plan, sturing loopt door, internal_failures gezet en gewist
10 herstart: virtuele inhoud en open dag overleven
11 rekenlast: de schaduwplannen in de executor, samen < 1,5 s
"""
import asyncio
import json
import math
import time
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import economische_schaduw as es
from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.const import (
    CONF_MANUAL_CHARGE_POWER,
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
)
from custom_components.energy_management_system.economische_schaduw_sturing import SCHADUW_SLEUTEL

T0 = datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)
SELECT, NUMBER = "select.op", "number.pow"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _accu(inhoud=3.0):
    return W.Accu(inhoud_kwh=inhoud, bruikbaar_kwh=7.8, laden_kw=2.4, ontladen_kw=2.4, verkoop_kw=1.2,
                  rendement=0.84, slijtage_eur=0.0422, verkoopmarge_eur=0.02, rendement_laden=0.914,
                  rendement_ontladen=0.919, min_actie_w=400, min_laad_w=500, zon_export_afdwingbaar=True,
                  huis_eerst=True, bewaarmarge_eur=0.05, bewaarkost_eur_per_kwh_uur=0.002)


def _kwartieren(now, n=24):
    begin = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    ks = []
    for i in range(n):
        t = begin + timedelta(minutes=15 * i)
        h = t.hour + t.minute / 60
        prijs = 0.20 + 0.15 * math.exp(-((h - 7.5) / 1.0) ** 2) + 0.18 * math.exp(-((h - 18) / 1.5) ** 2)
        zon = max(0.0, math.sin((h - 8) / 9 * math.pi)) * 0.5 if 8 < h < 17 else 0.0
        ks.append(W.Kwartier(t, 0.15, zon, prijs, prijs - 0.09, 1.0, uren=0.25 if i else 0.2417,
                             prijs_incl_eur=prijs + 0.11))
    return ks


class _Laag:
    """De meetlaag: alleen `laatste_kwartier` (zoals kwartierenergie.kwartier)."""

    def __init__(self):
        self.laatste_kwartier = None
        self.grenzen = []

    def kwartiergrens(self, grens):
        self.grenzen.append(grens)

    def meet(self, kwartier, huis=0.2, pv=0.0, imp=0.05, exp=0.0, bin_=0.0, bout=0.15):
        self.laatste_kwartier = {"kwartier": kwartier.isoformat(), "grid_import_kwh": imp,
                                 "grid_export_kwh": exp, "pv_kwh": pv, "battery_in_kwh": bin_,
                                 "battery_out_kwh": bout, "house_kwh": huis}


def _coordinator(make_coordinator, hass, aan=True):
    c = make_coordinator({CONF_OPERATION_SELECT: SELECT, CONF_MANUAL_POWER_NUMBER: NUMBER,
                          CONF_MANUAL_CHARGE_POWER: 2400})
    hass.states.set(SELECT, "smart", {"options": ["smart", "manual", "smart_charging"]})
    hass.states.set(NUMBER, "0")
    c._waardeplan_invoer = lambda now, entries: {"kwartieren": _kwartieren(now), "accu": _accu(c._inhoud),
                                                 "bruikbaar": 7.8, "balans": {}}
    c._inhoud = 3.0
    c.beschikbare_energie_kwh = lambda: c._inhoud
    c._waardeplan_knip = None
    c.salderingspositie_weergave = lambda: None
    c.zet_economische_schaduw(aan)
    return c


async def _kwartieren_draaien(c, laag, n, start=T0, laden=True):
    """n kwartieren: grens (afrekenen) en daarna het eerste plan van het kwartier."""
    if laden and c._schaduw_boek is None:
        await c.async_laad_economische_schaduw()
    plannen = []
    for i in range(n):
        grens = start + timedelta(minutes=15 * i)
        laag.meet(grens - timedelta(minutes=15))
        c._meetlaag_object = lambda: laag
        c._meetlaag_kwartier(grens)
        now = grens + timedelta(seconds=30)
        plannen.append(await c._async_bereken_waardeplan(now, []))
        # een herplanning midden in het kwartier: geen tweede schaduwplan
        plannen.append(await c._async_bereken_waardeplan(now + timedelta(minutes=3), []))
        taak = c._schaduw_taak
        if taak is not None and hasattr(taak, "__await__"):
            await taak
        c._inhoud = max(0.0, c._inhoud - 0.15 / 0.919)
    return plannen


def _vergelijkbaar(plannen):
    return json.dumps(plannen, sort_keys=True, default=str)


# --- 3 en 4 ---------------------------------------------------------------------

def test_96_schaduwkwartieren_zonder_sturing_en_productie_gelijk(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, aan=True)
    voor = (hass.states.get(SELECT).state, hass.states.get(NUMBER).state)
    plannen_aan = _run(_kwartieren_draaien(c, _Laag(), 96))
    assert hass.services.calls == []
    assert (hass.states.get(SELECT).state, hass.states.get(NUMBER).state) == voor
    boek = c._schaduw_boek
    assert len(boek.rijen) == 95                         # het eerste kwartier had nog geen plan
    assert {r[1] for r in boek.rijen} == {"ok"}
    assert SCHADUW_SLEUTEL not in c.internal_failures
    assert boek.open_dag["dag"] == "2026-11-05"          # de grens van 00:00 volgt pas
    # zelfde reeks met de schakelaar uit: hetzelfde productieplan, geen schaduw
    c2 = _coordinator(make_coordinator, hass, aan=False)
    c2._inhoud = 3.0
    plannen_uit = _run(_kwartieren_draaien(c2, _Laag(), 96, laden=False))
    assert _vergelijkbaar(plannen_aan) == _vergelijkbaar(plannen_uit)
    assert c2._schaduw_boek is None and hass.services.calls == []


def test_productieopdrachten_gelijk_met_en_zonder_schaduw(make_coordinator, hass):
    """De hele beslissing (_waardeplan_als_nodig) met schaduw aan en uit: dezelfde
    schrijfacties naar select en number."""

    def ronde_reeks(aan):
        hass.services.calls.clear()
        c = _coordinator(make_coordinator, hass, aan=aan)
        c._is_emergency_low_battery = lambda: False
        c._update_financial_tracking = lambda *a, **k: None
        c._update_shortfall_detection = lambda *a, **k: None
        c._finish_decision_tick = lambda now: None
        c._overschot_toestand = lambda: {"overschot_w": 0.0, "accu_vol": False}
        c._opstart_stuurstil = lambda now=None: False
        laag = _Laag()

        async def reeks():
            await c.async_laad_economische_schaduw()
            for i in range(16):
                grens = T0 + timedelta(hours=6, minutes=15 * i)
                laag.meet(grens - timedelta(minutes=15))
                c._meetlaag_object = lambda: laag
                c._meetlaag_kwartier(grens)
                await c._waardeplan_als_nodig(grens + timedelta(seconds=30), [])
                if c._schaduw_taak is not None and hasattr(c._schaduw_taak, "__await__"):
                    await c._schaduw_taak
        _run(reeks())
        return list(hass.services.calls), c

    oproepen_aan, c_aan = ronde_reeks(True)
    oproepen_uit, _c = ronde_reeks(False)
    assert oproepen_aan == oproepen_uit and oproepen_aan
    assert len(c_aan._schaduw_boek.rijen) == 15


def test_schakelaar_uit_slaat_het_pad_over(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, aan=False)
    _run(c._async_bereken_waardeplan(T0, []))
    assert c._schaduw_boek is None and c._schaduw_lopend is None
    c._economische_schaduw_kwartier(T0, _Laag())
    assert c._schaduw_boek is None


def test_meetlaag_kwartier_roept_de_afrekening_aan(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    laag = _Laag()
    c._meetlaag_object = lambda: laag
    gezien = []
    c._economische_schaduw_kwartier = lambda grens, l: gezien.append((grens, l))
    c._meetlaag_kwartier(T0)
    assert laag.grenzen == [T0] and gezien == [(T0, laag)]


def test_geen_meting_telt_niet(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    laag = _Laag()

    async def reeks():
        await _kwartieren_draaien(c, laag, 3)
        laag.laatste_kwartier = None                    # meetlaag gaf niets
        c._meetlaag_kwartier(T0 + timedelta(minutes=45))
    _run(reeks())
    assert [r[1] for r in c._schaduw_boek.rijen] == ["ok", "ok", "geen_meting"]
    virtueel = dict(c._schaduw_boek.virtueel)
    assert all(v is not None for v in virtueel.values())


def test_dag_sluit_om_middernacht(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _run(_kwartieren_draaien(c, _Laag(), 6, start=T0 - timedelta(hours=1)))
    boek = c._schaduw_boek
    assert [d["date"] for d in boek.dagen] == ["2026-11-04"]
    assert boek.dagen[0]["kwartieren_totaal"] == 4       # 23:00 t/m 23:45, gesloten op de grens van 00:00
    assert boek.open_dag["dag"] == "2026-11-05"
    # de waarde voor de nieuwe dag komt van het eerste productieplan van die dag
    assert "2026-11-05" in boek.waarden


# --- 7: midkwartier ----------------------------------------------------------------

def _plan(berekend, actie, accu_kwh=-0.2, uren=0.24, prijs=0.25, eind=0.26, waarde=0.40):
    return {"beschikbaar": True, "berekend_om": berekend.isoformat(), "inhoud_kwh": 3.0,
            "eindwaarde_eur_per_kwh": eind,
            "nu": {"actie": actie, "kwh": abs(accu_kwh), "accu_kwh": accu_kwh, "uren": uren,
                   "rekenprijs_eur": prijs, "waarde_inhoud_eur_per_kwh": waarde}}


def test_midkwartier_geweigerde_wissel_gelogd_gedrag_gelijk(make_coordinator, hass):
    def reeks(aan):
        c = _coordinator(make_coordinator, hass, aan=aan)
        c._is_emergency_low_battery = lambda: False
        c._update_financial_tracking = lambda *a, **k: None
        c._update_shortfall_detection = lambda *a, **k: None
        c._finish_decision_tick = lambda now: None
        c._overschot_toestand = lambda: {"overschot_w": 500.0, "accu_vol": False}
        c._waardeplan_accu_leeg = lambda now: False
        t = T0 + timedelta(hours=17, seconds=30)
        sleutel = c._kwartier_sleutel(t)
        c._schaduw_lopend = {"t": sleutel.timestamp(), "midk": None, "status": "gepland"}

        def ronde(plan, now):
            async def _p(n, e):
                return plan
            c._async_waardeplan_nu = _p
            _run(c._waardeplan_als_nodig(now, []))
            return dict(c.last_waardeplan), c.last_reason
        uit = [ronde(_plan(t, "huis"), t)]
        later = t + timedelta(minutes=2)
        uit.append(ronde(_plan(later, "houden", accu_kwh=0.0, uren=0.2), later))
        uit.append(ronde(_plan(later, "houden", accu_kwh=0.0, uren=0.2), later + timedelta(seconds=30)))
        return uit, c

    aan, c = reeks(True)
    uit, _c = reeks(False)
    assert [(p.get("uitgevoerd"), r) for p, r in aan] == [(p.get("uitgevoerd"), r) for p, r in uit]
    assert aan[1][0]["midkwartier"] == uit[1][0]["midkwartier"]
    midk = c._schaduw_lopend["midk"]
    # één keer per plan; voordeel tegen eindwaarde 0,26 en marginaal 0,40
    rest = 0.2 * 0.2 / 0.24
    assert midk[0] == 1 and midk[1] == 0
    assert midk[2] == pytest.approx(round(rest * abs(0.25 - 0.26), 4), abs=1e-4)
    assert midk[3] == pytest.approx(round(rest * abs(0.25 - 0.40), 4), abs=1e-4)
    assert _c._schaduw_lopend.get("midk") is None


def test_midkwartier_in_de_kwartierregel_en_dagtelling(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    laag = _Laag()

    async def reeks():
        await _kwartieren_draaien(c, laag, 2)
        c._schaduw_lopend["midk"] = [2, 1, 0.03, 0.05]
        await _kwartieren_draaien(c, laag, 1, start=T0 + timedelta(minutes=30))
    _run(reeks())
    rij = es.rij_als_dict(c._schaduw_boek.rijen[-1])
    assert rij["midk"] == [2, 1, 0.03, 0.05]
    regel = c._schaduw_boek.sluit_dag(T0.timestamp() + 86400, 0.919, 7.8)
    assert regel["midk_geweigerd"] == 2 and regel["midk_toegestaan"] == 1


# --- 9: fout in de schaduw ------------------------------------------------------------

def test_fout_in_de_schaduw_raakt_productie_niet(make_coordinator, hass, monkeypatch):
    c = _coordinator(make_coordinator, hass)
    laag = _Laag()
    goed = es.plan_varianten

    def kapot(*a, **k):
        raise RuntimeError("schaduw stuk")

    async def reeks():
        await c.async_laad_economische_schaduw()
        monkeypatch.setattr(es, "plan_varianten", kapot)
        plan = await c._async_bereken_waardeplan(T0 + timedelta(seconds=30), [])
        await c._schaduw_taak
        assert plan["beschikbaar"] is True
        assert "schaduw stuk" in c.internal_failures[SCHADUW_SLEUTEL]
        assert c._schaduw_lopend["status"] == "geen_plan"
        laag.meet(T0)
        c._meetlaag_object = lambda: laag
        c._meetlaag_kwartier(T0 + timedelta(minutes=15))
        assert c._schaduw_boek.rijen[-1][1] == "geen_plan"
        monkeypatch.setattr(es, "plan_varianten", goed)
        await c._async_bereken_waardeplan(T0 + timedelta(minutes=15, seconds=30), [])
        await c._schaduw_taak
        assert SCHADUW_SLEUTEL not in c.internal_failures
    _run(reeks())


def test_fout_bij_het_kopieren_raakt_productie_niet(make_coordinator, hass, monkeypatch):
    c = _coordinator(make_coordinator, hass)
    zonder = _coordinator(make_coordinator, hass, aan=False)

    async def reeks():
        await c.async_laad_economische_schaduw()
        c._schaduw_lopend_van = lambda *a: (_ for _ in ()).throw(ValueError("kapot"))
        return await c._async_bereken_waardeplan(T0, []), await zonder._async_bereken_waardeplan(T0, [])
    met, zonder_plan = _run(reeks())
    assert _vergelijkbaar([met]) == _vergelijkbaar([zonder_plan])
    assert "kapot" in c.internal_failures[SCHADUW_SLEUTEL]


# --- 10: herstart ------------------------------------------------------------------------

def test_virtuele_inhoud_en_open_dag_overleven_een_herstart(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _run(_kwartieren_draaien(c, _Laag(), 8))
    boek = c._schaduw_boek
    boek.virtueel["c2"] = 4.321
    c._schaduw_bewaren()
    nieuw = _coordinator(make_coordinator, hass)
    terug = _run(nieuw.async_laad_economische_schaduw())
    assert terug.virtueel["c2"] == pytest.approx(4.321)
    assert terug.open_dag == boek.open_dag and terug.rijen == boek.rijen
    assert terug.waarden == boek.waarden and terug.gestart == boek.gestart


def test_resync_dienst(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    assert c.economische_schaduw_resync() is False       # nog niet geladen
    _run(c.async_laad_economische_schaduw())
    c._inhoud = 2.5
    assert c.economische_schaduw_resync() is True
    assert c._schaduw_boek.virtueel == {"c2": 2.5, "c0": 2.5}


def test_sensor_en_diagnose(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    assert c.get_economische_schaduw()["status"] == "laden"
    _run(_kwartieren_draaien(c, _Laag(), 4))
    s = c.get_economische_schaduw()
    assert s["status"] == "loopt" and len(json.dumps(s)) < 4096
    assert c.economische_schaduw_besparing() is None    # nog geen volledige dag
    d = c.get_economische_schaduw_diagnose()
    assert d["kolommen"] == list(es.KOLOMMEN) and len(d["kwartieren"]) == 3
    c.zet_economische_schaduw(False)
    assert c.get_economische_schaduw()["status"] == "uit"


# --- 11: rekenlast --------------------------------------------------------------------------

def test_schaduwplannen_in_de_executor_en_snel_genoeg(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    gezien = []

    async def executor(func, *args):
        gezien.append(func)
        return func(*args)

    c.hass.async_add_executor_job = executor

    async def reeks():
        await c.async_laad_economische_schaduw()
        await c._async_bereken_waardeplan(T0, [])
        await c._schaduw_taak
    _run(reeks())
    assert gezien == [W.plan, es.plan_varianten]
    # twee schaduwplannen over 144 kwartieren (de reviewdag), beste van twee
    ks, accu = _kwartieren(T0 + timedelta(hours=12), 144), _accu()
    duur = []
    for _ in range(2):
        t = time.perf_counter()
        es.plan_varianten(W.plan, ks, accu, {n: (m, 3.0) for n, m in es.VARIANTEN.items()})
        duur.append(time.perf_counter() - t)
    assert min(duur) < 1.5, duur


def test_plan_voor_de_afrekening_wacht_op_de_afrekening(make_coordinator, hass):
    """Ronde van 00:15 vóór de klok van de kwartiergrens: het schaduwplan wacht
    tot het vorige kwartier is afgerekend (met de bijgewerkte virtuele inhoud)."""
    c = _coordinator(make_coordinator, hass)
    laag = _Laag()

    async def reeks():
        await _kwartieren_draaien(c, laag, 1)
        grens = T0 + timedelta(minutes=15)
        await c._async_bereken_waardeplan(grens + timedelta(seconds=1), [])
        assert c._schaduw_wacht is not None and c._schaduw_lopend["t"] == T0.timestamp()
        laag.meet(T0)
        c._meetlaag_object = lambda: laag
        c._meetlaag_kwartier(grens)
        assert c._schaduw_wacht is None and c._schaduw_lopend["t"] == grens.timestamp()
        await c._schaduw_taak
        assert c._schaduw_lopend["varianten"]["c2"] is not None
    _run(reeks())
    assert [r[1] for r in c._schaduw_boek.rijen] == ["ok"]


# --- 8: alleen vastleggen (geen wijziging) -----------------------------------------------

def test_zon_morgen_krijgt_een_correctie_huidig_gedrag(make_coordinator, hass):
    """Plantoets 8 documenteert het huidige gedrag (coordinator, `_estimate_pv_kwh_for_period`,
    tak 'niet vandaag'): een halfuur van morgen krijgt precies één factor - de geleerde
    uurverhouding, anders de dagbias - en niet beide. Deze release verandert daar niets aan."""
    c = make_coordinator({})
    nu = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
    morgen = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    reeks = [(morgen, morgen + timedelta(minutes=30), 1.0)]
    c._get_pv_forecast_entries = lambda: reeks
    c._pv_schatting_vast = lambda entries, veilig: {"positie": None, "band": {}, "bias": 10.0, "nu": nu}
    c.learned_pv_hourly_ratio = lambda uur: 1.2
    assert c._estimate_pv_kwh_for_period(morgen, morgen + timedelta(minutes=30)) == pytest.approx(1.2)
    c.learned_pv_hourly_ratio = lambda uur: None
    assert c._estimate_pv_kwh_for_period(morgen, morgen + timedelta(minutes=30)) == pytest.approx(1.1)
