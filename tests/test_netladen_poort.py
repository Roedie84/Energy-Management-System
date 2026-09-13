"""Netladen binnen het goedkope blok, met een poort (v4.10).

Uit de logica-audit, `coordinator.py:34131`:

    should_force_charge = in_cheap_block and is_low_solar

`is_low_solar` hangt aan de zonvoorspelling EN aan een geleerde drempel
die met de spreiding van de voorspelling meebeweegt. Binnen een goedkoop
blok van acht uur kan die kantelen - en dan stopt het laden op 2000 W
midden in het blok en begint het later weer. Twee, drie omslagen per
blok zijn mogelijk.

`_grid_charged_today` werd wel gezet maar niet als poort gebruikt. Nu
wel: eenmaal begonnen binnen een blok, blijft het laden tot het blok
voorbij is of de accu vol. Een besluit dat een half uur geldt, is geen
besluit.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
BLOK = (NU - timedelta(hours=1), NU + timedelta(hours=7))


def _laden(c, weinig_zon, nu=NU, blok=BLOK):
    c._is_low_solar_expected = lambda: weinig_zon
    return c._moet_uit_het_net_laden(nu, blok[0], blok[1])


def test_weinig_zon_in_het_blok_laadt(make_coordinator, hass):
    c = make_coordinator({})
    assert _laden(c, True) is True


def test_genoeg_zon_laadt_niet(make_coordinator, hass):
    c = make_coordinator({})
    assert _laden(c, False) is False


def test_eenmaal_begonnen_blijft_het_laden(make_coordinator, hass):
    """De drempel kantelt halverwege het blok; het laden niet."""
    c = make_coordinator({})
    _laden(c, True)

    assert _laden(c, False, nu=NU + timedelta(hours=2)) is True


def test_na_het_blok_stopt_het(make_coordinator, hass):
    c = make_coordinator({})
    _laden(c, True)

    assert _laden(c, True, nu=NU + timedelta(hours=8)) is False


def test_een_nieuw_blok_beslist_opnieuw(make_coordinator, hass):
    c = make_coordinator({})
    _laden(c, True)
    later = NU + timedelta(hours=12)

    assert _laden(c, False, nu=later, blok=(later, later + timedelta(hours=4))) is False


def test_buiten_een_blok_nooit(make_coordinator, hass):
    c = make_coordinator({})
    assert _laden(c, True, nu=NU, blok=(NU + timedelta(hours=3), NU + timedelta(hours=6))) is False
