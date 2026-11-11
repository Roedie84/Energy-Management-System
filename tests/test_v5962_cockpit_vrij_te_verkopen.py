"""v5.96.2: de tegel 'Vrij te verkopen' toont hetzelfde totaal als de uitleg."""
from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
      / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def test_tegel_toont_totaal():
    assert "const vrij = num(toets.vrij_te_verkopen_kwh) ?? (toets.mag_verkopen === false ? 0 : null);" in JS
    assert "num(toets.verkoop_na_blok_vrij_kwh) ?? num(toets.vrij_te_verkopen_kwh)" not in JS


def test_deel_na_blok_als_waarvan():
    # v5.216.0: de tegel "Vrij te verkopen" is vervangen door "Verkoop gepland" (uit het plan).
    assert 'mini("Verkoop gepland"' in JS and 'mini("Vrij te verkopen"' not in JS
