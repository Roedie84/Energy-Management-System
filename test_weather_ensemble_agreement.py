"""Weather Ensemble: overeenstemming met de werkelijke PV (v1.0.2).

De adviesmodule meldde "Weather Ensemble — structureel beschikbaar — 2
bron(nen) actief, nauwkeurigheid t.o.v. de werkelijkheid wordt niet
bijgehouden."

"Nauwkeurigheid van de voorspelling" is hier de verkeerde vraag: de
ensemble meldt de ACTUELE bewolking, geen verwachting. De vraag die er
wél toe doet is of die melding klopt met wat de eigen panelen doen — en
dat werd al per moment berekend voor de onenigheids-signalering, alleen
nooit over tijd bijgehouden.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES,
    WEATHER_ENSEMBLE_CLEAR_THRESHOLD_PERCENT,
    WEATHER_ENSEMBLE_OVERCAST_THRESHOLD_PERCENT,
    WEATHER_ENSEMBLE_OVERPERFORM_RATIO,
    WEATHER_ENSEMBLE_UNDERPERFORM_RATIO,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


# --- vastleggen -----------------------------------------------------


def test_clear_sky_with_good_yield_counts_as_agreement(make_coordinator, hass):
    c = make_coordinator({})

    c._record_weather_ensemble_agreement(avg_cloud_pct=5.0, ratio=1.0)

    assert c.weather_ensemble_agreement_history == [True]


def test_clear_sky_with_poor_yield_counts_as_disagreement(
    make_coordinator, hass
):
    """Heldere lucht terwijl de PV fors onderpresteert - precies het
    geval dat op een paneel- of omvormerkwestie kan wijzen."""
    c = make_coordinator({})

    c._record_weather_ensemble_agreement(
        avg_cloud_pct=WEATHER_ENSEMBLE_CLEAR_THRESHOLD_PERCENT - 1,
        ratio=WEATHER_ENSEMBLE_UNDERPERFORM_RATIO - 0.1,
    )

    assert c.weather_ensemble_agreement_history == [False]


def test_overcast_with_high_yield_counts_as_disagreement(
    make_coordinator, hass
):
    c = make_coordinator({})

    c._record_weather_ensemble_agreement(
        avg_cloud_pct=WEATHER_ENSEMBLE_OVERCAST_THRESHOLD_PERCENT + 1,
        ratio=WEATHER_ENSEMBLE_OVERPERFORM_RATIO + 0.1,
    )

    assert c.weather_ensemble_agreement_history == [False]


def test_overcast_with_low_yield_counts_as_agreement(make_coordinator, hass):
    """Bewolkt én weinig opbrengst is juist consistent."""
    c = make_coordinator({})

    c._record_weather_ensemble_agreement(avg_cloud_pct=95.0, ratio=0.3)

    assert c.weather_ensemble_agreement_history == [True]


def test_middle_ground_counts_as_agreement(make_coordinator, hass):
    """Half bewolkt met een middelmatige opbrengst spreekt elkaar niet
    tegen; alleen de twee uitgesproken tegenstellingen tellen als
    oneens."""
    c = make_coordinator({})

    c._record_weather_ensemble_agreement(avg_cloud_pct=50.0, ratio=0.7)

    assert c.weather_ensemble_agreement_history == [True]


def test_history_is_bounded(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        WEATHER_ENSEMBLE_AGREEMENT_HISTORY_LENGTH,
    )

    c = make_coordinator({})
    for _ in range(WEATHER_ENSEMBLE_AGREEMENT_HISTORY_LENGTH + 50):
        c._record_weather_ensemble_agreement(avg_cloud_pct=50.0, ratio=0.7)

    assert len(c.weather_ensemble_agreement_history) == (
        WEATHER_ENSEMBLE_AGREEMENT_HISTORY_LENGTH
    )


# --- oordeel --------------------------------------------------------


def _vul(c, eens, oneens):
    c.weather_ensemble_agreement_history = [True] * eens + [False] * oneens


def test_no_verdict_below_the_minimum(make_coordinator, hass):
    c = make_coordinator({})
    _vul(c, WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES - 1, 0)

    assert c.weather_ensemble_agreement_percent is None
    assert c.get_weather_ensemble_agreement_status()["status"] == (
        "onvoldoende_data"
    )


def test_high_agreement_is_ready(make_coordinator, hass):
    c = make_coordinator({})
    _vul(c, 19, 1)

    status = c.get_weather_ensemble_agreement_status()

    assert c.weather_ensemble_agreement_percent == 95.0
    assert status["status"] == "klaar"


def test_middling_agreement_is_almost_ready(make_coordinator, hass):
    c = make_coordinator({})
    _vul(c, 14, 6)

    assert c.get_weather_ensemble_agreement_status()["status"] == "bijna_klaar"


def test_low_agreement_is_flagged(make_coordinator, hass):
    """Slaan de bronnen er structureel naast, dan hoort dat te blijken -
    niet verstopt achter "structureel beschikbaar"."""
    c = make_coordinator({})
    _vul(c, 5, 15)

    assert c.get_weather_ensemble_agreement_status()["status"] == (
        "kwaliteit_te_laag"
    )


# --- inbedding ------------------------------------------------------


def test_readiness_uses_the_measurement(make_coordinator, hass):
    c = make_coordinator({})
    c.weather_ensemble_sources_used = ["weather.knmi", "weather.owm"]
    _vul(c, 19, 1)

    c._update_advisory_readiness(NOW)
    entry = c.advisory_readiness["weather_ensemble"]

    assert entry["status"] == "klaar"
    assert "2 bron(nen)" in entry["reden"]
    assert "niet bijgehouden" not in entry["reden"]


def test_recording_reuses_the_disagreement_thresholds(make_coordinator, hass):
    """De meting en de bestaande onenigheids-signalering moeten dezelfde
    definitie gebruiken - twee losse berekeningen zouden uit de pas
    kunnen gaan lopen en tegenstrijdige dingen beweren."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    functie = bron[bron.index("def _record_weather_ensemble_agreement") :][:1600]

    for drempel in (
        "WEATHER_ENSEMBLE_UNDERPERFORM_RATIO",
        "WEATHER_ENSEMBLE_CLEAR_THRESHOLD_PERCENT",
        "WEATHER_ENSEMBLE_OVERPERFORM_RATIO",
        "WEATHER_ENSEMBLE_OVERCAST_THRESHOLD_PERCENT",
    ):
        assert drempel in functie


def test_agreement_survives_a_restart(make_coordinator, hass):
    """Er zijn twintig waarnemingen BIJ DAGLICHT nodig; zonder herstel
    zou elke herstart die telling terugzetten."""
    import asyncio

    from custom_components.energy_management_system.sensor import (
        WeatherEnsembleSensor,
    )

    bron = make_coordinator({})
    _vul(bron, 18, 2)
    attrs = WeatherEnsembleSensor(bron, "entry1").extra_state_attributes

    class _Vorige:
        attributes = attrs

    verse = make_coordinator({})
    sensor = WeatherEnsembleSensor(verse, "entry1")

    async def get_last_state():
        return _Vorige()

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert len(verse.weather_ensemble_agreement_history) == 20
    assert verse.weather_ensemble_agreement_percent == 90.0
