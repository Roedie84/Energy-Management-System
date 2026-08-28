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
    c._plan_review_day_key = date(2026, 8, 6)
    # v1.49.0: de dagstand van de PV-geometrie werd bij elke herstart
    # weggegooid, waardoor "0/5 heldere dagen" op een strakblauwe dag
    # een zelfvervullende voorspelling was.
    c._pv_geometry_day_key = date(2026, 8, 6)
    c._pv_geometry_day_peak_w = 2900.0
    c._pv_geometry_day_peak_azimuth = 183.0
    c._pv_geometry_day_expected_peak_w = 3000.0
    c._co2_day_key = date(2026, 8, 6)
    # v3.33.0: de dagportie van de goedkope koeling. Zonder bewaren is
    # de bovengrens te omzeilen door de integratie te herladen.
    c.goedkope_koeling_teldag = date(2026, 8, 6)
    c.goedkope_koeling_teller = 3
    c._peak_power_month_key = 202608
    c._counterfactual_month_key = 202608
    c._summary_month_key = 202608
    # v1.1.8: een opslag die door de HUIDIGE versie is geschreven bevat
    # dit nummer. Ontbreekt het, dan is de opslag van vóór v1.1.6 en
    # hoort de balansreeks juist gewist te worden - zie
    # test_an_old_store_clears_the_balance_history.
    from custom_components.energy_management_system.const import (
        ENERGY_BALANCE_METHOD_VERSION,
    )

    c.energy_balance_method_version = ENERGY_BALANCE_METHOD_VERSION
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
    assert "async_save_persisted_state_now" in bron[unload : unload + 2000]


def test_per_tick_values_are_deliberately_not_persisted():
    """Bewust GEEN volledige momentopname: een per-tick berekende waarde
    terugzetten zou een verouderd getal tonen alsof het actueel is, wat
    erger is dan hem opnieuw laten berekenen.

    v1.43.0: `nilm_unconfirmed_candidates` staat hier NIET meer bij, en
    dat is een omkering van een eerdere keuze. De lijst wordt inderdaad
    elke tick opnieuw gevuld uit de entiteitenscan - maar één veld niet:
    `first_seen`, de dag waarop een apparaat voor het eerst opviel. Dat
    telde na elke herstart opnieuw vanaf nul, waardoor "dit apparaat
    wordt al tien dagen gezien" nooit verder kwam dan vandaag. Het
    vermogen dat één tick oud is wordt onmiddellijk overschreven; de
    datum niet.
    """
    vluchtig = (
        "last_explanation",
        "last_timeline",
        "climate_forecast_trajectory",
        "digital_twin_trajectory",
        "mpc_planned_actions",
        "advisory_readiness",
        "battery_module_live",
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
    # v2.1.0: de rondeduur meet de HUIDIGE versie op de HUIDIGE machine.
    # Metingen van voor een herstart zeggen daar niets over - een
    # herstart komt meestal juist door een nieuwe versie, en dan is de
    # oude meting niet meer geldig.
    "tick_duration_history",
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


def test_an_old_store_clears_the_balance_history(make_coordinator, hass):
    """v1.1.8: het wismechanisme uit v1.1.6 kon nooit afgaan.

    Het versieveld begon op de HUIDIGE waarde, dus de vergelijking was
    altijd gelijk zodra de opslag dat veld nog niet kende - precies het
    geval waarvoor het bedoeld was. In een echte export stond de
    balansreeks daardoor nog vol metingen van de oude meetmethode.
    """
    import asyncio

    bron = make_coordinator({})
    bron.energy_balance_error_history = [15330.1, 2014.7]
    # Opslag van vóór v1.1.6: het versieveld ontbreekt.
    bron.energy_balance_method_version = None
    asyncio.run(bron.async_save_persisted_state_now())

    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())

    assert verse.energy_balance_error_history == []


def test_a_current_store_keeps_the_balance_history(make_coordinator, hass):
    """Anders zou elke herstart de meting terugzetten."""
    import asyncio

    from custom_components.energy_management_system.const import (
        ENERGY_BALANCE_METHOD_VERSION,
    )

    bron = make_coordinator({})
    bron.energy_balance_error_history = [45.0, 80.0]
    bron.energy_balance_method_version = ENERGY_BALANCE_METHOD_VERSION
    asyncio.run(bron.async_save_persisted_state_now())

    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())

    assert verse.energy_balance_error_history == [45.0, 80.0]


# --- v1.43.0: de inventarisatie zelf --------------------------------

# Gevraagd: "Wordt nu echt alle data opgeslagen, zodat een herstart
# nergens meer invloed op heeft?"
#
# Dat viel niet te beantwoorden zonder alles met de hand na te lopen -
# en dus ook niet vol te houden. Deze test doet het voortaan: elk veld
# dat in `__init__` als lege verzameling of nulteller begint, moet in
# precies één van drie bakken vallen. Wie er een nieuwe bijzet en niets
# kiest, krijgt hier een rode test in plaats van stille dataverlies.
VLUCHTIG_MET_REDEN = {
    "mpc_doel_soc": "de doel-SOC-lijn over de MPC-horizon; elke ronde opnieuw achteruit gerekend uit zon en verbruik",
    "_mpc_gemeten_op": "welke dag de MPC-vergelijking al is vastgelegd; na een herstart mag die dag opnieuw gemeten worden",
    "mpc_balans": "de energiebalans over de MPC-horizon; elke ronde opnieuw berekend uit prijzen, zon en verbruik",
    "bestandscontrole": "de uitkomst van de hashvergelijking bij het opstarten; na een herstart hoort die opnieuw berekend te worden",
    "_meterstand_bij_cyclusstart": "de meterstand bij het begin van een lopende apparaatcyclus; na een herstart is die cyclus toch niet meer te sluiten",
    "meting_tijdstippen": "wanneer elk gespiegeld veld voor het laatst uit zijn sensor kwam; na een herstart hoort dat leeg te zijn",
    "last_plan_shortfall": "elke tick herrekend uit de kwartierplanning",
    # Elke tick opnieuw berekend; terugzetten zou een oud getal tonen
    # alsof het actueel is.
    "last_solar_defer_plan": "elke tick herrekend",
    "last_sell_check": "elke tick herrekend",
    "last_battery_vs_grid": "elke tick herrekend",
    "last_timeline": "elke tick herrekend",
    "last_transitions": "elke tick herrekend",
    "last_needed_kwh_breakdown": "elke tick herrekend",
    "last_reserve_margin_breakdown": "elke tick herrekend",
    "battery_module_live": "elke tick uit de sensoren gelezen",
    "battery_module_spread": "elke tick herrekend",
    "advisory_readiness": "elke tick herrekend",
    "decision_log": "loopt mee met de tick",
    "mpc_planned_actions": "elke tick herrekend",
    "mpc_horizon_quarters_used": "elke tick herrekend",
    "monte_carlo_simulations_run": "teller van deze draai",
    "monte_carlo_hours_simulated": "teller van deze draai",
    "digital_twin_trajectory": "elke tick herrekend",
    "digital_twin_hours_simulated": "teller van deze draai",
    "climate_forecast_trajectory": "elke tick herrekend",
    "weather_ensemble_sources_used": "elke tick herrekend",
    "weather_ensemble_readings": "elke tick herrekend",
    "internal_failures": "hoort na een herstart opnieuw te blijken",
    # v2.1.0: de rondeduur meet de HUIDIGE versie op de HUIDIGE machine.
    # Metingen van voor een herstart zeggen daar niets over - een
    # herstart komt meestal juist door een nieuwe versie.
    "tick_duration_history": "meet de huidige versie; begint opnieuw",
    "_tick_part_timings": "meet de huidige versie; begint opnieuw",
    # v2.2.3: wat het inlezen opleverde, blijkt bij elke start opnieuw.
    "energy_history_sources": "blijkt bij elke opstart opnieuw",
    # v3.4.0: versie en bestandsgegevens gelden voor DEZE draaironde.
    "_bestandsinfo": "blijkt bij elke opstart opnieuw",
    # v3.4.0: logregels gelden voor DEZE draaironde; na een herstart is
    # juist wat er daarna gebeurt interessant.
    "eigen_logregels": "geldt voor deze draaironde",
    # v2.0.0: de zelfcontrole rekent elke ronde opnieuw.
    "last_consistency_checks": "blijkt elke ronde opnieuw",
    # v2.2.0: hoe vaak de watchdog moest ingrijpen. Bij een herstart is
    # dat getal niet meer relevant - het gaat om de huidige draai.
    "watchdog_herstelpogingen": "telt per draai, niet over herstarts heen",
    "_laatste_zelfcontrole_sleutel": "blijkt elke ronde opnieuw",
    # v1.58.0: de REDEN blijkt elke tick opnieuw; alleen het beginmoment
    # (`fallback_since`) wordt bewaard, want dat is niet te herleiden.
    "fallback_reasons": "blijkt elke tick opnieuw",
    # v1.79.0: idem - of een terugval wachten of doen is, volgt uit de
    # oorzaak en die wordt elke tick opnieuw vastgesteld.
    "_fallback_soort": "blijkt elke tick opnieuw",
    "notification_suppressed_count": "demping begint na een herstart opnieuw",
    "_unavailable_entities": "blijkt opnieuw uit de sensoren",
    "_sensor_unavailable_since": "blijkt opnieuw uit de sensoren",
    "battery_cooling_state": "blijkt opnieuw uit de sensoren",
    # Halve metingen. Een stuk dat door een herstart een gat heeft, is
    # geen meting meer - beter opnieuw beginnen dan een verminkt getal
    # bewaren.
    "_efficiency_segment_direction": "half meetstuk, hoort te vervallen",
    "_efficiency_segment_ac_kwh": "half meetstuk, hoort te vervallen",
    "_efficiency_cumulative_charged_kwh": "oude methode, vervalt",
    "_efficiency_cumulative_discharged_kwh": "oude methode, vervalt",
    "_water_session_liters_integrated": "halve tapsessie",
    # v1.61.0: de metingen van een lopende cyclus. Een halve cyclus
    # terugzetten zou een verkeerd kWh-getal opleveren; de UITKOMST
    # (`appliance_cycle_kwh`) wordt wel bewaard.
    "_appliance_power_samples": "halve cyclus, hoort te vervallen",
    "_window_energy_kwh": "half meetvenster",
    "_window_duration_hours": "half meetvenster",
    "_window_temp_samples": "half meetvenster",
    "_temp_prediction_pending": "openstaande voorspelling zonder waarde",
    # v1.59.0: de tellers van de lopende dag. Die worden bij middernacht
    # in `veroudering_history` weggeschreven; halverwege bewaren zou een
    # halve dag als hele dag laten meetellen.
    "_veroudering_vandaag": "halve dag, wordt bij middernacht afgesloten",
    # Korte schuivende vensters van enkele minuten.
    "_recent_consumption_readings_kw": "venster van minuten",
    "_balance_power_samples": "venster van minuten",
    # Geen gegevens.
    "_idx": "hulpteller",
    "_listeners": "verbindingen, geen gegevens",
}


def test_every_accumulating_field_is_accounted_for():
    """Elk veld dat toestand opbouwt, moet bewaard worden - of expliciet
    als vluchtig zijn benoemd, mét reden."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    map_ = Path(pkg.__file__).parent
    bron = (map_ / "coordinator.py").read_text()
    kop = bron.index("    def __init__(")
    staart = bron.index("\n    async def ", kop)

    velden = re.findall(
        r"self\.(_?[A-Za-z][A-Za-z_0-9]*)\s*(?::[^=\n]+)?=\s*([^\n]+)",
        bron[kop:staart],
    )
    opbouwend = {
        naam
        for naam, waarde in velden
        if waarde.strip().startswith(("{}", "[]"))
        or re.match(r"^0\.0$|^0$", waarde.strip())
    }

    bewaard = set(
        PERSISTED_PLAIN_FIELDS
        + PERSISTED_INT_FIELDS
        + PERSISTED_DATE_FIELDS
        + PERSISTED_DATETIME_FIELDS
    )
    # De tweede bewaarlaag: sensoren die hun eigen attributen
    # terugzetten bij het opstarten.
    via_sensor = set(
        re.findall(r"coordinator\.([a-z_0-9]+) = ", (map_ / "sensor.py").read_text())
    )

    onbenoemd = opbouwend - bewaard - via_sensor - set(VLUCHTIG_MET_REDEN)

    assert not onbenoemd, (
        "Deze velden bouwen toestand op maar worden niet bewaard en staan "
        f"ook niet als vluchtig benoemd: {sorted(onbenoemd)}"
    )


def test_the_volatile_list_has_no_leftovers():
    """Een veld dat inmiddels wél bewaard wordt, hoort niet meer in de
    vluchtige lijst te staan - anders vertelt die lijst iets dat niet
    meer waar is."""
    bewaard = set(PERSISTED_PLAIN_FIELDS + PERSISTED_INT_FIELDS)

    dubbel = bewaard & set(VLUCHTIG_MET_REDEN)

    assert not dubbel, sorted(dubbel)


def test_user_decisions_are_never_volatile():
    """Wat jij hebt weggeklikt of bevestigd, hoort een herstart te
    overleven. Anders doet wegklikken er niet toe."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    # Bevestigde en afgewezen apparaten worden door hun eigen sensor
    # teruggezet; het dubbelpaar via de opslag. Beide tellen.
    via_sensor = set(
        re.findall(
            r"coordinator\.([a-z_0-9]+) = ",
            (Path(pkg.__file__).parent / "sensor.py").read_text(),
        )
    )
    bewaard = set(PERSISTED_PLAIN_FIELDS) | via_sensor

    for veld in (
        "nilm_confirmed_devices",
        "nilm_rejected_entities",
        "nilm_dismissed_duplicate_pairs",
    ):
        assert veld in bewaard, veld


def test_no_naive_clock_anywhere():
    """v1.48.0: `datetime.now()` volgt de tijdzone van het PROCES, niet
    die van Home Assistant. Draait HA in een container op UTC - wat
    gebruikelijk is - dan scheelt dat 's zomers twee uur.

    Dat viel nergens om: het gaf gewoon een plausibel getal van het
    verkeerde uur. Twee sensoren lazen zo het verbruiksprofiel en de
    PV-bias van het verkeerde uur af, en een NILM-bevestiging kreeg
    mogelijk de verkeerde datum.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    map_ = Path(pkg.__file__).parent
    for bestand in ("coordinator.py", "sensor.py", "diagnostics.py", "config_flow.py"):
        # Commentaarregels tellen niet mee: daar staat juist de uitleg
        # waaróm iets niet zo hoort.
        code = "\n".join(
            regel.split("#")[0]
            for regel in (map_ / bestand).read_text().splitlines()
        )
        assert "datetime.now()" not in code, bestand
        assert "datetime.utcnow()" not in code, bestand
        assert "date.today()" not in code, bestand
