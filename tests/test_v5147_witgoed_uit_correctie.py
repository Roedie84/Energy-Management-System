"""v5.147.0 (akkoord Ruud 29-10, beide punten).

1. Witgoed telt niet mee in de live verbruikscorrectie.
   Gezien 29-10 15:44: de vaatwasser trok 14:50-15:40 steeds 0,6-2,2 kW en was
   klaar; het huis gebruikte 0,42 kW, maar het kwartierplan rekende tot 17:45
   met 2,3-2,6 kW huisverbruik (accu 92 % -> 47 %, geen verkoop bij 57-80 ct).
   De metingen uit de verwarmingsfasen bleven in het mediaanvenster van 30
   minuten staan. Het gemeten vermogen van vaatwasser en wasmachine gaat er nu
   af voordat een meting het venster in gaat.

2. De kasprijs toont tot de eerste lading een schatting (de kostprijs) met
   `kasprijs_geschat`, in plaats van een streepje.
"""
from pathlib import Path


def _c(make_coordinator, hass, vaat_w, was_w=None):
    c = make_coordinator({
        "dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen",
        "washing_machine_power_sensor_entity": "sensor.wasmachine_vermogen",
    })
    hass.states.set("sensor.vaatwasser_vermogen", str(vaat_w))
    if was_w is not None:
        hass.states.set("sensor.wasmachine_vermogen", str(was_w))
    c._recent_consumption_readings_kw = []
    return c


def test_vaatwasser_gaat_er_af(make_coordinator, hass):
    c = _c(make_coordinator, hass, 2000)
    c._read_corrected_consumption_power = lambda: 2420.0

    c._track_recent_consumption_reading(None)

    assert c._recent_consumption_readings_kw[-1] == 0.42


def test_vaatwasser_en_wasmachine_samen(make_coordinator, hass):
    c = _c(make_coordinator, hass, 600, 1800)
    c._read_corrected_consumption_power = lambda: 2800.0

    c._track_recent_consumption_reading(None)

    assert c._recent_consumption_readings_kw[-1] == 0.4


def test_nooit_onder_nul(make_coordinator, hass):
    """Meet de vaatwassersensor even meer dan het huis (andere momenten)."""
    c = _c(make_coordinator, hass, 2500)
    c._read_corrected_consumption_power = lambda: 2000.0

    c._track_recent_consumption_reading(None)

    assert c._recent_consumption_readings_kw[-1] == 0.0


def test_zonder_witgoed_ongewijzigd(make_coordinator, hass):
    c = make_coordinator({})
    c._recent_consumption_readings_kw = []
    c._read_corrected_consumption_power = lambda: 900.0

    c._track_recent_consumption_reading(None)

    assert c._recent_consumption_readings_kw[-1] == 0.9


def test_kasprijs_schatting_tot_de_eerste_lading():
    import custom_components.energy_management_system as pkg

    sensor = (Path(pkg.__file__).parent / "sensor.py").read_text(encoding="utf-8")
    js = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert '"kasprijs_geschat": self._coordinator.battery_cash_basis_eur_per_kwh is None' in sensor
    assert 'if last_state.attributes.get("kasprijs_geschat"):' in sensor
    assert 'attr(s, "kasprijs_geschat") === true' in js
