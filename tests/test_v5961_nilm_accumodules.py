"""v5.96.1: accumodules (AB3000) zijn nooit een NILM-kandidaat."""
from custom_components.energy_management_system.const import NILM_PATTERN_EXCLUDED_KEYWORDS
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C


def test_nieuwe_ab3000_uitgesloten():
    assert C._is_nilm_pattern_excluded("sensor.ab3000_01029_power", "AB3000 01029 Power")


def test_hernoemde_module_uitgesloten():
    assert C._is_nilm_pattern_excluded("sensor.x_power", "Accu module 1 Power")


def test_gewoon_apparaat_niet_uitgesloten():
    assert not C._is_nilm_pattern_excluded("sensor.wasmachine_vermogen", "Wasmachine vermogen")


def test_sleutelwoorden():
    assert "ab3000" in NILM_PATTERN_EXCLUDED_KEYWORDS and "accu module" in NILM_PATTERN_EXCLUDED_KEYWORDS
