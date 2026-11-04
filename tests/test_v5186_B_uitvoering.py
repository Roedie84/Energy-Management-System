"""v5.186.0 track B: van besluit naar accu.

B18 opdrachtcontrole: wachttijd blijft staan bij (bijna) dezelfde waarde,
    marge max(25 W, 3 %), escalatie na N keer, niet nakijken wat mislukte.
B22 de schrijffuncties geven terug of het lukte; het waardeplan zegt waarom niet.
B25 'unknown' op het vermogensgetal blokkeert het zetten van de stand niet.
B19 paneelgrens: na een (her)start terug naar 100 %, ramp niet in de
    leermodus, vorige ramp stoppen, eindwaarde nakijken, vrij bij herladen.
B24 P1 regeldoel valt terug op de ruwe P1-meter.
"""
import asyncio
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
    CONF_SOLAR_POWER_LIMIT_ENTITY,
    OPDRACHT_BEVESTIGING_SECONDEN,
    OPDRACHT_ESCALATIE_RONDES,
    PANEELGRENS_MAX_HERHALINGEN,
)

SELECT = "select.op"
NUMBER = "number.pow"
LIMIET = "number.omvormer_limiet"
NU = datetime(2026, 11, 4, 17, 2, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _config(**extra):
    return {CONF_OPERATION_SELECT: SELECT, CONF_MANUAL_POWER_NUMBER: NUMBER, **extra}


# --- B18 -------------------------------------------------------------------


def test_wachttijd_blijft_staan_bij_bijna_dezelfde_waarde(make_coordinator, hass):
    c = make_coordinator(_config())
    c._noteer_opdracht(NUMBER, -1782, "vermogen", nu_seconden=100.0)
    c._noteer_opdracht(NUMBER, -1760, "vermogen", nu_seconden=160.0)
    assert c._openstaande_opdrachten[NUMBER]["sinds"] == 100.0
    assert c._openstaande_opdrachten[NUMBER]["verwacht"] == -1760
    c._noteer_opdracht(NUMBER, -800, "vermogen", nu_seconden=170.0)
    assert c._openstaande_opdrachten[NUMBER]["sinds"] == 170.0


def test_marge_bij_het_nakijken(make_coordinator, hass):
    c = make_coordinator(_config())
    assert c._opdracht_gelijk("-1745", -1782)  # binnen 3 %
    assert c._opdracht_gelijk("-20", 0)        # binnen 25 W
    assert not c._opdracht_gelijk("-1600", -1782)
    assert c._opdracht_gelijk("manual", "manual")
    assert not c._opdracht_gelijk("smart", "manual")


def test_escalatie_na_n_mislukte_controles(make_coordinator, hass):
    c = make_coordinator(_config())
    c._dispatch_notification = lambda **k: None
    hass.states.set(SELECT, "smart")
    for i in range(OPDRACHT_ESCALATIE_RONDES):
        assert "opdracht_niet_aangekomen" not in c.internal_failures
        c._noteer_opdracht(SELECT, "manual", "modus", nu_seconden=0.0)
        c.controleer_opdrachten(NU, nu_seconden=OPDRACHT_BEVESTIGING_SECONDEN + 1)
    assert SELECT in c.internal_failures["opdracht_niet_aangekomen"]
    hass.states.set(SELECT, "manual")
    c._noteer_opdracht(SELECT, "manual", "modus", nu_seconden=0.0)
    c.controleer_opdrachten(NU, nu_seconden=OPDRACHT_BEVESTIGING_SECONDEN + 1)
    assert "opdracht_niet_aangekomen" not in c.internal_failures


def test_mislukte_schrijfactie_wordt_niet_nagekeken(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "smart", {"options": ["smart", "manual", "smart_charging"]})
    hass.states.set(NUMBER, "0")

    async def kapot(*_a, **_k):
        raise RuntimeError("cloud weg")

    hass.services.async_call = kapot
    assert _run(c._async_apply_manual(-1600)) is False
    assert c._openstaande_opdrachten == {}
    assert c.laatste_schrijfuitkomst == "schrijven mislukt"
    assert _run(c._async_apply_operation("smart_charging")) is False
    assert c._openstaande_opdrachten == {}


def test_controle_aan_het_begin_van_de_ronde(make_coordinator, hass):
    c = make_coordinator(_config())
    volgorde = []
    c.controleer_opdrachten = lambda now: volgorde.append("controle")

    async def ronde():
        volgorde.append("ronde")

    c._async_update_locked = ronde
    _run(c._async_ronde())
    assert volgorde == ["controle", "ronde"]


# --- B22 / B25 ---------------------------------------------------------------


def test_schrijffuncties_geven_de_uitkomst(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "smart", {"options": ["smart", "manual", "smart_charging"]})
    hass.states.set(NUMBER, "0")
    assert _run(c._async_apply_manual(-1600)) is True
    assert _run(c._async_apply_operation("smart")) is True
    c.learning_only = True
    assert _run(c._async_apply_operation("smart")) is False
    assert c.laatste_schrijfuitkomst == "leermodus"


def test_onbekend_vermogensgetal_blokkeert_de_stand_niet(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "manual", {"options": ["smart", "manual", "smart_charging"]})
    hass.states.set(NUMBER, "unknown")
    assert _run(c._async_apply_operation("smart")) is True
    assert ("select", "select_option", {"entity_id": SELECT, "option": "smart"}) in hass.services.calls
    hass.services.calls.clear()
    assert _run(c._async_apply_manual(-1600)) is True
    assert ("number", "set_value", {"entity_id": NUMBER, "value": -1600}) in hass.services.calls
    hass.states.set(NUMBER, "unavailable")
    assert _run(c._async_apply_manual(-1600)) is False
    assert c.laatste_schrijfuitkomst == "accu onbereikbaar"


def _waardeplan(c, actie="huis", **nu):
    plan = {"beschikbaar": True, "berekend_om": NU.isoformat(), "inhoud_kwh": 3.0,
            "nu": {"actie": actie, "kwh": 0.0, "accu_kwh": 0.0, "uren": 0.2, **nu}}
    c._waardeplan_nu = lambda now, entries: plan
    c._is_emergency_low_battery = lambda: False
    c._update_financial_tracking = lambda *a, **k: None
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda now: None
    return plan


def test_waardeplan_zegt_waarom_niet_gestuurd(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "unavailable")
    _waardeplan(c, "huis")
    assert _run(c._waardeplan_als_nodig(NU, [])) is True
    assert c.last_waardeplan["niet_gestuurd"] == "accu onbereikbaar"
    assert c.last_waardeplan["opdracht_w"] is None


def test_waardeplan_geslaagd_claimt_opdracht(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "smart", {"options": ["smart", "manual", "smart_charging"]})
    hass.states.set(NUMBER, "0")
    _waardeplan(c, "zon_export", kwh=0.0)
    _run(c._waardeplan_als_nodig(NU, []))
    assert c.last_waardeplan["niet_gestuurd"] is None
    assert c.last_waardeplan["opdracht_w"] == 0


# --- B19 ---------------------------------------------------------------------


def _paneel(make_coordinator, hass, waarde):
    c = make_coordinator(_config(**{CONF_SOLAR_POWER_LIMIT_ENTITY: LIMIET}))
    hass.states.set(LIMIET, str(waarde))
    gestart = []
    c._ramp_solar_power_limit = lambda doel: asyncio.sleep(0, result=gestart.append(doel))
    return c, gestart


def test_paneelgrens_na_start_terug_naar_100(make_coordinator, hass):
    c, gestart = _paneel(make_coordinator, hass, 0)
    _run(c._async_na_negatieve_prijs(NU))
    assert c._paneelgrens_doel == 100.0
    assert c._paneelgrens_na_start_bekeken is True


def test_paneelgrens_niet_terug_als_2027_begrenst(make_coordinator, hass):
    c, gestart = _paneel(make_coordinator, hass, 40)
    c._teruglevering_begrensd = True
    c._herstel_paneelgrens_na_start()
    assert c._paneelgrens_doel is None


def test_ramp_omlaag_niet_in_de_leermodus(make_coordinator, hass):
    c, gestart = _paneel(make_coordinator, hass, 100)
    c.learning_only = True
    c._start_solar_ramp(0.0)
    assert c._paneelgrens_doel is None
    c._start_solar_ramp(100.0)
    assert c._paneelgrens_doel == 100.0


def test_vorige_ramp_wordt_gestopt(make_coordinator, hass):
    c, _ = _paneel(make_coordinator, hass, 100)

    class Taak:
        geannuleerd = False

        def done(self):
            return False

        def cancel(self):
            self.geannuleerd = True

    oud = c._solar_ramp_task = Taak()
    c.hass.async_create_task = lambda coro: coro.close() or Taak()
    c._start_solar_ramp(0.0)
    assert oud.geannuleerd


def test_eindwaarde_wordt_nagekeken(make_coordinator, hass):
    c, _ = _paneel(make_coordinator, hass, 55)
    c.hass.async_create_task = lambda coro: coro.close()
    c._paneelgrens_doel = 0.0
    c._solar_ramp_task = None
    for _ in range(PANEELGRENS_MAX_HERHALINGEN):
        c._solar_ramp_task = None
        c._controleer_paneelgrens()
    assert c._paneelgrens_herhalingen == PANEELGRENS_MAX_HERHALINGEN
    c._solar_ramp_task = None
    c._controleer_paneelgrens()
    assert "paneelgrens" in c.internal_failures
    hass.states.set(LIMIET, "0")
    c._controleer_paneelgrens()
    assert "paneelgrens" not in c.internal_failures


def test_panelen_vrij_bij_herladen(make_coordinator, hass):
    c, _ = _paneel(make_coordinator, hass, 0)
    c._is_negative_price_active = True
    _run(c.async_unload())
    assert ("number", "set_value", {"entity_id": LIMIET, "value": 100.0}) in hass.services.calls


def test_negatieve_prijs_ramp_herhaalt_als_hij_werd_overgeslagen(make_coordinator, hass):
    c, gestart = _paneel(make_coordinator, hass, 100)
    c.learning_only = True
    c._waardeplan_als_nodig = lambda now, entries: asyncio.sleep(0, result=True)
    _run(c._negatieve_prijs_ronde(NU, []))
    assert c._is_negative_price_active and c._paneelgrens_doel is None
    c.learning_only = False
    _run(c._negatieve_prijs_ronde(NU, []))
    assert c._paneelgrens_doel == 0.0


# --- B24 ---------------------------------------------------------------------


def test_p1_regeldoel_valt_terug_op_de_ruwe_meter(make_coordinator, hass):
    c = make_coordinator(_config())
    nu = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
    for _ in range(5):
        c.p1_regeldoel(110.0, 100.0, nu)  # verschuiving 10 W
    uit = c.p1_regeldoel(None, 200.0, nu)
    assert uit["waarde_w"] == 210.0
    assert uit["terugval"]
    assert c.p1_regeldoel(None, None, nu)["waarde_w"] is None


def test_p1_sensor_volgt_een_nieuwe_bron(make_coordinator, hass):
    from custom_components.energy_management_system.const import CONF_CONSUMPTION_POWER_SENSOR
    from custom_components.energy_management_system.sensor import P1RegeldoelSensor

    c = make_coordinator(_config(**{CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1"}))
    bron = {"id": "sensor.regel_a"}
    c.p1_regeldoel_bron_entity = lambda: bron["id"]
    s = P1RegeldoelSensor(c, "e")
    s.hass = hass
    s.entity_id = "sensor.ems_p1_regeldoel"
    s.async_write_ha_state = lambda: None
    s.async_on_remove = lambda f: None
    hass.states.set("sensor.p1", "200")
    _run(s.async_added_to_hass())
    assert s._gevolgd[0] == "sensor.regel_a"
    assert s.native_value == 200.0  # regelsensor weg: de ruwe meter
    bron["id"] = "sensor.regel_b"
    hass.states.set("sensor.regel_b", "150")
    c._notify_listeners()
    assert s._gevolgd[0] == "sensor.regel_b"
    assert s.native_value == 150.0
