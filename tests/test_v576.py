"""v5.76 (akkoord Ruud): geen wisselende attributen meer in de recorder.

Gemeten schrijvers: Monte Carlo (~3,4 KB x 1.500/dag), het komende schema
(~4 KB x 840/dag), de NILM-kandidaten (~1,3 KB x 1.500/dag), de
advies-gereedheid (~1,5 KB x 900/dag) en het Zendure-meelezen (2.900
rijen/dag). Elke entiteit van de integratie met attributen zet die nu als
geheel buiten de recorder ("*", Home Assistants MATCH_ALL). Toestanden
blijven gewoon gerecord; de kaarten lezen de attributen live.
"""
import ast
import inspect
import re
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import button, sensor, switch
from custom_components.energy_management_system.const import GEEN_ATTRIBUTEN_IN_RECORDER

PAKKET = Path(pkg.__file__).parent


def _entiteitklassen():
    for module in (sensor, switch, button):
        for naam, klasse in inspect.getmembers(module, inspect.isclass):
            if klasse.__module__ != module.__name__:
                continue
            if "extra_state_attributes" not in {
                n for k in klasse.__mro__ if k.__module__ == module.__name__ for n in vars(k)
            }:
                continue
            yield f"{module.__name__.rsplit('.', 1)[1]}.{naam}", klasse


KLASSEN = sorted(_entiteitklassen())


@pytest.mark.parametrize("naam, klasse", KLASSEN, ids=[n for n, _ in KLASSEN])
def test_elke_entiteit_met_attributen_houdt_ze_buiten_de_recorder(naam, klasse):
    assert getattr(klasse, "_unrecorded_attributes", None) == GEEN_ATTRIBUTEN_IN_RECORDER, naam


def test_match_all_is_de_ster():
    assert GEEN_ATTRIBUTEN_IN_RECORDER == frozenset({"*"})


@pytest.mark.parametrize(
    "klasse",
    [
        "MonteCarloAdvisorySensor",
        "UpcomingTimelineSensor",
        "NilmUnconfirmedCandidatesSensor",
        "AdvisoryReadinessSensor",
        "ZendureLokaalSensor",
        "MeetlogSensor",
        "AircoBesluitSensor",
        "ReserveShortfallSensor",
        "_CoordinatorDiagnosticSensor",
    ],
)
def test_de_gemeten_schrijvers(klasse):
    assert getattr(sensor, klasse)._unrecorded_attributes == GEEN_ATTRIBUTEN_IN_RECORDER


def test_de_integratie_leest_geen_historie_van_eigen_attributen():
    """Uitsluiten mag alleen als niets de attributen uit de recorder terugleest.
    Alle recorderreads gaan over ingestelde bronsensoren (P1, accu, zon, laadstand,
    zonvoorspelling) - nooit over een entiteit van deze integratie."""
    for bestand in PAKKET.glob("*.py"):
        tekst = bestand.read_text(encoding="utf-8")
        for regel in re.findall(r"(get_significant_states|state_changes_during_period)\(([^)]*)\)", tekst):
            assert "energy_management_system" not in regel[1], bestand.name


def test_geen_kaart_toont_attribuutgeschiedenis():
    kaart = (PAKKET / "dashboard_template.yaml").read_text(encoding="utf-8")
    assert "apexcharts" not in kaart
    for blok in kaart.split("type: history-graph")[1:]:
        assert "attribute:" not in blok.split("- type:")[0]
