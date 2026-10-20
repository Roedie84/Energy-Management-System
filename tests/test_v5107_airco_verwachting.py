"""v5.107.0 - de airco-verwachting kijkt naar aanwezigheid, dag en buitentemperatuur.

Gevraagd 20-10 15:42: "Neemt de airco voorspelling ook de aanwezigheid etc
mee" en "Ja graag alles meenemen". De reserve rekende per klokuur alleen met
hoe vaak de airco de laatste dagen in dat uur draaide.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import airco_ritme as R

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 20, 15, 45, tzinfo=TZ)          # dinsdag


def _ritme(uur=19, keer_aan=2, dagen=5, temp=None):
    r = R.leeg()
    for i in range(dagen):
        R.noteer_uur(r, uur, 0.8 if i < keer_aan else 0.0, buiten_c=temp)
    return r


def test_zonder_factoren_verandert_er_niets():
    r = _ritme()
    oud = R.gebruik_kwh(r, NU, NU + timedelta(hours=6))
    assert oud["uren"] and oud["uren"][0]["kans"] == 0.4


def test_niemand_thuis_tot_na_dat_uur_geeft_geen_airco():
    r = _ritme()
    assert R.gebruik_kwh(r, NU, NU + timedelta(hours=6))["extra_kwh"] > 0
    uit = R.gebruik_kwh(r, NU, NU + timedelta(hours=6), thuis_factor=lambda u: 0.0)
    assert uit["extra_kwh"] == 0 and uit["uren"] == []


def test_een_koude_avond_telt_zwaarder_dan_een_zachte():
    r = _ritme(keer_aan=2, temp=12.0)                      # geleerd bij 12 graden
    koud = R.gebruik_kwh(r, NU, NU + timedelta(hours=6), temp_factor=lambda u: R.temperatuurfactor(r, u.hour, 4.0))
    zacht = R.gebruik_kwh(r, NU, NU + timedelta(hours=6), temp_factor=lambda u: R.temperatuurfactor(r, u.hour, 17.0))
    assert koud["extra_kwh"] > zacht["extra_kwh"]
    assert R.temperatuurfactor(r, 19, 4.0) == pytest.approx(min((12 + 1) / (4 + 1), 2.0))
    assert R.temperatuurfactor(r, 19, 17.0) == pytest.approx(R.TEMP_FACTOR_MIN)


def test_zonder_temperatuurgeschiedenis_factor_een():
    r = _ritme()                                           # oude uren zonder temperatuur
    assert R.temperatuurfactor(r, 19, 3.0) == 1.0
    assert R.temperatuurfactor(_ritme(temp=10.0), 19, None) == 1.0


def test_temperatuur_loopt_gelijk_op_met_het_verbruik():
    r = R.leeg()
    for _ in range(3):
        R.noteer_uur(r, 19, 0.5)                           # oud: zonder temperatuur
    R.noteer_uur(r, 19, 0.7, buiten_c=8.04)
    assert r["uurbuiten"]["19"] == [None, None, None, 8.0]
    for _ in range(20):
        R.noteer_uur(r, 19, 0.1, buiten_c=9.0)
    assert len(r["uurbuiten"]["19"]) == len(r["uurverbruik"]["19"]) == R.UURVERBRUIK_DAGEN
    assert R.geldig(r)["uurbuiten"]["19"][-1] == 9.0


def test_draait_hij_al_dan_telt_alles_zeker():
    r = _ritme()
    uit = R.gebruik_kwh(r, NU, NU + timedelta(hours=6), loopt_nu=True,
                        loopt_tot=NU + timedelta(hours=7), thuis_factor=lambda u: 0.0,
                        temp_factor=lambda u: 0.25)
    assert any(u["zeker"] for u in uit["uren"])


# --- de aanwezigheidsfactor in de coordinator ----------------------------

def _profiel(thuis_vanaf_uur=18):
    p = {}
    for dag in range(7):
        for uur in range(24):
            for half in ("00", "30"):
                thuis = uur >= thuis_vanaf_uur or uur < 8 or dag >= 5   # weekend thuis
                if dag == 1 and 12 <= uur < 18:             # dinsdagmiddag nooit thuis
                    thuis = False
                p[f"{dag}-{uur:02d}{half}"] = [10 if thuis else 0, 10]
    return p


def test_weg_tot_de_gewone_thuiskomst(make_coordinator, hass):
    c = make_coordinator({})
    c.presence_week_profile = _profiel(18)
    c.presence_state = "weg"
    f = c._airco_thuisfactor(NU)
    assert f(NU.replace(minute=0)) == 0.0                   # 15:00
    assert f(NU.replace(hour=17, minute=0)) == 0.0          # 17:00-18:00
    assert f(NU.replace(hour=19, minute=0)) == 1.0          # vanaf 18:00 thuis


def test_thuis_dan_alleen_de_dag_van_de_week(make_coordinator, hass):
    c = make_coordinator({})
    c.presence_week_profile = _profiel(18)
    c.presence_state = "thuis"
    f = c._airco_thuisfactor(NU)
    assert f(NU.replace(hour=13, minute=0)) == 0.0          # dinsdag 13:00: nooit thuis
    assert f(NU.replace(hour=20, minute=0)) == 1.0


def test_weg_zonder_geleerd_patroon_hooguit_een_uur(make_coordinator, hass):
    c = make_coordinator({})
    c.presence_week_profile = {}
    c.presence_state = "weg"
    f = c._airco_thuisfactor(NU)
    assert f(NU.replace(minute=0) - timedelta(minutes=0)) == 0.0     # 15:00-16:00 < 16:45
    assert f(NU.replace(hour=17, minute=0)) == 1.0


def test_buitentemperatuur_uit_de_uurverwachting(make_coordinator, hass):
    c = make_coordinator({})
    c._climate_cached_forecast = [(NU.replace(hour=h, minute=0), 10.0 - h / 10) for h in range(16, 24)]
    assert c._buiten_verwacht_c(NU.replace(hour=19, minute=0)) == pytest.approx(8.1)
    assert c._buiten_verwacht_c(NU + timedelta(days=2)) is None
