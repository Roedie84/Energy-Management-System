"""Temperatuur-verbruik-regressie voor extreme-koude-dagen (v0.63.88,
uitgebreid besproken en ontworpen door de gebruiker na een analyse van
11 januari 2026 - het koudste etmaal van het jaar). Puur adviserend
("eerst observeren", expliciet zo afgesproken) - stuurt de bestaande
reserve-/dieptekort-berekening nog op geen enkele manier aan.

v1.81.0: de reeks draagt nu GEMIDDELD VERMOGEN in plaats van energie
over het venster. Gemeld met een screenshot: "Voorspeld 0.33 kWh bij
30.3°C, werkelijk 1.92 kWh (afwijking +476.4%)."

Het model voorspelde het totaal over het ontlaadvenster, terwijl de
lengte van dat venster niet in het model zat - de ene nacht drie uur, de
andere veertien. Vermogen is lengte-onafhankelijk.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 1, 11, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "knmi_weather_entity": "weather.knmi",
    }
    config.update(overrides)
    return config


def test_ols_fit_returns_none_with_too_few_points(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert coordinator._ols_fit([1.0], [2.0]) is None


def test_ols_fit_returns_none_with_no_x_variation(make_coordinator, hass):
    """All identical x-values - no line can be fit through them."""
    coordinator = make_coordinator({})

    assert coordinator._ols_fit([5.0, 5.0, 5.0], [1.0, 2.0, 3.0]) is None


def test_ols_fit_correct_for_a_simple_known_line(make_coordinator, hass):
    """y = 2x + 1, exactly - the fit must recover this precisely."""
    coordinator = make_coordinator({})
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [1.0, 3.0, 5.0, 7.0]

    slope, intercept = coordinator._ols_fit(xs, ys)

    assert round(slope, 4) == 2.0
    assert round(intercept, 4) == 1.0


def test_prediction_none_without_enough_history(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.temp_consumption_history = [
        {"temp_c": 5.0, "kw": 0.375, "uren": 8.0},
        {"temp_c": 0.0, "kw": 0.500, "uren": 8.0},
    ]  # fewer than TEMP_CONSUMPTION_MIN_SAMPLES (4)

    assert coordinator._predict_temp_consumption_kw(-5.0) is None


def test_prediction_colder_means_more_expected_consumption(make_coordinator, hass):
    """A clear inverse relationship: colder outdoor temp -> the
    regression must predict higher expected consumption."""
    coordinator = make_coordinator({})
    coordinator.temp_consumption_history = [
        {"temp_c": 10.0, "kw": 0.250, "uren": 8.0},
        {"temp_c": 5.0, "kw": 0.375, "uren": 8.0},
        {"temp_c": 0.0, "kw": 0.500, "uren": 8.0},
        {"temp_c": -5.0, "kw": 0.625, "uren": 8.0},
    ]

    predicted_cold = coordinator._predict_temp_consumption_kw(-10.0)
    predicted_mild = coordinator._predict_temp_consumption_kw(8.0)

    assert predicted_cold > predicted_mild


def test_window_finalization_samples_temperature_and_appends_history(
    make_coordinator, hass
):
    """A completed discharging window with outdoor temperature samples
    must append a (temp, kwh) pair to the learned history."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("weather.knmi", "sunny", {"temperature": -3.0})

    coordinator._window_temp_samples = [-3.0, -4.0, -2.0]
    coordinator._finalize_temp_consumption_regression(
        coordinator._window_temp_samples, window_energy_kwh=6.0, duur_uren=8.0
    )

    assert len(coordinator.temp_consumption_history) == 1
    entry = coordinator.temp_consumption_history[0]
    assert entry["temp_c"] == -3.0  # average of -3, -4, -2
    # v1.81.0: gemiddeld vermogen, niet de energie over het venster.
    assert entry["kw"] == 0.75  # 6,0 kWh over acht uur
    assert entry["uren"] == 8.0


def test_no_temp_samples_does_not_append_history(make_coordinator, hass):
    """Without any outdoor temperature reading during the window, no
    (temp, kwh) pair should be recorded - there's nothing to pair the
    consumption with."""
    coordinator = make_coordinator({})

    coordinator._finalize_temp_consumption_regression(
        [], window_energy_kwh=6.0, duur_uren=8.0
    )

    assert coordinator.temp_consumption_history == []
    assert "Geen buitentemperatuurmeting" in coordinator.last_temp_consumption_note


def test_prediction_error_tracked_using_only_prior_history(make_coordinator, hass):
    """Validation must use the history as it existed BEFORE this
    night's own data point is added - a non-leaky, honest accuracy
    check, not a fit-then-compare-to-itself shortcut."""
    coordinator = make_coordinator({})
    coordinator.temp_consumption_history = [
        {"temp_c": 10.0, "kw": 0.250, "uren": 8.0},
        {"temp_c": 5.0, "kw": 0.375, "uren": 8.0},
        {"temp_c": 0.0, "kw": 0.500, "uren": 8.0},
        {"temp_c": -5.0, "kw": 0.625, "uren": 8.0},
    ]
    # Predicted for -10.0 using the above (slope=-0.2, intercept=4.0):
    # 4.0 + (-0.2 * -10.0) = 6.0 kWh expected.
    coordinator._finalize_temp_consumption_regression(
        temp_samples=[-10.0], window_energy_kwh=6.6, duur_uren=8.0
    )

    assert len(coordinator.temp_consumption_prediction_error_history) == 1
    # (6.6 - 6.0) / 6.0 * 100 = +10.0%
    assert coordinator.temp_consumption_prediction_error_history[0] == 10.0
    # The new night's own pair must now also be part of the history,
    # for FUTURE predictions - but must not have affected THIS
    # validation's prediction.
    assert len(coordinator.temp_consumption_history) == 5


def test_history_capped_at_learning_window(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        LEARNING_HISTORY_DAYS,
    )

    coordinator = make_coordinator({})
    for i in range(LEARNING_HISTORY_DAYS + 3):
        coordinator._finalize_temp_consumption_regression(
            temp_samples=[float(i)], window_energy_kwh=3.0, duur_uren=8.0
        )

    assert len(coordinator.temp_consumption_history) == LEARNING_HISTORY_DAYS


# --- v1.81.0: het venster verschilt per nacht ------------------------


def test_a_short_window_is_not_recorded(make_coordinator, hass):
    """Gemeld met een screenshot: "Voorspeld 0.33 kWh bij 30.3°C,
    werkelijk 1.92 kWh (afwijking +476.4%)."

    Beide metingen van die nacht kwamen uit afgebroken vensters - om
    00:00 en om 06:04, dezelfde nacht. Zo'n stuk zegt niets over het
    nachtverbruik en hoort de reeks niet in.
    """
    coordinator = make_coordinator({})

    coordinator._finalize_temp_consumption_regression(
        temp_samples=[18.5], window_energy_kwh=1.6, duur_uren=0.4
    )

    assert coordinator.temp_consumption_history == []
    assert "te kort" in coordinator.last_temp_consumption_note


def test_two_windows_of_different_length_give_the_same_reading(
    make_coordinator, hass
):
    """De kern van de fout: het model voorspelde het TOTAAL over een
    venster waarvan de lengte er niet in zat. Drie uur en veertien uur
    schelen een factor vijf, en die verklaart de temperatuur niet.

    Op vermogen zijn twee nachten met hetzelfde verbruikspatroon
    identiek, hoe lang het venster ook was.
    """
    coordinator = make_coordinator({})

    coordinator._finalize_temp_consumption_regression(
        temp_samples=[10.0], window_energy_kwh=0.9, duur_uren=3.0
    )
    coordinator._finalize_temp_consumption_regression(
        temp_samples=[10.0], window_energy_kwh=4.2, duur_uren=14.0
    )

    kort, lang = coordinator.temp_consumption_history
    assert kort["kw"] == lang["kw"] == 0.3


def test_old_energy_entries_are_ignored(make_coordinator, hass):
    """Een reeks van vóór deze versie draagt kWh over wisselende
    vensters. Die meerekenen zou een model opleveren dat twee
    grootheden door elkaar haalt."""
    coordinator = make_coordinator({})
    coordinator.temp_consumption_history = [
        {"temp_c": float(t), "kwh": 3.0} for t in range(10)
    ]

    assert coordinator._predict_temp_consumption_kw(5.0) is None


def test_the_note_names_watts_not_kilowatthours(make_coordinator, hass):
    """De melding moet dezelfde grootheid noemen als het model gebruikt,
    anders is de afwijking niet na te rekenen."""
    coordinator = make_coordinator({})
    coordinator.temp_consumption_history = [
        {"temp_c": 20.0, "kw": 0.30, "uren": 8.0},
        {"temp_c": 15.0, "kw": 0.35, "uren": 8.0},
        {"temp_c": 10.0, "kw": 0.40, "uren": 8.0},
        {"temp_c": 5.0, "kw": 0.45, "uren": 8.0},
    ]

    coordinator._finalize_temp_consumption_regression(
        temp_samples=[10.0], window_energy_kwh=3.2, duur_uren=8.0
    )

    assert "W bij" in coordinator.last_temp_consumption_note
    assert "kWh" not in coordinator.last_temp_consumption_note
