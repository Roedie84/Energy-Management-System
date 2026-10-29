"""L-EMS-044: de tweeling volgt het kwartierplan (v5.143.0).

Gemeten 28-10 over 60 vergelijkingen: vensters met een laadblok 2,63 kWh
ernaast tegen 0,87 zonder. De tweeling laadde in elk blokkwartier op vol
vermogen, terwijl het kwartierplan maar een paar kwartieren laadt (26-10
00:00 voorspeld 10,34 tegen 2,77), en ontlaadde 's avonds op dure kwartieren
die de sturing door de reserve niet ontlaadt (28-10 20:15-22:15 fout 4,8-5,9).
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

TZ = timezone(timedelta(hours=1))
BEGIN = datetime(2026, 10, 28, 21, 0, tzinfo=TZ)


def _kwartier(i):
    return BEGIN + timedelta(minutes=15 * i)


class _Tweeling:
    """Alleen de simulatie: een blok van 8 uur, of een dure avond."""

    def instelling(self, sleutel, standaard):
        waarde = (self.config or {}).get(sleutel)
        return standaard if waarde is None else waarde

    learned_charge_efficiency_percent = 90
    learned_battery_efficiency_percent = None
    digital_twin_trajectory: list = []
    digital_twin_note = ""

    def __init__(self, modus="smart", duur=False, plan=None, blok=True, beschikbaar=3.0):
        self.last_cheap_block_start = BEGIN if blok else None
        self.last_cheap_block_end = BEGIN + timedelta(hours=8) if blok else None
        self.last_timeline = [
            {
                "start": _kwartier(i).isoformat(),
                "end": _kwartier(i + 1).isoformat(),
                "price_per_kwh": 0.50 if duur else 0.30,
                "mode": modus,
                "is_expensive": duur,
            }
            for i in range(32)
        ]
        self.config = {
            "available_energy_sensor_entity": "sensor.beschikbaar",
            "battery_total_capacity_sensor_entity": "sensor.capaciteit",
        }
        self._plan = plan
        self._beschikbaar = beschikbaar

    def _read_sensor_float(self, entity_id):
        if entity_id == "sensor.capaciteit":
            return 11.52
        return self._beschikbaar

    def beschikbare_energie_kwh(self):
        return self._beschikbaar

    def effective_min_soc_percent(self):
        return 10

    def _max_usable_battery_capacity_kwh(self):
        return 10.37

    def _estimate_pv_kwh_for_period(self, start, einde):
        return 0.0

    def _estimate_consumption_kwh_for_period(self, start, einde):
        return 0.06

    def get_quarter_plan(self, now=None):
        if self._plan is None:
            raise RuntimeError("geen plan")
        return self._plan

    def _resolve_digital_twin_predictions(self, now):
        pass

    def _queue_digital_twin_prediction(self, now):
        pass

    _run_digital_twin_simulation = C._run_digital_twin_simulation
    _twin_plan_cache = None
    _twin_volg_plan = C._twin_volg_plan
    _twin_plan_stappen = C._twin_plan_stappen
    _twin_plan_beginstand = C._twin_plan_beginstand
    _twin_plan_stap_voor = staticmethod(C._twin_plan_stap_voor)
    _twin_laadstap = C._twin_laadstap
    _twin_laadfactor = C._twin_laadfactor


def _plan(stappen, begin=3.0):
    """Plan met per kwartier een stap in kWh (positief = laden uit het net)."""
    soc = begin
    regels = []
    for i, stap in enumerate(stappen):
        soc += stap
        regels.append(
            {
                "start": _kwartier(i).isoformat(),
                "soc_kwh": round(soc, 2),
                "modus": "manual (laden)" if stap > 0 else "smart_discharging",
            }
        )
    return regels


def _draai(obj):
    obj._run_digital_twin_simulation(BEGIN)
    return obj


def test_block_of_8_hours_charges_only_the_4_planned_quarters():
    """Het plan laadt 4 kwartieren van 0,5 kWh; de rest van het blok niets.

    Vóór v5.143.0 laadde de tweeling alle 32 kwartieren tot de accu vol was.
    """
    stappen = [0.0] * 32
    for i in (12, 13, 14, 15):
        stappen[i] = 0.5
    obj = _draai(_Tweeling(plan=_plan(stappen)))

    assert abs(obj.digital_twin_final_soc_kwh - 5.0) < 0.01
    traj = obj.digital_twin_trajectory
    assert traj[11]["soc_kwh"] == 3.0
    assert traj[15]["soc_kwh"] == 5.0
    assert all(p["bron"] == "kwartierplan" for p in traj)


def test_without_a_plan_the_old_block_rule_still_applies():
    obj = _draai(_Tweeling(plan=None))

    # Geen plan: oude regel, laden op vol vermogen tot de bak vol is.
    assert obj.digital_twin_final_soc_kwh > 9.0
    assert all(p["bron"] == "tijdlijn" for p in obj.digital_twin_trajectory)


def test_expensive_evening_held_back_by_the_reserve_is_not_discharged():
    """28-10: dure avond, de sturing hield de accu vast (reserve > beschikbaar).

    Het plan houdt de stand vast (alleen een klein huisverbruik); de tweeling
    ontlaadde voorheen op vol vermogen op elk duur kwartier.
    """
    stappen = [0.0] * 32
    obj = _draai(
        _Tweeling(modus="manual", duur=True, blok=False, plan=_plan(stappen, begin=7.6), beschikbaar=7.6)
    )

    assert abs(obj.digital_twin_final_soc_kwh - 7.6) < 0.01
    assert obj.digital_twin_projected_profit_eur == 0


def test_quarters_beyond_the_plan_fall_back_to_the_timeline():
    stappen = [0.0] * 8
    obj = _draai(_Tweeling(modus="smart_discharging", blok=False, plan=_plan(stappen)))

    bronnen = [p["bron"] for p in obj.digital_twin_trajectory]
    assert bronnen[:8] == ["kwartierplan"] * 8
    assert set(bronnen[8:]) == {"tijdlijn"}
    # Na het plan: huisverbruik 0,06 per kwartier uit de accu.
    assert abs(obj.digital_twin_final_soc_kwh - (3.0 - 24 * 0.06)) < 0.01


def test_plan_steps_never_push_the_twin_below_empty_or_above_full():
    leeg = _draai(_Tweeling(blok=False, plan=_plan([-1.0] * 32), beschikbaar=3.0))
    assert leeg.digital_twin_final_soc_kwh == 0.0
    vol = _draai(_Tweeling(plan=_plan([1.0] * 32)))
    assert vol.digital_twin_final_soc_kwh <= 10.37


def test_first_step_is_measured_against_the_plan_start():
    """soc_kwh in het plan is de stand ná het kwartier; de eerste stap telt
    tegen de beginstand (beschikbaar, begrensd op de bruikbare capaciteit)."""
    plan = [{"start": _kwartier(0).isoformat(), "soc_kwh": 3.5, "modus": "manual (laden)"}]
    stappen = _Tweeling(plan=plan)._twin_plan_stappen(BEGIN)

    assert abs(stappen[_kwartier(0)]["delta_kwh"] - 0.5) < 1e-9
    assert stappen[_kwartier(0)]["net_laden"] is True


def test_grid_charging_cost_counts_through_the_charge_efficiency():
    stappen = [0.0] * 32
    stappen[0] = 0.9
    obj = _draai(_Tweeling(plan=_plan(stappen)))

    # 0,9 kWh erin bij 90 % laadrendement = 1,0 kWh van het net à 0,30.
    assert abs(obj.digital_twin_projected_profit_eur + 0.30) < 1e-6


def test_plan_split_groups_the_error_by_source():
    obj = C.__new__(C)
    obj.digital_twin_accuracy_history = [
        {"fout_kwh": 3.0},
        {"fout_kwh": 0.4, "plan_aandeel": 1.0},
        {"fout_kwh": 0.6, "plan_aandeel": 0.75},
        {"fout_kwh": 1.0, "plan_aandeel": 0.2},
    ]
    split = C.get_digital_twin_plan_split(obj)

    assert split["voor_bouw"] == {"aantal": 1, "gemiddelde_fout_kwh": 3.0}
    assert split["kwartierplan"] == {"aantal": 2, "gemiddelde_fout_kwh": 0.5}
    assert split["tijdlijn"] == {"aantal": 1, "gemiddelde_fout_kwh": 1.0}


def test_queued_prediction_records_the_plan_share(make_coordinator, hass):
    c = make_coordinator({})
    now = BEGIN
    c.digital_twin_trajectory = [
        {
            "start": (now + timedelta(minutes=15 * i)).isoformat(),
            "soc_kwh": 5.0,
            "zon_kwh": 0.0,
            "bron": "kwartierplan" if i < 18 else "tijdlijn",
        }
        for i in range(30)
    ]
    c._digital_twin_pending = []
    c._digital_twin_last_queued = None
    c._queue_digital_twin_prediction(now)

    assert c._digital_twin_pending
    assert c._digital_twin_pending[-1]["plan_aandeel"] == 0.72
