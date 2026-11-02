"""v5.165.0 punt 4 - net_w van het lopende kwartier in de plantabel.

Gemeld 02-11: 10.511 W net terwijl het huis 559 W gebruikte. Het waardeplan
rekent één keer per kwartier; de eerste rij gold voor de rest van het
kwartier op dat moment. Een paar minuten later telt de planregel nog maar
een minuut, en verbruik - zon van het hele kwartier werd door die minuut
gedeeld. Alleen weergave.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import planvolging
from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C


def test_rij_van_een_heel_kwartier_een_minuut_later():
    # huis 700 W over het hele kwartier, accu doet niets
    rij = {"net_kwh": 0.175, "accu_kwh": 0.0, "uren": 0.25}
    uren = 1 / 60
    net = C._waardeplan_net_kwh(rij, uren, True)
    assert net / uren * 1000 == pytest.approx(700, abs=30)


def test_accustap_telt_naar_rato_van_een_kwartier():
    # 2,4 kW laden (0,6 kWh per kwartier) plus 400 W huis, nog 5 minuten
    rij = {"net_kwh": 0.1 + 0.6, "accu_kwh": 0.6, "uren": 0.25}
    uren = 5 / 60
    net = C._waardeplan_net_kwh(rij, uren, True)
    assert net / uren * 1000 == pytest.approx(2800, abs=30)


def test_verse_rij_van_de_rest_van_het_kwartier():
    # de rij rekende al over 6 minuten; de planregel ook
    uren = 0.1
    rij = {"net_kwh": 0.04 + 0.6, "accu_kwh": 0.6, "uren": uren}
    net = C._waardeplan_net_kwh(rij, uren, True)
    assert net / uren * 1000 == pytest.approx(400 + 2400, abs=30)


def test_waardeplan_geeft_de_duur_mee():
    nu = datetime(2026, 11, 2, 12, 9, tzinfo=timezone.utc)
    kw = [W.Kwartier(nu, 0.06, 0.0, 0.3, 0.1, uren=0.1)]
    kw += [W.Kwartier(nu.replace(minute=15) + timedelta(minutes=15 * i), 0.1, 0.0, 0.3, 0.1) for i in range(4)]
    res = W.plan(kw, W.Accu(inhoud_kwh=1.0, bruikbaar_kwh=4.0))
    assert res.kwartieren[0]["uren"] == 0.1
    assert res.kwartieren[1]["uren"] == 0.25


def test_plantabel_toont_het_huisverbruik(make_coordinator, hass):
    c = make_coordinator({})
    begin = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)
    c._waardeplan_rijen = [{
        "begin": begin, "actie": "houden", "kwh": 0.0, "accu_kwh": 0.0, "net_kwh": 0.14,
        "inhoud_kwh": 1.0, "inhoud_delta_kwh": 0.0, "vol_vermogen": False, "prijs_eur": 0.3,
        "uren": 0.25,
    }]
    regel = {"start": begin.isoformat(), "uren": 2 / 60, "modus": "smart", "verbruik_kwh": 0.0187,
             "zon_kwh": 0.0, "soc_kwh": 1.0, "net_kwh": 0.0187}
    plan = c._met_waardeplan([regel])
    w = planvolging.vermogens_per_kwartier(plan, 1.0)[0]["net_w"]
    assert w == pytest.approx(560, abs=20)
