"""GACS-zelfbeoordeling en verbetermogelijkheden (v1.10.0).

Gevraagd naar aanleiding van de RVO-pagina: "Ja graag uitwerken, met een
nieuw tabblad voor GACS zodat ik hier in het bedrijfsleven van kan
leren."

De GACS-verplichting geldt NIET voor woningen - alleen voor
utiliteitsgebouwen zonder woonfunctie boven 290 kW verwarmings- of
koelvermogen. Dit is een spiegel langs de vier functionele eisen uit het
Besluit Bouwwerken Leefomgeving, geen nalevingsbewijs.
"""
from custom_components.energy_management_system.const import (
    GACS_EFFICIENCY_ADVICE_PERCENT,
)


# --- de beoordeling is geen nalevingsbewijs --------------------------


def test_a_low_efficiency_produces_advice(make_coordinator, hass):
    c = make_coordinator({})
    c.learned_efficiency_history = [82.9] * 8

    advies = next(
        a
        for a in c.get_improvement_suggestions()
        if a["onderwerp"] == "Accu-rendement"
    )

    assert "82.9" in advies["waarneming"]
    assert "laadvermogen" in advies["advies"]


def test_a_good_efficiency_produces_none(make_coordinator, hass):
    """Advies geven waar niets te verbeteren valt, maakt de hele lijst
    waardeloos."""
    c = make_coordinator({})
    c.learned_efficiency_history = [GACS_EFFICIENCY_ADVICE_PERCENT + 5] * 8

    assert not any(
        a["onderwerp"] == "Accu-rendement"
        for a in c.get_improvement_suggestions()
    )


def test_low_self_consumption_produces_advice(make_coordinator, hass):
    c = make_coordinator({})
    c.pv_production_today_kwh = 12.9
    c.pv_export_today_kwh = 6.0

    advies = next(
        a
        for a in c.get_improvement_suggestions()
        if a["onderwerp"] == "Zelfconsumptie"
    )

    assert "teruglevertarief" in advies["advies"]


def test_a_drifting_device_produces_advice(make_coordinator, hass):
    """Concreet worden: niet "mogelijk defect" maar wat je kunt
    nakijken."""
    c = make_coordinator({})
    c.nilm_confirmed_devices = {
        "sensor.koelkast": {
            "friendly_name": "Koelkast schuur",
            "anomaly_detected": True,
        }
    }

    advies = next(
        a
        for a in c.get_improvement_suggestions()
        if "meer dan normaal" in a["onderwerp"]
    )

    assert "condensorroosters" in advies["advies"]
    assert "Koelkast schuur" in advies["waarneming"]


def test_integrated_pv_produces_advice(make_coordinator, hass):
    c = make_coordinator({})

    advies = next(
        a
        for a in c.get_improvement_suggestions()
        if a["onderwerp"] == "PV-dagopwek"
    )

    assert "onderschat" in advies["advies"]


def test_every_advice_has_an_observation_and_an_action(
    make_coordinator, hass
):
    """De derde eis vraagt om verbetermogelijkheden, niet om nog een
    melding. Elk advies moet dus zeggen wat er is gemeten én wat je
    ermee kunt."""
    c = make_coordinator({})
    c.learned_efficiency_history = [70.0] * 8
    c.pv_production_today_kwh = 10.0
    c.pv_export_today_kwh = 8.0

    adviezen = c.get_improvement_suggestions()

    assert adviezen
    for a in adviezen:
        assert a["waarneming"] and a["advies"]
        assert len(a["advies"]) > 50, a["onderwerp"]


# --- statusbepaling --------------------------------------------------


def test_de_eisenspiegel_is_weg(make_coordinator, hass):
    """v5.246.0: alleen de verbetermogelijkheden blijven; de vier GACS-eisen
    (niet van toepassing op een woning, door niets gelezen) zijn eruit."""
    c = make_coordinator({})
    c.get_improvement_suggestions = lambda: [{"titel": "x"}]
    assert c.get_gacs_assessment() == {"verbetermogelijkheden": [{"titel": "x"}]}
    from custom_components.energy_management_system import const
    assert not hasattr(const, "GACS_REQUIREMENTS")
