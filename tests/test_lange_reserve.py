"""Verder vooruitkijken bij de reserve (v3.10.0).

Gevraagd: "Het gaat er mij vooral om dat er niet gewacht wordt tot een
duur kwartier om extra bij te laden. De integratie moet ruim vooruit
kijken."

Terecht, en de cijfers van 18 augustus laten het zien. De reserve rekent
tot het EERSTVOLGENDE goedkope blok - die dag tot 16:45. Daarna kwam de
avondpiek van 37,4 ct, en die telde niet mee bij de vraag hoeveel er in
dat blok van 28,9 ct geladen moest worden.

En daarna: "Eerst als meting, via de diagnostiek kun je dan later
bepalen of sturen wenselijk is toch?" Precies - dezelfde route als de
slijtagekosten.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    LANGE_RESERVE_MIN_METINGEN,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 8, 18, 9, 18, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, blok_ct=28.9, na_blok_ct=37.4):
    c = make_coordinator({})
    c.last_cheap_block_start = NU + timedelta(hours=2)
    c.last_cheap_block_end = NU + timedelta(hours=7)
    entries = []
    for i in range(60):
        moment = NU + timedelta(minutes=15 * i)
        in_blok = c.last_cheap_block_start <= moment < c.last_cheap_block_end
        ct = blok_ct if in_blok else na_blok_ct
        entries.append((moment, None, ct / 100 * PRICE_SCALE_FACTOR))
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.22}
    return c, entries


def test_the_short_and_long_horizon_are_both_computed(
    make_coordinator, hass
):
    c, entries = _coordinator(make_coordinator, hass)
    c._estimate_worst_case_deficit_kwh = lambda a, b: (
        0.3 if b == c.last_cheap_block_start else 2.8
    )

    c._meet_lange_reserve(NU, entries)

    r = c.lange_reserve_history[0]
    assert r["reserve_kort_kwh"] == 0.3
    assert r["reserve_lang_kwh"] == 2.8
    assert r["extra_kwh"] == 2.5


def test_it_compares_charging_cost_with_avoided_cost(
    make_coordinator, hass
):
    """Meer reserve betekent minder verkopen. Dat loont alleen als het
    prijsverschil de accukosten dekt - bij 84,5% rendement en 4,2 ct
    slijtage is dat ruwweg 11 ct."""
    c, entries = _coordinator(make_coordinator, hass)
    c._estimate_worst_case_deficit_kwh = lambda a, b: (
        0.3 if b == c.last_cheap_block_start else 2.8
    )
    c.charge_efficiency_history = [92.0] * 3
    c.discharge_efficiency_history = [92.0] * 3

    c._meet_lange_reserve(NU, entries)

    r = c.lange_reserve_history[0]
    # 28,9 ct laden bij 84,6% plus 4,22 ct slijtage is ruim 38 ct;
    # vermijden levert 37,4 ct op. Dat is dus NET niet gunstig.
    assert r["laadprijs_eur"] > 0.35
    assert r["voordeel_eur_per_kwh"] < 0


def test_a_big_price_gap_is_favourable(make_coordinator, hass):
    """Zoals na 1 januari, wanneer teruglevering nog 19 ct oplevert
    tegen 32 ct inkoop."""
    c, entries = _coordinator(make_coordinator, hass, blok_ct=12.0, na_blok_ct=40.0)
    c._estimate_worst_case_deficit_kwh = lambda a, b: (
        0.3 if b == c.last_cheap_block_start else 2.8
    )

    c._meet_lange_reserve(NU, entries)

    assert c.lange_reserve_history[0]["voordeel_eur_per_kwh"] > 0


def test_too_few_measurements_says_so(make_coordinator, hass):
    c, _ = _coordinator(make_coordinator, hass)

    kandidaat = c._kandidaat_lange_reserve()

    assert kandidaat["waarde"] is None
    assert str(LANGE_RESERVE_MIN_METINGEN) in str(
        kandidaat["zou_hebben_opgeleverd"]["reden"]
    )


def test_with_enough_measurements_it_reports(make_coordinator, hass):
    c, _ = _coordinator(make_coordinator, hass)
    c.lange_reserve_history = [
        {"extra_kwh": 2.5, "voordeel_eur_per_kwh": -0.05}
        for _ in range(LANGE_RESERVE_MIN_METINGEN)
    ]

    kandidaat = c._kandidaat_lange_reserve()

    assert "2.50 kWh extra reserve" in kandidaat["waarde"]
    assert kandidaat["zou_hebben_opgeleverd"]["aandeel_gunstig_procent"] == 0.0


def test_no_difference_is_reported_as_such(make_coordinator, hass):
    """Ligt het goedkope blok aan het eind van de bekende prijzen, dan
    verandert er niets - en dan hoort er geen extra reserve te staan."""
    c, _ = _coordinator(make_coordinator, hass)
    c.lange_reserve_history = [
        {"extra_kwh": 0.0, "voordeel_eur_per_kwh": 0.0}
        for _ in range(LANGE_RESERVE_MIN_METINGEN)
    ]

    assert c._kandidaat_lange_reserve()["waarde"] == "geen verschil"


def test_it_steers_nothing():
    """Gevraagd: "Eerst als meting." Dezelfde route als de
    slijtagekosten (v1.38.0)."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def _meet_lange_reserve")
    blok = bron[kop : bron.index("\n    def ", kop + 10)]
    code = "\n".join(r.split("#")[0] for r in blok.splitlines())

    for verboden in (
        "_async_apply_operation",
        "last_reason =",
        "self.last_needed_kwh",
        "force_manual",
    ):
        assert verboden not in code, verboden


def test_the_measurement_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "lange_reserve_history" in PERSISTED_PLAIN_FIELDS
