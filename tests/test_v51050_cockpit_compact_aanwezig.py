"""v5.105.0 - cockpit compacter, en bovenin of er iemand thuis is.

Gevraagd 19-10: "Informatie behouden op cockpit dashboard, maar graag wat
compacter, tevens de analyse van het EMS of er iemand thuis is of niet (boven
aan in dashboard)."
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _px(regel_begin, eigenschap):
    regel = next(r for r in JS.splitlines() if r.startswith(regel_begin))
    return [int(x) for x in re.search(eigenschap + r": ([\d px]+);", regel).group(1).replace("px", "").split()]


def test_aanwezigheid_komt_uit_de_eigen_sensor():
    assert 'aanwezig: "aanwezigheid",' in JS


def test_de_kop_toont_de_aanwezigheid():
    kop = JS.split("  _kop() {")[1].split("\n  }\n")[0]
    assert "this._aanwezigChip()" in kop


def test_de_chip_zegt_staat_sinds_en_waarom():
    chip = JS.split("  _aanwezigChip() {")[1].split("\n  }\n")[0]
    for woord in ('"Iemand thuis"', '"Niemand thuis"', '"Slaapt"', "sinds", "aanleiding", "laatst_gezien"):
        assert woord in chip
    assert 'if (!a || !a.beschikbaar || !a.nu) return "";' in chip


def test_een_spatieschaal():
    """v5.179: alle afstanden uit de schaal 4/8/12/16/24; kaarten 16 px binnenruimte."""
    assert _px(".regel {", "padding") == [8, 12]
    kaart = JS.split(".tegel, .paneel {")[1].split("}")[0]
    assert "padding: 16px" in kaart and "border-radius: var(--r)" in kaart
    assert "--r: 12px;" in JS
    assert "gap: 12px" in JS.split(".raster {")[1].split("}")[0]
    assert ".gwrap { position: relative; display: grid; grid-template-columns: 32px 1fr 36px; grid-template-rows: 180px 24px; }" in JS
