"""De proefstand: rekent mee, stuurt niets (v1.38.0).

Gevraagd: "Misschien eerst integreren totdat ze daadwerkelijk gaan
meebewegen? Dus een extra onzichtbaar tabblad waar waardes zichtbaar
zijn hoe betrouwbaar etc."

Precies de goede volgorde, en dezelfde die bij de plantoetsing werkte:
eerst meten, dan pas sturen. Vijf kandidaten laten zien wat ze zouden
zeggen; wie zich bewijst gaat mee in de besluitvorming - één tegelijk,
zodat bij een afwijking te zien is welke het deed.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_BATTERY_MODULE_TEMPERATURE_SENSORS,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_MIN_SOC_PERCENT,
    PRICE_SCALE_FACTOR,
    RELIABILITY_INSUFFICIENT,
)

NU = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator(
        {
            CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.cap",
            CONF_MIN_SOC_PERCENT: 10.0,
            CONF_BATTERY_MODULE_TEMPERATURE_SENSORS: [
                "sensor.m1",
                "sensor.m2",
                "sensor.m3",
            ],
        }
    )
    hass.states.set("sensor.cap", "8.6")
    return c


# --- het uitgangspunt ------------------------------------------------


def test_nothing_on_the_test_bench_steers_anything():
    """Het hele punt: deze kandidaten rekenen mee en sturen niets. Een
    test die dat vasthoudt is meer waard dan een belofte in de tekst.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def _update_proefstand")
    staart = bron[kop : bron.index("def get_wear_cost_overview")]

    # Alleen lezen en in eigen reeksen wegschrijven; geen modus, geen
    # vermogen, geen drempel.
    for verboden in (
        "_async_apply_manual",
        "last_reason =",
        "self.last_charge_power",
        "presence_state =",
    ):
        assert verboden not in staart, verboden


def test_every_candidate_reports_its_own_reliability(
    make_coordinator, hass
):
    """Een getal zonder te zeggen hoe hard het is, is erger dan geen
    getal."""
    c = _coordinator(make_coordinator, hass)

    kandidaten = c.get_proefstand()["kandidaten"]

    # v2.6.0: plus "Vasthouden voor morgen".
    # v2.9.0: plus het regressiewoud.
    # v3.10.0: plus "Verder vooruitkijken bij de reserve".
    assert len(kandidaten) == 9
    for kandidaat in kandidaten:
        assert kandidaat["naam"]
        assert kandidaat["status"]
        assert kandidaat["betrouwbaarheid"]


def test_a_fresh_install_claims_nothing(make_coordinator, hass):
    """Zonder gegevens hoort er "nog geen uitspraak" te staan, geen
    getal dat toevallig uit één waarneming rolt."""
    c = _coordinator(make_coordinator, hass)

    kandidaten = c.get_proefstand()["kandidaten"]
    onvoldoende = [
        k for k in kandidaten if k["status"] == RELIABILITY_INSUFFICIENT
    ]

    assert len(onvoldoende) >= 3


# --- 1. slijtage -----------------------------------------------------


def test_the_wear_cost_uses_the_real_prices(make_coordinator, hass):
    """3 x 729 euro over 7,74 kWh bruikbaar en 6000 cycli."""
    c = _coordinator(make_coordinator, hass)

    overzicht = c.get_wear_cost_overview()

    assert overzicht["aanschafwaarde_eur"] == 2187.0
    assert overzicht["bruikbaar_kwh"] == 7.74
    # v1.76.0: op de NOMINALE capaciteit, net als de cyclustelling. De
    # 6000 cycli van de fabrikant zijn daarop gespecificeerd; rekenen met
    # de bruikbare 7,74 maakte de slijtage kunstmatig hoger.
    #
    # 2187 / (8,6 x 6000) = 4,2 ct
    assert overzicht["nominale_capaciteit_kwh"] == 8.6
    assert 4.1 <= overzicht["slijtage_ct_per_kwh"] <= 4.3


def test_the_wear_cost_does_not_decide_between_house_and_grid():
    """Waar ik me eerst in vergiste: ontladen naar het huis of naar het
    net is dezelfde slijtage. Dit getal kiest daar dus niets tussen, en
    dat hoort in de toelichting te staan."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_wear_cost_overview")

    # v1.76.0: van 4000 naar 6000 tekens - de toelichting is gegroeid en
    # zoeken op een vast aantal tekens breekt zodra dat gebeurt.
    assert "dezelfde slijtage" in bron[kop : kop + 6000]


# --- 3. dagtype ------------------------------------------------------


def test_the_daytype_profile_is_collected_separately(
    make_coordinator, hass
):
    c = _coordinator(make_coordinator, hass)
    c._current_tracked_hour = 14
    c._hour_energy_kwh = 0.4
    c._hour_duration_hours = 1.0

    # 15 augustus 2026 is een zaterdag.
    c._finalize_hourly_bucket(datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc))

    assert "weekend-14" in c.daytype_consumption_profile


def test_a_small_difference_is_not_worth_splitting(make_coordinator, hass):
    """Onder de drempel verlies je aan waarnemingen wat je aan scherpte
    wint."""
    c = _coordinator(make_coordinator, hass)
    for uur in range(24):
        c.daytype_consumption_profile[f"werkdag-{uur}"] = [0.30, 0.31, 0.30]
        c.daytype_consumption_profile[f"weekend-{uur}"] = [0.31, 0.32, 0.31]

    kandidaat = c.get_proefstand()["kandidaten"][2]

    assert kandidaat["status"] == "indicatief"


def test_a_real_difference_is_called_reliable(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    for uur in range(24):
        c.daytype_consumption_profile[f"werkdag-{uur}"] = [0.30, 0.30, 0.30]
        c.daytype_consumption_profile[f"weekend-{uur}"] = [0.45, 0.46, 0.44]

    kandidaat = c.get_proefstand()["kandidaten"][2]

    assert kandidaat["status"] == "betrouwbaar"
    assert "+" in kandidaat["waarde"]


# --- 4. capaciteit ---------------------------------------------------


def test_the_capacity_is_recorded_once_a_day(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    c._update_proefstand(NU)
    c._update_proefstand(NU + timedelta(hours=3))

    assert len(c.capacity_trend_history) == 1
    assert c.capacity_trend_history[0]["capaciteit_kwh"] == 8.6


def test_a_short_capacity_series_says_nothing(make_coordinator, hass):
    """Capaciteitsverlies is enkele procenten per jáár."""
    c = _coordinator(make_coordinator, hass)
    c.capacity_trend_history = [
        {"datum": "2026-08-01", "capaciteit_kwh": 8.6, "doorzet_kwh": 0.0}
    ]

    assert c.get_proefstand()["kandidaten"][3]["status"] == RELIABILITY_INSUFFICIENT


# --- 5. prijsvorm ----------------------------------------------------


def test_the_price_shape_stores_ratios_not_prices(make_coordinator, hass):
    """Een dag van 40 ct en een van 12 ct hebben dezelfde vorm; alleen
    die vorm is bruikbaar om verder vooruit te kijken."""
    c = _coordinator(make_coordinator, hass)
    entries = []
    for i in range(96):
        start = NU.replace(hour=0, minute=0) + timedelta(minutes=15 * i)
        prijs = (0.10 if start.hour < 12 else 0.30) * PRICE_SCALE_FACTOR
        entries.append((start, start + timedelta(minutes=15), prijs))
    c._get_forecast_entries = lambda *a, **k: entries

    c._update_proefstand(NU)

    # Gemiddeld 20 ct: de ochtend is 0,5x, de middag 1,5x.
    assert c.price_shape_history["3"] == [0.5]
    assert c.price_shape_history["15"] == [1.5]


def test_a_partial_day_is_not_recorded(make_coordinator, hass):
    """Een halve dag geeft een vertekende vorm."""
    c = _coordinator(make_coordinator, hass)
    entries = [
        (
            NU.replace(hour=0, minute=0) + timedelta(minutes=15 * i),
            NU.replace(hour=0, minute=0) + timedelta(minutes=15 * (i + 1)),
            0.20 * PRICE_SCALE_FACTOR,
        )
        for i in range(40)
    ]
    c._get_forecast_entries = lambda *a, **k: entries

    c._update_proefstand(NU)

    assert c.price_shape_history == {}


# --- bewaren ---------------------------------------------------------


def test_the_test_bench_survives_a_restart():
    """Kandidaten die zich moeten bewijzen, kunnen dat niet als ze elke
    herstart opnieuw beginnen."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    for veld in (
        "daytype_consumption_profile",
        "capacity_trend_history",
        "price_shape_history",
    ):
        assert veld in PERSISTED_PLAIN_FIELDS, veld


# --- v1.39.0: wat zou het hebben opgeleverd? -------------------------


def test_every_candidate_says_what_it_would_have_yielded(
    make_coordinator, hass
):
    """Gevraagd: "Dan dus ook aangeven wat het opgeleverd zou hebben als
    ze wel zouden sturen."

    Zonder bedrag is "betrouwbaar" geen argument om iets aan te zetten.
    """
    c = _coordinator(make_coordinator, hass)

    for kandidaat in c.get_proefstand()["kandidaten"]:
        opbrengst = kandidaat.get("zou_hebben_opgeleverd")
        assert opbrengst is not None, kandidaat["naam"]
        if opbrengst.get("te_becijferen"):
            assert "bedrag_per_dag_eur" in opbrengst
        else:
            assert opbrengst["reden"]


def test_what_cannot_be_priced_says_so(make_coordinator, hass):
    """Een verzonnen bedrag is erger dan geen bedrag. De accugezondheid
    levert niets op - die voorkomt een verkeerde aanname."""
    c = _coordinator(make_coordinator, hass)
    c.capacity_trend_history = [
        {"datum": f"2026-07-{dag:02d}", "capaciteit_kwh": 8.6, "doorzet_kwh": dag * 5}
        for dag in range(1, 31)
    ]

    kandidaat = c.get_proefstand()["kandidaten"][3]

    assert kandidaat["zou_hebben_opgeleverd"]["te_becijferen"] is False
    assert "voorkomt een verkeerde aanname" in (
        kandidaat["zou_hebben_opgeleverd"]["reden"]
    )


def test_the_wear_is_booked_per_day(make_coordinator, hass):
    """4,7 ct maal wat er die dag doorheen ging."""
    c = _coordinator(make_coordinator, hass)
    c._update_proefstand(NU)
    c.battery_cumulative_discharged_kwh = 6.0

    c._update_proefstand(NU + timedelta(days=1))

    boeking = c.proefstand_ledger[-1]
    assert boeking["doorzet_kwh"] == 6.0
    # 6 kWh x 4,2 ct = 25 cent, als kostenpost dus negatief.
    assert -0.27 <= boeking["slijtage_eur"] <= -0.24


def test_the_wear_amount_reaches_the_candidate(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c._update_proefstand(NU)
    c.battery_cumulative_discharged_kwh = 6.0
    c._update_proefstand(NU + timedelta(days=1))

    opbrengst = c.get_proefstand()["kandidaten"][0]["zou_hebben_opgeleverd"]

    assert opbrengst["te_becijferen"] is True
    assert opbrengst["bedrag_per_jaar_eur"] < -80


def test_the_ledger_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "proefstand_ledger" in PERSISTED_PLAIN_FIELDS


# --- v1.45.0: niet weken wachten op wat er al is ---------------------


def test_the_daytype_profile_is_filled_from_history():
    """Gevraagd: "Nog geen data verzameld?"

    Klopt, en dat was onnodig traag. Het algemene uurprofiel wordt bij
    de installatie in één keer uit de recorder gevuld; het profiel per
    dagtype begon leeg en had daardoor weken nodig. Diezelfde
    geschiedenis draagt de dag al - elke emmer is een (datum, uur)-paar
    - alleen werd dat weggegooid.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("async def async_bootstrap_night_consumption_from_history")
    staart = bron[kop : bron.index("async def async_unload")]

    assert "daytype_consumption_profile" in staart
    assert "day.weekday() >= 5" in staart


def test_the_bootstrap_only_runs_when_empty():
    """Een bestaand profiel mag niet worden overschreven door een
    momentopname uit de recorder."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "need_daytype_bootstrap = not self.daytype_consumption_profile" in bron


def test_the_progress_says_which_side_lags(make_coordinator, hass):
    """"0 van de 24 uren" laat in het midden of er niets binnenkomt of
    dat één van de twee dagtypen achterloopt."""
    c = _coordinator(make_coordinator, hass)
    for uur in range(24):
        c.daytype_consumption_profile[f"werkdag-{uur}"] = [0.3, 0.3, 0.3, 0.3]
        c.daytype_consumption_profile[f"weekend-{uur}"] = [0.4, 0.4]

    tekst = c.get_proefstand()["kandidaten"][2]["betrouwbaarheid"]

    assert "werkdag" in tekst.lower()
    assert "weekend loopt achter" in tekst


# --- v3.0.0: meting en winst zijn twee dingen ------------------------


def test_a_reliable_measurement_is_not_yet_ready(make_coordinator, hass):
    """Gevraagd: "Zijn er al zaken uit (meetkwaliteit) die nu
    betrouwbaar genoeg zijn en eventueel al kunnen meedoen?"

    Die vraag was moeilijker te beantwoorden dan nodig. "Betrouwbaar"
    sloeg op twee dingen: de prijsvorm stond op betrouwbaar omdat de VORM
    stabiel is - terwijl er letterlijk bij stond dat de winst pas te
    becijferen valt zodra de voorspelde vorm naast de werkelijke prijzen
    kan.
    """
    c = make_coordinator({})

    uitkomst = c._met_gereedheid(
        {
            "naam": "Prijsvorm",
            "status": "betrouwbaar",
            "zou_hebben_opgeleverd": {"te_becijferen": False},
        }
    )

    assert uitkomst["meting_betrouwbaar"] is True
    assert uitkomst["winst_becijferd"] is False
    assert uitkomst["gereedheid"] == "winst onbekend"


def test_both_together_make_it_ready(make_coordinator, hass):
    c = make_coordinator({})

    uitkomst = c._met_gereedheid(
        {
            "naam": "Iets",
            "status": "betrouwbaar",
            "zou_hebben_opgeleverd": {"te_becijferen": True},
        }
    )

    assert uitkomst["gereedheid"] == "klaar om mee te doen"
    assert "één tegelijk" in uitkomst["gereedheid_uitleg"]


def test_an_unreliable_measurement_says_so(make_coordinator, hass):
    c = make_coordinator({})

    uitkomst = c._met_gereedheid(
        {
            "naam": "Iets",
            "status": "onvoldoende_data",
            "zou_hebben_opgeleverd": {"te_becijferen": True},
        }
    )

    assert uitkomst["gereedheid"] == "meet nog"


def test_every_candidate_carries_a_readiness(make_coordinator, hass):
    c = make_coordinator({})

    for k in c.get_proefstand()["kandidaten"]:
        assert k["gereedheid"] in (
            "meet nog",
            "winst onbekend",
            "klaar om mee te doen",
        ), k["naam"]


def test_the_summary_answers_the_question_at_a_glance(
    make_coordinator, hass
):
    """Zodat "is er al iets rijp?" met één blik te beantwoorden is, in
    plaats van door zeven kandidaten te lezen."""
    c = make_coordinator({})

    s = c.get_proefstand()["samenvatting"]

    assert s["aantal"] == 9
    assert isinstance(s["klaar"], list)
    assert s["oordeel"]
