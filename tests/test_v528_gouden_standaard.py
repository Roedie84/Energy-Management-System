"""v5.28: productie is ongewijzigd (gouden standaard).

Uit de review: "Laat expliciet zien dat voor de gouden scenario's v5.27.4
production_action = v5.28 production_action, inclusief Zendure-stand en
vermogen." `tests/fixtures/gouden_v5274.json` is vastgelegd met v5.27.4,
vóór er een regel van de meetlaag bestond.
"""
import json
from pathlib import Path

import pytest

from gouden_scenarios import SCENARIOS, draai

GOUD = json.loads((Path(__file__).parent / "fixtures" / "gouden_v5274.json").read_text())

# v5.29 filterde hier opdrachten weg die "al zo stonden". Sinds v5.31.2 telt
# alleen wat het EMS zelf schreef als "staat er al" - de scenario's starten
# zonder eerdere opdrachten, dus alles wordt verstuurd, zoals in v5.27.4.


# BEWUST GEWIJZIGD sinds de vastlegging, met de reden erbij.
AFWIJKINGEN = {
    # v5.81.1 (akkoord Ruud 11-10): de reserve wordt afgekapt op wat er
    # tussen de grenzen past, niet op de totale accu. Met 7,7 kWh beschikbaar
    # is de accu hier vol (plafond 7,34 kWh bij 15% minimum), en dan is de
    # brug "genoeg": laden uitstellen. Tot v5.81.1 zei hij met een volle accu
    # structureel "niet genoeg" (reserve 8,64 tegen hooguit 7,78 beschikbaar).
    "middag_16u_vol": {
        "reden": "discharging_window",
        "stand": "smart_discharging",
        "opdrachten": [["select", "select_option", {"entity_id": "select.op", "option": "smart_discharging"}]],
    },
}


@pytest.mark.parametrize("naam", sorted(SCENARIOS))
def test_productie_beslist_als_v5274(make_coordinator, hass, naam):
    nu = draai(make_coordinator, hass, naam)
    verwacht = AFWIJKINGEN.get(naam, GOUD[naam])

    assert nu["reden"] == verwacht["reden"]
    assert nu["stand"] == verwacht["stand"]
    assert nu["opdrachten"] == verwacht["opdrachten"]   # Zendure-stand en vermogen


def test_de_gouden_standaard_dekt_alle_soorten_besluiten():
    standen = {r["stand"] for r in GOUD.values()}
    vermogens = {o[2].get("value") for r in GOUD.values() for o in r["opdrachten"] if o[0] == "number"}
    assert {"smart", "smart_discharging", "manual"} <= standen
    assert {1600, -2000} <= vermogens          # verkopen en laden
