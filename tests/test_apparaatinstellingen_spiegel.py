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


def test_a_changed_charge_limit_is_caught(make_coordinator, hass):
    """Gemeten op 26 en 27 augustus: `chargeMaxLimit` ging van 2000 naar

    2400 en `inverseMaxPower` van 1600 naar 2000, zonder dat de
    berekening dat wist.
    """
    c = make_coordinator(
        {
            CONF_BATTERY_MAX_CHARGE_POWER_ENTITY: "number.laadlimiet",
            CONF_MANUAL_CHARGE_POWER: 2000,
        }
    )
    hass.states.set("number.laadlimiet", "2400")

    assert _regel(c, "Maximaal laadvermogen")["oordeel"] == "loopt_uiteen"


def test_a_changed_discharge_limit_is_caught(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_BATTERY_MAX_DISCHARGE_POWER_ENTITY: "number.ontlaadlimiet",
            CONF_MANUAL_DISCHARGE_POWER: 1600,
        }
    )
    hass.states.set("number.ontlaadlimiet", "2000")

    assert _regel(c, "Maximaal ontlaadvermogen")["oordeel"] == "loopt_uiteen"


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


def test_the_sign_convention_does_not_cause_a_false_alarm(
    make_coordinator, hass
):
    """Gemeten in de export van 28 augustus 10:55, meteen na het

    koppelen:

        Maximaal laadvermogen  -2000,0 vs 2400,0 W -> loopt_uiteen

    Het laadvermogen is in deze integratie NEGATIEF - laden is negatief -
    terwijl het apparaat een positieve grens meldt. Rechtstreeks
    vergelijken loopt dan per definitie uiteen, en dan is de melding geen
    signaal meer.
    """
    c = make_coordinator(
        {
            CONF_BATTERY_MAX_CHARGE_POWER_ENTITY: "sensor.laadlimiet",
            CONF_MANUAL_CHARGE_POWER: -2000,
        }
    )
    hass.states.set("sensor.laadlimiet", "2000")

    assert _regel(c, "Maximaal laadvermogen")["oordeel"] == "sluit_aan"


def test_a_real_difference_still_shows(make_coordinator, hass):
    """Wat er ná die correctie overblijft is wél een echt verschil: de

    accu kan 2400 W laden terwijl de berekening met 2000 rekent.
    """
    c = make_coordinator(
        {
            CONF_BATTERY_MAX_CHARGE_POWER_ENTITY: "sensor.laadlimiet",
            CONF_MANUAL_CHARGE_POWER: -2000,
        }
    )
    hass.states.set("sensor.laadlimiet", "2400")

    regel = _regel(c, "Maximaal laadvermogen")

    assert regel["oordeel"] == "loopt_uiteen"
    assert regel["verschil"] == 400.0


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
    assert STANDAARD_ENTITEITEN[CONF_BATTERY_MAX_CHARGE_POWER_ENTITY] == (
        "sensor.solarflow_2400_ac_charge_max_limit"
    )
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
