"""v5.164.1 - de live verbruikscorrectie heeft één plafond per plan.

Gemeld 02-11 19:00 (akkoord Ruud 19:53): een piek van 2,75 kW liet het
waardeplan tot ~20:30 met 2,4 kW rekenen (gemeten ~600 W), omdat het plafond
van 1,5 kWh per kwartier-opvraging gold in plaats van over het hele plan.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONSUMPTION_CORRECTION_MAX_EXTRA_KWH,
)

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 2, 19, 0, tzinfo=TZ)


def _c(make_coordinator):
    c = make_coordinator({})
    c.verbruik_uur_kw = lambda uur, moment=None: 0.665
    c._get_smoothed_consumption_correction_ratio = lambda uur: 2.75 / 0.665
    c._uitgedempte_correctie = lambda start, eind, ratio: ratio  # volle correctie
    return c


def _plan(c):
    totaal = 0.0
    for i in range(16):  # 4 uur aan kwartieren
        a = NU + timedelta(minutes=15 * i)
        totaal += c._estimate_consumption_kwh_for_period(a, a + timedelta(minutes=15))
    return totaal


def test_zonder_budget_per_kwartier_onbegrensd(make_coordinator):
    c = _c(make_coordinator)
    basis = 0.665 * 4
    assert _plan(c) - basis > 6.0   # het oude gedrag: ~8 kWh extra


def test_met_budget_hooguit_anderhalve_kwh_extra(make_coordinator):
    c = _c(make_coordinator)
    basis = 0.665 * 4
    with c._gedeeld_correctiebudget():
        totaal = _plan(c)
    assert abs(totaal - basis - CONSUMPTION_CORRECTION_MAX_EXTRA_KWH) < 1e-6
    assert getattr(c, "_correctie_budget", None) is None


def test_budget_geldt_ook_voor_de_segmenten(make_coordinator):
    c = _c(make_coordinator)
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=True: 0.0
    c.regelverschuiving_kw = lambda: 0.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c._vacation_adjusted_kwh = lambda k: k
    with c._gedeeld_correctiebudget():
        extra = 0.0
        for i in range(16):
            a = NU + timedelta(minutes=15 * i)
            seg = c._segmenten_verbruik_zon(a, a + timedelta(minutes=15), veilig=False)
            extra += sum(v for v, _z in seg) - 0.665 * 0.25
    assert abs(extra - CONSUMPTION_CORRECTION_MAX_EXTRA_KWH) < 1e-6


def test_genest_telt_het_buitenste_budget(make_coordinator):
    c = _c(make_coordinator)
    with c._gedeeld_correctiebudget():
        c._correctie_uit_budget(1.0)
        with c._gedeeld_correctiebudget():
            assert c._correctie_uit_budget(1.0) == 0.5


def test_negatieve_correctie_ongemoeid(make_coordinator):
    c = _c(make_coordinator)
    with c._gedeeld_correctiebudget():
        assert c._correctie_uit_budget(-0.3) == -0.3


# --- spiegelcontrole met modulesprong (gemeld 02-11 19:56) -----------------

def test_spiegel_rekent_met_dezelfde_modulesprong(make_coordinator, hass):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar"})
    hass.states.set("sensor.beschikbaar", "0.576")
    c.module_leeg_correctie_kwh = lambda: 0.551
    c.last_available_kwh = 0.025
    regel = next(r for r in c.get_spiegelcontrole() if r["naam"] == "Beschikbare energie")
    assert regel["oordeel"] != "loopt_uiteen"


def test_spiegel_zonder_modulesprong_meldt_nog_steeds(make_coordinator, hass):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar"})
    hass.states.set("sensor.beschikbaar", "0.576")
    c.module_leeg_correctie_kwh = lambda: 0.0
    c.last_available_kwh = 0.025
    regel = next(r for r in c.get_spiegelcontrole() if r["naam"] == "Beschikbare energie")
    assert regel["oordeel"] == "loopt_uiteen"


# --- waardeplan telt tekortkwartieren weer (gemeld 02-11 20:00) -----------

def test_waardeplan_lege_accu_met_netafname_is_tekort(make_coordinator):
    c = make_coordinator({})
    t = c._waardeplan_tekort
    assert t({"actie": "houden", "net_kwh": 0.15, "inhoud_kwh": 0.0}) is True
    assert t({"actie": "huis", "net_kwh": 0.05, "inhoud_kwh": 0.0}) is True


def test_waardeplan_keuzes_zijn_geen_tekort(make_coordinator):
    c = make_coordinator({})
    t = c._waardeplan_tekort
    assert t({"actie": "houden", "net_kwh": 0.15, "inhoud_kwh": 2.0}) is False
    assert t({"actie": "laden_net", "net_kwh": 0.6, "inhoud_kwh": 0.0}) is False
    assert t({"actie": "zon", "net_kwh": -0.2, "inhoud_kwh": 0.0}) is False
