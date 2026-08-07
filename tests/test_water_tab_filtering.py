"""Watertabellen groeien niet ongelimiteerd (v1.6.7).

Gevraagd: "Voorkomen dat de tabellen te groot worden, recente
gebruiksmomenten alleen vandaag tonen, daggeschiedenis alleen laatste 7
dagen."

Op een screenshot stond een lijst van twintig gebruiksmomenten over twee
dagen, en een kale opsomming van dagtotalen zonder datum.
"""
import re
from datetime import datetime
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml
from jinja2 import Environment

PAKKET = Path(pkg.__file__).parent


def _kaart(titel: str) -> str:
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    for view in data["views"]:
        for card in view.get("cards") or []:
            if titel in (card.get("title") or ""):
                return card["content"]
    raise AssertionError(f"kaart '{titel}' niet gevonden")


def _render(sjabloon: str, **context) -> str:
    env = Environment()
    env.globals["now"] = lambda: datetime(2026, 8, 7, 12, 0)
    env.globals["as_timestamp"] = lambda v: 0
    env.globals["state_attr"] = lambda *_: context.get("waarde")
    env.filters["timestamp_custom"] = lambda *_a, **_k: "x"
    return env.from_string(sjabloon).render()


# --- gebruiksmomenten: alleen vandaag --------------------------------


def test_only_todays_sessions_are_shown():
    sessies = [
        {"gestart": "2026-08-07T09:34:00+02:00", "duur_minuten": 2.7, "liter": 4.5},
        {"gestart": "2026-08-06T22:44:00+02:00", "duur_minuten": 6.6, "liter": 6.3},
        {"gestart": "2026-08-06T19:19:00+02:00", "duur_minuten": 8.1, "liter": 100.2},
    ]

    uitvoer = _render(_kaart("Recente gebruiksmomenten"), waarde=sessies)

    assert "1 moment(en) vandaag" in uitvoer
    # De rijen van gisteren mogen niet meer in de tabel staan.
    assert uitvoer.count("|") < 20


def test_it_says_so_when_there_is_nothing_today():
    """Een lege tabel zonder uitleg zou lijken alsof de detectie stuk
    is."""
    sessies = [
        {"gestart": "2026-08-06T22:44:00+02:00", "duur_minuten": 6.6, "liter": 6.3}
    ]

    uitvoer = _render(_kaart("Recente gebruiksmomenten"), waarde=sessies)

    assert "Nog geen gebruiksmomenten vandaag" in uitvoer
    assert "1 eerdere momenten bewaard" in uitvoer


def test_an_empty_history_is_distinguished():
    uitvoer = _render(_kaart("Recente gebruiksmomenten"), waarde=[])

    assert "Nog geen gebruiksmomenten geregistreerd" in uitvoer


def test_a_session_without_a_start_does_not_crash():
    """In de praktijk komen sessies zonder starttijd voor; die mogen de
    hele kaart niet onderuit halen."""
    sessies = [{"duur_minuten": 1.0, "liter": 2.0}, {"gestart": None}]

    uitvoer = _render(_kaart("Recente gebruiksmomenten"), waarde=sessies)

    assert "Nog geen gebruiksmomenten vandaag" in uitvoer


# --- daggeschiedenis: laatste zeven ----------------------------------


def test_only_seven_days_are_shown():
    uitvoer = _render(_kaart("Dag-geschiedenis"), waarde=[float(n) for n in range(1, 21)])

    # Twintig dagen bewaard, zeven getoond.
    for zichtbaar in ("20.0", "14.0"):
        assert zichtbaar in uitvoer
    assert "13.0" not in uitvoer


def test_the_history_has_dates_not_just_numbers():
    """Een kale lijst getallen zegt niets over wanneer die dag was."""
    uitvoer = _render(_kaart("Dag-geschiedenis"), waarde=[441.25, 327.19])

    assert "| Dag | Verbruik |" in uitvoer


def test_an_empty_day_history_says_so():
    uitvoer = _render(_kaart("Dag-geschiedenis"), waarde=[])

    assert "Nog geen volledige dagen" in uitvoer


# --- borging ---------------------------------------------------------


def test_no_home_assistant_only_jinja_tests_are_used():
    """`match` en `search` bestaan wel in Home Assistant maar niet in
    kale Jinja - en dan loopt de opmaaktest stuk voordat hij de tabel
    kan controleren. Dat kostte hier drie pogingen."""
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    for filtertest in ("'match'", "'search'"):
        assert filtertest not in yaml_tekst
