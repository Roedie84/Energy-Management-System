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


# --- de splitsing kreeg nooit een dagvergelijking (v3.64.0) ----------


def test_every_trajectory_point_carries_the_expected_sun():
    """Gemeten in de export van 28 augustus 17:58: zestig van de zestig

    vergelijkingen stonden als "zonder zon", nul met zon - terwijl er
    die dag uren zon waren geweest.

    Twee fouten. De punten in de tijdlijn droegen alleen `start`, `mode`
    en `soc_kwh`; de lus in `_queue_digital_twin_prediction` telde dus
    een sleutel op die er nooit in heeft gezeten en kwam altijd op nul
    uit. En `zon_kwh` werd alleen berekend in de ontlaadtak, dus in de
    andere takken bestond hij niet eens.

    Daarmee deed de splitsing van v3.45.0 niets: alles heette nacht, ook
    het midden van de dag.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C._run_digital_twin_simulation)

    # De zon wordt bepaald vóór de takken, en gaat mee in elk punt.
    berekend = bron.index("zon_kwh = self._estimate_pv_kwh_for_period")
    eerste_tak = bron.index("if mode == OPTION_MANUAL")

    assert berekend < eerste_tak, "zon_kwh hoort vóór de takken te staan"
    assert '"zon_kwh": round(zon_kwh, 3)' in bron


def test_a_sunny_point_is_labelled_as_such(make_coordinator, hass):
    """De sleutel die de splitsing leest, moet er ook echt in zitten."""
    obj = _Tweeling(zon_per_kwartier=0.4)
    obj._run_digital_twin_simulation(datetime(2026, 8, 28, 12, 0))

    assert obj.digital_twin_trajectory
    assert all("zon_kwh" in punt for punt in obj.digital_twin_trajectory)
    assert obj.digital_twin_trajectory[0]["zon_kwh"] == 0.4


# --- geen dubbele afrekeningen (v3.73.0) -----------------------------


def test_two_predictions_for_the_same_moment_count_once(
    make_coordinator, hass
):
    """Gevonden bij het opruimen op 29 augustus: twee vergelijkingen op

    hetzelfde moment, met bijna dezelfde waarde:

        28-08 15:30  voorspeld 7,061  fout 0,715
        28-08 15:30  voorspeld 6,594  fout 1,182

    `_digital_twin_last_queued` is vluchtig, dus na een herstart verviel
    de wachttijd en werd er meteen opnieuw ingelegd. Zes uur later komen
    die twee samen aan en tellen ze allebei mee in de gemiddelde fout.
    """
    c = make_coordinator({})
    c.digital_twin_accuracy_history = [
        {"moment": "2026-08-28T15:30:00+02:00", "fout_kwh": 0.715},
        {"moment": "2026-08-28T15:30:00+02:00", "fout_kwh": 1.182},
        {"moment": "2026-08-28T21:30:00+02:00", "fout_kwh": 0.4},
    ]
    c._digital_twin_pending = []

    c._resolve_digital_twin_predictions(datetime(2026, 8, 29, 10, 0))

    momenten = [r["moment"] for r in c.digital_twin_accuracy_history]
    assert len(momenten) == len(set(momenten))
    # De eerste blijft staan.
    assert c.digital_twin_accuracy_history[0]["fout_kwh"] == 0.715


def test_the_queue_moment_survives_a_restart(make_coordinator, hass):
    """De openstaande voorspellingen weten zelf wanneer ze zijn

    ingelegd, en die overleven de herstart wél.
    """
    c = make_coordinator({})
    c._digital_twin_last_queued = None
    c._digital_twin_pending = [
        {"voorspeld_op": "2026-08-29T09:00:00+02:00", "doelmoment": "x"}
    ]

    laatst = c._digital_twin_laatst_ingelegd(
        datetime(2026, 8, 29, 9, 30, tzinfo=None)
    )

    assert laatst is not None
    assert laatst.hour == 9
