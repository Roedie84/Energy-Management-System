"""De doorklik achter de cockpit (v5.23).

Uit de cockpit-opdracht: AANDACHT aanklikbaar maken "zodat ik kan zien
welke twee aandachtspunten actief zijn", en "als ik wil weten WAAROM de
reserve bijvoorbeeld 4,60 kWh bedraagt, moet dat liever via doorklik
beschikbaar zijn, gebaseerd op de daadwerkelijke Dynamic Reserve-
berekening".

De plaat staat in een markdown-kaart, en die kent geen tikactie. Dus twee
knoppen onder de plaat, naar de pagina's die er AL waren: Meetkwaliteit
(met de kaart Aandachtspunten) en Reservemarge. Een eigen detailpagina was
dubbel geweest - de dashboardregels vingen dat.
"""
from pathlib import Path

import jinja2
import yaml

import custom_components.energy_management_system as pkg


def _dashboard():
    return yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )


def _pagina(pad):
    return next(v for v in _dashboard()["views"] if v.get("path") == pad)


def _knoppen():
    stapel = _pagina("visueel")["cards"][0]["cards"]
    rij = next(k for k in stapel if k["type"] == "horizontal-stack")
    return {k["name"]: k["tap_action"]["navigation_path"] for k in rij["cards"]}


def test_de_cockpit_heeft_knoppen_naar_de_details():
    knoppen = _knoppen()

    assert knoppen["Aandachtspunten"].endswith("/detail-kwaliteit")
    assert knoppen["Reserve-opbouw"].endswith("/detail-reservemarge")


def test_de_knoppen_wijzen_naar_bestaande_paginas():
    paden = {v.get("path") for v in _dashboard()["views"]}

    for doel in _knoppen().values():
        assert doel.rsplit("/", 1)[-1] in paden, doel


def _reservekaart(m):
    pagina = _pagina("detail-reservemarge")
    gevonden = []

    def loop(k):
        if isinstance(k, dict):
            if k.get("title") == "Reservemarge" and "content" in k:
                gevonden.append(k["content"])
            for w in k.values():
                loop(w)
        elif isinstance(k, list):
            for w in k:
                loop(w)

    loop(pagina)
    env = jinja2.Environment()
    env.globals["state_attr"] = lambda e, a: m
    return env.from_string(gevonden[0]).render()


def test_de_reservekaart_toont_de_zin_uit_de_coordinator(make_coordinator, hass):
    """Situatie van 28 september 15:06. De zin komt uit de coordinator -
    logica in een dashboardsjabloon gaat stil kapot (v3.95.4)."""
    c = make_coordinator({})
    zin = c._verschuiving_en_bodem_zin(
        {"regelverschuiving_w": 50, "bodem_kwh": 1.296, "bodem_bindend": False}
    )
    uit = _reservekaart({
        "beschikbaar": True, "totaal_procent": 30.0, "diepste_tekort_kwh": 5.21,
        "reserve_kwh": 6.773, "vast_procent": 25.0, "dynamisch_procent": 5.0,
        "onderdelen": [{"naam": "Basis", "procent": 10.0, "soort": "vast"}],
        "verschuiving_en_bodem_zin": zin,
    })

    assert "50 W" in uit
    assert "1,30 kWh" in uit
    assert "nooit verkocht" in uit


def test_zonder_verschuiving_en_bodem_geen_zin(make_coordinator, hass):
    c = make_coordinator({})

    assert c._verschuiving_en_bodem_zin({"regelverschuiving_w": 0, "bodem_kwh": None}) == ""


def test_de_uitsplitsing_draagt_de_verschuiving_en_de_bodem(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reserve_margin_breakdown = {
        "base_percent": 10.0, "total_percent": 10.0,
        "needed_kwh_before_margin": 5.21, "reserve_kwh_after_margin": 5.73,
        "regelverschuiving_w": 50, "bodem_kwh": 1.296, "bodem_bindend": False,
    }

    overzicht = c.get_reserve_margin_overview()

    assert overzicht["regelverschuiving_w"] == 50
    assert overzicht["bodem_kwh"] == 1.296
