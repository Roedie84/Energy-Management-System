"""v5.220.0: prijsniveau in de jaarafrekening, vervallen sensoren, pendelmeting bewaard.

Ruud 11-11 15:55 ("Als je zeker bent van je zaak, alles akkoord") na het
onderzoek naar getallen, berekeningen en wat niet meer gebruikt wordt.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.energy_management_system import jaarafrekening as ja
from custom_components.energy_management_system import sensor as S
from custom_components.energy_management_system.const import PERSISTED_FIELDS
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

VANDAAG = date(2026, 11, 11)
START = date(2025, 4, 1)


def _dagen(prijs_nu=0.50, prijs_oud=0.25, gas_nu=1.80, gas_oud=1.20, dagen_nu=40):
    """Twee jaar dagwaarden: vorig jaar compleet, dit jaar de laatste `dagen_nu` dagen."""
    uit = {}
    d = date(2025, 4, 1)
    while d < date(2026, 4, 1):
        uit[d] = {"afname_eur": 10 * prijs_oud, "afname_kwh": 10.0, "terug_eur": 0.0, "terug_kwh": 0.0,
                  "gas_eur": 2 * gas_oud, "gas_m3": 2.0}
        d += timedelta(days=1)
    for i in range(1, dagen_nu + 1):
        d = VANDAAG - timedelta(days=i)
        uit[d] = {"afname_eur": 8 * prijs_nu, "afname_kwh": 8.0, "terug_eur": 0.0, "terug_kwh": 0.0,
                  "gas_eur": 1 * gas_nu, "gas_m3": 1.0}
    return uit


# --- 1. prijsniveau -------------------------------------------------------


def test_factor_is_prijs_per_eenheid_nu_gedeeld_door_vorig_jaar():
    n = ja.prijsniveau(_dagen(), VANDAAG - timedelta(days=1))
    assert n["afname"]["toegepast"] and n["afname"]["factor"] == pytest.approx(2.0)
    assert n["gas"]["factor"] == pytest.approx(1.5)
    assert n["afname"]["dagen"] == ja.PRIJSNIVEAU_DAGEN
    # geen teruglevering in beide jaren: geen paren, factor 1
    assert n["terug"] == {"factor": 1.0, "dagen": 0, "toegepast": False}


def test_te_weinig_dagparen_laat_de_schatting_zoals_hij_was():
    n = ja.prijsniveau(_dagen(dagen_nu=ja.PRIJSNIVEAU_MIN_DAGEN - 1), VANDAAG - timedelta(days=1))
    assert n["afname"]["toegepast"] is False and n["afname"]["factor"] == 1.0


def test_factor_is_begrensd():
    # v5.227.0: binnen de aannemelijke dagprijzen (5 ct - EUR 1,50)
    n = ja.prijsniveau(_dagen(prijs_nu=1.40, prijs_oud=0.10), VANDAAG - timedelta(days=1))
    assert n["afname"]["factor"] == ja.PRIJSNIVEAU_MAX
    n = ja.prijsniveau(_dagen(prijs_nu=0.06, prijs_oud=0.50), VANDAAG - timedelta(days=1))
    assert n["afname"]["factor"] == ja.PRIJSNIVEAU_MIN


# --- v5.227.0: een sprong in de meterstatistiek ------------------------------


def test_een_sprong_in_de_kwh_van_vorig_jaar_verandert_de_factor_niet():
    """Oktober 2025: de P1-statistiek sprong 234 kWh op een dag; met sommen
    werd vorig jaar 10,8 ct en de factor 3,0 (saldo EUR -529)."""
    tot = VANDAAG - timedelta(days=1)
    schoon = ja.prijsniveau(_dagen(prijs_nu=0.33, prijs_oud=0.22), tot)
    dagen = _dagen(prijs_nu=0.33, prijs_oud=0.22)
    dagen[date(2025, 10, 20)]["afname_kwh"] += 234.0
    met_sprong = ja.prijsniveau(dagen, tot)

    assert schoon["afname"]["factor"] == pytest.approx(1.5)
    assert met_sprong["afname"]["factor"] == pytest.approx(1.5)
    assert met_sprong["afname"]["vorig_jaar_per_eenheid"] == pytest.approx(0.22)
    # de sprongdag zelf valt buiten de aannemelijke prijzen en telt niet mee
    assert met_sprong["afname"]["dagen"] == schoon["afname"]["dagen"] - 1


def test_de_mediaan_en_niet_het_gewogen_gemiddelde():
    tot = VANDAAG - timedelta(days=1)
    dagen = _dagen(prijs_nu=0.30, prijs_oud=0.20)
    # vijf dure dagen met veel verbruik trekken een som omhoog, de mediaan niet
    for i in range(1, 6):
        dag = VANDAAG - timedelta(days=i)
        dagen[dag] = {**dagen[dag], "afname_eur": 60 * 0.60, "afname_kwh": 60.0}

    assert ja.prijsniveau(dagen, tot)["afname"]["factor"] == pytest.approx(1.5)


def test_een_onaannemelijke_dagprijs_telt_niet_mee():
    tot = VANDAAG - timedelta(days=1)
    dagen = _dagen(prijs_nu=0.30, prijs_oud=0.20)
    dagen[VANDAAG - timedelta(days=3)]["afname_eur"] = 500.0

    n = ja.prijsniveau(dagen, tot)
    assert n["afname"]["dagen"] == ja.PRIJSNIVEAU_DAGEN - 1
    assert n["afname"]["factor"] == pytest.approx(1.5)


def test_de_rest_van_het_jaar_rekent_met_het_niveau_van_nu():
    inst = ja.Instellingen()
    duur = ja.bereken(_dagen(), START, VANDAAG, inst)
    gelijk = ja.bereken(_dagen(prijs_nu=0.25, gas_nu=1.20), START, VANDAAG, inst)
    # zelfde verbruik vorig jaar, dubbele stroomprijs en anderhalf keer de gasprijs
    assert duur["schatting_rest"]["afname_kwh"] == gelijk["schatting_rest"]["afname_kwh"]
    assert duur["schatting_rest"]["afname_eur"] == pytest.approx(2 * gelijk["schatting_rest"]["afname_eur"], rel=1e-3)
    assert duur["schatting_rest"]["gas_eur"] == pytest.approx(1.5 * gelijk["schatting_rest"]["gas_eur"], rel=1e-3)
    assert duur["verwacht_saldo_eur"] < gelijk["verwacht_saldo_eur"]
    assert duur["prijsniveau"]["afname"]["factor"] == pytest.approx(2.0)


def test_wat_al_gebeurd_is_verandert_niet():
    inst = ja.Instellingen()
    a = ja.bereken(_dagen(), START, VANDAAG, inst)
    dagen = _dagen()
    werkelijk, _, _, _ = ja._loop(dagen, inst, date(2026, 4, 1), date(2027, 3, 31), VANDAAG - timedelta(days=1))
    assert a["opbouw"]["afname_eur"] == pytest.approx(werkelijk["afname_eur"], abs=0.01)


def test_de_cockpit_noemt_de_omrekening():
    from pathlib import Path

    js = (Path(ja.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert "a.prijsniveau" in js and "prijsniveau van de laatste 30 dagen" in js


# --- 2. vervallen sensoren ------------------------------------------------

WEG = ("DischargeWindowStartSensor", "EffectiveExpensiveQuartersSensor", "SimulatedActionSensor",
       "EnergyBridgeCheckSensor", "DischargeValueSensor", "ChargeCostSensor", "MonthlySummarySensor",
       "LearnedNightConsumptionSensor")


@pytest.mark.parametrize("klasse", WEG)
def test_de_sensor_bestaat_niet_meer(klasse):
    assert not hasattr(S, klasse)


def test_hun_registratie_wordt_opgeruimd():
    for sleutel in ("discharge_window_start", "effective_expensive_quarters", "simulated_action",
                    "energy_bridge_check", "discharge_value", "charge_cost", "monthly_summary",
                    "learned_night_consumption", "battery_protection"):
        assert sleutel in S.VERVALLEN_SENSOREN


def test_de_tellers_erachter_blijven_bewaard():
    for veld in ("total_discharge_value_eur", "total_charge_cost_eur", "night_consumption_history",
                 "energy_bridge_transition_log", "current_month_discharge_value_eur"):
        assert veld in PERSISTED_FIELDS, veld


def test_opruimen_haalt_alleen_de_vervallen_sensoren_weg(monkeypatch):
    import sys
    import types

    weg = []

    class Register:
        def async_get_entity_id(self, domein, platform, unique_id):
            return f"sensor.{unique_id}" if unique_id.startswith("e1_") else None

        def async_remove(self, entity_id):
            weg.append(entity_id)

    er = types.ModuleType("homeassistant.helpers.entity_registry")
    er.async_get = lambda hass: Register()
    import homeassistant.helpers as helpers

    monkeypatch.setitem(sys.modules, "homeassistant.helpers.entity_registry", er)
    monkeypatch.setattr(helpers, "entity_registry", er, raising=False)
    S._ruim_vervallen_sensoren_op(object(), "e1")
    assert sorted(weg) == sorted(f"sensor.e1_{s}" for s in S.VERVALLEN_SENSOREN)


# --- 3. pendelmeting overleeft een herstart --------------------------------


def _pendel(c, w, t):
    return C._p1_pendel_energie(c, w, t)


def test_pendelmeting_staat_in_de_opslag():
    assert PERSISTED_FIELDS["p1_pendel_dagen"] == {"type": "plain"}


def test_vandaag_en_gisteren_komen_terug_na_een_herstart():
    t = datetime(2026, 11, 11, 16, 0, tzinfo=timezone.utc)
    c = SimpleNamespace(_p1_pendel_energie_staat=None,
                        p1_pendel_dagen={"dag": "2026-11-11", "vandaag": 12.1, "gisteren": 30.5})
    uit = _pendel(c, 100.0, t)
    assert uit == {"pendel_wh_vandaag": 12.1, "pendel_wh_gisteren": 30.5}
    assert c.p1_pendel_dagen["dag"] == "2026-11-11"


def test_herstart_na_middernacht_schuift_vandaag_naar_gisteren():
    t = datetime(2026, 11, 12, 0, 5, tzinfo=timezone.utc)
    c = SimpleNamespace(_p1_pendel_energie_staat=None,
                        p1_pendel_dagen={"dag": "2026-11-11", "vandaag": 12.14, "gisteren": 30.5})
    uit = _pendel(c, 100.0, t)
    assert uit == {"pendel_wh_vandaag": 0.0, "pendel_wh_gisteren": 12.1}


def test_oude_of_kapotte_opslag_begint_gewoon_opnieuw():
    t = datetime(2026, 11, 12, 0, 5, tzinfo=timezone.utc)
    for oud in (None, {"dag": "2026-11-01", "vandaag": 99.0, "gisteren": 1.0}, {"dag": "2026-11-12", "vandaag": "x"}, "kapot"):
        c = SimpleNamespace(_p1_pendel_energie_staat=None, p1_pendel_dagen=oud)
        assert _pendel(c, 100.0, t) == {"pendel_wh_vandaag": 0.0, "pendel_wh_gisteren": None}
