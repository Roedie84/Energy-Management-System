"""v5.203.0: kosten vandaag inclusief vaste kosten.

Ruud 09-11: "Waarom tellen vaste kosten niet mee? Ik moet toch een totaal
plaatje hebben voor zowel tablet en cockpit voor gas en elektra."
"""
from datetime import date
from pathlib import Path

from custom_components.energy_management_system import jaarafrekening as ja
from custom_components.energy_management_system.const import (
    CONF_GAS_EUR_VANDAAG_SENSOR,
    CONF_INKOOP_EUR_VANDAAG_SENSOR,
    CONF_TERUGLEVER_EUR_VANDAAG_SENSOR,
)
from custom_components.energy_management_system.sensor import EnergiekostenVandaagSensor, GaskostenVandaagSensor

PAKKET = Path(__file__).parent.parent / "custom_components" / "energy_management_system"


def _inst(**kw):
    basis = dict(vastrecht_stroom_mnd=6.25, vastrecht_gas_mnd=6.25, netbeheer_stroom_jaar=478.0,
                 netbeheer_gas_jaar=267.0, vermindering_eb_jaar=628.96, gas_overstap=date(2026, 11, 22),
                 gas_nieuw_vastrecht_mnd=8.33, gas_nieuw_korting_jaar=210.0)
    basis.update(kw)
    inst = ja.Instellingen()
    for k, v in basis.items():
        setattr(inst, k, v)
    return inst


def test_vaste_kosten_per_dag():
    v = ja.vaste_kosten_dag(_inst(), date(2026, 11, 9))
    assert round(v["stroom_eur"], 3) == round((75 + 478 - 628.96) / 365, 3)   # -0,208: EB-korting
    assert round(v["gas_eur"], 3) == round((75 + 267) / 365, 3)               # 0,937
    na = ja.vaste_kosten_dag(_inst(), date(2026, 11, 22))
    assert round(na["gas_eur"], 3) == round((8.33 * 12 + 267 - 210) / 365, 3)


def test_kosten_vandaag_09_11():
    k = ja.kosten_vandaag(afname_eur=2.4673, terug_eur=0.8644, gas_eur=0.3724,
                          vast=ja.vaste_kosten_dag(_inst(), date(2026, 11, 9)))
    assert k["stroom_variabel_eur"] == 1.6
    assert k["stroom_eur"] == round(1.6029 - 0.2081, 2)
    assert k["gas_eur"] == round(0.3724 + 0.937, 2)
    assert k["totaal_eur"] == round(1.6029 - 0.2081 + 0.3724 + 0.937, 2)
    leeg = ja.kosten_vandaag(afname_eur=None, terug_eur=None, gas_eur=0.3, vast=ja.vaste_kosten_dag(_inst(), date(2026, 11, 9)))
    assert leeg["stroom_eur"] is None and leeg["totaal_eur"] is None and leeg["gas_eur"] is not None


def test_sensoren(make_coordinator, hass):
    c = make_coordinator({CONF_INKOOP_EUR_VANDAAG_SENSOR: "sensor.a", CONF_TERUGLEVER_EUR_VANDAAG_SENSOR: "sensor.t",
                          CONF_GAS_EUR_VANDAAG_SENSOR: "sensor.g"})
    hass.states.set("sensor.a", "2.4673", {})
    hass.states.set("sensor.t", "0.8644", {})
    hass.states.set("sensor.g", "0.3724", {})
    s = EnergiekostenVandaagSensor(c, "e")
    assert s._attr_unique_id == "e_kosten_vandaag_totaal"
    k = c.get_kosten_vandaag()
    assert s.native_value == k["totaal_eur"] and k["stroom_variabel_eur"] == 1.6
    assert GaskostenVandaagSensor(c, "e").native_value == k["gas_eur"]


def test_cockpit_toont_totaal():
    js = (PAKKET / "www" / "ems-cockpit.js").read_text()
    assert 'kostenTotaal: "kosten_vandaag_totaal"' in js and "Totaal vandaag <b>" in js
