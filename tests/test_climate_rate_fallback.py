"""Indicatieve klimaatreeks bevroor maandenlang (v1.1.2).

Gevraagd: "Maar korte termijn zou toch op relatief korte termijn een
indicatie geven?"

Terecht. "Indicatief" belooft juist snel iets, en dat gebeurde niet. De
celruimte is buitentemperatuur x rolluikstand x airco-status = 252
mogelijke cellen. In een echte export hadden er na vijf dagen zes enige
data en haalde er precies één de drempel van vijf metingen - terwijl de
projectie 24 uur vooruit loopt langs telkens een ander
buitentemperatuur-vakje. Vrijwel elk uur viel dus terug op "bevriezen".

De strenge reeks blijft ongewijzigd; dat is haar bestaansreden. De
indicatieve reeks valt nu terug op een grovere samenvatting.
"""
from custom_components.energy_management_system.const import (
    CLIMATE_RATE_MIN_SAMPLES,
    CLIMATE_RATE_RELIABLE_SAMPLES,
)


def _cel(c, bucket, rolluik, airco, waarden):
    """v3.47.0: sleutels dragen sinds v3.41.0 het VERSCHIL met binnen en

    beginnen met een `d`. De toetsen hier gebruikten nog de oude vorm op
    buitentemperatuur, en die valt sinds de nieuwe bereiktoets buiten de
    gemeten reeks.
    """
    if not str(bucket).startswith("d"):
        bucket = f"d{bucket}"
    c.climate_rate_history[f"{bucket}|{rolluik}|{airco}"] = list(waarden)


# --- de strenge reeks blijft streng ---------------------------------


def test_the_strict_series_is_unchanged(make_coordinator, hass):
    """De belangrijkste borging: "betrouwbaar" mag nooit op een
    samenvatting rusten."""
    c = make_coordinator({})
    _cel(c, "2.0", "beide_dicht", "uit", [-0.2] * CLIMATE_RATE_RELIABLE_SAMPLES)

    ander = c.get_climate_rate("d20.0", "beide_open", "aan")

    assert ander["betrouwbaarheid"] == "onvoldoende_data"
    assert ander["rate_c_per_hour"] is None


# --- terugval van de indicatieve reeks ------------------------------


def test_an_exact_cell_wins(make_coordinator, hass):
    c = make_coordinator({})
    _cel(c, "2.0", "beide_dicht", "uit", [-0.2] * CLIMATE_RATE_MIN_SAMPLES)

    resultaat = c.get_climate_rate_indicative("d2.0", "beide_dicht", "uit")

    assert resultaat["basis"] == "exact"
    assert resultaat["rate_c_per_hour"] == -0.2


def test_it_falls_back_to_a_neighbouring_bucket(make_coordinator, hass):
    """Twee graden verschil buiten weegt minder zwaar dan een andere
    rolluikstand, dus dit gaat vóór de bucket-brede samenvatting."""
    c = make_coordinator({})
    _cel(c, "0.0", "beide_dicht", "uit", [-0.3] * CLIMATE_RATE_MIN_SAMPLES)

    resultaat = c.get_climate_rate_indicative("d2.0", "beide_dicht", "uit")

    assert resultaat["basis"] == "naburige_buitentemperatuur"
    assert resultaat["rate_c_per_hour"] == -0.3
    assert resultaat["betrouwbaarheid"] == "indicatief"


def test_neighbours_are_preferred_over_the_same_bucket(make_coordinator, hass):
    """Expliciet: de rolluikstand bepaalt hoeveel zon er binnenvalt en
    heeft daarmee meer invloed dan twee graden buiten."""
    c = make_coordinator({})
    _cel(c, "0.0", "beide_dicht", "uit", [-0.3] * CLIMATE_RATE_MIN_SAMPLES)
    _cel(c, "2.0", "beide_open", "aan", [-9.9] * CLIMATE_RATE_MIN_SAMPLES)

    resultaat = c.get_climate_rate_indicative("d2.0", "beide_dicht", "uit")

    assert resultaat["basis"] == "naburige_buitentemperatuur"


def test_it_falls_back_to_the_same_bucket_any_state(make_coordinator, hass):
    c = make_coordinator({})
    _cel(c, "2.0", "beide_open", "aan", [-0.4] * CLIMATE_RATE_MIN_SAMPLES)

    resultaat = c.get_climate_rate_indicative("d2.0", "beide_dicht", "uit")

    assert resultaat["basis"] == "zelfde_buitentemperatuur"


def test_it_falls_back_to_everything(make_coordinator, hass):
    """Binnen bereik mag de brede samenvatting; net buiten het gemeten

    vakje is dat nog verdedigbaar.
    """
    c = make_coordinator({})
    _cel(c, "2.0", "beide_dicht", "uit", [-0.2] * CLIMATE_RATE_MIN_SAMPLES)

    resultaat = c.get_climate_rate_indicative("d4.0", "beide_open", "aan")

    assert resultaat["basis"] == "algemeen"
    assert resultaat["rate_c_per_hour"] == -0.2


def test_far_outside_the_measured_range_it_says_nothing(
    make_coordinator, hass
):
    """Gemeld met een schermafdruk van de klimaattabel (v3.47.0): vanaf

    11:00 stond overal `algemeen` met nul metingen, en de voorspelde
    binnentemperatuur zakte van 21,3 naar 20,9 terwijl het buiten naar
    31 graden liep - een verschil van +10 met binnen, waar geen enkele
    cel voor bestond.

    `algemeen` neemt de mediaan over ALLE cellen, en die zijn overwegend
    nachtcellen met dichte rolluiken die afkoelen. Dat gemiddelde werd
    losgelaten op een middag waarin buiten tien graden boven binnen
    staat.

    Een projectie die zegt "het koelt af terwijl het buiten tien graden
    warmer is" is erger dan geen projectie: hij oogt geloofwaardig en
    klopt niet.
    """
    c = make_coordinator({})
    _cel(c, "-6.0", "beide_dicht", "uit", [-0.2] * CLIMATE_RATE_MIN_SAMPLES)

    resultaat = c.get_climate_rate_indicative("d10.0", "beide_open", "aan")

    assert resultaat["basis"] == "buiten_bereik"
    assert resultaat["rate_c_per_hour"] is None
    assert "buiten de gemeten reeks" in resultaat["toelichting"]


def test_with_no_data_at_all_it_says_so(make_coordinator, hass):
    """Zonder enige meting mag er niets verzonnen worden - dan hoort de
    reeks wél te bevriezen."""
    c = make_coordinator({})

    resultaat = c.get_climate_rate_indicative("d2.0", "beide_dicht", "uit")

    assert resultaat["basis"] == "geen"
    assert resultaat["voldoende_data"] is False
    assert resultaat["rate_c_per_hour"] is None


def test_too_few_samples_in_total_is_still_not_enough(make_coordinator, hass):
    """De drempel van vijf metingen geldt ook voor de samenvatting -
    terugvallen mag geen sluiproute worden om die te omzeilen."""
    c = make_coordinator({})
    _cel(c, "2.0", "beide_dicht", "uit", [-0.2] * (CLIMATE_RATE_MIN_SAMPLES - 1))

    resultaat = c.get_climate_rate_indicative("d4.0", "beide_open", "aan")

    assert resultaat["voldoende_data"] is False


def test_scattered_cells_add_up(make_coordinator, hass):
    """Precies de situatie in de praktijk: zes cellen met een of twee
    metingen. Los is dat te weinig, samen genoeg voor een indicatie."""
    c = make_coordinator({})
    for bucket in ("-4.0", "-2.0", "0.0", "2.0", "4.0"):
        _cel(c, bucket, "beide_dicht", "uit", [-0.2])

    resultaat = c.get_climate_rate_indicative("d6.0", "beide_open", "aan")

    assert resultaat["voldoende_data"] is True
    assert resultaat["sample_count"] == 5


# --- de projectie zelf ----------------------------------------------


def test_the_projection_no_longer_freezes(make_coordinator, hass):
    """Waar het uiteindelijk om gaat: de korte-termijnreeks beweegt, de
    betrouwbare blijft bevroren tot ze het echt weet."""
    from datetime import datetime, timedelta, timezone

    c = make_coordinator({})
    now = datetime(2026, 8, 6, 15, 0, tzinfo=timezone.utc)
    c.living_room_current_temp_c = 24.3
    c.climate_shutter_state = "beide_dicht"
    c.climate_airco_state = "uit"
    _cel(c, "2.0", "beide_dicht", "uit", [-0.2] * CLIMATE_RATE_MIN_SAMPLES)
    c._climate_cached_forecast = [
        (now + timedelta(hours=u), 26.0) for u in range(1, 5)
    ]

    c._recompute_climate_trajectory(now)
    traject = c.climate_forecast_trajectory

    assert len(traject) == 4
    # Korte termijn daalt mee; betrouwbaar blijft op de startwaarde.
    assert traject[-1]["kort_termijn_temp_c"] < 24.3
    assert traject[-1]["betrouwbaar_temp_c"] == 24.3
    # v3.47.0: buiten 26 en binnen 24,3 is een verschil van +1,7 - dat
    # valt in vakje d2.0, en dat is precies de cel die hierboven is
    # gevuld. Vóór de sleutelwijziging van v3.41.0 sleutelde deze cel op
    # de buitentemperatuur en viel hij door naar `algemeen`.
    assert traject[0]["basis"] == "exact"
