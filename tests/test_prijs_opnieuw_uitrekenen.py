"""De prijs wordt opnieuw uitgerekend, niet onthouden (v3.51.0).

Bij het nalopen van alle gespiegelde velden bleek
`last_current_price_per_kwh` de grootste van de drie: tien lezers, en
geen enkele controle op zijn leeftijd.

Bij de accustand en de beschikbare energie was een leeftijdsgrens het
antwoord, want die komen uit een sensor die kan haperen. De prijs niet:
die volgt uit de prijsreeks en de klok, en is dus altijd opnieuw uit te
rekenen. Onthouden is hier helemaal niet nodig.

En het verschil is groot. Prijzen springen op de kwartiergrens - op 26
augustus van 37,5 naar 22,0 cent binnen één kwartier. Blijft het veld
staan omdat een ronde eerder eindigde, dan rekenen tien plekken met een
prijs die anderhalf uur oud kan zijn.
"""
from datetime import datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util

NU = datetime(2026, 8, 27, 20, 40)


def _reeks(c, prijzen):
    """Een prijsreeks van kwartieren vanaf 20:00."""
    from custom_components.energy_management_system.const import (
        PRICE_SCALE_FACTOR,
    )

    begin = NU.replace(hour=20, minute=0, second=0, microsecond=0)
    c._get_forecast_entries = lambda **kw: [
        (
            begin + timedelta(minutes=15 * i),
            begin + timedelta(minutes=15 * (i + 1)),
            p * PRICE_SCALE_FACTOR,
        )
        for i, p in enumerate(prijzen)
    ]
    return c


def test_the_price_comes_from_the_clock(make_coordinator, hass):
    """20:40 valt in het derde kwartier: 0,220."""
    c = _reeks(make_coordinator({}), [0.375, 0.310, 0.220, 0.180])

    assert c.huidige_prijs_eur_per_kwh(NU) == pytest.approx(0.220)


def test_a_stale_field_does_not_win(make_coordinator, hass):
    """De kern: het onthouden getal is van het eerste kwartier, en dat

    geldt niet meer.
    """
    c = _reeks(make_coordinator({}), [0.375, 0.310, 0.220, 0.180])
    c.last_current_price_per_kwh = 0.375
    c.meting_tijdstippen["last_current_price_per_kwh"] = NU

    assert c.huidige_prijs_eur_per_kwh(NU) == pytest.approx(0.220)


def test_the_quarter_boundary_is_respected(make_coordinator, hass):
    """De sprong van 26 augustus: 37,5 naar 22,0 cent."""
    c = _reeks(make_coordinator({}), [0.375, 0.220])
    begin = NU.replace(hour=20, minute=0)

    assert c.huidige_prijs_eur_per_kwh(begin + timedelta(minutes=14)) == (
        pytest.approx(0.375)
    )
    assert c.huidige_prijs_eur_per_kwh(begin + timedelta(minutes=16)) == (
        pytest.approx(0.220)
    )


# --- de terugval -----------------------------------------------------


def test_without_prices_a_fresh_field_is_used(make_coordinator, hass):
    """Zonder prijsgegevens valt er niets uit te rekenen; dan geldt

    dezelfde regel als bij de andere twee velden.
    """
    c = make_coordinator({})
    c._get_forecast_entries = lambda **kw: []
    c.last_current_price_per_kwh = 0.310
    c.meting_tijdstippen["last_current_price_per_kwh"] = dt_util.now()

    assert c.huidige_prijs_eur_per_kwh() == pytest.approx(0.310)


def test_without_prices_a_stale_field_is_refused(make_coordinator, hass):
    c = make_coordinator({})
    c._get_forecast_entries = lambda **kw: []
    c.last_current_price_per_kwh = 0.310
    c.meting_tijdstippen["last_current_price_per_kwh"] = (
        dt_util.now() - timedelta(hours=3)
    )

    assert c.huidige_prijs_eur_per_kwh() is None


def test_outside_the_series_it_says_nothing(make_coordinator, hass):
    """Een moment dat in geen enkel kwartier valt levert geen prijs op -

    en dan liever niets dan het vorige kwartier.
    """
    c = _reeks(make_coordinator({}), [0.375, 0.220])

    assert c.huidige_prijs_eur_per_kwh(NU + timedelta(hours=6)) is None


# --- de lezers -------------------------------------------------------


def test_the_price_sensor_recomputes():
    """De prijssensor op het dashboard toonde het onthouden getal."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()

    assert "huidige_prijs_eur_per_kwh()" in bron
    assert "last_current_price_per_kwh" not in bron


def test_no_reader_uses_the_raw_field(make_coordinator, hass):
    """Op de diagnostiek-export na, die het RUWE veld toont zodat een

    afwijking juist zichtbaar blijft.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    lezers = [
        r.strip()
        for r in bron.split("\n")
        if "self.last_current_price_per_kwh" in r
        and "=" not in r.split("self.last_current_price_per_kwh")[1][:3]
        and not r.strip().startswith("#")
        and "_meting_is_vers" not in r
        and "return self.last_current_price_per_kwh" not in r
        # De declaratie in `__init__` is geen lezer.
        and ": float | None = None" not in r
    ]

    assert not lezers, f"nog directe lezers: {lezers}"
