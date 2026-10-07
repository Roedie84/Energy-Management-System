"""Tekort door capaciteit tegenover tekort door planning (v5.40).

Gemeld: de cockpit ging naar LET OP bij een tekortnacht, ook als de sturing
klopte - de accu was vol en het huis vroeg simpelweg meer dan erin past.
Capaciteit is informatief; planning (er was ruimte of kans) blijft een
aandachtspunt.
"""
from datetime import datetime, timedelta, timezone

DAG = datetime(2026, 10, 6, tzinfo=timezone.utc)


def _c(make_coordinator, hass, soc="100", net="0", accu="0"):
    c = make_coordinator(
        {
            "battery_soc_sensor_entity": "sensor.soc",
            "consumption_power_sensor_entity": "sensor.p1",
            "battery_power_sensor_entity": "sensor.accu",
        }
    )
    hass.states.set("sensor.soc", soc)
    hass.states.set("sensor.p1", net)
    hass.states.set("sensor.accu", accu)
    return c


def _record(datum, soort, tekort=1.4):
    return {
        "date": datum,
        "shortfall": soort is not None,
        "tekortnacht_kwh": tekort if soort else 0.0,
        "tekort_soort": soort,
        "excess": False,
    }


def test_vol_en_niets_verkocht_is_capaciteit(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="100")
    c._volg_vol_en_verkoop(DAG.replace(hour=13))
    hass.states.set("sensor.soc", "40")
    c._volg_vol_en_verkoop(DAG.replace(hour=20))

    assert c._vol_voor_nacht is True
    assert c._tekort_soort(1.4, c._vol_voor_nacht, c._verkocht_na_vol_kwh) == "capaciteit"


def test_vol_maar_daarna_verkocht_is_planning(make_coordinator, hass):
    """2 oktober: om 13:00 vol, en in vier uur naar 23% - verkocht."""
    c = _c(make_coordinator, hass, soc="100")
    c._volg_vol_en_verkoop(DAG.replace(hour=13))
    hass.states.set("sensor.soc", "80")
    hass.states.set("sensor.p1", "-1500")
    hass.states.set("sensor.accu", "1600")
    moment = DAG.replace(hour=17)
    for _ in range(12):  # een uur verkopen, per vijf minuten
        moment += timedelta(minutes=5)
        c._volg_vol_en_verkoop(moment)

    assert c._verkocht_na_vol_kwh > 1.0
    assert c._tekort_soort(1.4, c._vol_voor_nacht, c._verkocht_na_vol_kwh) == "planning"


def test_niet_vol_geweest_is_planning(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="70")
    c._volg_vol_en_verkoop(DAG.replace(hour=13))

    assert c._tekort_soort(1.4, c._vol_voor_nacht, 0.0) == "planning"


def test_geen_tekort_geen_soort(make_coordinator, hass):
    c = _c(make_coordinator, hass)

    assert c._tekort_soort(0.2, True, 0.0) is None
    assert c._tekort_soort(None, True, 0.0) is None


def test_meer_nodig_dan_erin_past_is_capaciteit(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="70")
    c.bruikbaar_tussen_grenzen_kwh = lambda: 7.8

    assert c._tekort_soort(1.0, False, 0.0, nodig_kwh=9.0) == "capaciteit"
    assert c._tekort_soort(1.0, False, 0.0, nodig_kwh=6.0) == "planning"


def test_de_nacht_wordt_om_negen_uur_ingedeeld_en_komt_in_het_dagrecord(
    make_coordinator, hass
):
    c = _c(make_coordinator, hass, soc="100")
    c._volg_vol_en_verkoop(DAG.replace(hour=14))
    hass.states.set("sensor.soc", "10")
    c._volg_vol_en_verkoop(DAG.replace(hour=23))
    # De ochtend sluit de nacht af met 1,4 kWh tekort.
    c._tekortnacht_vandaag_kwh = 1.4
    volgende = DAG + timedelta(days=1)
    c._volg_vol_en_verkoop(volgende.replace(hour=9, minute=1))

    assert c._tekort_soort_vandaag == "capaciteit"
    assert c._vol_voor_nacht is False, "nieuw venster voor de volgende nacht"

    c._shortfall_check_date = volgende.date()
    c._update_shortfall_detection(volgende + timedelta(days=1), "default_smart")

    assert c.reserve_daily_records[-1]["tekort_soort"] == "capaciteit"
    assert c._tekort_soort_vandaag is None


def test_een_herstart_overdag_deelt_niet_opnieuw_in(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="50")
    c._tekortnacht_vandaag_kwh = 1.4
    c._volg_vol_en_verkoop(DAG.replace(hour=9, minute=5))
    eerste = c._tekort_soort_vandaag
    c._vol_voor_nacht = True
    c._volg_vol_en_verkoop(DAG.replace(hour=12))

    assert c._tekort_soort_vandaag == eerste == "planning"


def test_capaciteit_is_geen_aandachtspunt(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.reserve_daily_records = [
        _record("2026-10-01", "capaciteit"),
        _record("2026-10-02", None),
        _record("2026-10-03", "capaciteit"),
    ]

    samenvatting = c.get_diagnostic_summary()

    assert not any("tekort-dag" in p for p in samenvatting["aandachtspunten"])
    assert any("door capaciteit" in p for p in samenvatting["informatief"])


def test_planning_blijft_een_aandachtspunt(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.reserve_daily_records = [
        _record("2026-10-01", "capaciteit"),
        _record("2026-10-02", "planning"),
        # van voor v5.40: geen soort, telt als planning
        {"date": "2026-10-03", "shortfall": True, "excess": False},
    ]

    samenvatting = c.get_diagnostic_summary()

    assert "2 onverwachte tekort-dag(en) in de laatste 3 dagen." in samenvatting[
        "aandachtspunten"
    ]
    soorten = c.get_tekortsoorten()
    assert soorten["tekort_soort_per_nacht"] == ["capaciteit", "planning", "onbekend"]
    assert soorten["tekortnachten_capaciteit"] == 1
    assert soorten["tekortnachten_planning"] == 2


def test_verwacht_capaciteitstekort_is_informatief(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.last_reserve_margin_breakdown = {"needed_kwh_before_margin": 6.11}
    c.beschikbare_energie_kwh = lambda: 5.0
    c._vol_voor_nacht = True
    c._verkocht_na_vol_kwh = 0.0

    verwacht = c.verwacht_tekort()
    samenvatting = c.get_diagnostic_summary()

    assert verwacht["tekort_soort"] == "capaciteit"
    assert verwacht["tekort_kwh"] == 1.11
    assert any("Verwacht tekort" in p for p in samenvatting["informatief"])
    assert "capaciteitstekort" in c._tekort_soort_zin()


def test_verwacht_planningstekort(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="60")
    c.last_reserve_margin_breakdown = {"needed_kwh_before_margin": 6.11}
    c.beschikbare_energie_kwh = lambda: 5.0
    c._vol_voor_nacht = False

    assert c.verwacht_tekort()["tekort_soort"] == "planning"
    assert c._tekort_soort_zin() == ""


def test_de_sensoren_tonen_de_soort(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        MonteCarloAdvisorySensor,
        ReserveShortfallSensor,
    )

    c = _c(make_coordinator, hass)
    c.reserve_daily_records = [_record("2026-10-01", "capaciteit")]

    tekort = ReserveShortfallSensor(c, "x").extra_state_attributes
    mc = MonteCarloAdvisorySensor(c, "x").extra_state_attributes

    assert tekort["tekortnachten_capaciteit"] == 1
    assert tekort["tekort_soort_per_nacht"] == ["capaciteit"]
    assert mc["tekort_soort_per_nacht"] == ["capaciteit"]
    assert "verwacht_tekort" in mc


def test_de_velden_overleven_een_herstart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    for veld in (
        "_vol_voor_nacht",
        "_verkocht_na_vol_kwh",
        "_tekort_soort_vandaag",
        "_nacht_geclassificeerd_op",
    ):
        assert veld in PERSISTED_PLAIN_FIELDS
