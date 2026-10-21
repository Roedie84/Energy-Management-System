"""v5.113.0: de cockpit compacter.

Gevraagd 21-10 07:03 (screenshot): "De energie cockpit is nu vrij groot
geworden, graag kijken of je de indeling kunt optimaliseren en het zo
compacter kunt maken". De rechterkolom (verkoop, geld, zon) was bijna twee
keer zo lang als de andere: de prijsgrafiek, de kwaliteit van de verwachting
en een tabel van 14 dagen zaten allemaal in Geld.
"""
from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
      / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _methode(naam):
    begin = JS.index(f"\n  {naam}(") + 1
    return JS[begin:JS.index("\n  }\n", begin)]


def test_prijzen_eigen_paneel_in_de_middenkolom():
    k2 = JS[JS.index('<div class="kol k2">'):JS.index('<div class="kol k3">')]
    assert 'data-p="planning"' in k2 and 'data-p="prijzen"' in k2 and 'data-p="huis"' in k2
    assert k2.index('data-p="planning"') < k2.index('data-p="prijzen"') < k2.index('data-p="huis"')
    assert 'prijzen: ["prijsverwachting", "plan", "uitleg"]' in JS
    p = _methode("_prijzen")
    assert "this._prijsGrafiek()" in p and "this._prijsKwaliteit()" in p


def test_geld_zonder_prijzen():
    z = _methode("_zelfanalyse")
    assert "_prijsGrafiek" not in z and "_prijsKwaliteit" not in z and '"prijsverwachting"' not in z
    geld = JS[JS.index("  geld: ["):JS.index("\n", JS.index("  geld: ["))]
    assert "prijsverwachting" not in geld


def test_per_dag_ingeklapt_en_blijft_zo():
    k = _methode("_prijsKwaliteit")
    assert 'this._uitklap("prijs_per_dag"' in k
    assert 'addEventListener("toggle"' in JS and "this._uitgeklapt[d.dataset.uitklap] = d.open" in JS
    assert all(ord(c) < 128 for c in _methode("_prijzen") + _methode("_uitklap") + k)


def test_raster_kent_het_paneel_op_elke_breedte():
    assert '"stroom" "planning" "prijzen"' in JS
    assert '"prijzen prijzen"' in JS
    assert ".p-prijzen { grid-area: prijzen; }" in JS
