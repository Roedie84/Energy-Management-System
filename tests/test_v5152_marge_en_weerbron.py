"""v5.152.0: eigen marge per NILM-apparaat, en weerbronnen per kwartier.

Akkoord 31-10 op beide punten.

1. CV-ketel: om de dag 8,2 of 9,9 W. Met een vaste marge van 10 % telde
   elke 9,9-dag mee; de optelling stond op 3,5 (alarm bij 1) en elke dag
   met 5 W extra gaf meteen "mogelijk defect".
2. L-EMS-046: de weerbronreeks kreeg elke minuut een waarneming (200 =
   ruim drie uur). Nu één per kwartier, met datum; weren pas na twee dagen.
"""
import asyncio
from datetime import datetime, timedelta, timezone

CV_REEKS = [
    8.3, 9.87, 8.92, 8.65, 12.94, 9.04, 8.05, 9.91, 8.42, 8.08, 8.23, 8.07,
    12.64, 8.23, 8.11, 9.91, 12.07, 7.59, 8.27, 7.76, 13.76, 7.83, 8.28,
    10.26, 8.98, 8.55, 8.88, 9.17, 8.2, 13.56,
]


def _cv(reeks=None, cusum=3.47, alarm=True):
    return {
        "friendly_name": "CV-ketel Vermogen",
        "daily_avg_history": list(reeks or CV_REEKS),
        "cusum_accumulator": cusum,
        "anomaly_detected": alarm,
        "estimated_drift_percent": 61.0 if alarm else None,
        "reference_avg_w": 8.42,
    }


def test_marge_uit_het_bovenkwartiel(make_coordinator):
    c = make_coordinator({})
    assert c._nilm_marge_uit([10.0] * 20) == 0.10  # vlak: de vaste marge
    marge = c._nilm_marge_uit(CV_REEKS[:-5])
    assert 0.12 < marge < 0.25
    assert c._nilm_marge_uit([1, 1, 1, 10, 10, 10]) == 0.5  # plafond


def test_herijk_haalt_het_valse_alarm_van_de_ketel_weg(make_coordinator):
    c = make_coordinator({})
    c.nilm_confirmed_devices = {"sensor.cv_ketel_vermogen": _cv()}
    c._herijk_nilm_marges()
    d = c.nilm_confirmed_devices["sensor.cv_ketel_vermogen"]
    assert d["cusum_accumulator"] < 1.0
    assert d["anomaly_detected"] is False
    assert d["_marge_herijkt"] is True
    # Eenmalig.
    d["cusum_accumulator"] = 2.0
    c._herijk_nilm_marges()
    assert d["cusum_accumulator"] == 2.0


def test_een_echt_stijgend_apparaat_houdt_zijn_alarm(make_coordinator):
    c = make_coordinator({})
    reeks = [60.0, 62.0, 61.0, 63.0, 60.0, 62.0, 61.0, 62.0, 60.0, 61.0] + [90.0] * 8
    c.nilm_confirmed_devices = {"sensor.koelkast": _cv(reeks, cusum=3.0)}
    c._herijk_nilm_marges()
    d = c.nilm_confirmed_devices["sensor.koelkast"]
    assert d["cusum_accumulator"] >= 1.0
    assert d["anomaly_detected"] is True


def test_dagelijkse_afwisseling_bouwt_niets_op(make_coordinator):
    """Een afwisselend 8,2/9,9-patroon telt niet meer op."""
    c = make_coordinator({})
    reeks = [8.2, 9.9] * 8
    d = _cv(reeks, cusum=0.0, alarm=False)
    c.nilm_confirmed_devices = {"sensor.cv": d}
    for _ in range(10):
        for w in (8.2, 9.9):
            c._finalize_nilm_device_day("sensor.cv", d, w)
    assert d["cusum_accumulator"] < 0.2
    assert d["anomaly_detected"] is False


def test_marge_leert_niet_bij_tijdens_een_alarm(make_coordinator):
    c = make_coordinator({})
    d = {"normale_marge": 0.1, "anomaly_detected": True}
    assert c._nilm_marge(d, [62.0] * 5 + [87.0] * 5) == 0.1


def _kwartieren(c, bron, uitkomsten, start):
    nu = start
    for eens in uitkomsten:
        c._weerbron_kwartier_bij(bron, eens, nu)
        nu += timedelta(minutes=15)
    c._weerbron_kwartier_bij(bron, True, nu)  # sluit het laatste kwartier


def test_een_kwartier_is_een_waarneming(make_coordinator):
    c = make_coordinator({})
    t = datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc)
    for m in range(15):  # vijftien minuten, meerderheid oneens
        c._weerbron_kwartier_bij("weather.owm", m < 5, t + timedelta(minutes=m))
    c._weerbron_kwartier_bij("weather.owm", True, t + timedelta(minutes=15))
    assert c.weather_source_agreement["weather.owm"] == [False]
    assert c.weather_source_agreement_dagen["weather.owm"] == ["2026-10-31"]


def test_oude_minutenreeks_begint_opnieuw(make_coordinator):
    c = make_coordinator({})
    c.weather_source_agreement = {"weather.owm": [True] * 200}
    t = datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc)
    _kwartieren(c, "weather.owm", [False], t)
    assert c.weather_source_agreement["weather.owm"] == [False]


def test_weren_pas_na_twee_dagen(make_coordinator):
    c = make_coordinator({})
    dag1 = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)
    _kwartieren(c, "weather.goed", [True] * 60, dag1)
    _kwartieren(c, "weather.slecht", [False] * 60, dag1)
    uit = c.weerbronnen_voor_het_ensemble(["weather.goed", "weather.slecht"])
    assert uit["geweerd"] == []
    rapport = c.get_weather_source_reliability()
    assert rapport["weather.slecht"]["aantal_dagen"] == 1

    dag2 = datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc)
    _kwartieren(c, "weather.goed", [True] * 10, dag2)
    _kwartieren(c, "weather.slecht", [False] * 10, dag2)
    uit = c.weerbronnen_voor_het_ensemble(["weather.goed", "weather.slecht"])
    assert uit["geweerd"] == ["weather.slecht"]


def test_dagen_overleven_een_herstart(make_coordinator):
    c = make_coordinator({})
    _kwartieren(c, "weather.owm", [True] * 3, datetime(2026, 10, 31, 9, tzinfo=timezone.utc))
    asyncio.run(c.async_save_persisted_state_now())
    vers = make_coordinator({})
    asyncio.run(vers.async_load_persisted_state())
    assert vers.weather_source_agreement_dagen["weather.owm"] == ["2026-10-31"] * 3
