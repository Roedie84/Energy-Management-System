"""v5.104.2 - de cockpit in kolommen, zonder gat onder de planning.

Gemeld 19-10 (screenshot): "Cockpit is opzich super! alleen de grote lege
ruimte." Sinds v5.178.0 (compacte cockpit, 04-11) zijn het er twee: links de
brede kaart Prijs en lading met huis en apparaten eronder, rechts een smalle
kolom met accumodules, zon/verkopen/reserve en de knoppen.
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _skelet():
    return JS.split('`<main class="raster">`')[1].split("`</main>`")[0]


def test_twee_kolommen_met_eigen_hoogte():
    """v5.242.0 (Ruud 19-11, "compacter"): links accu nu, Prijs en lading en
    huis; rechts geld, accumodules, zon en de bediening. Geen kaarten meer die
    even hoog worden als de langste."""
    s = _skelet()
    links = s.split('class="kolom k-links"')[1].split('class="kolom k-rechts"')[0]
    rechts = s.split('class="kolom k-rechts"')[1]
    assert links.index('data-p="accu"') < links.index('data-p="planning"') < links.index('data-p="huis"')
    assert rechts.index('data-p="geld"') < rechts.index('data-p="modules"') < rechts.index('data-p="verkoop"') < rechts.index('data-p="bediening"')
    assert 'data-p="planvandaag"' not in JS and 'class="hero"' not in JS.split("class EmsJaarafrekeningCard")[0]
    assert ".raster { display: grid; gap: 10px; grid-template-columns: minmax(0, 1fr); align-items: start; }" in JS


def test_alle_panelen_staan_er_precies_een_keer():
    s = _skelet()
    for p in ("planning", "verkoop", "modules", "huis", "bediening"):
        assert s.count(f'data-p="{p}"') == 1
    for weg in ("stroom", "zon", "prijzen"):
        assert f'data-p="{weg}"' not in JS


def test_smal_een_kolom_breed_twee():
    assert ".kolom { display: contents; }" in JS
    breed = JS.split("@container (min-width: 1100px)")[1].split("@container")[0]
    assert ".raster { grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); }" in breed
    assert ".kolom { display: flex; flex-direction: column; gap: 10px; min-width: 0; }" in breed
    # smal: nu - grafiek - geld - bediening - accu - zon - huis
    for klasse, plek in ((".t-accu", 0), (".p-planning", 1), (".t-geld", 2), (".p-bediening", 3),
                         (".p-modules", 4), (".p-verkoop", 5), (".p-huis", 6)):
        assert f"{klasse} {{ order: {plek}; }}" in JS
