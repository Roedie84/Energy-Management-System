"""v5.49: twee rapportagefouten, alleen weergave.

1. L-EMS-008: de watertrend zette vandaag-tot-nu tegen hele dagen ("-84,5%"
   midden op de dag). Nu gelijk met gelijk: tot dezelfde kloktijd.
2. De cockpit sprong op "balans wijkt af" bij snelle zonwisselingen, en
   "balans" verdween uit de regel als de controle even niet beschikbaar was.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from homeassistant.util import dt as dt_util

from custom_components.energy_management_system.const import (
    ENERGIEBALANS_AFWIJKING_MIN_S,
    ENERGIEBALANS_OORDEEL_VASTHOUDEN_S,
    PERSISTED_FIELDS,
)


def _lokaal(dag, uur, minuut=0):
    return datetime(2026, 10, dag, uur, minuut, tzinfo=timezone.utc)


def _c(make_coordinator):
    return make_coordinator(
        {"water_daily_total_sensor_entity": "sensor.water_verbruik_vandaag"}
    )


def _dag(hass, liter):
    hass.states.set(
        "sensor.water_verbruik_vandaag", str(liter), {"unit_of_measurement": "L"}
    )


def _profiel(datum, ochtend=100.0, avond=100.0):
    """Ochtenddouche 07-08 uur, avondwas 19-20 uur, verder niets."""
    uren = {}
    for h in range(24):
        stand = 0.0
        if h >= 7:
            stand += ochtend
        if h >= 19:
            stand += avond
        uren[str(h)] = stand
    return {"datum": datum, "uren": uren, "totaal": ochtend + avond}


# --- 1. de watertrend ------------------------------------------------------


def test_het_gemelde_geval_geen_min_85_procent_midden_op_de_dag(make_coordinator):
    """Om 12:00 de ochtenddouche gehad, net als altijd: trend 0, niet -50%
    (en zeker geen -85%)."""
    c = _c(make_coordinator)
    c.water_daily_history = [200.0, 200.0, 200.0]
    c.water_dagprofielen = [_profiel(f"2026-10-0{d}") for d in (1, 2, 3)]
    c.water_daily_total_l = 100.0

    t = c.water_trend(_lokaal(8, 12))

    assert t["methode"] == "zelfde_tijdstip"
    assert t["referentie_liter"] == 100.0
    assert t["procent"] == 0.0


def test_binnen_het_uur_lineair(make_coordinator):
    c = _c(make_coordinator)
    c.water_dagprofielen = [_profiel(f"2026-10-0{d}") for d in (1, 2, 3)]
    c.water_daily_total_l = 50.0

    t = c.water_trend(_lokaal(8, 7, 30))  # halverwege de douche

    assert t["referentie_liter"] == 50.0
    assert t["procent"] == 0.0


def test_mediaan_over_de_dagen_en_meer_verbruik_is_positief(make_coordinator):
    c = _c(make_coordinator)
    c.water_dagprofielen = [
        _profiel("2026-10-01", ochtend=80.0),
        _profiel("2026-10-02", ochtend=100.0),
        _profiel("2026-10-03", ochtend=300.0),
    ]
    c.water_daily_total_l = 150.0

    t = c.water_trend(_lokaal(8, 10))

    assert t["referentie_liter"] == 100.0
    assert t["procent"] == 50.0


def test_dag_met_gat_telt_niet_mee_en_vandaag_ook_niet(make_coordinator):
    c = _c(make_coordinator)
    gat = _profiel("2026-10-04")
    del gat["uren"]["9"]  # HA stond uit
    c.water_dagprofielen = [
        _profiel("2026-10-01"),
        _profiel("2026-10-02"),
        gat,
        _profiel("2026-10-08", ochtend=999.0),  # vandaag zelf
    ]
    c.water_daily_total_l = 100.0

    t = c.water_trend(_lokaal(8, 10))

    # twee bruikbare dagen: te weinig voor een profieltrend, en voor 20:00
    # geen geschaalde trend.
    assert t["procent"] is None
    assert t["reden"]


def test_zonder_profielen_overdag_geen_trend(make_coordinator):
    c = _c(make_coordinator)
    c.water_daily_history = [200.0] * 7
    c.water_daily_total_l = 30.0

    t = c.water_trend(_lokaal(8, 9))

    assert t["procent"] is None
    assert t["methode"] is None


def test_zonder_profielen_na_20_uur_geschaald(make_coordinator):
    c = _c(make_coordinator)
    c.water_daily_history = [240.0] * 7
    c.water_daily_total_l = 210.0

    t = c.water_trend(_lokaal(8, 21))

    assert t["methode"] == "geschaald_hele_dag"
    assert t["referentie_liter"] == 210.0  # 240 x 21/24
    assert t["procent"] == 0.0


def test_het_profiel_wordt_per_uur_opgebouwd_en_gearchiveerd(make_coordinator, hass):
    c = _c(make_coordinator)
    _dag(hass, 40)
    c._update_water_tracking(_lokaal(7, 7, 10))
    _dag(hass, 95)
    c._update_water_tracking(_lokaal(7, 7, 55))
    _dag(hass, 180)
    c._update_water_tracking(_lokaal(7, 23, 55))

    assert c.water_dagprofiel_vandaag == {
        "datum": "2026-10-07",
        "uren": {"7": 95.0, "23": 180.0},
    }

    # Net na middernacht nog de oude stand: niet als verbruik van vandaag.
    c._update_water_tracking(_lokaal(8, 0, 0))
    assert c.water_dagprofiel_vandaag == {"datum": "2026-10-08", "uren": {}}
    assert c.water_dagprofielen == [
        {"datum": "2026-10-07", "uren": {"7": 95.0, "23": 180.0}, "totaal": 180.0}
    ]
    _dag(hass, 2)
    c._update_water_tracking(_lokaal(8, 0, 5))
    assert c.water_dagprofiel_vandaag["uren"] == {"0": 2.0}


def test_het_archief_is_begrensd(make_coordinator, hass):
    c = _c(make_coordinator)
    for d in range(1, 20):
        _dag(hass, 10 + d)
        c._update_water_tracking(datetime(2026, 9, d, 12, tzinfo=timezone.utc))
    assert len(c.water_dagprofielen) == 7
    assert c.water_dagprofielen[-1]["datum"] == "2026-09-18"


def test_profielen_worden_bewaard_en_overleven_een_herstart(make_coordinator, hass):
    assert PERSISTED_FIELDS["water_dagprofiel_vandaag"]["type"] == "plain"
    assert PERSISTED_FIELDS["water_dagprofielen"]["type"] == "plain"
    c = _c(make_coordinator)
    c.water_dagprofielen = [_profiel("2026-10-01")]
    c.water_dagprofiel_vandaag = {"datum": "2026-10-08", "uren": {"7": 12.0}}
    asyncio.run(c.async_save_persisted_state_now())
    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())

    assert verse.water_dagprofielen == [_profiel("2026-10-01")]
    assert verse.water_dagprofiel_vandaag == {"datum": "2026-10-08", "uren": {"7": 12.0}}


def test_oude_opslag_zonder_profielen_laadt(make_coordinator, hass):
    c = make_coordinator({})
    hass._fake_store_backing[c._state_store.key] = {"water_daily_history": [150.0]}
    asyncio.run(c.async_load_persisted_state())

    assert c.water_daily_history == [150.0]
    assert c.water_dagprofielen is None
    assert c.water_dagprofiel_vandaag is None


def test_geen_gedeelde_lijst_tussen_instanties(make_coordinator, hass):
    a = _c(make_coordinator)
    b = _c(make_coordinator)
    _dag(hass, 10)
    a._update_water_tracking(_lokaal(7, 12))
    a._update_water_tracking(_lokaal(8, 12))

    assert a.water_dagprofielen
    assert b.water_dagprofielen is None
    assert b.water_dagprofiel_vandaag is None


def test_sensor_toont_methode_en_referentie(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import WaterUsageSensor

    c = _c(make_coordinator)
    c.water_daily_total_l = 10.0
    a = WaterUsageSensor(c, "x").extra_state_attributes

    assert {"trend_procent", "trend_methode", "trend_referentie_liter", "trend_toelichting"} <= set(a)


# --- 2. het balansoordeel van de cockpit -----------------------------------

AF = {"beschikbaar": True, "alles_klopt": False}
GOED = {"beschikbaar": True, "alles_klopt": True}
WEG = {"beschikbaar": False, "reden": "x"}


def test_een_korte_afwijking_meldt_niets(make_coordinator):
    c = make_coordinator({})
    t0 = dt_util.now()
    assert c._balans_oordeel(GOED, t0) is True
    # twee rondes afwijking bij een zonwisseling, dan weer goed
    assert c._balans_oordeel(AF, t0 + timedelta(minutes=1)) is True
    assert c._balans_oordeel(AF, t0 + timedelta(minutes=2)) is True
    assert c._balans_oordeel(GOED, t0 + timedelta(minutes=3)) is True
    # de teller begint opnieuw
    assert c._balans_afwijking_rondes == 0


def test_een_aanhoudende_afwijking_wordt_wel_gemeld(make_coordinator):
    c = make_coordinator({})
    t0 = dt_util.now()
    c._balans_oordeel(GOED, t0)
    stappen = [c._balans_oordeel(AF, t0 + timedelta(minutes=m)) for m in (1, 2, 3, 4)]

    # rondes 1-3 duren samen 2 minuten: nog niet; ronde 4 na 3 minuten wel.
    assert stappen == [True, True, True, False]
    assert ENERGIEBALANS_AFWIJKING_MIN_S == 180


def test_veel_rondes_in_korte_tijd_is_nog_geen_afwijking(make_coordinator):
    """Een korte ronde-instelling (5 s) mag de drie minuten niet omzeilen."""
    c = make_coordinator({})
    t0 = dt_util.now()
    uit = [c._balans_oordeel(AF, t0 + timedelta(seconds=5 * i)) for i in range(10)]

    assert set(uit) == {None}


def test_herstel_is_direct(make_coordinator):
    c = make_coordinator({})
    t0 = dt_util.now()
    for m in range(5):
        c._balans_oordeel(AF, t0 + timedelta(minutes=m))
    assert c._balans_stabiel_oordeel is False
    assert c._balans_oordeel(GOED, t0 + timedelta(minutes=5)) is True


def test_even_niet_beschikbaar_houdt_het_laatste_oordeel_vast(make_coordinator):
    c = make_coordinator({})
    t0 = dt_util.now()
    c._balans_oordeel(GOED, t0)

    assert c._balans_oordeel(WEG, t0 + timedelta(minutes=2)) is True
    assert c._balans_oordeel(
        WEG, t0 + timedelta(seconds=ENERGIEBALANS_OORDEEL_VASTHOUDEN_S)
    ) is True
    assert c._balans_oordeel(
        WEG, t0 + timedelta(seconds=ENERGIEBALANS_OORDEEL_VASTHOUDEN_S + 1)
    ) is None


def test_de_cockpitregel_houdt_balans_vast(make_coordinator, hass):
    c = make_coordinator({})
    c.last_successful_update = dt_util.now()
    c.internal_failures = {}
    c.get_configuratiecontrole = lambda: {
        "entiteiten": [{"oordeel": "in_orde", "instelling": "price_sensor_entity"}]
    }
    c.get_diagnostic_summary = lambda: {"aandachtspunten": []}
    c.get_energiebalans_controle = lambda: GOED
    assert c._ems_status() == ("GOED", "koppelingen 1/1 · balans ✓")

    c.get_energiebalans_controle = lambda: WEG
    assert c._ems_status() == ("GOED", "koppelingen 1/1 · balans ✓")

    c.get_energiebalans_controle = lambda: AF
    assert c._ems_status() == ("GOED", "koppelingen 1/1 · balans ✓")


def test_diagnostiek_toont_het_oordeel(make_coordinator):
    c = make_coordinator({})
    c._balans_oordeel(AF, dt_util.now())
    o = c.get_energiebalans_oordeel()

    assert o["afwijking_rondes"] == 1
    assert o["oordeel"] is None
    assert o["afwijking_sinds"]


def test_het_oordeel_wordt_niet_bewaard(make_coordinator):
    """Na een herstart opnieuw bepalen; geen oud oordeel."""
    for veld in (
        "_balans_afwijking_sinds",
        "_balans_afwijking_rondes",
        "_balans_stabiel_oordeel",
        "_balans_laatst_geldig",
    ):
        assert veld not in PERSISTED_FIELDS
