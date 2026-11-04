"""v5.161.3 - storingsvlag, planvolging lopend kwartier, valse kostenmelding."""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import planvolging
from custom_components.energy_management_system.const import RELIABILITY_RELIABLE, RELIABILITY_UNRELIABLE
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C
from custom_components.energy_management_system.waardeplan import Accu, Kwartier, plan


def _fout():
    raise ValueError("kapot")


def test_vlag_gaat_eraf_na_geslaagde_stap(make_coordinator, hass):
    c = make_coordinator({})
    c._voer_staartstap_uit("proef", _fout)
    assert "ronde:proef" in c.internal_failures
    c._voer_staartstap_uit("proef", lambda: None)
    assert "ronde:proef" not in c.internal_failures


def test_vlag_van_ander_onderdeel_blijft(make_coordinator, hass):
    c = make_coordinator({})
    c._voer_staartstap_uit("een", _fout)
    c._voer_staartstap_uit("twee", lambda: None)
    assert "ronde:een" in c.internal_failures


def test_vlag_blijft_als_stap_blijft_vallen(make_coordinator, hass):
    c = make_coordinator({})
    c._voer_staartstap_uit("proef", _fout)
    c._voer_staartstap_uit("proef", _fout)
    assert "ronde:proef" in c.internal_failures


def test_delta_hangt_niet_af_van_afronding_of_startstand():
    rij = {"inhoud_delta_kwh": 0.0, "soc_kwh": 1.6, "uren": 0.0717}
    assert planvolging.gepland_uit_plan(rij, 1.6128)["accu_w"] == 0
    rij = {"inhoud_delta_kwh": 0.4, "soc_kwh": 1.8, "uren": 0.05}
    assert planvolging.gepland_uit_plan(rij, 0.9)["accu_w"] == -1600


def test_zonder_delta_de_oude_rekenwijze():
    rij = {"soc_kwh": 1.0, "uren": 0.25}
    assert planvolging.gepland_uit_plan(rij, 1.5)["accu_w"] == 2000
    assert planvolging.vermogens_per_kwartier([rij], None)[0]["accu_w"] is None
    assert planvolging.vermogens_per_kwartier([rij], 1.5)[0]["accu_w"] == 2000


def test_vermogens_met_delta_in_lopend_kwartier():
    rijen = [
        {"inhoud_delta_kwh": 0.1, "soc_kwh": 1.7, "uren": 0.0717, "net_kwh": 0.05},
        {"inhoud_delta_kwh": 0.2, "soc_kwh": 1.9, "uren": 0.25, "net_kwh": 0.3},
    ]
    uit = planvolging.vermogens_per_kwartier(rijen, 1.6128)
    assert [r["accu_w"] for r in uit] == [-400, -800]
    assert uit[0]["net_w"] == round(0.05 * 1000 / 0.0717)


def test_waardeplan_geeft_delta_mee():
    nu = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    kw = [Kwartier(nu + timedelta(minutes=15 * i), 0.1, 0.0, 0.1 + 0.1 * (i > 3), 0.1) for i in range(8)]
    res = plan(kw, Accu(inhoud_kwh=1.0, bruikbaar_kwh=4.0))
    inhoud = 1.0
    for r in res.kwartieren:
        inhoud += r["inhoud_delta_kwh"]
        # v5.186.0: doorlopende inhoud, per rij op 0,001 kWh afgerond
        assert inhoud == pytest.approx(r["inhoud_kwh"], abs=0.002)


def test_net_eerste_rij_alleen_accustap_schalen():
    rij = {"net_kwh": 0.175, "accu_kwh": 0.134}
    assert C._waardeplan_net_kwh(rij, 0.075, True) == pytest.approx(0.041 + 0.134 * 0.3, abs=0.001)


def test_net_oudere_rij_helemaal_schalen():
    assert C._waardeplan_net_kwh({"net_kwh": 0.2, "accu_kwh": 0.1}, 0.125, False) == pytest.approx(0.1)


def test_net_heel_kwartier_ongemoeid():
    assert C._waardeplan_net_kwh({"net_kwh": 0.2, "accu_kwh": 0.1}, 0.25, True) == 0.2


def _kosten(stand, status=RELIABILITY_UNRELIABLE):
    return {"status": status, "zonneplan_netto_eur": stand}


def test_kostenmelding_pas_na_drie_standen(make_coordinator, hass):
    c = make_coordinator({})
    assert not c._kostenverschil_bevestigd(_kosten(1.27))
    assert not c._kostenverschil_bevestigd(_kosten(1.27))
    assert not c._kostenverschil_bevestigd(_kosten(1.60))
    assert c._kostenverschil_bevestigd(_kosten(1.90))


def test_achterlopende_teller_geeft_geen_melding(make_coordinator, hass):
    c = make_coordinator({})
    c._kostenverschil_bevestigd(_kosten(1.27))
    c._kostenverschil_bevestigd(_kosten(1.60))
    c._kostenverschil_bevestigd(_kosten(2.27, RELIABILITY_RELIABLE))
    assert not c._kostenverschil_bevestigd(_kosten(2.40))
