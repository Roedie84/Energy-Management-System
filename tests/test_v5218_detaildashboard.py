"""v5.218.0: het detaildashboard wordt door het EMS zelf aangemeld.

Gevonden 11-11: de cockpit linkt naar /energy-management-system/<pagina>,
maar dat dashboard bestond niet in Home Assistant.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import detail_dashboard as dd

MAP = Path(pkg.__file__).parent
BRON = (MAP / "__init__.py").read_text(encoding="utf-8")
COCKPIT = (MAP / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


class _Hass:
    def __init__(self, gegevens):
        self.data = {"lovelace": gegevens} if gegevens is not None else {}


class _Gegevens:
    def __init__(self):
        self.dashboards = {}


def _nep_lovelace(paneel=None):
    aanroepen = []

    def registreer(hass, url_path, mode, config, update):
        aanroepen.append((url_path, mode, dict(config), update))
        if paneel is not None:
            raise paneel

    ll = types.ModuleType("homeassistant.components.lovelace")
    ll._register_panel = registreer
    dash = types.ModuleType("homeassistant.components.lovelace.dashboard")
    dash.LovelaceYAML = lambda hass, url_path, config: ("yaml", url_path, config["filename"])
    ll.dashboard = dash
    comp = sys.modules.get("homeassistant.components") or types.ModuleType("homeassistant.components")
    return aanroepen, {
        "homeassistant.components": comp,
        "homeassistant.components.lovelace": ll,
        "homeassistant.components.lovelace.dashboard": dash,
    }, (comp, ll)


def _draai(hass, paneel=None):
    aanroepen, modules, (comp, ll) = _nep_lovelace(paneel)
    with patch.dict(sys.modules, modules), patch.object(comp, "lovelace", ll, create=True):
        return dd.registreer_detaildashboard(hass, "energy_management_system_dashboard.yaml"), aanroepen


def test_pad_is_het_pad_waar_de_cockpit_naar_linkt():
    assert f'const DETAIL = "/{dd.DETAIL_URL_PAD}/";' in COCKPIT


def test_aangemeld_als_yaml_dashboard_buiten_de_zijbalk():
    gegevens = _Gegevens()
    uitkomst, aanroepen = _draai(_Hass(gegevens))
    assert uitkomst == "aangemeld"
    assert gegevens.dashboards[dd.DETAIL_URL_PAD] == (
        "yaml", dd.DETAIL_URL_PAD, "energy_management_system_dashboard.yaml")
    pad, mode, config, update = aanroepen[0]
    assert (pad, mode, update) == (dd.DETAIL_URL_PAD, "yaml", False)
    assert config["show_in_sidebar"] is False and config["require_admin"] is False
    assert config["title"] and config["icon"].startswith("mdi:")


def test_eigen_dashboard_op_dit_pad_gaat_voor():
    gegevens = _Gegevens()
    gegevens.dashboards[dd.DETAIL_URL_PAD] = "van de gebruiker"
    uitkomst, aanroepen = _draai(_Hass(gegevens))
    assert uitkomst == "bestond al" and not aanroepen
    assert gegevens.dashboards[dd.DETAIL_URL_PAD] == "van de gebruiker"


def test_tweede_keer_doet_niets():
    hass = _Hass(_Gegevens())
    assert _draai(hass)[0] == "aangemeld"
    uitkomst, aanroepen = _draai(hass)
    assert uitkomst == "bestond al" and not aanroepen


def test_paneel_bestond_al_is_geen_fout():
    gegevens = _Gegevens()
    uitkomst, _ = _draai(_Hass(gegevens), paneel=ValueError("Overwriting panel"))
    assert uitkomst == "bestond al" and dd.DETAIL_URL_PAD in gegevens.dashboards


def test_andere_fout_laat_niets_half_achter():
    gegevens = _Gegevens()
    uitkomst, _ = _draai(_Hass(gegevens), paneel=RuntimeError("kapot"))
    assert uitkomst.startswith("niet mogelijk") and dd.DETAIL_URL_PAD not in gegevens.dashboards


def test_zonder_lovelace_geen_fout():
    assert _draai(_Hass(None))[0].startswith("niet mogelijk")


def test_oude_dict_vorm_werkt_ook():
    gegevens = {"dashboards": {}}
    assert _draai(_Hass(gegevens))[0] == "aangemeld"
    assert dd.DETAIL_URL_PAD in gegevens["dashboards"]


def test_aanmelden_na_het_kopieren_en_nooit_blokkerend():
    setup = BRON[BRON.index("async def async_setup_entry"):]
    kopie = setup.index("async_add_executor_job(_copy_dashboard_template, hass)")
    aanmelden = setup.index("registreer_detaildashboard(hass, DASHBOARD_FILENAME)")
    assert kopie < aanmelden
    blok = setup[kopie:aanmelden + 600]
    assert "except Exception as err" in blok


def test_lovelace_staat_in_after_dependencies():
    import json
    manifest = json.loads((MAP / "manifest.json").read_text(encoding="utf-8"))
    assert "lovelace" in manifest["after_dependencies"]
