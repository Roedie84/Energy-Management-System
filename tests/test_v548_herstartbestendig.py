"""v5.48: een herstart verandert niets.

De eigenaar herstart Home Assistant vaak. Tellers, kosten, geleerde
modellen en dagsleutels moeten daarna precies zo doorlopen als zonder
herstart. Deze toetsen leggen per bevinding vast dat dat zo is.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import FakeHass

NU = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)


def _herstart(make_coordinator, bron):
    asyncio.run(bron.async_save_persisted_state_now())
    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())
    return verse


# --- 1. elke ronde een opslag, en direct wegschrijven bij het stoppen -----


def test_elke_ronde_plant_een_opslag(make_coordinator, hass):
    c = make_coordinator({})
    asyncio.run(c.async_load_persisted_state())

    async def ronde():
        c.actual_cost_today_eur += 0.25
        c.battery_cumulative_discharged_kwh += 0.4

    c._async_update_locked = ronde
    c._meetlaag_na_besluit = lambda: None

    async def geen_pv_model(_now):
        return None

    c.async_ververs_pv_model = geen_pv_model
    hass._fake_store_backing.clear()
    asyncio.run(c.async_update())

    opgeslagen = hass._fake_store_backing[c._state_store.key]
    assert opgeslagen["actual_cost_today_eur"] == pytest.approx(0.25)
    assert opgeslagen["battery_cumulative_discharged_kwh"] == pytest.approx(0.4)


def test_geen_rondeopslag_voor_de_opslag_gelezen_is(make_coordinator, hass):
    """Anders overschrijft een vroege ronde de opslag met beginwaarden."""
    c = make_coordinator({})

    async def ronde():
        return None

    c._async_update_locked = ronde
    c._meetlaag_na_besluit = lambda: None

    async def geen_pv_model(_now):
        return None

    c.async_ververs_pv_model = geen_pv_model
    hass._fake_store_backing = {}
    asyncio.run(c.async_update())
    assert c._state_store.key not in hass._fake_store_backing


def test_afsluiten_schrijft_toestand_en_meetlaag_direct_weg(coordinator_cls):
    hass = FakeHass(core_state="STARTING")
    c = coordinator_cls(
        hass, {"price_sensor_entity": "sensor.price", "operation_select_entity": "select.op"}
    )

    async def geen_update():
        return None

    c.async_update = geen_update
    asyncio.run(c.async_setup())
    luisteraars = dict(hass.bus.listeners)
    assert "homeassistant_stop" in luisteraars

    bewaard = []

    class Laag:
        async def bewaar_nu(self):
            bewaard.append(True)

    c._meetlaag = Laag()
    c.actual_cost_today_eur = 3.21
    asyncio.run(luisteraars["homeassistant_stop"](None))

    assert hass._fake_store_backing[c._state_store.key]["actual_cost_today_eur"] == 3.21
    assert bewaard == [True]
    assert c._unsub_afsluiten is None


def test_herladen_zegt_de_afsluitluisteraar_op(make_coordinator):
    c = make_coordinator({})
    opgezegd = []
    c._unsub_afsluiten = lambda: opgezegd.append(True)
    asyncio.run(c.async_unload())
    assert opgezegd == [True]
    assert c._unsub_afsluiten is None


def test_oplopende_teller_daalt_niet_door_een_oudere_opslag(make_coordinator):
    """Opslag van voor een stroomstoring, sensor al verder: de hoogste
    stand blijft, anders ziet de recorder een meterwissel."""
    bron = make_coordinator({})
    bron.total_discharge_value_eur = 10.0
    bron.total_charge_cost_eur = 4.0
    bron.battery_cumulative_discharged_kwh = 800.0
    verse = _herstart(make_coordinator, bron)
    # Het sensorherstel: de laatste stand in de recorder was hoger.
    verse.total_discharge_value_eur = 10.5
    verse.total_charge_cost_eur = 4.2
    verse.battery_cumulative_discharged_kwh = 801.0
    verse.herstel_de_opslag_na_de_sensoren()
    assert verse.total_discharge_value_eur == 10.5
    assert verse.total_charge_cost_eur == 4.2
    assert verse.battery_cumulative_discharged_kwh == 801.0


def test_store_wint_laat_een_oplopende_teller_niet_dalen(make_coordinator):
    from custom_components.energy_management_system.sensor import DischargeValueSensor

    bron = make_coordinator({})
    bron.total_discharge_value_eur = 10.0
    verse = _herstart(make_coordinator, bron)

    class Toestand:
        state = "10.75"
        attributes = {}

    sensor = DischargeValueSensor(verse, "x")

    async def laatste():
        return Toestand()

    sensor.async_get_last_state = laatste
    asyncio.run(sensor.async_added_to_hass())
    assert verse.total_discharge_value_eur == 10.75


# --- 2. de kopie voor na de sensoren is de toestand NA het laden ---------


def test_opschoning_bij_het_laden_blijft_na_de_sensoren(make_coordinator, hass):
    """Een opslag zonder methodeversie wist de balansreeks. De kopie werd
    vóór het wissen genomen, dus kwam de reeks na de sensoren terug."""
    c = make_coordinator({})
    hass._fake_store_backing[c._state_store.key] = {
        "energy_balance_error_history": [10.0, 20.0, 30.0],
    }
    asyncio.run(c.async_load_persisted_state())
    assert c.energy_balance_error_history == []
    c.herstel_de_opslag_na_de_sensoren()
    assert c.energy_balance_error_history == []


def test_oude_opslag_zonder_nieuwe_velden_laadt_en_laat_het_vangnet(
    make_coordinator, hass
):
    """Achterwaarts verenigbaar: een opslag van v5.47 kent de nieuwe
    velden niet. Ze houden hun beginwaarde, en wat een sensor herstelde
    wordt niet met een beginwaarde overschreven."""
    c = make_coordinator({})
    hass._fake_store_backing[c._state_store.key] = {
        "actual_cost_today_eur": 1.5,
        "_counterfactual_day_key": "2026-10-08",
    }
    asyncio.run(c.async_load_persisted_state())
    assert c.actual_cost_today_eur == 1.5
    assert c._capacity_trend_day_key is None
    assert c._veroudering_vandaag == {}
    assert c._grid_charged_today is False
    c._veroudering_vandaag = {"uren_boven_hoge_stand": 2.0}  # "sensor"
    c.herstel_de_opslag_na_de_sensoren()
    assert c._veroudering_vandaag == {"uren_boven_hoge_stand": 2.0}
    assert c.actual_cost_today_eur == 1.5


def test_nieuwe_datumvelden_gaan_als_iso_tekst_de_opslag_in(make_coordinator):
    c = make_coordinator({})
    c._cusum_check_date = date(2026, 10, 8)
    c._capacity_trend_day_key = date(2026, 10, 8)
    c._grid_charged_date = date(2026, 10, 8)
    data = c._collect_persisted_state()
    assert data["_cusum_check_date"] == "2026-10-08"
    assert data["_capacity_trend_day_key"] == "2026-10-08"
    assert data["_grid_charged_date"] == "2026-10-08"


# --- 3-8, 10: dagsleutels en dagtellers -----------------------------------


def test_sluipverbruik_dagvloer_overleeft_een_herstart(make_coordinator):
    """Zonder bewaren begon de dagvloer na een herstart opnieuw en werd de
    dag afgesloten met alleen het deel na de herstart."""
    from custom_components.energy_management_system.const import (
        SLUIPVERBRUIK_METHODE_VERSIE,
    )

    bron = make_coordinator({})
    bron.sluipverbruik_methode_versie = SLUIPVERBRUIK_METHODE_VERSIE
    bron._cusum_check_date = NU.date()
    bron._today_min_load_kw = 0.11
    verse = _herstart(make_coordinator, bron)
    assert verse._cusum_check_date == NU.date()
    assert verse._today_min_load_kw == 0.11


def _proefstand_klaar(c, capaciteit=8.64):
    c._read_sensor_float = lambda *_a, **_k: capaciteit
    c._get_forecast_entries = lambda: []
    c._dagtype_verschil_kwh = lambda _dag: None
    c.get_wear_cost_overview = lambda: {
        "beschikbaar": True,
        "slijtage_ct_per_kwh": 5.0,
    }


def test_capaciteitstrend_en_slijtage_tellen_een_herstart_niet(make_coordinator):
    bron = make_coordinator({})
    _proefstand_klaar(bron)
    bron.battery_cumulative_discharged_kwh = 800.0
    bron._update_proefstand(NU)
    assert len(bron.capacity_trend_history) == 1
    assert bron._proefstand_doorzet_bij_dagstart == 800.0

    bron.battery_cumulative_discharged_kwh = 803.0
    verse = _herstart(make_coordinator, bron)
    _proefstand_klaar(verse)
    verse._update_proefstand(NU + timedelta(hours=1))
    # Geen tweede meting voor dezelfde dag.
    assert len(verse.capacity_trend_history) == 1

    verse.battery_cumulative_discharged_kwh = 805.0
    verse._update_proefstand(NU + timedelta(days=1))
    boeking = verse.proefstand_ledger[-1]
    # Alleen de doorzet van die dag, niet de levensdoorzet.
    assert boeking["doorzet_kwh"] == 5.0
    assert boeking["datum"] == NU.date().isoformat()


def test_zonder_beginstand_geen_slijtageboeking(make_coordinator):
    c = make_coordinator({})
    _proefstand_klaar(c)
    c.battery_cumulative_discharged_kwh = 800.0
    c._proefstand_doorzet_bij_dagstart = None
    c._boek_proefstand_dag(NU.date())
    assert all("slijtage_eur" not in b for b in c.proefstand_ledger)
    assert c._proefstand_doorzet_bij_dagstart == 800.0


def test_capaciteitstrend_ook_geen_dubbele_dag_uit_een_oude_opslag(make_coordinator):
    """Een opslag van v5.47 kent de dagsleutel niet; de reeks wel."""
    c = make_coordinator({})
    _proefstand_klaar(c)
    c.capacity_trend_history = [
        {"datum": NU.date().isoformat(), "capaciteit_kwh": 8.64, "doorzet_kwh": 1.0}
    ]
    c._update_proefstand(NU)
    assert len(c.capacity_trend_history) == 1


def test_prijsvorm_dagsleutel_overleeft_een_herstart(make_coordinator):
    bron = make_coordinator({})
    bron._price_shape_day_key = NU.date()
    verse = _herstart(make_coordinator, bron)
    assert verse._price_shape_day_key == NU.date()


def test_dagrapport_telt_door_na_een_herstart(make_coordinator):
    bron = make_coordinator({})
    bron._update_daily_report(NU)
    bron._update_daily_report(NU + timedelta(minutes=5))
    assert bron._daily_report_counters["ticks"] == 2
    verse = _herstart(make_coordinator, bron)
    assert verse._daily_report_day_key == NU.date()
    verse._update_daily_report(NU + timedelta(minutes=10))
    assert verse._daily_report_counters["ticks"] == 3
    assert verse.daily_report_history == []


def test_dagrapport_met_sleutel_maar_zonder_tellers_valt_niet_om(make_coordinator):
    c = make_coordinator({})
    c._daily_report_day_key = NU.date()
    c._daily_report_counters = {}
    c._update_daily_report(NU)
    assert c._daily_report_counters["ticks"] == 1


def test_netladen_vandaag_overleeft_een_herstart(make_coordinator):
    bron = make_coordinator({})
    bron._grid_charged_today = True
    bron._grid_charged_date = NU.date()
    verse = _herstart(make_coordinator, bron)
    assert verse._grid_charged_today is True
    assert verse._grid_charged_date == NU.date()


def test_verouderingsdag_overleeft_een_herstart(make_coordinator):
    bron = make_coordinator({})
    bron._veroudering_day_key = NU.date()
    bron._veroudering_vandaag = {"uren_boven_hoge_stand": 3.25}
    verse = _herstart(make_coordinator, bron)
    assert verse._veroudering_day_key == NU.date()
    assert verse._veroudering_vandaag == {"uren_boven_hoge_stand": 3.25}


def test_laagste_stand_en_kostendag_overleven_een_herstart(make_coordinator):
    bron = make_coordinator({})
    bron.laagste_soc_vandaag_procent = 17.0
    bron._daily_cost_day_key = NU.date()
    verse = _herstart(make_coordinator, bron)
    assert verse.laagste_soc_vandaag_procent == 17.0
    assert verse._daily_cost_day_key == NU.date()


# --- 9. de meetlaag ---------------------------------------------------------


def test_meetlaag_bewaar_nu_schrijft_alles_weg(make_coordinator, hass):
    from custom_components.energy_management_system.meetlaag import Meetlaag

    c = make_coordinator({})
    geschreven = {}

    class Opslag:
        def __init__(self, sleutel):
            self.sleutel = sleutel

        async def async_save(self, inhoud):
            geschreven[self.sleutel] = inhoud

    laag = Meetlaag(c, opslag_factory=Opslag)
    laag._laden_klaar = True
    laag.log.voeg_toe("evaluatie", NU, {"a": 1})
    asyncio.run(laag.bewaar_nu())
    assert geschreven, "niets weggeschreven"
    # Daarna is er niets meer te bewaren.
    geschreven.clear()
    asyncio.run(laag.bewaar_nu())
    assert geschreven == {}


def test_meetlaag_bewaar_nu_wacht_op_het_terugladen(make_coordinator):
    from custom_components.energy_management_system.meetlaag import Meetlaag

    c = make_coordinator({})
    geschreven = []

    class Opslag:
        def __init__(self, sleutel):
            pass

        async def async_save(self, inhoud):
            geschreven.append(inhoud)

    laag = Meetlaag(c, opslag_factory=Opslag)
    laag._laden_klaar = False
    laag.log.voeg_toe("evaluatie", NU, {"a": 1})
    asyncio.run(laag.bewaar_nu())
    assert geschreven == []


# --- 11. de dienst confirm_water_source -------------------------------------


def test_dienst_waterbron_bevestigen_werkt(make_coordinator, hass):
    import custom_components.energy_management_system as pkg
    from custom_components.energy_management_system.const import DOMAIN

    c = make_coordinator({})
    bevestigd = []
    c.confirm_water_source = lambda bron, sessie=None: bevestigd.append(bron)
    hass.data = {DOMAIN: {"entry": c, "entry_solar_tracker": object()}}
    pkg._async_register_nilm_services(hass)
    handler = hass.services._registered[(DOMAIN, "confirm_water_source")]

    class Aanroep:
        data = {"bron": "wc"}

    asyncio.run(handler(Aanroep()))
    assert bevestigd == ["wc"]
