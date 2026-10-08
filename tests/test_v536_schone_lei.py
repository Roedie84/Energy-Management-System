"""Opstartfase in de cockpit, materiële moduledrift en Monte Carlo (v5.36).

Gemeten op 7 oktober:
- de cockpit stond 10:49:24-10:50:26 op STORING direct na een herstart;
- AB3000 00996 "liep uit de pas" met een celdelta van 0,01-0,03 V;
- 4 tekortdagen in 7 dagen naast een Monte-Carlo-tekortkans van 0,0.
"""
from datetime import timedelta

from homeassistant.util import dt as dt_util
from test_cockpit_matrix import _gezond

from custom_components.energy_management_system.const import (
    BATTERY_MODULE_CELL_DELTA_MATERIEEL_V,
    KOPPELING_HAPERT_S,
    STARTUP_GRACE_SECONDS,
)
from custom_components.energy_management_system.coordinator import koppeling_hapert


# --- opstartfase ------------------------------------------------------------


def test_tijdens_het_opstarten_geen_storing(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    c.last_successful_update = None          # eerste ronde nog niet gelukt
    c._started_at = dt_util.now() - timedelta(seconds=30)

    stand, reden = c._ems_status()

    assert stand == "LET OP"
    assert "opstarten" in reden


def test_na_het_opstarten_telt_een_mislukte_ronde_weer(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    c.last_successful_update = None
    c._started_at = dt_util.now() - timedelta(seconds=STARTUP_GRACE_SECONDS + 5)

    assert c._ems_status()[0] == "STORING"


def test_alleen_een_koppeling_zonder_waarde_kan_haperen():
    assert koppeling_hapert({"oordeel": "geen_waarde", "geen_waarde_s": 20})
    assert not koppeling_hapert(
        {"oordeel": "geen_waarde", "geen_waarde_s": KOPPELING_HAPERT_S + 1}
    )
    # niet bestaan is meestal een hernoeming: telt meteen
    assert not koppeling_hapert({"oordeel": "bestaat_niet", "bestaat_niet_s": 5})


def test_de_controle_telt_haperende_koppelingen_apart(make_coordinator, hass):
    c = make_coordinator({})
    controle = c.get_configuratiecontrole()

    assert "aantal_hapert" in controle
    assert controle["aantal_stuk"] == sum(
        1
        for r in controle["entiteiten"]
        if r["oordeel"] not in ("in_orde", "slaapt") and not koppeling_hapert(r)
    )


# --- moduledrift -----------------------------------------------------------


def _staat_met_drift():
    return {
        "cusum": {"cel_delta_afwijking_v": {"drift": True}},
        "geschiedenis": {"cel_delta_v": [0.03, 0.02, 0.01]},
    }


def test_een_paar_millivolt_is_geen_drift(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = [{"module": 1, "cel_delta_v": 0.01}]

    assert c._module_drift_velden("1", _staat_met_drift()) == []


def test_een_materieel_verschil_blijft_drift(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = [
        {"module": 1, "cel_delta_v": BATTERY_MODULE_CELL_DELTA_MATERIEEL_V + 0.01}
    ]

    assert c._module_drift_velden("1", _staat_met_drift()) == ["cel_delta_afwijking_v"]


def test_andere_driftvelden_blijven_staan(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = [{"module": 1, "cel_delta_v": 0.0}]
    staat = {"cusum": {"temperatuur_afwijking_c": {"drift": True}}}

    assert c._module_drift_velden("1", staat) == ["temperatuur_afwijking_c"]


# --- Monte Carlo naast de tekortdagen --------------------------------------


def test_de_vergelijking_legt_beide_bases_uit(make_coordinator, hass):
    c = make_coordinator({})
    c.reserve_daily_records = [{"shortfall": s} for s in (True, False, True, True, False, True, False)]

    v = c.get_monte_carlo_vergelijking()

    assert v["tekortdagen_laatste_7"] == 4
    assert v["werkelijke_tekortfrequentie_procent"] == round(100 * 4 / 7, 1)
    assert "goedkoopste blok" in v["basis"]
    assert "22:00-09:00" in v["tekortdag_basis"]


def test_de_tekortkans_gebruikt_de_drempel_van_een_tekortdag():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    # v5.47: de grens staat nu op één plek voor beide kansen.
    i = bron.index("grens = available_kwh + ")
    assert "SHORTFALL_MIN_NETIMPORT_KWH" in bron[i : i + 300]
