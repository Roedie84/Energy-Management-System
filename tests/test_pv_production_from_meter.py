"""Dagopwek uit de meterstand in plaats van geïntegreerd (v1.9.1).

Gemeld: "Dagrapport geeft aan opwek 12.9 kWh terwijl mijn PV installatie
zegt 13.5 kWh" - 4,4% verschil, te veel voor ruis.

Oorzaak: de dagopwek werd geïntegreerd uit het vermogen, wat aanneemt dat
het vermogen tussen twee metingen constant was. De SolarEdge-sensor werkt
maar eens per 15-20 minuten bij (blijkt uit het meetfrequentie-rapport),
dus pieken daartussen vallen weg. De omvormer telt ze wél mee.
"""
from custom_components.energy_management_system.const import (
    CONF_PV_ENERGY_SENSOR,
    RELIABILITY_INDICATIVE,
    RELIABILITY_RELIABLE,
)

METER = "sensor.solaredge_i1_ac_energy"


def _met_meter(make_coordinator, hass, stand):
    c = make_coordinator({CONF_PV_ENERGY_SENSOR: METER})
    hass.states.set(METER, str(stand))
    return c


def test_the_day_total_comes_from_the_meter(make_coordinator, hass):
    """De kern: het dagverschil van een doorlopende teller, niet een
    optelling van momentopnames."""
    c = _met_meter(make_coordinator, hass, 22620.0)
    c._verwerk_pv_meterstand(22620.0)          # ijkpunt bij zonsopgang

    hass.states.set(METER, "22633.5")
    c._verwerk_pv_meterstand(22633.5)

    assert c.pv_production_today_kwh == 13.5
    assert c.pv_production_source == "meterstand"


def test_a_meter_reset_does_not_produce_a_negative(make_coordinator, hass):
    """Bij een herstart van de omvormer kan de teller terugvallen; dan is
    het verschil betekenisloos."""
    c = _met_meter(make_coordinator, hass, 22620.0)
    c._verwerk_pv_meterstand(22620.0)
    c._verwerk_pv_meterstand(22628.0)
    assert c.pv_production_today_kwh == 8.0

    # Teller teruggezet naar nul.
    c._verwerk_pv_meterstand(0.5)

    assert c.pv_production_today_kwh >= 8.0


def test_what_was_produced_is_kept_after_a_reset(make_coordinator, hass):
    """De opwek van vóór de reset weggooien zou de dag onbruikbaar
    maken."""
    c = _met_meter(make_coordinator, hass, 100.0)
    c._verwerk_pv_meterstand(100.0)
    c._verwerk_pv_meterstand(108.0)
    c._verwerk_pv_meterstand(0.0)
    c._verwerk_pv_meterstand(2.0)

    assert c.pv_production_today_kwh == 10.0


def test_the_day_rollover_re_anchors(make_coordinator, hass):
    """De meterstand loopt door over middernacht heen; zonder nieuw
    ijkpunt zou de opwek van gisteren gewoon doortellen."""
    c = _met_meter(make_coordinator, hass, 22620.0)
    c._verwerk_pv_meterstand(22620.0)
    c._verwerk_pv_meterstand(22633.5)

    c._reset_pv_energy_meter_day()
    c._verwerk_pv_meterstand(22635.0)

    assert c.pv_production_today_kwh == 1.5


def test_without_a_meter_it_still_integrates(make_coordinator, hass):
    """Niet iedereen heeft een cumulatieve meter; de terugval moet
    blijven werken."""
    c = make_coordinator({})

    assert c.pv_production_source == "geïntegreerd vermogen"


def test_the_source_is_reported(make_coordinator, hass):
    """Zodat in het dagrapport te zien is hoe hard het cijfer is."""
    c = _met_meter(make_coordinator, hass, 100.0)
    c._verwerk_pv_meterstand(100.0)

    rij = next(
        r for r in c.get_reliability_overview() if r["naam"] == "PV-dagopwek"
    )

    assert rij["niveau"] == RELIABILITY_RELIABLE
    assert "meterstand" in rij["reden"]


def test_integrating_is_marked_as_less_reliable(make_coordinator, hass):
    """Integreren onderschat structureel; dat hoort zichtbaar te zijn in
    plaats van als exact cijfer te worden gepresenteerd."""
    c = make_coordinator({})

    rij = next(
        r for r in c.get_reliability_overview() if r["naam"] == "PV-dagopwek"
    )

    assert rij["niveau"] == RELIABILITY_INDICATIVE
    assert "Onderschat structureel" in rij["reden"]
    assert "Configureren" in rij["reden"]
