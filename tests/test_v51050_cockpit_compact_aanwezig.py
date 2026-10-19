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
    for woord in ('"Thuis"', '"Niemand thuis"', '"Slaapt"', "sinds", "aanleiding", "laatst_gezien"):
        assert woord in chip
    assert 'if (!a || !a.beschikbaar || !a.nu) return "";' in chip


def test_compacter_dan_voorheen():
    assert _px(".pb {", "padding") == [0, 14]
    assert _px(".regel {", "padding") == [6, 9]
    assert _px(".mini {", "padding") == [7, 10]
    assert ".gwrap { position: relative; display: grid; grid-template-columns: 34px 1fr 34px; grid-template-rows: 180px 22px; }" in JS
    assert "gap: 14px" not in JS.split(".raster {")[1].split("}")[0]
