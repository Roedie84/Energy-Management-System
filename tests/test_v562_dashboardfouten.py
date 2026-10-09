"""v5.62: fouten in het dashboard, gevonden in de live installatie (9 oktober).

1. De Plantoetsing-pagina las `opbrengst_afwijking_mediaan_procent`. Die
   sleutel bestaat sinds v3.71.0 niet meer (het oordeel gaat over het
   VERKOCHTE, `verkocht_afwijking_mediaan_procent`). Home Assistant logde
   `UndefinedError: 'dict object' has no attribute ...`.
2. Drie icoonkleuren op het overzicht hadden dubbel verdubbelde
   aanhalingstekens (`''''sensor...''''`): geen geldig sjabloon, dus nooit
   een kleur.
3. De dashboardcontrole zette de nooit ingedrukte waterknoppen, de
   accubescherming zonder grens en de lerende airco-verwachting tussen de
   "lege" entiteiten - bij een doorlichting werden ze voor ontbrekende
   entiteiten aangezien. Ze bestaan; "unknown" is daar de gewone toestand.

Plus de borging: elke sleutel die het dashboard leest, bestaat in de code;
elk sjabloon is geldig Jinja.
"""
import re
from pathlib import Path

import jinja2
import pytest
import yaml

import custom_components.energy_management_system as pkg

MAP = Path(pkg.__file__).parent
SJABLOON = MAP / "dashboard_template.yaml"


def _sjabloon() -> dict:
    return yaml.safe_load(SJABLOON.read_text(encoding="utf-8"))


def _teksten(knoop=None) -> list[str]:
    if knoop is None:
        knoop = _sjabloon()
    uit = []
    if isinstance(knoop, dict):
        for waarde in knoop.values():
            uit += _teksten(waarde)
    elif isinstance(knoop, list):
        for waarde in knoop:
            uit += _teksten(waarde)
    elif isinstance(knoop, str):
        uit.append(knoop)
    return uit


def _view(pad: str) -> dict:
    return next(v for v in _sjabloon()["views"] if v.get("path") == pad)


def _kaart(view: dict, titel: str) -> dict:
    for sectie in view.get("sections") or []:
        for kaart in sectie.get("cards") or []:
            if kaart.get("title") == titel:
                return kaart
    raise KeyError(titel)


# --- 1. de plantoetsing --------------------------------------------------


def test_de_verdwenen_sleutel_staat_niet_meer_in_het_dashboard():
    tekst = SJABLOON.read_text(encoding="utf-8")
    assert "opbrengst_afwijking_mediaan_procent" not in tekst
    assert "verkocht_afwijking_mediaan_procent" in tekst


def _render(inhoud: str, attributen: dict) -> str:
    """Rendert zoals Home Assistant, maar strenger: elke ontbrekende
    sleutel is een fout (StrictUndefined)."""
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    return env.from_string(inhoud).render(
        state_attr=lambda entiteit, sleutel: attributen.get(sleutel)
    )


def _plantoetsing_regel(datum: str, verkocht=-79.0) -> dict:
    """Een regel zoals `_finish_plan_review` hem bewaart (live, 8 okt)."""
    return {
        "datum": datum,
        "opgenomen_om": "08:00",
        "zon": {"voorspeld_kwh": 12.6, "werkelijk_kwh": 11.87, "afwijking_procent": -5.8},
        "verkocht": {"voorspeld_kwh": 3.53, "werkelijk_kwh": 0.74, "afwijking_procent": verkocht},
        "opbrengst": {
            "voorspeld_eur": 1.32,
            "werkelijk_eur": -0.9,
            "vergelijkbaar": False,
            "toelichting": "De voorspelling telt alleen de opbrengst van de verkoopkwartieren.",
            "_afwijking_ongeldig": -168.5,
        },
        "import": {"voorspeld_kwh": 0, "werkelijk_kwh": 0.5},
        "laagste_soc": {"voorspeld_procent": 31, "werkelijk_procent": 58},
        "tekort_kwartieren_voorspeld": 0,
        "verkoopkwartieren_voorspeld": 3,
        "oordeel": "Afwijking: verkocht -79%.",
    }


def _plantoetsing_echt(make_coordinator):
    """Wat de pagina-sensor Plantoetsing nu werkelijk doorgeeft."""
    from custom_components.energy_management_system import sensor as m

    c = make_coordinator({})
    c.plan_review_history = [
        _plantoetsing_regel(f"2026-09-{d:02d}") for d in range(9, 31)
    ] + [_plantoetsing_regel(f"2026-10-{d:02d}") for d in range(1, 9)]
    rij = next(r for r in m.DASHBOARD_PAGINA_SENSOREN if r[3] == ("plantoetsing",))
    return m.DashboardPaginaSensor(c, "x", *rij).extra_state_attributes


@pytest.mark.parametrize("titel", ["Wat er structureel opvalt", "Per dag"])
def test_de_plantoetsing_rendert_met_echte_gegevens(make_coordinator, hass, titel):
    attributen = _plantoetsing_echt(make_coordinator)
    kaart = _kaart(_view("detail-plantoetsing"), titel)

    uit = _render(kaart["content"], attributen)

    if titel == "Per dag":
        assert "2026-10-08" in uit
        assert "11.87 / 12.6 kWh" in uit
        assert "€ -0.9 / € 1.32" in uit
        assert "58% / 31%" in uit
    else:
        assert "| Dagen getoetst | 30 |" in uit
        assert "Verkocht, mediane afwijking | -79.0%" in uit
        assert "Zon, mediane afwijking | -5.8%" in uit


@pytest.mark.parametrize(
    "plantoetsing",
    [
        None,
        {},
        {"beschikbaar": False, "reden": "Nog geen volledige dag getoetst."},
        # Beschikbaar, maar zonder één van de getallen: nooit een fout.
        {"beschikbaar": True},
        {
            "beschikbaar": True,
            "dagen": 3,
            "zon_afwijking_mediaan_procent": None,
            "verkocht_afwijking_mediaan_procent": None,
            "dagen_overzicht": [{"datum": "2026-10-08"}, {}],
        },
    ],
)
@pytest.mark.parametrize("titel", ["Wat er structureel opvalt", "Per dag"])
def test_de_plantoetsing_is_defensief(plantoetsing, titel):
    """Precies de fout uit het logboek: een ontbrekende sleutel mag geen
    UndefinedError geven, maar een streepje."""
    kaart = _kaart(_view("detail-plantoetsing"), titel)

    uit = _render(kaart["content"], {"plantoetsing": plantoetsing})

    assert "None%" not in uit


def test_ontbrekende_getallen_worden_een_streepje():
    kaart = _kaart(_view("detail-plantoetsing"), "Wat er structureel opvalt")

    uit = _render(
        kaart["content"],
        {"plantoetsing": {"beschikbaar": True, "verkocht_afwijking_mediaan_procent": None}},
    )

    assert "| Verkocht, mediane afwijking | – |" in uit
    assert "| Dagen getoetst | – |" in uit


# --- 2. geldige sjablonen ------------------------------------------------


def test_elk_sjabloon_is_geldig_jinja():
    """Drie icoonkleuren waren ongeldig door verdubbelde aanhalingstekens
    (`''''sensor...''''` in het bestand, `''sensor...''` voor Jinja)."""
    env = jinja2.Environment(extensions=["jinja2.ext.loopcontrols"])
    fouten = []
    for tekst in _teksten():
        if "{{" in tekst or "{%" in tekst:
            try:
                env.parse(tekst)
            except jinja2.TemplateSyntaxError as fout:
                fouten.append(f"{fout}: {tekst[:120]}")
    assert not fouten, fouten


def test_de_besparingstegels_kleuren_weer():
    tegels = [
        t
        for t in _teksten()
        if "besparing_eur >= 0" in t and "'green'" in t
    ]
    assert len(tegels) == 3
    for tegel in tegels:
        assert "''" not in tegel
        assert "state_attr('sensor.woonkamer_energy_management_system_perioden', 'perioden')" in tegel


# --- borging: elke gelezen sleutel bestaat in de code -------------------


def _gelezen_sleutels() -> set[tuple[str, str]]:
    """(soort, sleutel) voor alles wat het dashboard uit een EMS-attribuut
    leest: het attribuut zelf, en de sleutels daarbinnen (`x.get('s')`,
    `x.s`), ook via afgeleide variabelen en lussen."""
    gelezen = set()
    for tekst in _teksten():
        for _entiteit, sleutel in re.findall(
            r"state_attr\('((?:sensor|switch|button)\.[a-z0-9_]*energy_management_system[a-z0-9_]*)',\s*'([^']+)'\)",
            tekst,
        ):
            gelezen.add(("attribuut", sleutel))
        namen = set(
            re.findall(
                r"\{%-?\s*set\s+(\w+)\s*=\s*\(?state_attr\('[^']*energy_management_system[^']*'",
                tekst,
            )
        )
        for _ in range(3):
            if not namen:
                break
            patroon = "|".join(map(re.escape, namen))
            namen |= set(re.findall(rf"\{{%-?\s*set\s+(\w+)\s*=\s*\(?(?:{patroon})\b", tekst))
            namen |= set(re.findall(rf"\{{%-?\s*for\s+(\w+)\s+in\s+\(?(?:{patroon})\b", tekst))
        for naam in namen:
            for sleutel in set(re.findall(rf"\b{naam}\.get\('(\w+)'", tekst)) | set(
                re.findall(rf"(?<![\w.]){naam}\.(\w+)\b(?!\()", tekst)
            ):
                if sleutel not in ("get", "items", "keys", "values"):
                    gelezen.add(("sleutel", sleutel))
    return gelezen


def test_elke_gelezen_sleutel_bestaat_in_de_code():
    """De vorm van de plantoetsingsfout: de code hernoemde een sleutel, het
    dashboard las de oude. Hier: elke sleutel die het dashboard leest,
    staat ergens in de code als tekst."""
    code = "\n".join(p.read_text(encoding="utf-8") for p in MAP.glob("*.py"))
    ontbreekt = sorted(
        sleutel
        for _soort, sleutel in _gelezen_sleutels()
        if f'"{sleutel}"' not in code and f"'{sleutel}'" not in code
    )
    assert not ontbreekt, f"het dashboard leest sleutels die de code niet maakt: {ontbreekt}"


def test_de_borging_had_de_fout_gevonden():
    gelezen = _gelezen_sleutels()
    assert ("sleutel", "verkocht_afwijking_mediaan_procent") in gelezen
    assert ("sleutel", "dagen_binnen_marge") in gelezen


# --- 3. "onbekend" dat gewoon is ----------------------------------------


@pytest.mark.parametrize(
    "entity_id",
    [
        "button.water_was_toilet",
        "button.water_was_douche",
        "sensor.energy_management_system_battery_protection",
        "sensor.woonkamer_energy_management_system_airco_verwachting_woonkamertemperatuur",
    ],
)
def test_gewoon_onbekend_staat_apart(make_coordinator, hass, entity_id):
    c = make_coordinator({})
    hass.states.set(entity_id, "unknown")

    rapport = c.get_dashboard_health()

    assert entity_id in rapport["onbekend_maar_normaal"]
    assert entity_id not in rapport["lege_entiteiten"]
    assert entity_id not in rapport["niet_bestaande_entiteiten"]


def test_een_echt_lege_sensor_blijft_leeg(make_coordinator, hass):
    c = make_coordinator({})
    hass.states.set("sensor.energy_management_system_last_decision_reason", "unknown")
    hass.states.set("button.water_was_keuken", "unavailable")

    rapport = c.get_dashboard_health()

    assert "sensor.energy_management_system_last_decision_reason" in rapport["lege_entiteiten"]
    # Een knop die onbeschikbaar is, is wél iets.
    assert "button.water_was_keuken" in rapport["lege_entiteiten"]


def test_de_waterknoppen_op_het_dashboard_bestaan():
    """De zes knoppen heten vast `button.water_was_<bron>` (v4.9.5), en het
    dashboard noemt precies die zes."""
    from custom_components.energy_management_system.const import WATERBRONNEN

    tekst = SJABLOON.read_text(encoding="utf-8")
    op_het_dashboard = set(re.findall(r"button\.water_was_[a-z_]+", tekst))
    assert op_het_dashboard == {f"button.water_was_{b}" for b in WATERBRONNEN}
    bron = (MAP / "button.py").read_text(encoding="utf-8")
    assert 'self.entity_id = f"button.water_was_{bron}"' in bron


# --- het dashboard in Home Assistant volgt vanzelf -----------------------


def test_het_dashboard_wordt_bij_elke_start_overschreven(tmp_path):
    """Het YAML-dashboard in Home Assistant is een kopie die bij elke start
    (en elke herlading) van de integratie wordt overschreven - na een
    update hoeft er niets met de hand gekopieerd te worden."""
    from types import SimpleNamespace

    from custom_components.energy_management_system import (
        DASHBOARD_FILENAME,
        _copy_dashboard_template,
    )

    doel = tmp_path / DASHBOARD_FILENAME
    doel.write_text("oud", encoding="utf-8")
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda naam: str(tmp_path / naam)))

    _copy_dashboard_template(hass)

    assert doel.read_text(encoding="utf-8") == SJABLOON.read_text(encoding="utf-8")
    assert "opbrengst_afwijking_mediaan_procent" not in doel.read_text(encoding="utf-8")
