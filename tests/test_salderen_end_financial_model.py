"""Saldering-bewuste financiële waardering (v0.63.117).

Gevraagd: "Als de accu terug levert aan mijn woning bespaart dit
inkopen, als de accu laadt beperkt dit opbrengst van terug levering PV
energie. Zit dit ook in alle kosten/financiele berekeningen zo
verwerkt?" - gevolgd door: "Alles oppakken en integreren dat vanaf
01-01-2027 saldering niet meer geldt."

Twee dingen worden hier vastgelegd:

1. **Symmetrie van de terugleverpremie.** Tot v0.63.116 werd de premie
   van €0,02/kWh WEL bijgeteld bij export, maar NIET afgetrokken bij
   het laden van PV-overschot dat anders was teruggeleverd. Een
   structurele, altijd eenzijdige overschatting van de besparing.

2. **Einde saldering.** Zolang salderen geldt is een teruggeleverde kWh
   evenveel waard als een ingekochte kWh kost. Daarna niet meer: dan
   levert teruglevering alleen nog het kale (onbelaste) marktarief op,
   terwijl inkoop belast blijft. Elke financiële berekening moet dat
   onderscheid maken, anders wordt de opbrengst van teruglevering fors
   overschat en de waarde van opslaan onderschat.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_FEEDIN_COST_EUR_PER_KWH,
    CONF_PV_POWER_SENSOR,
    CONF_SALDEREN_END_DATE,
    FEEDIN_PREMIUM_EUR_PER_KWH,
    PRICE_SCALE_FACTOR,
)

TZ = timezone.utc
TIJDENS_SALDEREN = datetime(2026, 8, 6, 12, 0, tzinfo=TZ)
NA_SALDEREN = datetime(2027, 3, 5, 12, 0, tzinfo=TZ)

# €0,30/kWh inkoop (incl. belasting), €0,08/kWh kale marktprijs.
INKOOP_EUR = 0.30
MARKT_EUR = 0.08


def _entries(moment, prijs_eur):
    start = moment - timedelta(minutes=5)
    end = moment + timedelta(minutes=55)
    return [(start, end, prijs_eur * PRICE_SCALE_FACTOR)]


def _price_sensor_state(moment):
    """Forecast met zowel belaste als onbelaste prijs, zoals Zonneplan
    die levert."""
    start = moment - timedelta(minutes=5)
    end = moment + timedelta(minutes=55)
    return {
        "forecast": [
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "price_tax_included": {"amount": INKOOP_EUR * PRICE_SCALE_FACTOR},
                "price_tax_excluded": {"amount": MARKT_EUR * PRICE_SCALE_FACTOR},
            }
        ]
    }


def _make(make_coordinator, hass, moment, extra=None):
    config = {
        CONF_PRICE_SENSOR: "sensor.prijs",
        CONF_AVAILABLE_ENERGY_SENSOR: "sensor.accu_beschikbaar",
        CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1",
        CONF_PV_POWER_SENSOR: "sensor.pv",
        CONF_BATTERY_POWER_SENSOR: "sensor.accu_vermogen",
        CONF_SALDEREN_END_DATE: "2026-12-31",
    }
    config.update(extra or {})
    coordinator = make_coordinator(config)
    hass.states.set("sensor.prijs", "0.30", _price_sensor_state(moment))
    return coordinator


# --- Regime-bepaling ---------------------------------------------------


def test_salderen_active_on_the_final_day(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)
    assert coordinator._is_salderen_active(datetime(2026, 12, 31, 23, 0, tzinfo=TZ))


def test_salderen_inactive_the_next_day(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)
    assert not coordinator._is_salderen_active(datetime(2027, 1, 1, 0, 30, tzinfo=TZ))


def test_invalid_end_date_falls_back_to_salderen_active(make_coordinator, hass):
    """Bewust conservatief: een typefout mag niet stilzwijgend een heel
    ander waarderingsmodel activeren."""
    coordinator = _make(
        make_coordinator, hass, TIJDENS_SALDEREN, {CONF_SALDEREN_END_DATE: "geen datum"}
    )
    assert coordinator._is_salderen_active(NA_SALDEREN)


# --- Terugleverwaarde --------------------------------------------------


def test_feedin_value_equals_import_price_plus_premium_under_salderen(
    make_coordinator, hass
):
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)
    waarde = coordinator._get_feedin_value_per_kwh(
        _entries(TIJDENS_SALDEREN, INKOOP_EUR), TIJDENS_SALDEREN
    )
    assert waarde == INKOOP_EUR + FEEDIN_PREMIUM_EUR_PER_KWH


def test_feedin_value_drops_to_market_rate_after_salderen(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, NA_SALDEREN)
    waarde = coordinator._get_feedin_value_per_kwh(
        _entries(NA_SALDEREN, INKOOP_EUR), NA_SALDEREN
    )
    assert waarde == MARKT_EUR + FEEDIN_PREMIUM_EUR_PER_KWH


def test_feedin_costs_are_subtracted_after_salderen(make_coordinator, hass):
    coordinator = _make(
        make_coordinator,
        hass,
        NA_SALDEREN,
        {CONF_FEEDIN_COST_EUR_PER_KWH: 0.05},
    )
    waarde = coordinator._get_feedin_value_per_kwh(
        _entries(NA_SALDEREN, INKOOP_EUR), NA_SALDEREN
    )
    assert abs(waarde - (MARKT_EUR + FEEDIN_PREMIUM_EUR_PER_KWH - 0.05)) < 1e-9


def test_feedin_value_may_go_negative(make_coordinator, hass):
    """Bij hoge terugleverkosten kost terugleveren geld - dat wordt
    bewust niet op nul afgekapt."""
    coordinator = _make(
        make_coordinator, hass, NA_SALDEREN, {CONF_FEEDIN_COST_EUR_PER_KWH: 0.5}
    )
    waarde = coordinator._get_feedin_value_per_kwh(
        _entries(NA_SALDEREN, INKOOP_EUR), NA_SALDEREN
    )
    assert waarde < 0


# --- Splitsing van laad-/ontlaadstromen --------------------------------


def test_charge_split_recognises_pv_surplus(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)
    hass.states.set("sensor.pv", "3000")
    hass.states.set("sensor.p1", "-2000")
    hass.states.set("sensor.accu_vermogen", "0")

    pv_kwh, net_kwh = coordinator._split_charge_pv_vs_grid(1.0, 1.0)

    assert pv_kwh > 0
    assert abs(pv_kwh + net_kwh - 1.0) < 1e-9


def test_charge_split_without_pv_sensor_counts_everything_as_grid(
    make_coordinator, hass
):
    """Conservatief: zonder PV-sensor de hogere inkoopprijs aanhouden,
    zodat de besparing niet wordt overschat."""
    coordinator = _make(
        make_coordinator, hass, TIJDENS_SALDEREN, {CONF_PV_POWER_SENSOR: None}
    )
    pv_kwh, net_kwh = coordinator._split_charge_pv_vs_grid(1.0, 1.0)

    assert pv_kwh == 0.0
    assert net_kwh == 1.0


def test_discharge_split_separates_export_from_household_load(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)
    hass.states.set("sensor.p1", "-1000")
    hass.states.set("sensor.pv", "0")
    hass.states.set("sensor.accu_vermogen", "2000")

    export_kwh, load_kwh = coordinator._split_discharge_export_vs_load(2.0, 1.0)

    assert export_kwh > 0
    assert load_kwh > 0
    assert abs(export_kwh + load_kwh - 2.0) < 1e-9


# --- Kostprijs bij laden ------------------------------------------------


def _charge_once(coordinator, hass, moment, van_kwh, naar_kwh, prijs_eur=INKOOP_EUR):
    entries = _entries(moment, prijs_eur)
    hass.states.set("sensor.accu_beschikbaar", str(van_kwh))
    coordinator._update_battery_cost_basis_and_savings(
        moment - timedelta(minutes=5), entries
    )
    hass.states.set("sensor.accu_beschikbaar", str(naar_kwh))
    coordinator._update_battery_cost_basis_and_savings(moment, entries)


def test_pv_charged_energy_costs_the_forgone_feedin_under_salderen(
    make_coordinator, hass
):
    """DE KERN VAN DE ASYMMETRIE-FIX: PV-overschot dat de accu ingaat
    kost de inkoopprijs PLUS de gemiste premie - niet alleen de
    inkoopprijs."""
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)
    hass.states.set("sensor.pv", "20000")
    hass.states.set("sensor.p1", "-20000")
    hass.states.set("sensor.accu_vermogen", "0")

    _charge_once(coordinator, hass, TIJDENS_SALDEREN, 1.0, 2.0)

    verwacht = INKOOP_EUR + FEEDIN_PREMIUM_EUR_PER_KWH
    assert abs(coordinator.battery_cost_basis_eur_per_kwh - verwacht) < 1e-6


def test_grid_charged_energy_still_costs_the_import_price(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)
    hass.states.set("sensor.pv", "0")
    hass.states.set("sensor.p1", "3000")
    hass.states.set("sensor.accu_vermogen", "0")

    _charge_once(coordinator, hass, TIJDENS_SALDEREN, 1.0, 2.0)

    assert abs(coordinator.battery_cost_basis_eur_per_kwh - INKOOP_EUR) < 1e-6


def test_pv_charged_energy_is_much_cheaper_after_salderen(make_coordinator, hass):
    """Na saldering is de gederfde teruglevering nog maar het kale
    marktarief - opslaan wordt daardoor juist aantrekkelijk."""
    coordinator = _make(make_coordinator, hass, NA_SALDEREN)
    hass.states.set("sensor.pv", "20000")
    hass.states.set("sensor.p1", "-20000")
    hass.states.set("sensor.accu_vermogen", "0")

    _charge_once(coordinator, hass, NA_SALDEREN, 1.0, 2.0)

    verwacht = MARKT_EUR + FEEDIN_PREMIUM_EUR_PER_KWH
    assert abs(coordinator.battery_cost_basis_eur_per_kwh - verwacht) < 1e-6
    assert coordinator.battery_cost_basis_eur_per_kwh < INKOOP_EUR


def test_charge_source_split_is_tracked(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)
    hass.states.set("sensor.pv", "20000")
    hass.states.set("sensor.p1", "-20000")
    hass.states.set("sensor.accu_vermogen", "0")

    _charge_once(coordinator, hass, TIJDENS_SALDEREN, 1.0, 2.0)

    assert coordinator.charge_pv_kwh_total > 0
    assert coordinator.forgone_feedin_eur_total > 0


# --- Opbrengst bij ontladen --------------------------------------------


def _discharge_once(coordinator, hass, moment, van_kwh, naar_kwh):
    entries = _entries(moment, INKOOP_EUR)
    hass.states.set("sensor.accu_beschikbaar", str(van_kwh))
    coordinator._update_battery_cost_basis_and_savings(
        moment - timedelta(minutes=5), entries
    )
    hass.states.set("sensor.accu_beschikbaar", str(naar_kwh))
    coordinator._update_battery_cost_basis_and_savings(moment, entries)


def test_covering_household_load_saves_the_full_import_price(make_coordinator, hass):
    """Ontladen naar de woning bespaart inkoop tegen het volle,
    belaste tarief - ook na saldering."""
    coordinator = _make(make_coordinator, hass, NA_SALDEREN)
    coordinator.battery_cost_basis_eur_per_kwh = 0.0
    hass.states.set("sensor.pv", "0")
    hass.states.set("sensor.p1", "50000")
    hass.states.set("sensor.accu_vermogen", "0")

    _discharge_once(coordinator, hass, NA_SALDEREN, 2.0, 1.0)

    assert abs(coordinator.total_battery_savings_eur - 1.0 * INKOOP_EUR) < 1e-6


def test_exporting_earns_far_less_after_salderen(make_coordinator, hass):
    """Hetzelfde kWh, maar het net op in plaats van de woning in:
    na saldering fors minder waard."""
    coordinator = _make(make_coordinator, hass, NA_SALDEREN)
    coordinator.battery_cost_basis_eur_per_kwh = 0.0
    hass.states.set("sensor.pv", "0")
    hass.states.set("sensor.p1", "-100000")
    hass.states.set("sensor.accu_vermogen", "0")

    _discharge_once(coordinator, hass, NA_SALDEREN, 2.0, 1.0)

    verwacht = MARKT_EUR + FEEDIN_PREMIUM_EUR_PER_KWH
    assert abs(coordinator.total_battery_savings_eur - verwacht) < 1e-6
    assert coordinator.total_battery_savings_eur < INKOOP_EUR


def test_export_under_salderen_matches_the_old_formula(make_coordinator, hass):
    """Regressiebewaking: zolang salderen geldt moet de uitkomst exact
    gelijk blijven aan het oude model (prijs + premie op het
    geëxporteerde deel)."""
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)
    coordinator.battery_cost_basis_eur_per_kwh = 0.10
    hass.states.set("sensor.pv", "0")
    hass.states.set("sensor.p1", "-100000")
    hass.states.set("sensor.accu_vermogen", "0")

    _discharge_once(coordinator, hass, TIJDENS_SALDEREN, 2.0, 1.0)

    verwacht = 1.0 * (INKOOP_EUR - 0.10) + 1.0 * FEEDIN_PREMIUM_EUR_PER_KWH
    assert abs(coordinator.total_battery_savings_eur - verwacht) < 1e-6


# --- Tegenfeitelijke KPI -----------------------------------------------


def test_grid_flow_cost_uses_separate_rates_per_direction(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, NA_SALDEREN)

    import_kosten = coordinator._grid_flow_cost_eur(1000, 1.0, INKOOP_EUR, MARKT_EUR)
    export_opbrengst = coordinator._grid_flow_cost_eur(
        -1000, 1.0, INKOOP_EUR, MARKT_EUR
    )

    assert abs(import_kosten - INKOOP_EUR) < 1e-9
    assert abs(export_opbrengst + MARKT_EUR) < 1e-9


def test_grid_flow_cost_is_symmetric_under_salderen(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, TIJDENS_SALDEREN)

    import_kosten = coordinator._grid_flow_cost_eur(1000, 1.0, INKOOP_EUR, INKOOP_EUR)
    export_opbrengst = coordinator._grid_flow_cost_eur(
        -1000, 1.0, INKOOP_EUR, INKOOP_EUR
    )

    assert abs(import_kosten + export_opbrengst) < 1e-9


# --- Zichtbaarheid ------------------------------------------------------


def test_regime_is_reported_as_informational_after_salderen(make_coordinator, hass):
    coordinator = _make(make_coordinator, hass, NA_SALDEREN)
    coordinator.salderen_active = False
    coordinator.current_feedin_value_eur_per_kwh = MARKT_EUR

    summary = coordinator.get_diagnostic_summary()

    assert any("Salderen is vervallen" in p for p in summary["informatief"])
    assert summary["status"] == "nominaal"


def test_missing_feedin_tariff_after_salderen_is_a_real_attention_point(
    make_coordinator, hass
):
    """Zonder teruglevertarief valt alles terug op de inkoopprijs -
    dat overschat de opbrengst en verdient dus wél aandacht."""
    coordinator = _make(make_coordinator, hass, NA_SALDEREN)
    coordinator.salderen_active = False
    coordinator.current_feedin_value_eur_per_kwh = None

    summary = coordinator.get_diagnostic_summary()

    assert any("teruglevertarief" in p for p in summary["aandachtspunten"])



def test_dashboard_template_matches_the_repository_dashboard():
    """De twee dashboardbestanden moeten identiek blijven."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    template = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    repo = (
        Path(pkg.__file__).parent.parent.parent
        / "dashboards"
        / "energy_management_system_dashboard.yaml"
    ).read_text()

    assert template == repo
