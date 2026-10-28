"""v5.137.0: batterijlader blijft overdag aan zolang er iets aan hangt (keuze B).

Gemeten 27-10: een vol apparaat aan de Anker laadt vanzelf bij (~10 min 7 W,
~10 min 2,8 W). Het EMS zag de lage fase als "vol", zette uit, en bij de
kwartiertest begon het bijladen opnieuw: 3-4 schakelingen per uur.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 10, 27, tzinfo=timezone.utc)


def _prijs(hour, minute):
    return 2_500_000


def _config():
    return {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "manual_discharge_power": 1600,
        "batterijlader_switch_entity": "switch.opladers_batterijen",
        "batterijlader_power_sensor_entity": "sensor.opladers_batterijen_power",
        "appliance_notify_service": "notify.telefoon",
    }


def _nu(when):
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def _schakel(hass):
    return [c[1] for c in hass.services.calls if c[0] == "switch" and c[2].get("entity_id") == "switch.opladers_batterijen"]


def _meldingen(hass):
    return [c for c in hass.services.calls if c[0] == "notify"]


def _loop(c, hass, start, minuten, vermogen_op):
    """Elke minuut een ronde; `vermogen_op(minuut)` geeft het vermogen."""
    async def run():
        for m in range(minuten):
            hass.states.set("sensor.opladers_batterijen_power", str(vermogen_op(m)))
            _nu(start + timedelta(minutes=m))
            await c._async_update_locked()
            if _schakel(hass) and _schakel(hass)[-1] == "turn_on":
                hass.states.set("switch.opladers_batterijen", "on")
            elif _schakel(hass) and _schakel(hass)[-1] == "turn_off":
                hass.states.set("switch.opladers_batterijen", "off")
    asyncio.run(run())


RUST = [1.8] * 6   # geleerd rustverbruik van de Anker -> drempel 3,8 W


def _klaar(hass):
    hass.states.set("sensor.price", "0", {"forecast": make_price_forecast(DAY0, _prijs)})
    hass.states.set("switch.opladers_batterijen", "off")
    hass.states.set("sensor.opladers_batterijen_power", "0")


def test_bijladen_houdt_de_lader_aan_en_meldt_een_keer(make_coordinator, hass):
    _klaar(hass)
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)
    # 10 min 7 W, 10 min 2,8 W, en zo door (zoals 27-10 06:04-06:44)
    _loop(c, hass, DAY0.replace(hour=8), 90, lambda m: 7.2 if (m // 10) % 2 == 0 else 2.8)
    # één keer aan, nooit uit
    assert _schakel(hass) == ["turn_on"]
    assert len(_meldingen(hass)) <= 1
    assert c.last_batterijlader_action in ("aan_het_laden", "vol_blijft_aan")


def test_uit_na_een_uur_zonder_lading(make_coordinator, hass):
    _klaar(hass)
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)
    # 15 min laden, daarna alleen nog rust
    _loop(c, hass, DAY0.replace(hour=9), 15 + 61, lambda m: 7.2 if m < 15 else 1.8)
    assert _schakel(hass) == ["turn_on", "turn_off"]
    assert len(_meldingen(hass)) == 1
    assert c.last_batterijlader_action == "wacht_op_apparaat"
    assert c._batterijlader_next_poll_at is not None


def test_vol_status_tussen_vol_en_leeg(make_coordinator, hass):
    _klaar(hass)
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)
    _loop(c, hass, DAY0.replace(hour=10), 15 + 20, lambda m: 7.2 if m < 15 else 1.8)
    assert c.last_batterijlader_action == "vol_blijft_aan"
    assert _schakel(hass) == ["turn_on"]


def test_s_nachts_uit_bij_vol(make_coordinator, hass):
    _klaar(hass)
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)
    c._batterijlader_ever_active_this_session = True
    c._batterijlader_charge_started_at = DAY0.replace(hour=22, minute=0)
    hass.states.set("switch.opladers_batterijen", "on")
    _loop(c, hass, DAY0.replace(hour=22, minute=30), 15, lambda m: 1.8)
    assert _schakel(hass)[-1] == "turn_off"


# --- v5.141.1: alleen bijladen is geen nieuwe lading -----------------
# Gemeten 27-10: rondje van ~1 3/4 uur (test, ~20 min bijladen, een uur
# "vol, blijft aan", uit, kwartier later weer een test), 6x overdag.


def test_bijladen_na_een_test_wacht_langer(make_coordinator, hass):
    _klaar(hass)
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)
    start = DAY0.replace(hour=9)
    # 20 min bijladen, daarna alleen rust: na het uur uit
    _loop(c, hass, start, 20 + 61, lambda m: 7.2 if m < 20 else 1.8)
    assert _schakel(hass) == ["turn_on", "turn_off"]
    wacht = (c._batterijlader_next_poll_at - (start + timedelta(minutes=80))).total_seconds() / 60
    assert wacht >= 60  # niet meer na een kwartier


def test_wachttijd_loopt_op_en_valt_terug_na_echte_lading(make_coordinator, hass):
    c = make_coordinator(_config())
    nu = DAY0.replace(hour=10)
    attr = "last_batterijlader_action"
    kort = nu - timedelta(minutes=80)  # 20 min laden + 60 min laag
    assert c._bijladen_wachttijd(nu, kort, 60, attr) == 60
    assert c._bijladen_wachttijd(nu, kort, 60, attr) == 120
    assert c._bijladen_wachttijd(nu, kort, 60, attr) == 240
    assert c._bijladen_wachttijd(nu, kort, 60, attr) == 240
    lang = nu - timedelta(minutes=150)  # 90 min echte lading
    assert c._bijladen_wachttijd(nu, lang, 60, attr) == 0
    assert c._bijladen_wachttijd(nu, kort, 60, attr) == 60


def test_een_echte_lading_test_daarna_gewoon(make_coordinator, hass):
    _klaar(hass)
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)
    start = DAY0.replace(hour=8)
    _loop(c, hass, start, 45 + 61, lambda m: 7.2 if m < 45 else 1.8)
    assert _schakel(hass) == ["turn_on", "turn_off"]
    wacht = (c._batterijlader_next_poll_at - (start + timedelta(minutes=105))).total_seconds() / 60
    assert wacht <= 15
