"""Werkelijke afrekening van Zonneplan naast de eigen berekening
(v1.6.0).

Gevraagd: "We zouden het financiele tabblad nog wat kunnen uitbreiden
middels waardes uit de zonneplan integratie?" - gevolgd door de
uitdrukkelijke eis: "Ik wil de entiteiten niet zelf invullen, deze
moeten automatisch uit de zonneplan integratie gehaald worden zonder
manuele config."

Dit is voor geld wat de Kirchhoff-check voor energie is: twee
onafhankelijke bronnen die hetzelfde zouden moeten zeggen.
"""
from custom_components.energy_management_system.const import (
    CONF_PRICE_SENSOR,
    RELIABILITY_INSUFFICIENT,
    RELIABILITY_NOT_CONFIGURED,
    RELIABILITY_RELIABLE,
    RELIABILITY_UNRELIABLE,
)

PRIJS = "sensor.zonneplan_current_quarter_hourly_electricity_tariff"
AFNAME = "sensor.zonneplan_electricity_delivery_costs_today"
TERUG = "sensor.zonneplan_electricity_production_costs_today"


def _coordinator(make_coordinator, prijs_entity=PRIJS):
    return make_coordinator({CONF_PRICE_SENSOR: prijs_entity})


# --- automatisch vinden ----------------------------------------------


def test_the_prefix_comes_from_the_price_sensor(make_coordinator, hass):
    """Geen extra configuratie nodig: wie de prijssensor heeft ingevuld,
    heeft de integratie draaien."""
    c = _coordinator(make_coordinator)

    assert c._zonneplan_prefix() == "sensor.zonneplan_"


def test_both_language_variants_are_found(make_coordinator, hass):
    """De integratie levert entity_id's in twee talen door elkaar,
    afhankelijk van wanneer de entiteit is aangemaakt."""
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "2.50")
    hass.states.set(
        "sensor.zonneplan_elektriciteitsleveringskosten_deze_maand", "45.0"
    )

    gevonden = c.find_zonneplan_cost_entities()

    assert gevonden["afname_vandaag"] == AFNAME
    assert gevonden["afname_deze_maand"].endswith("deze_maand")


def test_a_disabled_sensor_is_skipped(make_coordinator, hass):
    """Veel van deze sensoren staan standaard uit in Home Assistant. Een
    entiteit die bestaat maar geen waarde geeft is net zo onbruikbaar als
    een die niet bestaat."""
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "unavailable")

    assert "afname_vandaag" not in c.find_zonneplan_cost_entities()


def test_another_price_supplier_finds_nothing(make_coordinator, hass):
    """Wie geen Zonneplan gebruikt, hoort hier geen last van te hebben."""
    c = _coordinator(make_coordinator, prijs_entity="sensor.nordpool_tariff")

    assert c._zonneplan_prefix() is None
    assert c.find_zonneplan_cost_entities() == {}


def test_no_price_sensor_at_all(make_coordinator, hass):
    c = make_coordinator({})

    assert c.find_zonneplan_cost_entities() == {}


# --- de vergelijking -------------------------------------------------


def test_matching_costs_are_confirmed(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "3.00")
    hass.states.set(TERUG, "0.50")
    c.actual_cost_today_eur = 2.45

    vergelijking = c.get_zonneplan_cost_comparison()

    assert vergelijking["zonneplan_netto_eur"] == 2.5
    assert vergelijking["status"] == RELIABILITY_RELIABLE


def test_a_large_difference_is_flagged(make_coordinator, hass):
    """Loopt het uiteen, dan klopt er iets niet in de prijsafhandeling."""
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "3.00")
    hass.states.set(TERUG, "0.50")
    c.actual_cost_today_eur = 6.00

    vergelijking = c.get_zonneplan_cost_comparison()

    assert vergelijking["status"] == RELIABILITY_UNRELIABLE
    assert vergelijking["verschil_eur"] == 3.5
    assert "prijsattribuut" in vergelijking["reden"]


def test_the_threshold_scales_with_the_amount(make_coordinator, hass):
    """Bij een groot bedrag is 50 cent verschil verwaarloosbaar; bij een
    klein bedrag niet. Een vaste drempel zou het een van beide fout
    doen."""
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "100.00")
    hass.states.set(TERUG, "0")
    c.actual_cost_today_eur = 105.0

    assert c.get_zonneplan_cost_comparison()["status"] == RELIABILITY_RELIABLE


def test_without_sensors_it_explains_how_to_enable_them(
    make_coordinator, hass
):
    """Een ontbrekende sensor is normaal - dat mag geen foutmelding
    opleveren, hooguit een uitleg."""
    c = _coordinator(make_coordinator)

    vergelijking = c.get_zonneplan_cost_comparison()

    assert vergelijking["status"] == RELIABILITY_NOT_CONFIGURED
    assert "staan standaard uit" in vergelijking["reden"]


def test_sensors_present_but_no_value_yet(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    hass.states.set(
        "sensor.zonneplan_afname_gemiddelde_prijs_per_kwh_vandaag", "0.30"
    )

    assert (
        c.get_zonneplan_cost_comparison()["status"] == RELIABILITY_INSUFFICIENT
    )


def test_feed_in_is_subtracted(make_coordinator, hass):
    """Zonneplan splitst afname en teruglevering; onze eigen berekening
    is het netto bedrag."""
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "5.00")
    hass.states.set(TERUG, "2.00")
    c.actual_cost_today_eur = 3.00

    assert c.get_zonneplan_cost_comparison()["zonneplan_netto_eur"] == 3.0


# --- inbedding -------------------------------------------------------


def test_it_appears_in_the_reliability_overview(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    namen = {r["naam"] for r in c.get_reliability_overview()}

    assert "Kosten t.o.v. Zonneplan-afrekening" in namen


def test_it_is_on_the_financial_sensor(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        CounterfactualSavingsSensor,
    )

    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "3.00")

    attrs = CounterfactualSavingsSensor(c, "entry1").extra_state_attributes

    assert "zonneplan_vergelijking" in attrs


def test_no_configuration_field_was_added():
    """De eis was uitdrukkelijk: geen handmatige invoer. Een
    configuratieveld erbij zou die eis stilzwijgend omzeilen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "config_flow.py").read_text()

    assert "zonneplan" not in bron.lower()


# --- v1.6.1: wat dit wél en niet toetst ------------------------------


def test_both_sides_measure_the_same_meter():
    """Opgemerkt: "zonneplan kan financieel niets over de accu zeggen,
    hun kunnen niet zien wat accu verbruik, naar woning en pv naar
    woning etc is."

    Klopt - en juist daarom is de vergelijking geldig. Onze
    `actual_cost_today_eur` wordt berekend uit `p1_power_w`, precies
    dezelfde meter die Zonneplan afrekent. Zou hij uit accu- of
    PV-vermogen worden berekend, dan zou de vergelijking niets
    betekenen.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("actual_cost_eur = self._grid_flow_cost_eur(")
    blok = bron[start : start + 200]

    assert "p1_power_w" in blok


def test_the_explanation_names_what_is_not_covered(make_coordinator, hass):
    """De accu-boekhouding en de tegenfeitelijke besparing kunnen
    hiermee NIET worden bevestigd. Dat verzwijgen zou de vergelijking
    geloofwaardiger laten lijken dan ze is."""
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "3.00")

    vergelijking = c.get_zonneplan_cost_comparison()

    uitleg = vergelijking["wat_dit_toetst"]
    assert "achter de meter" in uitleg
    assert "tegenfeitelijke besparing" in uitleg


def test_the_verdict_mentions_the_p1_scope(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "3.00")
    hass.states.set(TERUG, "0.50")
    c.actual_cost_today_eur = 2.45

    assert "P1-meter" in c.get_zonneplan_cost_comparison()["reden"]


def test_the_dashboard_explains_the_limitation():
    """Op het tabblad staat de tegenfeitelijke besparing vlak boven deze
    vergelijking - zonder uitleg zou iemand kunnen denken dat Zonneplan
    dát bevestigt."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()
    plat = " ".join(yaml_tekst.split())

    assert "Wat dit níét toetst" in plat
    assert "weten niet eens dat er een accu staat" in plat


# --- v1.7.0: gas -----------------------------------------------------

GAS = "sensor.zonneplan_gas_delivery_costs_today"


def test_gas_is_found_automatically(make_coordinator, hass):
    """Gevraagd: "Zonneplan levert ook gas aan mij, dit graag meenemen in
    het financiele gedeelte." Zonder configuratie, net als de rest."""
    c = _coordinator(make_coordinator)
    hass.states.set(GAS, "0.1304714")

    assert c.find_zonneplan_cost_entities()["gas_vandaag"] == GAS


def test_the_total_adds_gas_to_net_electricity(make_coordinator, hass):
    """Zonder gas zijn de energiekosten maar half zichtbaar."""
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "3.00")
    hass.states.set(TERUG, "0.50")
    hass.states.set(GAS, "1.20")
    c.actual_cost_today_eur = 2.45

    vergelijking = c.get_zonneplan_cost_comparison()

    assert vergelijking["zonneplan_netto_eur"] == 2.5
    assert vergelijking["zonneplan_gas_vandaag_eur"] == 1.2
    assert vergelijking["totale_energiekosten_vandaag_eur"] == 3.7


def test_gas_does_not_affect_the_electricity_verdict(make_coordinator, hass):
    """Gas staat los: deze integratie berekent er niets aan, dus het mag
    het oordeel over de stroomberekening niet beïnvloeden."""
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "3.00")
    hass.states.set(TERUG, "0.50")
    hass.states.set(GAS, "50.00")
    c.actual_cost_today_eur = 2.45

    vergelijking = c.get_zonneplan_cost_comparison()

    assert vergelijking["status"] == RELIABILITY_RELIABLE
    assert vergelijking["verschil_eur"] == -0.05


def test_without_gas_the_total_is_just_electricity(make_coordinator, hass):
    """Niet iedereen heeft gas bij dezelfde leverancier."""
    c = _coordinator(make_coordinator)
    hass.states.set(AFNAME, "3.00")
    hass.states.set(TERUG, "0.50")
    c.actual_cost_today_eur = 2.45

    vergelijking = c.get_zonneplan_cost_comparison()

    assert vergelijking["zonneplan_gas_vandaag_eur"] is None
    assert vergelijking["totale_energiekosten_vandaag_eur"] == 2.5


def test_the_dashboard_hides_gas_when_there_is_none():
    """Een regel met "None €" is erger dan geen regel."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()

    assert "if z.get('zonneplan_gas_vandaag_eur') is not none" in yaml_tekst


def test_the_dashboard_says_gas_is_not_verified():
    """Gas wordt alleen getoond, niet getoetst - deze integratie
    berekent er niets aan. Dat verzwijgen zou suggereren dat het
    gecontroleerd is."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()
    plat = " ".join(yaml_tekst.split())

    assert "Gas wordt alleen getóónd, niet getoetst" in plat
    assert "alleen een dagtotaal" in plat
