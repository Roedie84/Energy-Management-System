"""De kostenrij meet van links naar rechts hetzelfde (v2.3.0).

Gemeld met een screenshot: "Kosten (EUR) vandaag -0.54" bij 0,04 kWh
afname. Een negatief bedrag bij afname kan niet.

De dagkolom kwam uit `actual_cost_today_eur` - de eigen
kostenberekening, waar de opbrengst van teruglevering vanaf gaat. De
historische kolommen lezen de kostenmeter, die alleen de afname telt.
Twee verschillende grootheden in één rij.
"""
from custom_components.energy_management_system.const import (
    CONF_COST_ENERGY_SENSOR,
)


def _coordinator(make_coordinator, hass, stand=None):
    c = make_coordinator({CONF_COST_ENERGY_SENSOR: "sensor.kosten"})
    if stand is not None:
        hass.states.set("sensor.kosten", str(stand))
    return c


def test_a_daily_sensor_gives_todays_value(make_coordinator, hass):
    """Een dagsensor reset zelf; dan is de stand de aangroei."""
    c = _coordinator(make_coordinator, hass, stand=0.42)
    c._kosten_meter_dagbegin = 0.0

    assert c._kosten_vandaag_uit_meter() == 0.42


def test_a_lifetime_meter_gives_the_growth(make_coordinator, hass):
    """Zonder ijkpunt zou hier het totaal-ooit staan - een verschil van
    jaren in de kolom "vandaag"."""
    c = _coordinator(make_coordinator, hass, stand=1834.55)
    c._kosten_meter_dagbegin = 1833.90

    assert c._kosten_vandaag_uit_meter() == 0.65


def test_a_reset_meter_falls_back_to_the_reading(make_coordinator, hass):
    """Om middernacht springt een dagsensor terug naar nul; de stand is
    dan zelf de aangroei."""
    c = _coordinator(make_coordinator, hass, stand=0.03)
    c._kosten_meter_dagbegin = 0.42

    assert c._kosten_vandaag_uit_meter() == 0.03


def test_without_a_reference_point_it_still_answers(make_coordinator, hass):
    """Vlak na een herstart is het ijkpunt onbekend. Een verzonnen
    ijkpunt zou erger zijn; dit corrigeert zichzelf bij de volgende
    dagwissel."""
    c = _coordinator(make_coordinator, hass, stand=0.42)
    c._kosten_meter_dagbegin = None

    assert c._kosten_vandaag_uit_meter() == 0.42


def test_without_a_meter_the_field_stays_empty(make_coordinator, hass):
    """De eigen berekening erin zetten zou de rij weer ongelijksoortig
    maken."""
    c = make_coordinator({})

    assert c._kosten_vandaag_uit_meter() is None


def test_the_row_uses_one_source(make_coordinator, hass):
    """De kern: de dagkolom mag niet uit de eigen kostenberekening
    komen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("vandaag_rij = {")
    blok = bron[kop : bron.index("}", bron.index('"besparing_eur"', kop))]

    # Commentaar eruit: dat noemt de oude bron bij naam in de uitleg.
    code = "\n".join(r.split("#")[0] for r in blok.splitlines())

    assert "_kosten_vandaag_uit_meter()" in code
    assert "actual_cost_today_eur" not in code.split("besparing_eur")[0]


def test_savings_still_uses_the_counterfactual(make_coordinator, hass):
    """Het saldo verdwijnt niet - het staat in de besparingsrij, waar het
    thuishoort: dat is per definitie een verschil."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("vandaag_rij = {")
    blok = bron[kop : kop + 1500]

    assert "counterfactual_cost_today_eur" in blok


def test_the_reference_point_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "_kosten_meter_dagbegin" in PERSISTED_PLAIN_FIELDS
