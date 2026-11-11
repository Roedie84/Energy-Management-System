"""v5.186.0 track B: de ronde zelf - vangnet, slot, opstartfase, herinneringen.

B16 een omvallende adviesstap slaat de ronde niet meer over; na N rondes
    zonder besluit met de accu handmatig: terug naar smart.
B17 tijdslimiet op schrijven; geen extra rondes in de rij als het slot bezet is.
B21 de stille opstartfase begint bij de eerste ronde, niet bij het laden.
B26 de knoppen schrijven binnen het slot.
B27 herinnering bij een lange kalibratie of force_manual.
B28 internal_failures worden gewist als het weer lukt.
B29 een handmatige stand die de herstart niet overleefde, wordt gemeld.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast
from homeassistant.util import dt as dt_util

from custom_components.energy_management_system.const import (
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
    HANDMATIGE_STAND_LADEN,
    STARTUP_GRACE_SECONDS,
    VANGNET_RONDES_ZONDER_BESLUIT,
)

SELECT = "select.op"
NUMBER = "number.pow"
DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _config(**extra):
    return {CONF_OPERATION_SELECT: SELECT, CONF_MANUAL_POWER_NUMBER: NUMBER, **extra}


def _volle_config():
    return {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": SELECT,
        "manual_power_number_entity": NUMBER,
        "available_energy_sensor_entity": "sensor.available_energy",
        "battery_total_capacity_sensor_entity": "sensor.total_capacity",
        "battery_min_soc_number_entity": "number.min_soc",
        "manual_discharge_power": 1600,
        "manual_charge_power": -1600,
    }


# --- B16: een adviesstap die omvalt -----------------------------------------


def test_omvallende_adviesstap_slaat_het_besluit_niet_over(make_coordinator, hass, monkeypatch):
    forecast = make_price_forecast(DAY0, lambda h, m: 2_500_000)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.available_energy", "1.0")
    hass.states.set("sensor.total_capacity", "5.0")
    hass.states.set("number.min_soc", "0")
    c = make_coordinator(_volle_config())
    from custom_components.energy_management_system import coordinator as mod

    monkeypatch.setattr(mod.dt_util, "now", lambda: DAY0.replace(hour=10))

    def kapot(*_a, **_k):
        raise RuntimeError("stap stuk")

    # v5.221.0: MPC en de digitale tweeling zijn vervallen; de NILM-stap staat ervoor in de plaats.
    c._update_nilm_confirmed_devices = kapot
    c._run_monte_carlo_simulation = kapot
    c._update_presence = kapot
    _run(c._async_ronde())

    assert c._besluit_deze_ronde is True
    assert c.last_reason not in (None, "")
    assert "ronde:nilm-apparaten" in c.internal_failures
    assert "ronde:monte carlo" in c.internal_failures
    assert "ronde:aanwezigheid" in c.internal_failures
    # De volgende ronde lukt het weer: de vlaggen eraf.
    del c._update_nilm_confirmed_devices
    _run(c._async_ronde())
    assert "ronde:nilm-apparaten" not in c.internal_failures


def test_adviesstappen_in_dezelfde_volgorde():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )
    import inspect

    bron = inspect.getsource(C._adviesstappen_voor_besluit)
    assert bron.index("_update_appliance_state_machine") < bron.index("_run_monte_carlo")
    assert "_compute_mpc_plan" not in bron and "_update_kalman" not in bron  # v5.221.0


def _rondes_zonder_besluit(c, n, fout=False):
    async def ronde():
        if fout:
            raise RuntimeError("stuk")

    c._async_update_locked = ronde
    for _ in range(n):
        try:
            _run(c._async_ronde())
        except RuntimeError:
            pass


def test_vangnet_zet_handmatig_terug_naar_smart(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "manual", {"options": ["smart", "manual", "smart_charging"]})
    hass.states.set(NUMBER, "-1600")
    _rondes_zonder_besluit(c, VANGNET_RONDES_ZONDER_BESLUIT - 1, fout=True)
    assert hass.services.calls == []
    _rondes_zonder_besluit(c, 1, fout=True)
    assert ("select", "select_option", {"entity_id": SELECT, "option": "smart"}) in hass.services.calls
    assert "vangnet_geen_besluit" in c.internal_failures
    assert c.vangnet_laatst["teruggezet"] is True


def test_vangnet_ook_bij_rondes_zonder_besluit_zonder_fout(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "manual")
    _rondes_zonder_besluit(c, VANGNET_RONDES_ZONDER_BESLUIT)
    assert any(x[0] == "select" for x in hass.services.calls)


def test_vangnet_niet_bij_smart_of_bewuste_standen(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "smart")
    _rondes_zonder_besluit(c, VANGNET_RONDES_ZONDER_BESLUIT + 2)
    assert hass.services.calls == []
    hass.states.set(SELECT, "manual")
    c.force_manual = True
    _rondes_zonder_besluit(c, VANGNET_RONDES_ZONDER_BESLUIT + 2)
    assert hass.services.calls == []
    assert c.rondes_zonder_besluit == 0


def test_een_besluit_zet_de_teller_terug(make_coordinator, hass):
    c = make_coordinator(_config())
    c.rondes_zonder_besluit = 2
    c.internal_failures["vangnet_geen_besluit"] = "x"

    async def ronde():
        c._besluit_deze_ronde = True

    c._async_update_locked = ronde
    _run(c._async_ronde())
    assert c.rondes_zonder_besluit == 0
    assert "vangnet_geen_besluit" not in c.internal_failures


# --- B17: tijdslimiet en het slot ------------------------------------------


def test_schrijven_met_tijdslimiet(make_coordinator, hass, monkeypatch):
    from custom_components.energy_management_system import coordinator as mod

    c = make_coordinator(_config())
    monkeypatch.setattr(mod, "ACCU_SCHRIJF_TIMEOUT_S", 0.01)

    async def hangt(*_a, **_k):
        await asyncio.sleep(5)

    hass.services.async_call = hangt
    gelukt = _run(c._stuur_naar_de_accu("select", "select_option", {}, "stand smart"))
    assert gelukt is False
    assert "geen antwoord" in c.internal_failures["accu_aansturing"]


def test_schakelaar_heeft_een_eigen_foutsleutel(make_coordinator, hass):
    c = make_coordinator(_config())
    c.internal_failures["accu_aansturing"] = "stand manual: kapot"
    _run(c._async_set_switch("switch.fiets", True))
    assert "accu_aansturing" in c.internal_failures


def test_geen_rondes_in_de_rij_als_het_slot_bezet_is(make_coordinator, hass):
    c = make_coordinator(_config())
    jobs = []
    hass.add_job = lambda f: jobs.append(f)

    async def met_slot():
        async with c._lock:
            c._handle_interval(None)
            c._handle_state_change(None)

    _run(met_slot())
    assert jobs == []
    assert c.rondes_overgeslagen == {"klok": 1, "prijssensor": 1}
    c._handle_interval(None)
    c._kwartierronde(None)
    assert len(jobs) == 2


def test_watchdog_slaat_over_als_er_een_ronde_hangt(make_coordinator, hass):
    c = make_coordinator(_config())
    c.last_successful_update = dt_util.now() - timedelta(hours=2)
    gestart = []

    async def update():
        gestart.append(1)

    c.async_update = update

    async def met_slot():
        async with c._lock:
            await c._watchdog(None)

    _run(met_slot())
    assert gestart == []
    assert c.rondes_overgeslagen["watchdog"] == 1


# --- B21: opstartfase vanaf de eerste ronde ---------------------------------


def test_opstartfase_begint_bij_de_eerste_ronde(make_coordinator, hass):
    c = make_coordinator(_config())
    _run(c.async_load_persisted_state())
    assert c._opstart_stil_tot is None
    assert c._opstart_stil_wacht_op_ronde is True

    async def ronde():
        pass

    c._async_update_locked = ronde
    voor = dt_util.now()
    _run(c._async_ronde())
    assert c._opstart_stil_wacht_op_ronde is False
    assert c._opstart_stil_tot >= voor + timedelta(seconds=STARTUP_GRACE_SECONDS - 1)
    assert c._opstart_stuurstil()


def test_einde_opstartfase_plant_een_ronde(make_coordinator, hass, monkeypatch):
    import homeassistant.helpers.event as ev

    gepland = []
    monkeypatch.setattr(ev, "async_call_later", lambda h, s, f: gepland.append((s, f)) or (lambda: None),
                        raising=False)
    c = make_coordinator(_config())
    c._opstart_stil_wacht_op_ronde = True
    c._start_opstartfase(dt_util.now())
    assert gepland and gepland[0][0] > STARTUP_GRACE_SECONDS
    jobs = []
    hass.add_job = lambda f: jobs.append(f)
    gepland[0][1](None)
    assert jobs == [c.async_update]


# --- B26: de knoppen binnen het slot -----------------------------------------


def test_knop_schrijft_binnen_het_slot(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "smart")
    hass.states.set(NUMBER, "0")
    gezien = []

    async def schrijf(power):
        gezien.append(c._lock.locked())
        return True

    c._async_apply_manual = schrijf

    async def leer(waarde):
        gezien.append(("leer", c._lock.locked()))

    c.async_set_learning_only = leer
    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN))
    assert gezien == [True, ("leer", False)]


# --- B27: herinneringen ---------------------------------------------------


def test_herinnering_bij_lange_kalibratie_en_force_manual(make_coordinator, hass):
    c = make_coordinator(_config())
    meldingen = []
    c._dispatch_notification = lambda **k: meldingen.append(k)
    nu = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    c.kalibratie = True
    c.kalibratie_sinds = (nu - timedelta(hours=3)).isoformat()
    c.force_manual = True
    c._waarschuw_bij_lange_stand(nu)  # force_manual: sinds = nu
    assert [m["notification_id"] for m in meldingen] == ["ems_lange_stand_kalibratie"]
    c._waarschuw_bij_lange_stand(nu + timedelta(minutes=30))
    assert len(meldingen) == 1
    c._waarschuw_bij_lange_stand(nu + timedelta(hours=2, minutes=1))
    ids = [m["notification_id"] for m in meldingen]
    assert ids.count("ems_lange_stand_kalibratie") == 2 and "ems_lange_stand_force_manual" in ids
    # Alleen herinneren, nooit zelf uitzetten.
    assert c.kalibratie is True and c.force_manual is True


def test_force_manual_onthoudt_sinds(make_coordinator, hass):
    c = make_coordinator(_config())
    c.async_update = lambda: asyncio.sleep(0)
    _run(c.async_set_force_manual(True))
    assert c.force_manual_sinds is not None
    _run(c.async_set_force_manual(False))
    assert c.force_manual_sinds is None


# --- B28: vlaggen eraf ------------------------------------------------------


def test_bewaak_stap_zet_en_wist(make_coordinator, hass):
    c = make_coordinator(_config())

    def kapot():
        raise ValueError("x")

    assert c._bewaak_stap("balanceren", kapot) is False
    assert "balanceren" in c.internal_failures
    assert c._bewaak_stap("balanceren", lambda: None) is True
    assert "balanceren" not in c.internal_failures


def test_ondergrens_en_module_leeg_worden_gewist(make_coordinator, hass):
    c = make_coordinator(_config())
    c.internal_failures["ondergrens"] = "oud"
    c.internal_failures["module_leeg"] = "oud"
    c._volg_ondergrens = lambda now: None
    c._volg_module_leeg = lambda now: None
    c._read_battery_modules = lambda: [
        {"module": 1, "cel_delta_v": 0.01, "temperatuur_c": 20, "soc_percent": 50, "vermogen_w": 0}
    ]
    c._update_battery_module_health(datetime(2026, 11, 4, 12, tzinfo=timezone.utc))
    assert "ondergrens" not in c.internal_failures
    assert "module_leeg" not in c.internal_failures


# --- B29: vervallen handmatige stand ------------------------------------------


def test_vervallen_handmatige_stand_wordt_gemeld(make_coordinator, hass):
    bron = make_coordinator(_config())
    bron.handmatige_stand_bij_afsluiten = {"stand": "laden", "sinds": "2026-11-04T09:00:00+00:00"}
    verse = make_coordinator(_config())
    verse._apply_persisted_state(bron._collect_persisted_state())
    assert verse.handmatige_stand is None
    meldingen = []
    verse._dispatch_notification = lambda **k: meldingen.append(k)
    verse._meld_vervallen_handmatige_stand(dt_util.now())
    verse._meld_vervallen_handmatige_stand(dt_util.now())
    assert len(meldingen) == 1 and "laden" in meldingen[0]["message"]
    assert verse.handmatige_stand_bij_afsluiten is None


def test_uitgezette_stand_wordt_niet_gemeld(make_coordinator, hass):
    c = make_coordinator(_config())
    c.async_set_learning_only = lambda waarde: asyncio.sleep(0)
    c._async_apply_operation = lambda optie: asyncio.sleep(0)
    _run(c.async_set_handmatige_stand("smart_charge"))
    assert c.handmatige_stand_bij_afsluiten["stand"] == "smart_charge"
    _run(c.async_set_handmatige_stand(None))
    assert c.handmatige_stand_bij_afsluiten is None


def test_celbescherming_wordt_bewaard(make_coordinator, hass):
    bron = make_coordinator(_config())
    bron._celbescherming = {"sinds": "2026-11-04T01:00:00+00:00", "module": 4, "laagste_cel_v": 2.8,
                            "laden_om": "2026-11-04T03:00:00+00:00", "buffer_gevuld": False}
    verse = make_coordinator(_config())
    verse._apply_persisted_state(bron._collect_persisted_state())
    assert verse._celbescherming == bron._celbescherming
