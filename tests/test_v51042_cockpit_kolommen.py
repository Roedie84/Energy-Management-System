"""v5.104.2 - de cockpit in kolommen, zonder gat onder de planning.

Gemeld 19-10 (screenshot): "Cockpit is opzich super! alleen de grote lege
ruimte." Sinds v5.178.0 (compacte cockpit, 04-11) zijn het er twee: links de
brede kaart Prijs en lading met huis en apparaten eronder, rechts een smalle
kolom met accumodules, zon/verkopen/reserve en de knoppen.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _skelet():
    return JS.split('`<main class="raster">`')[1].split("`</main>`")[0]


def test_twee_kolommen_met_elk_hun_panelen():
    s = _skelet()
    k1, k2 = s.split('class="kol k1"')[1], s.split('class="kol k2"')[1]
    assert k1.index('data-p="planning"') < k1.index('data-p="huis"') < k1.index('class="kol k2"')
    assert k2.index('data-p="modules"') < k2.index('data-p="verkoop"') < k2.index('data-p="bediening"')


def test_alle_panelen_staan_er_precies_een_keer():
    s = _skelet()
    for p in ("planning", "verkoop", "modules", "huis", "bediening"):
        assert s.count(f'data-p="{p}"') == 1
    for weg in ("stroom", "zon", "prijzen"):
        assert f'data-p="{weg}"' not in JS


def test_smal_doen_de_kolommen_niet_mee():
    assert ".kol { display: contents; }" in JS
    breed = JS.split("@container (min-width: 1260px)")[1].split("@container")[0]
    assert '"k1 k2"' in breed and "display: flex; flex-direction: column" in breed
    assert "planning planning" in JS.split("@container (min-width: 820px)")[1].split("@container")[0]
    # mobiel: na Prijs en lading eerst de knoppen, dan de rechterkolom
    assert 'grid-template-areas: "planning" "bediening" "modules" "verkoop" "huis";' in JS
