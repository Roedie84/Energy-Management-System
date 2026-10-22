"""v5.116.0: dagbesparing met de accu-inhoud tegen de gemeten laadprijs, en
de uitval van de prijsbron in de diagnose.

Plan tegen werkelijkheid 22-10 (meetdag 21-10): eigen berekening € 0,35,
de meter "EMS Accubesparing - vandaag" € 1,56 (rekent de daling van de
accu-inhoud niet mee) en de dagsensor € 0,06 (voorraad tegen de prijs van
het moment). En `sensor.stroomprijs_kwartier` was 5 3/4 uur weg zonder dat de
diagnose zei sinds wanneer en met welke prijzen het EMS doorrekende.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from homeassistant.util import dt as dt_util

from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system.const import PERSISTED_FIELDS
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)
from custom_components.energy_management_system.sensor import (
    CounterfactualSavingsTotalSensor,
)


# --- 1. de kostprijs van wat er in de accu zit ---------------------------

def test_voorraad_kostprijs_per_opgeslagen_kwh():
    partijen = [A.Partij(1.0, 0.0, "begin", "d", None),
                A.Partij(2.0, 0.22, "net", "d", None),
                A.Partij(1.0, 0.10, "zon", "d", None)]
    uit = A.voorraad_kostprijs(partijen, 0.92)
    assert uit["bekend_kwh"] == 3.0 and uit["onbekend_kwh"] == 1.0
    assert uit["eur_per_kwh"] == pytest.approx((2 * 0.22 + 0.10) / 3 / 0.92, abs=1e-4)


def test_alleen_beginvoorraad_geeft_geen_kostprijs():
    uit = A.voorraad_kostprijs([A.Partij(5.0, 0.0, "begin", "d", None)], 0.92)
    assert uit["eur_per_kwh"] is None


def test_doorreken_geeft_de_voorraad_kostprijs():
    dag = "2026-10-21"
    regels = [{"tijd": f"{u:02d}:00:00", "beschikbaar_kwh": 1.0 + u * 0.5, "prijs_ct": 25.0,
               "accu_w": -2000, "net_w": 2000} for u in range(4)]
    uit = A.doorreken({dag: regels}, 0.92, 0.92, 0.0)
    kp = uit["voorraad_kostprijs"]
    assert kp["bekend_kwh"] == pytest.approx(1.5) and kp["eur_per_kwh"] == pytest.approx(0.25 / 0.92, abs=1e-4)


def _c():
    c = object.__new__(C)
    c.battery_cost_basis_eur_per_kwh = None
    c.current_feedin_value_eur_per_kwh = None
    c.get_accukosten = lambda now=None: {}
    return c


def test_waarde_eerst_de_gemeten_laadprijs():
    c = _c()
    c.get_accukosten = lambda now=None: {"voorraad_kostprijs": {"eur_per_kwh": 0.267}}
    c.battery_cost_basis_eur_per_kwh = 0.3677
    c.current_feedin_value_eur_per_kwh = 0.37
    assert c._voorraad_kwh_waarde() == (0.267, "gemeten laadprijs van de voorraad")


def test_waarde_terugval_kostprijs_dan_prijs_nu():
    c = _c()
    c.battery_cost_basis_eur_per_kwh = 0.3677
    c.current_feedin_value_eur_per_kwh = 0.37
    assert c._voorraad_kwh_waarde() == (0.3677, "kostprijsmodel")
    c.battery_cost_basis_eur_per_kwh = None
    assert c._voorraad_kwh_waarde() == (0.37, "terugleverwaarde nu")
    c.current_feedin_value_eur_per_kwh = None
    assert c._voorraad_kwh_waarde() == (None, None)


def test_dag_21_10_komt_op_de_eigen_berekening():
    """Rauw € 1,55, accu 60 -> 21 % (-4,5 kWh) tegen 26,7 ct = € 0,35."""
    c = _c()
    c.get_accukosten = lambda now=None: {"voorraad_kostprijs": {"eur_per_kwh": 0.267}}
    c._savings_day_start_available_kwh = 6.9
    c.beschikbare_energie_kwh = lambda: 2.4
    c.counterfactual_cost_today_eur = 3.05
    c.actual_cost_today_eur = 1.50
    corr = c.get_savings_correction()
    assert corr["besparing_gecorrigeerd_eur"] == pytest.approx(0.35, abs=0.01)
    assert corr["kwh_waarde_bron"] == "gemeten laadprijs van de voorraad"


# --- 2. het oplopende totaal voor de meters ------------------------------

def _rondgang(make_coordinator, monkeypatch):
    """Een coordinator waarvan de tegenfeitelijke telling te sturen is."""
    c = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    from custom_components.energy_management_system import coordinator as mod
    c.config[mod.CONF_CONSUMPTION_POWER_SENSOR] = "sensor.p1"
    toestand = {"p1": 0.0, "accu": 0.0, "kwh": 6.9}
    c._read_sensor_float = lambda e: toestand["p1"]
    c.huidige_prijs_eur_per_kwh = lambda: 0.30
    c._get_feedin_value_per_kwh = lambda entries, now: 0.30
    c.beschikbare_energie_kwh = lambda: toestand["kwh"]
    c.get_accukosten = lambda now=None: {"voorraad_kostprijs": {"eur_per_kwh": 0.25}}
    return c, toestand


def test_totaal_loopt_door_over_de_daggrens(make_coordinator, monkeypatch):
    c, t = _rondgang(make_coordinator, monkeypatch)
    sensor = CounterfactualSavingsTotalSensor(c, "e")
    d1 = datetime(2026, 10, 21, 0, 0, 5, tzinfo=timezone.utc)
    c._update_counterfactual_savings(d1)              # dagbegin 6,9 kWh
    assert c._savings_day_start_available_kwh == 6.9
    begin_totaal = sensor.native_value
    # de dag: accu ontlaadt 4,5 kWh
    t["kwh"] = 2.4
    voor = c.besparing_totaal_gecorrigeerd_eur()
    assert voor - begin_totaal == pytest.approx(-4.5 * 0.25, abs=1e-6)
    # middernacht: de correctie van gisteren gaat het totaal in, geen sprong
    d2 = datetime(2026, 10, 22, 0, 0, 5, tzinfo=timezone.utc)
    c._update_counterfactual_savings(d2)
    assert c._savings_day_start_available_kwh == 2.4
    assert c.besparing_voorraadcorrectie_totaal_eur == pytest.approx(-1.125)
    assert c.besparing_totaal_gecorrigeerd_eur() == pytest.approx(voor, abs=1e-6)
    attrs = sensor.extra_state_attributes
    assert attrs["voorraadcorrectie_afgesloten_dagen_eur"] == pytest.approx(-1.125, abs=0.01)
    assert attrs["kwh_waarde_bron"] == "gemeten laadprijs van de voorraad"


def test_eerste_start_sluit_geen_dag_af(make_coordinator, monkeypatch):
    c, t = _rondgang(make_coordinator, monkeypatch)
    c._counterfactual_day_key = None
    c._savings_day_start_available_kwh = 1.0
    c._update_counterfactual_savings(datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc))
    assert c.besparing_voorraadcorrectie_totaal_eur == 0.0


def test_bewaard():
    assert PERSISTED_FIELDS["besparing_voorraadcorrectie_totaal_eur"] == {"type": "plain"}


# --- 3. de prijsbron in de diagnose --------------------------------------

def _reeks(begin, n):
    return [{"start_date": (begin + timedelta(minutes=15 * i)).isoformat(),
             "end_date": (begin + timedelta(minutes=15 * (i + 1))).isoformat(),
             "price_tax_included": {"amount": 3_000_000 + i}} for i in range(n)]


def _pc(attrs):
    c = object.__new__(C)
    c.config = {"price_sensor_entity": "sensor.prijs"}
    toestand = SimpleNamespace(attributes=attrs) if attrs is not None else None
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: toestand))
    c.instelling = lambda k, d=None: d
    c.prijs_forecast_cache = None
    return c


def test_prijsbron_weg_en_terug(monkeypatch):
    klok = {"nu": datetime(2026, 10, 21, 12, 40, tzinfo=timezone.utc)}
    monkeypatch.setattr(dt_util, "now", lambda *a: klok["nu"], raising=False)
    begin = klok["nu"].replace(minute=0) - timedelta(hours=10)
    c = _pc({"forecast": _reeks(begin, 4 * 34)})
    c._get_forecast_entries()
    assert c.get_prijsbron()["bron"] == "prijssensor (live)"
    assert c._prijsbron_aandachtspunt() is None

    # 14:46 lokale tijd: Zonneplan weg
    klok["nu"] = datetime(2026, 10, 21, 12, 46, tzinfo=timezone.utc)
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: SimpleNamespace(attributes={})))
    c._get_forecast_entries()
    pb = c.get_prijsbron()
    assert pb["bron"] == "bewaarde reeks" and pb["weg_minuten"] == 0
    assert c._prijsbron_aandachtspunt() is None             # nog geen half uur

    klok["nu"] = datetime(2026, 10, 21, 13, 31, tzinfo=timezone.utc)
    c._get_forecast_entries()
    pb = c.get_prijsbron()
    assert pb["weg_minuten"] == 45
    assert pb["bewaarde_reeks_leeftijd_minuten"] == 51
    assert pb["bewaarde_kwartieren_vooruit"] > 0
    punt = c._prijsbron_aandachtspunt()
    assert "sinds 21-10" in punt and "(45 min)" in punt and "bewaarde kwartierprijzen" in punt

    # 20:30: weer prijzen
    klok["nu"] = datetime(2026, 10, 21, 18, 30, tzinfo=timezone.utc)
    c.hass = SimpleNamespace(states=SimpleNamespace(
        get=lambda e: SimpleNamespace(attributes={"forecast": _reeks(begin, 4 * 34)}))
    )
    c._get_forecast_entries()
    pb = c.get_prijsbron()
    assert pb["bron"] == "prijssensor (live)" and pb["weg_sinds"] is None
    assert pb["storingen_7_dagen"] == 1 and pb["storingen_7_dagen_minuten"] == 344
    assert pb["laatste_storingen"][0]["terugval"] == "bewaarde reeks"
    assert c._prijsbron_aandachtspunt() is None


def test_kort_weg_na_een_herstart_is_geen_storing(monkeypatch):
    klok = {"nu": datetime(2026, 10, 22, 5, 7, tzinfo=timezone.utc)}
    monkeypatch.setattr(dt_util, "now", lambda *a: klok["nu"], raising=False)
    c = _pc({})
    c.prijs_forecast_cache = {"sensor": "sensor.prijs", "om": klok["nu"].isoformat(),
                              "forecast": _reeks(klok["nu"], 40)}
    c._get_forecast_entries()
    assert c._prijsbron_weg_sinds is not None
    klok["nu"] += timedelta(minutes=2)
    c.hass = SimpleNamespace(states=SimpleNamespace(
        get=lambda e: SimpleNamespace(attributes={"forecast": _reeks(klok["nu"], 40)})))
    c._get_forecast_entries()
    assert c._prijsbron_weg_sinds is None and not c.prijsbron_storingen


def test_zonder_bewaarde_reeks_staat_het_er_ook(monkeypatch):
    nu = datetime(2026, 10, 21, 13, 31, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "now", lambda *a: nu, raising=False)
    c = _pc({})
    c.prijsgeschiedenis = {}
    c._prijsbron_weg_sinds = (nu - timedelta(minutes=90)).isoformat()
    c._get_forecast_entries()
    assert c.get_prijsbron()["bron"] == "geen"
    assert "geen prijzen om mee te rekenen" in c._prijsbron_aandachtspunt()
    assert "(1 u 30 min)" in c._prijsbron_aandachtspunt()


def test_prijsbron_bewaard_en_in_de_diagnose():
    from pathlib import Path

    for veld in ("prijsbron_storingen", "_prijsbron_weg_sinds", "_prijsbron_terugval"):
        assert PERSISTED_FIELDS[veld] == {"type": "plain"}
    diag = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
            / "diagnostics.py").read_text(encoding="utf-8")
    assert '"prijsbron": _veilig("get_prijsbron"' in diag


def test_aandachtspunt_in_de_samenvatting(make_coordinator):
    c = make_coordinator({})
    c._prijsbron_aandachtspunt = lambda now=None: "Prijsbron sensor.prijs geeft sinds 21-10 14:46 geen prijzen (45 min); x."
    punten = c.get_diagnostic_summary()["aandachtspunten"]
    assert any(p.startswith("Prijsbron sensor.prijs") for p in punten)
