"""Verwachte planning per kwartier (v1.22.2).

Gevraagd: "Tevens wil ik ergens op een dashboard deze verwachting per
kwartier (dus ook SoC in procenten) zodat ik dit kan monitoren en we
eventueel kunnen corrigeren."

En, over de tabel die ik eerder maakte: "Ik mis alleen de manual export
tegen dure prijzen... wanneer de accu van het net geladen is mag er niet
op manual ontladen worden."

Terecht - die tabel simuleerde alleen `smart` en `smart_discharging`.
Zonder de manual-verkoop belooft een planning iets anders dan de
aansturing doet, en dat is erger dan geen planning.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    PRICE_SCALE_FACTOR,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_MIN_SOC_PERCENT,
)

NU = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, van_net=False, beschikbaar=7.0):
    c = make_coordinator(
        {
            CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.cap",
            CONF_MIN_SOC_PERCENT: 15.0,
            CONF_MANUAL_DISCHARGE_POWER: 1600.0,
        }
    )
    hass.states.set("sensor.cap", "8.6")
    c.last_available_kwh = beschikbaar
    c.last_expensive_price_threshold = 0.32
    c._grid_charged_today = van_net

    entries = []
    for i in range(48):
        start = NU + timedelta(minutes=15 * i)
        # v1.24.2: rauwe eenheden, zoals Zonneplan ze levert
        prijs = (
            0.35 if start.hour < 11 else (0.15 if start.hour < 17 else 0.38)
        ) * PRICE_SCALE_FACTOR
        entries.append((start, start + timedelta(minutes=15), prijs))
    c._get_forecast_entries = lambda: entries
    c._estimate_pv_kwh_for_period = lambda a, b: (
        0.6 * (b - a).total_seconds() / 3600 if 9 <= a.hour < 18 else 0.0
    )
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: 0.3 * (b - a).total_seconds() / 3600
    )
    return c


# --- de manual-regel -------------------------------------------------


def test_solar_charged_battery_may_sell_at_high_prices(
    make_coordinator, hass
):
    """De eerder afgesproken regel: is de accu alleen met zon geladen,
    dan mag hij in dure kwartieren op manual verkopen."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    verkoop = [r for r in plan if "manual" in r["modus"]]

    assert verkoop
    assert all(r["prijs_ct"] >= 32 for r in verkoop)


def test_a_grid_charged_battery_never_sells(make_coordinator, hass):
    """Is de accu van het net geladen, dan zou verkopen dezelfde stroom
    met verlies terugverkopen - geen arbitrage."""
    plan = _coordinator(make_coordinator, hass, van_net=True).get_quarter_plan(
        NU
    )

    assert not [r for r in plan if "manual" in r["modus"]]


def test_cheap_quarters_never_sell(make_coordinator, hass):
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    for r in plan:
        if r["prijs_ct"] < 32:
            assert "manual" not in r["modus"]


def test_an_empty_battery_does_not_sell(make_coordinator, hass):
    """Zonder lading valt er niets te verkopen.

    Let op: mét zon vult de accu zich tussendoor weer, en dán mag hij in
    een duur kwartier wél verkopen - dat is juist de bedoeling. Deze
    test zet de zon daarom op nul, anders toetst hij iets anders dan hij
    beweert.
    """
    c = _coordinator(make_coordinator, hass, beschikbaar=0.05)
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0

    plan = c.get_quarter_plan(NU)

    assert not [r for r in plan if "manual" in r["modus"]]


def test_solar_refills_and_then_selling_resumes(make_coordinator, hass):
    """Het omgekeerde geval, expliciet: een lege accu die zich met zon
    vult, hoort daarna weer te verkopen in dure kwartieren."""
    plan = _coordinator(make_coordinator, hass, beschikbaar=0.05).get_quarter_plan(
        NU
    )

    assert [r for r in plan if "manual" in r["modus"]]


# --- de tabel zelf ---------------------------------------------------


def test_every_row_has_what_was_asked_for(make_coordinator, hass):
    """Gevraagd: prijs, verwachte PV, accustand en SoC in procenten."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    assert plan
    for r in plan:
        for veld in (
            "van",
            "tot",
            "prijs_ct",
            "zon_kwh",
            "verbruik_kwh",
            "modus",
            "soc_kwh",
            "soc_procent",
        ):
            assert veld in r, veld


def test_the_soc_stays_within_bounds(make_coordinator, hass):
    """Een planning die boven 100% of onder 0% uitkomt, klopt niet."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    for r in plan:
        assert 0 <= r["soc_procent"] <= 100, r


def test_the_soc_moves_with_the_mode(make_coordinator, hass):
    """Verkopen hoort de accu te legen, zon opvangen hoort hem te
    vullen."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    verkoop = [r for r in plan if "manual" in r["modus"]]
    assert verkoop[0]["soc_procent"] > verkoop[-1]["soc_procent"]


def test_past_quarters_are_skipped(make_coordinator, hass):
    """Een planning gaat over wat komt, niet over wat voorbij is."""
    c = _coordinator(make_coordinator, hass)

    plan = c.get_quarter_plan(NU + timedelta(hours=6))

    assert all(r["van"] >= "15:00" for r in plan)


def test_without_prices_there_is_no_plan(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c._get_forecast_entries = lambda: []

    assert c.get_quarter_plan(NU) == []


def test_without_a_battery_reading_there_is_no_plan(make_coordinator, hass):
    """Gokken op een accustand zou een planning opleveren die nergens op
    slaat."""
    c = _coordinator(make_coordinator, hass)
    c.last_available_kwh = None

    assert c.get_quarter_plan(NU) == []


# --- inbedding -------------------------------------------------------


def test_it_is_on_the_dashboard():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    pagina = next(
        v for v in data["views"] if v.get("path") == "detail-kwartier"
    )
    kaarten = [k for s in pagina["sections"] for k in s.get("cards") or []]

    # v1.23.1: er staan meerdere markdown-kaarten op deze pagina
    # (samenvatting, verkooptoets, tabel). Zoeken op de kolomkop is
    # stabieler dan op één veld dat ook elders kan voorkomen.
    inhoud = next(
        k["content"]
        for k in kaarten
        if k.get("type") == "markdown" and "{% for r in p %}" in str(k.get("content"))
    )

    assert "soc_procent" in inhoud
    assert "prijs_ct" in inhoud
    # v1.23.2: de uitleg over de manual-verkoop staat op de
    # samenvattingspagina, bij de verkooptoets waar hij thuishoort.


def test_it_is_in_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "quarter_plan" in bron


# --- v1.23.1: samenvatting en opbrengst -----------------------------


def test_every_row_has_its_revenue(make_coordinator, hass):
    """Gevraagd: "ik wil dit graag volledig kunnen bewaken totdat we
    meer data hebben." Zonder opbrengst per kwartier is niet te zien
    waar de winst vandaan komt."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    for r in plan:
        assert "opbrengst_eur" in r
        assert "cumulatief_eur" in r
        assert "in_goedkoop_blok" in r


def test_the_running_total_adds_up(make_coordinator, hass):
    """Het cumulatief hoort de som van de losse kwartieren te zijn -
    anders klopt de eindwaarde niet."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    som = round(sum(r["opbrengst_eur"] for r in plan), 2)

    assert abs(plan[-1]["cumulatief_eur"] - som) < 0.01


def test_selling_earns_and_importing_costs(make_coordinator, hass):
    """Teruglevering hoort positief te zijn, import negatief."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    for r in plan:
        if r["net_kwh"] < 0:
            assert r["opbrengst_eur"] > 0, r
        elif r["net_kwh"] > 0:
            assert r["opbrengst_eur"] < 0, r


def test_the_summary_shows_what_was_asked(make_coordinator, hass):
    """Verwachte PV, verwachte winst, en genoeg om te bewaken."""
    samenvatting = _coordinator(make_coordinator, hass).get_quarter_plan_summary(
        NU
    )

    for veld in (
        "zon_kwh",
        "verbruik_kwh",
        "import_kwh",
        "export_kwh",
        "verwachte_opbrengst_eur",
        "opbrengst_uit_verkoop_eur",
        "verkoopkwartieren",
        "laagste_soc_procent",
        "eind_soc_procent",
        "modi",
    ):
        assert veld in samenvatting, veld


def test_the_lowest_soc_is_the_warning_signal(make_coordinator, hass):
    """De belangrijkste regel om te bewaken: zakt de accu volgens dit
    plan te diep, dan is het te gretig.

    v1.24.3: de ondergrens is niet 0 maar de harde minimum-SoC.
    """
    samenvatting = _coordinator(make_coordinator, hass).get_quarter_plan_summary(
        NU
    )

    assert 0 <= samenvatting["laagste_soc_procent"] <= 100
    assert samenvatting["laagste_soc_procent"] >= 0
    assert (
        samenvatting["laagste_soc_procent"]
        <= samenvatting["hoogste_soc_procent"]
    )


def test_the_summary_counts_every_quarter(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    plan = c.get_quarter_plan(NU)
    samenvatting = c.get_quarter_plan_summary(NU)

    assert samenvatting["kwartieren"] == len(plan)
    assert sum(samenvatting["modi"].values()) == len(plan)


def test_no_plan_means_no_summary(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c._get_forecast_entries = lambda: []

    assert c.get_quarter_plan_summary(NU)["beschikbaar"] is False


def test_the_summary_is_on_the_dashboard():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    pagina = next(v for v in data["views"] if v.get("path") == "detail-kwartier")
    kaarten = [k for s in pagina["sections"] for k in s.get("cards") or []]

    inhoud = " ".join(str(k.get("content", "")) for k in kaarten)

    # v1.23.2: de samenvatting staat op een eigen pagina, omdat de
    # tabel met alle kolommen anders over de leesbaarheidsgrens loopt.
    data2 = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    sam = next(
        v
        for v in data2["views"]
        if v.get("path") == "detail-planning-samenvatting"
    )
    samkaarten = [k for s in sam["sections"] for k in s.get("cards") or []]
    saminhoud = " ".join(str(k.get("content", "")) for k in samkaarten)

    assert "verwachte_opbrengst_eur" in saminhoud
    assert "laagste_soc_procent" in saminhoud
    assert "zon_kwh" in inhoud


# --- v1.23.2: vooruitkijken en wijzigingen --------------------------


def test_the_table_is_capped(make_coordinator, hass):
    """Gevraagd: "moet eigenlijk vooruitkijken zoveel prijzen er zijn."

    De grens is een fysiek plafond van twee etmalen, geen keuze - er
    komen nooit meer prijzen binnen dan dat.
    """
    from custom_components.energy_management_system.const import (
        QUARTER_PLAN_MAX_ROWS,
    )

    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    assert len(plan) <= QUARTER_PLAN_MAX_ROWS
    assert QUARTER_PLAN_MAX_ROWS == 192


# --- v1.25.0: zover als er prijzen zijn ------------------------------


def _lange_reeks(make_coordinator, hass, kwartieren=109):
    """Een coordinator met meer prijzen dan negen uur - zoals Zonneplan
    ze levert zodra de prijzen van morgen bekend zijn."""
    c = _coordinator(make_coordinator, hass)
    entries = []
    for i in range(kwartieren):
        start = NU + timedelta(minutes=15 * i)
        prijs = (
            0.35 if start.hour < 11 else (0.15 if start.hour < 17 else 0.38)
        ) * PRICE_SCALE_FACTOR
        entries.append((start, start + timedelta(minutes=15), prijs))
    c._get_forecast_entries = lambda: entries
    return c


def test_the_plan_runs_as_far_as_the_prices_do(make_coordinator, hass):
    """Gemeld: "De kwartierplanning toont niet de maximale aantal
    kwartieren vooruit (waarin zonneplan prijzen beschikbaar zijn)."

    In de export van 10 augustus stonden 109 toekomstige kwartieren
    klaar en toonde de tabel er 36.
    """
    plan = _lange_reeks(make_coordinator, hass, 109).get_quarter_plan(NU)

    assert len(plan) == 109


def test_the_physical_ceiling_still_holds(make_coordinator, hass):
    """Zoveel prijzen komen er nooit, maar een tabel die eindeloos
    doorgroeit is erger dan een die te kort is."""
    from custom_components.energy_management_system.const import (
        QUARTER_PLAN_MAX_ROWS,
    )

    plan = _lange_reeks(make_coordinator, hass, 400).get_quarter_plan(NU)

    assert len(plan) == QUARTER_PLAN_MAX_ROWS


def test_quarters_beyond_today_carry_a_day_marker(make_coordinator, hass):
    """Nu de tabel verder reikt dan een etmaal, komt elk tijdstip twee
    keer voor. Zonder dagmerk staat er twee keer "05:15" onder elkaar.
    """
    plan = _lange_reeks(make_coordinator, hass, 109).get_quarter_plan(NU)

    vandaag = [r for r in plan if r["dag"] == ""]
    morgen = [r for r in plan if r["dag"] == "morgen "]

    assert vandaag and morgen
    # Vandaag krijgt bewust geen merk - dat leest rustiger.
    assert all(r["dag"] == "" for r in plan[: len(vandaag)])
    # En een tijdstip dat twee keer voorkomt, is nu te onderscheiden.
    dubbel = [r for r in plan if r["van"] == plan[0]["van"]]
    assert len({(r["dag"], r["van"]) for r in dubbel}) == len(dubbel)


def test_the_dashboard_gets_a_slimmed_down_plan(make_coordinator, hass):
    """De sensor zat met 36 regels al op ruim 21 kB, en Home Assistant
    bewaart de attributen van een toestand boven 16 kB niet meer. Het
    dashboard krijgt daarom alleen de velden die de tabel toont.
    """
    import json

    c = _lange_reeks(make_coordinator, hass, 109)
    vol = c.get_quarter_plan(NU)
    kort = c.get_quarter_plan_compact(NU)

    assert len(kort) == len(vol)
    # Alles wat de tabel rendert, moet erin zitten.
    for veld in (
        "van",
        "dag",
        "prijs_ct",
        "zon_kwh",
        "modus",
        "soc_procent",
        "cumulatief_eur",
        "gewijzigd",
        "eerst_voorspeld",
        "tekort",
    ):
        assert veld in kort[0]
    # En de rest niet - dat is precies waar de winst zit.
    assert "soc_kwh" not in kort[0]
    assert "net_kwh" not in kort[0]
    assert len(json.dumps(kort)) < len(json.dumps(vol)) * 0.7


def test_the_summary_still_reads_the_full_rows(make_coordinator, hass):
    """De samenvatting rekent met verbruik en netto per kwartier; die
    velden zitten niet in de compacte variant. Dat mag niet stilletjes
    kapot gaan.
    """
    c = _lange_reeks(make_coordinator, hass, 109)
    c.get_quarter_plan_compact(NU)

    samenvatting = c.get_quarter_plan_summary(NU)

    assert samenvatting["beschikbaar"] is True
    assert samenvatting["kwartieren"] == 109


def test_a_changed_quarter_is_flagged(make_coordinator, hass):
    """Gevraagd: "als de waarde later door extra verbruik of iets
    dergelijks verandert (smart_discharge naar smart) bijvoorbeeld, wil
    ik dat de tekst rood gearceerd wordt."

    Juist die wijzigingen zeggen iets over hoe betrouwbaar de planning
    is.
    """
    c = _coordinator(make_coordinator, hass)
    eerste = c.get_quarter_plan(NU)

    assert not [r for r in eerste if r["gewijzigd"]]

    # De accu blijkt bijna leeg: verkopen kan niet meer.
    c.last_available_kwh = 0.3
    tweede = c.get_quarter_plan(NU)

    gewijzigd = [r for r in tweede if r["gewijzigd"]]

    assert gewijzigd
    assert all(r["eerst_voorspeld"] != r["modus"] for r in gewijzigd)


def test_an_unchanged_quarter_is_not_flagged(make_coordinator, hass):
    """Alles rood maken zou de markering waardeloos maken."""
    c = _coordinator(make_coordinator, hass)
    c.get_quarter_plan(NU)

    tweede = c.get_quarter_plan(NU)

    assert not [r for r in tweede if r["gewijzigd"]]


def test_the_summary_counts_the_changes(make_coordinator, hass):
    """Veel wijzigingen betekent dat de planning onrustig is - dat wil
    je in één oogopslag zien."""
    c = _coordinator(make_coordinator, hass)
    c.get_quarter_plan(NU)
    c.last_available_kwh = 0.3

    samenvatting = c.get_quarter_plan_summary(NU)

    assert samenvatting["gewijzigde_kwartieren"] > 0


def test_past_quarters_are_not_shown(make_coordinator, hass):
    """Gevraagd: "Als kwartieren inmiddels voorbij zijn hoeft het niet
    meer getoond te worden." """
    c = _coordinator(make_coordinator, hass)

    plan = c.get_quarter_plan(NU + timedelta(hours=3))

    assert all(r["van"] >= "12:00" for r in plan)


def test_the_snapshot_stays_bounded(make_coordinator, hass):
    """Zonder begrenzing groeit de geschiedenis eindeloos."""
    from custom_components.energy_management_system.const import (
        QUARTER_PLAN_SNAPSHOT_LENGTH,
    )

    c = _coordinator(make_coordinator, hass)
    for uur in range(0, 40):
        c.get_quarter_plan(NU + timedelta(hours=uur))

    assert len(c.quarter_plan_first_seen) <= QUARTER_PLAN_SNAPSHOT_LENGTH


def test_the_card_marks_changes_in_red():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    pagina = next(v for v in data["views"] if v.get("path") == "detail-kwartier")
    kaarten = [k for s in pagina["sections"] for k in s.get("cards") or []]
    tabel = next(
        k["content"] for k in kaarten if "{% for r in p %}" in str(k.get("content"))
    )

    assert "color:#e05252" in tabel
    assert "r.gewijzigd" in tabel
    assert "eerst_voorspeld" in tabel


# --- v1.24.1: de accustand rechtstreeks lezen -----------------------


def test_the_plan_works_without_last_available_kwh(make_coordinator, hass):
    """Gemeld met screenshot: "Nog geen planning" en "Accustand
    onbekend" terwijl de accu gewoon 7,69 kWh had.

    `last_available_kwh` wordt alleen gezet als de HELE energie-check
    slaagt, en op een tak zonder verbruiksschatting zelfs expliciet op
    None. Dat veld is een bijproduct van die check, geen betrouwbare
    accustand.
    """
    from custom_components.energy_management_system.const import (
        CONF_AVAILABLE_ENERGY_SENSOR,
    )

    c = _coordinator(make_coordinator, hass)
    c.config = {**c.config, CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar"}
    hass.states.set("sensor.beschikbaar", "7.69")
    c.last_available_kwh = None

    assert c.beschikbare_energie_kwh() == 7.69
    assert c.get_quarter_plan(NU)


def test_it_falls_back_to_the_computed_value(make_coordinator, hass):
    """Zonder sensor blijft het bijproduct bruikbaar."""
    c = _coordinator(make_coordinator, hass)
    c.last_available_kwh = 5.0

    assert c.beschikbare_energie_kwh() == 5.0


def test_the_reason_says_what_is_missing(make_coordinator, hass):
    """"Nog geen planning" liet de gebruiker zoeken naar iets wat kapot
    leek, terwijl er gewoon een gegeven miste."""
    c = make_coordinator({})

    reden = c.get_quarter_plan_summary(NU)["reden"]

    assert "prijsgegevens" in reden
    assert "ontbreken" in reden or "ontbreekt" in reden


def test_a_missing_price_sensor_does_not_crash(make_coordinator, hass):
    """`_get_forecast_entries` gooit een KeyError zonder prijssensor -
    dezelfde valkuil als bij de export in v1.22.1. Een planning is
    informatief en mag nooit iets laten vallen."""
    c = make_coordinator({})

    assert c.get_quarter_plan(NU) == []
    assert c.get_quarter_plan_summary(NU)["beschikbaar"] is False


# --- v1.24.2: prijzen in euro's -------------------------------------


def test_the_revenue_is_in_euros(make_coordinator, hass):
    """Gemeld met screenshot: "Verwachte opbrengst 15124941.79 EUR" en
    de vraag "word ik nu miljonair?".

    `_get_forecast_entries` geeft de RAUWE waarde terug (3181681), niet
    euro's - elders wordt die door PRICE_SCALE_FACTOR gedeeld, in de
    nieuwe planning gebeurde dat niet.
    """
    samenvatting = _coordinator(make_coordinator, hass).get_quarter_plan_summary(
        NU
    )

    assert abs(samenvatting["verwachte_opbrengst_eur"]) < 100


def test_the_price_column_is_in_cents(make_coordinator, hass):
    """Een kwartierprijs hoort tussen -50 en 150 cent te liggen."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    for r in plan:
        assert -50 <= r["prijs_ct"] <= 150, r


# --- v1.24.3: de echte accustand ------------------------------------


def test_the_soc_never_drops_below_the_hard_floor(make_coordinator, hass):
    """Gemeld: "Dit kon toch niet, zoals aangegeven minimale soc = 10%.
    SoC laagste / hoogste 0% / 86%."

    Klopt: er werd het percentage van de BRUIKBARE capaciteit getoond,
    dus 0% betekende 10% - de harde ondergrens. Dat leest als iets
    onmogelijks. Nu de echte accustand, zoals in de Zendure-app.
    """
    from custom_components.energy_management_system.const import (
        CONF_MIN_SOC_PERCENT,
    )

    c = _coordinator(make_coordinator, hass)
    c.config = {**c.config, CONF_MIN_SOC_PERCENT: 10.0}
    hass.states.set("number.min_soc", "10")

    plan = c.get_quarter_plan(NU)

    for r in plan:
        assert r["soc_procent"] >= 10, r


def test_both_percentages_are_available(make_coordinator, hass):
    """De echte stand zegt wat de accu doet; het bruikbare deel zegt wat
    er nog te gebruiken valt. Allebei nuttig, maar niet hetzelfde."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    for r in plan:
        assert r["soc_procent"] >= r["soc_bruikbaar_procent"]


def test_an_empty_battery_reads_as_the_floor(make_coordinator, hass):
    """0% bruikbaar hoort samen te vallen met de harde ondergrens.

    v3.92.1: de accu kwam hier vroeger vanzelf op nul uit doordat de
    planning 's avonds tot leeg verkocht. Dat doet hij niet meer - de
    reservebodem staat er nu onder. Deze toets gaat over de WEERGAVE,
    dus de lege accu wordt hier rechtstreeks gezet: geen zon, niets
    binnen, en dan blijft hij leeg.
    """
    c = _coordinator(make_coordinator, hass, beschikbaar=0.0)
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0

    plan = c.get_quarter_plan(NU)
    leeg = [r for r in plan if r["soc_bruikbaar_procent"] == 0]

    assert leeg
    assert all(r["soc_procent"] == round(c.effective_min_soc_percent()) for r in leeg)


def test_the_summary_shows_both(make_coordinator, hass):
    samenvatting = _coordinator(make_coordinator, hass).get_quarter_plan_summary(
        NU
    )

    assert "laagste_soc_procent" in samenvatting
    assert "laagste_bruikbaar_procent" in samenvatting
    assert (
        samenvatting["laagste_soc_procent"]
        >= samenvatting["laagste_bruikbaar_procent"]
    )


# --- v1.27.0: de vermogensgrenzen gelden ook in de simulatie ---------


def _zonnig(make_coordinator, hass, zon_kw=8.0):
    """Een accu die leeg begint met veel meer zon dan hij kan opnemen.

    Gemeld: "Hier gaat wat mis de accu kan niet in 1 uur vol zijn."
    De simulatie kende de grenzen niet: 2000 W laden en 1600 W ontladen,
    bewust handmatig ingesteld.
    """
    from custom_components.energy_management_system.const import (
        CONF_MANUAL_CHARGE_POWER,
    )

    c = _coordinator(make_coordinator, hass, beschikbaar=0.1)
    c.config[CONF_MANUAL_CHARGE_POWER] = -2000.0
    c._estimate_pv_kwh_for_period = lambda a, b: (
        zon_kw * (b - a).total_seconds() / 3600 if 9 <= a.hour < 18 else 0.0
    )
    return c


def test_charging_respects_the_power_limit(make_coordinator, hass):
    """Met 2000 W kan er hooguit 0,5 kWh per kwartier in - wat de zon
    ook doet. De rest gaat naar het net."""
    plan = _zonnig(make_coordinator, hass).get_quarter_plan(NU)

    stijgingen = [
        plan[i + 1]["soc_kwh"] - plan[i]["soc_kwh"] for i in range(len(plan) - 1)
    ]

    assert max(stijgingen) <= 0.5 + 0.001


def test_the_battery_cannot_fill_in_an_hour(make_coordinator, hass):
    """De gemelde regel zelf: 10% -> 100% in vier kwartieren."""
    plan = _zonnig(make_coordinator, hass).get_quarter_plan(NU)

    vol = next(
        (i for i, r in enumerate(plan) if r["soc_procent"] >= 100), len(plan)
    )

    # 7,7 kWh bruikbaar bij 0,5 kWh per kwartier is minstens vijftien
    # kwartieren, niet vier.
    assert vol >= 15


def test_surplus_above_the_limit_goes_to_the_grid(make_coordinator, hass):
    """Zon die er niet in kan, hoort als teruglevering geboekt te worden
    - anders verdwijnt hij uit de opbrengst."""
    plan = _zonnig(make_coordinator, hass).get_quarter_plan(NU)

    overdag = [r for r in plan if 9 <= int(r["van"][:2]) < 17]

    assert all(r["net_kwh"] < 0 for r in overdag)


def test_discharging_respects_the_power_limit(make_coordinator, hass):
    """1600 W is 0,4 kWh per kwartier; meer kan de accu niet leveren."""
    c = _coordinator(make_coordinator, hass)
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: 3.0 * (b - a).total_seconds() / 3600
    )

    plan = c.get_quarter_plan(NU)

    dalingen = [
        plan[i]["soc_kwh"] - plan[i + 1]["soc_kwh"] for i in range(len(plan) - 1)
    ]

    assert max(dalingen) <= 0.4 + 0.001


# --- v1.42.0: tekorten tellen tot het bijladen -----------------------


def test_shortfalls_are_counted_until_the_cheap_block(
    make_coordinator, hass
):
    """Gevonden in de export van 11 augustus 16:31: 36 tekortkwartieren,
    en de melding "Accu haalt de nacht mogelijk niet" ging om 14:30,
    15:31 én 16:31 af.

    Dat getal was zinloos geworden. Het telde over de HELE planning, en
    die reikt sinds v1.25.0 zover als er prijzen zijn - daar 126
    kwartieren, ruim 31 uur. Over die periode vraagt het huis 38 kWh
    terwijl er 7,78 kWh in de accu past; dat de accu ergens leeg is, is
    dan geen storing maar rekenkunde.
    """
    c = _coordinator(make_coordinator, hass, beschikbaar=0.4)
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: 0.5 * (b - a).total_seconds() / 3600
    )
    c.last_cheap_block_start = NU + timedelta(hours=2)
    c.last_cheap_block_end = NU + timedelta(hours=8)

    samenvatting = c.get_quarter_plan_summary(NU)

    # Tot het blok is het een handvol kwartieren; daarna loopt de accu
    # de hele nacht leeg en zou de oude telling tientallen opleveren.
    assert samenvatting["tekort_kwartieren"] < 10
    assert (
        samenvatting["tekort_kwartieren_hele_planning"]
        > samenvatting["tekort_kwartieren"]
    )


def test_inside_the_cheap_block_nothing_counts(make_coordinator, hass):
    """Staan we er al in, dan is de belofte ingelost."""
    c = _coordinator(make_coordinator, hass, beschikbaar=0.4)
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: 0.5 * (b - a).total_seconds() / 3600
    )
    c.last_cheap_block_start = NU - timedelta(hours=1)
    c.last_cheap_block_end = NU + timedelta(hours=5)

    assert c.get_quarter_plan_summary(NU)["tekort_kwartieren"] == 0


def test_without_a_cheap_block_everything_counts(make_coordinator, hass):
    """Zonder blok is er niets om op te wachten, dus telt de hele
    planning - net als voorheen."""
    c = _coordinator(make_coordinator, hass, beschikbaar=0.4)
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: 0.5 * (b - a).total_seconds() / 3600
    )
    c.last_cheap_block_start = None

    samenvatting = c.get_quarter_plan_summary(NU)

    assert (
        samenvatting["tekort_kwartieren"]
        == samenvatting["tekort_kwartieren_hele_planning"]
    )


# --- v1.44.0: wélke uren hangt het huis aan het net? -----------------


def _leeglopend(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, beschikbaar=0.4)
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: 0.5 * (b - a).total_seconds() / 3600
    )
    c.last_cheap_block_start = NU + timedelta(hours=4)
    c.last_cheap_block_end = NU + timedelta(hours=10)
    return c


def test_the_shortfall_hours_are_named(make_coordinator, hass):
    """Gevraagd: "waar zie ik dan welke uren hij verwacht aan het net te
    hangen?"

    Nergens - tenzij je de 120 regels van de kwartiertabel afzocht op
    het uitroepteken. Een aantal zonder tijdstip is een alarm zonder
    adres.
    """
    samenvatting = _leeglopend(make_coordinator, hass).get_quarter_plan_summary(NU)

    perioden = samenvatting["tekort_perioden"]

    assert perioden
    assert "-" in perioden[0]


def test_consecutive_quarters_become_one_period(make_coordinator, hass):
    """Acht losse tijdstippen leest niemand; "03:15-05:15" wel."""
    samenvatting = _leeglopend(make_coordinator, hass).get_quarter_plan_summary(NU)

    assert len(samenvatting["tekort_perioden"]) == 1
    assert samenvatting["tekort_kwartieren"] > 1


def test_the_periods_match_the_count(make_coordinator, hass):
    """Perioden en telling komen uit dezelfde regels; lopen ze uiteen,
    dan klopt een van beide niet."""
    c = _leeglopend(make_coordinator, hass)

    samenvatting = c.get_quarter_plan_summary(NU)
    plan = c.get_quarter_plan(NU)
    losse = [
        r for r in plan if r.get("tekort") and r.get("voor_bijladen", True)
    ]

    assert samenvatting["tekort_kwartieren"] == len(losse)
    assert bool(samenvatting["tekort_perioden"]) == bool(losse)


# --- v1.48.0: maten die met de horizon meegroeiden -------------------


def test_the_summary_can_be_bounded(make_coordinator, hass):
    """De planning loopt sinds v1.25.0 zover als er prijzen zijn - tot 31
    uur. De plantoetsing legde die verwachting naast de dagtellers, en
    die stoppen om middernacht.

    Bij 21 kWh rest-vandaag plus 23 kWh morgen tegenover 23 kWh gemeten
    zou er elke dag een afwijking van tientallen procenten zijn gemeld.
    """
    c = _lange_reeks(make_coordinator, hass, 109)
    middernacht = (NU + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    heel = c.get_quarter_plan_summary(NU)
    tot_middernacht = c.get_quarter_plan_summary(NU, tot=middernacht)

    assert heel["kwartieren"] == 109
    assert tot_middernacht["kwartieren"] < heel["kwartieren"]
    assert tot_middernacht["zon_kwh"] <= heel["zon_kwh"]


def test_every_row_carries_its_real_moment(make_coordinator, hass):
    """Tot nu toe droeg een planregel alleen "14:30", en moest elke
    afbakening met omwegen worden gemaakt - dat ging twee keer mis."""
    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    from homeassistant.util import dt as dt_util

    assert dt_util.parse_datetime(plan[0]["start"]) is not None


def test_the_lowest_soc_is_bounded_too(make_coordinator, hass):
    """"Laagste 10%" op de tegel ging over morgenochtend laat, niet over
    vannacht - en dat is wel wat je erin leest."""
    c = _lange_reeks(make_coordinator, hass, 109)
    c.last_available_kwh = 3.0
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: 0.4 * (b - a).total_seconds() / 3600
    )
    c.last_cheap_block_start = NU + timedelta(hours=3)
    c.last_cheap_block_end = NU + timedelta(hours=9)

    samenvatting = c.get_quarter_plan_summary(NU)
    plan = c.get_quarter_plan(NU)
    na_het_blok = [
        r["soc_procent"] for r in plan if not r.get("voor_bijladen", True)
    ]

    # De hele planning zakt verder dan het stuk tot het bijladen; de
    # tegel hoort dat laatste te tonen.
    assert min(na_het_blok) <= samenvatting["laagste_soc_procent"]
    assert (
        samenvatting["laagste_soc_tot_bijladen_procent"]
        >= samenvatting["laagste_soc_procent"]
    )


def test_inside_the_cheap_block_it_reports_the_current_level(
    make_coordinator, hass
):
    """Staan we al in het blok, dan is er niets te overbruggen."""
    c = _coordinator(make_coordinator, hass, beschikbaar=3.0)
    c.last_cheap_block_start = NU - timedelta(hours=1)
    c.last_cheap_block_end = NU + timedelta(hours=5)

    samenvatting = c.get_quarter_plan_summary(NU)

    assert samenvatting["laagste_soc_tot_bijladen_procent"] is not None


# --- v1.69.0: de goedkoop-drempel per dag ----------------------------


def test_the_cheap_threshold_is_per_day(make_coordinator, hass):
    """Nagelopen na "Gaat het misschien op nog meer plekken kapot?"

    De drempel werd berekend over alle beschikbare prijzen, dus over
    twee dagen tegelijk. Heeft morgen een extreme piek en vandaag niet,
    dan rekt die piek de range op en gelden er vandaag ineens veel meer
    kwartieren als "goedkoop blok".
    """
    c = _coordinator(make_coordinator, hass)
    morgen = NU + timedelta(days=1)
    entries = []
    for i in range(96):
        start = NU.replace(hour=0, minute=0) + timedelta(minutes=15 * i)
        # Vandaag vlak: 13 tot 38 ct.
        prijs = (0.13 if 10 <= start.hour < 16 else 0.38) * PRICE_SCALE_FACTOR
        entries.append((start, start + timedelta(minutes=15), prijs))
    for i in range(96):
        start = morgen.replace(hour=0, minute=0) + timedelta(minutes=15 * i)
        # Morgen een uitschieter van 72 ct.
        prijs = (0.72 if start.hour == 19 else 0.30) * PRICE_SCALE_FACTOR
        entries.append((start, start + timedelta(minutes=15), prijs))
    c._get_forecast_entries = lambda *a, **k: entries

    plan = c.get_quarter_plan(NU)
    vandaag = [r for r in plan if not r.get("dag")]

    # Met de gedeelde drempel (0,13 tot 0,72) zou 0,278 gelden en telde
    # ALLES van vandaag onder 27,8 ct als goedkoop blok. Met de eigen
    # drempel van vandaag (0,13 tot 0,38) is dat 0,193.
    duur_vandaag = [r for r in vandaag if r["prijs_ct"] > 25]

    assert duur_vandaag
    assert not [r for r in duur_vandaag if r["in_goedkoop_blok"]]


def test_tomorrow_gets_its_own_threshold(make_coordinator, hass):
    """En morgen mag niet met de vlakke dag van vandaag worden
    beoordeeld."""
    c = _coordinator(make_coordinator, hass)
    morgen = NU + timedelta(days=1)
    entries = []
    for i in range(96):
        start = NU.replace(hour=0, minute=0) + timedelta(minutes=15 * i)
        entries.append(
            (start, start + timedelta(minutes=15), 0.30 * PRICE_SCALE_FACTOR)
        )
    for i in range(96):
        start = morgen.replace(hour=0, minute=0) + timedelta(minutes=15 * i)
        prijs = (0.10 if 10 <= start.hour < 16 else 0.50) * PRICE_SCALE_FACTOR
        entries.append((start, start + timedelta(minutes=15), prijs))
    c._get_forecast_entries = lambda *a, **k: entries

    plan = c.get_quarter_plan(NU)
    goedkoop_morgen = [
        r for r in plan if r.get("dag") and r["in_goedkoop_blok"]
    ]

    assert goedkoop_morgen
    assert all(r["prijs_ct"] < 25 for r in goedkoop_morgen)
