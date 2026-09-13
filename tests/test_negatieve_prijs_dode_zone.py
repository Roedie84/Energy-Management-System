"""Negatieve prijs met een dode zone (v4.10).

Uit de logica-audit, `coordinator.py:34182`:

    is_negative_price = current_price_per_kwh is not None and current_price_per_kwh < 0

Een kale grens op nul. Bij een prijs die rond nul hangt - precies wat er
gebeurt aan het begin en het eind van een negatieve periode - klapt de
accu tussen laden op 2000 W en de gewone sturing. Anders dan bij de vijf
schakelparen van v3.99.4 en v3.99.14 zat hier geen rem op: geen marge,
geen minimumtijd.

Erger dan die vijf, om twee redenen. Het gaat om VOL VERMOGEN in plaats
van een stand, en bij elke omslag wordt `_start_solar_ramp()` opnieuw
aangeroepen.

Nu: aan onder -0,5 ct, uit pas boven +0,5 ct, en minstens een kwartier
aan - dezelfde vorm als de verkooptoets.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _prijs(c, ct, nu=NU):
    return c._is_negatieve_prijs(ct / 100, nu)


def test_ruim_negatief_gaat_aan(make_coordinator, hass):
    c = make_coordinator({})
    assert _prijs(c, -2.0) is True


def test_net_onder_nul_gaat_niet_aan(make_coordinator, hass):
    """-0,2 ct is geen negatieve prijs om 2 kW voor aan te zetten."""
    c = make_coordinator({})
    assert _prijs(c, -0.2) is False


def test_eenmaal_aan_blijft_het_bij_een_kleine_stijging(make_coordinator, hass):
    c = make_coordinator({})
    _prijs(c, -2.0)
    assert _prijs(c, 0.2, NU + timedelta(minutes=30)) is True


def test_ruim_boven_nul_gaat_het_uit(make_coordinator, hass):
    c = make_coordinator({})
    _prijs(c, -2.0)
    assert _prijs(c, 1.0, NU + timedelta(minutes=30)) is False


def test_minstens_een_kwartier_aan(make_coordinator, hass):
    """Een prijs die na vijf minuten omhoog schiet, mag de accu niet
    meteen weer laten stoppen."""
    c = make_coordinator({})
    _prijs(c, -2.0)
    assert _prijs(c, 5.0, NU + timedelta(minutes=5)) is True
    assert _prijs(c, 5.0, NU + timedelta(minutes=16)) is False


def test_zonder_prijs_geen_lading(make_coordinator, hass):
    c = make_coordinator({})
    assert c._is_negatieve_prijs(None, NU) is False


def test_de_beslisboom_gebruikt_de_dode_zone():
    """De ratel: nergens meer een kale vergelijking met nul."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "_is_negatieve_prijs(" in bron
    assert not re.search(r"is_negative_price = \(\s*current_price_per_kwh is not None and current_price_per_kwh < 0", bron)
