"""v5.124.0: de verkooptoets toont ook bij een vroege rem de getallen.

Gemeld 23-10: de cockpit liet bij een zonarme dag '--' zien bij Tot het
blok en Na het blok. Alleen weergave; de beslissing verandert niet.
"""

from datetime import datetime, timedelta, timezone


NU = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)


def _met_blok(make_coordinator):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.last_cheap_block_start = NU + timedelta(hours=10)
    c.last_reserve_margin_breakdown = {
        "needed_kwh_before_margin": 6.31,
        "lange_horizon_extra_kwh": 0.0,
    }
    return c


def test_zonarme_dag_krijgt_getallen(make_coordinator, hass):
    c = _met_blok(make_coordinator)
    toets = {"mag_verkopen": False, "reden": "Zonarme dag"}
    uit = c._verkooptoets_weergave(toets, 3.2)
    assert uit["mag_verkopen"] is False
    assert uit["reden"] == "Zonarme dag"
    assert uit["beschikbaar_kwh"] == 3.2
    assert uit["vrij_te_verkopen_kwh"] == 0.0
    assert uit["nodig_tot_blok_kwh"] == 6.31
    assert uit["nodig_na_blok_kwh"] == 0.0
    # het origineel blijft ongemoeid
    assert "beschikbaar_kwh" not in toets


def test_mag_verkopen_blijft_ongewijzigd(make_coordinator, hass):
    c = _met_blok(make_coordinator)
    toets = {"mag_verkopen": True, "vrij_te_verkopen_kwh": 1.5}
    assert c._verkooptoets_weergave(toets, 5.0) == toets


def test_bestaande_waarden_niet_overschreven(make_coordinator, hass):
    c = _met_blok(make_coordinator)
    toets = {"mag_verkopen": False, "beschikbaar_kwh": 2.0, "nodig_tot_blok_kwh": 4.0}
    uit = c._verkooptoets_weergave(toets, 9.9)
    assert uit["beschikbaar_kwh"] == 2.0
    assert uit["nodig_tot_blok_kwh"] == 4.0


# --- v5.124.1: P1 regeldoel kiest nooit zichzelf als bron ------------------


def test_p1_regeldoel_kiest_zichzelf_niet_na_herstart(make_coordinator, hass):
    """Live 23-10 14:55: na een herstart (eigen sensor nog zonder kenmerk)
    werd de eigen sensor zijn eigen bron en bleef 'onbekend'."""
    c = make_coordinator({})
    c.p1_regeldoel_entity_id = "sensor.ems_p1"
    c.p1_regeldoel_bron = "sensor.regel_quooker"
    c._zendure_p1meter = lambda: "sensor.ems_p1"
    # eigen sensor bestaat nog niet / heeft geen kenmerk
    assert c.p1_regeldoel_bron_entity() == "sensor.regel_quooker"
    hass.states.set("sensor.ems_p1", "unknown")
    assert c.p1_regeldoel_bron_entity() == "sensor.regel_quooker"
    assert c._is_eigen_p1_regeldoel("sensor.ems_p1", hass.states.get("sensor.ems_p1"))


def test_p1_regeldoel_volgt_andere_bron(make_coordinator, hass):
    c = make_coordinator({})
    c.p1_regeldoel_entity_id = "sensor.ems_p1"
    c._zendure_p1meter = lambda: "sensor.regel_quooker"
    hass.states.set("sensor.regel_quooker", "12")
    assert c.p1_regeldoel_bron_entity() == "sensor.regel_quooker"
    assert c.p1_regeldoel_bron == "sensor.regel_quooker"
