"""Planning van vaatwasser en wasmachine in gewone taal (v5.139.0).

Gevraagd 27-10: "Kunnen we iets bouwen dat we uitgestelde start en eindtijd
helderder in het EMS krijgen? Voor o.a. wasmachine en vaatwasser."

Gemeten 27-10 10:31: wasmachine draaide (Katoen), Home Connect eindtijd
12:29 en voortgang 33%, de eigen schatting zei 10%. De geleerde duur was
150 min over alle programma's, met fragmenten van 23 en 96 min ertussen.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import witgoedplanning as wp
from custom_components.energy_management_system.const import (
    CONF_DISHWASHER_START_IN,
    CONF_WASHING_MACHINE_END_AT,
)

NU = datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc)


def _invoer(**kw):
    basis = dict(naam="wasmachine", nu=NU)
    basis.update(kw)
    return wp.Invoer(**basis)


def _vlakke_prijzen(prijs=0.25, uren=24, duur_blok=None):
    uit = []
    t = NU.replace(minute=0)
    for i in range(uren * 4):
        b = t + timedelta(minutes=15 * i)
        p = duur_blok(b) if duur_blok else prijs
        uit.append((b, b + timedelta(minutes=15), p))
    return uit


# --- programma's -----------------------------------------------------


def test_program_names_are_readable():
    assert wp.programma_sleutel("laundry_care_washer_program_cotton") == "cotton"
    assert wp.programma_naam("cotton") == "Katoen"
    assert wp.programma_naam(wp.programma_sleutel("dishcare_dishwasher_program_quick_65")) == "Snel 65"
    assert wp.programma_sleutel("unavailable") is None
    assert wp.programma_naam("iets_nieuws") == "Iets nieuws"


def test_learning_per_program_keeps_the_last_ones():
    reeksen = {}
    for d in range(15):
        reeksen = wp.leer_programma(reeksen, "cotton", 140 + d)
    assert len(reeksen["cotton"]) == wp.PROGRAMMA_HISTORIE
    assert wp.geleerd_per_programma(reeksen, "cotton")[1] == wp.PROGRAMMA_HISTORIE
    assert wp.geleerd_per_programma(reeksen, "quick_65") is None


def test_program_duration_beats_the_device_average():
    """Dit is het hele punt voor de reserve: een snel programma kreeg de
    duur van katoen, en daarmee een begin dat ruim een uur te vroeg lag."""
    eind = NU + timedelta(hours=5)
    uit = wp.bepaal(_invoer(
        hc_toestand="delayedstart",
        hc_eindtijd=eind,
        programma="laundry_care_washer_program_super_153045_super_1530",
        duur_per_programma={"super_153045_super_1530": [32, 34, 33]},
        duur_apparaat=150,
    ))
    assert uit["status"] == "gepland"
    assert uit["duur_bron"] == "programma"
    assert datetime.fromisoformat(uit["start"]) == eind - timedelta(minutes=33)
    assert uit["start_bron"] == "geleerd"
    assert uit["eind_bron"] == "home_connect"


# --- gepland ---------------------------------------------------------


def test_dishwasher_gets_an_end_time():
    """De vaatwasser gaf alleen een begin; nu ook wanneer hij klaar is."""
    uit = wp.bepaal(_invoer(
        naam="vaatwasser",
        hc_toestand="delayedstart",
        hc_start_over_s=3 * 3600,
        duur_apparaat=74,
    ))
    assert uit["status"] == "gepland"
    assert datetime.fromisoformat(uit["start"]) == NU + timedelta(hours=3)
    assert datetime.fromisoformat(uit["eind"]) == NU + timedelta(hours=3, minutes=74)
    assert uit["start_bron"] == "home_connect"
    assert "±" in uit["tekst"]  # afgeleide eindtijd
    assert uit["in_reserve"] is True


def test_an_end_time_before_the_start_is_not_the_end():
    """Bij een uitgestelde start geeft Home Connect soms de eindtijd alsof hij
    nu zou starten; die ligt vóór het begin."""
    uit = wp.bepaal(_invoer(
        naam="vaatwasser",
        hc_toestand="delayedstart",
        hc_start_over_s=3 * 3600,
        hc_eindtijd=NU + timedelta(minutes=70),
        duur_apparaat=74,
    ))
    assert uit["eind_bron"] == "geleerd"


def test_a_leftover_option_is_not_a_plan():
    """Een eindtijd of starttijd bij een gekozen programma, terwijl Home
    Connect "ready" zegt, is geen planning - en telt niet in de reserve."""
    uit = wp.bepaal(_invoer(
        hc_toestand="ready",
        hc_eindtijd=NU + timedelta(hours=3),
        duur_apparaat=150,
    ))
    assert uit["status"] == "niets"
    assert uit["in_reserve"] is False


def test_without_home_connect_state_the_old_rule_holds():
    """Valt de toestand weg (cloudlimiet), dan geldt v1.70.0: eindtijd min
    geleerde duur, en geen planning als dat begin al voorbij is."""
    plan = wp.bepaal(_invoer(hc_toestand="unavailable", hc_eindtijd=NU + timedelta(hours=4), duur_apparaat=150))
    assert plan["status"] == "gepland"
    assert plan["in_reserve"] is True
    voorbij = wp.bepaal(_invoer(hc_toestand=None, hc_eindtijd=NU + timedelta(hours=1), duur_apparaat=150))
    assert voorbij["status"] == "niets"


def test_delayed_without_times_says_so():
    uit = wp.bepaal(_invoer(hc_toestand="delayedstart"))
    assert uit["status"] == "gepland"
    assert "nog niet bekend" in uit["tekst"]
    assert uit["in_reserve"] is False


# --- draait / klaar --------------------------------------------------


def test_running_uses_home_connect_progress_and_end():
    """Gemeten 27-10: eigen schatting 10%, Home Connect 33%."""
    uit = wp.bepaal(_invoer(
        hc_toestand="run",
        hc_eindtijd=NU + timedelta(hours=2),
        hc_voortgang=33,
        programma="laundry_care_washer_program_cotton",
        ems_toestand="actief",
        ems_gestart=NU - timedelta(minutes=15),
        duur_apparaat=150,
    ))
    assert uit["status"] == "draait"
    assert uit["voortgang_procent"] == 33
    assert uit["voortgang_bron"] == "home_connect"
    assert uit["eind_bron"] == "home_connect"
    assert uit["tekst"].startswith("Draait (Katoen)")
    assert "33%" in uit["tekst"]
    assert uit["in_reserve"] is False  # zit al in de live meting


def test_running_without_home_connect_uses_own_estimate():
    uit = wp.bepaal(_invoer(ems_toestand="actief", ems_gestart=NU - timedelta(minutes=75), duur_apparaat=150))
    assert uit["voortgang_procent"] == 50
    assert uit["voortgang_bron"] == "geleerd"
    assert "±" in uit["tekst"]


def test_done_is_shown_for_a_while():
    klaar = wp.bepaal(_invoer(ems_toestand="klaar", ems_klaar_sinds=NU - timedelta(hours=1)))
    assert klaar["status"] == "klaar"
    assert klaar["tekst"].startswith("Klaar sinds")
    oud = wp.bepaal(_invoer(ems_toestand="klaar", ems_klaar_sinds=NU - timedelta(days=2)))
    assert oud["tekst"] == "Niets gepland"


# --- prijs -----------------------------------------------------------


def test_price_verdict_finds_a_cheaper_start_before_the_end():
    def prijs(b):
        return 0.10 if NU + timedelta(hours=1) <= b < NU + timedelta(hours=3) else 0.30

    uit = wp.bepaal(_invoer(
        naam="vaatwasser",
        hc_toestand="delayedstart",
        hc_start_over_s=4 * 3600,
        duur_apparaat=60,
        kwh_apparaat=1.0,
        prijzen=_vlakke_prijzen(duur_blok=prijs),
    ))
    p = uit["prijs"]
    assert p["te_becijferen"]
    assert p["kosten_eur"] == 0.30
    assert p["beste_kosten_eur"] == 0.10
    assert p["besparing_eur"] == 0.20
    assert "zou € 0,10 zijn" in uit["tekst"]


def test_price_verdict_is_quiet_when_already_cheapest():
    uit = wp.bepaal(_invoer(
        naam="vaatwasser",
        hc_toestand="delayedstart",
        hc_start_over_s=2 * 3600,
        duur_apparaat=60,
        kwh_apparaat=1.0,
        prijzen=_vlakke_prijzen(0.20),
    ))
    assert uit["prijs"]["beste_start"] is None
    assert "goedkoopste moment" in uit["tekst"]


def test_cost_needs_full_price_coverage():
    assert wp.kosten_bij_start(_vlakke_prijzen(0.2, uren=1), NU + timedelta(minutes=30), 120, 1.0) is None


# --- coordinator ----------------------------------------------------


def _coordinator(make_coordinator, **config):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    return make_coordinator(config)


def test_coordinator_uses_home_connect_state(make_coordinator, hass):
    c = _coordinator(make_coordinator, **{CONF_WASHING_MACHINE_END_AT: "sensor.einde"})
    c.__dict__["_bedrijfstoestand_entiteit"] = {"wasmachine": "sensor.wasmachine_status"}
    c.__dict__["_hc_zusters"] = {}
    hass.states.set("sensor.einde", (NU + timedelta(hours=6)).isoformat())
    c.washing_machine_cycle_duration_history = [150, 152, 148]

    hass.states.set("sensor.wasmachine_status", "ready")
    assert c.get_planned_appliance_load(NU)["beschikbaar"] is False

    hass.states.set("sensor.wasmachine_status", "delayedstart")
    plan = c.get_planned_appliance_load(NU)
    assert plan["beschikbaar"] is True
    regel = plan["apparaten"][0]
    assert regel["eindtijd_kort"]
    assert "geleerde cyclusduur" in regel["let_op"]
    tekst = c.get_witgoed_planning("wasmachine", NU)["tekst"]
    assert tekst.startswith("Start ±")


def test_coordinator_learns_per_program(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.__dict__["_hc_zusters"] = {("wasmachine", wp.HC_ACTIEF_PROGRAMMA): "select.prog"}
    hass.states.set("select.prog", "laundry_care_washer_program_cotton")
    c._noteer_lopend_programma("wasmachine")
    hass.states.set("select.prog", "unknown")  # bij klaar is hij leeg
    c._leer_per_programma("wasmachine", 152.0, 0.9)

    assert c.witgoed_duur_per_programma["wasmachine"]["cotton"] == [152.0]
    assert c.witgoed_kwh_per_programma["wasmachine"]["cotton"] == [0.9]

    # een fragment leert geen duur
    c._noteer_lopend_programma("wasmachine")
    c._witgoed_lopend_programma["wasmachine"] = "laundry_care_washer_program_cotton"
    c._leer_per_programma("wasmachine", 6.0, None)
    assert c.witgoed_duur_per_programma["wasmachine"]["cotton"] == [152.0]


def test_dishwasher_plan_has_start_and_end(make_coordinator, hass):
    c = _coordinator(make_coordinator, **{CONF_DISHWASHER_START_IN: "number.start_in"})
    hass.states.set("number.start_in", str(3 * 3600))
    c.dishwasher_cycle_duration_history = [74]
    planning = c.get_witgoed_planning("vaatwasser", NU)
    assert planning["status"] == "gepland"
    assert planning["start"] and planning["eind"]
    regel = c.get_planned_appliance_load(NU)["apparaten"][0]
    assert regel["start_kort"] and regel["eindtijd_kort"]


def test_program_data_is_persisted():
    from custom_components.energy_management_system.const import (
        PERSISTED_FIELDS,
    )

    assert "witgoed_duur_per_programma" in PERSISTED_FIELDS
    assert "witgoed_kwh_per_programma" in PERSISTED_FIELDS
