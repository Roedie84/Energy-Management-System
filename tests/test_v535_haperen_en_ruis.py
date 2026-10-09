"""Cockpit, diagnoseregel en modulenaam (v5.35).

Gemeten op 6 oktober: de accusensor (`sensor.zendure_batterij_vermogen`, een
HomeWizard-stekker) viel 11:20-14:47 17 keer 10-20 seconden weg. Elke keer
stond de cockpit een ronde op STORING, zonder dat achteraf te zien was
waarom. En `diagnose_gezondheid` veranderde elke 30 s, alleen omdat de
GACS-duur van die ronde erin stond: 2.937 logboekregels in 12 uur.
"""
from types import SimpleNamespace

from test_cockpit_matrix import _gezond

from custom_components.energy_management_system.const import (
    GACS_DUUR_OPVALLEND_MS,
    KOPPELING_HAPERT_S,
)


def _met_koppeling(c, **regel):
    c.get_configuratiecontrole = lambda: {
        "entiteiten": [{"instelling": "battery_power_sensor_entity", **regel}]
    }


def test_een_koppeling_die_net_wegviel_is_nog_geen_storing(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    _met_koppeling(c, oordeel="geen_waarde", geen_waarde_s=15)

    assert c._ems_status()[0] != "STORING"


def test_een_koppeling_die_lang_weg_is_blijft_storing(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    _met_koppeling(c, oordeel="geen_waarde", geen_waarde_s=KOPPELING_HAPERT_S + 1)

    stand, reden = c._ems_status()
    assert stand == "STORING"
    assert "battery_power_sensor_entity" in reden


def test_zonder_duur_telt_hij_zoals_altijd(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    _met_koppeling(c, oordeel="geen_waarde")

    assert c._ems_status()[0] == "STORING"


def test_de_controle_noteert_hoe_lang_een_koppeling_weg_is(make_coordinator, hass):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    hass.states.set("sensor.accu", "unavailable")
    staat = hass.states.get("sensor.accu")
    try:
        staat.last_changed = dt_util.now() - timedelta(seconds=20)
    except AttributeError:
        echte_get = hass.states.get
        nep = SimpleNamespace(
            state="unavailable", attributes={},
            last_changed=dt_util.now() - timedelta(seconds=20),
        )
        hass.states.get = lambda e: nep if e == "sensor.accu" else echte_get(e)
    c = make_coordinator({"battery_power_sensor_entity": "sensor.accu"})

    regel = next(
        r for r in c.get_configuratiecontrole()["entiteiten"]
        if r["entiteit"] == "sensor.accu"
    )
    assert regel["oordeel"] == "geen_waarde"
    assert 19 <= regel["geen_waarde_s"] <= 25


def test_de_cockpit_legt_de_reden_vast(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import CockpitSensor

    c = make_coordinator({})
    c.cockpit_gegevens = lambda: {"status_kort": "STORING", "status_regel": "x kapot"}
    c.get_cockpit_svg = lambda *_: "<svg/>"  # v5.62: krijgt de gegevens mee
    attrs = CockpitSensor(c, "e").extra_state_attributes

    assert attrs["reden"] == "x kapot"
    assert "reden" not in CockpitSensor._unrecorded_attributes


def test_een_gewone_gacs_duur_verandert_de_regel_niet(make_coordinator, hass):
    c = make_coordinator({})
    c.gacs_traagste = {"ms": 2869.0, "traagste_onderdelen": {}}

    c.gacs_duur_ms = 284.0
    eerst = c._diagnose_gacs()
    c.gacs_duur_ms = 291.0

    assert c._diagnose_gacs() == eerst == "max 2869"


def test_een_opvallende_gacs_duur_staat_er_wel(make_coordinator, hass):
    c = make_coordinator({})
    c.gacs_traagste = {"ms": 2869.0, "traagste_onderdelen": {}}
    c.gacs_duur_ms = GACS_DUUR_OPVALLEND_MS + 500.0

    assert c._diagnose_gacs().startswith("1500ms max 2869")


def test_de_accumodule_heet_naar_zijn_apparaat(make_coordinator, hass):
    c = make_coordinator({"battery_module_cell_voltage_max_sensor_entities": ["sensor.a", "sensor.b"]})
    c.apparaatnaam_van = lambda e: {"sensor.a": "AB3000 00996"}.get(e)

    modules = c._read_battery_modules()
    assert modules[0]["naam"] == "AB3000 00996"
    assert modules[1]["naam"] is None


def test_zonder_register_geen_apparaatnaam(make_coordinator, hass):
    c = make_coordinator({})
    c._entiteitenregister = lambda: None
    assert c.apparaatnaam_van("sensor.x") is None


def test_de_melding_noemt_de_module_bij_naam(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = [{"module": 1, "naam": "AB3000 00996"}, {"module": 2, "naam": None}]
    c.battery_module_health = {"1": {"cusum": {"cel_delta_afwijking_v": {"drift": True}}}}

    tabel = c.get_battery_module_table()
    assert tabel[0]["label"] == "1 (AB3000 00996)"
    assert tabel[1]["label"] == 2
