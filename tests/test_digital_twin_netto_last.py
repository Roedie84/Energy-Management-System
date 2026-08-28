"""De tweeling volgt de accustand ook buiten het goedkope blok (v3.35.1).

Gemeten over 60 vergelijkingen in de export van 20 augustus: gemiddeld
1,25 kWh ernaast, zes uur vooruit. Dat is 16% van de bruikbare
capaciteit, en het stond als "onnauwkeurige simulatie" op de kaart.

Het was geen onnauwkeurigheid maar een ontbrekende term. In
`smart_discharging` voedt de accu het huis, en de tweeling liet de stand
ongemoeid - dat stond zelfs met zoveel woorden in de toelichting.

    zes uur x 0,23 kW geleerd huisverbruik = 1,4 kWh

Vrijwel precies de gemeten fout. De kwartierplanning rekende dat allang
uit met `_estimate_pv_kwh_for_period` en
`_estimate_consumption_kwh_for_period`; de tweeling gebruikte ze niet.
"""
from datetime import datetime, timedelta

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


class _Tweeling:

    def instelling(self, sleutel, standaard):
        """v3.56.0: de standaard geldt ook bij een opgeslagen None."""
        waarde = (self.config or {}).get(sleutel)
        return standaard if waarde is None else waarde
    """Alleen de simulatie, met een tijdlijn van zes uur ontladen."""

    last_cheap_block_start = None
    last_cheap_block_end = None
    digital_twin_trajectory: list = []
    digital_twin_note = ""

    def __init__(self, zon_per_kwartier=0.0, huis_per_kwartier=0.0575):
        self.zon = zon_per_kwartier
        self.huis = huis_per_kwartier
        start = datetime(2026, 8, 20, 18, 0)
        self.last_timeline = [
            {
                "start": (start + timedelta(minutes=15 * i)).isoformat(),
                "end": (start + timedelta(minutes=15 * (i + 1))).isoformat(),
                "price_per_kwh": 0.30,
                "mode": "smart_discharging",
                "is_expensive": False,
            }
            for i in range(24)
        ]
        self.config = {"available_energy_sensor_entity": "sensor.beschikbaar"}

    def _read_sensor_float(self, entity_id):
        return 7.0

    def _max_usable_battery_capacity_kwh(self):
        return 7.78

    def _estimate_pv_kwh_for_period(self, start, einde):
        return self.zon

    def _estimate_consumption_kwh_for_period(self, start, einde):
        return self.huis

    def _resolve_digital_twin_predictions(self, now):
        pass

    def _queue_digital_twin_prediction(self, now):
        pass

    _run_digital_twin_simulation = C._run_digital_twin_simulation


def _eind_soc(**kw):
    obj = _Tweeling(**kw)
    obj._run_digital_twin_simulation(datetime(2026, 8, 20, 18, 0))
    return obj.digital_twin_final_soc_kwh


def test_the_battery_now_empties_while_it_feeds_the_house():
    """Zes uur ontladen bij 0,23 kW hoort ongeveer 1,4 kWh te kosten.

    Vóór v3.35.1 bleef de stand op 7,0 staan - precies de fout die als
    "gemiddelde afwijking 1,25 kWh" op de kaart kwam.
    """
    eind = _eind_soc()

    assert eind < 7.0
    assert 5.4 < eind < 5.8


def test_sun_surplus_charges_the_battery():
    """Andersom net zo goed: meer zon dan verbruik vult de accu."""
    eind = _eind_soc(zon_per_kwartier=0.2, huis_per_kwartier=0.05)

    assert eind > 7.0


def test_the_battery_never_goes_below_empty():
    obj = _Tweeling(huis_per_kwartier=2.0)
    obj._read_sensor_float = lambda e: 0.4
    obj._run_digital_twin_simulation(datetime(2026, 8, 20, 18, 0))

    assert obj.digital_twin_final_soc_kwh >= 0.0


def test_the_battery_never_goes_above_full():
    obj = _Tweeling(zon_per_kwartier=3.0, huis_per_kwartier=0.0)
    obj._run_digital_twin_simulation(datetime(2026, 8, 20, 18, 0))

    assert obj.digital_twin_final_soc_kwh <= 7.78


def test_the_discharge_power_still_caps_it():
    """Een huis dat meer trekt dan de omvormer kan leveren, trekt niet

    meer uit de accu dan de omvormer kan leveren.
    """
    obj = _Tweeling(huis_per_kwartier=5.0)
    obj.config["manual_discharge_power"] = 800
    obj._run_digital_twin_simulation(datetime(2026, 8, 20, 18, 0))

    # 24 kwartieren x 0,25 uur x 0,8 kW = 4,8 kWh, dus niet leeg vanaf 7.
    assert obj.digital_twin_final_soc_kwh > 2.0


def test_the_note_no_longer_claims_the_simplification():
    """De toelichting zei letterlijk dat er geen huishoudverbruik werd

    gemodelleerd. Dat klopt niet meer.
    """
    obj = _Tweeling()
    obj._run_digital_twin_simulation(datetime(2026, 8, 20, 18, 0))

    assert "geen huishoudverbruik" not in obj.digital_twin_note
    assert "huisverbruik" in obj.digital_twin_note
