"""v5.104.1 - de laatste regeneratie van de waterontharder in de cockpit, bij de apparaten.

Gevraagd 19-10: "Waar kan ik in HA (dashboard) nog zien of de waterontharder
heeft geregenereerd?" en daarna "Energycockpit bij apparaten graag". Het stond
alleen op de Water-subpagina van het YAML-dashboard, dat uit de zijbalk is.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _huis():
    return JS.split("  _huis() {")[1].split("  /* ---- geld ---- */")[0]


def test_de_ontharder_staat_bij_huis_en_apparaten():
    blok = _huis()
    assert '"Waterontharder"' in blok
    assert "waterontharder_laatste_regeneratie" in blok
    assert "laatst geregenereerd" in blok


def test_liters_en_duur_uit_dezelfde_sessie():
    blok = _huis()
    assert "recente_gebruiksmomenten" in blok
    assert "sessie.liter" in blok and "sessie.duur_minuten" in blok


def test_zonder_regeneratie_geen_regel():
    blok = _huis()
    assert "if (reg) {" in blok
