"""v5.128.0: vijf goedgekeurde punten (akkoord Ruud 26-10).

- L-EMS-038: het kwartierplan verkoopt niet in het goedkope blok van de sturing.
- L-EMS-037: het kwartierplan laadt met laadrendement en afbouw boven 90 %.
- Nachtcontrole: rondes waarin de sturing bewust niet ontlaadt, tellen niet.
- Maandteller "Besparing deze maand" met bewaarde beginstand.
- Punt 15: bijladen tot 100 % bij een negatieve of heel lage prijs.
"""
import math

import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.energy_management_system.const import (
    HEEL_LAGE_PRIJS_GRENS_MAX_EUR,
    LAAD_AFBOUW_FACTOR_BIJ_VOL,
    LAAD_AFBOUW_VANAF_PROCENT,
    NACHT_BEWUST_NIET_ONTLADEN_REDENEN,
    PERSISTED_FIELDS,
    PRICE_SCALE_FACTOR,
)
from custom_components.energy_management_system.sensor import SavingsThisMonthSensor

CET = timezone(timedelta(hours=1))
DAG = datetime(2026, 10, 25, tzinfo=CET)
BLOK = (DAG.replace(hour=21, minute=30), DAG.replace(hour=6) + timedelta(days=1))


# --- L-EMS-038: niet verkopen in het lopende blok -------------------------


def _verkoop_coordinator(make_coordinator):
    c = make_coordinator({})
    c._planning_verkoopreserve_kwh = lambda *a, **k: 0.5
    c._is_worth_discharging_now = lambda *a, **k: True
    c._is_worth_discharging_at_secondary_tier = lambda *a, **k: True
    return c


def test_038_geen_verkoop_in_het_blok(make_coordinator):
    """25-10 23:30 (19,1 ct) in het blok 21:30-06:00: de sturing verkocht niet."""
    c = _verkoop_coordinator(make_coordinator)
    regels = {"zonarm": {}, "blok": BLOK}
    start = DAG.replace(hour=23, minute=30)
    assert c._plan_verkoopruimte([], start, 0.191, True, 2.3, 0.6, {}, regels, 2400) is None
    assert c._plan_verkoopruimte([], start, 0.191, False, 2.3, 0.6, {}, regels, 2400) is None


def test_038_buiten_het_blok_ongewijzigd(make_coordinator):
    c = _verkoop_coordinator(make_coordinator)
    regels = {"zonarm": {}, "blok": BLOK}
    start = DAG.replace(hour=20, minute=0)
    assert c._plan_verkoopruimte([], start, 0.35, True, 2.3, 0.6, {}, regels, 2400) == pytest.approx(1.8)
    # het blokeinde zelf hoort er niet meer bij
    assert c._plan_verkoopruimte([], BLOK[1], 0.35, True, 2.3, 0.6, {}, regels, 2400) == pytest.approx(1.8)


def test_038_zonder_blok_ongewijzigd(make_coordinator):
    c = _verkoop_coordinator(make_coordinator)
    start = DAG.replace(hour=23, minute=30)
    for regels in ({"zonarm": {}}, {"zonarm": {}, "blok": (None, None)}):
        assert c._plan_verkoopruimte([], start, 0.35, True, 2.3, 0.6, {}, regels, 2400) == pytest.approx(1.8)


# --- L-EMS-037: laadrendement en afbouw -----------------------------------


def test_037_afbouwfactor(make_coordinator):
    f = make_coordinator({})._laad_afbouw_factor
    assert f(None) == 1.0
    assert f(50.0) == 1.0
    assert f(LAAD_AFBOUW_VANAF_PROCENT) == 1.0
    assert math.isclose(f(100.0), LAAD_AFBOUW_FACTOR_BIJ_VOL)
    assert math.isclose(f(95.0), (1 + LAAD_AFBOUW_FACTOR_BIJ_VOL) / 2)
    assert f(93.0) > f(96.0) > f(99.0)


def test_037_laadrendement(make_coordinator):
    c = make_coordinator({})
    c.charge_efficiency_history = []
    assert math.isclose(c._plan_laadrendement(81.0), math.sqrt(0.81))
    c.charge_efficiency_history = [92.0] * 50
    assert math.isclose(c._plan_laadrendement(81.0), 0.92)


def test_037_onder_90_procent_alleen_het_rendement(make_coordinator):
    c = make_coordinator({})
    erin, van_net = c._plan_lading(3.0, 10.35, 5.0, 0.6, 0.9, 10.0)
    assert math.isclose(erin, 0.54, abs_tol=1e-9)
    assert math.isclose(van_net, 0.6, abs_tol=1e-9)


def test_037_klein_gat_kost_meer_net_dan_erin(make_coordinator):
    c = make_coordinator({})
    erin, van_net = c._plan_lading(3.0, 10.35, 0.2, 0.6, 0.9, 10.0)
    assert math.isclose(erin, 0.2, abs_tol=1e-9)
    assert math.isclose(van_net, 0.2 / 0.9, abs_tol=1e-9)


def test_037_boven_90_procent_trager(make_coordinator):
    c = make_coordinator({})
    bruikbaar = 10.35
    soc_95 = bruikbaar * (95 - 10) / 90
    erin, van_net = c._plan_lading(soc_95, bruikbaar, 5.0, 0.6, 0.9, 10.0)
    assert erin < 0.54 * 0.7
    assert van_net < 0.6
    # nooit voller dan vol
    erin, _ = c._plan_lading(bruikbaar - 0.01, bruikbaar, 5.0, 0.6, 0.9, 10.0)
    assert erin <= 0.01 + 1e-9


def test_037_meer_laadkwartieren_nodig(make_coordinator):
    """25-10: 6 kwartieren gepland waar er meer nodig waren - van 27 % tot vol."""
    c = make_coordinator({})
    bruikbaar = 10.35
    soc = bruikbaar * (27 - 10) / 90
    oud = math.ceil((bruikbaar - soc) / 0.6)
    kwartieren = 0
    while bruikbaar - soc > 0.01 and kwartieren < 100:
        erin, _ = c._plan_lading(soc, bruikbaar, bruikbaar - soc, 0.6, 0.9, 10.0)
        soc += erin
        kwartieren += 1
    assert oud == 14
    assert kwartieren >= oud + 3


def test_037_zonder_laadgrens(make_coordinator):
    erin, van_net = make_coordinator({})._plan_lading(3.0, 10.35, 0.5, float("inf"), 0.9, 10.0)
    assert erin == 0.5 and math.isclose(van_net, 0.5 / 0.9)


def test_037_netregels_kennen_het_laadrendement(make_coordinator):
    c = make_coordinator({})
    c._get_forecast_entries = lambda *a, **k: []
    regels = c._plan_netregels(DAG, [], lambda moment: 0.2)
    assert 0.5 <= regels["laadrendement"] <= 1.0
    assert regels["heel_laag_grens_eur"] >= 0.0


# --- Nachtcontrole --------------------------------------------------------


def test_nacht_bewust_niet_ontladen_telt_niet(make_coordinator):
    c = make_coordinator({})
    c._nachtrondes = None
    nacht = DAG.replace(hour=22, minute=54)
    for i in range(74):
        reden = "sparen_in_blok" if i < 60 else "grid_charging_profitable"
        c._tel_nachtronde(nacht + timedelta(seconds=30 * i), reden, net_w=400.0)
    assert (c._nachtrondes or {"totaal": 0})["totaal"] == 0
    uit = c.zelfcontrole_nacht_gecontroleerd()
    assert uit["in_orde"] is True
    assert uit["bewust_niet_ontladen"] == 74
    assert "bewust niet ontlaadde" in uit["uitleg"]


def test_nacht_echte_fout_wordt_nog_gezien(make_coordinator):
    c = make_coordinator({})
    c._nachtrondes = None
    nacht = DAG.replace(hour=23)
    for i in range(70):
        c._tel_nachtronde(nacht + timedelta(seconds=30 * i), "default_smart", net_w=400.0)
    c._tel_nachtronde(nacht, "sparen_in_blok", net_w=400.0)
    uit = c.zelfcontrole_nacht_gecontroleerd()
    assert uit["in_orde"] is False
    assert uit["totaal"] == 70


def test_nacht_teller_per_nacht(make_coordinator):
    c = make_coordinator({})
    c._tel_nachtronde(DAG.replace(hour=23), "sparen_in_blok", net_w=400.0)
    assert c._nachtrondes_bewust == 1
    c._tel_nachtronde(DAG.replace(hour=23) + timedelta(days=1), "default_smart", net_w=0.0)
    assert c._nachtrondes_bewust == 0


def test_nacht_redenen_bestaan():
    from custom_components.energy_management_system.const import REASON_REGISTRY

    assert NACHT_BEWUST_NIET_ONTLADEN_REDENEN <= set(REASON_REGISTRY)
    assert "default_smart" not in NACHT_BEWUST_NIET_ONTLADEN_REDENEN
    assert "discharging_window" not in NACHT_BEWUST_NIET_ONTLADEN_REDENEN


# --- Maandteller besparing ------------------------------------------------


def _maand_coordinator(make_coordinator, totaal=42.57):
    c = make_coordinator({})
    c._wacht_op_eerste_ronde = False
    c.counterfactual_cost_all_time_eur = -15.81
    c.actual_cost_all_time_eur = -57.38
    c.counterfactual_cost_current_month_eur = 21.93
    c.actual_cost_current_month_eur = 13.90
    c._counterfactual_month_key = 202610
    c.besparing_maand = None
    c.besparing_totaal_gecorrigeerd_eur = lambda: totaal
    return c


def test_maand_reconstructie_eerste_keer(make_coordinator):
    """Rauw totaal 41,57 min rauwe maand 8,03 = 33,54 op 1-10."""
    c = _maand_coordinator(make_coordinator)
    c._werk_besparing_maand_bij(DAG.replace(hour=12))
    info = c.besparing_maand
    assert info["maand"] == "2026-10"
    assert math.isclose(info["begin_eur"], 33.54, abs_tol=1e-6)
    assert math.isclose(c.besparing_deze_maand_eur(), 9.03, abs_tol=1e-6)
    assert "reconstructie" in info["bron"]


def test_maand_beginstand_blijft(make_coordinator):
    c = _maand_coordinator(make_coordinator)
    c._werk_besparing_maand_bij(DAG.replace(hour=12))
    c.counterfactual_cost_current_month_eur = 0.0   # telt niet meer mee
    c.besparing_totaal_gecorrigeerd_eur = lambda: 43.07
    c._werk_besparing_maand_bij(DAG.replace(hour=13))
    assert math.isclose(c.besparing_deze_maand_eur(), 9.53, abs_tol=1e-6)


def test_maand_opstart_en_storing_houden_de_waarde(make_coordinator):
    c = _maand_coordinator(make_coordinator)
    c._werk_besparing_maand_bij(DAG.replace(hour=12))
    c._wacht_op_eerste_ronde = True
    c.besparing_totaal_gecorrigeerd_eur = lambda: 41.0     # opstartwaarde
    c._werk_besparing_maand_bij(DAG.replace(hour=12, minute=1))
    assert math.isclose(c.besparing_deze_maand_eur(), 9.03, abs_tol=1e-6)
    c._wacht_op_eerste_ronde = False

    def stuk():
        raise ValueError("onbeschikbaar")

    c.besparing_totaal_gecorrigeerd_eur = stuk
    c._werk_besparing_maand_bij(DAG.replace(hour=12, minute=2))
    assert math.isclose(c.besparing_deze_maand_eur(), 9.03, abs_tol=1e-6)
    c.besparing_totaal_gecorrigeerd_eur = lambda: float("nan")
    c._werk_besparing_maand_bij(DAG.replace(hour=12, minute=3))
    assert math.isclose(c.besparing_deze_maand_eur(), 9.03, abs_tol=1e-6)


def test_maand_herstart_kost_niets(make_coordinator, coordinator_cls, hass):
    c = _maand_coordinator(make_coordinator)
    c._werk_besparing_maand_bij(DAG.replace(hour=12))
    bewaard = {"besparing_maand": dict(c.besparing_maand)}
    nieuw = make_coordinator({})
    nieuw._apply_persisted_state(bewaard)
    assert math.isclose(nieuw.besparing_deze_maand_eur(), 9.03, abs_tol=1e-6)
    nieuw._wacht_op_eerste_ronde = False
    nieuw.besparing_totaal_gecorrigeerd_eur = lambda: 42.77
    nieuw._werk_besparing_maand_bij(DAG.replace(hour=14))
    assert math.isclose(nieuw.besparing_deze_maand_eur(), 9.23, abs_tol=1e-6)
    assert "besparing_maand" in PERSISTED_FIELDS


def test_maand_wissel_neemt_het_laatste_totaal(make_coordinator):
    c = _maand_coordinator(make_coordinator)
    c._werk_besparing_maand_bij(DAG.replace(day=31, hour=23, minute=59))
    c.besparing_totaal_gecorrigeerd_eur = lambda: 42.80
    nov = datetime(2026, 11, 1, 0, 1, tzinfo=CET)
    c._werk_besparing_maand_bij(nov)
    info = c.besparing_maand
    assert info["maand"] == "2026-11"
    assert math.isclose(info["begin_eur"], 42.57, abs_tol=1e-6)
    assert math.isclose(c.besparing_deze_maand_eur(), 0.23, abs_tol=1e-6)


def test_maand_sensor():
    coord = SimpleNamespace(
        besparing_maand={"maand": "2026-10", "begin_eur": 33.54, "laatste_totaal_eur": 42.57,
                         "waarde_eur": 9.03, "bron": "x", "bijgewerkt": "t"},
        besparing_deze_maand_eur=lambda: 9.03,
    )
    s = SavingsThisMonthSensor(coord, "e")
    assert s.available is True
    assert s.native_value == 9.03
    assert s.last_reset.month == 10 and s.last_reset.day == 1 and s.last_reset.hour == 0
    assert s.extra_state_attributes["beginstand_totaal_eur"] == 33.54
    leeg = SavingsThisMonthSensor(
        SimpleNamespace(besparing_maand=None, besparing_deze_maand_eur=lambda: None), "e"
    )
    assert leeg.available is False
    assert leeg.last_reset is None


def test_maand_sensor_op_het_dashboard():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    tekst = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    assert "sensor.woonkamer_energy_management_system_besparing_deze_maand" in tekst


# --- Punt 15: bijladen tot vol bij een heel lage prijs ---------------------


def test_15_heel_lage_prijs(make_coordinator):
    h = make_coordinator({})._heel_lage_prijs
    assert h(-0.01, 0.0) is True
    assert h(0.0, 0.0) is True
    assert h(0.10, 0.111) is True
    assert h(0.111, 0.111) is True
    assert h(0.142, 0.111) is False
    assert h(0.05, -1.0) is False          # negatieve grens telt als 0
    assert h(None, 0.111) is False


def test_15_grens(make_coordinator):
    c = make_coordinator({})
    c._gemeten_belastingdeel_eur_per_kwh = lambda: 0.111
    assert math.isclose(c._heel_lage_prijs_grens_eur(), 0.111)
    c._gemeten_belastingdeel_eur_per_kwh = lambda: 0.5
    assert c._heel_lage_prijs_grens_eur() == HEEL_LAGE_PRIJS_GRENS_MAX_EUR

    def stuk():
        raise KeyError("geen prijssensor")

    c._gemeten_belastingdeel_eur_per_kwh = stuk
    assert c._heel_lage_prijs_grens_eur() == 0.0


def _entries():
    uit = []
    for i in range(2 * 96):
        b = DAG + timedelta(minutes=15 * i)
        uit.append((b, b + timedelta(minutes=15), 0.28 * PRICE_SCALE_FACTOR))
    return uit


def _live(make_coordinator, soc, prijs):
    c = make_coordinator({})
    entries = _entries()
    c._get_forecast_entries = lambda *a, **k: entries
    c.huidige_prijs_eur_per_kwh = lambda: prijs
    c._resterende_laadruimte_kwh = lambda: 0.35
    c.beschikbare_energie_kwh = lambda: 10.0
    c.accustand_procent = lambda: soc
    c._laadkosten_ct = lambda: 4.22
    c._balanceer_laadbesluit = lambda *a, **k: None
    c._verwacht_zonoverschot_kwh = lambda *a, **k: 0.0
    c._zon_vol_om = lambda *a, **k: None
    c._goedkoopste_laadmomenten = lambda *a, **k: True
    c._gemeten_belastingdeel_eur_per_kwh = lambda: 0.111
    c.last_reason = "default_smart"
    return c


NU = DAG.replace(hour=13, minute=5)
MIDDAGBLOK = (DAG.replace(hour=12), DAG.replace(hour=15))


def test_15_beslissing_laadt_bij_heel_lage_prijs(make_coordinator):
    uit = _live(make_coordinator, 97.0, 0.08).laadbesluit_uit_het_net(NU, *MIDDAGBLOK)
    assert uit["laden"] is True
    assert uit["heel_lage_prijs"] is True


def test_15_beslissing_laadt_bij_negatieve_prijs(make_coordinator):
    uit = _live(make_coordinator, 99.0, -0.02).laadbesluit_uit_het_net(NU, *MIDDAGBLOK)
    assert uit["laden"] is True


def test_15_gewone_prijs_houdt_de_rem(make_coordinator):
    uit = _live(make_coordinator, 97.0, 0.142).laadbesluit_uit_het_net(NU, *MIDDAGBLOK)
    assert uit["laden"] is False
    assert uit["hysterese"] is True


def _plan(make_coordinator, grens):
    c = make_coordinator({})
    c._verwacht_zonoverschot_kwh = lambda *a, **k: 0.0
    c._zon_vol_om = lambda *a, **k: None
    c._goedkoopste_laadmomenten = lambda *a, **k: True
    regels = {
        "slijtage_ct": 4.22, "rendement": 83.9, "salderen": True,
        "reeks": [(b, p / PRICE_SCALE_FACTOR) for b, _e, p in _entries()],
        "laadde_vorig": False, "blok": MIDDAGBLOK, "heel_laag_grens_eur": grens,
    }
    return c, regels


def test_15_plan_laadt_bij_heel_lage_prijs(make_coordinator):
    c, regels = _plan(make_coordinator, 0.111)
    soc_97 = 10.35 * (97 - 10) / 90
    einde = DAG.replace(hour=13, minute=15)
    assert c._plan_laadt(regels, einde, 0.08, soc_97, 10.35, 0.6, 0.6) > 0.0
    assert c._plan_laadt(regels, einde, 0.142, soc_97, 10.35, 0.6, 0.6) == 0.0


def test_15_plan_zonder_grens_alleen_negatief(make_coordinator):
    c, regels = _plan(make_coordinator, 0.0)
    soc_97 = 10.35 * (97 - 10) / 90
    einde = DAG.replace(hour=13, minute=15)
    assert c._plan_laadt(regels, einde, 0.08, soc_97, 10.35, 0.6, 0.6) == 0.0
    assert c._plan_laadt(regels, einde, -0.01, soc_97, 10.35, 0.6, 0.6) > 0.0
