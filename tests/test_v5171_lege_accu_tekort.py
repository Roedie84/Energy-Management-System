"""v5.171.0 (L-EMS-059) - een lege accu boven 13 % telt als tekort.

Nacht 02->03: SoC 15-16 % met 0,02-0,14 kWh bruikbaar (module 00996 op zijn
celgrens), 1,887 kWh van het net 22-07 uur, geteld als tekort: 0. Nu ook leeg
bij een bruikbare inhoud onder 0,1 kWh, los van de SoC.
"""
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system.coordinator import accu_is_leeg

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 3, 2, 0, tzinfo=TZ)


def _c(make_coordinator, soc, inhoud, reden):
    c = make_coordinator({})
    c.last_reason = reden
    c.piekverkoop_tot = None
    c.accustand_procent = lambda: soc
    c.beschikbare_energie_kwh = lambda: inhoud
    c.effective_min_soc_percent = lambda: 10.0
    return c


def test_soc_15_inhoud_0_02_houden_is_tekort(make_coordinator, hass):
    assert _c(make_coordinator, 15, 0.02, "waardeplan_houden")._netimport_is_tekort(NU) is True


def test_soc_15_met_inhoud_is_vasthouden(make_coordinator, hass):
    assert _c(make_coordinator, 15, 0.8, "waardeplan_houden")._netimport_is_tekort(NU) is False


def test_bewuste_netafname_blijft_bewust_ook_leeg(make_coordinator, hass):
    assert _c(make_coordinator, 15, 0.02, "waardeplan_laden")._netimport_is_tekort(NU) is False


def test_zonder_inhoud_de_soc_regel(make_coordinator, hass):
    assert _c(make_coordinator, 12, None, "default_smart")._netimport_is_tekort(NU) is True
    assert _c(make_coordinator, 15, None, "default_smart")._netimport_is_tekort(NU) is False


def test_accu_is_leeg():
    assert accu_is_leeg(15, 0.02, 13) is True
    assert accu_is_leeg(15, 0.14, 13) is False
    assert accu_is_leeg(12, 2.0, 13) is True
    assert accu_is_leeg(None, None, 13) is False


def _nacht(soc, inhoud, reden="waardeplan_houden", net_w=300.0):
    """Dagverloop 02-11 22:00 t/m 03-11 08:45, elk kwartier gelijk."""
    def regels(van, tot):
        uit = []
        for kw in range(van * 4, tot * 4):
            r = {"tijd": f"{kw // 4:02d}:{kw % 4 * 15:02d}", "soc": soc, "net_w": net_w, "reden": reden}
            if inhoud is not None:
                r["beschikbaar_kwh"] = inhoud
            uit.append(r)
        return uit
    return {"2026-11-02": regels(22, 24), "2026-11-03": regels(0, 9)}


def test_verloop_lege_inhoud_bij_15_procent_telt(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = _nacht(15, 0.02)
    kwh = c._tekortnacht_uit_verloop(date(2026, 11, 3), 13.0)
    assert kwh == round(44 * 0.3 * 0.25, 3)


def test_verloop_oude_regels_zonder_inhoud_soc_regel(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = _nacht(15, None)
    assert c._tekortnacht_uit_verloop(date(2026, 11, 3), 13.0) == 0.0


def test_verloop_vasthouden_met_inhoud_telt_niet(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = _nacht(15, 1.2)
    assert c._tekortnacht_uit_verloop(date(2026, 11, 3), 13.0) == 0.0


def test_economisch_lege_nacht_houdt_de_bestaande_indeling(make_coordinator, hass):
    """Een nacht waarin het plan de lege accu bewust liet (netladen loonde
    niet) telt nu als tekort, maar de soort komt uit de bestaande regels:
    economisch, en die telt niet mee in de marge (L-EMS-054)."""
    from custom_components.energy_management_system.const import (
        MARGE_TELT_NIET_MEE_SOORTEN,
        TEKORTSOORT_ECONOMISCH,
        TEKORTSOORT_PLANNING,
    )

    c = make_coordinator({})
    c.dagverloop = _nacht(15, 0.02)
    kwh = c._tekortnacht_uit_verloop(date(2026, 11, 3), 13.0)
    c.bruikbaar_tussen_grenzen_kwh = lambda: 5.0
    assert c._tekort_soort(kwh, vol=False, verkocht_kwh=0.0, economisch=True) == TEKORTSOORT_ECONOMISCH
    assert TEKORTSOORT_ECONOMISCH in MARGE_TELT_NIET_MEE_SOORTEN
    # zonder economische afwijzing: planning, en die telt wel mee
    assert c._tekort_soort(kwh, vol=False, verkocht_kwh=0.0) == TEKORTSOORT_PLANNING
