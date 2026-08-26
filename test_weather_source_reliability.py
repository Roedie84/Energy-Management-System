"""Betrouwbaarheid per weerbron (v1.5.2).

Gerapporteerd: "Weerbronnen lopen 70 procentpunt uiteen over de
bewolking (weather.forecast_thuis: 12%, weather.openweathermap: 83%)...
Openweathermap lijkt het bij het juiste eind te hebben."

Het gemiddelde meten zegt niets over WELKE bron deugt. Bij zo'n
spreiding is precies dat de vraag.

Gevraagd bij het bouwen: "Ik neem aan dat je het meeneemt in je
diagnostiek file? Gezien het nu op 1 dag natuurlijk niet betrouwbaar
is." Dus: meten, en pas oordelen als er genoeg is.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_KNMI_WEATHER_ENTITY,
    CONF_OPENWEATHERMAP_WEATHER_ENTITY,
    RELIABILITY_INSUFFICIENT,
    RELIABILITY_RELIABLE,
    RELIABILITY_UNRELIABLE,
    WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES,
)

NOW = datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)
METNO = "weather.forecast_thuis"
OWM = "weather.openweathermap"


def _config():
    return {
        CONF_KNMI_WEATHER_ENTITY: METNO,
        CONF_OPENWEATHERMAP_WEATHER_ENTITY: OWM,
    }


def _weer(hass, entity_id, bewolking):
    hass.states.set(entity_id, "cloudy", {"cloud_coverage": bewolking})


def _waarneming(c, hass, metno_pct, owm_pct, ratio):
    """Eén meetmoment: beide bronnen melden iets, de panelen doen iets."""
    _weer(hass, METNO, metno_pct)
    _weer(hass, OWM, owm_pct)
    c._update_weather_ensemble_check(NOW)
    c._record_weather_ensemble_agreement(
        (metno_pct + owm_pct) / 2, ratio
    )


# --- meten per bron --------------------------------------------------


def test_each_source_is_judged_separately(make_coordinator, hass):
    """De kern: de gerapporteerde situatie. met.no meldt heldere lucht
    terwijl de panelen fors onderpresteren; OpenWeatherMap meldt terecht
    zware bewolking."""
    c = make_coordinator(_config())

    for _ in range(WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES + 5):
        _waarneming(c, hass, metno_pct=12, owm_pct=83, ratio=0.2)

    rapport = c.get_weather_source_reliability()

    assert rapport[METNO]["status"] == RELIABILITY_UNRELIABLE
    assert rapport[OWM]["status"] == RELIABILITY_RELIABLE


def test_no_verdict_on_a_single_day(make_coordinator, hass):
    """Uitdrukkelijk gevraagd: één dag zegt niets."""
    c = make_coordinator(_config())

    for _ in range(3):
        _waarneming(c, hass, metno_pct=12, owm_pct=83, ratio=0.2)

    rapport = c.get_weather_source_reliability()

    assert rapport[METNO]["status"] == RELIABILITY_INSUFFICIENT
    assert rapport[METNO]["overeenstemming_percent"] is None


def test_both_good_sources_are_both_reliable(make_coordinator, hass):
    c = make_coordinator(_config())

    for _ in range(WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES + 5):
        _waarneming(c, hass, metno_pct=85, owm_pct=88, ratio=0.2)

    rapport = c.get_weather_source_reliability()

    assert rapport[METNO]["status"] == RELIABILITY_RELIABLE
    assert rapport[OWM]["status"] == RELIABILITY_RELIABLE


def test_the_same_thresholds_are_used_as_for_the_ensemble():
    """Twee definities naast elkaar zouden tegenstrijdige uitkomsten
    kunnen geven over dezelfde waarneming."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("def _record_weather_ensemble_agreement")
    blok = bron[start : start + 3000]

    assert blok.count("WEATHER_ENSEMBLE_UNDERPERFORM_RATIO") >= 2
    assert blok.count("WEATHER_ENSEMBLE_OVERCAST_THRESHOLD_PERCENT") >= 2


# --- vergelijken -----------------------------------------------------


def test_a_clearly_better_source_is_named(make_coordinator, hass):
    c = make_coordinator(_config())

    for _ in range(WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES + 5):
        _waarneming(c, hass, metno_pct=12, owm_pct=83, ratio=0.2)

    vergelijking = c.get_weather_source_reliability()["_vergelijking"]

    assert vergelijking["beste_bron"] == OWM
    assert vergelijking["slechtste_bron"] == METNO
    assert "uit de configuratie" in vergelijking["advies"]


def test_comparable_sources_get_no_advice(make_coordinator, hass):
    c = make_coordinator(_config())

    for _ in range(WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES + 5):
        _waarneming(c, hass, metno_pct=85, owm_pct=88, ratio=0.2)

    vergelijking = c.get_weather_source_reliability()["_vergelijking"]

    assert "vergelijkbaar" in vergelijking["advies"]


def test_no_comparison_until_both_have_enough(make_coordinator, hass):
    """Anders zou een bron met drie waarnemingen "de beste" kunnen
    heten."""
    c = make_coordinator(_config())

    for _ in range(4):
        _waarneming(c, hass, metno_pct=12, owm_pct=83, ratio=0.2)

    assert "_vergelijking" not in c.get_weather_source_reliability()


def test_it_is_informational_not_an_attention_point(make_coordinator, hass):
    """Een matige weerbron is geen storing van deze integratie."""
    c = make_coordinator(_config())

    for _ in range(WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES + 5):
        _waarneming(c, hass, metno_pct=12, owm_pct=83, ratio=0.2)

    samenvatting = c.get_diagnostic_summary()

    assert any(
        "structureel in betrouwbaarheid" in p for p in samenvatting["informatief"]
    )
    assert not any(
        "structureel in betrouwbaarheid" in p
        for p in samenvatting["aandachtspunten"]
    )


# --- inbedding -------------------------------------------------------


def test_nothing_is_weighted_automatically(make_coordinator, hass):
    """Bewust meten en niet meteen wegen: een bron die deze week beter
    is kan volgende week slechter zijn. Het gemiddelde blijft dus een
    ongewogen gemiddelde."""
    c = make_coordinator(_config())

    for _ in range(WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES + 5):
        _waarneming(c, hass, metno_pct=12, owm_pct=83, ratio=0.2)

    assert c.weather_ensemble_cloud_cover_percent == 47.5


def test_each_source_appears_in_the_reliability_overview(
    make_coordinator, hass
):
    c = make_coordinator(_config())
    for _ in range(WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES + 5):
        _waarneming(c, hass, metno_pct=12, owm_pct=83, ratio=0.2)

    namen = {r["naam"] for r in c.get_reliability_overview()}

    assert f"Weerbron {METNO}" in namen
    assert f"Weerbron {OWM}" in namen


def test_the_measurement_survives_a_restart(make_coordinator, hass):
    """Twintig waarnemingen bij daglicht per bron - zonder bewaren zou
    die telling na elke herstart opnieuw beginnen."""
    import asyncio

    bron = make_coordinator(_config())
    bron.weather_source_agreement = {METNO: [False] * 10, OWM: [True] * 10}
    asyncio.run(bron.async_save_persisted_state_now())

    verse = make_coordinator(_config())
    asyncio.run(verse.async_load_persisted_state())

    assert len(verse.weather_source_agreement[METNO]) == 10
    assert verse.weather_source_agreement[OWM] == [True] * 10
