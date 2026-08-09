"""Loont het om de accu uit te breiden? (v1.19.0)

Gevraagd: "Is het mogelijk dat je een advies uitbrengt om mijn accu uit
te breiden? Nu heb ik 1 2400AC omvormer met 3 accumodules. Wat als ik er
1 omvormer met 1 accu bij koop en dan dus 2 omvormers met beide 2
modules. Het vermogen kan dan omhoog (ca 50%) en is het dan rendabel?"

De kernvraag is welke van twee dingen knelt: het VERMOGEN of de
CAPACITEIT. Dat bepaalt of een tweede omvormer of een extra module het
juiste antwoord is - en dat is uit de eigen meetgegevens te beantwoorden.

Bij deze installatie: hoogste uurverbruik 644 W tegen 1600 W
ontlaadvermogen (40% benutting), maar 7,7 kWh dagverbruik tegen 7,3 kWh
bruikbare capaciteit en twee tekort-nachten. Het vermogen knelt dus niet,
de capaciteit wel.
"""
from custom_components.energy_management_system.const import (
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_MIN_SOC_PERCENT,
)

# Het werkelijke geleerde profiel uit de export.
ECHT_PROFIEL = {
    0: 0.276, 1: 0.213, 2: 0.211, 3: 0.214, 4: 0.227, 5: 0.214,
    6: 0.211, 7: 0.203, 8: 0.312, 9: 0.318, 10: 0.353, 11: 0.644,
    12: 0.438, 13: 0.416, 14: 0.366, 15: 0.298, 16: 0.497, 17: 0.318,
    18: 0.298, 19: 0.295, 20: 0.342, 21: 0.349, 22: 0.379, 23: 0.300,
}


def _coordinator(make_coordinator, hass, profiel=None, tekorten=True,
                 capaciteit="8.6", ontlaad=1600.0):
    c = make_coordinator(
        {
            CONF_MANUAL_DISCHARGE_POWER: ontlaad,
            CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.cap",
            CONF_MIN_SOC_PERCENT: 15.0,
        }
    )
    hass.states.set("sensor.cap", capaciteit)
    c.hourly_consumption_profile = dict(profiel or ECHT_PROFIEL)
    c.reserve_daily_records = [
        {"date": f"2026-08-0{d}", "shortfall": tekorten and d >= 7, "excess": False}
        for d in range(4, 9)
    ]
    return c


# --- het gerapporteerde geval ----------------------------------------


def test_power_is_not_the_constraint(make_coordinator, hass):
    """Het hoogste geleerde uur is 644 W, tegen 1600 W ontlaadvermogen -
    op geen enkel uur wordt meer dan 40% benut."""
    advies = _coordinator(make_coordinator, hass).get_expansion_advice()

    assert advies["hoogste_uurverbruik_w"] == 644
    assert advies["vermogensbenutting_procent"] == 40
    assert advies["vermogen_knelt"] is False


def test_capacity_is_the_constraint(make_coordinator, hass):
    """7,7 kWh dagverbruik tegen 7,3 kWh bruikbaar, en twee
    tekort-nachten."""
    advies = _coordinator(make_coordinator, hass).get_expansion_advice()

    assert advies["dagverbruik_kwh"] == 7.7
    assert advies["bruikbare_capaciteit_kwh"] == 7.3
    assert advies["capaciteit_knelt"] is True


def test_it_advises_a_module_not_an_inverter(make_coordinator, hass):
    """Het antwoord op de vraag: een tweede omvormer voegt vermogen toe
    dat ongebruikt blijft."""
    advies = _coordinator(make_coordinator, hass).get_expansion_advice()

    assert "extra module" in advies["advies"]
    assert "ongebruikt blijft" in advies["advies"]


# --- de andere uitkomsten --------------------------------------------


def test_a_power_constrained_house_gets_an_inverter(make_coordinator, hass):
    """Bij een verbruik dat wél tegen het vermogen aan loopt, is een
    tweede omvormer juist het antwoord."""
    zwaar = {u: 1.5 for u in range(24)}
    c = _coordinator(
        make_coordinator, hass, profiel=zwaar, capaciteit="60.0", tekorten=False
    )

    advies = c.get_expansion_advice()

    assert advies["vermogen_knelt"] is True
    assert advies["capaciteit_knelt"] is False
    assert "tweede omvormer helpt" in advies["advies"]


def test_both_constrained_advises_both(make_coordinator, hass):
    zwaar = {u: 1.5 for u in range(24)}
    c = _coordinator(make_coordinator, hass, profiel=zwaar)

    advies = c.get_expansion_advice()

    assert "mét eigen modules" in advies["advies"]


def test_no_constraint_advises_nothing(make_coordinator, hass):
    """Uitbreiden aanraden waar niets knelt, kost geld zonder
    opbrengst."""
    licht = {u: 0.1 for u in range(24)}
    c = _coordinator(
        make_coordinator, hass, profiel=licht, capaciteit="30.0", tekorten=False
    )

    advies = c.get_expansion_advice()

    assert advies["vermogen_knelt"] is False
    assert advies["capaciteit_knelt"] is False
    assert "weinig op" in advies["advies"]


# --- eerlijkheid over de grenzen -------------------------------------


def test_it_states_its_limitations(make_coordinator, hass):
    """Negen dagen in augustus is geen jaar, en prijzen en garantie
    kent de integratie niet."""
    advies = _coordinator(make_coordinator, hass).get_expansion_advice()

    assert "winter" in advies["voorbehoud"]
    assert "prijzen" in advies["voorbehoud"]


def test_too_little_history_says_so(make_coordinator, hass):
    """Zonder verbruiksprofiel valt er niets te beoordelen."""
    c = _coordinator(make_coordinator, hass, profiel={0: 0.2, 1: 0.2})

    advies = c.get_expansion_advice()

    assert advies["beschikbaar"] is False
    assert "te weinig" in advies["reden"]


# --- inbedding -------------------------------------------------------


def test_it_is_in_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "expansion_advice" in bron


def test_it_is_on_the_battery_page():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    accu = next(v for v in data["views"] if v["path"] == "detail-accu")
    kaarten = [k for s in accu["sections"] for k in s.get("cards") or []]

    kaart = next(k for k in kaarten if "uitbreiden" in str(k.get("title", "")).lower())

    assert "vermogensbenutting_procent" in kaart["content"]
    assert "voorbehoud" in kaart["content"]
