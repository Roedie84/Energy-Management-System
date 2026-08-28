"""De instellingen van het apparaat tegen die van de berekening
(v3.53.0).

Gevraagd: "De properties/report moeten ook in de diagnostiek zitten om
de integratie te verbeteren."

Bewust NIET door dat adres zelf uit te lezen - dat is een tweede bron
van waarheid naast de Zendure-integratie, en precies daar zijn we op 26
augustus twee dagen aan kwijt geweest. Wel de entiteiten die die
integratie al maakt.

De aanleiding staat in dezelfde momentopname:

    minSoc: 50        het apparaat houdt 5% aan
    EMS rekent met                      10%

Die 5% was de kalibratie-instelling van een week eerder. EMS plande dus
met een bodem van 10 terwijl de accu doorliep tot 5, en in de nacht van
27 op 28 augustus kwam module 1 op 0% uit met een cel op 2,71 V.

Een instelling die in het apparaat anders staat dan waar de berekening
mee rekent, is niet van buitenaf te zien.
"""
import pytest

from custom_components.energy_management_system.const import (
    CONF_BATTERY_MAX_CHARGE_POWER_ENTITY,
    CONF_BATTERY_MAX_DISCHARGE_POWER_ENTITY,
    CONF_BATTERY_MAX_SOC_NUMBER,
    CONF_BATTERY_MIN_SOC_NUMBER,
    CONF_MANUAL_CHARGE_POWER,
    CONF_MANUAL_DISCHARGE_POWER,
    SPIEGEL_MARGE_INSTELLING_PROCENT,
)


def _regel(c, naam):
    return next(
        (r for r in c.get_spiegelcontrole() if r["naam"] == naam), None
    )


# --- de ondergrens: de storing van 28 augustus -----------------------


def test_a_floor_that_differs_is_caught(make_coordinator, hass):
    """Het apparaat op 5%, de berekening op 10%."""
    c = make_coordinator(
        {CONF_BATTERY_MIN_SOC_NUMBER: "number.min_soc"}
    )
    hass.states.set("number.min_soc", "5.0")
    c.effective_min_soc_percent = lambda: 10.0

    regel = _regel(c, "Ondergrens van de accu")

    assert regel["oordeel"] == "loopt_uiteen"
    assert regel["verschil"] == 5.0


def test_a_matching_floor_passes(make_coordinator, hass):
    c = make_coordinator({CONF_BATTERY_MIN_SOC_NUMBER: "number.min_soc"})
    hass.states.set("number.min_soc", "10.0")
    c.effective_min_soc_percent = lambda: 10.0

    assert _regel(c, "Ondergrens van de accu")["oordeel"] == "sluit_aan"


def test_rounding_is_allowed(make_coordinator, hass):
    """Nul zou te streng zijn - een number-entiteit rondt af."""
    c = make_coordinator({CONF_BATTERY_MIN_SOC_NUMBER: "number.min_soc"})
    hass.states.set(
        "number.min_soc", str(10.0 + SPIEGEL_MARGE_INSTELLING_PROCENT - 0.5)
    )
    c.effective_min_soc_percent = lambda: 10.0

    assert _regel(c, "Ondergrens van de accu")["oordeel"] == "sluit_aan"


# --- de vermogens ----------------------------------------------------


# --- optioneel blijft optioneel --------------------------------------


def test_an_unconfigured_setting_is_simply_absent(make_coordinator, hass):
    """Wie ze niet koppelt, mist alleen de controle - geen bevinding en

    geen foutmelding.
    """
    c = make_coordinator({})

    for naam in (
        "Ondergrens van de accu",
        "Bovengrens van de accu",
        "Maximaal laadvermogen",
        "Maximaal ontlaadvermogen",
    ):
        assert _regel(c, naam) is None


def test_a_missing_entity_is_not_a_finding(make_coordinator, hass):
    c = make_coordinator({CONF_BATTERY_MIN_SOC_NUMBER: "number.weg"})

    assert _regel(c, "Ondergrens van de accu")["oordeel"] == (
        "niet_te_vergelijken"
    )


# --- en het komt in de zelfcontrole ----------------------------------


def test_a_differing_setting_becomes_a_finding(make_coordinator, hass):
    c = make_coordinator({CONF_BATTERY_MIN_SOC_NUMBER: "number.min_soc"})
    hass.states.set("number.min_soc", "5.0")
    c.effective_min_soc_percent = lambda: 10.0

    namen = [b["naam"] for b in c.get_consistency_checks()["bevindingen"]]

    assert "Spiegel: Ondergrens van de accu" in namen


# --- het teken (v3.54.0) ---------------------------------------------


# --- de standaardwaarden (v3.54.0) -----------------------------------


def test_the_known_entities_have_a_default():
    """Gevraagd: "Alles wat nu goed en bekend is moet hard in de code

    staan om verwarring te voorkomen."

    Als standaardwaarde in plaats van hard ingebakken. Het verschil
    telt: deze week braken drie dingen doordat een naam of adres
    veranderde, en hard ingebakken namen breken dan STIL.
    """
    from custom_components.energy_management_system.const import (
        STANDAARD_ENTITEITEN,
    )

    assert STANDAARD_ENTITEITEN[CONF_BATTERY_MIN_SOC_NUMBER] == (
        "number.solarflow_2400_ac_min_soc"
    )
    # v3.55.0: de twee vermogensgrenzen staan hier BEWUST NIET bij.
    assert CONF_BATTERY_MAX_CHARGE_POWER_ENTITY not in STANDAARD_ENTITEITEN
    # v3.59.0: de twee energiemeters zijn erbij gekomen.
    assert len(STANDAARD_ENTITEITEN) == 4


def test_the_default_is_used_when_nothing_is_configured():
    """Er hoeft niets ingevuld te worden - het staat meteen goed."""
    from custom_components.energy_management_system.config_flow import (
        _optioneel,
    )

    veld = _optioneel(CONF_BATTERY_MIN_SOC_NUMBER, {})

    assert veld.default() == "number.solarflow_2400_ac_min_soc"


def test_a_configured_value_always_wins():
    """Wie hem hernoemt of een ander merk gebruikt, kan hem aanpassen

    zonder de code in.
    """
    from custom_components.energy_management_system.config_flow import (
        _optioneel,
    )

    veld = _optioneel(
        CONF_BATTERY_MIN_SOC_NUMBER,
        {CONF_BATTERY_MIN_SOC_NUMBER: "number.iets_anders"},
    )

    assert veld.default() == "number.iets_anders"


def test_the_power_limits_are_not_compared(make_coordinator, hass):
    """Gemeld: "Maximale ontlaadvermogen is hard in de software van

    Zendure begrensd op 1600 W, oplaadvermogen op 2000 W. Dit heeft
    niets met HA te maken maar is geconfigureerd in de Zendure-app in de
    veiligheidsinstellingen."

    De sensoren tonen iets anders - 2400 en 2000 - dus die meten niet
    die instellingen. Vergelijken levert dan ALTIJD "loopt uiteen" op,
    en dat is geen signaal maar ruis.

    Ruis is hier het gevaarlijkst wat er is: wie elke dag twee valse
    meldingen ziet, kijkt over de echte heen.
    """
    c = make_coordinator(
        {
            CONF_BATTERY_MAX_CHARGE_POWER_ENTITY: "sensor.laadlimiet",
            CONF_BATTERY_MAX_DISCHARGE_POWER_ENTITY: "sensor.ontlaadlimiet",
            CONF_MANUAL_CHARGE_POWER: -2000,
            CONF_MANUAL_DISCHARGE_POWER: 1600,
        }
    )
    hass.states.set("sensor.laadlimiet", "2400")
    hass.states.set("sensor.ontlaadlimiet", "2000")

    assert _regel(c, "Maximaal laadvermogen") is None
    assert _regel(c, "Maximaal ontlaadvermogen") is None


def test_the_settings_that_do_match_remain(make_coordinator, hass):
    """De ondergrens blijft, en dat is degene die er toe doet: 5 tegen 10

    kostte module 1 een nacht op 2,71 V.
    """
    c = make_coordinator({CONF_BATTERY_MIN_SOC_NUMBER: "number.min_soc"})
    hass.states.set("number.min_soc", "5.0")
    c.effective_min_soc_percent = lambda: 10.0

    assert _regel(c, "Ondergrens van de accu")["oordeel"] == "loopt_uiteen"


def test_the_phase_sensors_have_a_default():
    """Gevraagd: "Ik wil dit niet allemaal in de config zelf doen, ik

    raak daardoor het overzicht kwijt."

    Een instelling met meerdere entiteiten heeft een lijst als
    standaardwaarde, en die past niet in dezelfde dict.
    """
    from custom_components.energy_management_system.const import (
        CONF_PHASE_POWER_SENSORS,
        STANDAARD_ENTITEITLIJSTEN,
    )

    fasen = STANDAARD_ENTITEITLIJSTEN[CONF_PHASE_POWER_SENSORS]

    assert len(fasen) == 3
    assert fasen[0].endswith("_l1")
    assert fasen[2].endswith("_l3")


def test_the_energy_meters_have_a_default():
    from custom_components.energy_management_system.const import (
        CONF_DISHWASHER_ENERGY_SENSOR,
        CONF_WASHING_MACHINE_ENERGY_SENSOR,
        STANDAARD_ENTITEITEN,
    )

    assert STANDAARD_ENTITEITEN[CONF_DISHWASHER_ENERGY_SENSOR] == (
        "sensor.vaatwasser_energy_import"
    )
    assert STANDAARD_ENTITEITEN[CONF_WASHING_MACHINE_ENERGY_SENSOR] == (
        "sensor.wasmachine_energy_import"
    )


def test_nothing_needs_to_be_filled_in():
    """De kern van het verzoek: er hoeft niets ingevuld te worden.

    Als standaardwaarde en niet hard ingebakken, want hard ingebakken
    namen breken STIL - de configuratiecontrole meldt "bestaat niet" en
    verder gebeurt er niets.
    """
    from custom_components.energy_management_system.config_flow import (
        _optioneel,
    )
    from custom_components.energy_management_system.const import (
        CONF_PHASE_POWER_SENSORS,
        STANDAARD_ENTITEITEN,
        STANDAARD_ENTITEITLIJSTEN,
    )

    for sleutel in list(STANDAARD_ENTITEITEN) + list(STANDAARD_ENTITEITLIJSTEN):
        veld = _optioneel(sleutel, {})

        assert veld.default() not in (None, ""), sleutel

    assert _optioneel(CONF_PHASE_POWER_SENSORS, {}).default() == (
        STANDAARD_ENTITEITLIJSTEN[CONF_PHASE_POWER_SENSORS]
    )
