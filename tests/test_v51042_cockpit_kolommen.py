"""v5.104.2 - de cockpit in drie kolommen, zonder gat onder de planning.

Gemeld 19-10 (screenshot): "Cockpit is opzich super! alleen de grote lege
ruimte." Het brede raster liet de planning over twee rijen lopen; de rij was
zo hoog als stroom + modules en verkoop + geld, en onder de korte planning
bleef een groot gat.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _skelet():
    return JS.split('`<main class="raster">`')[1].split("`</main>`")[0]


def test_drie_kolommen_met_elk_hun_panelen():
    s = _skelet()
    k1, k2, k3 = s.split('class="kol k1"')[1], s.split('class="kol k2"')[1], s.split('class="kol k3"')[1]
    assert k1.index('data-p="stroom"') < k1.index('data-p="modules"') < k1.index('class="kol k2"')
    assert k2.index('data-p="planning"') < k2.index('data-p="huis"') < k2.index('data-p="zon"') < k2.index('class="kol k3"')
    assert k3.index('data-p="verkoop"') < k3.index('data-p="geld"') < k3.index('data-p="bediening"')


def test_alle_panelen_staan_er_precies_een_keer():
    s = _skelet()
    for p in ("stroom", "planning", "verkoop", "modules", "zon", "huis", "geld", "bediening"):
        assert s.count(f'data-p="{p}"') == 1


def test_smal_doen_de_kolommen_niet_mee():
    assert ".kol { display: contents; }" in JS
    breed = JS.split("@container (min-width: 1260px)")[1].split("@container")[0]
    assert '"k1 k2 k3"' in breed and "display: flex; flex-direction: column" in breed
    assert "planning planning" in JS.split("@container (min-width: 820px)")[1].split("@container")[0]
