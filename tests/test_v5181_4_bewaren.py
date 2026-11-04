"""v5.181.4: "Bewaren" overal hetzelfde; het lopende kwartier volgt de meting.

04-11 13:13 (Ruud, screenshot): de tegel zei "Bewaren voor later", de
Vooruitblik en de grafiek "Rust" voor hetzelfde kwartier, terwijl de accu
164 W uit de zon laadde.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import standweergave as sw

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def test_sparen_zonder_vermogen_is_bewaren():
    assert sw.weergave(None, "smart_charging (sparen)", 0.0) == {"k": "bewaren", "label": "Bewaren voor later"}
    # zelfde zin als de tegel met reden
    assert sw.weergave("waardeplan_houden", "smart_charging (sparen)", 0.0)["label"] == "Bewaren voor later"
    assert sw.weergave("battery_saved_for_peak", "smart_charging (sparen)", 0.0)["label"] == "Bewaren voor de piek"


def test_slim_zonder_vermogen_blijft_rust():
    assert sw.weergave(None, "smart", 0.0)["k"] == "rust"


def test_sparen_terwijl_de_zon_laadt_is_zon_laden():
    assert sw.weergave("waardeplan_houden", "smart_charging (sparen)", -164.0)["label"] == \
        "Zon laden – lading bewaren voor later"


def test_leeg_gaat_voor_bewaren():
    assert sw.weergave("waardeplan_leeg", "smart_charging (sparen)", 0.0)["k"] == "leeg"


def test_cockpit_lopend_kwartier_uit_de_meting():
    assert "_rijNu(rij, live)" in JS
    assert "kwartierWeergave(this._rijNu(rij, live), reden)" in JS
    assert "kwartierWeergave(lopend ? this._rijNu(r) : r)" in JS
    assert 'bewaren: { label: "Bewaren voor later"' in JS


def test_een_tab_met_alle_bekende_prijzen():
    """Ruud 04-11 13:28: geen tabs Vandaag/Morgen, alleen de beschikbare prijzen; 7 dagen blijft."""
    assert 'const TABS = [["prijzen", "Prijzen"], ["week", "7 dagen"]];' in JS
    plan = JS.split("  _planning() {", 1)[1].split("\n  }\n", 1)[0]
    assert "this._planGrafiek(rijen, tijden)" in plan
    assert "morgen" not in plan.split("const uitleg", 1)[0].lower()
