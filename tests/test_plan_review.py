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
    c.last_soc_percent = soc_laagste
    c._update_plan_review(OCHTEND + timedelta(hours=1))
    c.pv_production_today_kwh = zon
    c.counterfactual_cost_today_eur = opbrengst
    c.actual_cost_today_eur = 0.0
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
