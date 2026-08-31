"""De bodem werd berekend en daarna weggegooid (v3.92.1).

Openstaand punt 1 uit de overdracht: "De reservebodem grijpt te laat in."
Gemeten in de nacht van 30 op 31 augustus:

    opwek 6,04   verbruik 9,03   import 9,74   ontladen 7,69
    naar het net 3,65
    accu 's ochtends: 17 %   (voorspeld was 52 %)

De aanname was dat de bodem op de MOMENTOPNAME werkt en niet in de
vooruitberekening. Nagerekend klopt dat maar half: de bodem werkte
helemaal niet.

`_get_dynamic_discharge_reserve_kwh` rekent de bodem uit, zet hem in
`last_reserve_margin_breakdown` — dat is wat het dashboard toont — en
geeft daarna `needed_kwh * margin` terug, dus de waarde van vóór de
bodem. Gemeten bij een diepste tekort van 0,001 kWh en 7,78 kWh
bruikbaar:

    gemeld aan het dashboard   1,167 kWh   bodem bindend: true
    teruggegeven aan de sturing 0,00125 kWh

De zeven toetsen van v3.74.0 keken allemaal naar de uitsplitsing of naar
de constante, geen enkele naar wat de functie teruggaf. Vierde keer dat
een toets de aanname bevestigde in plaats van de code.

En de kwartierplanning kent de bodem sowieso niet: die simuleert zijn
eigen reserve, en die valt op nul zodra het goedkope blok begonnen is.
Daardoor plant hij 's avonds verkoop tot de accu leeg is.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    RESERVE_BODEM_FRACTIE,
)

NU = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
BLOK = NU + timedelta(hours=13)


# --- 1. wat de functie TERUGGEEFT ------------------------------------


def _reserve(c, diepste, capaciteit=7.78):
    c.bruikbare_capaciteit_kwh = lambda: capaciteit
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: diepste
    return c._get_dynamic_discharge_reserve_kwh(NU, BLOK)


def test_de_teruggegeven_reserve_houdt_de_bodem_aan(make_coordinator, hass):
    """Het geval waar het om gaat: de voorspelling zegt dat er niets

    nodig is, en dan hoort de bodem eronder te staan — niet alleen in
    het dashboard.
    """
    c = make_coordinator({})

    teruggegeven = _reserve(c, diepste=0.001)

    assert teruggegeven == pytest.approx(7.78 * RESERVE_BODEM_FRACTIE, abs=0.01)


def test_wat_teruggegeven_wordt_is_wat_gemeld_wordt(make_coordinator, hass):
    """De uitsplitsing is geen apart getal: het dashboard hoort te tonen

    waar de sturing werkelijk mee rekent.
    """
    c = make_coordinator({})

    teruggegeven = _reserve(c, diepste=0.001)
    gemeld = c.last_reserve_margin_breakdown["reserve_kwh_after_margin"]

    assert teruggegeven == pytest.approx(gemeld, abs=0.001)


def test_een_echt_tekort_wint_nog_steeds(make_coordinator, hass):
    """De bodem vervangt de berekening niet, hij staat eronder."""
    c = make_coordinator({})

    teruggegeven = _reserve(c, diepste=5.0)

    assert teruggegeven > 7.78 * RESERVE_BODEM_FRACTIE
    assert c.last_reserve_margin_breakdown["bodem_bindend"] is False


def test_zonder_capaciteit_geen_verzonnen_bodem(make_coordinator, hass):
    """Geen capaciteit betekent geen bodem — beter dan een grens uit het

    niets.
    """
    c = make_coordinator({})

    teruggegeven = _reserve(c, diepste=0.001, capaciteit=None)

    assert teruggegeven == pytest.approx(0.00125, abs=0.001)


# --- 2. de bodem in de vooruitberekening ------------------------------


def _plan_situatie(c, hass, beschikbaar_kwh, capaciteit=8.64):
    """Een dag met dure kwartieren en een accu die deels vol is."""
    from conftest import make_price_forecast

    dag0 = datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc)
    hass.states.set(
        "sensor.price",
        "0.40",
        {
            "forecast": make_price_forecast(
                dag0, lambda h, m: 1_200_000 if 2 <= h < 6 else 4_000_000
            )
        },
    )
    hass.states.set("sensor.capaciteit", str(capaciteit))
    c.beschikbare_energie_kwh = lambda: beschikbaar_kwh
    c.bruikbare_capaciteit_kwh = lambda: capaciteit
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 0.001
    c._verbruik_met_terugval = lambda start, einde: 0.06
    c._estimate_pv_kwh_for_period = lambda start, einde: 0.0
    c.last_expensive_price_threshold = 0.30
    c._grid_charged_today = False


def _verkoopkwartieren(plan):
    return [regel for regel in plan if regel["modus"] == "manual (verkopen)"]


def _export_kwh(plan):
    return sum(-regel["net_kwh"] for regel in plan if regel["net_kwh"] < 0)


def _plan(c, hass, blok):
    config_al_gezet = c.config.get("price_sensor_entity")
    assert config_al_gezet, "de prijssensor hoort in de configuratie te staan"
    c.last_cheap_block_start, c.last_cheap_block_end = blok
    return c.get_quarter_plan(datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc))


CONFIG = {
    "price_sensor_entity": "sensor.price",
    "price_attribute": "price_tax_included",
    "battery_total_capacity_sensor_entity": "sensor.capaciteit",
    "manual_discharge_power": 1600,
    "manual_charge_power": 2000,
}

BODEM_KWH = 8.64 * RESERVE_BODEM_FRACTIE
KWARTIER_KWH = 1.6 * 0.25


def test_de_planning_verkoopt_niet_door_de_bodem_heen(make_coordinator, hass):
    """Het geval van 30 op 31 augustus: 's avonds ging 3,65 kWh naar het

    net terwijl het goedkope blok al achter de rug was. Vanaf dat moment
    stond de gesimuleerde reserve op nul en plande de tabel verkoop tot
    de accu leeg was.

    Gemeten op de oude code, met 6,0 kWh beschikbaar en geen zon:

        verkoopkwartieren            15
        export                        5,10 kWh
        laagste stand bij verkoop     0,00 kWh
    """
    c = make_coordinator(CONFIG)
    _plan_situatie(c, hass, beschikbaar_kwh=6.0)

    plan = _plan(
        c,
        hass,
        (
            datetime(2026, 8, 30, 2, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 30, 6, 0, tzinfo=timezone.utc),
        ),
    )

    assert plan, "geen planning opgebouwd"
    verkoop = _verkoopkwartieren(plan)
    assert verkoop, "de planning verkoopt in deze opzet wel degelijk"
    # De toets staat VOOR de verkoop, dus het laatste kwartier mag er
    # nog een ontlading onder duiken - niet meer dan dat.
    assert min(regel["soc_kwh"] for regel in verkoop) >= BODEM_KWH - KWARTIER_KWH


def test_de_planning_houdt_de_bodem_ook_zonder_goedkoop_blok(
    make_coordinator, hass
):
    """Zonder bekend blok gaf de simulatie reserve nul terug. Een bodem

    is geen voorspelling en heeft dat blok niet nodig.
    """
    c = make_coordinator(CONFIG)
    _plan_situatie(c, hass, beschikbaar_kwh=6.0)

    plan = _plan(c, hass, (None, None))

    verkoop = _verkoopkwartieren(plan)
    assert verkoop, "de planning verkoopt in deze opzet wel degelijk"
    assert min(regel["soc_kwh"] for regel in verkoop) >= BODEM_KWH - KWARTIER_KWH


def test_er_blijft_ruimte_voor_arbitrage(make_coordinator, hass):
    """De bodem mag de verkoop niet stilleggen, alleen begrenzen.

    Van de 6,0 kWh hoort ongeveer alles boven de bodem nog verkocht te
    mogen worden.
    """
    c = make_coordinator(CONFIG)
    _plan_situatie(c, hass, beschikbaar_kwh=6.0)

    plan = _plan(c, hass, (None, None))

    assert _export_kwh(plan) > 3.0


def test_de_bodem_beschermt_het_huis_niet_tegen_zichzelf(
    make_coordinator, hass
):
    """Bewust vastgelegd: de reserve houdt VERKOOP tegen, geen

    huishoudverbruik. Een accu die het huis niet meer mag voeden zou
    het net inschakelen op precies het verkeerde moment.
    """
    c = make_coordinator(CONFIG)
    _plan_situatie(c, hass, beschikbaar_kwh=6.0)

    plan = _plan(c, hass, (None, None))

    laagste = min(regel["soc_kwh"] for regel in plan)
    assert laagste < BODEM_KWH
