"""Een terugval mag, zolang hij vers is (v3.50.0).

Gevraagd: "Graag de gehele integratie hierop nakijken, alle parameters
dienen geverifieerd te worden om fouten te voorkomen."

Bij het nalopen bleek dat `beschikbare_energie_kwh()` exact dezelfde
half-afgemaakte reparatie droeg als `accustand_procent()`. De toelichting
van v1.24.1 zegt het goed - "dat veld is een bijproduct van die check,
geen betrouwbare accustand" - en liet het veld daarna alsnog als terugval
staan.

Eerst heb ik die terugval geschrapt. Achtenveertig toetsen vielen om, en
dat was terecht: bij een sensor die één ronde niets zegt is een waarde
van een minuut geleden prima. De aansturing stilzetten bij elke hapering
is erger dan het kwaad.

Het probleem is niet de terugval maar de LEEFTIJD ervan. Op 27 augustus
stond de accustand op 38% terwijl de accu op 6% zat - een waarde uit de
nacht. Een minuut oud is bruikbaar, vijf uur niet, en zonder tijdstempel
is dat verschil niet te zien.
"""
from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_SOC_SENSOR,
    METING_MAX_LEEFTIJD_MINUTEN,
)


def _config():
    return {
        CONF_SOC_SENSOR: "sensor.soc",
        CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
    }


def _ouderdom(c, veld, minuten):
    c.meting_tijdstippen[veld] = dt_util.now() - timedelta(minutes=minuten)


# --- de beschikbare energie ------------------------------------------


def test_a_fresh_value_bridges_a_hiccup(make_coordinator, hass):
    """Een sensor die één ronde niets zegt mag de aansturing niet

    stilzetten.
    """
    c = make_coordinator(_config())
    c.last_available_kwh = 4.2
    _ouderdom(c, "last_available_kwh", 1)

    assert c.beschikbare_energie_kwh() == 4.2


def test_a_stale_value_is_refused(make_coordinator, hass):
    """De storing van 27 augustus: een waarde uit de nacht."""
    c = make_coordinator(_config())
    c.last_available_kwh = 4.2
    _ouderdom(c, "last_available_kwh", 300)

    assert c.beschikbare_energie_kwh() != 4.2


def test_the_live_sensor_always_wins(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set("sensor.beschikbaar", "0.4")
    c.last_available_kwh = 4.2
    _ouderdom(c, "last_available_kwh", 1)

    assert c.beschikbare_energie_kwh() == 0.4


@pytest.mark.parametrize(
    "minuten,bruikbaar",
    [(0.5, True), (METING_MAX_LEEFTIJD_MINUTEN - 1, True),
     (METING_MAX_LEEFTIJD_MINUTEN + 1, False), (600, False)],
)
def test_the_age_limit_is_the_deciding_factor(
    make_coordinator, hass, minuten, bruikbaar
):
    c = make_coordinator(_config())
    c.last_available_kwh = 4.2
    _ouderdom(c, "last_available_kwh", minuten)

    assert (c.beschikbare_energie_kwh() == 4.2) is bruikbaar


# --- de accustand ----------------------------------------------------


def test_the_same_rule_holds_for_the_state_of_charge(
    make_coordinator, hass
):
    """Twee helpers met dezelfde vorm horen dezelfde regel te volgen -

    anders is de reparatie weer half, en dat is precies wat er tussen 11
    en 27 augustus misging.
    """
    c = make_coordinator(_config())
    c.last_soc_percent = 38.0
    _ouderdom(c, "last_soc_percent", 300)

    assert c.accustand_procent() is None

    _ouderdom(c, "last_soc_percent", 1)

    assert c.accustand_procent() == 38.0


# --- de tijdstempels zelf --------------------------------------------


def test_every_writer_records_the_moment(make_coordinator, hass):
    """Zonder tijdstempel bij het schrijven meet de leeftijdstoets niets."""
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C)
    for veld in ("last_soc_percent", "last_available_kwh"):
        schrijvers = bron.count(f"self.{veld} = ")
        onthouden = bron.count(f'self._onthoud_meting("{veld}")')

        # Elke schrijver die een WAARDE zet, legt het moment vast. De
        # regels die op None zetten hoeven dat niet.
        assert onthouden >= schrijvers - 2, (
            f"{veld}: {schrijvers} schrijvers, {onthouden} tijdstempels"
        )


def test_the_timestamps_do_not_survive_a_restart(make_coordinator, hass):
    """Na een herstart is er niets vers - dan hoort de sensor gelezen te

    worden, niet een waarde van voor de herstart.
    """
    c = make_coordinator(_config())

    assert c.meting_tijdstippen == {}


def test_an_unknown_field_counts_as_fresh(make_coordinator, hass):
    """Bewuste keuze: geen tijdstempel betekent niet "oud".

    Anders zou de aansturing na elke herstart een ronde zonder terugval
    zitten. De storing van 27 augustus wordt hoe dan ook gevangen, want
    daar was het veld wél via de normale weg gezet - alleen uren eerder.
    """
    c = make_coordinator(_config())
    c.last_available_kwh = 4.2

    assert c.beschikbare_energie_kwh() == 4.2
