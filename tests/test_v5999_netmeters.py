"""v5.99.9: afname/teruglevering uit de P1-meterstanden (controle 17-10)."""
from datetime import datetime, timezone
from types import SimpleNamespace

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)
from custom_components.energy_management_system.const import (
    CONF_GRID_EXPORT_ENERGY_SENSOR, CONF_GRID_IMPORT_ENERGY_SENSOR,
)

NU = datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)


def _z(imp, exp, **kw):
    meters = {"sensor.imp": imp, "sensor.exp": exp}
    z = SimpleNamespace(
        config={CONF_GRID_IMPORT_ENERGY_SENSOR: "sensor.imp", CONF_GRID_EXPORT_ENERGY_SENSOR: "sensor.exp"},
        netmeterdag={}, grid_import_today_kwh=1.0, pv_export_today_kwh=2.0,
        solar_export_today_kwh=1.5, battery_export_today_kwh=0.5,
        gross_consumption_today_kwh=5.0, **kw)
    z._read_sensor_float = lambda e: meters.get(e)
    z._meters = meters
    z._noteer_accu_tellers = lambda dag: None
    return z


def test_eerste_keer_geen_sprong_daarna_meter():
    z = _z(100.0, 50.0)
    C._ijk_netmeters(z, NU)
    assert z.grid_import_today_kwh == 1.0 and z.pv_export_today_kwh == 2.0
    # integratie mist 0,3 kWh afname; de meter niet
    z._meters["sensor.imp"] = 100.8
    z._meters["sensor.exp"] = 50.4
    z.grid_import_today_kwh += 0.5
    z.pv_export_today_kwh += 0.4
    z.solar_export_today_kwh += 0.4
    z.gross_consumption_today_kwh += 0.1
    C._ijk_netmeters(z, NU)
    assert z.grid_import_today_kwh == 1.8
    assert z.pv_export_today_kwh == 2.4
    assert round(z.gross_consumption_today_kwh, 3) == 5.4  # +0,3 afname


def test_herstart_houdt_dagbegin():
    z = _z(100.0, 50.0)
    C._ijk_netmeters(z, NU)
    bewaard = z.netmeterdag
    z2 = _z(103.0, 51.0, )
    z2.netmeterdag = bewaard
    z2.grid_import_today_kwh = 0.0  # na herstart integratie op nul
    z2.pv_export_today_kwh = 0.0
    C._ijk_netmeters(z2, NU)
    assert z2.grid_import_today_kwh == 4.0
    assert z2.pv_export_today_kwh == 3.0


def test_nieuwe_dag_begint_op_laatste_stand():
    z = _z(100.0, 50.0)
    C._ijk_netmeters(z, NU)
    z._meters["sensor.imp"] = 101.0
    C._ijk_netmeters(z, NU)
    # middernacht: tellers op nul gezet door de dagwissel
    z.grid_import_today_kwh = z.pv_export_today_kwh = 0.0
    z._meters["sensor.imp"] = 101.2
    C._ijk_netmeters(z, NU.replace(day=18))
    assert z.grid_import_today_kwh == 0.2


def test_zonder_meter_blijft_integratie():
    z = _z(None, None)
    C._ijk_netmeters(z, NU)
    assert z.grid_import_today_kwh == 1.0 and z.pv_export_today_kwh == 2.0


def test_prijzen_per_uur_in_euro():
    from custom_components.energy_management_system import slimme_bronnen
    from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR
    uit = slimme_bronnen.prijzen_per_uur([(NU, 3755765 / PRICE_SCALE_FACTOR)], None)
    assert uit[10]["eur_per_kwh"] == 0.3756
