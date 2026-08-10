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
        prijs = 0.35 if start.hour < 11 else (0.15 if start.hour < 17 else 0.38)
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
    plan te diep, dan is het te gretig."""
    samenvatting = _coordinator(make_coordinator, hass).get_quarter_plan_summary(
        NU
    )

    assert 0 <= samenvatting["laagste_soc_procent"] <= 100
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
    """Gevraagd: "moet eigenlijk vooruitkijken zoveel prijzen er zijn,
    dus waarschijnlijk max. 36 regels." Negen uur is genoeg om te zien
    wat er komt zonder dat de tabel onleesbaar wordt."""
    from custom_components.energy_management_system.const import (
        QUARTER_PLAN_MAX_ROWS,
    )

    plan = _coordinator(make_coordinator, hass).get_quarter_plan(NU)

    assert len(plan) <= QUARTER_PLAN_MAX_ROWS
    assert QUARTER_PLAN_MAX_ROWS == 36


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
