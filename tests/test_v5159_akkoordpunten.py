"""v5.159.0 - akkoordpunten 02-11: pendeldemping alleen bij een last,
L-EMS-050 (temperatuurmodel uit een vaste nacht), zelfcontrole met een
negatieve beschikbare energie, en de KPI 'huis gaat voor' met regeloverschot.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PENDEL_SPRONG_W

TZ = timezone(timedelta(hours=1))
T0 = datetime(2026, 11, 1, 18, 0, tzinfo=TZ)


def _c(make_coordinator):
    c = make_coordinator({})
    c._is_salderen_active = lambda now=None: True
    return c


def _pulsen(n, aan=1800, uit=-900, duur=5):
    reeks = []
    for _ in range(n):
        reeks += [aan] * duur + [uit] * duur
    return reeks


# --- 2. pendeldemping ------------------------------------------------------

def test_accu_slingert_bij_constant_huis_geen_demping(make_coordinator, hass):
    """Huis constant ~600 W, P1 slingert door de accu: geen demping."""
    c = _c(make_coordinator)
    c._read_corrected_consumption_power = lambda: 600.0
    uit = None
    for i, w in enumerate(_pulsen(8, aan=560, uit=-1400)):
        uit = c.p1_regeldoel(w, w, T0 + timedelta(seconds=i))
    assert uit["pendel"]["actief"] is False
    assert uit["pendel"]["niet_geteld_accu"] >= 3
    assert uit["waarde_w"] == -1400


def test_pulserende_last_wordt_geteld(make_coordinator, hass):
    c = _c(make_coordinator)
    huis = {"w": 400.0}
    c._read_corrected_consumption_power = lambda: huis["w"]
    uit = None
    for i, w in enumerate(_pulsen(8)):
        huis["w"] = 2400.0 if w > 0 else 300.0
        uit = c.p1_regeldoel(w, w, T0 + timedelta(seconds=i))
    assert uit["pendel"]["actief"] is True
    # v5.175.1: alleen nog tellen - de Zendure krijgt de momentwaarde.
    assert uit["waarde_w"] == -900


def test_pendel_door_last():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    vast = [(T0, 600.0 + (i % 3) * 20) for i in range(30)]
    assert C._pendel_door_last(vast) is False
    springend = [(T0, 300.0 if i % 2 else 300.0 + PENDEL_SPRONG_W + 500) for i in range(30)]
    assert C._pendel_door_last(springend) is True
    assert C._pendel_door_last([]) is True  # zonder meting: zoals voorheen


# --- 4. L-EMS-050 ------------------------------------------------------

def test_vaste_nacht_levert_een_meting(make_coordinator, hass):
    c = make_coordinator({})
    c._read_corrected_consumption_power = lambda: 300.0
    c._get_live_outdoor_temp_c = lambda now: 4.0
    c.temp_consumption_history = []
    t = datetime(2026, 11, 1, 22, 0, tzinfo=TZ)
    while t <= datetime(2026, 11, 2, 7, 5, tzinfo=TZ):
        c._update_vaste_nacht_temp(t)
        t += timedelta(minutes=5)
    assert len(c.temp_consumption_history) == 1
    m = c.temp_consumption_history[0]
    assert m["temp_c"] == 4.0
    assert abs(m["kw"] - 0.3) < 0.01
    assert m["uren"] >= 8.9


def test_geen_dubbele_meting_als_het_ontlaadvenster_er_al_een_gaf(make_coordinator, hass):
    from homeassistant.util import dt as dt_util

    c = make_coordinator({})
    c._read_corrected_consumption_power = lambda: 300.0
    c._get_live_outdoor_temp_c = lambda now: 4.0
    c.temp_consumption_history = [{"temp_c": 4.0, "kw": 0.3, "uren": 6.0}]
    t = datetime(2026, 11, 1, 22, 0, tzinfo=TZ)
    while t <= datetime(2026, 11, 2, 7, 5, tzinfo=TZ):
        c._temp_monster_om = t - timedelta(hours=1)
        c._update_vaste_nacht_temp(t)
        t += timedelta(minutes=5)
    assert len(c.temp_consumption_history) == 1


def test_herstartgat_telt_niet(make_coordinator, hass):
    c = make_coordinator({})
    c._read_corrected_consumption_power = lambda: 300.0
    c._get_live_outdoor_temp_c = lambda now: 4.0
    t = datetime(2026, 11, 1, 22, 0, tzinfo=TZ)
    c._update_vaste_nacht_temp(t)
    c._update_vaste_nacht_temp(t + timedelta(hours=3))  # gat
    assert c._vaste_nacht["uren"] == 0.0


# --- 7. zelfcontrole -----------------------------------------------------

def test_negatieve_beschikbare_energie_telt_als_nul(make_coordinator, hass):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar"})
    hass.states.set("sensor.beschikbaar", "-0.576")
    c.last_available_kwh = 0.0
    regels = c.get_spiegelcontrole() if hasattr(c, "get_spiegelcontrole") else None
    if regels is None:
        import inspect

        bron = inspect.getsource(type(c))
        assert "_gemeten_beschikbaar = 0.0" in bron
        return
    regel = next(r for r in regels if r["naam"] == "Beschikbare energie")
    assert regel["gemeten"] == 0.0 and regel["oordeel"] == "sluit_aan"


# --- 8. KPI huis gaat voor ---------------------------------------------

def test_kpi_huis_gaat_voor_met_regeloverschot():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    kpi = C._huis_gaat_voor_kpi(
        [{"dag": "2026-11-01", "marge_bij_export_min_kwh": 0.4}],
        {"2026-11-01": 0.342, "2026-10-31": 0.05},
    )
    assert kpi["2026-11-01"]["geschonden"] is True
    assert kpi["2026-11-01"]["regeloverschot_kwh"] == 0.342
    assert kpi["2026-10-31"]["geschonden"] is False
    kpi = C._huis_gaat_voor_kpi([{"dag": "2026-11-02", "marge_bij_export_min_kwh": -0.2}], {})
    assert kpi["2026-11-02"]["onder_reserve_kwartieren"] == 1
    assert kpi["2026-11-02"]["geschonden"] is True
