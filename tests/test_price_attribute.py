"""Klopt het prijsattribuut - zit de belasting erin? (v1.37.0)

Gevraagd: "Neem je alles gerelateerd aan de kwartier prijzen van
zonneplan mee incl tax/btw?"

Ja: overal `price_tax_included`, en het kale `price_tax_excluded` alleen
voor het teruglevertarief NA de saldering. Maar dat was een antwoord uit
de code, geen meting.

Zonneplan levert zelf de gemiddelde afnameprijs van vandaag. Die stond
al in de export als gevonden entiteit en werd nergens gebruikt.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_PRICE_ATTRIBUTE,
    PRICE_ATTRIBUTE_EXCL_TAX,
    PRICE_ATTRIBUTE_INCL_TAX,
    PRICE_SCALE_FACTOR,
    RELIABILITY_INSUFFICIENT,
    RELIABILITY_RELIABLE,
    RELIABILITY_UNRELIABLE,
)

NU = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, gemiddelde="0.29"):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    # De prijzen van vandaag tot nu toe: 13 tot 38 ct.
    entries = []
    # Tot 15:00, zodat er ook een kwartier is dat NU bevat.
    for i in range(60):
        start = NU.replace(hour=0, minute=0) + timedelta(minutes=15 * i)
        prijs = (0.131 if 10 <= start.hour < 17 else 0.38) * PRICE_SCALE_FACTOR
        entries.append((start, start + timedelta(minutes=15), prijs))
    c._get_forecast_entries = lambda *a, **k: entries
    c.find_zonneplan_cost_entities = lambda: {
        "gemiddelde_afnameprijs_vandaag": "sensor.zp_gemiddeld"
    }
    if gemiddelde is not None:
        hass.states.set("sensor.zp_gemiddeld", gemiddelde)
    return c


def test_a_price_inside_the_range_confirms_the_attribute(
    make_coordinator, hass
):
    """Zonneplan weegt naar werkelijk verbruik, dus hun gemiddelde hoort
    ergens tussen de laagste en hoogste prijs van vandaag te liggen."""
    c = _coordinator(make_coordinator, hass, gemiddelde="0.29")

    toets = c.get_price_attribute_check()

    assert toets["status"] == RELIABILITY_RELIABLE
    assert toets["inclusief_belasting"] is True


def test_a_price_far_below_the_range_is_flagged(make_coordinator, hass):
    """Het kale markttarief ligt ver onder de prijs inclusief
    energiebelasting en BTW. Valt het gemiddelde daar, dan wordt er een
    ander veld gelezen dan waarvoor betaald wordt."""
    c = _coordinator(make_coordinator, hass, gemiddelde="0.06")

    toets = c.get_price_attribute_check()

    assert toets["status"] == RELIABILITY_UNRELIABLE
    assert "buiten" in toets["reden"]


def test_the_wrong_attribute_is_caught_before_measuring(
    make_coordinator, hass
):
    """Staat het attribuut zelf al verkeerd, dan hoeft er niets gemeten
    te worden - dan valt elke drempel, reserve en opbrengst te laag
    uit."""
    c = _coordinator(make_coordinator, hass)
    c.config[CONF_PRICE_ATTRIBUTE] = PRICE_ATTRIBUTE_EXCL_TAX

    toets = c.get_price_attribute_check()

    assert toets["status"] == RELIABILITY_UNRELIABLE
    assert toets["inclusief_belasting"] is False


def test_without_the_zonneplan_sensor_it_says_so(make_coordinator, hass):
    """Die kostensensoren staan in Home Assistant standaard uit; dan valt
    er niets te toetsen en hoort dat er te staan."""
    c = _coordinator(make_coordinator, hass, gemiddelde=None)
    c.find_zonneplan_cost_entities = lambda: {}

    toets = c.get_price_attribute_check()

    assert toets["status"] == RELIABILITY_INSUFFICIENT


def test_the_default_is_including_tax():
    from custom_components.energy_management_system.const import (
        DEFAULT_PRICE_ATTRIBUTE,
    )

    assert DEFAULT_PRICE_ATTRIBUTE == PRICE_ATTRIBUTE_INCL_TAX


def test_only_the_feedin_may_use_the_bare_market_price():
    """Het kale tarief hoort maar op één plek te worden gebruikt: het
    teruglevertarief na de saldering. Overal elders betaal je belasting
    en BTW, dus overal elders hoort de prijs inclusief te zijn.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    regels = [
        r
        for r in bron.splitlines()
        if "price_key_override=" in r and not r.strip().startswith("#")
    ]

    # v1.37.1: twee plekken, allebei over de teruglevering - de
    # berekening zelf en de vooruitblik die nakijkt of dat veld er
    # überhaupt is voordat 1 januari aanbreekt.
    #
    # v1.75.0: een derde, en ook die gaat over de teruglevering: het
    # gemeten verschil tussen belast en kaal, waarmee de doorrekening
    # van na de saldering exact wordt in plaats van geschat.
    assert len(regels) == 3
    assert all("veld" in r or "feedin" in r for r in regels)


# --- v1.37.1: de dag ná de saldering ---------------------------------


def _met_kaal_tarief(make_coordinator, hass, kaal=0.06):
    """Een prijssensor die beide velden levert, zoals Zonneplan doet."""
    c = _coordinator(make_coordinator, hass)
    belast = c._get_forecast_entries()

    def _entries(price_key_override=None):
        if price_key_override == PRICE_ATTRIBUTE_EXCL_TAX:
            return [
                (start, einde, kaal * PRICE_SCALE_FACTOR)
                for start, einde, _prijs in belast
            ]
        return belast

    c._get_forecast_entries = _entries
    return c


def test_the_bare_rate_is_checked_before_january(make_coordinator, hass):
    """Gevraagd: "Wanneer salderen wordt afgeschaft (na 31-12-2026) geldt
    de export prijs zonder tax/btw als ik het goed heb."

    Klopt. Maar dat leunt op een veld dat vandaag nergens voor wordt
    gebruikt; ontbreekt het, dan valt de terugleverwaarde op 1 januari
    stil en sta je op de slechtst denkbare dag te zoeken.
    """
    c = _met_kaal_tarief(make_coordinator, hass)

    toets = c.get_price_attribute_check()

    assert toets["teruglever_veld"] == PRICE_ATTRIBUTE_EXCL_TAX
    assert toets["kale_prijs_nu_eur_per_kwh"] == 0.06
    assert "aanwezig en leesbaar" in toets["teruglevering_na_saldering"]


def test_a_missing_bare_rate_is_reported(make_coordinator, hass):
    """Zolang salderen geldt merk je er niets van - juist daarom moet het
    nu al opvallen."""
    c = _coordinator(make_coordinator, hass)
    belast = c._get_forecast_entries()
    c._get_forecast_entries = lambda price_key_override=None: (
        [] if price_key_override else belast
    )

    toets = c.get_price_attribute_check()

    assert "zit niet in deze prijssensor" in toets["teruglevering_na_saldering"]


def test_a_bare_rate_that_is_not_lower_is_suspicious(make_coordinator, hass):
    """Een tarief zonder energiebelasting en BTW kan niet hoger zijn dan
    de belaste prijs."""
    c = _met_kaal_tarief(make_coordinator, hass, kaal=0.45)

    toets = c.get_price_attribute_check()

    assert "niet lager" in toets["teruglevering_na_saldering"]


def test_the_switch_follows_the_configured_date(make_coordinator, hass):
    """De datum is instelbaar en niet ingebakken: politiek uitstel is in
    het verleden al meermaals voorgekomen."""
    from custom_components.energy_management_system.const import (
        CONF_SALDEREN_END_DATE,
    )

    c = _met_kaal_tarief(make_coordinator, hass)
    c.config[CONF_SALDEREN_END_DATE] = "2026-12-31"
    assert c.get_price_attribute_check()["salderen_actief"] is True

    c.config[CONF_SALDEREN_END_DATE] = "2026-08-01"
    assert c.get_price_attribute_check()["salderen_actief"] is False
