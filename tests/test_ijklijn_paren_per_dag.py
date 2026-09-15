"""De ijklijn kon nooit klaar komen (v1.0.1).

Uit de export van 15 september, na 20 dagen meten:

    gevulde bakjes            7 van 3 nodig
    bruikbare paren           300 van 100 nodig
    rangordescore             None
    wat ontbreekt             "Nog geen enkele bron heeft 100 paren"

Alles is er, en toch geen score - en de uitleg noemt een reden die
aantoonbaar niet klopt. De echte reden zit in `weerbron_rangorde_score`:
naast honderd paren eist die tien DAGEN in de paren. Maar de paren
worden elke RONDE toegevoegd - elke minuut waarop de bakje-meting loopt -
en op 300 afgekapt. Driehonderd rondes is vijf uur. De laatste 300 paren
beslaan dus altijd één, hooguit twee dagen, en de dagentoets faalt
voorgoed. Hoe langer het draait, hoe zekerder.

Twee dingen mis: paren per minuut waar één per uur genoeg is (de bakjes
zijn per uur zonnestand), en een uitlegtekst die naar de verkeerde eis
wijst. Nu: één paar per bron per uur, veertig dagen bewaard, en de
uitleg noemt wat er werkelijk ontbreekt.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _meting(c, wanneer, bewolking=40.0, pv_w=2000.0, bakje="30.0"):
    c.weather_ensemble_readings = {"weather.a": bewolking}
    c.weerbron_helderheid_paren = getattr(c, "weerbron_helderheid_paren", None) or {}
    c._voeg_helderheidspaar_toe(wanneer, pv_w, bakje)


def test_een_paar_per_uur_per_bron(make_coordinator, hass):
    c = make_coordinator({})
    c.weerbron_helderheid_paren = {}
    for m in range(0, 60, 5):
        _meting(c, NU + timedelta(minutes=m))
    _meting(c, NU + timedelta(hours=1))

    assert len(c.weerbron_helderheid_paren["weather.a"]) == 2


def test_de_paren_beslaan_genoeg_dagen(make_coordinator, hass):
    """Veertig dagen aan uurparen past ruim in de bewaargrens; met de
    oude grens van 300 per minuut paste er één dag in."""
    from custom_components.energy_management_system.const import (
        HELDERHEID_MIN_DAGEN_PAREN,
        HELDERHEID_PAREN_LENGTE,
    )

    c = make_coordinator({})
    c.weerbron_helderheid_paren = {}
    for dag in range(12):
        for uur in range(8, 18):
            _meting(c, NU + timedelta(days=dag, hours=uur - 12))

    paren = c.weerbron_helderheid_paren["weather.a"]
    dagen = {p[3] for p in paren}
    assert len(dagen) >= HELDERHEID_MIN_DAGEN_PAREN
    assert len(paren) <= HELDERHEID_PAREN_LENGTE
    assert HELDERHEID_PAREN_LENGTE >= 12 * 10


def test_de_uitleg_noemt_de_echte_reden(make_coordinator, hass):
    """Honderd paren maar te weinig dagen: dan moet de uitleg over de
    DAGEN gaan, niet over de paren."""
    c = make_coordinator({})
    # drie gevulde bakjes, dus die eis is gehaald - net als bij Ruud
    c.helderheid_ijklijn = {b: [1500.0 + i for i in range(60)] for b in ("20.0", "30.0", "40.0")}
    c.helderheid_dagen = {b: [f"d{i}" for i in range(10)] for b in ("20.0", "30.0", "40.0")}
    # 120 paren, maar allemaal van één dag
    c.weerbron_helderheid_paren = {
        "weather.a": [[40.0 + (i % 5), 1800.0, "30.0", "2026-09-15"] for i in range(120)]
    }

    uit = c.get_helderheid_ijking()

    assert "dag" in uit["wat_ontbreekt"].lower()
    assert "100 paren" not in uit["wat_ontbreekt"]
