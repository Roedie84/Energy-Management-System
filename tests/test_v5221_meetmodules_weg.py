"""v5.221.0: MPC, Kalman, digitale tweeling, smart-charging-proef en de tekeningen zijn weg.

Ruud 11-11 16:10 ("10 en 11 oppakken"). Ze dateerden van voor het waardeplan,
stuurden niets en stonden niet in de cockpit.
"""

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import const, diagnostics, sensor as S
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

MAP = Path(pkg.__file__).parent
REPO = MAP.parent.parent


@pytest.mark.parametrize("pad", [
    MAP / "overview_svg.py", MAP / "overview_background.svg",
    REPO / "dashboards" / "energy_management_system_overview.svg",
])
def test_de_tekenbestanden_zijn_weg(pad):
    assert not pad.exists()


@pytest.mark.parametrize("methode", [
    "_compute_mpc_plan", "_meet_mpc", "_kandidaat_mpc", "_update_kalman_filters",
    "_run_digital_twin_simulation", "get_digital_twin_accuracy_status", "get_smart_charging_proefplanning",
    "get_cockpit_svg", "get_overview_svg", "get_overview_status_svg", "get_overview_sections_svg",
])
def test_de_methode_bestaat_niet_meer(methode):
    assert not hasattr(C, methode)


@pytest.mark.parametrize("klasse", [
    "MpcAdvisorySensor", "KalmanFilterAdvisorySensor", "DigitalTwinAdvisorySensor", "DigitalTwinAccuracySensor",
])
def test_de_sensor_bestaat_niet_meer(klasse):
    assert not hasattr(S, klasse)


def test_hun_registratie_wordt_opgeruimd():
    for sleutel in ("mpc_advisory", "kalman_filtering", "digital_twin", "digital_twin_accuracy", "smart_charging_proef"):
        assert sleutel in S.VERVALLEN_SENSOREN
    assert "smart_charging_proef" not in {p[0] for p in S.DASHBOARD_PAGINA_SENSOREN}


def test_wat_de_cockpit_en_de_dagcontrole_lezen_blijft():
    for klasse in ("MonteCarloAdvisorySensor", "AdvisoryReadinessSensor", "GacsAssessmentSensor", "CockpitSensor"):
        assert hasattr(S, klasse), klasse
    for sleutel in ("kwartierplanning_tabel", "perioden", "plantoetsing"):  # v5.223.0: proefstand ook weg
        assert sleutel in {p[0] for p in S.DASHBOARD_PAGINA_SENSOREN}
    assert hasattr(C, "_run_monte_carlo_simulation") and hasattr(C, "_twin_laadfactor")


def test_de_ronde_roept_ze_niet_meer_aan():
    bron = inspect.getsource(C._adviesstappen_voor_besluit) + inspect.getsource(C._adviesstappen_na_tijdlijn)
    for weg in ("mpc", "kalman", "digital_twin"):
        assert weg not in bron, weg
    assert "_monte_carlo_op_tijd" in bron and "_update_advisory_readiness" in bron


def test_gereedheid_noemt_de_vervallen_modules_niet():
    bron = inspect.getsource(C._update_advisory_readiness)
    for weg in ('readiness["mpc"]', 'readiness["kalman"]', 'readiness["digital_twin"]'):
        assert weg not in bron
    for blijft in ('readiness["kirchhoff"]', 'readiness["monte_carlo"]', 'readiness["nilm"]'):
        assert blijft in bron


def test_geen_bewaarde_velden_en_constanten_meer():
    for veld in ("mpc_vergelijking_history", "kalman_divergence_history", "digital_twin_accuracy_history"):
        assert veld not in const.PERSISTED_FIELDS
    namen = [n for n in dir(const) if n.startswith(("MPC_", "KALMAN_", "DIGITAL_TWIN_"))]
    assert namen == [] or len(namen) <= 1, namen


def test_de_diagnose_vraagt_niets_op_dat_weg_is():
    bron = inspect.getsource(diagnostics)
    for weg in ("mpc_", "kalman_", "digital_twin", "smart_charging_proef"):
        assert weg not in bron, weg


def test_de_opstart_kopieert_geen_tekening_meer_en_ruimt_de_oude_op(tmp_path):
    bron = (MAP / "__init__.py").read_text(encoding="utf-8")
    assert "_copy_overview_background" not in bron and "import shutil" not in bron
    (tmp_path / "www").mkdir()
    oud = tmp_path / pkg.OUDE_ACHTERGROND_PAD
    oud.write_text("<svg/>", encoding="utf-8")
    ander = tmp_path / "www" / "iets_anders.svg"
    ander.write_text("<svg/>", encoding="utf-8")
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda naam: str(tmp_path / naam)))
    pkg._verwijder_oude_dashboardkopie(hass)
    assert not oud.exists() and ander.exists()
