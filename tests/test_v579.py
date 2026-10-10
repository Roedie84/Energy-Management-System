"""v5.79 (akkoord Ruud 10-10 19:37): ontladen dekt het huis; terugleveren
alleen uit de vrije ruimte boven de reserve tot het blok.

Gezien op 10-10 18:45-19:00: expensive_quarter, Zendure ~2,4 kW, P1 -1,8..-1,9
kW, beschikbaar 6,91 -> 6,22 kWh tegen 6,78 kWh reserve tot het blok (5,42 x
marge 1,25), blok morgen 10:45. De poort per ronde klopte, het vermogen niet:
2,4 kW vast, ongeacht hoeveel er vrij was.
"""
from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 10, 18, 46, tzinfo=TZ)


def _c(make_coordinator, huis_w=500.0, tot=5.42, salderen="2026-12-31"):
    c = make_coordinator({"salderen_end_date": salderen, "update_interval_seconds": 60})
    c._read_corrected_consumption_power = lambda: huis_w
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.last_reserve_margin_breakdown = {
        "needed_kwh_before_margin": tot + 1.0, "lange_horizon_extra_kwh": 1.0,
        "total_percent": 25.0,
    }
    return c


def test_verkooptoets_nee_dan_alleen_het_huis(make_coordinator):
    """Het scenario: beschikbaar 6,22 < 6,78 nodig - geen export."""
    c = _c(make_coordinator)
    c.last_sell_check = {"mag_verkopen": False, "beschikbaar_kwh": 6.22, "nodig_voor_woning_kwh": 6.78}
    assert c.cap_discharge_to_own_consumption(NU, 2400.0) == 500.0
    assert c.last_ontlaadgrens["export_max_w"] == 0.0


def test_verkooptoets_ja_maar_de_reserve_tot_het_blok_gaat_voor(make_coordinator):
    """De verkooptoets gaf 0,5 kWh vrij, maar boven 5,42 x 1,25 = 6,78 zit maar
    0,13 kWh: alleen die mag eruit, verdeeld over de rest van het kwartier."""
    c = _c(make_coordinator)
    c.last_sell_check = {"mag_verkopen": True, "beschikbaar_kwh": 6.91, "vrij_te_verkopen_kwh": 0.5}
    vermogen = c.cap_discharge_to_own_consumption(NU, 2400.0)
    rest_h = 14 / 60
    assert vermogen == pytest.approx(500.0 + (6.91 - 5.42 * 1.25) / rest_h * 1000, abs=1)
    assert c.last_ontlaadgrens["vrij_te_verkopen_kwh"] == pytest.approx(0.135, abs=0.001)
    # in een kwartier niet meer dan de vrije ruimte eruit (huis + 0,13 kWh)
    assert (vermogen - 500.0) / 1000 * rest_h <= 0.135 + 1e-4


def test_een_ronde_verkoopt_nooit_meer_dan_er_vrij_is(make_coordinator):
    """Vlak voor het kwartiereinde: minstens één ronde (60 s) als noemer."""
    c = _c(make_coordinator)
    c.last_sell_check = {"mag_verkopen": True, "beschikbaar_kwh": 6.80, "vrij_te_verkopen_kwh": 0.02}
    laat = NU.replace(minute=59, second=50)
    vermogen = c.cap_discharge_to_own_consumption(laat, 2400.0)
    assert (vermogen - 500.0) / 1000 * (60 / 3600) <= 0.02 + 1e-6


def test_met_ruimte_mag_het_volle_vermogen(make_coordinator):
    c = _c(make_coordinator, tot=2.0)
    c.last_sell_check = {"mag_verkopen": True, "beschikbaar_kwh": 7.0, "vrij_te_verkopen_kwh": 4.0}
    assert c.cap_discharge_to_own_consumption(NU, 2400.0) == 2400.0


def test_niets_te_dekken_en_niets_vrij_dan_slim(make_coordinator):
    c = _c(make_coordinator, huis_w=40.0)
    c.last_sell_check = {"mag_verkopen": False, "beschikbaar_kwh": 6.22}
    assert c.cap_discharge_to_own_consumption(NU, 2400.0) is None


def test_ook_na_salderen_eerst_de_verkoopruimte(make_coordinator):
    c = _c(make_coordinator, salderen="2026-01-01")
    c.last_sell_check = {"mag_verkopen": False, "beschikbaar_kwh": 6.22}
    assert c.cap_discharge_to_own_consumption(NU, 2400.0) <= 500.0 + 1e-6


def test_zonder_verkooptoets_onveranderd(make_coordinator):
    c = _c(make_coordinator)
    c.last_sell_check = None
    assert c.cap_discharge_to_own_consumption(NU, 2400.0) == 2400.0


def test_het_dagverloop_bewaart_de_verkooptoets(make_coordinator):
    c = _c(make_coordinator)
    c.last_sell_check = {"mag_verkopen": False}
    c._leg_dagverloop_vast(NU)
    assert c.dagverloop[NU.date().isoformat()][-1]["mag_verkopen"] is False
