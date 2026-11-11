"""Zelfvoorziening: welk deel van het verbruik dekte de eigen zon? (v5.222.0)

Geschiedenis. v3.16.0: "-103.2% Zelfvoorziening" doordat netlading als
huisverbruik telde. v3.23.1: "-54%" doordat de netladingsteller kon
ontbreken. Beide reparaties hielden de definitie "alles wat niet rechtstreeks
van het net kwam". Met een accu die op prijs uit het net laadt is dat niet
wat de naam belooft: op 11-11-2026 stond er 60 % terwijl de zon 24 % van het
verbruik dekte, en de perioden gaven met een andere formule 21 %.

Sinds v5.222.0 een definitie, voor vandaag en voor elke periode: de zon die
niet het net op ging, gedeeld door het verbruik, tussen 0 en 100.
"""
from tests._coordinator_bron import coordinator_bron


def _c(make_coordinator, verbruik, opwek, zon_export=0.0, importeren=0.0, netlading=0.0):
    c = make_coordinator({})
    c.gross_consumption_today_kwh = verbruik
    c.pv_production_today_kwh = opwek
    c.pv_export_today_kwh = zon_export
    c.solar_export_today_kwh = zon_export
    c.battery_discharge_today_kwh = 0.0
    c.grid_import_today_kwh = importeren
    c.grid_charge_today_kwh = netlading
    return c


def test_de_dag_van_de_melding(make_coordinator, hass):
    """11-11: 6,77 kWh verbruik, 2,03 kWh zon waarvan 0,38 het net op,
    en een accu die 's ochtends uit het net laadde."""
    c = _c(make_coordinator, verbruik=6.77, opwek=2.03, zon_export=0.38, importeren=11.95, netlading=9.15)
    assert c.self_sufficiency_ratio_percent == 24.4


def test_netlading_telt_niet_als_eigen(make_coordinator, hass):
    """Wat de accu uit het net laadde en later aan het huis levert is geen
    eigen opwek, hoeveel het ook is."""
    zonder = _c(make_coordinator, 10.0, 3.0, importeren=7.0).self_sufficiency_ratio_percent
    met = _c(make_coordinator, 10.0, 3.0, importeren=12.0, netlading=5.0).self_sufficiency_ratio_percent
    assert zonder == met == 30.0


def test_altijd_tussen_nul_en_honderd(make_coordinator, hass):
    assert _c(make_coordinator, 2.87, 0.0, importeren=5.88, netlading=3.6).self_sufficiency_ratio_percent == 0.0
    assert _c(make_coordinator, 3.91, 0.0, importeren=5.93).self_sufficiency_ratio_percent == 0.0
    assert _c(make_coordinator, 4.0, 9.0).self_sufficiency_ratio_percent == 100.0
    assert _c(make_coordinator, 4.0, 9.0, zon_export=12.0).self_sufficiency_ratio_percent == 0.0


def test_zonder_verbruik_geen_cijfer(make_coordinator, hass):
    assert _c(make_coordinator, 0.0, 5.0).self_sufficiency_ratio_percent is None


def test_een_ontbrekende_teller_valt_niet_om(make_coordinator, hass):
    c = _c(make_coordinator, verbruik=4.0, opwek=2.0)
    c.grid_charge_today_kwh = None
    assert c.self_sufficiency_ratio_percent == 50.0


def test_vandaag_en_de_perioden_rekenen_hetzelfde(make_coordinator, hass):
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    c = _c(make_coordinator, verbruik=10.0, opwek=6.0, zon_export=2.0)
    assert c.self_sufficiency_ratio_percent == C._zelfvoorziening_uit_zon(6.0, 2.0, 10.0) == 40.0


def test_de_netladingsteller_blijft_bestaan():
    """Andere onderdelen rekenen ermee; hij rolt om middernacht en overleeft een herstart."""
    from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS

    bron = coordinator_bron()
    kop = bron.index("self.grid_import_today_kwh = 0.0")
    assert "self.grid_charge_today_kwh = 0.0" in bron[kop : kop + 200]
    assert "grid_charge_today_kwh" in PERSISTED_PLAIN_FIELDS


def test_de_zelfcontrole_past_bij_de_nieuwe_definitie():
    """De narekening met import min netlading hoorde bij de oude definitie
    en zou nu elke dag een fout melden."""
    bron = coordinator_bron()
    kop = bron.index("# --- 1. Zelfvoorziening kan niet boven de eigen zon uitkomen ---")
    blok = bron[kop : kop + 1100]
    assert "plafond" in blok and "grid_charge_today_kwh" not in blok
