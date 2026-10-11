"""Nachtladen alleen als het meer oplevert dan de zon die het verdringt (v5.86, L-EMS-021).

Gemeld op 11 oktober: "Waarom manueel laden vannacht? Is toch niet gezien
de zonvoorspelling morgen?" Het plan laadde 02:30-04:30 van 47 naar 100 %
tegen ~33 ct om om 08:00 te verkopen tegen 47 ct. De accu was om 11:30
toch vol van de zon; het middagoverschot ging tegen 30-32 ct het net op.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator,
)

T0 = datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)


def _om(uur: int, minuut: int = 0) -> datetime:
    return T0 + timedelta(hours=uur, minutes=minuut)


# Ochtend (vóór de zon de accu vult) en avond (erna), als in de planning van 11-10.
OCHTEND = [
    (0.479, _om(8)), (0.465, _om(8, 15)), (0.457, _om(7, 45)), (0.449, _om(7, 30)),
    (0.449, _om(9)), (0.442, _om(7, 15)), (0.438, _om(8, 30)), (0.422, _om(6, 45)),
]
AVOND = [
    (0.484, _om(18, 45)), (0.474, _om(19)), (0.472, _om(19, 15)), (0.470, _om(19, 30)),
    (0.466, _om(18, 30)), (0.461, _om(20)), (0.460, _om(19, 45)),
]
MIDDAG = [(0.330, _om(11, 30)), (0.326, _om(11, 45))]
LATER = sorted(OCHTEND + AVOND + MIDDAG, key=lambda paar: paar[0], reverse=True)
VOL_OM = _om(11, 30)


def _regel(*, prijs_nu=0.331, beschikbaar=4.0, vol_om=VOL_OM, overschot=0.0):
    return EnergyManagementSystemCoordinator._laadregel(
        prijs_nu=prijs_nu,
        beschikbaar=beschikbaar,
        ruimte=4.6,
        later=LATER,
        rendement=84.0,
        slijtage_ct=5.0,
        per_kwartier=0.6,
        zonoverschot=lambda tot: overschot,
        vol_om=vol_om,
    )


def test_zonder_vol_moment_het_oude_besluit():
    """Zonder vol-moment telt de avond mee: 46,5 x 84% - 5 = 34,1 ct > 33,1."""
    assert _regel(vol_om=None)["laden"] is True


def test_11_oktober_niet_meer_laden():
    """De avond levert de zon. Van de ochtend dekt de lading al zes
    kwartieren; de volgende kWh gaat in 43,8 ct: 31,8 ct waard < 33,1."""
    besluit = _regel()
    assert besluit["laden"] is False
    assert besluit["latere_prijs_eur"] == pytest.approx(0.438)


def test_lading_die_tot_het_vol_moment_blijft_verdringt_zon():
    """Dekt de lading alle ochtendkwartieren, dan verdringt de volgende kWh
    zon die voor 33,0 ct het net op gaat - geen winst tegen 33,1 ct."""
    besluit = _regel(beschikbaar=6.0)
    assert besluit["laden"] is False
    assert besluit["verdringt_zon"] is True
    assert besluit["exportprijs_eur"] == pytest.approx(0.330)
    assert "zon" in besluit["reden"]


def test_heel_goedkope_nacht_loont_ook_als_het_zon_verdringt():
    """15 ct nu, de verdrongen zon brengt 33 ct op: dan loont het wel."""
    besluit = _regel(beschikbaar=6.0, prijs_nu=0.15)
    assert besluit["laden"] is True
    assert besluit["marge_ct"] == pytest.approx(18.0, abs=0.1)


def test_vol_moment_uit_verbruik_en_zon(make_coordinator, hass):
    """Ruimte 3 kWh om 00:00; 's nachts 0,5 kWh/u verbruik, vanaf 09:00
    1,5 kWh/u zon boven het verbruik. 9 uur x 0,5 = 4,5 erbij -> 7,5 vrij
    (capaciteit 8); vol na 5 uur zon: 14:00."""
    c = make_coordinator({})
    eind = _om(24)

    def segmenten(start, end, veilig=True):
        assert veilig is True
        uit = []
        cursor = start
        while cursor < end:
            uit.append((0.5, 0.0) if cursor.hour < 9 else (0.5, 2.0))
            cursor += timedelta(hours=1)
        return uit

    c._segmenten_verbruik_zon = segmenten
    assert c._zon_vol_om(T0, 5.0, 3.0, eind) == _om(14)


def test_geen_vol_moment_zonder_zon(make_coordinator, hass):
    c = make_coordinator({})
    c._segmenten_verbruik_zon = lambda a, b, veilig=True: [(0.5, 0.0)] * 24
    assert c._zon_vol_om(T0, 5.0, 3.0, _om(24)) is None


def test_geen_vol_moment_zonder_verbruiksprofiel(make_coordinator, hass):
    c = make_coordinator({})
    c._segmenten_verbruik_zon = lambda a, b, veilig=True: None
    assert c._zon_vol_om(T0, 5.0, 3.0, _om(24)) is None


def test_waarom_bij_verdrongen_zon(make_coordinator, hass):
    c = make_coordinator({})
    c.last_laadbesluit = _regel(beschikbaar=6.0, prijs_nu=0.15)
    regels = c._waarom_bij_laden("grid_charging_profitable", [], None)
    assert any("het net op" in r for r in regels)
