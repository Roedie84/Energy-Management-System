"""v5.112.1: de kop "Wat doet het EMS nu" zegt wat de accu nu doet.

Gemeld 20-10 20:40 (screenshot): "Accu levert aan woning maar tekst zegt
standaard slim laden".
"""
from pathlib import Path

from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C

JS = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
      / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _c(watt):
    c = object.__new__(C)
    c._read_corrected_battery_power = lambda: watt
    return c


def test_kop_volgt_de_accu():
    assert _c(374.0)._waarom_kop("default_smart") == "Nul op de meter: accu voedt het huis"
    assert _c(-800.0)._waarom_kop("default_smart") == "Nul op de meter: accu laadt op zon"
    assert _c(3.0)._waarom_kop("default_smart") == "Nul op de meter: accu in rust"
    assert _c(None)._waarom_kop("default_smart") == "Nul op de meter"


def test_andere_redenen_houden_hun_titel():
    from custom_components.energy_management_system.const import REASON_REGISTRY

    code = next(k for k, v in REASON_REGISTRY.items() if k != "default_smart" and v.get("titel"))
    assert _c(374.0)._waarom_kop(code) == REASON_REGISTRY[code]["titel"]


def test_cockpit_gebruikt_de_kop():
    assert "waarom.kop ? hoofd(waarom.kop)" in JS


def test_reden_noemt_het_vermogen_van_nu():
    assert _c(374.0)._slim_nu_tekst() == "de accu levert nu 374 W aan het huis"
    assert _c(None)._slim_nu_tekst() == "de accu vangt zon op en voedt het huis"
