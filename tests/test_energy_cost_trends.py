"""Week-, maand- en jaarcijfers plus trends voor stroom en gas (v1.8.0).

Gevraagd: "Graag ook voor gas, week, maand en jaar cijfers. Voor zowel
gas als electra wil ik ook een soort dagelijkse/wekelijkse trend zien.
Iets als meer verbruikt dan gister, minder verbruikt dan vorige week.
Dit wil ik dan in % zien."

Zonneplan levert voor gas alleen een DAGtotaal, dus week/maand/jaar
worden hier zelf opgebouwd.
"""
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system.const import COST_TREND_MIN_EUR

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _met_dagen(make_coordinator, stroom, gas=None):
    """Bouwt een geschiedenis van voltooide dagen, oudste eerst."""
    c = make_coordinator({})
    gas = gas if gas is not None else [None] * len(stroom)
    start = date(2026, 1, 1)
    c.daily_cost_history = [
        {
            "datum": (start + timedelta(days=i)).isoformat(),
            "stroom_eur": s,
            "gas_eur": g,
        }
        for i, (s, g) in enumerate(zip(stroom, gas))
    ]
    c._huidige_dagkosten = lambda: {"stroom_eur": 0.5, "gas_eur": 0.2}
    return c


# --- totalen ---------------------------------------------------------


def test_week_month_and_year_totals(make_coordinator, hass):
    c = _met_dagen(make_coordinator, [1.0] * 40, [0.5] * 40)

    o = c.get_energy_cost_overview()

    assert o["stroom"]["week"] == 7.0
    assert o["stroom"]["maand"] == 30.0
    assert o["stroom"]["jaar"] == 40.0
    assert o["gas"]["week"] == 3.5


def test_gas_totals_are_built_from_daily_values(make_coordinator, hass):
    """Zonneplan levert voor gas geen maand- of jaarcijfer; die worden
    hier opgebouwd."""
    c = _met_dagen(make_coordinator, [1.0] * 10, [0.30] * 10)

    assert c.get_energy_cost_overview()["gas"]["week"] == 2.1


def test_missing_gas_gives_no_total(make_coordinator, hass):
    """Wie geen gas bij dezelfde leverancier heeft, hoort geen nul te
    zien - dat suggereert dat er niets verbruikt is."""
    c = _met_dagen(make_coordinator, [1.0] * 10)

    assert c.get_energy_cost_overview()["gas"]["week"] is None


# --- trends ----------------------------------------------------------


def test_the_day_trend_compares_two_complete_days(make_coordinator, hass):
    """Gisteren tegen eergisteren - allebei volledig."""
    c = _met_dagen(make_coordinator, [2.0, 3.0])

    o = c.get_energy_cost_overview()

    assert o["stroom"]["gisteren"] == 3.0
    assert o["stroom"]["eergisteren"] == 2.0
    assert o["stroom"]["dagtrend_procent"] == 50.0


def test_a_cheaper_day_gives_a_negative_percentage(make_coordinator, hass):
    c = _met_dagen(make_coordinator, [4.0, 3.0])

    assert c.get_energy_cost_overview()["stroom"]["dagtrend_procent"] == -25.0


def test_the_week_trend_compares_two_full_weeks(make_coordinator, hass):
    c = _met_dagen(make_coordinator, [1.0] * 7 + [2.0] * 7)

    o = c.get_energy_cost_overview()

    assert o["stroom"]["vorige_week"] == 7.0
    assert o["stroom"]["week"] == 14.0
    assert o["stroom"]["weektrend_procent"] == 100.0


def test_no_week_trend_before_two_weeks(make_coordinator, hass):
    c = _met_dagen(make_coordinator, [1.0] * 10)

    assert "weektrend_procent" not in c.get_energy_cost_overview()["stroom"]


def test_a_tiny_amount_gives_no_percentage(make_coordinator, hass):
    """Van 2 cent naar 4 cent is "+100%" en dat is pure ruis."""
    klein = COST_TREND_MIN_EUR / 10
    c = _met_dagen(make_coordinator, [klein, klein * 2])

    assert c.get_energy_cost_overview()["stroom"]["dagtrend_procent"] is None


def test_gas_and_electricity_are_trended_separately(make_coordinator, hass):
    c = _met_dagen(make_coordinator, [2.0, 3.0], [1.0, 0.5])

    o = c.get_energy_cost_overview()

    assert o["stroom"]["dagtrend_procent"] == 50.0
    assert o["gas"]["dagtrend_procent"] == -50.0


# --- de kern: geen trend op een halve dag ----------------------------


def test_today_has_no_trend(make_coordinator, hass):
    """Het belangrijkste ontwerppunt.

    "Vandaag tot nu toe" vergelijken met een volledige gisteren geeft de
    hele dag een negatieve trend die om middernacht vanzelf verdwijnt -
    om 10:00 sta je op een derde van je dagverbruik en dat leest als
    "65% minder", terwijl er niets aan de hand is.
    """
    c = _met_dagen(make_coordinator, [3.0, 3.0])

    o = c.get_energy_cost_overview()

    assert o["vandaag_tot_nu_toe"]["stroom_eur"] == 0.5
    # De dagtrend gaat over gisteren/eergisteren, niet over vandaag.
    assert o["stroom"]["gisteren"] == 3.0
    assert "vandaag" not in str(o["stroom"].keys())


def test_the_note_explains_why(make_coordinator, hass):
    c = _met_dagen(make_coordinator, [1.0] * 3)

    assert "VOLTOOIDE dagen" in c.get_energy_cost_overview()["note"]


# --- dagafsluiting ---------------------------------------------------


def test_a_day_is_closed_at_the_rollover(make_coordinator, hass):
    c = make_coordinator({})
    c._huidige_dagkosten = lambda: {"stroom_eur": 1.5, "gas_eur": 0.4}

    c._update_daily_cost_history(NOW)          # eerste tick: ijkpunt
    c._update_daily_cost_history(NOW + timedelta(hours=6))
    c._update_daily_cost_history(NOW + timedelta(days=1))

    assert len(c.daily_cost_history) == 1
    assert c.daily_cost_history[0]["stroom_eur"] == 1.5


def test_the_value_from_before_midnight_is_kept(make_coordinator, hass):
    """De Zonneplan-teller springt om middernacht terug naar nul, dus na
    de wissel is de vorige dag niet meer op te vragen."""
    c = make_coordinator({})
    c._huidige_dagkosten = lambda: {"stroom_eur": 2.8, "gas_eur": 0.9}
    c._update_daily_cost_history(NOW)
    c._update_daily_cost_history(NOW + timedelta(hours=11))

    # Na middernacht staat de teller weer op nul.
    c._huidige_dagkosten = lambda: {"stroom_eur": 0.0, "gas_eur": 0.0}
    c._update_daily_cost_history(NOW + timedelta(days=1))

    assert c.daily_cost_history[0]["stroom_eur"] == 2.8


def test_the_history_survives_a_restart(make_coordinator, hass):
    """Zonder bewaren zou er nooit een week-, maand- of jaarcijfer
    ontstaan."""
    import asyncio

    bron = _met_dagen(make_coordinator, [1.0] * 5)
    asyncio.run(bron.async_save_persisted_state_now())

    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())

    assert len(verse.daily_cost_history) == 5
