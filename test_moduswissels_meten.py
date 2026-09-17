"""Hoe vaak wisselt het EMS van reden? (v4.19)

Gevraagd: "In de export zie ik tientallen wissels tussen
arbitrage_solar_capture en discharging_window op dezelfde middag."

Nagerekend over zes dagen dagverloop:

    09-11:  2 wissels    09-14: 12 wissels
    09-12:  5 wissels    09-15: 12 wissels
    09-13:  1 wissel     09-16:  2 wissels

Het paar arbitrage/discharging komt maximaal VIER keer per dag voor,
niet tientallen. Vier keer wisselen tussen "zon opvangen" en "huis
dekken" op een dag met wolkenvelden is normaal gedrag.

Maar dat was niet te zien zonder een script erbij. Daarom nu in de
export: het aantal wissels over 24 uur en over zeven dagen, de paren die
het vaakst wisselen, en een waarschuwing zodra het écht te veel wordt.

De grens is bewust hoog. Twaalf wissels op 96 kwartieren is 12% - dat is
een dag met wolken, niet geklapper. Pas boven de dertig per dag gaat het
om iets dat aandacht vraagt.
"""
import pytest


def _dag(c, datum, redenen):
    c.dagverloop = dict(c.dagverloop or {})
    c.dagverloop[datum] = [
        {"tijd": f"{i // 4:02d}:{(i % 4) * 15:02d}", "reden": r}
        for i, r in enumerate(redenen)
    ]


def test_de_wissels_van_een_dag_worden_geteld(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-16", ["a", "a", "b", "b", "a", "c"])

    uit = c.get_redenwissels()

    assert uit["wissels_24h"] == 3


def test_de_vaakst_wisselende_paren(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-15", ["a", "b", "a", "b", "a", "c"])

    uit = c.get_redenwissels()

    assert uit["meest_gewisselde_paren"][0]["paar"] == ["a", "b"]
    assert uit["meest_gewisselde_paren"][0]["aantal"] == 4


def test_zeven_dagen_samen(make_coordinator, hass):
    c = make_coordinator({})
    for d in range(10, 17):
        _dag(c, f"2026-09-{d:02d}", ["a", "b", "a"])

    uit = c.get_redenwissels()

    assert uit["wissels_7d"] == 14
    assert uit["dagen_geteld"] == 7


def test_een_rustige_dag_geeft_geen_waarschuwing(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-16", ["a"] * 90 + ["b"] * 6)

    uit = c.get_redenwissels()

    assert uit["te_veel"] is False
    assert "normaal" in uit["oordeel"].lower() or "rustig" in uit["oordeel"].lower()


def test_echt_geklapper_geeft_wel_een_waarschuwing(make_coordinator, hass):
    """Elk kwartier een andere reden - dat is geen wolkenveld meer."""
    from custom_components.energy_management_system.const import (
        MODUSWISSELS_TE_VEEL_PER_DAG,
    )

    c = make_coordinator({})
    _dag(c, "2026-09-16", ["a" if i % 2 else "b" for i in range(96)])

    uit = c.get_redenwissels()

    assert uit["wissels_24h"] > MODUSWISSELS_TE_VEEL_PER_DAG
    assert uit["te_veel"] is True
    assert uit["meest_gewisselde_paren"][0]["paar"] == ["a", "b"]


def test_de_gemeten_werkelijkheid_is_geen_geklapper(make_coordinator, hass):
    """De grens staat zo dat Ruuds drukste dag (12 wissels) er niet
    onder valt - anders waarschuwt de integratie over normaal weer."""
    from custom_components.energy_management_system.const import (
        MODUSWISSELS_TE_VEEL_PER_DAG,
    )

    assert MODUSWISSELS_TE_VEEL_PER_DAG > 12


def test_zonder_dagverloop_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}

    uit = c.get_redenwissels()

    assert uit["wissels_24h"] == 0
    assert uit["te_veel"] is False


# --- v4.20: gemiddelde tijd in een reden ------------------------------
#
# Gevraagd als vierde observatiemeter. Dit is het getal dat zegt of
# wissels geklapper zijn: vier wissels op een dag betekent gemiddeld zes
# uur per reden, en dat is rustig. Vierentwintig wissels betekent een
# uur, en dan is er iets aan de hand.
#
# Observatiemeter, geen ratel: er wordt niets op gestuurd.


def test_de_gemiddelde_tijd_per_reden(make_coordinator, hass):
    c = make_coordinator({})
    # 96 kwartieren, 4 blokken van 24 = gemiddeld 6 uur per reden
    _dag(c, "2026-09-16", ["a"] * 24 + ["b"] * 24 + ["c"] * 24 + ["d"] * 24)

    uit = c.get_redenwissels()

    assert uit["gemiddelde_tijd_in_reden_minuten"] == pytest.approx(360, abs=1)


def test_geklapper_geeft_een_korte_tijd(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-16", ["a" if i % 2 else "b" for i in range(96)])

    uit = c.get_redenwissels()

    assert uit["gemiddelde_tijd_in_reden_minuten"] == pytest.approx(15, abs=1)


def test_een_dag_zonder_wissel(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-16", ["a"] * 96)

    uit = c.get_redenwissels()

    assert uit["gemiddelde_tijd_in_reden_minuten"] == pytest.approx(1440, abs=1)


def test_de_tijd_per_reden_apart(make_coordinator, hass):
    """Welke reden lang aanstaat en welke kort - dat zegt meer dan het
    gemiddelde."""
    c = make_coordinator({})
    _dag(c, "2026-09-16", ["a"] * 80 + ["b", "a", "b", "a"] + ["a"] * 12)

    uit = c.get_redenwissels()

    assert uit["tijd_per_reden_minuten"]["a"] > uit["tijd_per_reden_minuten"]["b"]
