"""Eigen getallen naast hun bron (v3.49.0).

Gevraagd: "Volgens mij moet je in de diagnostiek iets bouwen dat
werkelijke entiteiten vergelijkt met entiteiten van het EMS, zodat
fouten hierin sneller gedetecteerd worden."

Terecht, en het zou deze week drie keer geholpen hebben:

- 27 augustus: `last_soc_percent` stond op 38% terwijl de sensor 6%
  aangaf. Het veld wordt maar op drie plaatsen geschreven, en alle drie
  zitten in een tak die die ochtend niet werd bereikt.
- 26 augustus: `beschikbare_energie_kwh` stond op 0,00 terwijl er nog
  stroom in de accu zat.
- 11 augustus: hetzelfde veld op None terwijl de accu 22% aangaf.

Drie keer dezelfde vorm: een intern getal dat afdrijft van de meting
waar het vandaan komt. Van binnenuit is dat niet te zien, want alles wat
ermee rekent, rekent consequent met dezelfde verkeerde waarde.
"""
from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_SOC_SENSOR,
    SPIEGEL_MARGE_KRUIS_PROCENT,
    SPIEGEL_MARGE_SOC_PROCENT,
)


def _config():
    return {
        CONF_SOC_SENSOR: "sensor.soc",
        CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
    }


def _regel(c, naam):
    return next(r for r in c.get_spiegelcontrole() if r["naam"] == naam)


# --- de storing van 27 augustus --------------------------------------


def test_the_stale_soc_field_is_caught(make_coordinator, hass):
    """De aanleiding, met de gemeten getallen: het veld op 38%, de

    sensor op 6%.
    """
    c = make_coordinator(_config())
    hass.states.set("sensor.soc", "6.0")
    c.last_soc_percent = 38.0

    regel = _regel(c, "Accustand")

    assert regel["oordeel"] == "loopt_uiteen"
    assert regel["verschil"] == 32.0
    assert regel["bron"] == "sensor.soc"


def test_a_field_that_follows_its_sensor_is_fine(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set("sensor.soc", "42.0")
    c.last_soc_percent = 42.0

    assert _regel(c, "Accustand")["oordeel"] == "sluit_aan"


def test_a_small_difference_is_allowed(make_coordinator, hass):
    """Een sensor die net is bijgewerkt en een veld van de vorige ronde

    lopen altijd iets uiteen. Daar is de marge voor.
    """
    c = make_coordinator(_config())
    hass.states.set("sensor.soc", "42.0")
    c.last_soc_percent = 42.0 + SPIEGEL_MARGE_SOC_PROCENT - 1

    assert _regel(c, "Accustand")["oordeel"] == "sluit_aan"


# --- de kruistoets ---------------------------------------------------


def test_the_cross_check_catches_impossible_pairs(make_coordinator, hass):
    """De sterkste toets: accustand en beschikbare energie komen uit

    VERSCHILLENDE sensoren. Wijken die van elkaar af, dan is er één
    stuk - en dan maakt het niet uit welke van de twee zijn eigen bron
    nog volgt.

    38% tegenover 0,00 kWh kan niet allebei waar zijn.
    """
    c = make_coordinator(_config())
    hass.states.set("sensor.soc", "38.0")
    hass.states.set("sensor.beschikbaar", "0.0")
    c.bruikbare_capaciteit_kwh = lambda: 7.78

    regel = _regel(c, "Accustand tegen beschikbare energie")

    assert regel["oordeel"] == "loopt_uiteen"
    assert regel["verschil"] > SPIEGEL_MARGE_KRUIS_PROCENT


def test_a_matching_pair_passes(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set("sensor.soc", "50.0")
    hass.states.set("sensor.beschikbaar", "3.5")
    c.bruikbare_capaciteit_kwh = lambda: 7.78

    assert (
        _regel(c, "Accustand tegen beschikbare energie")["oordeel"]
        == "sluit_aan"
    )


def test_without_a_capacity_the_cross_check_is_skipped(
    make_coordinator, hass
):
    """De kruistoets heeft de capaciteit nodig om de omrekening te doen.

    Op 27 augustus viel die weg: `sensor.zendure_manager_total_kwh` komt
    uit dezelfde manager die zijn accu kwijt was, dus de capaciteit was
    None en `wear_cost_overview` stond op null. Alles tegelijk.

    Dat de kruistoets dan zwijgt is juist - er valt niets om te rekenen.
    Maar de twee LOSSE toetsen blijven wél werken, en die vangen het
    geval alsnog: het veld tegen zijn eigen sensor.
    """
    c = make_coordinator(_config())
    hass.states.set("sensor.soc", "6.0")
    hass.states.set("sensor.beschikbaar", "0.0")
    c.last_soc_percent = 38.0

    namen = [r["naam"] for r in c.get_spiegelcontrole()]

    assert "Accustand tegen beschikbare energie" not in namen
    assert _regel(c, "Accustand")["oordeel"] == "loopt_uiteen"


# --- wat er niet mag gebeuren ----------------------------------------


def test_a_missing_sensor_is_not_a_finding(make_coordinator, hass):
    """Een sensor die niets zegt is geen afwijking - dan valt er alleen

    niets te vergelijken.
    """
    c = make_coordinator(_config())
    c.last_soc_percent = 38.0

    assert _regel(c, "Accustand")["oordeel"] == "niet_te_vergelijken"


def test_without_configured_sensors_it_stays_empty(make_coordinator, hass):
    c = make_coordinator({})

    assert c.get_spiegelcontrole() == []


# --- en het komt in de zelfcontrole terecht --------------------------


def test_a_drifting_field_becomes_a_finding(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set("sensor.soc", "6.0")
    c.last_soc_percent = 38.0

    namen = [b["naam"] for b in c.get_consistency_checks()["bevindingen"]]

    assert "Spiegel: Accustand" in namen


def test_the_finding_names_both_numbers(make_coordinator, hass):
    """Wie de melding leest moet kunnen zien welke twee getallen

    uiteenlopen, zonder een export te hoeven opvragen.
    """
    c = make_coordinator(_config())
    hass.states.set("sensor.soc", "6.0")
    c.last_soc_percent = 38.0

    bevinding = next(
        b
        for b in c.get_consistency_checks()["bevindingen"]
        if b["naam"] == "Spiegel: Accustand"
    )

    assert "38" in bevinding["uitleg"]
    assert "6" in bevinding["uitleg"]
    assert "sensor.soc" in bevinding["uitleg"]
