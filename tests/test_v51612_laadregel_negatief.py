"""v5.161.2 - laadregel met een (licht) negatieve beschikbare energie.

02-11 15:00: de gesimuleerde accu-inhoud in het kwartierplan kwam net onder
de bodem (-0,0x kWh). k = int(beschikbaar // per_kwartier) + 1 werd 0,
later[:0] was leeg en min() viel om: kwartierplan, cockpit, planvolging en
planningsmeldingen rekenden niet meer.
"""
from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 2, 15, 0, tzinfo=TZ)


def _later():
    return sorted(
        ((0.50 - i * 0.01, NU + timedelta(hours=3, minutes=15 * i)) for i in range(8)),
        key=lambda paar: paar[0], reverse=True,
    )


@pytest.mark.parametrize("beschikbaar", [-0.01, -0.39, -1.5])
def test_negatief_valt_niet_om(make_coordinator, hass, beschikbaar):
    c = make_coordinator({})
    uit = c._laadregel(prijs_nu=0.35, beschikbaar=beschikbaar, ruimte=6.0, later=_later(),
                       rendement=83.0, slijtage_ct=4.2, per_kwartier=0.6,
                       zonoverschot=lambda tot: 0.0)
    nul = c._laadregel(prijs_nu=0.35, beschikbaar=0.0, ruimte=6.0, later=_later(),
                       rendement=83.0, slijtage_ct=4.2, per_kwartier=0.6,
                       zonoverschot=lambda tot: 0.0)
    assert uit == nul


def test_negatief_met_zon_vol(make_coordinator, hass):
    c = make_coordinator({})
    uit = c._laadregel(prijs_nu=0.35, beschikbaar=-0.2, ruimte=6.0, later=_later(),
                       rendement=83.0, slijtage_ct=4.2, per_kwartier=0.6,
                       zonoverschot=lambda tot: 0.0, vol_om=NU + timedelta(hours=4))
    assert "laden" in uit
