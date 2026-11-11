"""v5.217.0 (Ruud 11-11: "Ja graag doen"): Nederlandse opmaak op de detailpagina's."""
from pathlib import Path

import pytest
import yaml

from custom_components.energy_management_system import dashboard_opmaak as O

PAKKET = Path(O.__file__).parent
SJABLOON = PAKKET / "dashboard_template.yaml"
KOPIE = PAKKET.parent.parent / "dashboards" / "energy_management_system_dashboard.yaml"


def _tekstsjablonen():
    uit = []

    def loop(node, pad):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and k in O.VELDEN and ("{{" in v or "{%" in v):
                    uit.append((f"{pad}/{k}", v))
                else:
                    loop(v, f"{pad}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                loop(v, f"{pad}[{i}]")

    loop(yaml.safe_load(SJABLOON.read_text(encoding="utf-8")), "")
    return uit


def test_elk_tekstsjabloon_is_gewikkeld():
    """Een nieuw sjabloon zonder de opmaak toont weer 84.1% in plaats van 84,1%."""
    sjablonen = _tekstsjablonen()
    assert len(sjablonen) >= 230
    zonder = [pad for pad, s in sjablonen if not (s.startswith(O.KOP) and O.filter_tekst(O.KOMMA) in s and s.rstrip().endswith("}}"))]
    assert not zonder, zonder[:5]


def test_kopie_in_dashboards_is_gelijk():
    assert KOPIE.read_text(encoding="utf-8") == SJABLOON.read_text(encoding="utf-8")


@pytest.mark.parametrize("voor, na", [
    ("84.1%", "84,1%"), ("1128.4 W", "1128,4 W"), ("-1.03 kWh", "-1,03 kWh"), ("(0.10)", "(0,10)"),
    ("met 0.926. Een", "met 0,926. Een"), ("1.20x en 0.83x", "1,20x en 0,83x"), ("3.2-4.5 kWh", "3,2-4,5 kWh"),
])
def test_punt_wordt_komma(voor, na):
    assert O.opmaak(voor, euro=False, datum=False) == na


@pytest.mark.parametrize("tekst", [
    "v5.214.0", "5.214.0", "192.168.1.5", "sensor.x_1.5", "12:30.5", "x=5.1", "1.593,5", "weather.forecast_thuis",
])
def test_wat_geen_getal_is_blijft_staan(tekst):
    assert O.opmaak(tekst, euro=False, datum=False) == tekst


@pytest.mark.parametrize("voor, na", [
    ("4.45 € tegen 4.41 € bij", "€ 4,45 tegen € 4,41 bij"), ("-0.50 EUR", "-€ 0,50"), ("168.0 EUR", "€ 168,0"),
    ("kost in 2027 € 1,22/jaar", "kost in 2027 € 1,22/jaar"), ("Kosten (EUR)", "Kosten (€)"), ("€ 3,86 / € -0,76", "€ 3,86 / € -0,76"),
])
def test_euroteken_voor_het_bedrag(voor, na):
    assert O.opmaak(voor, datum=False) == na


def test_datum_kort():
    assert O.opmaak("vanaf 2026-04-01. En 2026-11-11 23:45") == "vanaf 01-04-2026. En 11-11-2026 23:45"


def test_wikkel_is_idempotent_en_bewaart_het_sjabloon():
    s = "{{ states('sensor.x') }} kWh"
    w = O.wikkel(s, euro=True)
    assert w.startswith(O.KOP + s) and O.wikkel(w) == w
    assert "replace('EUR', '€')" in w


def test_gewikkeld_sjabloon_rendert_met_jinja():
    jinja2 = pytest.importorskip("jinja2")
    import re

    env = jinja2.Environment()
    env.filters["regex_replace"] = lambda v, find="", replace="", ignorecase=False: re.sub(find, replace, str(v))
    uit = env.from_string(O.wikkel("{{ 84.1 }}% - {{ '4.45' }} EUR - 2026-04-01 - v5.214.0", euro=True, datum=True)).render()
    assert uit == "84,1% - € 4,45 - 01-04-2026 - v5.214.0"


def test_losse_herstellingen_in_het_sjabloon():
    tekst = SJABLOON.read_text(encoding="utf-8")
    assert "{{ states(''sensor.solarflow_2400_ac_available_kwh'') }} kWh" not in tekst
    assert "ct/kWh" in tekst and "niet beschikbaar" in tekst and "geen correctie" in tekst
