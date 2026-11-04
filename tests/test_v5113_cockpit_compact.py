"""v5.113.0: de cockpit compacter.

Gevraagd 21-10 07:03 (screenshot): "De energie cockpit is nu vrij groot
geworden, graag kijken of je de indeling kunt optimaliseren en het zo
compacter kunt maken". De prijzen een week vooruit kregen toen een eigen
paneel; sinds v5.178.0 zijn ze het tabblad "7 dagen" van Prijs en lading en
staat de kwaliteit van de verwachting zichtbaar in dat tabblad.
"""
from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
      / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _methode(naam):
    begin = JS.index(f"\n  {naam}(") + 1
    return JS[begin:JS.index("\n  }\n", begin)]


def test_prijzen_zijn_het_tabblad_7_dagen():
    assert 'planning: ["plan", "schema", "uitleg", "blok", "soc", "prijsverwachting"]' in JS
    w = _methode("_week")
    assert "this._prijsGrafiek()" in w and "this._prijsKwaliteit()" in w
    assert "this._week()" in _methode("_planning")
    assert "  _prijzen(" not in JS


def test_geld_zonder_prijzen():
    z = _methode("_zelfanalyse")
    assert "_prijsGrafiek" not in z and "_prijsKwaliteit" not in z and '"prijsverwachting"' not in z
    geld = JS[JS.index("  geld: ["):JS.index("\n", JS.index("  geld: ["))]
    assert "prijsverwachting" not in geld


def test_per_dag_ingeklapt_en_blijft_zo():
    k = _methode("_prijsKwaliteit")
    assert 'this._uitklap("prijs_per_dag"' in k
    assert 'addEventListener("toggle"' in JS and "this._uitgeklapt[d.dataset.uitklap] = d.open" in JS
    assert all(ord(c) < 128 for c in _methode("_week") + _methode("_uitklap") + k)


def test_raster_kent_elk_paneel():
    for p in ("planning", "verkoop", "modules", "huis", "bediening"):
        assert f".p-{p} {{ grid-area: {p}; }}" in JS
