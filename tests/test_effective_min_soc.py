"""De werkelijke minimum-SoC (v1.23.3).

Gemeld: "Laagste SoC kan nooit 0% zijn, minimale SoC van mijn accu is
10%." En op de vraag of er nog andere grenzen waren: "Nee er is 1 harde
begrenzing van 10% verder nergens."

De configuratie stond op 15% terwijl de accu op 10% staat. Dat maakte
0,43 kWh onbruikbaar in élke berekening: de reserve hield te veel
achter, het uitbreidingsadvies zag een kleinere accu, de SoC-percentages
klopten niet en tekort-nachten werden eerder gemeld dan nodig.

De omvormer weet het zelf - `number.solarflow_2400_ac_min_soc` stond al
geconfigureerd, maar werd op één plek gebruikt terwijl het handmatige
getal de berekeningen bepaalde.
"""
from custom_components.energy_management_system.const import (
    CONF_BATTERY_MIN_SOC_NUMBER,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_MIN_SOC_PERCENT,
)


def _coordinator(make_coordinator, hass, gemeten="10", ingesteld=15.0):
    c = make_coordinator(
        {
            CONF_BATTERY_MIN_SOC_NUMBER: "number.min_soc",
            CONF_MIN_SOC_PERCENT: ingesteld,
            CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.cap",
        }
    )
    hass.states.set("sensor.cap", "8.6")
    if gemeten is not None:
        hass.states.set("number.min_soc", gemeten)
    return c


# --- de gemeten waarde gaat voor -------------------------------------


def test_the_measured_minimum_wins(make_coordinator, hass):
    """De accu weet het zelf; het handmatige getal is een aanname."""
    c = _coordinator(make_coordinator, hass)

    assert c.effective_min_soc_percent() == 10.0


def test_it_falls_back_to_the_setting(make_coordinator, hass):
    """Zonder meting is het ingestelde getal het beste dat er is."""
    c = _coordinator(make_coordinator, hass, gemeten="unavailable")

    assert c.effective_min_soc_percent() == 15.0


def test_an_implausible_reading_is_ignored(make_coordinator, hass):
    """Een sensor die 120% meldt, mag de berekening niet omgooien."""
    c = _coordinator(make_coordinator, hass, gemeten="120")

    assert c.effective_min_soc_percent() == 15.0


def test_without_the_entity_the_setting_is_used(make_coordinator, hass):
    c = make_coordinator({CONF_MIN_SOC_PERCENT: 12.0})

    assert c.effective_min_soc_percent() == 12.0


# --- wat het uitmaakt ------------------------------------------------


def test_the_usable_capacity_grows(make_coordinator, hass):
    """0,43 kWh die eerder als onbruikbaar werd gerekend."""
    c = _coordinator(make_coordinator, hass)

    bruikbaar = 8.6 * (100 - c.effective_min_soc_percent()) / 100

    assert abs(bruikbaar - 7.74) < 0.01


def test_every_calculation_uses_it():
    """Het handmatige getal bepaalde vijf berekeningen; die horen
    allemaal de gemeten waarde te gebruiken."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert bron.count("effective_min_soc_percent()") >= 5


# --- tekort zichtbaar ------------------------------------------------


def test_a_shortfall_quarter_is_flagged(make_coordinator, hass):
    """0% van de bruikbare capaciteit betekent dat de accu op zijn harde
    ondergrens staat en het huis aan het net hangt - dat is geen gewone
    regel maar een waarschuwing."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert '"tekort": tekort,' in bron
    assert '"tekort_kwartieren"' in bron


def test_the_summary_shows_the_hard_floor():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    pagina = next(
        v for v in data["views"] if v.get("path") == "detail-planning-samenvatting"
    )
    kaarten = [k for s in pagina["sections"] for k in s.get("cards") or []]
    inhoud = " ".join(str(k.get("content", "")) for k in kaarten)

    assert "tekort_kwartieren" in inhoud
    assert "min_soc_procent_hard" in inhoud
