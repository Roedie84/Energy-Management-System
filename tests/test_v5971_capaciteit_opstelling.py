"""v5.97.1: een module erbij maakt de oude capaciteitsmetingen ongeldig;
de kruiscontrole rekent de beschikbare energie juist terug."""
import pytest


def _reeks_oud_en_nieuw():
    reeks = [{"datum": f"2026-09-{d:02d}", "capaciteit_kwh": 8.64, "doorzet_kwh": 1.0}
             for d in range(1, 31)]
    reeks += [{"datum": f"2026-10-{d:02d}", "capaciteit_kwh": 8.64, "doorzet_kwh": 1.0}
              for d in range(1, 15)]
    reeks += [{"datum": "2026-10-10", "capaciteit_kwh": 8.07, "doorzet_kwh": None, "bron": "kalibratie"}]
    return reeks


def test_oude_kalibratie_telt_niet_na_een_extra_module(make_coordinator, hass):
    c = make_coordinator({"battery_total_capacity_sensor_entity": "sensor.capaciteit"})
    hass.states.set("sensor.capaciteit", "11.52")
    c.capacity_trend_history = _reeks_oud_en_nieuw()
    assert c.gemeten_capaciteit_kwh() is None
    assert c.bruikbare_capaciteit_kwh() == pytest.approx(11.52)


def test_zonder_wijziging_blijft_de_kalibratie_gelden(make_coordinator, hass):
    c = make_coordinator({"battery_total_capacity_sensor_entity": "sensor.capaciteit"})
    hass.states.set("sensor.capaciteit", "8.64")
    c.capacity_trend_history = _reeks_oud_en_nieuw()
    assert c.gemeten_capaciteit_kwh() == pytest.approx(8.07, abs=0.01)


def test_nieuwe_kalibratie_met_eigen_nominaal_telt(make_coordinator, hass):
    c = make_coordinator({"battery_total_capacity_sensor_entity": "sensor.capaciteit"})
    hass.states.set("sensor.capaciteit", "11.52")
    c.capacity_trend_history = _reeks_oud_en_nieuw() + [
        {"datum": "2026-10-14", "capaciteit_kwh": 11.1, "bron": "kalibratie", "nominaal_kwh": 11.52}
    ]
    assert c.gemeten_capaciteit_kwh() == pytest.approx(11.1, abs=0.01)


def test_kruiscontrole_rekent_met_nominaal_maal_honderd(make_coordinator, hass):
    """14-10: (84 - 10) % x 11,52 = 8,5248 kWh; terugrekenen geeft 84 %."""
    c = make_coordinator({
        "battery_total_capacity_sensor_entity": "sensor.capaciteit",
        "battery_min_soc_number_entity": "number.min_soc",
        "battery_soc_sensor_entity": "sensor.soc",
        "available_energy_sensor_entity": "sensor.beschikbaar",
    })
    hass.states.set("sensor.capaciteit", "11.52")
    hass.states.set("number.min_soc", "10.0")
    hass.states.set("sensor.soc", "84")
    hass.states.set("sensor.beschikbaar", "8.5248")
    c.bruikbare_capaciteit_kwh = lambda: 8.07   # een oude meting telt hier niet
    regel = next(r for r in c.get_spiegelcontrole()
                 if r["naam"] == "Accustand tegen beschikbare energie")
    assert regel["oordeel"] == "sluit_aan"
    assert abs(regel["verschil"]) < 0.1
