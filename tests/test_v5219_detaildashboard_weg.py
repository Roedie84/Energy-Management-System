"""v5.219.0: de detailpagina's zijn vervallen.

Ruud 11-11 15:09 ("1, 2 en 3 akkoord"): het detaildashboard gaat eruit, de
cockpit linkt nergens meer heen en de oude kopie in de configuratiemap wordt
opgeruimd.
"""

from pathlib import Path
from types import SimpleNamespace

import custom_components.energy_management_system as pkg

MAP = Path(pkg.__file__).parent
REPO = MAP.parent.parent
BRON = (MAP / "__init__.py").read_text(encoding="utf-8")
COCKPIT = (MAP / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _hass(map_):
    return SimpleNamespace(config=SimpleNamespace(path=lambda naam: str(Path(map_) / naam)))


def test_de_bestanden_zijn_weg():
    for pad in (
        MAP / "dashboard_template.yaml",
        MAP / "detail_dashboard.py",
        MAP / "dashboard_opmaak.py",
        REPO / "dashboards" / "energy_management_system_dashboard.yaml",
    ):
        assert not pad.exists(), pad


def test_de_opstart_kopieert_en_meldt_niets_meer_aan():
    assert "_copy_dashboard_template" not in BRON
    assert "registreer_detaildashboard" not in BRON
    assert BRON.count("async_add_executor_job(_verwijder_oude_dashboardkopie, hass)") == 1


def test_oude_kopie_wordt_opgeruimd(tmp_path):
    oud = tmp_path / pkg.DASHBOARD_FILENAME
    oud.write_text("views: []\n", encoding="utf-8")
    ander = tmp_path / "configuration.yaml"
    ander.write_text("x: 1\n", encoding="utf-8")
    pkg._verwijder_oude_dashboardkopie(_hass(tmp_path))
    assert not oud.exists() and ander.exists()


def test_geen_kopie_is_geen_fout(tmp_path):
    pkg._verwijder_oude_dashboardkopie(_hass(tmp_path))
    pkg._verwijder_oude_dashboardkopie(_hass(tmp_path / "bestaat_niet"))


def test_een_map_met_die_naam_blijft_staan(tmp_path):
    (tmp_path / pkg.DASHBOARD_FILENAME).mkdir()
    pkg._verwijder_oude_dashboardkopie(_hass(tmp_path))
    assert (tmp_path / pkg.DASHBOARD_FILENAME).is_dir()


def test_de_cockpit_linkt_nergens_meer_heen():
    for weg in ("data-nav", "/energy-management-system", "detail-", "_ga(", 'class="meer"', 'class="links"'):
        assert weg not in COCKPIT, weg
    # de voet toont nog wel versie, fouten en storingen
    assert 'class="voetregel"' in COCKPIT


def test_de_dashboardcontrole_meldt_niet_beschikbaar():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    uit = C.get_dashboard_health(SimpleNamespace())
    assert uit["beschikbaar"] is False and "vervallen" in uit["reden"]
    assert not uit.get("niet_bestaande_entiteiten")
