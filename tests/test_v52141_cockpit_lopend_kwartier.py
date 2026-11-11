"""v5.214.1 (Ruud 11-11 12:57): staaf en tijdlijn van het lopende kwartier
volgen het gemeten vermogen, net als de Vooruitblik en de tegel."""
from pathlib import Path

JS = (Path(__file__).parent.parent / "custom_components" / "energy_management_system" / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _blok(naam: str) -> str:
    start = JS.index(naam)
    return JS[start:start + 2500]


def test_staaf_van_het_lopende_kwartier_gebruikt_de_meting():
    blok = _blok("_planGrafiek(rijen, tijden) {")
    assert "const dk = doen(lopend ? this._rijNu(r) : r);" in blok
    assert "t0 + 15 * 60000 > Date.now()" in blok


def test_tijdlijn_van_het_lopende_kwartier_gebruikt_de_meting():
    assert "DOEN[doen(t0 <= nu ? this._rijNu(r) : r)]" in _blok("_planvandaag() {")


def test_vooruitblik_deed_dat_al():
    assert "kwartierWeergave(lopend ? this._rijNu(r) : r)" in JS
