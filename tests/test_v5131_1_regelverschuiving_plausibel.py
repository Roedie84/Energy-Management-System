"""v5.131.1 (H-EMS-14): een onaannemelijke regelverschuiving telt niet.

Live 26-10 15:00:25, direct na een herstart: de regelsensor en de
verbruikssensor liepen uit de pas, `regelverschuiving_w` 1462/1497 W. Over
20 uur tot het blok werd de reserve 14 s lang 76,1/78,8 kWh in een accu van
10,37 kWh; 15:00:39 weer normaal.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import REGELVERSCHUIVING_MAX_W


def _met_regelsensor(c, hass, echt, regel):
    c.config = dict(c.config or {})
    c.config["consumption_power_sensor_entity"] = "sensor.hw_p1_vermogen"
    c.config["control_p1_sensor_entity"] = "sensor.hw_p1_vermogen_100w"
    hass.states.set("sensor.hw_p1_vermogen", str(echt))
    hass.states.set("sensor.hw_p1_vermogen_100w", str(regel))
    return c


def _ronde(c, minuut):
    c._forecast_cache_ronde = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc) + timedelta(minutes=minuut)


def test_grens_is_ruim_boven_de_bewuste_verschuiving():
    assert 100 <= REGELVERSCHUIVING_MAX_W <= 300


def test_opstartpiek_zonder_eerdere_meting_telt_als_nul(make_coordinator, hass):
    c = _met_regelsensor(make_coordinator({}), hass, echt=-1480, regel=-18)
    _ronde(c, 0)
    assert c.regelverschuiving_kw() == 0.0
    verworpen = c._regelverschuiving_verworpen
    assert verworpen["gemeten_w"] == 1462 and verworpen["gebruikt_w"] == 0
    assert verworpen["aantal"] == 1


def test_piek_houdt_de_laatste_aannemelijke_waarde(make_coordinator, hass):
    c = _met_regelsensor(make_coordinator({}), hass, echt=-28, regel=-18)
    _ronde(c, 0)
    assert round(c.regelverschuiving_kw(), 3) == 0.01
    hass.states.set("sensor.hw_p1_vermogen", "-1515")
    _ronde(c, 1)
    assert round(c.regelverschuiving_kw(), 3) == 0.01
    assert c._regelverschuiving_verworpen["gebruikt_w"] == 10
    # weer in de pas: gewoon meten
    hass.states.set("sensor.hw_p1_vermogen", "-68")
    _ronde(c, 2)
    assert round(c.regelverschuiving_kw(), 3) == 0.05


def test_net_onder_de_grens_telt_nog(make_coordinator, hass):
    c = _met_regelsensor(make_coordinator({}), hass, echt=-(REGELVERSCHUIVING_MAX_W - 1), regel=0)
    _ronde(c, 0)
    assert round(c.regelverschuiving_kw() * 1000) == REGELVERSCHUIVING_MAX_W - 1
    assert getattr(c, "_regelverschuiving_verworpen", None) is None


def test_reserve_blijft_binnen_de_accu_bij_een_opstartpiek(make_coordinator, hass):
    """20 u tot het blok met 200 W huis: met de piek zou er 29 kWh bij komen."""
    c = _met_regelsensor(make_coordinator({}), hass, echt=-1480, regel=-18)
    _ronde(c, 0)
    c.learned_hourly_avg_kw = lambda uur: 0.2
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: 0.0
    c._uitgedempte_correctie = lambda a, b, r: 1.0
    c._get_smoothed_consumption_correction_ratio = lambda uur: 1.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c._vacation_adjusted_kwh = lambda kwh: kwh
    begin = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)
    segmenten = c._segmenten_verbruik_zon(begin, begin + timedelta(hours=20))
    assert segmenten is not None
    assert sum(s[0] for s in segmenten) < 5.0
