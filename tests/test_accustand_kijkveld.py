"""De accustand in de kijkvelden loopt achter (v3.92.0).

Gemeld: "Spiegel: Accustand — 43.0 tegenover 17.0 % uit
sensor.solarflow_2400_ac_electric_level".

Gemeten in de export van 31 augustus 06:51:

    accustand_procent            17,0 %   (de sensor)
    last_soc_percent             43,0 %   (het kijkveld)
    kruistoets                   16,3 tegenover 17,0 -> sluit_aan
    last_used_soc_taper_fallback false
    laatste ronde                06:51:12, geslaagd

Het veld `last_soc_percent` wordt op drie plaatsen geschreven en alle
drie zitten in een tak: de dynamische reserve, de terugval op de
SoC-helling, en de kalibratie. Op deze ronde werd geen van de drie
bereikt, dus bleef er een waarde uit de nacht staan.

`_ververs_toestandsvelden` is in v3.29.0 juist gemaakt om dat te
voorkomen — "houdt de kijkvelden bij terwijl de sturing stilligt" —
maar hij wordt alleen in de kalibratietak aangeroepen.

Twee toetsen dus: het veld hoort de sensor te volgen ongeacht welke tak
de ronde neemt, en de onderdrukking uit v3.74.0 hoort de analyse ook
werkelijk te bereiken.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAG0 = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _config(**extra):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "battery_soc_sensor_entity": "sensor.soc",
        "available_energy_sensor_entity": "sensor.beschikbaar",
    }
    config.update(extra)
    return config


def _nu(coordinator, wanneer):
    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: wanneer


def _zet_prijzen(hass, dag0):
    hass.states.set(
        "sensor.price",
        "0.32",
        {"forecast": make_price_forecast(dag0, lambda h, m: 2_500_000)},
    )


# --- 1. het kijkveld hoort de sensor te volgen ------------------------


def test_de_accustand_volgt_de_sensor_ook_zonder_ontlaadtak(
    make_coordinator, hass
):
    """Het geval van 31 augustus: een geslaagde ronde die de

    ontlaadberekening niet raakt, en dan blijft de nachtwaarde staan.
    """
    c = make_coordinator(_config())
    _zet_prijzen(hass, DAG0)
    hass.states.set("sensor.soc", "17.0")
    hass.states.set("sensor.beschikbaar", "0.6048")

    # Een waarde uit de nacht, zoals hij in de export stond.
    c.last_soc_percent = 43.0

    _nu(c, DAG0.replace(hour=6, minute=51))
    asyncio.run(c._async_update_locked())

    assert c.last_soc_percent == 17.0


def test_de_accustand_blijft_kloppen_zonder_prijzen(make_coordinator, hass):
    """De vroegste terugkeer die er is: geen bruikbare prijsreeks.

    Juist daar staan de kijkvelden het langst stil.
    """
    c = make_coordinator(_config())
    hass.states.set("sensor.price", "0.32", {"forecast": []})
    hass.states.set("sensor.soc", "17.0")
    c.last_soc_percent = 43.0

    _nu(c, DAG0.replace(hour=6, minute=51))
    asyncio.run(c._async_update_locked())

    assert c.last_soc_percent == 17.0


def test_een_sensor_zonder_waarde_maakt_er_geen_oud_getal_van(
    make_coordinator, hass
):
    """Liever leeg dan oud — dezelfde regel als in v3.48.0."""
    c = make_coordinator(_config())
    _zet_prijzen(hass, DAG0)
    hass.states.set("sensor.soc", "unavailable")
    c.last_soc_percent = 43.0

    _nu(c, DAG0.replace(hour=6, minute=51))
    asyncio.run(c._async_update_locked())

    assert c.last_soc_percent is None


# --- 2. de onderdrukking hoort de analyse te bereiken ------------------


def _spiegelsituatie(c, intern, sensor_stand, beschikbaar):
    c.last_soc_percent = intern
    c.last_available_kwh = beschikbaar
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.hass.states.set("sensor.soc", str(sensor_stand))
    c.hass.states.set("sensor.beschikbaar", str(beschikbaar))


def test_de_analyse_zwijgt_als_de_kruistoets_aansluit(make_coordinator, hass):
    """v3.74.0 onderdrukt deze melding, maar de analyse liep om die

    onderdrukking heen en meldde hem alsnog.
    """
    c = make_coordinator(_config())
    _spiegelsituatie(c, intern=43.0, sensor_stand=17.0, beschikbaar=0.6048)

    onderwerpen = [p["onderwerp"] for p in c.get_analyse()["punten"]]

    assert "Spiegel: Accustand" not in onderwerpen


def test_een_echte_afwijking_wordt_nog_steeds_gemeld(make_coordinator, hass):
    """De onderdrukking mag de toets niet doof maken: loopt de

    kruistoets zelf uiteen, dan is er wél iets stuk.
    """
    c = make_coordinator(_config())
    # 0,00 kWh bij een stand van 38% — de situatie van 27 augustus.
    _spiegelsituatie(c, intern=38.0, sensor_stand=38.0, beschikbaar=0.0)

    onderwerpen = [p["onderwerp"] for p in c.get_analyse()["punten"]]

    assert "Spiegel: Accustand tegen beschikbare energie" in onderwerpen


def test_de_analyse_meldt_elke_spiegelregel_hoogstens_een_keer(
    make_coordinator, hass
):
    """Twee paden die dezelfde bevinding maken, is de vorm van

    structuurscan 11.
    """
    c = make_coordinator(_config())
    _spiegelsituatie(c, intern=38.0, sensor_stand=38.0, beschikbaar=0.0)

    onderwerpen = [
        p["onderwerp"]
        for p in c.get_analyse()["punten"]
        if p["onderwerp"].startswith("Spiegel: ")
    ]

    assert len(onderwerpen) == len(set(onderwerpen))
