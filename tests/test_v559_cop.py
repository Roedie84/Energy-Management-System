"""COP van de airco instelbaar uit de fabrieksopgave (v5.59).

Bron voor Ruud: Daikin data book 3MXM-A (EEDEN22, p.10), 3MXM52A met
FTXA25AW + FTXA35AW: 6,80 kW warmte bij 1,53 kW -> COP 4,44 bij 7 °C.
De helling 0,08 per graad blijft een aanname.
"""
import pytest
import voluptuous as vol

from custom_components.energy_management_system import slimme_bronnen as sb
from custom_components.energy_management_system.config_flow import (
    _schema,
    _validate_input,
)
from custom_components.energy_management_system.const import (
    CONF_AIRCO_COP_BIJ_7C,
    CONF_AIRCO_COP_PER_GRAAD,
)


def _oude_cop(t):
    """De lijn van v5.58, letterlijk."""
    if t is None:
        return 3.0
    return max(2.0, min(4.5, 3.0 + 0.08 * t))


# --- zonder optie: identiek aan v5.58 ----------------------------------


@pytest.mark.parametrize("t", [None, -40, -10, -5, 0, 7, 12, 20, 40])
def test_zonder_optie_identiek(t):
    assert sb.cop_bij(t) == _oude_cop(t)
    assert sb.cop_bij(t, None, None) == _oude_cop(t)
    assert sb.cop_bij(t, "", 0.08) == pytest.approx(_oude_cop(t))


def test_advies_zonder_optie_identiek():
    uit = sb.verwarmingsadvies(1.7427, 0.2371, buiten_c=12.0)
    cop = _oude_cop(12.0)
    assert uit["cop_geschat"] == round(cop, 2)
    assert uit["omslag_stroomprijs_eur"] == round(1.7427 / 8.8 * cop, 4)
    assert uit["cop_bron"] == "algemene schatting"


# --- met de fabrieksopgave ---------------------------------------------


def test_fabrieksopgave_punten():
    assert sb.cop_bij(7, 4.44) == pytest.approx(4.44)
    assert sb.cop_bij(0, 4.44) == pytest.approx(3.88)
    assert sb.cop_bij(-10, 4.44) == pytest.approx(3.08)
    assert sb.cop_bij(-40, 4.44) == 2.0
    assert sb.cop_bij(None, 4.44) == pytest.approx(4.44)


def test_fabrieksopgave_bovengrens():
    # max(4,5 ; 4,44 + 0,5) = 4,94
    assert sb.cop_bij(30, 4.44) == pytest.approx(4.94)
    # een lage opgave houdt de gewone bovengrens 4,5
    assert sb.cop_bij(40, 3.0) == pytest.approx(4.5)


def test_eigen_helling():
    assert sb.cop_bij(0, 4.44, 0.1) == pytest.approx(3.74)


@pytest.mark.parametrize("t", [-10, 0, 7, 15])
def test_omslagpunt(t):
    uit = sb.verwarmingsadvies(1.7427, 0.25, buiten_c=t, cop_bij_7c=4.44)
    cop = sb.cop_bij(t, 4.44)
    assert uit["omslag_stroomprijs_eur"] == round(1.7427 / 8.8 * cop, 4)
    assert uit["cop_bron"] == "fabrieksopgave (COP 4.44 bij 7 °C)"
    assert "fabrieksopgave" in uit["reden"]


def test_coordinator_geeft_de_optie_mee(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config.update(
        gas_price_sensor_entity="sensor.gas",
        **{CONF_AIRCO_COP_BIJ_7C: 4.44},
    )
    hass.states.set("sensor.gas", "1.76")
    c.huidige_prijs_eur_per_kwh = lambda now=None: 0.30
    c._get_live_outdoor_temp_c = lambda now: 0.0
    uit = c.get_verwarmingsadvies()
    assert uit["cop_geschat"] == pytest.approx(3.88)
    assert uit["omslag_stroomprijs_eur"] == pytest.approx(1.76 / 8.8 * 3.88, abs=1e-4)


def test_coordinator_zonder_optie(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config.update(gas_price_sensor_entity="sensor.gas")
    c.config[CONF_AIRCO_COP_BIJ_7C] = None  # leeg opgeslagen
    hass.states.set("sensor.gas", "1.76")
    c.huidige_prijs_eur_per_kwh = lambda now=None: 0.30
    c._get_live_outdoor_temp_c = lambda now: 0.0
    uit = c.get_verwarmingsadvies()
    assert uit["cop_geschat"] == 3.0
    assert uit["cop_bron"] == "algemene schatting"


# --- options flow ------------------------------------------------------


def test_flow_accepteert_leeg():
    invoer = {CONF_AIRCO_COP_BIJ_7C: None, CONF_AIRCO_COP_PER_GRAAD: ""}
    assert _validate_input(invoer) == {}
    assert CONF_AIRCO_COP_BIJ_7C not in invoer
    assert CONF_AIRCO_COP_PER_GRAAD not in invoer


def test_flow_accepteert_waarde():
    invoer = {CONF_AIRCO_COP_BIJ_7C: 4.44, CONF_AIRCO_COP_PER_GRAAD: "0,08"}
    assert _validate_input(invoer) == {}
    assert invoer[CONF_AIRCO_COP_BIJ_7C] == 4.44
    assert invoer[CONF_AIRCO_COP_PER_GRAAD] == 0.08


def test_flow_weigert_buiten_bereik():
    assert _validate_input({CONF_AIRCO_COP_BIJ_7C: 9}) == {
        CONF_AIRCO_COP_BIJ_7C: "out_of_range"
    }


def test_schema_bevat_de_velden_en_laat_leeg_toe():
    for defaults in ({}, {CONF_AIRCO_COP_BIJ_7C: 4.44}):
        schema = _schema(defaults)
        sleutels = {str(k): k for k in schema.schema}
        assert CONF_AIRCO_COP_BIJ_7C in sleutels
        assert CONF_AIRCO_COP_PER_GRAAD in sleutels
        veld = sleutels[CONF_AIRCO_COP_BIJ_7C]
        # geen default: leegmaken valt niet terug op de oude waarde
        assert veld.default is vol.UNDEFINED
    veld = {str(k): k for k in _schema({CONF_AIRCO_COP_BIJ_7C: 4.44}).schema}[
        CONF_AIRCO_COP_BIJ_7C
    ]
    assert veld.description == {"suggested_value": 4.44}
