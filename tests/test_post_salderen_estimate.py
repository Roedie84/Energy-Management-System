"""Wat de saldering kost, gemeten in plaats van geschat (v1.75.0).

Gevraagd: "Kun je dat nu bekijken? Saldering is als bekend nu nog
actief, en stopt na 31-12-2026."

De eerste schatting nam aan dat het kale tarief een vast DEEL van de
belaste prijs is (23%). Dat klopt niet: energiebelasting plus BTW is een
vast BEDRAG per kWh. Daardoor stond er "€ 0,61 in plaats van € 3,90" -
een daling van 84%, terwijl het met de gemeten cijfers 35% is.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    PRICE_ATTRIBUTE_EXCL_TAX,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 8, 13, 9, 30, tzinfo=timezone.utc)
BELASTINGDEEL = 0.1108  # gemeten bij deze aansluiting


def _coordinator(make_coordinator, hass):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})

    def _entries(price_key_override=None):
        regels = []
        for i in range(96):
            start = NU.replace(hour=0, minute=0) + timedelta(minutes=15 * i)
            belast = 0.13 if 10 <= start.hour < 16 else 0.30
            prijs = (
                max(0.0, belast - BELASTINGDEEL)
                if price_key_override == PRICE_ATTRIBUTE_EXCL_TAX
                else belast
            )
            regels.append(
                (start, start + timedelta(minutes=15), prijs * PRICE_SCALE_FACTOR)
            )
        return regels

    c._get_forecast_entries = _entries
    return c


def test_the_tax_component_is_measured(make_coordinator, hass):
    """Het verschil tussen de belaste en de kale prijs uit dezelfde
    sensor - een vast bedrag, geen percentage."""
    c = _coordinator(make_coordinator, hass)

    assert round(c._gemeten_belastingdeel_eur_per_kwh(), 4) == BELASTINGDEEL


def test_the_share_is_not_constant(make_coordinator, hass):
    """De kern van de fout: bij 30 ct belast is kaal 19 ct (63%), bij 13
    ct is kaal 1,9 ct (15%). Eén breuk kan dat niet vangen."""
    deel = BELASTINGDEEL

    assert round((0.30 - deel) / 0.30, 2) == 0.63
    assert round((0.13 - deel) / 0.13, 2) == 0.15


def test_the_estimate_uses_the_measured_amount(make_coordinator, hass):
    """Met het gemeten bedrag komt de doorrekening uit op een realistisch
    verschil in plaats van een daling van 84%."""
    c = _coordinator(make_coordinator, hass)
    c.get_quarter_plan = lambda *a, **k: [
        {
            "net_kwh": -1.0,
            "prijs_ct": 30.0,
            "cumulatief_eur": 4.16,
            "zon_kwh": 1.0,
            "verbruik_kwh": 0.1,
        }
        for _ in range(13)
    ]

    kandidaat = c._kandidaat_na_saldering()

    assert "gemeten" in kandidaat["betrouwbaarheid"].lower()
    assert "11.1" in kandidaat["betrouwbaarheid"]


def test_without_the_bare_field_it_says_so(make_coordinator, hass):
    """Levert het kale veld niets, dan mag er geen exact getal worden
    voorgewend."""
    c = _coordinator(make_coordinator, hass)
    alles = c._get_forecast_entries()
    c._get_forecast_entries = lambda price_key_override=None: (
        [] if price_key_override else alles
    )

    assert c._gemeten_belastingdeel_eur_per_kwh() == 0.0


def test_a_negative_difference_is_ignored(make_coordinator, hass):
    """Een kwartier waarin het kale veld hoger staat dan het belaste is
    onzin en mag de mediaan niet verslepen."""
    c = _coordinator(make_coordinator, hass)
    alles = c._get_forecast_entries()

    def _entries(price_key_override=None):
        if price_key_override != PRICE_ATTRIBUTE_EXCL_TAX:
            return alles
        kaal = c._get_forecast_entries.__wrapped__(price_key_override) if False else None
        return [
            (b, e, p * 2 if i == 0 else max(0.0, p - BELASTINGDEEL * PRICE_SCALE_FACTOR))
            for i, (b, e, p) in enumerate(alles)
        ]

    c._get_forecast_entries = _entries

    # De uitschieter telt niet mee; de rest geeft nog steeds het juiste
    # bedrag.
    assert round(c._gemeten_belastingdeel_eur_per_kwh(), 4) == BELASTINGDEEL
