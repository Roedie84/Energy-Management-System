"""v5.81.1 (akkoord Ruud 11-10 07:56): vier punten uit de controle van 04:45.

1. Het reserve-plafond is wat er tussen de grenzen past (7,78 kWh), niet de
   totale accu (8,64): de beschikbare energie komt nooit boven 7,78.
2. Zelfcontrole "Eén reserve": de verkooptoets tegen de verkoopreserve.
3. De uitlegtekst noemt wat het getal is: tot het blok plus de lange horizon.
4. De tweede prijslaag leest de accustand met de modulesprong.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import coordinator as mod

NU = datetime(2026, 10, 10, 19, 30, tzinfo=timezone(timedelta(hours=2)))
BLOK = NU + timedelta(hours=15, minutes=15)


def _c(make_coordinator, beschikbaar=7.78):
    c = make_coordinator({"battery_min_soc_number_entity": "number.min_soc",
                          "available_energy_sensor_entity": "sensor.beschikbaar"})
    c.hass.states.set("number.min_soc", "10")
    c.hass.states.set("sensor.beschikbaar", str(beschikbaar))
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    # 10-10 19:30: (5,42 + 4,20) x 1,25 = 12,03 kWh
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 9.62
    return c


# --- 1. het plafond -------------------------------------------------------


def test_de_reserve_wordt_afgekapt_op_wat_er_tussen_de_grenzen_past(make_coordinator, hass):
    c = _c(make_coordinator)
    assert c.bruikbaar_tussen_grenzen_kwh() == pytest.approx(7.776)
    reserve = c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    assert reserve == pytest.approx(7.776)
    assert c.last_reserve_margin_breakdown["boven_capaciteit"] is True
    assert c.last_reserve_margin_breakdown["ongekapt_kwh"] > 8.64


def test_zonder_grenzen_valt_het_plafond_terug_op_de_capaciteit(make_coordinator, hass):
    c = make_coordinator({})
    c.bruikbaar_tussen_grenzen_kwh = lambda: None
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    assert c._reserve_plafond_kwh() == 8.64


def test_een_volle_accu_is_genoeg_voor_de_brug(make_coordinator, hass, monkeypatch):
    """Was structureel "niet genoeg": 7,78 beschikbaar tegen 8,64."""
    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)
    c = _c(make_coordinator, beschikbaar=7.776)
    c._should_postpone_charging([], NU, BLOK)
    assert c.last_needed_kwh_to_bridge == pytest.approx(7.776)
    assert c.last_has_enough_energy is True


def test_bijna_vol_bij_een_afgekapte_reserve_is_nog_niet_genoeg(make_coordinator, hass, monkeypatch):
    """Geen marge van 10% eronder: de woning vraagt meer dan erin past, dus
    vullen tot hij echt vol is."""
    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)
    c = _c(make_coordinator, beschikbaar=7.4)
    c._should_postpone_charging([], NU, BLOK)
    assert c.last_has_enough_energy is False


def test_bindt_het_plafond_dan_niets_te_verkopen(make_coordinator, hass, monkeypatch):
    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)
    c = _c(make_coordinator, beschikbaar=7.776)
    c.last_cheap_block_start = BLOK
    uit = c.may_sell_now(NU, 7.776)
    assert uit["mag_verkopen"] is False
    assert uit["nodig_voor_woning_kwh"] <= 7.78


# --- 2. de zelfcontrole ---------------------------------------------------


def _zelf(make_coordinator, monkeypatch, verkoop, verkoopreserve):
    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.last_cheap_block_start = BLOK
    c.last_reserve_margin_breakdown = {"reserve_kwh_after_margin": 5.867}
    c.last_needed_kwh_to_bridge = 5.867
    c.last_sell_check = {"nodig_voor_woning_kwh": verkoop}
    c.last_verkoopreserve = {"reserve_kwh": verkoopreserve}
    return c.zelfcontrole_een_reserve()


def test_de_verkoopreserve_is_geen_tweede_definitie(make_coordinator, hass, monkeypatch):
    """11-10 04:45: verkooptoets 1,41 tegen sturing 5,87 - de bewuste
    verkoopreserve van v5.70 (1,13 x 1,25)."""
    uit = _zelf(make_coordinator, monkeypatch, 1.41, 1.41)
    assert uit["in_orde"] is True
    assert uit["afwijkend"] == []


def test_een_echte_afwijking_wordt_nog_steeds_gemeld(make_coordinator, hass, monkeypatch):
    uit = _zelf(make_coordinator, monkeypatch, 3.0, 1.41)
    assert uit["in_orde"] is False
    assert uit["afwijkend"] == ["verkooptoets"]


def test_zonder_verkoopreserve_tegen_de_sturing(make_coordinator, hass, monkeypatch):
    assert _zelf(make_coordinator, monkeypatch, 5.867, None)["in_orde"] is True


# --- 3. de uitleg ---------------------------------------------------------


def test_de_uitleg_noemt_wat_het_getal_is(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reason = "default_smart"
    c.last_has_enough_energy = False
    c.last_needed_kwh_to_bridge = 5.87
    c.last_available_kwh = 1.99
    tekst = c._build_explanation()
    assert "dure kwartieren van vandaag" not in tekst
    assert "tot het goedkope blok en de uren daarna" in tekst
    assert "geschat nodig: 5.87 kWh" in tekst


# --- 4. de tweede prijslaag ----------------------------------------------


def test_de_tweede_prijslaag_rekent_met_de_modulesprong():
    bron = inspect.getsource(mod.EnergyManagementSystemCoordinator)
    assert "secondary_available_kwh = self._na_module_leeg(" in bron
