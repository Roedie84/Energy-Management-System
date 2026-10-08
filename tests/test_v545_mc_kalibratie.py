"""De Monte-Carlo-tekortkans van 22:00 per avond bewaard (v5.45).

Uit de leerronde van 7 oktober: kans om 22:00 tegen de uitkomst over 8
nachten (30-09..07-10) gaf Brier 0,038, maar de sensor heeft geen
state_class - na ~10 dagen recorder is de voorspelling per nacht weg. Nu
bewaart de integratie de kans van 22:00 per avond en zet hem in het
dagrecord van de nacht die erop volgt. Stuurt niets.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    MC_KALIBRATIE_BEWAAR_AVONDEN,
    PERSISTED_PLAIN_FIELDS,
)

TZ = timezone.utc


def _seed(c, kw=0.3):
    for h in range(24):
        c.hourly_consumption_profile[h] = [kw] * 7
        c.pv_hourly_bias_history[h] = [0.0] * 7


def _c(make_coordinator, hass, beschikbaar="0.5"):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.available_energy"})
    hass.states.set("sensor.available_energy", beschikbaar)
    _seed(c)
    return c


def test_de_kans_van_22_uur_wordt_bewaard(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    avond = datetime(2026, 10, 7, 22, 4, tzinfo=TZ)

    c._run_monte_carlo_simulation(avond, avond + timedelta(hours=4))

    stand = c.mc_22u_per_avond["2026-10-07"]
    assert stand["kans_pct"] == c.monte_carlo_shortfall_probability_percent == 100.0
    assert stand["tijd"] == "22:04"
    assert stand["beschikbaar_kwh"] == 0.5
    assert stand["mediaan_kwh"] == c.monte_carlo_median_deficit_kwh


def test_de_eerste_ronde_van_het_uur_telt(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    eerst = datetime(2026, 10, 7, 22, 1, tzinfo=TZ)
    c._run_monte_carlo_simulation(eerst, eerst + timedelta(hours=4))
    hass.states.set("sensor.available_energy", "9.0")
    later = datetime(2026, 10, 7, 22, 40, tzinfo=TZ)
    c._run_monte_carlo_simulation(later, later + timedelta(hours=4))

    assert c.mc_22u_per_avond["2026-10-07"]["tijd"] == "22:01"
    assert c.mc_22u_per_avond["2026-10-07"]["kans_pct"] == 100.0


def test_buiten_het_uur_niets(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    for uur in (21, 23):
        moment = datetime(2026, 10, 7, uur, 30, tzinfo=TZ)
        c._run_monte_carlo_simulation(moment, moment + timedelta(hours=4))

    assert not c.mc_22u_per_avond


def test_zonder_kans_niets(make_coordinator, hass):
    c = make_coordinator({})
    _seed(c)
    avond = datetime(2026, 10, 7, 22, 4, tzinfo=TZ)
    c._run_monte_carlo_simulation(avond, avond + timedelta(hours=4))

    assert not c.mc_22u_per_avond


def test_hooguit_veertien_avonden(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    begin = datetime(2026, 9, 1, 22, 5, tzinfo=TZ)
    for d in range(20):
        moment = begin + timedelta(days=d)
        c._run_monte_carlo_simulation(moment, moment + timedelta(hours=4))

    assert len(c.mc_22u_per_avond) == MC_KALIBRATIE_BEWAAR_AVONDEN
    assert min(c.mc_22u_per_avond) == "2026-09-07"


def test_bewaard_over_een_herstart():
    assert "mc_22u_per_avond" in PERSISTED_PLAIN_FIELDS


def test_het_dagrecord_krijgt_de_kans_van_de_avond_ervoor(make_coordinator, hass):
    """Dagrecord 8 oktober draagt de nacht die op 8 oktober om 09:00 afliep;
    de kans daarvoor is op 7 oktober om 22:00 uitgerekend."""
    c = make_coordinator({})
    c.mc_22u_per_avond = {
        "2026-10-07": {"tijd": "22:00", "kans_pct": 41.7},
        "2026-10-08": {"tijd": "22:00", "kans_pct": 3.0},
    }
    c._shortfall_check_date = datetime(2026, 10, 8, tzinfo=TZ).date()
    c._tekortnacht_vandaag_kwh = 0.0
    c._update_shortfall_detection(
        datetime(2026, 10, 9, 0, 0, tzinfo=TZ), "default_smart", None, None
    )

    record = c.reserve_daily_records[-1]
    assert record["date"] == "2026-10-08"
    assert record["mc_22u"]["kans_pct"] == 41.7


def test_zonder_bewaarde_avond_geen_veld(make_coordinator, hass):
    c = make_coordinator({})
    c._shortfall_check_date = datetime(2026, 10, 8, tzinfo=TZ).date()
    c._tekortnacht_vandaag_kwh = 0.0
    c._update_shortfall_detection(
        datetime(2026, 10, 9, 0, 0, tzinfo=TZ), "default_smart", None, None
    )

    assert "mc_22u" not in c.reserve_daily_records[-1]


def test_kalibratie_brier_over_de_bewaarde_nachten(make_coordinator, hass):
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"date": "2026-10-08", "shortfall": True, "mc_22u": {"kans_pct": 90.0}},
        {"date": "2026-10-09", "shortfall": False, "mc_22u": {"kans_pct": 10.0}},
        {"date": "2026-10-10", "shortfall": False},  # van voor v5.45: telt niet
    ]

    k = c.get_mc_kalibratie_22u()

    assert k["nachten"] == 2
    assert k["brier"] == 0.01
    assert k["per_nacht"][0] == {"nacht_tot": "2026-10-08", "kans_pct": 90.0, "tekortnacht": True}
    assert c.get_monte_carlo_vergelijking()["kalibratie_22u"]["nachten"] == 2


def test_kalibratie_zonder_nachten(make_coordinator, hass):
    c = make_coordinator({})

    assert c.get_mc_kalibratie_22u() == {"nachten": 0, "brier": None, "per_nacht": []}


# =========================================================================
# v5.45 - het dagrapport zegt hoeveel kwartieren het kon narekenen
# =========================================================================

def test_het_dagrapport_telt_de_bruikbare_kwartieren():
    """8 oktober: de zonteller (SolarEdge-cloud, dagteller) staat 's nachts
    op unknown; die kwartieren telden wel als gemeten maar niet mee."""
    from custom_components.energy_management_system import schaduw
    from custom_components.energy_management_system.meetlaag import schaduw_dagrapport

    ev = [{"evaluation_timestamp": f"2026-10-07T0{u}:00:00+02:00", "production_action": {"categorie": "huis_dekken"},
           "economic_per_slijtage": {ct: "huis_dekken" for ct in schaduw.SLIJTAGEVARIANTEN_CT},
           "measurements": {"beschikbaar_kwh": 5.0}} for u in range(4)]
    kw = [
        {"kwartier": "2026-10-07T00:00:00+02:00", "house_kwh": None, "pv_kwh": None, "prijs_eur": 0.38, "coverage_percent": 100},
        {"kwartier": "2026-10-07T01:00:00+02:00", "house_kwh": None, "pv_kwh": 0.0, "prijs_eur": 0.36, "coverage_percent": 80},
        {"kwartier": "2026-10-07T02:00:00+02:00", "house_kwh": 0.05, "pv_kwh": 0.0, "prijs_eur": None, "coverage_percent": 100},
        {"kwartier": "2026-10-07T03:00:00+02:00", "house_kwh": 0.05, "pv_kwh": 0.0, "prijs_eur": 0.35, "coverage_percent": 100},
    ]

    rapport = schaduw_dagrapport(ev, kw, 7.78, 83.8)

    assert rapport["kwartieren_gemeten"] == 4
    assert rapport["kwartieren_bruikbaar"] == 1
    assert rapport["kwartieren_ongebruikt"] == {
        "pv_onbekend": 1, "andere_teller_onbekend": 1, "geen_prijs": 1,
    }
