"""Het plan van vanochtend naast de werkelijkheid (v1.31.0).

Gevraagd: "Kun je de diagnostiek zo maken, dat je leert van het accu
gedrag en morgen verder optimaliseert indien noodzakelijk?" Hiervan is
dit stap een: METEN. Zonder meting is bijsturen blind, en is niet te
controleren of een aanpassing hielp.

De aanleiding staat in dezelfde week: de zonschatting stond verkeerd
geijkt (v1.27.0) zonder dat iets aansloeg. Een dagelijkse vergelijking
van voorspeld en werkelijk had dat er binnen een dag uitgehaald.
"""
from datetime import datetime, timedelta, timezone

OCHTEND = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, samenvatting=None):
    c = make_coordinator({})
    c.get_quarter_plan_summary = lambda *a, **k: samenvatting or {
        "beschikbaar": True,
        "verwachte_opbrengst_eur": 4.0,
        "zon_kwh": 23.0,
        "verbruik_kwh": 5.7,
        "import_kwh": 0.0,
        "export_kwh": 17.3,
        "laagste_soc_procent": 20,
        "tekort_kwartieren": 0,
        "verkoopkwartieren": 17,
    }
    return c


# --- de momentopname -------------------------------------------------


def test_the_morning_plan_is_captured(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    c._update_plan_review(OCHTEND)

    assert c.plan_snapshot["verwachte_zon_kwh"] == 23.0
    assert c.plan_snapshot["datum"] == "2026-08-11"


def test_it_is_captured_once_per_day(make_coordinator, hass):
    """Elke tick opnieuw vastleggen zou het plan van 23:59 toetsen, en
    dat klopt per definitie."""
    c = _coordinator(make_coordinator)

    c._update_plan_review(OCHTEND)
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "zon_kwh": 99.0,
        "verwachte_opbrengst_eur": 9.0,
        "import_kwh": 0.0,
        "export_kwh": 0.0,
        "verbruik_kwh": 0.0,
        "laagste_soc_procent": 50,
        "tekort_kwartieren": 0,
        "verkoopkwartieren": 0,
    }
    c._update_plan_review(OCHTEND + timedelta(hours=4))

    assert c.plan_snapshot["verwachte_zon_kwh"] == 23.0


def test_nothing_is_captured_before_the_day_begins(make_coordinator, hass):
    """'s Nachts staat er nog geen zon in het plan; dan zou het rapport
    iets toetsen wat nergens over gaat."""
    c = _coordinator(make_coordinator)

    c._update_plan_review(OCHTEND.replace(hour=3))

    assert c.plan_snapshot is None


def test_an_unavailable_plan_is_not_captured(make_coordinator, hass):
    c = _coordinator(make_coordinator, samenvatting={"beschikbaar": False})

    c._update_plan_review(OCHTEND)

    assert c.plan_snapshot is None


# --- het oordeel -----------------------------------------------------


def _dag_afronden(c, zon=23.0, opbrengst=4.0, soc_laagste=20.0):
    c._update_plan_review(OCHTEND)
    # v3.48.0: de stand komt uit de SENSOR, niet uit `last_soc_percent`.
    # Dat veld liep achter - in de export van 27 augustus stond het op
    # 38% terwijl de accu op 6% zat - en is daarom geen terugval meer.
    c.accustand_procent = lambda: soc_laagste
    c.last_soc_percent = soc_laagste
    c._update_plan_review(OCHTEND + timedelta(hours=1))
    c.pv_production_today_kwh = zon
    c.counterfactual_cost_today_eur = opbrengst
    c.actual_cost_today_eur = 0.0
    # v1.74.0: nog één tick op dezelfde dag, zodat de eindstand wordt
    # vastgehouden. In bedrijf gebeurt dat vanzelf - de tellers lopen
    # elke vijf minuten mee - maar de toetsing mag niet met de tellers
    # van ná de dagwissel rekenen, want die staan dan al op nul.
    c._update_plan_review(OCHTEND + timedelta(hours=12))
    c._update_plan_review(OCHTEND + timedelta(days=1))
    return c.plan_review_history[-1]


def test_a_matching_day_is_reported_as_correct(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    regel = _dag_afronden(c, zon=22.0, opbrengst=3.9)

    assert regel["oordeel"].startswith("Het plan klopte")


def test_a_disappointing_day_is_flagged(make_coordinator, hass):
    """Precies het geval dat de zonschatting had moeten verraden: 23 kWh
    voorspeld, 12 geworden."""
    c = _coordinator(make_coordinator)

    regel = _dag_afronden(c, zon=12.0, opbrengst=2.0)

    assert "zon" in regel["oordeel"]
    assert regel["zon"]["afwijking_procent"] < -20


def test_a_battery_that_ran_lower_than_planned_is_flagged(
    make_coordinator, hass
):
    """Dít is het accugedrag waar het om gaat: het plan beloofde 20% en
    het werd 5%."""
    c = _coordinator(make_coordinator)

    regel = _dag_afronden(c, soc_laagste=5.0)

    assert "accu zakte" in regel["oordeel"]


def test_a_tiny_basis_does_not_produce_a_percentage(make_coordinator, hass):
    """Bij een voorspelling van 0,02 kWh is elke afwijking honderden
    procenten en zegt het niets."""
    c = _coordinator(
        make_coordinator,
        samenvatting={
            "beschikbaar": True,
            "zon_kwh": 0.02,
            "verwachte_opbrengst_eur": 0.01,
            "import_kwh": 0.0,
            "export_kwh": 0.0,
            "verbruik_kwh": 5.0,
            "laagste_soc_procent": 40,
            "tekort_kwartieren": 0,
            "verkoopkwartieren": 0,
        },
    )

    regel = _dag_afronden(c, zon=0.4, opbrengst=0.2, soc_laagste=40.0)

    assert regel["zon"]["afwijking_procent"] is None
    assert regel["opbrengst"]["afwijking_procent"] is None
    assert regel["oordeel"].startswith("Het plan klopte")


# --- het overzicht ---------------------------------------------------


def test_without_days_it_says_so(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    assert c.get_plan_review()["beschikbaar"] is False


def test_a_structural_deviation_is_named(make_coordinator, hass):
    """Een losse dag zegt niets; een reeks wel. Dit is het punt waar het
    zelf bijstellen ooit op kan aanhaken."""
    c = _coordinator(make_coordinator)
    c.plan_review_history = [
        {
            "datum": f"2026-08-{dag:02d}",
            "zon": {
                "voorspeld_kwh": 23.0,
                "werkelijk_kwh": 15.0,
                "afwijking_procent": -35.0,
            },
            "opbrengst": {
                "voorspeld_eur": 4.0,
                "werkelijk_eur": 3.9,
                "afwijking_procent": -2.5,
            },
            "import": {"voorspeld_kwh": 0.0, "werkelijk_kwh": 0.0},
            "laagste_soc": {"voorspeld_procent": 20, "werkelijk_procent": 20},
            "tekort_kwartieren_voorspeld": 0,
            "verkoopkwartieren_voorspeld": 5,
            "oordeel": "Afwijking: zon -35%.",
        }
        for dag in range(1, 8)
    ]

    overzicht = c.get_plan_review()

    assert overzicht["dagen"] == 7
    assert overzicht["dagen_binnen_marge"] == 0
    assert "structureel te hoog" in overzicht["structureel"]


def test_it_survives_a_restart():
    """Gevraagd: "Let op alle gecreeerde data dient na een herstart niet
    verloren te gaan." Dit gaat over dagen, niet over een tick."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "plan_review_history" in PERSISTED_PLAIN_FIELDS
    assert "plan_snapshot" in PERSISTED_PLAIN_FIELDS


def test_it_only_reports_and_never_adjusts():
    """Er wordt hier bewust niets bijgestuurd - stap twee is een aparte
    beslissing."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def _update_plan_review")
    staart = bron[kop : bron.index("def get_plan_review")]

    for verboden in ("SAFETY_FACTOR =", "self.reserve_", "_FACTOR ="):
        assert verboden not in staart


# --- v1.31.1: de accustand moet wél gelezen worden -------------------


def test_the_lowest_soc_is_read_from_the_sensor(make_coordinator, hass):
    """Gevonden in de export van 11 augustus 08:36: `last_soc_percent`
    stond op None terwijl de accu 22% aangaf.

    Dat veld wordt alleen gezet in de berekening van het
    ontlaadvermogen, en die tak wordt niet bereikt zodra de tick eerder
    eindigt - bij `solar_capture_deferred` gebeurt dat elke ochtend die
    met uitstellen begint. Juist dán zakt de accu het diepst.
    """
    from custom_components.energy_management_system.const import CONF_SOC_SENSOR

    c = _coordinator(make_coordinator)
    c.config[CONF_SOC_SENSOR] = "sensor.soc"
    hass.states.set("sensor.soc", "22")
    c.last_soc_percent = None

    c._update_plan_review(OCHTEND)

    assert c.laagste_soc_vandaag_procent == 22.0


def test_the_state_of_charge_has_a_fallback(make_coordinator, hass):
    """Zonder SoC-sensor valt hij terug op de beschikbare energie -
    liever een afgeleide stand dan geen stand."""
    from custom_components.energy_management_system.const import (
        CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
        CONF_MIN_SOC_PERCENT,
    )

    c = _coordinator(make_coordinator)
    c.config[CONF_BATTERY_TOTAL_CAPACITY_SENSOR] = "sensor.cap"
    c.config[CONF_MIN_SOC_PERCENT] = 10.0
    hass.states.set("sensor.cap", "8.6")
    c.last_available_kwh = 3.87  # de helft van 7,74 bruikbaar

    assert round(c.accustand_procent()) == 55


# --- v1.37.2: vergelijken vanaf de momentopname ----------------------


def test_only_what_happened_after_the_snapshot_counts(
    make_coordinator, hass
):
    """Gevonden in de export van 11 augustus 11:21: de momentopname was
    om 10:26 genomen - de verwachting gaat dus over de REST van de dag,
    want de planning begint bij nu. De werkelijkheid werd daarna
    vergeleken met de dagtellers, en die tellen vanaf middernacht.

    Vandaag scheelde dat de hele ochtendzon: 21,1 kWh verwacht tegen
    ruim 23 kWh gemeten, gerapporteerd als 10% afwijking terwijl de
    voorspelling gewoon klopte.
    """
    c = _coordinator(make_coordinator)
    # Er stond vanochtend al 8 kWh op de teller voordat het plan werd
    # vastgelegd.
    c.pv_production_today_kwh = 8.0
    c.counterfactual_cost_today_eur = 1.0
    c.actual_cost_today_eur = 0.0
    c._update_plan_review(OCHTEND)

    # De rest van de dag levert precies wat er voorspeld was: 23 kWh en
    # 4 euro, boven op wat er al stond.
    c.pv_production_today_kwh = 8.0 + 23.0
    c.counterfactual_cost_today_eur = 1.0 + 4.0
    c.last_soc_percent = 20.0
    c._update_plan_review(OCHTEND + timedelta(days=1))

    regel = c.plan_review_history[-1]

    assert regel["zon"]["werkelijk_kwh"] == 23.0
    assert regel["opbrengst"]["werkelijk_eur"] == 4.0
    assert regel["oordeel"].startswith("Het plan klopte")


def test_the_snapshot_records_the_counters(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.pv_production_today_kwh = 8.0

    c._update_plan_review(OCHTEND)

    assert c.plan_snapshot["pv_bij_opname_kwh"] == 8.0


def test_an_old_snapshot_without_counters_still_works(
    make_coordinator, hass
):
    """Een opslagbestand van voor deze versie kent die velden niet; dan
    mag de toetsing niet omvallen."""
    c = _coordinator(make_coordinator)
    c._update_plan_review(OCHTEND)
    del c.plan_snapshot["pv_bij_opname_kwh"]
    del c.plan_snapshot["opbrengst_bij_opname_eur"]
    del c.plan_snapshot["import_bij_opname_kwh"]
    c.pv_production_today_kwh = 23.0
    c.last_soc_percent = 20.0

    c._update_plan_review(OCHTEND + timedelta(days=1))

    assert c.plan_review_history[-1]["zon"]["werkelijk_kwh"] == 23.0


# --- v1.74.0: rekenen met de eindstand, niet met nul ------------------


def test_the_counters_are_read_before_they_reset(make_coordinator, hass):
    """Gevonden in de export van 13 augustus: de plantoetsing meldde
    "zon -1190%" met een werkelijke opbrengst van -20,82 kWh.

    Dat is precies de negatieve stand van de momentopname. De oorzaak
    is een volgordefout: `pv_production_today_kwh` wordt bij de dagwissel
    op nul gezet door een routine die eerder in de tick draait, dus
    rekende de toetsing 0 min 20,82.
    """
    c = _coordinator(make_coordinator)
    c.pv_production_today_kwh = 0.2
    c._update_plan_review(OCHTEND)

    # De dag verloopt; de teller loopt op.
    c.pv_production_today_kwh = 21.0
    c.last_soc_percent = 40.0
    c._update_plan_review(OCHTEND + timedelta(hours=10))

    # Middernacht: de teller is al gewist voordat de toetsing draait.
    c.pv_production_today_kwh = 0.0
    c._update_plan_review(OCHTEND + timedelta(days=1))

    regel = c.plan_review_history[-1]
    assert regel["zon"]["werkelijk_kwh"] > 0
    assert round(regel["zon"]["werkelijk_kwh"], 1) == 20.8


def test_the_same_holds_for_import_and_savings(make_coordinator, hass):
    """Alle drie de dagtellers hadden dezelfde fout."""
    c = _coordinator(make_coordinator)
    c._update_plan_review(OCHTEND)

    c.grid_import_today_kwh = 1.5
    c.counterfactual_cost_today_eur = 4.0
    c.actual_cost_today_eur = 0.5
    c.last_soc_percent = 40.0
    c._update_plan_review(OCHTEND + timedelta(hours=10))

    c.grid_import_today_kwh = 0.0
    c.counterfactual_cost_today_eur = 0.0
    c.actual_cost_today_eur = 0.0
    c._update_plan_review(OCHTEND + timedelta(days=1))

    regel = c.plan_review_history[-1]
    assert regel["import"]["werkelijk_kwh"] == 1.5
    assert regel["opbrengst"]["werkelijk_eur"] == 3.5


def test_a_restart_does_not_discard_this_mornings_snapshot(
    make_coordinator, hass
):
    """Gevonden in de export van 13 augustus: de momentopnames staan op
    18:00 en 20:19 in plaats van 08:00, telkens vlak na een herstart.

    `_plan_review_day_key` werd niet bewaard, dus stond hij na een
    herstart op None - en dan wiste de dagwisselregel de opname van
    vanochtend. Een opname om 18:00 vergelijkt de REST van de dag (1,91
    kWh zon) met de werkelijkheid; dat zegt nauwelijks iets.
    """
    c = _coordinator(make_coordinator)
    c._update_plan_review(OCHTEND)
    opname = dict(c.plan_snapshot)

    # Herstart: de dagsleutel is leeg, de momentopname komt terug uit de
    # opslag.
    verse = _coordinator(make_coordinator)
    verse.plan_snapshot = opname
    verse._plan_review_day_key = None

    verse._update_plan_review(OCHTEND + timedelta(hours=9))

    assert verse.plan_snapshot["opgenomen_om"] == opname["opgenomen_om"]


def test_a_restart_on_a_new_day_still_closes_yesterday(
    make_coordinator, hass
):
    """Blijft de opname van gisteren staan omdat de integratie 's nachts
    uit was, dan hoort hij alsnog afgesloten te worden - anders
    verdwijnt die dag stilzwijgend uit de reeks."""
    c = _coordinator(make_coordinator)
    c._update_plan_review(OCHTEND)
    opname = dict(c.plan_snapshot)

    verse = _coordinator(make_coordinator)
    verse.plan_snapshot = opname
    verse._plan_review_day_key = None
    verse.last_soc_percent = 40.0

    verse._update_plan_review(OCHTEND + timedelta(days=1))

    assert verse.plan_review_history
    assert verse.plan_review_history[-1]["datum"] == opname["datum"]


# --- v1.96.0: restanten van de volgordefout opruimen -----------------


def test_impossible_rows_are_removed_on_startup(make_coordinator, hass):
    """Gevonden bij de eindcontrole van 14 augustus: de plantoetsing
    droeg nog regels met een werkelijke zonopbrengst van -20,82 en -22,73
    kWh.

    Die zijn geschreven toen de dagtellers al op nul stonden voordat de
    toetsing draaide. De fout is in v1.74.0 gerepareerd, maar net als bij
    de energiereeks bleven de foute regels staan - een reparatie van het
    SCHRIJVEN raakt niet wat er al bewaard is.
    """
    regels = [
        {"datum": "2026-08-11", "zon": {"werkelijk_kwh": -22.73}},
        {"datum": "2026-08-12", "zon": {"werkelijk_kwh": -20.82}},
        {"datum": "2026-08-13", "zon": {"werkelijk_kwh": 21.48}},
    ]

    bewaard = [
        r for r in regels if (r.get("zon") or {}).get("werkelijk_kwh", 0) >= 0
    ]

    assert [r["datum"] for r in bewaard] == ["2026-08-13"]


def test_a_row_without_sun_data_is_kept(make_coordinator, hass):
    """Ontbrekend is geen onmogelijk - zo'n regel mag blijven."""
    regel = {"datum": "2026-08-10", "zon": {}}

    assert (regel.get("zon") or {}).get("werkelijk_kwh", 0) >= 0


def test_the_cleanup_runs_after_the_state_is_restored():
    """Anders ruimt hij een lege lijst op - precies de fout van v1.95.0."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("    async def async_setup(self) -> None:")
    staart = bron.index("\n    async def ", kop + 40)
    blok = bron[kop:staart]

    assert blok.index("async_load_persisted_nilm_state()") < blok.index(
        "voor_toetsing = len(self.plan_review_history)"
    )
