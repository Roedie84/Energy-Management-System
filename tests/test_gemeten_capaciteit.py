"""De gemeten capaciteit is nooit gemeten (v3.92.5).

Gemeten in de export van 31 augustus 10:40, 153 dagen na installatie:

    nominaal_kwh    8,64
    gemeten_kwh     null
    dagen_gemeten   153

De toelichting belooft dat de reserve met de gemeten capaciteit rekent
"zodra die er is - na 30 dagen". Vijf keer dertig dagen later staat er
nog steeds niets.

Twee oorzaken, en de tweede is de ernstige.

1. `gemeten_capaciteit_kwh` leest `r.get("bruikbaar_kwh")` uit
   `capacity_trend_history`. De schrijver legt `datum`,
   `capaciteit_kwh` en `doorzet_kwh` vast. De sleutel `bruikbaar_kwh`
   is er nooit geweest, dus de lijst met waarden is altijd leeg en de
   functie geeft altijd None terug. Dood sinds v3.5.0.

2. Wat de schrijver vastlegt is de NOMINALE sensor. De sleutel
   repareren zou `gemeten_kwh` op 8,64 zetten en de degradatie op 0% -
   het zou eruitzien alsof er gemeten wordt terwijl er niets gemeten
   is. Dat is erger dan null.

En `available_kwh` kan die meting ook niet leveren. Vier momenten uit
vier exports, op vier decimalen exact:

    SoC 17 %  ->  0,6048 kWh      (17-10)/100 * 8,64 = 0,6048
    SoC 19 %  ->  0,7776 kWh      (19-10)/100 * 8,64 = 0,7776
    SoC 21 %  ->  0,9504 kWh      (21-10)/100 * 8,64 = 0,9504

De sensor is geen meting maar een rekensom op de laadstand en de
nominale capaciteit, met een vaste bodem van 10%. Er kan per definitie
geen slijtage uit blijken.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 8, 31, 10, 40, tzinfo=timezone.utc)


def _met_capaciteitssensor(make_coordinator, hass):
    hass.states.set("sensor.capaciteit", "8.64")
    return make_coordinator(
        {"battery_total_capacity_sensor_entity": "sensor.capaciteit"}
    )


def _reeks(dagen, capaciteit=8.64):
    """Zoals de schrijver hem werkelijk vastlegt."""
    return [
        {
            "datum": f"2026-0{3 + i // 30}-{1 + i % 28:02d}",
            "capaciteit_kwh": capaciteit,
            "doorzet_kwh": 1.1 * i,
        }
        for i in range(dagen)
    ]


# --- 1. de sleutel die nooit bestond ----------------------------------


def test_de_reeks_wordt_gelezen_met_de_sleutel_die_erin_staat(
    make_coordinator, hass
):
    """153 dagen data en een lezer die naar `bruikbaar_kwh` zoekt."""
    c = make_coordinator({})
    c.capacity_trend_history = _reeks(153)

    geschreven = set(c.capacity_trend_history[0])
    assert "capaciteit_kwh" in geschreven
    assert "bruikbaar_kwh" not in geschreven


def test_de_uitkomst_zegt_wat_er_aan_de_hand_is(make_coordinator, hass):
    """Null zonder uitleg is 153 dagen lang voor "nog even wachten"

    aangezien. De kaart hoort te zeggen dat er niets gemeten wordt.
    """
    c = _met_capaciteitssensor(make_coordinator, hass)
    c.capacity_trend_history = _reeks(153)

    overzicht = c.get_capacity_overview()

    assert overzicht["gemeten_kwh"] is None
    assert overzicht["meet_niets_reden"]
    assert "nominale" in overzicht["meet_niets_reden"].lower()


def test_er_wordt_geen_degradatie_van_nul_gemeld(make_coordinator, hass):
    """De verleiding was de sleutel te repareren. Dan komt er 8,64 uit

    tegenover een nominale 8,64, en meldt de kaart 0% degradatie alsof
    dat een uitkomst is.
    """
    c = _met_capaciteitssensor(make_coordinator, hass)
    c.capacity_trend_history = _reeks(153)

    assert c.get_capacity_overview()["degradatie_procent"] is None


def test_een_echte_meting_wordt_wel_gebruikt(make_coordinator, hass):
    """Komt er ooit een reeks met een afwijkende capaciteit, dan telt

    die gewoon mee. De rem zit op verzonnen metingen, niet op metingen.
    """
    c = _met_capaciteitssensor(make_coordinator, hass)
    c.capacity_trend_history = _reeks(153, capaciteit=7.90)

    overzicht = c.get_capacity_overview()

    assert overzicht["gemeten_kwh"] == pytest.approx(7.90, abs=0.01)
    assert overzicht["degradatie_procent"] == pytest.approx(8.6, abs=0.5)


# --- 2. het kijkveld voor de beschikbare energie ----------------------


def test_de_beschikbare_energie_volgt_ook_elke_ronde(make_coordinator, hass):
    """Zelfde vorm als `last_soc_percent` in v3.92.0, en over het hoofd

    gezien: `last_available_kwh` wordt alleen in de ontlaadtak gezet.

    In de exports van 10:27 en 10:40 stond hij op null terwijl de sensor
    gewoon 0,9504 gaf - de ronde nam een andere tak.
    """
    from conftest import make_price_forecast

    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "battery_soc_sensor_entity": "sensor.soc",
        "available_energy_sensor_entity": "sensor.beschikbaar",
    }
    c = make_coordinator(config)
    hass.states.set(
        "sensor.price",
        "0.32",
        {"forecast": make_price_forecast(NU.replace(hour=0), lambda h, m: 2_500_000)},
    )
    hass.states.set("sensor.soc", "21.0")
    hass.states.set("sensor.beschikbaar", "0.9504")
    c.last_available_kwh = None

    import asyncio

    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: NU
    asyncio.run(c._async_update_locked())

    assert c.last_available_kwh == pytest.approx(0.9504, abs=0.001)
