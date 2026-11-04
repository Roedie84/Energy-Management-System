"""v5.177.0 (A7) - één definitie van 'leeg'."""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 4, 6, 30, tzinfo=TZ)


def _c(make_coordinator, inhoud, soc=15.0, cap=8.64, ondergrens=10.0):
    c = make_coordinator({})
    c.beschikbare_energie_kwh = lambda: inhoud
    c.accustand_procent = lambda: soc
    c.bruikbare_capaciteit_kwh = lambda: cap
    c.effectieve_ondergrens_procent = lambda now=None: ondergrens
    return c


def test_grens_is_drie_procent_van_de_capaciteit(make_coordinator, hass):
    c = _c(make_coordinator, 0.2)
    assert abs(c.accu_leeg_grens_kwh() - 0.2592) < 1e-6
    assert abs(c.accu_leeg_grens_plan_kwh() - 0.3) < 1e-9


def test_inhoud_beslist_niet_de_ruwe_laadstand(make_coordinator, hass):
    # 0,17 kWh boven de grens bij 12 %: leeg (v5.176.1: status en plan gelijk)
    assert _c(make_coordinator, 0.17, soc=12.0).accu_leeg(NU) is True
    # 0,5 kWh boven de grens, maar de laadstand op 12 % (module-correctie): niet leeg
    assert _c(make_coordinator, 0.5, soc=12.0).accu_leeg(NU) is False


def test_zonder_inhoud_de_laadstand_tegen_de_effectieve_ondergrens(make_coordinator, hass):
    assert _c(make_coordinator, None, soc=12.5, ondergrens=10.0).accu_leeg(NU) is True
    assert _c(make_coordinator, None, soc=14.0, ondergrens=10.0).accu_leeg(NU) is False


def test_plan_tekort_en_status_dezelfde_grens(make_coordinator, hass):
    c = _c(make_coordinator, 0.25)
    rij = {"actie": "houden", "net_kwh": 0.1, "inhoud_kwh": 0.3}
    assert c._waardeplan_tekort(rij, c.accu_leeg_grens_plan_kwh()) is True
    assert c._waardeplan_accu_leeg(NU) is True


def test_noodregel_gebruikt_de_gecorrigeerde_inhoud(make_coordinator, hass):
    c = _c(make_coordinator, 0.0, soc=14.0)
    c._is_low_solar_expected = lambda: True
    c._dipbesluit = lambda now, blok: {"laden": True}
    assert c._is_emergency_low_battery() is True      # 14 % maar niets bruikbaar
    c.beschikbare_energie_kwh = lambda: 2.0
    c._noodlading_actief = False
    assert c._is_emergency_low_battery() is False
