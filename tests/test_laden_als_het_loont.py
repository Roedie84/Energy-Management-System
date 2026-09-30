"""Bijladen omdat het loont (v5.21).

Gemeld: "werkt het bijladen echt goed? Gezien ik dit nu regelmatig
handmatig doe." Het EMS laadde alleen van het net op dagen met weinig zon.
In vijf dagen koos het nooit zelf voor laden. Beide handmatige laadbeurten
waren rendabel:

    26 sep   6,6 kWh tegen 17,6 ct   break-even 32,4 ct   avond 40,3 ct
    27 sep   3,1 kWh tegen 13,1 ct   break-even 27,1 ct   avond 37,5 ct
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

NU = datetime(2026, 9, 27, 14, 15, tzinfo=timezone.utc)
BLOK = (NU - timedelta(minutes=15), NU + timedelta(hours=2))


def _stel_in(
    c,
    *,
    prijs_nu=0.131,
    later=(0.384,) * 4 + (0.375,) * 4 + (0.30,) * 8 + (0.22,) * 40,
    ruimte=3.0,
    beschikbaar=0.4,
    zonoverschot=0.0,
    salderen=True,
):
    c.huidige_prijs_eur_per_kwh = lambda: prijs_nu
    c._resterende_laadruimte_kwh = lambda: ruimte
    c.beschikbare_energie_kwh = lambda: beschikbaar
    # het geleerde rendement komt uit de gemeten halve slagen, net als in
    # test_verkopen_na_saldering: 83,7% heen, 100% terug
    c.charge_efficiency_history = [83.7] * 7
    c.discharge_efficiency_history = [100.0] * 7
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 11.40}
    c._is_salderen_active = lambda now: salderen
    c._verwacht_zonoverschot_kwh = lambda a, b, veilig=True: zonoverschot
    avond = BLOK[1] + timedelta(hours=2)
    c._get_forecast_entries = lambda **kw: [
        (avond + timedelta(minutes=15 * i), avond + timedelta(minutes=15 * (i + 1)),
         p * PRICE_SCALE_FACTOR)
        for i, p in enumerate(later)
    ]
    return c


def test_27_september_had_moeten_laden(make_coordinator, hass):
    """13,1 ct nu, de volgende kWh gaat in een kwartier van 38,4 ct:
    38,4 x 83,7% - 11,4 = 20,7 ct waard. Dat loont."""
    c = _stel_in(make_coordinator({}))

    besluit = c.laadbesluit_uit_het_net(NU, *BLOK)

    assert besluit["laden"] is True
    assert besluit["marge_ct"] == pytest.approx(7.6, abs=0.2)


def test_de_zon_vult_de_accu_dan_niet_laden(make_coordinator, hass):
    """Nooit kopen wat de zon gratis levert."""
    c = _stel_in(make_coordinator({}), zonoverschot=3.5)

    besluit = c.laadbesluit_uit_het_net(NU, *BLOK)

    assert besluit["laden"] is False
    assert "zon" in besluit["reden"]


def test_te_duur_nu_dan_niet_laden(make_coordinator, hass):
    """30 ct nu tegen 20,7 ct waarde later: dat is verlies."""
    c = _stel_in(make_coordinator({}), prijs_nu=0.30)

    besluit = c.laadbesluit_uit_het_net(NU, *BLOK)

    assert besluit["laden"] is False
    assert besluit["marge_ct"] < 0


def test_het_laden_stopt_waar_het_niet_meer_loont(make_coordinator, hass):
    """Wat al in de accu zit gaat naar de duurste kwartieren. Met 3,2 kWh
    erin zijn de acht dure kwartieren gevuld, en de volgende kWh komt in
    een kwartier van 30 ct: 30 x 83,7% - 11,4 = 13,7 ct. Nog net winst.
    Met 6,4 kWh erin valt hij in een kwartier van 22 ct: 7,0 ct - verlies."""
    c = _stel_in(make_coordinator({}), beschikbaar=3.2, ruimte=5.0)
    assert c.laadbesluit_uit_het_net(NU, *BLOK)["laden"] is True

    c = _stel_in(make_coordinator({}), beschikbaar=6.4, ruimte=2.0)
    assert c.laadbesluit_uit_het_net(NU, *BLOK)["laden"] is False


def test_buiten_het_blok_niet_als_de_accu_het_blok_haalt(make_coordinator, hass):
    """v5.25: buiten het blok alleen in een prijsdip, en dan alleen als de
    accu het volgende blok NIET haalt - zie test_laden_in_een_dip.py. Hier
    is er geen spaarplan actief, dus geen dip."""
    c = _stel_in(make_coordinator({}))

    besluit = c.laadbesluit_uit_het_net(BLOK[1] + timedelta(minutes=5), *BLOK)

    assert besluit["laden"] is False


def test_zonder_prijs_of_ruimte_niet_laden(make_coordinator, hass):
    """Ontbreekt een gegeven, dan niet laden in plaats van een gok."""
    c = _stel_in(make_coordinator({}))
    c.huidige_prijs_eur_per_kwh = lambda: None

    assert c.laadbesluit_uit_het_net(NU, *BLOK)["laden"] is False


def test_voorzichtige_zon_zolang_de_saldering_loopt(make_coordinator, hass):
    """Te veel laden kost dan bijna niets - het middagoverschot gaat tegen
    ongeveer dezelfde middagprijs het net op. Te weinig laden kost de marge."""
    c = _stel_in(make_coordinator({}))
    gezien = {}

    def overschot(a, b, veilig=True):
        gezien["veilig"] = veilig
        return 0.0

    c._verwacht_zonoverschot_kwh = overschot
    c.laadbesluit_uit_het_net(NU, *BLOK)
    assert gezien["veilig"] is True

    c._is_salderen_active = lambda now: False
    c.laadbesluit_uit_het_net(NU, *BLOK)
    assert gezien["veilig"] is False


@pytest.mark.asyncio
async def test_laden_omdat_het_loont_verbiedt_de_avondverkoop_niet(
    make_coordinator, hass
):
    """`_grid_charged_today` schakelt de verkoop in dure kwartieren uit.
    Bij laden uit nood terecht; bij laden omdat het loont is die verkoop
    juist het doel."""
    c = _stel_in(make_coordinator({}))
    c._grid_charged_today = False
    toegepast = []

    async def pas_toe(vermogen):
        toegepast.append(vermogen)

    c._async_apply_manual = pas_toe
    c._update_financial_tracking = lambda *a, **k: None
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda now: None

    geladen = await c._laad_uit_het_net_als_nodig(NU, [], False, *BLOK)

    assert geladen is True
    assert c.last_reason == "grid_charging_profitable"
    assert toegepast and toegepast[0] < 0
    assert c._grid_charged_today is False


@pytest.mark.asyncio
async def test_laden_bij_weinig_zon_houdt_voorrang(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    c._grid_charged_today = False

    async def pas_toe(vermogen):
        pass

    c._async_apply_manual = pas_toe
    c._update_financial_tracking = lambda *a, **k: None
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda now: None

    await c._laad_uit_het_net_als_nodig(NU, [], True, *BLOK)

    assert c.last_reason == "grid_charging_low_solar"
    assert c._grid_charged_today is True


def test_de_waarom_regels_tonen_de_getallen_van_het_besluit(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    c.last_laadbesluit = c.laadbesluit_uit_het_net(NU, *BLOK)

    regels = " · ".join(c._waarom_bij_laden("grid_charging_profitable", [], None))

    assert "stroom kost nu 13.1 ct" in regels
    assert "38.4 ct x 84%" in regels
    assert "11.4 ct slijtage" in regels
