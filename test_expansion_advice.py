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
    # v1.19.5: `hourly_consumption_profile` bevat per uur de LOSSE
    # metingen, niet het gemiddelde - dat was precies de fout die de
    # export aanwees. De testopstelling moet dezelfde structuur
    # gebruiken, anders toetst ze iets dat in productie niet bestaat.
    c.hourly_consumption_profile = {
        uur: [waarde] * 3 for uur, waarde in (profiel or ECHT_PROFIEL).items()
    }
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


def test_both_constrained_advises_the_cheapest_route(make_coordinator, hass):
    """v1.20.7: eerder werd hier "een tweede omvormer mét eigen modules"
    aangeraden. De fabrikantspecificatie laat zien dat dat te duur is:
    één omvormer draagt tot zes modules (17,28 kWh), dus capaciteit
    vraagt geen tweede omvormer.
    """
    zwaar = {u: 1.5 for u in range(24)}
    c = _coordinator(make_coordinator, hass, profiel=zwaar)

    advies = c.get_expansion_advice()

    assert "tot zes modules" in advies["advies"]
    assert "geen tweede omvormer voor nodig" in advies["advies"]


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


# --- v1.19.5: de fout die de export zelf aanwees --------------------


def test_it_uses_the_averaging_method(make_coordinator, hass):
    """Uit `internal_failures` in een export: "TypeError: unsupported
    operand type(s) for +: 'int' and 'list'".

    `hourly_consumption_profile` is `dict[int, list[float]]` - per uur de
    LOSSE metingen, niet het gemiddelde. Het advies gebruikte hem alsof
    er kant-en-klare getallen in stonden, waardoor `sum()` lijsten
    probeerde op te tellen.

    `learned_hourly_avg_kw()` doet die omrekening al en wordt ook door de
    export gebruikt.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("def get_expansion_advice")
    blok = bron[start : start + 2000]

    assert "learned_hourly_avg_kw" in blok
    assert "self.hourly_consumption_profile or {}" not in blok


def test_it_survives_the_real_structure(make_coordinator, hass):
    """De testopstelling gebruikte kant-en-klare getallen en toetste
    daarmee iets dat in productie niet bestaat - precies waarom deze
    fout niet eerder opviel."""
    c = _coordinator(make_coordinator, hass)

    for uur, waarden in c.hourly_consumption_profile.items():
        assert isinstance(waarden, list), uur

    advies = c.get_expansion_advice()

    assert advies["beschikbaar"] is True
    assert advies["dagverbruik_kwh"] > 0


# --- v1.20.4: het gemeten piekvermogen telt mee ---------------------


def test_a_measured_peak_above_the_inverter_counts(make_coordinator, hass):
    """Gevonden bij het volledig doorlichten van de diagnostiek: het
    hoogste geleerde UUR is 497 W, maar het gemeten piekvermogen 2199 W
    - ruim boven het ontlaadvermogen van 1600 W.

    Een uurgemiddelde verbergt dat: koken of een oven trekt minuten lang
    veel, en dat verdwijnt in het gemiddelde. Zo'n piek vraagt geen
    capaciteit, maar wél vermogen.
    """
    c = _coordinator(make_coordinator, hass)
    c.peak_power_all_time_w = 2199.0

    advies = c.get_expansion_advice()

    assert advies["gemeten_piekvermogen_w"] == 2199
    assert advies["vermogen_knelt"] is True


def test_a_modest_peak_does_not_trigger_it(make_coordinator, hass):
    """Onder het ontlaadvermogen is er niets aan de hand."""
    c = _coordinator(make_coordinator, hass)
    c.peak_power_all_time_w = 900.0

    advies = c.get_expansion_advice()

    assert advies["vermogen_knelt"] is False


def test_without_a_peak_measurement_it_still_works(make_coordinator, hass):
    """Een verse installatie heeft nog geen piek gemeten."""
    c = _coordinator(make_coordinator, hass)
    c.peak_power_all_time_w = None

    assert c.get_expansion_advice()["beschikbaar"] is True


# --- v1.20.6: echte prijzen en terugverdientijd ---------------------

def _met_kosten(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_BATTERY_MODULE_TEMPERATURE_SENSORS,
    )

    c = make_coordinator(
        {
            CONF_MANUAL_DISCHARGE_POWER: 1600.0,
            CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.cap",
            CONF_MIN_SOC_PERCENT: 15.0,
            CONF_BATTERY_MODULE_TEMPERATURE_SENSORS: ["a", "b", "c"],
        }
    )
    hass.states.set("sensor.cap", "8.6")
    c.hourly_consumption_profile = {
        uur: [waarde] * 3 for uur, waarde in ECHT_PROFIEL.items()
    }
    c.reserve_daily_records = [
        {"date": f"2026-08-{x:02d}", "shortfall": x >= 8, "excess": False}
        for x in range(5, 11)
    ]
    c.peak_power_all_time_w = 2199.0
    c.actual_cost_all_time_eur = -8.13
    c.counterfactual_cost_all_time_eur = -4.64
    return c


def test_the_cheapest_step_comes_first(make_coordinator, hass):
    """Het ontlaadvermogen staat op 1600 W terwijl de omvormer 2400 W
    aankan; dat dekt de gemeten piek van 2199 W zonder nieuwe hardware.

    v1.20.7: de fabrikantspecificatie corrigeert dit. Zendure schrijft:
    "have an electrician install it on a dedicated circuit without other
    loads... You can then request a power upgrade to 2400W via the app."

    Het was dus onterecht om dit "gratis" te noemen. Nog steeds de
    goedkoopste stap - maar met de voorwaarde erbij in plaats van
    eroverheen.
    """
    advies = _met_kosten(make_coordinator, hass).get_expansion_advice()

    assert advies["eerst_proberen"] is not None
    assert "2400 W aankan" in advies["eerst_proberen"]
    assert "eigen groep" in advies["eerst_proberen"]
    assert "elektricien" in advies["eerst_proberen"]


def test_no_free_option_when_the_setting_is_already_maxed(
    make_coordinator, hass
):
    c = _met_kosten(make_coordinator, hass)
    c.config = {**c.config, CONF_MANUAL_DISCHARGE_POWER: 2400.0}

    assert c.get_expansion_advice()["eerst_proberen"] is None


def test_the_payback_uses_the_real_prices(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        DEFAULT_BATTERY_INVERTER_PRICE_EUR,
        DEFAULT_BATTERY_MODULE_PRICE_EUR,
    )

    advies = _met_kosten(make_coordinator, hass).get_expansion_advice()

    assert advies["moduleprijs_eur"] == DEFAULT_BATTERY_MODULE_PRICE_EUR == 729.0
    assert advies["omvormerprijs_eur"] == DEFAULT_BATTERY_INVERTER_PRICE_EUR == 374.0


def test_an_extra_module_yields_less_than_the_average(make_coordinator, hass):
    """De eerste kilowattuur vangt de grootste prijsverschillen; wat
    daarna komt wordt alleen op dure dagen benut."""
    advies = _met_kosten(make_coordinator, hass).get_expansion_advice()

    per_module = advies["opbrengst_accu_per_jaar_eur"] / 3

    assert advies["opbrengst_extra_module_per_jaar_eur"] < per_module


def test_the_inverter_pays_back_faster_than_a_module(make_coordinator, hass):
    """Met 374 tegen 729 euro is dat wiskunde, maar het is wel de
    conclusie die de eerdere bundelprijs van 959 euro verborg."""
    advies = _met_kosten(make_coordinator, hass).get_expansion_advice()

    assert (
        advies["terugverdientijd_omvormer_jaar"]
        < advies["terugverdientijd_module_jaar"]
    )


def test_without_cost_history_there_is_no_payback(make_coordinator, hass):
    """Zonder gemeten voordeel valt er niets te berekenen."""
    c = _met_kosten(make_coordinator, hass)
    c.actual_cost_all_time_eur = None
    c.counterfactual_cost_all_time_eur = None

    advies = c.get_expansion_advice()

    assert advies["terugverdientijd_module_jaar"] is None


def test_one_inverter_carries_six_modules(make_coordinator, hass):
    """Uit de fabrikantspecificatie: "It supports AB3000X, with a
    maximum of 6 battery connections, expanding total capacity to
    17.28kWh."

    Dat is wezenlijk voor het advies: een vierde module heeft geen
    tweede omvormer nodig. Dat scheelt de aanschaf én een tweede groep,
    want meerdere omvormers moeten volgens Zendure op aparte circuits.
    """
    advies = _met_kosten(make_coordinator, hass).get_expansion_advice()

    assert advies["modules_mogelijk_op_deze_omvormer"] == 6
    assert advies["modules_nu"] == 3


def test_the_power_upgrade_names_its_condition(make_coordinator, hass):
    """Zonder die voorwaarde leest het als "even een instelling
    aanpassen", en dat is het niet."""
    advies = _met_kosten(make_coordinator, hass).get_expansion_advice()

    assert "zonder andere belasting" in advies["eerst_proberen"]


# --- v1.21.1: fabrieksgrenzen uit de handleiding --------------------


def test_the_charge_power_has_headroom_too(make_coordinator, hass):
    """Uit de handleiding (V1.2, sectie 9): accu laden/ontladen
    2400W/2600W max. Het laadvermogen staat op 2000 W.

    Dat raakt de tekort-nachten: bij dynamische prijzen tellen goedkope
    blokken van een kwartier, en sneller laden vangt meer kilowattuur
    binnen hetzelfde blok.
    """
    from custom_components.energy_management_system.const import (
        CONF_MANUAL_CHARGE_POWER,
        SOLARFLOW_MAX_BATTERY_CHARGE_W,
    )

    c = _met_kosten(make_coordinator, hass)
    c.config = {**c.config, CONF_MANUAL_CHARGE_POWER: -2000.0}

    advies = c.get_expansion_advice()

    assert advies["laadvermogen_w"] == 2000
    assert advies["laadvermogen_max_w"] == SOLARFLOW_MAX_BATTERY_CHARGE_W
    assert "goedkope kwartier" in advies["laadruimte_over"]


def test_the_charge_hint_names_the_same_condition(make_coordinator, hass):
    """Boven 800 W geldt de eis van een eigen groep - ook voor laden."""
    from custom_components.energy_management_system.const import (
        CONF_MANUAL_CHARGE_POWER,
    )

    c = _met_kosten(make_coordinator, hass)
    c.config = {**c.config, CONF_MANUAL_CHARGE_POWER: -2000.0}

    advies = c.get_expansion_advice()

    assert "eigen groep" in advies["laadruimte_over"]
    assert "elektricien" in advies["laadruimte_over"]


def test_a_maxed_charge_power_gives_no_hint(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_MANUAL_CHARGE_POWER,
        SOLARFLOW_MAX_BATTERY_CHARGE_W,
    )

    c = _met_kosten(make_coordinator, hass)
    c.config = {
        **c.config,
        CONF_MANUAL_CHARGE_POWER: -SOLARFLOW_MAX_BATTERY_CHARGE_W,
    }

    assert c.get_expansion_advice()["laadruimte_over"] is None


def test_the_limits_come_from_the_manual():
    """Vastgelegd zodat ze niet stilaan uit een aanname gaan bestaan."""
    from custom_components.energy_management_system.const import (
        SOLARFLOW_DEFAULT_GRID_POWER_W,
        SOLARFLOW_MAX_BATTERY_CHARGE_W,
        SOLARFLOW_MAX_GRID_POWER_W,
        SOLARFLOW_MAX_MODULES,
        SOLARFLOW_OPERATING_TEMP_MAX_C,
        SOLARFLOW_OPERATING_TEMP_MIN_C,
    )

    assert SOLARFLOW_MAX_GRID_POWER_W == 2400.0
    assert SOLARFLOW_DEFAULT_GRID_POWER_W == 800.0
    assert SOLARFLOW_MAX_BATTERY_CHARGE_W == 2400.0
    assert SOLARFLOW_MAX_MODULES == 6
    assert SOLARFLOW_OPERATING_TEMP_MIN_C == -20.0
    assert SOLARFLOW_OPERATING_TEMP_MAX_C == 60.0


# --- v1.21.2: bewust begrensd vermogen -------------------------------


def _bewust(make_coordinator, hass, bewust=True):
    from custom_components.energy_management_system.const import (
        CONF_MANUAL_CHARGE_POWER,
        CONF_POWER_LIMITS_INTENTIONAL,
    )

    c = _met_kosten(make_coordinator, hass)
    c.config = {
        **c.config,
        CONF_MANUAL_CHARGE_POWER: -2000.0,
        CONF_POWER_LIMITS_INTENTIONAL: bewust,
    }
    return c.get_expansion_advice()


def test_deliberate_limits_get_no_suggestions(make_coordinator, hass):
    """Gemeld: "Let wel op dat ik handmatig begrensd heb op 2000W laden
    1600W ontladen."

    Het advies zag alleen dat die onder de fabrieksgrens van 2400 liggen
    en raadde aan ze te verhogen. Dat is ongefundeerd: het zijn bewuste
    keuzes, en de redenen kent de integratie niet - de groep in de
    meterkast, cellen sparen, geluid, of gewoon marge willen houden.
    """
    advies = _bewust(make_coordinator, hass)

    assert advies["eerst_proberen"] is None
    assert advies["laadruimte_over"] is None
    assert advies["vermogen_bewust_begrensd"] is True


def test_without_the_flag_the_suggestions_return(make_coordinator, hass):
    """De instelling mag geen suggesties wegnemen bij wie ze wél wil."""
    advies = _bewust(make_coordinator, hass, bewust=False)

    assert advies["eerst_proberen"] is not None
    assert advies["laadruimte_over"] is not None


def test_the_verdict_changes_too(make_coordinator, hass):
    """"Verhoog het vermogen" is bij een bewuste grens geen advies maar
    een herhaling van iets dat al is afgewogen."""
    advies = _bewust(make_coordinator, hass)

    assert "bewust begrensd" in advies["advies"]
    assert "een keuze is en geen gebrek" in advies["advies"]


def test_the_capacity_advice_survives(make_coordinator, hass):
    """Wat wél overblijft moet blijven staan: de capaciteit knelt echt,
    en daar helpt een module."""
    advies = _bewust(make_coordinator, hass)

    assert advies["capaciteit_knelt"] is True
    assert "zes modules" in advies["advies"]


def test_the_setting_exists():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "config_flow.py").read_text()

    assert "CONF_POWER_LIMITS_INTENTIONAL" in bron
