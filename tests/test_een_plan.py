"""Een plan op het scherm (v5.26).

Gemeld: "planning komt nog niet overeen met de werkelijkheid?" De kaart
"Komend schema" toonde de oude tijdlijn (`_build_forecast_timeline`), een
tweede simulatie met eigen regels. Om 12:47 op 30 september:

    export (kwartierplan)   12:45-13:15 laden    avond: slim
    kaart (oude tijdlijn)   12:45-17:45 slim     avond: verkopen

terwijl het EMS op dat moment laadde - bij weinig zon.
"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=2))
START = datetime(2026, 9, 30, 12, 45, tzinfo=TZ)


def _rij(i, modus, prijs):
    return {"start": (START + timedelta(minutes=15 * i)).isoformat(), "modus": modus, "prijs_ct": prijs}


def test_het_kwartierplan_wordt_blokken(make_coordinator, hass):
    c = make_coordinator({})
    c.get_quarter_plan = lambda now=None: [
        _rij(0, "manual (laden)", 17.2),
        _rij(1, "manual (laden)", 19.7),
        _rij(2, "smart", 23.2),
        _rij(3, "smart", 23.8),
        _rij(4, "manual (verkopen)", 44.8),
    ]

    blokken = c.get_plan_blokken()

    assert [b["mode"] for b in blokken] == ["manual (laden)", "smart", "manual (verkopen)"]
    assert blokken[0]["start"] == START.isoformat()
    assert blokken[0]["end"] == (START + timedelta(minutes=30)).isoformat()
    assert blokken[0]["min_price_per_kwh"] == 0.172
    assert blokken[0]["max_price_per_kwh"] == 0.197


def test_een_gat_in_de_tijd_is_een_nieuw_blok(make_coordinator, hass):
    c = make_coordinator({})
    c.get_quarter_plan = lambda now=None: [_rij(0, "smart", 20.0), _rij(2, "smart", 21.0)]

    assert len(c.get_plan_blokken()) == 2


def test_de_kaart_toont_het_kwartierplan(make_coordinator, hass):
    """De sensor achter "Komend schema" en "blok(ken) gepland"."""
    from custom_components.energy_management_system.sensor import UpcomingTimelineSensor

    c = make_coordinator({})
    c.get_quarter_plan = lambda now=None: [_rij(0, "manual (laden)", 17.2)]
    c.last_transitions = [{"mode": "smart", "start": "oud", "end": "oud"}]

    sensor = UpcomingTimelineSensor(c, "entry")

    assert sensor.extra_state_attributes["transitions"][0]["mode"] == "manual (laden)"
    assert sensor.native_value == 1


def test_het_plan_laadt_het_blok_bij_weinig_zon(make_coordinator, hass):
    """Zoals de beslissing (`grid_charging_low_solar`): het hele blok,
    ongeacht de marge - tot de accu vol is."""
    c = make_coordinator({})
    netregels = {"weinig_zon": True, "slijtage_ct": 11.40, "rendement": 83.7, "reeks": []}

    assert c._plan_laadt(netregels, START, 0.172, soc=4.0, bruikbaar=7.78, laad_kwh=0.5, per_kwartier=0.4) == 0.5
    assert c._plan_laadt(netregels, START, 0.172, soc=7.6, bruikbaar=7.78, laad_kwh=0.5, per_kwartier=0.4) == pytest_approx(0.18)


def pytest_approx(waarde):
    import pytest

    return pytest.approx(waarde, abs=1e-9)
