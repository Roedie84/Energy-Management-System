"""Geen verliezen meer na een herstart (v1.0.4).

Gevraagd: "kijk naar de gehele integratie welke waardes eventueel
verloren gaan na een herstart, ik wil algeheel geen verliezen".

Een inventarisatie van alle 286 attributen in de coordinator liet zien
dat het overgrote deel elke tick opnieuw wordt berekend - dat verliezen
is onschadelijk. Maar een deel is echt OPGEBOUWD (maandenlange
leergeschiedenis, cumulatieve financiële tellers) en verdween tot v1.0.3
bij elke herstart.

Opgelost met één gedeelde Store in plaats van tientallen losse
RestoreEntity-paden, waarin twee eerdere lessen samenkomen:
entiteit-attributen hebben een recorder-limiet van 16 KB (v0.63.66), en
de laadvolgorde moet vóór platform-setup liggen (v0.63.115).
"""
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    PERSISTED_DATE_FIELDS,
    PERSISTED_DATETIME_FIELDS,
    PERSISTED_INT_FIELDS,
    PERSISTED_PLAIN_FIELDS,
)

STORE_KEY = "energy_management_system_state"
NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _vul_alles(c):
    """Zet elk persistent veld op een herkenbare waarde."""
    c.battery_module_health = {"1": {"geschiedenis": {"temperatuur_afwijking_c": [1.0] * 30}}}
    c.energy_balance_error_history = [10.0, 20.0, 30.0]
    c.mode_change_log = [{"moment": "2026-08-06T10:00:00", "modus": "manual"}]
    c.discharge_floor_events = [{"moment": "2026-08-06T11:00:00"}]
    c.dishwasher_cycle_duration_history = [120.0, 130.0]
    c.dishwasher_usage_hourly_history = {"18": 4}
    c.washing_machine_cycle_duration_history = [90.0]
    c.washing_machine_usage_hourly_history = {"9": 2}
    c.living_room_temp_bucket_humidity = {"24.0": [45.0, 46.0]}
    c.battery_cooling_history = [{"actie": "aan", "reden": "test"}]
    c.actual_cost_today_eur = 1.11
    c.actual_cost_current_month_eur = 22.22
    c.actual_cost_all_time_eur = 333.33
    c.counterfactual_cost_today_eur = 2.22
    c.counterfactual_cost_current_month_eur = 33.33
    c.counterfactual_cost_all_time_eur = 444.44
    c.charge_pv_kwh_total = 12.5
    c.charge_grid_kwh_total = 3.5
    c.discharge_export_kwh_total = 4.5
    c.forgone_feedin_eur_total = 0.55
    c.co2_emitted_today_kg = 1.75
    c.pv_production_today_kwh = 15.0
    c.pv_export_today_kwh = 6.0
    c.gross_consumption_today_kwh = 9.0
    c.grid_import_today_kwh = 2.0
    c.peak_power_today_w = 941.0
    c.water_sessions_today_l = 27.3
    c.water_sessions_today_count = 6
    c._water_sessions_day_key = date(2026, 8, 6)
    c._battery_module_day_key = date(2026, 8, 6)
    c._peak_power_day_key = date(2026, 8, 6)
    c._counterfactual_day_key = date(2026, 8, 6)
    c._self_sufficiency_day_key = date(2026, 8, 6)
    c._co2_day_key = date(2026, 8, 6)
    c._peak_power_month_key = 202608
    c._counterfactual_month_key = 202608
    c._summary_month_key = 202608
    c.battery_cooling_last_change = NOW


def _herstart(make_coordinator, bron):
    """Slaat op en laadt in een verse coordinator - de echte herstart."""
    import asyncio

    asyncio.run(bron.async_save_persisted_state_now())
    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())
    return verse


# --- de kern --------------------------------------------------------


def test_months_of_learned_module_health_survive(make_coordinator, hass):
    """Het duurste verlies: de accu-modulebewaking bouwt maandenlang op
    voordat drift-detectie iets kan zeggen."""
    bron = make_coordinator({})
    _vul_alles(bron)

    verse = _herstart(make_coordinator, bron)

    geschiedenis = verse.battery_module_health["1"]["geschiedenis"]
    assert len(geschiedenis["temperatuur_afwijking_c"]) == 30


def test_cumulative_financial_totals_survive(make_coordinator, hass):
    bron = make_coordinator({})
    _vul_alles(bron)

    verse = _herstart(make_coordinator, bron)

    assert verse.actual_cost_all_time_eur == 333.33
    assert verse.counterfactual_cost_all_time_eur == 444.44
    assert verse.charge_pv_kwh_total == 12.5
    assert verse.forgone_feedin_eur_total == 0.55


def test_appliance_learning_survives(make_coordinator, hass):
    bron = make_coordinator({})
    _vul_alles(bron)

    verse = _herstart(make_coordinator, bron)

    assert verse.dishwasher_cycle_duration_history == [120.0, 130.0]
    assert verse.washing_machine_usage_hourly_history == {"9": 2}


def test_mode_change_log_survives(make_coordinator, hass):
    """Het Geschiedenis-tabblad was na elke herstart leeg."""
    bron = make_coordinator({})
    _vul_alles(bron)

    verse = _herstart(make_coordinator, bron)

    assert len(verse.mode_change_log) == 1


def test_every_persisted_field_round_trips(make_coordinator, hass):
    """Dekkingstest: elk veld in de lijst moet daadwerkelijk terugkomen.
    Een veld toevoegen aan de lijst zonder werkende (de)serialisatie zou
    anders stil misgaan."""
    bron = make_coordinator({})
    _vul_alles(bron)

    verse = _herstart(make_coordinator, bron)

    for veld in PERSISTED_PLAIN_FIELDS + PERSISTED_INT_FIELDS:
        assert getattr(verse, veld) == getattr(bron, veld), veld
    for veld in PERSISTED_DATE_FIELDS + PERSISTED_DATETIME_FIELDS:
        assert getattr(verse, veld) == getattr(bron, veld), veld


# --- de datum-sleutels ----------------------------------------------


def test_date_keys_come_back_as_dates_not_strings(make_coordinator, hass):
    """Zouden ze als tekst terugkomen, dan is de vergelijking met
    `now.date()` altijd ongelijk en springen de dagtellers bij de
    eerstvolgende tick alsnog op nul - dan was het terugzetten
    zinloos."""
    bron = make_coordinator({})
    _vul_alles(bron)

    verse = _herstart(make_coordinator, bron)

    for veld in PERSISTED_DATE_FIELDS:
        assert isinstance(getattr(verse, veld), date), veld


def test_today_counters_are_not_wiped_on_the_next_tick(make_coordinator, hass):
    """Het gedrag waar die datum-sleutels voor bestaan, end-to-end."""
    bron = make_coordinator({})
    _vul_alles(bron)
    bron._peak_power_day_key = NOW.date()

    verse = _herstart(make_coordinator, bron)
    verse._update_peak_power_tracking(NOW)

    assert verse.peak_power_today_w == 941.0


def test_an_unreadable_date_does_not_crash_startup(make_coordinator, hass):
    """Liever een teller die één dag opnieuw begint dan een integratie
    die niet opstart."""
    c = make_coordinator({})

    c._apply_persisted_state({"_peak_power_day_key": "geen-datum"})

    assert c._peak_power_day_key is None


# --- robuustheid ----------------------------------------------------


def test_missing_keys_keep_their_starting_value(make_coordinator, hass):
    """Een opslagbestand van een oudere versie kent nieuwe velden niet;
    die mogen dan niet hun beginwaarde kwijtraken."""
    c = make_coordinator({})
    c.charge_pv_kwh_total = 5.0

    c._apply_persisted_state({"actual_cost_all_time_eur": 1.0})

    assert c.charge_pv_kwh_total == 5.0
    assert c.actual_cost_all_time_eur == 1.0


def test_loading_is_idempotent(make_coordinator, hass):
    """De load draait vóór platform-setup; een tweede aanroep mag niet
    over verser geheugen heen lezen."""
    import asyncio

    bron = make_coordinator({})
    _vul_alles(bron)
    asyncio.run(bron.async_save_persisted_state_now())

    verse = make_coordinator({})

    async def run():
        await verse.async_load_persisted_state()
        verse.actual_cost_all_time_eur = 999.0
        await verse.async_load_persisted_state()

    asyncio.run(run())

    assert verse.actual_cost_all_time_eur == 999.0


def test_an_empty_store_leaves_everything_alone(make_coordinator, hass):
    """Een verse installatie mag niet op nul worden gezet door een
    opslag die er nog niet is."""
    import asyncio

    c = make_coordinator({})
    c.actual_cost_all_time_eur = 7.0

    asyncio.run(c.async_load_persisted_state())

    assert c.actual_cost_all_time_eur == 7.0


# --- inbedding ------------------------------------------------------


def test_state_is_saved_during_a_normal_update(make_coordinator, hass):
    """Zonder opslag tijdens het draaien zou alleen een nette afsluiting
    iets bewaren - en juist een onverwachte herstart is het geval dat
    telt."""
    import asyncio

    c = make_coordinator({})
    c.actual_cost_all_time_eur = 42.0
    c.schedule_persisted_state_save()

    opgeslagen = hass._fake_store_backing.get(STORE_KEY)
    assert opgeslagen is not None
    assert opgeslagen["actual_cost_all_time_eur"] == 42.0
    assert asyncio is not None


def test_setup_loads_state_before_the_platforms():
    """Zelfde volgorde-eis als de NILM-store (v0.63.115): entiteiten met
    een eigen herstelpad draaien anders eerder en kunnen op verkeerde
    aannames handelen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "__init__.py").read_text()

    laden = bron.index("async_load_persisted_state()")
    platforms = bron.index("async_forward_entry_setups(")
    assert laden < platforms


def test_unload_forces_an_immediate_save():
    """Een geplande, nog niet uitgevoerde opslag zou bij een herstart
    alsnog verloren gaan."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    unload = bron.index("async def async_unload")
    assert "async_save_persisted_state_now" in bron[unload : unload + 900]


def test_per_tick_values_are_deliberately_not_persisted():
    """Bewust GEEN volledige momentopname: een per-tick berekende waarde
    terugzetten zou een verouderd getal tonen alsof het actueel is, wat
    erger is dan hem opnieuw laten berekenen."""
    vluchtig = (
        "last_explanation",
        "last_timeline",
        "climate_forecast_trajectory",
        "digital_twin_trajectory",
        "mpc_planned_actions",
        "advisory_readiness",
        "battery_module_live",
        "nilm_unconfirmed_candidates",
        "weather_ensemble_cloud_cover_percent",
    )
    alles = PERSISTED_PLAIN_FIELDS + PERSISTED_INT_FIELDS
    for veld in vluchtig:
        assert veld not in alles, veld


# --- borging tegen toekomstige gaten --------------------------------

# Velden die op naam als "opgebouwd" ogen maar dat niet zijn. Bewust
# expliciet: wie hier iets aan toevoegt moet zich afvragen of het echt
# afleidbaar is, in plaats van dat de test stilzwijgend meegeeft.
GEEN_OPGEBOUWDE_TOESTAND = {
    # Een vlag die bij het opstarten opnieuw wordt gezet, geen
    # geschiedenis - de naam suggereert alleen iets anders.
    "was_bootstrapped_from_history",
}


def _opgebouwde_velden():
    """Alle publieke coordinator-attributen die op naam opgebouwde
    toestand zijn: geschiedenislijsten en cumulatieve totalen."""
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    tree = ast.parse((Path(pkg.__file__).parent / "coordinator.py").read_text())
    coord = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and "Coordinator" in n.name
    )
    init = next(
        n
        for n in coord.body
        if isinstance(n, ast.FunctionDef) and n.name == "__init__"
    )

    velden = set()
    for node in ast.walk(init):
        doelen = (
            node.targets
            if isinstance(node, ast.Assign)
            else ([node.target] if isinstance(node, ast.AnnAssign) else [])
        )
        for doel in doelen:
            if (
                isinstance(doel, ast.Attribute)
                and isinstance(doel.value, ast.Name)
                and doel.value.id == "self"
            ):
                velden.add(doel.attr)

    return {
        veld
        for veld in velden
        if not veld.startswith("_")
        and (
            veld.endswith("_history")
            or veld.startswith("total_")
            or veld.endswith("_total")
            or veld.endswith("_kwh_total")
        )
    }


def test_no_accumulated_field_is_left_unpersisted():
    """De borging waar het om draait.

    De inventarisatie die tot v1.0.4 leidde was handwerk; deze test
    herhaalt hem bij elke run. Een nieuw geschiedenis- of totaalveld dat
    noch in de Store-lijst staat, noch ergens door een RestoreEntity
    wordt teruggezet, laat de suite falen - in plaats van pas op te
    vallen als iemand na een herstart zijn opgebouwde gegevens kwijt is.
    """
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    map_ = Path(pkg.__file__).parent
    herstelcode = "".join(
        (map_ / bestand).read_text()
        for bestand in ("sensor.py", "solar_forecast.py", "switch.py")
    )

    gaten = []
    for veld in sorted(_opgebouwde_velden()):
        if veld in GEEN_OPGEBOUWDE_TOESTAND:
            continue
        in_store = veld in PERSISTED_PLAIN_FIELDS
        elders_hersteld = bool(re.search(rf"coordinator\.{veld}\s*=", herstelcode))
        if not in_store and not elders_hersteld:
            gaten.append(veld)

    assert not gaten, (
        "deze opgebouwde velden overleven geen herstart - zet ze in "
        f"PERSISTED_PLAIN_FIELDS of geef ze een RestoreEntity: {gaten}"
    )


def test_the_exception_list_stays_honest():
    """Elke uitzondering moet nog bestaan. Een naam die na een
    hernoeming blijft staan zou stilzwijgend een echt veld kunnen gaan
    afdekken."""
    bestaand = _opgebouwde_velden()
    for veld in GEEN_OPGEBOUWDE_TOESTAND:
        assert veld in bestaand, f"uitzondering '{veld}' bestaat niet meer"
