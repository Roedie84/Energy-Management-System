"""v5.186.0 spoor C - de zonverwachting.

30. De uurcorrectie leert niet van begrensde uren (negatieve prijs, 2027-grens)
    of van een stukje uur na een herstart; elk nieuw monster begrensd.
36. Vandaag: de geleerde correctie geldt ook voor vandaag (oorzaak van de
    -13 %), plus de zon van de laatste uren, uitdovend; de min-regel alleen
    voor "veilig".
38. Een weggevallen bron: gebufferde halfuren gelden tot hun eigen eind;
    ontbrekende zon overdag is een gat, geen 0.
43. Een witgoedprofiel volgt de geplande duur.
Klein: de Solcast-teller "rest van vandaag" begrensd.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import coordinator as mod
from custom_components.energy_management_system import witgoedprofiel as P
from custom_components.energy_management_system.bronbuffer import Bronbuffer
from custom_components.energy_management_system.const import (
    PV_HOURLY_BIAS_MAX_RATIO,
    ZON_RECENT_MAX,
    ZON_REST_MAX,
)

TZ = timezone(timedelta(hours=1))
DAG = datetime(2026, 6, 1, tzinfo=TZ)


def _pv(make_coordinator, hass, extra=None):
    c = make_coordinator({"pv_power_sensor_entity": "sensor.pv", **(extra or {})})
    hass.states.set("sensor.pv", "2000")
    c._get_forecast_kwh_for_hour = lambda d, h: 2.0
    c._leg_pv_modelmonster_vast = lambda *a: None
    c._ruwe_zon_kwh = lambda a, b: 0.0
    return c


def _loop(c, van, tot):
    t = van
    c._update_pv_hourly_bias_tracking(t)
    while t < tot:
        t += timedelta(minutes=1)
        c._update_pv_hourly_bias_tracking(t)


# --- 30 ------------------------------------------------------------------


def test_een_stukje_uur_na_een_herstart_leert_niets(make_coordinator, hass):
    """Reviewer: herstart 12:40 -> 20 min opwek tegen het hele uur (0,33)."""
    c = _pv(make_coordinator, hass)
    _loop(c, DAG.replace(hour=12, minute=40), DAG.replace(hour=13, minute=1))
    assert not any(c.pv_hourly_bias_history.values())


def test_een_heel_uur_leert_wel(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    _loop(c, DAG.replace(hour=11, minute=59), DAG.replace(hour=13, minute=1))
    assert sum(len(v) for v in c.pv_hourly_bias_history.values()) == 1
    (waarde,) = [v for v in c.pv_hourly_bias_history.values() if v][0]
    assert waarde == pytest.approx(1.0, abs=0.02)        # 2 kW x 1 u tegen 2 kWh


def test_een_begrensd_uur_leert_niets(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    c._is_negative_price_active = True
    hass.states.set("sensor.pv", "0")
    _loop(c, DAG.replace(hour=11, minute=59), DAG.replace(hour=13, minute=1))
    assert not any(c.pv_hourly_bias_history.values())


def test_begrensd_via_de_omvormergrens(make_coordinator, hass):
    c = _pv(make_coordinator, hass, {"solar_power_limit_entity": "number.grens"})
    hass.states.set("number.grens", "40")
    assert c._pv_begrensd_nu() is True
    hass.states.set("number.grens", "100")
    assert c._pv_begrensd_nu() is False
    c._teruglevering_begrensd = True
    assert c._pv_begrensd_nu() is True


def test_negen_tiende_uur_geschaald(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    c._pv_current_tracked_hour = 12
    c._pv_hour_energy_kwh, c._pv_hour_duration_hours = 1.8, 0.95
    c._finalize_pv_hourly_bucket(DAG.replace(hour=13))
    (waarde,) = [v for v in c.pv_hourly_bias_history.values() if v][0]
    assert waarde == pytest.approx(1.8 / (2.0 * 0.95))


def test_elk_monster_begrensd(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    c._pv_current_tracked_hour = 12
    c._pv_hour_energy_kwh, c._pv_hour_duration_hours = 9.0, 1.0
    c._finalize_pv_hourly_bucket(DAG.replace(hour=13))
    (waarde,) = [v for v in c.pv_hourly_bias_history.values() if v][0]
    assert waarde == PV_HOURLY_BIAS_MAX_RATIO


# --- 36 ------------------------------------------------------------------


def _entries(dag, kw=2.0):
    return [(dag + timedelta(minutes=30 * i), dag + timedelta(minutes=30 * (i + 1)), kw * 0.5)
            for i in range(48)]


def _vandaag(make_coordinator, monkeypatch, nu):
    c = make_coordinator({})
    monkeypatch.setattr(mod.dt_util, "now", lambda: nu)
    entries = _entries(nu.replace(hour=0, minute=0)) + _entries(nu.replace(hour=0, minute=0) + timedelta(days=1))
    c._get_pv_forecast_entries = lambda: entries
    c._get_pv_remaining_correction_ratio = lambda n, e: 1.0
    c._zon_realisatie = lambda n, e: None
    c.zonbias_percent = lambda: None
    return c


def test_vandaag_krijgt_de_geleerde_correctie(make_coordinator, monkeypatch):
    """De oorzaak van de -13 %: voor vandaag gold alleen de teller (~1,0)."""
    nu = DAG.replace(hour=7)
    c = _vandaag(make_coordinator, monkeypatch, nu)
    c._zon_recent = lambda n: None
    c.learned_pv_hourly_ratio = lambda uur: 0.87
    a = nu.replace(hour=13)
    assert c._estimate_pv_kwh_for_period(a, a + timedelta(hours=1)) == pytest.approx(2.0 * 0.87)
    # morgen al zo
    m = a + timedelta(days=1)
    assert c._estimate_pv_kwh_for_period(m, m + timedelta(hours=1)) == pytest.approx(2.0 * 0.87)


def test_recente_zon_dooft_uit(make_coordinator, monkeypatch):
    nu = DAG.replace(hour=10)
    c = _vandaag(make_coordinator, monkeypatch, nu)
    c.learned_pv_hourly_ratio = lambda uur: None
    c._zon_recent = lambda n: 0.6
    dichtbij = c._estimate_pv_kwh_for_period(nu, nu + timedelta(minutes=30))
    halverwege = c._estimate_pv_kwh_for_period(nu + timedelta(hours=2), nu + timedelta(hours=2, minutes=30))
    ver = c._estimate_pv_kwh_for_period(nu + timedelta(hours=5), nu + timedelta(hours=5, minutes=30))
    assert dichtbij == pytest.approx(0.6)
    assert halverwege == pytest.approx(1.0 * (1 - 0.5 * 0.4))
    assert ver == pytest.approx(1.0)


def test_veilig_houdt_de_min_regel(make_coordinator, monkeypatch):
    nu = DAG.replace(hour=10)
    c = _vandaag(make_coordinator, monkeypatch, nu)
    c.learned_pv_hourly_ratio = lambda uur: 0.9
    c._zon_realisatie = lambda n, e: 0.7
    c._zon_recent = lambda n: 1.3
    c.get_pv_band_calibration = lambda: {"beschikbaar": False}
    a = nu + timedelta(hours=3)
    assert c._estimate_pv_kwh_for_period(a, a + timedelta(hours=1), veilig=True) == pytest.approx(2.0 * 0.7)
    # verwacht: de correctie met de recente zon, uitdovend (3 en 3,5 uur weg)
    assert c._estimate_pv_kwh_for_period(a, a + timedelta(hours=1)) == pytest.approx(
        2.0 * 0.9 * (1 + 0.3 * (0.25 + 0.125) / 2))


def test_recente_verhouding_begrensd_en_zonder_begrensde_uren(make_coordinator, monkeypatch):
    nu = DAG.replace(hour=10, minute=30)
    c = _vandaag(make_coordinator, monkeypatch, nu)
    c.learned_pv_hourly_ratio = lambda uur: None
    c._pv_recente_uren = [{"begin": nu.replace(minute=0) - timedelta(hours=1), "eind": nu.replace(minute=0),
                           "werkelijk_kwh": 4.0, "verwacht_kwh": 2.0, "geldig": True}]
    c._pv_hour_duration_hours, c._pv_hour_energy_kwh = 0.0, 0.0
    assert c._zon_recent(nu) == ZON_RECENT_MAX
    c._pv_recente_uren[0]["geldig"] = False
    assert c._zon_recent(nu) is None
    # het lopende half uur telt mee
    c._pv_hour_duration_hours, c._pv_hour_energy_kwh = 0.5, 0.5
    assert c._zon_recent(nu) == pytest.approx(0.5)


def test_rest_van_vandaag_begrensd(make_coordinator, hass, monkeypatch):
    nu = DAG.replace(hour=16)
    c = make_coordinator({"solar_remaining_today_sensor_entity": "sensor.rest"})
    hass.states.set("sensor.rest", "40")
    assert c._get_pv_remaining_correction_ratio(nu, _entries(nu.replace(hour=0))) == ZON_REST_MAX


# --- 38 ------------------------------------------------------------------


def _solcast(dag):
    return [{"period_start": (dag + timedelta(minutes=30 * i)).isoformat(), "pv_estimate": 1.0}
            for i in range(48)]


def test_gebufferde_halfuren_gelden_tot_hun_eind():
    b = Bronbuffer()
    b.regels = {"sensor.morgen": ("dag", 0)}
    gisteren = DAG.replace(hour=20) - timedelta(days=1)

    class S:
        state, attributes = "12.0", {"detailedForecast": _solcast(DAG)}

    b.lees("sensor.morgen", S(), gisteren)
    nu = DAG.replace(hour=9, minute=10)
    uit = b.lees("sensor.morgen", None, nu)
    assert uit is not None and uit.state == "unavailable"
    rest = uit.attributes["detailedForecast"]
    assert rest[0]["period_start"] == DAG.replace(hour=9).isoformat()
    assert len(rest) == 48 - 18
    # de dag erna: niets meer over
    assert b.lees("sensor.morgen", None, DAG + timedelta(days=1, hours=1)) is None


def test_geen_dubbele_halfuren(make_coordinator, hass):
    c = make_coordinator({
        "solar_today_forecast_sensor_entity": "sensor.vandaag",
        "solar_forecast_sensor_entity": "sensor.morgen",
    })
    hass.states.set("sensor.vandaag", "10", {"detailedForecast": _solcast(DAG)})
    hass.states.set("sensor.morgen", "10", {"detailedForecast": [
        {**i, "pv_estimate": 5.0} for i in _solcast(DAG)]})
    entries = c._lees_pv_forecast_entries()
    assert len(entries) == 48
    assert entries[0][2] == pytest.approx(0.5)            # de sensor van vandaag wint


def test_ontbrekende_zon_overdag_is_een_gat(make_coordinator, hass, monkeypatch):
    c = make_coordinator({"solar_forecast_sensor_entity": "sensor.morgen"})
    monkeypatch.setattr(mod.dt_util, "now", lambda: DAG.replace(hour=8))
    c._get_pv_forecast_entries = lambda: _entries(DAG)
    c._bereken_zonstand = lambda t: (180.0, 40.0 if 6 <= t.hour < 21 else -10.0)
    morgen = DAG + timedelta(days=1)
    assert c._pv_gat_in(DAG.replace(hour=12), DAG.replace(hour=12, minute=15)) is False   # gedekt
    assert c._pv_gat_in(morgen.replace(hour=12), morgen.replace(hour=12, minute=15)) is True
    assert c._pv_gat_in(morgen.replace(hour=2), morgen.replace(hour=2, minute=15)) is False  # nacht
    assert "zonvoorspelling ontbreekt" in c._pv_gat_aandachtspunt(DAG.replace(hour=8, minute=5))
    # zonder zonvoorspelling ingesteld geen gat
    c.config = {}
    assert c._pv_gat_in(morgen.replace(hour=12), morgen.replace(hour=12, minute=15)) is False


def test_waardeplan_knipt_bij_een_zongat():
    bron = (mod.Path(mod.__file__).parent / "waardeplan_sturing.py").read_text()
    assert "if self._pv_gat_in(van, eind):" in bron


# --- 43 ------------------------------------------------------------------


def test_profiel_gerekt_naar_de_geplande_duur():
    prof = [0.4, 0.3, 0.2, 0.1]                     # een uur
    lang = P.rek(prof, 120)
    assert len(lang) == 8 and sum(lang) == pytest.approx(1.0)
    assert lang[0] + lang[1] == pytest.approx(0.4)  # de vorm blijft
    assert P.rek(prof, 65) == prof                  # binnen de drempel
    assert P.rek(prof, None) == prof
    assert P.rek(prof, 900) == prof                 # onzin


def test_geplande_cyclus_volgt_het_eind(make_coordinator):
    t = DAG.replace(hour=4)
    prof = [0.4, 0.3, 0.2, 0.1]
    regel = {"start": t.isoformat(), "eind": (t + timedelta(hours=2)).isoformat(), "kwh": 1.0}
    q = [mod.witgoed_kwh_in_periode(regel, t + timedelta(minutes=15 * i), t + timedelta(minutes=15 * (i + 1)), prof)
         for i in range(8)]
    assert sum(q) == pytest.approx(1.0) and q[7] > 0
    assert q[0] == pytest.approx(0.2)


def test_een_cyclus_is_geen_profiel():
    afwas = [1900, 1900, 1240, 1300, 1200, 1340, 1500, 1500, 1360, 600, 560, 520] + [5] * 8
    assert P.profiel(afwas) is None
    assert P.profiel(afwas + afwas) is not None
