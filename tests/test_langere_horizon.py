"""Vasthouden voor morgen in plaats van nu terugleveren (v2.6.0).

Gevraagd: "Houdt de integratie ook rekening met bijvoorbeeld minder PV
energie morgen en daardoor meer te behouden in plaats van terugleveren?"

Deels. De reserve kijkt tot het EERSTVOLGENDE goedkope blok en
redeneert dan: daar kan ik bijladen. De vraag erachter is een andere dan
"haal ik de nacht": is deze kWh MORGEN meer waard dan wat hij nu
opbrengt?

Deze kandidaat meet dat en stuurt niets - dezelfde route als de
slijtagekosten (v1.38.0).
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    LANGERE_HORIZON_MIN_METINGEN,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 8, 16, 19, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, prijs_nu=0.35, later=0.45):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.last_current_price_per_kwh = prijs_nu
    c.is_battery_discharging = lambda: True
    c.last_cheap_block_end = NU + timedelta(hours=16)
    entries = [
        (
            NU + timedelta(hours=16, minutes=15 * i),
            None,
            later * PRICE_SCALE_FACTOR,
        )
        for i in range(8)
    ]
    c._get_forecast_entries = lambda *a, **k: entries
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.2}
    return c


def test_a_measurement_is_recorded_while_discharging(
    make_coordinator, hass
):
    c = _coordinator(make_coordinator, hass)

    c._meet_langere_horizon(NU)

    assert len(c.langere_horizon_history) == 1


def test_nothing_is_recorded_when_not_discharging(make_coordinator, hass):
    """De vraag speelt alleen op het moment dat er energie weggaat."""
    c = _coordinator(make_coordinator, hass)
    c.is_battery_discharging = lambda: False

    c._meet_langere_horizon(NU)

    assert c.langere_horizon_history == []


def test_holding_wins_when_tomorrow_is_dearer(make_coordinator, hass):
    """Nu 35 ct terugleveren tegen 45 ct besparen morgen, na rendement en
    slijtage - dat hoort positief uit te vallen."""
    c = _coordinator(make_coordinator, hass, prijs_nu=0.35, later=0.60)
    # Het rendement is een property; hier via de onderliggende reeksen.
    c.charge_efficiency_history = [95.0] * 3
    c.discharge_efficiency_history = [95.0] * 3

    c._meet_langere_horizon(NU)

    assert c.langere_horizon_history[0]["voordeel_eur_per_kwh"] > 0


def test_selling_wins_when_now_is_dearer(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, prijs_nu=0.70, later=0.30)
    # Het rendement is een property; hier via de onderliggende reeksen.
    c.charge_efficiency_history = [95.0] * 3
    c.discharge_efficiency_history = [95.0] * 3

    c._meet_langere_horizon(NU)

    assert c.langere_horizon_history[0]["voordeel_eur_per_kwh"] < 0


def test_efficiency_and_wear_are_subtracted(make_coordinator, hass):
    """Een kWh vasthouden kost rendement en slijtage; die horen van de
    besparing af."""
    c = _coordinator(make_coordinator, hass, prijs_nu=0.30, later=0.40)
    c.charge_efficiency_history = [89.5] * 3
    c.discharge_efficiency_history = [89.5] * 3

    c._meet_langere_horizon(NU)

    r = c.langere_horizon_history[0]
    # 0,40 x 0,80 - 0,042 = 0,278, tegen 0,30 + premie nu.
    assert r["besparing_later_eur"] < 0.40


def test_too_few_measurements_says_so(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    kandidaat = c._kandidaat_langere_horizon()

    assert kandidaat["waarde"] is None
    assert str(LANGERE_HORIZON_MIN_METINGEN) in str(
        kandidaat["zou_hebben_opgeleverd"]["reden"]
    )


def test_with_enough_measurements_it_reports(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c.langere_horizon_history = [
        {"voordeel_eur_per_kwh": 0.05 if i % 2 else -0.02}
        for i in range(LANGERE_HORIZON_MIN_METINGEN)
    ]

    kandidaat = c._kandidaat_langere_horizon()

    assert kandidaat["waarde"] is not None
    assert kandidaat["zou_hebben_opgeleverd"]["te_becijferen"] is True


def test_it_admits_what_it_does_not_know(make_coordinator, hass):
    """Deze meting weet niet of de accu die kWh straks nog kwijt kan. Op
    een zomerdag met overschot is vasthouden zinloos - dan is de accu
    toch vol. Dat hoort erbij te staan."""
    c = _coordinator(make_coordinator, hass)
    c.langere_horizon_history = [
        {"voordeel_eur_per_kwh": 0.05}
    ] * LANGERE_HORIZON_MIN_METINGEN

    kandidaat = c._kandidaat_langere_horizon()

    assert "vol" in kandidaat["betrouwbaarheid"]
    assert "niets stuurt" in kandidaat["betrouwbaarheid"]


def test_it_steers_nothing():
    """Een kandidaat op de proefstand mag de aansturing niet raken."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def _meet_langere_horizon")
    blok = bron[kop : bron.index("\n    def ", kop + 10)]
    code = "\n".join(r.split("#")[0] for r in blok.splitlines())

    for verboden in (
        "_async_apply_operation",
        "last_reason =",
        "force_manual",
    ):
        assert verboden not in code, verboden
