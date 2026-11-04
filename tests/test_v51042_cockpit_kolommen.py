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


def test_rijen_die_gelijk_eindigen():
    """v5.179: rij 2 = Prijs en lading (8) naast een stapel met accumodules en
    reserve (4); rij 3 = Huis en apparaten (8) naast de bediening (4)."""
    s = _skelet()
    stapel = s.split('class="stapel"')[1].split("`</div>`")[0]
    assert s.index('data-p="planning"') < s.index('class="stapel"') < s.index('data-p="huis"') < s.index('data-p="bediening"')
    assert stapel.index('data-p="modules"') < stapel.index('data-p="verkoop"')
    assert 'data-p="bediening"' not in stapel


def test_alle_panelen_staan_er_precies_een_keer():
    s = _skelet()
    for p in ("planning", "verkoop", "modules", "huis", "bediening"):
        assert s.count(f'data-p="{p}"') == 1
    for weg in ("stroom", "zon", "prijzen"):
        assert f'data-p="{weg}"' not in JS


def test_smal_doet_de_stapel_niet_mee():
    assert ".stapel { display: contents; }" in JS
    breed = JS.split("@container (min-width: 1260px)")[1].split("@container")[0]
    assert "grid-template-columns: repeat(12, minmax(0, 1fr))" in breed
    assert ".p-planning, .p-huis { grid-column: span 8;" in breed
    assert ".stapel { display: flex; flex-direction: column; gap: 12px; grid-column: span 4;" in breed
    assert ".p-bediening { grid-column: span 4;" in breed
    # de grafiek vult de kaart tot de stapel ernaast: geen gat onderaan
    assert "grid-template-rows: minmax(220px, 1fr) 24px" in breed
    # mobiel: na Prijs en lading eerst de knoppen, dan de rechterkolom
    orde = {p: int(re.search(r"\.p-" + p + r" \{ order: (\d+); \}", JS).group(1))
            for p in ("planning", "bediening", "modules", "verkoop", "huis")}
    assert sorted(orde, key=orde.get) == ["planning", "bediening", "modules", "verkoop", "huis"]
