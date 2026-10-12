"""Wanneer veranderde de laadplanning het laatst? (v5.88)

Gevraagd: "Energiecockpit, ik wil op het dashboard laatste wijziging
timestamp voor planning accu laden".
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS

T0 = datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)


def _plan(laden_vanaf_kwartier: list[int], n: int = 40) -> list[dict]:
    return [
        {
            "start": (T0 + timedelta(minutes=15 * i)).isoformat(),
            "modus": "manual (laden)" if i in laden_vanaf_kwartier else "smart",
        }
        for i in range(n)
    ]


def test_eerste_plan_is_een_wijziging(make_coordinator, hass):
    c = make_coordinator({})
    c._volg_laadplan(_plan([10, 11, 12]), T0)
    w = c.get_laadplan_gewijzigd()
    assert w["om"] == T0.isoformat()
    assert len(w["kwartieren"]) == 3


def test_zelfde_plan_is_geen_wijziging(make_coordinator, hass):
    c = make_coordinator({})
    c._volg_laadplan(_plan([10, 11, 12]), T0)
    c._volg_laadplan(_plan([10, 11, 12]), T0 + timedelta(minutes=1))
    assert c.get_laadplan_gewijzigd()["om"] == T0.isoformat()


def test_verstreken_laadkwartier_is_geen_wijziging(make_coordinator, hass):
    """Om 02:46 is het laadkwartier van 02:30 voorbij: geen wijziging."""
    c = make_coordinator({})
    c._volg_laadplan(_plan([10, 11, 12]), T0 + timedelta(hours=2))
    later = T0 + timedelta(hours=2, minutes=46)
    c._volg_laadplan(_plan([10, 11, 12]), later)
    assert c.get_laadplan_gewijzigd()["om"] == (T0 + timedelta(hours=2)).isoformat()


def test_ander_laadblok_is_een_wijziging(make_coordinator, hass):
    c = make_coordinator({})
    c._volg_laadplan(_plan([10, 11, 12]), T0)
    nu = T0 + timedelta(minutes=5)
    c._volg_laadplan(_plan([10, 11]), nu)
    w = c.get_laadplan_gewijzigd()
    assert w["om"] == nu.isoformat()
    assert w["was"] and w["blokken"] != w["was"]


def test_laadplan_vervalt(make_coordinator, hass):
    c = make_coordinator({})
    c._volg_laadplan(_plan([10, 11]), T0)
    c._volg_laadplan(_plan([]), T0 + timedelta(minutes=1))
    assert c.get_laadplan_gewijzigd()["blokken"] == "geen laden uit het net gepland"


def test_blokken_samengevoegd():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    k = [T0 + timedelta(minutes=15 * i) for i in (0, 1, 2, 5)]
    tekst = C._laadblokken_tekst(k, T0)
    assert tekst.count(",") == 1


def test_wordt_bewaard():
    assert "laadplan_gewijzigd" in PERSISTED_PLAIN_FIELDS
