"""v5.99.11: de lange-horizonreserve springt niet meer per minuut."""
from datetime import datetime, timezone
from types import SimpleNamespace

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

T = datetime(2026, 10, 17, 21, 16, tzinfo=timezone.utc)


def test_kleine_schommeling_binnen_kwartier_blijft_staan():
    z = SimpleNamespace(_lange_reserve_extra_kwh=None)
    z._lange_reserve_extra_kwh = C._rustige_lange_reserve(z, 8.0, T)
    assert C._rustige_lange_reserve(z, 8.3, T.replace(minute=17)) == 8.0
    assert C._rustige_lange_reserve(z, 7.7, T.replace(minute=29)) == 8.0


def test_groot_verschil_meteen():
    z = SimpleNamespace(_lange_reserve_extra_kwh=None)
    z._lange_reserve_extra_kwh = C._rustige_lange_reserve(z, 8.0, T)
    assert C._rustige_lange_reserve(z, 9.6, T.replace(minute=18)) == 9.6


def test_nieuw_kwartier_neemt_over():
    z = SimpleNamespace(_lange_reserve_extra_kwh=None)
    z._lange_reserve_extra_kwh = C._rustige_lange_reserve(z, 8.0, T)
    assert C._rustige_lange_reserve(z, 8.2, T.replace(minute=30)) == 8.2
