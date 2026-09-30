"""Laden in een prijsdip, buiten het goedkope blok (v5.25).

Gevraagd: "en wanneer het kosten efficient genoeg is gaat hij bij laden van
het net toch?" Alleen als de accu het volgende blok niet haalt, en het
duurste kwartier dat hij niet dekt meer oplevert dan de stroom nu kost:

    waarde = duurste ongedekte kwartier x rendement - slijtage
"""
from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 11, 20, 2, 0, tzinfo=TZ)
BLOK = datetime(2026, 11, 20, 13, 0, tzinfo=TZ)


def _stel_in(c, *, prijs_nu, duurste_ongedekt, beschikbaar=1.0, nodig=3.0, actief=True):
    c.spaarplan = lambda now, entries, blok: {
        "actief": actief, "beschikbaar_kwh": beschikbaar, "nodig_kwh": nodig,
        "duurste_ongedekt_eur": duurste_ongedekt, "blok": BLOK.isoformat(),
    }
    c._get_forecast_entries = lambda **kw: []
    c.huidige_prijs_eur_per_kwh = lambda: prijs_nu
    c._resterende_laadruimte_kwh = lambda: 6.0
    c.charge_efficiency_history = [83.7] * 7
    c.discharge_efficiency_history = [100.0] * 7
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 11.40}
    return c


def test_een_winderige_nacht_loont(make_coordinator, hass):
    """15 ct nu, de ochtendpiek van 40 ct wordt niet gedekt:
    40 x 83,7% - 11,4 = 22,1 ct waard. Dat loont."""
    c = _stel_in(make_coordinator({}), prijs_nu=0.15, duurste_ongedekt=0.40)

    besluit = c._dipbesluit(NU, BLOK)

    assert besluit["laden"] is True
    assert besluit["marge_ct"] == pytest.approx(7.1, abs=0.1)
    assert besluit["gat_kwh"] == 2.0  # nooit meer dan er tot het blok ontbreekt


def test_29_september_loont_niet(make_coordinator, hass):
    """Nacht 25 ct tegen 22,1 ct waarde: dan spaart het EMS in plaats daarvan
    - dat verschuift zonder rendementsverlies."""
    c = _stel_in(make_coordinator({}), prijs_nu=0.25, duurste_ongedekt=0.40)

    assert c._dipbesluit(NU, BLOK)["laden"] is False


def test_haalt_de_accu_het_blok_dan_nooit(make_coordinator, hass):
    """Anders koop je nu wat het blok straks goedkoper levert."""
    c = _stel_in(make_coordinator({}), prijs_nu=0.10, duurste_ongedekt=0.40, actief=False)

    assert c._dipbesluit(NU, BLOK)["laden"] is False


def test_zonder_prijs_geen_gok(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), prijs_nu=None, duurste_ongedekt=0.40)

    assert c._dipbesluit(NU, BLOK)["laden"] is False


def test_buiten_het_blok_gaat_het_laadbesluit_naar_de_dipregel(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), prijs_nu=0.15, duurste_ongedekt=0.40)
    blok = (BLOK, BLOK + timedelta(hours=2))

    besluit = c.laadbesluit_uit_het_net(NU, *blok)

    assert besluit["soort"] == "dip" and besluit["laden"] is True


@pytest.mark.asyncio
async def test_de_dip_heeft_een_eigen_reden(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), prijs_nu=0.15, duurste_ongedekt=0.40)
    toegepast = []

    async def pas_toe(vermogen):
        toegepast.append(vermogen)

    c._async_apply_manual = pas_toe
    c._update_financial_tracking = lambda *a, **k: None
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda now: None
    c._grid_charged_today = False

    await c._laad_uit_het_net_als_nodig(NU, [], False, BLOK, BLOK + timedelta(hours=2))

    assert c.last_reason == "grid_charging_dip"
    assert toegepast and toegepast[0] < 0
    # geen winterbeveiliging: de lading is voor het huis in de piek
    assert c._grid_charged_today is False


def test_de_waarom_regels_van_de_dip(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), prijs_nu=0.15, duurste_ongedekt=0.40)
    c.last_laadbesluit = c._dipbesluit(NU, BLOK)

    regels = " · ".join(c._waarom_bij_laden("grid_charging_dip", [], None))

    assert "stroom kost nu 15.0 ct" in regels
    assert "13:00 niet" in regels
    assert "40.0 ct x 84%" in regels


def test_de_dip_heeft_een_titel_in_het_register():
    from custom_components.energy_management_system.const import REASON_REGISTRY

    assert REASON_REGISTRY["grid_charging_dip"]["titel"] == "Bijladen in een prijsdip"


# --- in het kwartierplan -------------------------------------------------


def _netregels(prijzen_tekort, blok_start):
    start = NU
    kwartieren = [
        (start + timedelta(minutes=15 * i), p, d) for i, (p, d) in enumerate(prijzen_tekort)
    ]
    return {
        "kwartieren": kwartieren,
        "volgend_blok": {b: blok_start for b, _p, _d in kwartieren},
        "rendement": 83.7,
        "slijtage_ct": 11.40,
    }


def test_het_plan_laadt_in_de_dip(make_coordinator, hass):
    """Nacht 15 ct, straks acht kwartieren ochtendpiek van 40 ct met elk
    0,1 kWh tekort; de gesimuleerde lading is op."""
    c = make_coordinator({})
    netregels = _netregels([(0.15, 0.08)] * 4 + [(0.40, 0.1)] * 8, NU + timedelta(hours=3))

    geladen = c._plan_dip_laadt(netregels, NU, 0.15, soc=0.0, bruikbaar=7.78, laad_kwh=0.5)

    assert geladen == 0.5


def test_het_plan_laadt_niet_als_de_lading_de_piek_al_dekt(make_coordinator, hass):
    c = make_coordinator({})
    netregels = _netregels([(0.15, 0.08)] * 4 + [(0.40, 0.1)] * 8, NU + timedelta(hours=3))

    assert c._plan_dip_laadt(netregels, NU, 0.15, soc=1.2, bruikbaar=7.78, laad_kwh=0.5) == 0.0


def test_het_plan_laadt_niet_bij_een_te_hoge_nachtprijs(make_coordinator, hass):
    c = make_coordinator({})
    netregels = _netregels([(0.25, 0.08)] * 4 + [(0.40, 0.1)] * 8, NU + timedelta(hours=3))

    assert c._plan_dip_laadt(netregels, NU, 0.25, soc=0.0, bruikbaar=7.78, laad_kwh=0.5) == 0.0
