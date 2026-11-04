"""v5.177.0 - het waardeplan: plan en sturing zeggen hetzelfde (A1-A12, B1)."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system import overschotwaarde as OW
from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.const import (
    BALANCEER_MAX_PRIJS_EUR,
    CONF_VERKOOP_MIN_WINST_CT,
    CONF_VERKOOP_MIN_WINST_GEMIGREERD,
    OPTION_SMART,
    PRICE_SCALE_FACTOR,
    REASON_REGISTRY,
    WAARDEPLAN_MIN_ACTIE_W,
    WAARDEPLAN_MIN_VERMOGEN_W,
)

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 4, 7, 0, tzinfo=TZ)


def _kw(prijzen, verbruik=0.1, zon=0.0, teruglever=None, **extra):
    t, uit = NU, []
    for p in prijzen:
        uit.append(W.Kwartier(t, verbruik, zon, p, p if teruglever is None else teruglever, **extra))
        t += timedelta(minutes=15)
    return uit


def _accu(inhoud=0.0, **k):
    return W.Accu(inhoud_kwh=inhoud, bruikbaar_kwh=7.8, rendement=0.84, slijtage_eur=0.0422, **k)


# --- A1: verkopen alleen onder de eigen vloer van het plan -------------------

def _c(make_coordinator, plan, inhoud):
    c = make_coordinator({})
    c.beschikbare_energie_kwh = lambda: inhoud
    c.bereken_waardeplan = lambda now, entries: plan
    c._is_emergency_low_battery = lambda: False
    c.smart_charging_supported = lambda: True
    c.verkoopreserve = lambda *a, **k: pytest.fail("de oude verkoopreserve mag niet meer tellen")
    toegepast = []

    async def manual(w):
        toegepast.append(("manual", w))

    async def stand(s):
        toegepast.append(("stand", s))

    c._async_apply_manual = manual
    c._async_apply_operation = stand
    c._update_financial_tracking = lambda *a, **k: None
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda *a, **k: None
    return c, toegepast


def _plan(actie, accu_kwh, kwh, vloer=0.0, uren=0.25, **nu):
    return {
        "beschikbaar": True, "inhoud_kwh": 3.0, "bruikbaar_kwh": 7.8,
        "nu": {"actie": actie, "accu_kwh": accu_kwh, "kwh": kwh, "prijs_eur": 0.3,
               "begin": NU.isoformat(), "inhoud_kwh": 3.0, "verkoop_vloer_kwh": vloer,
               "uren": uren, **nu},
        "vooruit": [], "kwartieren": 96, "besparing_plan_eur": 1.0,
    }


def test_a1_verkoop_boven_de_vloer_van_het_plan_gaat_door(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("verkopen", -0.6, 0.5, vloer=1.0), inhoud=3.0)
    asyncio.run(c._waardeplan_als_nodig(NU, []))
    assert c.last_reason == "waardeplan_verkopen"
    assert t[-1][0] == "manual" and t[-1][1] > 0


def test_a1_onder_de_vloer_van_het_plan_huis(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("verkopen", -0.6, 0.5, vloer=3.0), inhoud=3.0)
    asyncio.run(c._waardeplan_als_nodig(NU, []))
    assert c.last_reason == "waardeplan_huis" and t[-1] == ("stand", OPTION_SMART)
    assert "plan" in c.last_waardeplan["verkoop_tegengehouden"]


def test_a1_planrij_draagt_de_vloer():
    kw = _kw([0.3] * 4)
    kw[0].verkoop_vloer_kwh = 1.5
    u = W.plan(kw, _accu(3.0))
    assert u.kwartieren[0]["verkoop_vloer_kwh"] == 1.5


# --- A2: balanceergrens tegen de prijs incl. belasting ----------------------

def test_a2_balanceren_toetst_de_prijs_incl(make_coordinator, hass):
    c = make_coordinator({})
    c.balanceerlading = lambda now: {"nodig": True, "reden": "balans"}
    c._resterende_laadruimte_kwh = lambda: 7.0
    c._balanceer_zon_vult_vandaag = lambda *a: False
    # marginaal 15 ct (onder de grens), incl. 26 ct (erboven)
    kw = _kw([0.15] * 120, prijs_incl_eur=0.26)
    accu = _accu(0.5)
    uit = c._waardeplan_balanceren(NU, kw, accu)
    assert "kwartier" not in uit and "onder" in uit["reden"]
    c._balanceer_doel = None
    kw2 = _kw([0.15] * 120)
    assert "kwartier" in c._waardeplan_balanceren(NU, kw2, accu)
    assert BALANCEER_MAX_PRIJS_EUR > 0.15


# --- A3: de leerlus leert van de verwachting van het plan -------------------

def test_a3_planrij_geeft_de_waarde_van_een_netlading():
    u = W.plan(_kw([0.10] * 8 + [0.50] * 8, teruglever=0.0), _accu(0.0, verkopen=False, min_laad_w=500))
    laden = [r for r in u.kwartieren if r["actie"] == "laden_net"]
    assert laden
    for r in laden:
        # later 50 ct x ontlaadrendement - slijtage, x laadrendement: tussen 25 en 50 ct
        assert 0.25 < r["waarde_eur_per_kwh"] < 0.50


def test_a3_laadwaarde_uit_het_plan():
    from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C

    c = SimpleNamespace(
        _waardeplan_stuurt_nu=lambda: True,
        last_waardeplan={"nu": {"actie": "laden_net", "waarde_eur_per_kwh": 0.3612}},
        last_laadbesluit={"laden": True, "waarde_eur": 0.10},
    )
    assert C._laad_waarde_ct(c) == pytest.approx(36.12)
    c.last_waardeplan = {"nu": {"actie": "houden"}}
    assert C._laad_waarde_ct(c) is None     # niet het bevroren oude besluit


def test_a3_oude_bevroren_verwachting_telt_niet():
    r = {"reden": "waardeplan_laden", "laad_waarde_ct": 30.0}
    assert A._laadverwachting(r) is None
    assert A._laadverwachting({**r, "laad_waarde_bron": "waardeplan"}) == 30.0
    # v5.183.0 (punt 3): ladingen van de oude regels tellen ook niet meer mee
    assert A._laadverwachting({"reden": "grid_charging_profitable", "laad_waarde_ct": 30.0}) is None


# --- A4: het lopende kwartier telt zijn eigen duur --------------------------

def test_a4_lopend_kwartier_plant_niet_meer_dan_er_past():
    kw = _kw([0.05] * 2 + [0.60] * 8, verbruik=0.0)
    kw[0].uren = 0.05                  # nog 3 minuten
    u = W.plan(kw, _accu(0.0, laden_kw=2.4, verkopen=False))
    eerste = u.kwartieren[0]
    assert eerste["accu_kwh"] <= 2.4 * 0.05 + 1e-6
    assert u.kwartieren[1]["accu_kwh"] > 0.4


def test_a4_vermogen_uit_de_duur_van_de_rij(make_coordinator, hass):
    c = make_coordinator({})
    rij = {"accu_kwh": 0.1, "uren": 0.1, "vol_vermogen": False}
    assert c._waardeplan_laadvermogen_w(rij) == pytest.approx(1000)
    assert c._waardeplan_laadvermogen_w({"accu_kwh": 0.1}) == pytest.approx(400)


# --- A5: een gat knipt de horizon af ----------------------------------------

def _entries(n):
    return [(NU + timedelta(minutes=15 * i), NU + timedelta(minutes=15 * (i + 1)), 0.3 * PRICE_SCALE_FACTOR)
            for i in range(n)]


def test_a5_gat_knipt_af_in_plaats_van_alles_weg(make_coordinator, hass):
    c = make_coordinator({})
    gat = NU + timedelta(minutes=15 * 8)
    c._segmenten_verbruik_zon = lambda a, b, veilig=True: None if a >= gat else [(0.1, 0.0)]
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: 0.0
    c._is_salderen_active = lambda t: True
    c._planning_verkoopreserve_kwh = lambda *a: 0.0
    kw = c._waardeplan_kwartieren(NU, _entries(20))
    assert len(kw) == 8 and c._waardeplan_knip == gat
    gat = NU + timedelta(minutes=15 * 2)
    assert c._waardeplan_kwartieren(NU, _entries(20)) is None


def test_a5_slijtage_terugval(make_coordinator, hass):
    c = make_coordinator({})
    c.get_wear_cost_overview = lambda: {"beschikbaar": False}
    assert c._waardeplan_slijtage_ct() == pytest.approx(4.22)


def test_a5_geen_plan_wordt_zichtbaar(make_coordinator, hass):
    c = make_coordinator({})
    c._noteer_waardeplan_beschikbaar(NU, {"beschikbaar": False, "reden": "rekenfout"})
    assert c.waardeplan_weg_teller["rondes"] == 1
    assert c._waardeplan_aandachtspunt(NU + timedelta(minutes=5)) is None
    punt = c._waardeplan_aandachtspunt(NU + timedelta(minutes=45))
    assert "rekenfout" in punt and "oude regels" in punt
    c._noteer_waardeplan_beschikbaar(NU, {"beschikbaar": True})
    assert c._waardeplan_aandachtspunt(NU + timedelta(minutes=45)) is None


# --- A6: besparing uit het gemeten vermogen ---------------------------------

def test_a6_gemeten_vermogen_in_plaats_van_de_opdracht(make_coordinator, hass):
    c = make_coordinator({})
    c._read_corrected_battery_power = lambda: 800.0
    assert c._gemeten_accu_w(2400, 1) == 800.0
    assert c._gemeten_accu_w(2400, -1) == 0.0
    c._read_corrected_battery_power = lambda: None
    assert c._gemeten_accu_w(-2400, -1) == 2400


# --- A8: de uitleg zegt wat er boven de ondergrens zit ----------------------

def test_a8_uitleg_inhoud_en_ruimte(make_coordinator, hass):
    c = make_coordinator({})
    c.last_waardeplan = {**_plan("houden", 0.0, 0.0), "inhoud_kwh": 0.7, "bruikbaar_kwh": 7.8}
    tekst = " · ".join(c._waarom_waardeplan())
    assert "0,7 kWh boven de ondergrens" in tekst and "ruimte tot vol 7,1 kWh" in tekst
    assert "bruikbaar 7" not in tekst


# --- A9: geen zonnebonus op teruglevering uit de accu -----------------------

def test_a9_accu_zonder_zonnebonus():
    assert OW.terugleverwaarde_2027(0.10) == pytest.approx(0.13)
    assert OW.terugleverwaarde_accu_2027(0.10) == pytest.approx(0.12)
    acc = _accu()
    # 1 kWh uit de accu het net op: tegen de accuprijs
    k = W._kosten_stap(0.0, 0.0, 0.3, 0.13, np.array([-1.0]), acc, 0.12)[0]
    assert k == pytest.approx(-0.12 + 0.0422)
    # zonoverschot 1 kWh, accu stil: tegen de zonprijs
    assert W._kosten_stap(0.0, 1.0, 0.3, 0.13, np.array([0.0]), acc, 0.12)[0] == pytest.approx(-0.13)


def test_a9_kwartieren_2027_dragen_de_accuprijs(make_coordinator, hass):
    c = make_coordinator({})
    c._segmenten_verbruik_zon = lambda a, b, veilig=True: [(0.1, 0.0)]
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: 0.0
    c._is_salderen_active = lambda t: False
    c._planning_verkoopreserve_kwh = lambda *a: 0.0
    e = _entries(4)
    c._kale_entries = lambda: [(a, b, 0.10 * PRICE_SCALE_FACTOR) for a, b, _p in e]
    kw = c._waardeplan_kwartieren(NU, e)
    assert kw[0].teruglever_accu_eur < kw[0].teruglever_eur


# --- A10: eindwaarde uit de verwachting, anders het 75e percentiel ----------

def test_a10_eindwaarde():
    kw = _kw([0.20] * 6 + [0.40] * 2)
    acc = _accu()
    eta = W.rendementen(acc)[1]
    assert W.eindwaarde(kw, acc, eta) == pytest.approx(0.25 * eta - 0.0422, abs=1e-6)
    acc.eindprijs_eur = 0.50
    assert W.eindwaarde(kw, acc, eta) == pytest.approx(0.50 * eta - 0.0422, abs=1e-6)


def test_a10_eindprijs_uit_de_prijsverwachting(make_coordinator, hass):
    c = make_coordinator({})
    kw = _kw([0.2] * 4)
    eind = kw[-1].begin + timedelta(minutes=15)
    uren = []
    for i in range(12):
        t = (eind + timedelta(hours=i)).astimezone(timezone.utc)
        uren.append({"sleutel": t.strftime("%Y-%m-%dT%H"), "prijs_eur": 0.20 + 0.02 * i})
    c.prijsverwachting = {"dagen": {"x": {"model": {"uren": uren}}}}
    p = c._waardeplan_eindprijs(kw)
    assert 0.33 < p < 0.38
    c.prijsverwachting = {}
    assert c._waardeplan_eindprijs(kw) is None


# --- A11: zon terugleveren als opslaan niet loont ---------------------------

def test_a11_saldering_zon_terug_als_later_niet_duurder():
    """Saldering: terugleveren levert de inkoopprijs + premie op. Bij een
    vlakke prijs loont opslaan niet; het plan levert terug en de sturing
    moet dat afdwingen (zon_export)."""
    kw = _kw([0.30] * 8, verbruik=0.0, zon=0.0)
    for k in kw[:4]:
        k.zon_kwh, k.teruglever_eur = 0.4, 0.32
    u = W.plan(kw, _accu(1.0, zon_export_afdwingbaar=True, verkoopmarge_eur=0.02, netladen=False,
                                verkopen=False))
    assert [r["actie"] for r in u.kwartieren[:4]] == ["zon_export"] * 4


def test_a11_2027_zon_opslaan_blijft():
    kw = _kw([0.30] * 4 + [0.40] * 4, verbruik=0.0, zon=0.0)
    for k in kw[:4]:
        k.zon_kwh, k.teruglever_eur = 0.4, 0.08
    for k in kw[4:]:
        k.verbruik_kwh = 0.3
    u = W.plan(kw, _accu(0.0, zon_export_afdwingbaar=True, verkoopmarge_eur=0.02, netladen=False))
    assert all(r["actie"] == "zon" for r in u.kwartieren[:4])


def test_a11_sturing_handmatig_nul(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("zon_export", 0.0, 0.0), inhoud=3.0)
    asyncio.run(c._waardeplan_als_nodig(NU, []))
    assert c.last_reason == "waardeplan_terugleveren" and t[-1] == ("manual", 0)
    assert "waardeplan_terugleveren" in REASON_REGISTRY


# --- A12: geen planvermogen dat de sturing niet stuurt ----------------------

def test_a12_een_grens():
    assert WAARDEPLAN_MIN_VERMOGEN_W == WAARDEPLAN_MIN_ACTIE_W


def test_a12_geen_netlading_onder_500_w():
    u = W.plan(_kw([0.10] * 8 + [0.50] * 8, teruglever=0.0),
               _accu(0.0, verkopen=False, min_actie_w=400, min_laad_w=500))
    for r in u.kwartieren:
        net = r["accu_kwh"] - max(0.0, -r["net_kwh"] + r["accu_kwh"] - 0.1)
        if r["inhoud_delta_kwh"] > 0:
            assert r["actie"] == "laden_net" and r["accu_kwh"] / 0.25 * 1000 >= 500 - 1e-6, (r, net)


def test_a12_lege_accu_geen_geplande_ontlading():
    """06:30: 0,06 kWh telde als 0,1 en het plan ontlaadde een lege accu."""
    u = W.plan(_kw([0.40] * 4), _accu(0.06, netladen=False, verkopen=False))
    assert u.kwartieren[0]["inhoud_delta_kwh"] == 0.0
    assert u.kwartieren[0]["accu_ac_w"] == 0


def test_a12_huis_gepland_als_het_tekort():
    u = W.plan(_kw([0.40] * 4, verbruik=0.1), _accu(2.0, netladen=False, verkopen=False))
    huis = [r for r in u.kwartieren if r["actie"] == "huis"]
    assert huis and all(r["accu_ac_w"] == 400 for r in huis)


# --- B1: verkoopmarge 2 ct --------------------------------------------------

def test_b1_migratie():
    from custom_components.energy_management_system import migreer_verkoop_min_winst as M

    assert M({CONF_VERKOOP_MIN_WINST_CT: 10.0})[CONF_VERKOOP_MIN_WINST_CT] == 2.0
    assert M({CONF_VERKOOP_MIN_WINST_CT: 5.0})[CONF_VERKOOP_MIN_WINST_CT] == 5.0
    assert M({}, {CONF_VERKOOP_MIN_WINST_CT: 10})[CONF_VERKOOP_MIN_WINST_CT] == 2.0
    assert M({CONF_VERKOOP_MIN_WINST_CT: 10.0, CONF_VERKOOP_MIN_WINST_GEMIGREERD: True}) is None
    assert CONF_VERKOOP_MIN_WINST_CT not in M({})
