"""Zelfcontrole op onmogelijke waarden (v1.9.5).

Gevraagd: "Heb je de diagnostiek nu zo goed nagekeken dat daar niets meer
uit te herleiden valt?"

Het eerlijke antwoord was nee. De export heeft ~200 velden en er waren er
handmatig veertig echt bekeken. Het accu-rendement van 8290% viel pas op
toen de HELE betrouwbaarheidslijst werd uitgeprint in plaats van alleen
de statussen.

Zo'n fout hoort de integratie zelf te vinden.
"""
from custom_components.energy_management_system.const import (
    PLAUSIBILITY_RULES,
)


# --- de twee fouten van vandaag --------------------------------------


def test_the_8290_percent_efficiency_would_be_caught(make_coordinator, hass):
    """De vondst van v1.9.4, die alleen opviel door toevallig goed te
    kijken."""
    c = make_coordinator({})
    c.learned_efficiency_percent = 8290.0

    velden = {w["veld"] for w in c.get_plausibility_warnings()}

    assert "learned_efficiency_percent" in velden


def test_the_negative_self_consumption_would_be_caught(
    make_coordinator, hass
):
    """De vondst van v1.9.2: -244,6% waar een aandeel tussen 0 en 100
    hoort te liggen."""
    c = make_coordinator({})
    c.zelfconsumptie_ratio_percent = -244.6

    velden = {w["veld"] for w in c.get_plausibility_warnings()}

    assert "zelfconsumptie_ratio_percent" in velden


# --- de regelkeuze ---------------------------------------------------


def test_the_most_specific_rule_wins(make_coordinator, hass):
    """"_ratio_percent" moet voorgaan op "_percent". Anders krijgt een
    aandeel de ruime percentage-grenzen en glipt -244% er alsnog
    doorheen."""
    c = make_coordinator({})
    c.iets_ratio_percent = 150.0

    waarschuwing = next(
        w for w in c.get_plausibility_warnings() if "ratio" in w["veld"]
    )

    assert waarschuwing["soort"] == "aandeel"


def test_a_soc_above_100_is_impossible(make_coordinator, hass):
    c = make_coordinator({})
    c.module_soc_percent = 150.0

    assert any(
        w["veld"] == "module_soc_percent" for w in c.get_plausibility_warnings()
    )


# --- geen vals alarm -------------------------------------------------


def test_normal_values_produce_no_warnings(make_coordinator, hass):
    """Een verse coordinator hoort schoon te zijn - anders wordt de
    melding meteen genegeerd."""
    c = make_coordinator({})

    assert c.get_plausibility_warnings() == []


def test_a_realistic_set_stays_clean(make_coordinator, hass):
    c = make_coordinator({})
    c.learned_efficiency_percent = 82.9
    c.zelfconsumptie_ratio_percent = 64.0
    c.module_soc_percent = 17.0
    c.pv_production_today_kwh = 12.9
    c.actual_cost_today_eur = -1.31

    assert c.get_plausibility_warnings() == []


def test_a_negative_spread_is_allowed(make_coordinator, hass):
    """Een negatieve spreiding tussen inkoop en teruglevering kan echt
    voorkomen; die mag geen alarm geven."""
    c = make_coordinator({})
    c.feedin_import_spread_eur_per_kwh = -0.02

    assert c.get_plausibility_warnings() == []


def test_booleans_and_text_are_skipped(make_coordinator, hass):
    c = make_coordinator({})
    c.iets_percent = "onbekend"
    c.andere_percent = True

    assert c.get_plausibility_warnings() == []


# --- inbedding -------------------------------------------------------


def test_it_becomes_an_attention_point(make_coordinator, hass):
    """Een fysiek onmogelijke waarde is altijd een rekenfout en hoort
    niet stilzwijgend in een export te blijven staan."""
    c = make_coordinator({})
    c.learned_efficiency_percent = 8290.0

    melding = next(
        p
        for p in c.get_diagnostic_summary()["aandachtspunten"]
        if "Onmogelijke waarde" in p
    )

    assert "8290" in melding
    assert "rekenfout" in melding


def test_every_rule_has_a_sane_range():
    for fragment, minimum, maximum, omschrijving in PLAUSIBILITY_RULES:
        assert minimum < maximum, fragment
        assert omschrijving, fragment
