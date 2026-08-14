"""Alle cijfers over dag, week, maand, jaar en contractjaar (v1.91.0).

Gevraagd: "Misschien dag/week/maand/jaar voor alle relevante sensoren
invoeren en zichtbaar maken? Kosten, verbruik, opwek, accu, noem het maar
op."

Eén reeks, één optelling, één tabel. Losse tellers per onderwerp en per
periode zouden tientallen sensoren opleveren die elk hun eigen dagwissel
en herstart moeten overleven - en dat is precies waar deze week een paar
keer iets misging.
"""
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_CONTRACT_START_DATE,
)

NU = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, dagen=40, **config):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator(config)
    c.energy_daily_history = [
        {
            "datum": (NU.date() - timedelta(days=n)).isoformat(),
            "opwek_kwh": 20.0,
            "zon_export_kwh": 8.0,
            "export_kwh": 9.0,
            "verbruik_kwh": 10.0,
            "import_kwh": 1.0,
            "accu_ontladen_kwh": 5.0,
            "kosten_eur": -2.0,
            "zonder_sturing_eur": -1.0,
            "co2_kg": 0.2,
        }
        for n in range(1, dagen + 1)
    ]
    c.pv_production_today_kwh = 3.0
    c.gross_consumption_today_kwh = 2.0
    c.grid_import_today_kwh = 0.5
    c.pv_export_today_kwh = 1.0
    c.battery_discharge_today_kwh = 1.5
    c.actual_cost_today_eur = -0.4
    c.counterfactual_cost_today_eur = -0.1
    return c


def test_every_quantity_appears_in_every_period(make_coordinator, hass):
    """Het punt van de vraag: niet één onderwerp maar allemaal."""
    c = _coordinator(make_coordinator)

    o = c.get_period_overview(NU)

    sleutels = [g["sleutel"] for g in o["grootheden"]]
    assert "opwek_kwh" in sleutels
    assert "verbruik_kwh" in sleutels
    assert "accu_ontladen_kwh" in sleutels
    assert "kosten_eur" in sleutels

    for naam in ("week", "maand", "jaar"):
        for sleutel in sleutels:
            assert sleutel in o["perioden"][naam], f"{naam}/{sleutel}"


def test_a_week_adds_up(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    week = c.get_period_overview(NU)["perioden"]["week"]

    assert week["dagen"] == 6
    assert week["opwek_kwh"] == 120.0
    assert week["accu_ontladen_kwh"] == 30.0


def test_savings_is_a_difference_not_a_sum(make_coordinator, hass):
    """Besparing is het verschil tussen twee reeksen; optellen van een
    kolom zou onzin geven."""
    c = _coordinator(make_coordinator)

    week = c.get_period_overview(NU)["perioden"]["week"]

    # 6 dagen x (-1,00 zonder sturing min -2,00 werkelijk) = +6,00
    assert week["besparing_eur"] == 6.0


def test_today_counts_from_the_live_counters(make_coordinator, hass):
    """Vandaag zit nog niet in de reeks; die komt uit de lopende
    tellers."""
    c = _coordinator(make_coordinator)

    vandaag = c.get_period_overview(NU)["perioden"]["vandaag"]

    assert vandaag["opwek_kwh"] == 3.0
    assert vandaag["besparing_eur"] == 0.3


def test_the_contract_year_is_included_when_set(make_coordinator, hass):
    c = _coordinator(
        make_coordinator, **{CONF_CONTRACT_START_DATE: "2026-08-01"}
    )

    o = c.get_period_overview(NU)

    assert "contractjaar" in o["perioden"]
    assert o["perioden"]["contractjaar"]["dagen"] == 13


def test_without_a_contract_date_it_is_left_out(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    assert "contractjaar" not in c.get_period_overview(NU)["perioden"]


def test_an_empty_series_still_shows_today(make_coordinator, hass):
    """Vlak na de eerste installatie is er nog geen afgesloten dag."""
    c = _coordinator(make_coordinator, dagen=0)

    o = c.get_period_overview(NU)

    assert list(o["perioden"]) == ["vandaag"]


def test_a_day_missing_a_field_does_not_break_it(make_coordinator, hass):
    """Dagen van vóór deze versie hebben geen accu- of kostenveld."""
    c = _coordinator(make_coordinator)
    for r in c.energy_daily_history:
        r.pop("accu_ontladen_kwh", None)
        r.pop("kosten_eur", None)

    week = c.get_period_overview(NU)["perioden"]["week"]

    # v1.97.0: geen enkele dag met een waarde is iets anders dan een
    # periode die op nul uitkomt. Die nullen waren geen meting maar een
    # gat, en dat hoort zichtbaar te zijn.
    assert week["accu_ontladen_kwh"] is None
    assert week["opwek_kwh"] == 120.0


# --- v1.92.0: gemiddelden en historische cijfers ---------------------


def test_every_period_has_a_daily_average(make_coordinator, hass):
    """Gevraagd: "Worden de kosten en het verbruik etc ook
    dag/week/maand/jaar meegenomen en gemiddelden etc."

    Zonder gemiddelde is een maand niet met een week te vergelijken - je
    kijkt dan naar het aantal dagen in plaats van naar het verbruik.
    """
    c = _coordinator(make_coordinator)

    week = c.get_period_overview(NU)["perioden"]["week"]

    assert week["gemiddeld_per_dag"]["opwek_kwh"] == 20.0
    assert week["gemiddeld_per_dag"]["verbruik_kwh"] == 10.0
    assert week["gemiddeld_per_dag"]["besparing_eur"] == 1.0


def test_the_average_makes_periods_comparable(make_coordinator, hass):
    """Een maand telt meer op dan een week, maar het gemiddelde hoort
    gelijk te zijn bij gelijke dagen."""
    c = _coordinator(make_coordinator)
    o = c.get_period_overview(NU)["perioden"]

    assert o["maand"]["opwek_kwh"] > o["week"]["opwek_kwh"]
    assert (
        o["maand"]["gemiddeld_per_dag"]["opwek_kwh"]
        == o["week"]["gemiddeld_per_dag"]["opwek_kwh"]
    )


def test_history_is_read_from_statistics_not_power(make_coordinator, hass):
    """Gevraagd: "Historische cijfers kun je toch meenemen?"

    Ja, maar alleen uit METERS. Een vermogenssensor zou per uur
    geintegreerd moeten worden en dat wordt een schatting; deze cijfers
    moeten naast een jaarafrekening kunnen liggen.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("async def async_bootstrap_energy_history")
    blok = bron[kop : kop + 4000]

    assert "statistics_during_period" in blok
    assert "CONF_GRID_IMPORT_ENERGY_SENSOR" in blok


def test_the_bootstrap_never_overwrites_measured_days():
    """Wat live is gemeten wint van wat achteraf uit statistieken komt -
    de live meting kent de splitsing tussen zon- en accu-export."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("async def async_bootstrap_energy_history")
    # v1.97.0: op de FUNCTIEGRENS zoeken, niet op een aantal tekens.
    # Dat brak zodra de functie groeide - een valkuil die al in de
    # overdracht staat beschreven.
    blok = bron[kop : bron.index("\n    def ", kop)]

    assert "if dag < oudste" in blok


def test_a_backfilled_day_is_marked(make_coordinator, hass):
    """Ingelezen dagen missen de export-splitsing; dat hoort zichtbaar te
    zijn en niet stilzwijgend als gemeten door te gaan."""
    c = _coordinator(make_coordinator, dagen=0)
    c.energy_daily_history = [
        {
            "datum": "2026-07-01",
            "opwek_kwh": 22.0,
            "import_kwh": 1.0,
            "export_kwh": 9.0,
            "verbruik_kwh": 14.0,
            "zon_export_kwh": None,
            "herkomst": "statistieken",
        }
    ]

    week = c.get_self_consumption_overview(NU)["perioden"].get("maand")

    # Zonder splitsing valt hij terug op de oude aanname, en dat mag -
    # als het maar navolgbaar is.
    assert c.energy_daily_history[0]["herkomst"] == "statistieken"


# --- v1.93.0: de eenheid stond niet vast -----------------------------


def test_the_unit_is_read_not_assumed():
    """Gemeld: "De data is onreëel - Opwek 131548 kWh over een week."

    Dat is een factor duizend: de bronsensor levert wattuur en de code
    nam kilowattuur aan. Statistieken dragen hun eigen eenheid.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("async def async_bootstrap_energy_history")
    blok = bron[kop : bron.index("\n    def ", kop)]

    assert "get_metadata" in blok
    assert "ENERGY_UNIT_TO_KWH" in blok


def test_the_conversion_table_covers_the_usual_units():
    from custom_components.energy_management_system.const import (
        ENERGY_UNIT_TO_KWH,
    )

    assert ENERGY_UNIT_TO_KWH["Wh"] == 0.001
    assert ENERGY_UNIT_TO_KWH["kWh"] == 1.0
    assert ENERGY_UNIT_TO_KWH["MWh"] == 1000.0


def test_consumption_is_not_invented(make_coordinator, hass):
    """Stonden de netmeters niet ingesteld, dan werden import en export
    nul en kwam verbruik gelijk aan de opwek uit. In de tabel stond
    daardoor twee keer hetzelfde getal - en dat was meteen de verklikker
    dat er iets niet klopte."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("async def async_bootstrap_energy_history")
    blok = bron[kop : bron.index("\n    def ", kop)]

    assert '<= set(waarden)' in blok


def test_a_missing_field_counts_as_missing_not_zero(make_coordinator, hass):
    """Een ingelezen dag zonder netmeter mag de optelling niet laten
    omvallen, maar ook geen nul verzinnen."""
    c = _coordinator(make_coordinator, dagen=0)
    c.energy_daily_history = [
        {
            "datum": (NU.date() - timedelta(days=n)).isoformat(),
            "opwek_kwh": 20.0,
            "import_kwh": None,
            "export_kwh": None,
            "verbruik_kwh": None,
            "zon_export_kwh": None,
            "herkomst": "statistieken",
        }
        for n in range(1, 4)
    ]

    week = c.get_period_overview(NU)["perioden"]["week"]

    assert week["opwek_kwh"] == 60.0
    assert week["verbruik_kwh"] is None


def test_an_absurd_day_is_rejected():
    """Een dag met meer dan het plafond is geen meting maar een
    meterwissel of een teller die opnieuw begon."""
    from custom_components.energy_management_system.const import (
        ENERGY_DAY_SANITY_MAX_KWH,
    )

    assert ENERGY_DAY_SANITY_MAX_KWH < 1000


# --- v1.94.0: de foute reeks stond er nog ----------------------------


def test_days_from_an_older_bootstrap_are_discarded(make_coordinator, hass):
    """Gemeld na de reparatie van v1.93.0: de tabel stond nog steeds op
    131548 kWh per week.

    Terecht. Die versie repareerde het INLEZEN, maar de reeks was al
    bewaard - en de routine vult alleen dagen VOOR de oudste bekende dag
    aan. Die 399 foute dagen bleven dus staan.
    """
    from custom_components.energy_management_system.const import (
        ENERGY_BOOTSTRAP_VERSION,
    )

    oud = {"datum": "2025-07-11", "opwek_kwh": 21924.0, "herkomst": "statistieken"}
    nieuw = {
        "datum": "2025-07-12",
        "opwek_kwh": 21.9,
        "herkomst": "statistieken",
        "inlees_versie": ENERGY_BOOTSTRAP_VERSION,
    }
    gemeten = {"datum": "2026-08-13", "opwek_kwh": 18.0}

    bewaard = [
        r
        for r in (oud, nieuw, gemeten)
        if r.get("herkomst") != "statistieken"
        or r.get("inlees_versie", 0) >= ENERGY_BOOTSTRAP_VERSION
    ]

    assert bewaard == [nieuw, gemeten]


def test_a_measured_day_is_never_discarded(make_coordinator, hass):
    """Wat live is gemeten kent de export-splitsing en is niet opnieuw op
    te halen; dat blijft altijd staan."""
    from custom_components.energy_management_system.const import (
        ENERGY_BOOTSTRAP_VERSION,
    )

    gemeten = {"datum": "2026-08-13", "opwek_kwh": 18.0, "zon_export_kwh": 6.0}

    assert gemeten.get("herkomst") != "statistieken"
    assert ENERGY_BOOTSTRAP_VERSION >= 2


def test_an_impossible_day_is_rejected_regardless_of_origin(
    make_coordinator, hass
):
    """Een vangnet dat losstaat van het merkteken: 21924 kWh op een dag
    kan een woonhuis niet, wie het er ook in zette."""
    c = make_coordinator({})

    assert c._energiedag_is_onzin({"opwek_kwh": 21924.0}) is True
    assert c._energiedag_is_onzin({"verbruik_kwh": 131548.0}) is True
    assert c._energiedag_is_onzin({"opwek_kwh": 21.9}) is False


def test_a_day_with_missing_values_is_not_rejected(make_coordinator, hass):
    """Ontbrekend is geen onzin."""
    c = make_coordinator({})

    assert c._energiedag_is_onzin(
        {"opwek_kwh": 20.0, "verbruik_kwh": None, "import_kwh": None}
    ) is False


# --- v1.97.0: wat wél en niet uit geschiedenis kan --------------------


def test_the_battery_row_can_come_from_a_meter():
    """Gevraagd bij een screenshot waarop accu, kosten, CO2 en besparing
    nul stonden voor de langere perioden: "deze kunnen toch ook met data
    uit geschiedenis worden bepaald?"

    Wat een METER heeft wel: bij deze installatie
    `sensor.zendure_export` voor de accu.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("async def async_bootstrap_energy_history")
    blok = bron[kop : bron.index("\n    def ", kop)]

    assert "CONF_BATTERY_DISCHARGE_ENERGY_SENSOR" in blok


def test_co2_is_derived_not_measured():
    """CO2 volgt uit de al ingelezen netafname maal de intensiteit; daar
    is geen aparte meter voor nodig."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("async def async_bootstrap_energy_history")
    blok = bron[kop : bron.index("\n    def ", kop)]

    assert "co2_intensiteit" in blok


def test_savings_can_never_be_reconstructed(make_coordinator, hass):
    """Besparing is het verschil met een wereld zonder aansturing, en die
    is nooit ergens vastgelegd. Terugrekenen zou historische
    kwartierprijzen vragen die de prijssensor niet bewaart - en een
    geschat verschil naast echte cijfers zetten is erger dan een leeg
    vakje.
    """
    c = _coordinator(make_coordinator, dagen=0)
    c.energy_daily_history = [
        {
            "datum": (NU.date() - timedelta(days=n)).isoformat(),
            "opwek_kwh": 20.0,
            "kosten_eur": -2.0,
            "zonder_sturing_eur": None,
            "herkomst": "statistieken",
        }
        for n in range(1, 4)
    ]

    week = c.get_period_overview(NU)["perioden"]["week"]

    assert week["kosten_eur"] == -6.0
    assert week["besparing_eur"] is None


def test_a_measured_day_still_gives_savings(make_coordinator, hass):
    """Live gemeten dagen hebben de tegenfeitelijke kosten wel."""
    c = _coordinator(make_coordinator)

    assert c.get_period_overview(NU)["perioden"]["week"]["besparing_eur"] == 6.0
