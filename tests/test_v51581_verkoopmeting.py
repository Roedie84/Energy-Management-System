"""v5.158.1 (L-EMS-052): verkoop door het waardeplan telt als verkoop.

v5.158.0 voegde `waardeplan_verkopen` toe, maar niet aan `_VERKOOPREDENEN`.
Daardoor zou elke verkoop van het waardeplan als regeloverschot tellen en
leeg blijven in `verkoopkwartieren`, de meting van de harde regel. Alleen
meten; stuurt niets.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import REASON_REGISTRY, OPTION_MANUAL
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 2, 18, 0, 7, tzinfo=TZ)


def _c(make_coordinator, reden, mag=True):
    c = make_coordinator({"update_interval_seconds": 60})
    c.beschikbare_energie_kwh = lambda: 6.05
    c._read_sensor_float = lambda _e: -1850.0
    c._read_corrected_battery_power = lambda: 2400.0
    c._lees_pv_vermogen_w = lambda: 0.0
    c._read_corrected_consumption_power = lambda: 550.0
    c.last_reason = reden
    c.last_sell_check = {"mag_verkopen": mag, "nodig_voor_woning_kwh": 4.0}
    return c


def _regel(c):
    return c.dagverloop[NU.date().isoformat()][-1]


def test_verkoop_van_het_waardeplan_telt_als_verkoop(make_coordinator):
    c = _c(make_coordinator, "waardeplan_verkopen")
    for m in range(8):
        c._leg_dagverloop_vast(NU + timedelta(minutes=m))
    r = _regel(c)
    assert r["verkocht"] is True
    assert r["regeloverschot_kwh"] == 0.0
    assert r["export_uit_accu_kwh"] > 0.2


def test_verkoop_van_het_waardeplan_staat_in_de_harde_regelmeting(make_coordinator):
    c = _c(make_coordinator, "waardeplan_verkopen")
    for m in range(8):
        c._leg_dagverloop_vast(NU + timedelta(minutes=m))
    attr = c.sturing_meetattributen()
    assert attr["verkoopkwartieren"], "verkoop ontbreekt in de meting van de harde regel"


@pytest.mark.parametrize("reden", ["waardeplan_huis", "waardeplan_houden", "waardeplan_laden"])
def test_de_andere_standen_zijn_geen_verkoop(make_coordinator, reden):
    c = _c(make_coordinator, reden)
    for m in range(8):
        c._leg_dagverloop_vast(NU + timedelta(minutes=m))
    r = _regel(c)
    assert r["verkocht"] is False
    assert r["regeloverschot_kwh"] > 0


def test_elke_handmatige_ontlaadreden_met_verkoopuitleg_is_verkoopreden():
    """Vangnet: een nieuwe verkoopreden moet ook de meting in."""
    verkoop = [r for r, g in REASON_REGISTRY.items() if g.get("mode") == OPTION_MANUAL and "verko" in r]
    assert verkoop
    assert all(r in C._VERKOOPREDENEN for r in verkoop)
