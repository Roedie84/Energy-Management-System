"""De verschuiving op de P1-meter telt mee in de reserve (v5.20).

Gemeld op 25 september om 06:53: "accu weer bijna leeg". De accu stond op
12% met nog vijf uur tot het goedkope blok. De reserve had de nacht
doorgerekend alsof de accu alleen het huis dekt - maar de Zendure regelt op
een template "P1 + 50" en houdt de echte meter daardoor op -50 W. Over de
nacht was dat 0,34 kWh extra, precies het tekort van die ochtend.
"""
from datetime import datetime, timedelta, timezone


def _met_regelsensor(c, hass, echt, regel):
    c.config = dict(c.config or {})
    c.config["consumption_power_sensor_entity"] = "sensor.hw_p1_vermogen"
    c.config["control_p1_sensor_entity"] = "sensor.hw_p1_vermogen_100w"
    hass.states.set("sensor.hw_p1_vermogen", str(echt))
    hass.states.set("sensor.hw_p1_vermogen_100w", str(regel))
    return c


def test_de_verschuiving_is_het_verschil_tussen_de_twee_sensoren(make_coordinator, hass):
    """Geen vaste 50 W in de code: het verschil tussen de sensoren IS de
    verschuiving."""
    c = _met_regelsensor(make_coordinator({}), hass, echt=-48, regel=2)

    assert round(c.regelverschuiving_kw(), 3) == 0.05


def test_zonder_instelling_is_er_geen_verschuiving(make_coordinator, hass):
    c = make_coordinator({})

    assert c.regelverschuiving_kw() == 0.0


def test_zonder_meting_is_er_geen_verschuiving(make_coordinator, hass):
    c = _met_regelsensor(make_coordinator({}), hass, echt=-48, regel="unavailable")

    assert c.regelverschuiving_kw() == 0.0


def test_een_negatieve_verschuiving_telt_niet(make_coordinator, hass):
    """Regelt de accu op een HOGERE afname, dan legt dat geen extra beslag
    op de accu."""
    c = _met_regelsensor(make_coordinator({}), hass, echt=50, regel=0)

    assert c.regelverschuiving_kw() == 0.0


def test_de_reserve_telt_de_verschuiving_mee(make_coordinator, hass):
    """Zeven uur nacht met 200 W huis en 50 W verschuiving: 0,35 kWh meer
    tekort dan zonder."""
    c = make_coordinator({})
    c.learned_hourly_avg_kw = lambda uur: 0.2
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: 0.0
    c._uitgedempte_correctie = lambda a, b, r: 1.0
    c._get_smoothed_consumption_correction_ratio = lambda uur: 1.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c._vacation_adjusted_kwh = lambda kwh: kwh
    begin = datetime(2026, 9, 25, 0, 0, tzinfo=timezone.utc)
    eind = begin + timedelta(hours=7)

    c.regelverschuiving_kw = lambda: 0.0
    zonder = c._estimate_worst_case_deficit_kwh(begin, eind)
    c.regelverschuiving_kw = lambda: 0.05
    met = c._estimate_worst_case_deficit_kwh(begin, eind)

    assert round(zonder, 2) == 1.40
    assert round(met - zonder, 2) == 0.35


def test_de_gacs_sensor_bouwt_de_oude_plaat_niet_meer():
    """v5.20: het dashboard leest de plaat sinds v5.19 van de cockpitsensor.
    De GACS-sensor bouwde de oude "overzichtsplaat" nog steeds - zijn
    traagste onderdeel, 85 ms per keer, voor niets."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    sensor = (Path(pkg.__file__).parent / "sensor.py").read_text()

    assert '("overzichtsplaat", self._coordinator.get_overview_svg)' not in sensor
