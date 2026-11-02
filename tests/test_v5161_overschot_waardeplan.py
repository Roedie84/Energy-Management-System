"""v5.161.0 - L-EMS-053: overschotdagen tellen weer onder het waardeplan.

Sinds v5.158.0 stuurt het waardeplan met de redenen 'waardeplan_huis'
(stand smart) en 'waardeplan_verkopen' (stand manual). De overschotmeting
liep alleen bij stand smart_discharging en de dure-kwartierredenen, dus
geen dag telde nog als overschotdag en de reservemarge kon alleen stijgen.
"""
from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 2, 19, 0, tzinfo=TZ)


def _c(make_coordinator):
    c = make_coordinator({})
    c._shortfall_check_date = NU.date()
    c._excess_detected_today = False
    c._shortfall_detected_today = False
    c._import_verklaard_door_ontlaadgrens = lambda reden: True
    return c


@pytest.mark.parametrize("reden", ["waardeplan_huis", "waardeplan_verkopen"])
def test_waardeplan_telt_als_overschotdag(make_coordinator, hass, reden):
    c = _c(make_coordinator)
    c._update_shortfall_detection(NU, reden, available_kwh=6.0, needed_kwh=2.0)
    assert c._excess_detected_today is True


@pytest.mark.parametrize("reden", ["waardeplan_houden", "waardeplan_laden"])
def test_houden_en_laden_tellen_niet(make_coordinator, hass, reden):
    c = _c(make_coordinator)
    c._update_shortfall_detection(NU, reden, available_kwh=6.0, needed_kwh=2.0)
    assert c._excess_detected_today is False


def test_krappe_voorraad_is_geen_overschot(make_coordinator, hass):
    c = _c(make_coordinator)
    c._update_shortfall_detection(NU, "waardeplan_huis", available_kwh=2.1, needed_kwh=2.0)
    assert c._excess_detected_today is False


def test_de_dag_wordt_afgesloten_met_overschot(make_coordinator, hass):
    c = _c(make_coordinator)
    c._update_shortfall_detection(NU, "waardeplan_huis", available_kwh=6.0, needed_kwh=2.0)
    voor = c.current_month_excess_days
    c._tekortnacht_vandaag_kwh = 0.0
    c._update_shortfall_detection(NU + timedelta(hours=6), "default_smart")
    assert c.reserve_daily_records[-1]["excess"] is True
    assert c.current_month_excess_days == voor + 1
