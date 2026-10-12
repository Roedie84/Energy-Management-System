"""De reden bij 'zon opvangen uitstellen: nee' noemt zijn getallen (v5.91.1).

Gemeld met een schermafdruk: "Nog 12,4 kWh vandaag" naast "Te weinig zon
verwacht om 5,6 kWh voor 16:00 nog veilig op te vangen". Beide klopten, maar
de reden zei niet waarmee hij rekende.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


def test_de_getallen_staan_erbij():
    start = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)

    tekst = C._zonuitstel_te_weinig(5.6, (start, 7.3, 2.7, 4.6, 7.7))

    assert "tussen 10:00 en 16:00" in tekst
    assert "7.3 kWh zon" in tekst
    assert "4.6 kWh om op te vangen" in tekst
    assert "7.7 kWh nodig" in tekst


def test_zonder_getoetst_venster_de_korte_zin():
    assert C._zonuitstel_te_weinig(5.6, None).endswith("op te vangen.")
