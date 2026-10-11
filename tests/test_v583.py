"""v5.83: het verwachte airco-gebruik in de reserve.

Akkoord Ruud 11-10 10:57: "als verwacht wordt dat de airco aangaat zeker
meenemen, eigen verbruik is belangrijker dan verkoop". Aanleiding: 09-10 en
10-10 's avonds 1,8 en 1,6 kWh airco die het mediaanprofiel niet zag.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import airco_ritme as ar

MAP = Path(pkg.__file__).parent
TZ = timezone(timedelta(hours=2))
VAN = datetime(2026, 10, 11, 18, 0, tzinfo=TZ)
TOT = datetime(2026, 10, 12, 11, 0, tzinfo=TZ)


def _ritme(uurverbruik: dict) -> dict:
    r = ar.leeg()
    r["uurverbruik"] = {str(k): v for k, v in uurverbruik.items()}
    return r


def test_minder_dan_de_helft_telt_naar_kans():
    # 2 van 5 avonden 0,4 kWh in het uur van 20:00: mediaan 0, kans 0,4
    r = _ritme({20: [0, 0.4, 0, 0.4, 0]})
    uit = ar.gebruik_kwh(r, VAN, TOT)
    assert uit["al_in_profiel_kwh"] == 0
    assert abs(uit["extra_kwh"] - 0.16) < 1e-6


def test_vaker_dan_de_helft_telt_volledig():
    r = _ritme({20: [0, 0.4, 0.4, 0.4, 0.3]})   # mediaan 0,4 zit al in het profiel
    uit = ar.gebruik_kwh(r, VAN, TOT)
    assert uit["extra_kwh"] == 0                 # typisch 0,4 - al 0,4
    r = _ritme({20: [0, 0.4, 0, 0.4, 0.4, 0]})   # kans 0,5, mediaan 0,2
    assert abs(ar.gebruik_kwh(r, VAN, TOT)["extra_kwh"] - 0.2) < 1e-6


def test_te_weinig_dagen_telt_niet():
    r = _ritme({20: [0.4, 0.4]})
    assert ar.gebruik_kwh(r, VAN, TOT)["extra_kwh"] == 0


def test_draait_nu_dan_zeker_tot_de_uittijd():
    r = _ritme({19: [0, 0, 0, 0.5], 20: [0, 0, 0, 0], 21: [0, 0, 0, 0], 22: [0, 0, 0, 0]})
    nu = datetime(2026, 10, 11, 19, 30, tzinfo=TZ)
    uit = ar.gebruik_kwh(r, nu, TOT, loopt_nu=True, loopt_tot=nu.replace(hour=22, minute=0))
    # 19:30-22:00 = 2,5 uur zeker, typisch 0,5 (uur 19) of alle-uren 0,5
    assert abs(uit["extra_kwh"] - 1.25) < 1e-6
    assert all(u["zeker"] for u in uit["uren"])
    assert "22:00" not in [u["uur"] for u in uit["uren"]]


def test_ochtend_blijft_bij_de_ochtendverwarming():
    r = _ritme({6: [0, 0.5, 0, 0.5, 0]})
    assert ar.gebruik_kwh(r, VAN, TOT)["extra_kwh"] > 0
    assert ar.gebruik_kwh(r, VAN, TOT, zonder_ochtend=True)["extra_kwh"] == 0


def test_leeg_ritme_niets():
    assert ar.gebruik_kwh(ar.leeg(), VAN, TOT)["extra_kwh"] == 0


def test_reserve_neemt_het_mee():
    coord = (MAP / "coordinator.py").read_text()
    assert 'needed_kwh += airco_gebruik["extra_kwh"]' in coord
    assert '"airco_gebruik_extra_kwh": airco_gebruik["extra_kwh"]' in coord
    # niet dubbel via het temperatuurmodel
    assert 'airco_ochtend["extra_kwh"] + airco_gebruik["extra_kwh"]' in coord


def test_coordinator_zonder_ritme_en_vermogen(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 11, 18, 0, tzinfo=TZ)
    assert c._airco_gebruik_extra_kwh(nu, nu + timedelta(hours=10))["extra_kwh"] == 0
    assert c._airco_gebruik_extra_kwh(nu, nu)["extra_kwh"] == 0
