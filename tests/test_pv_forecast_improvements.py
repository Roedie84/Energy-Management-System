"""De zonvoorspelling verbeteren (v2.4.0).

Gevraagd: "Kun je diepgaand uitzoeken hoe we de PV voorspelling beter
kunnen maken? Het is namelijk 1 van de belangrijkste zaken."

De gemeten cijfers wezen een andere kant op dan verwacht:

    mediane fout      2,7%
    gemiddelde fout  10,8%
    slechtste dag    41,6%

De meeste dagen kloppen dus prima en een paar zitten er volledig naast.
Een betere gemiddelde correctie helpt daar niet - die maakt de goede
dagen slechter zonder de slechte te redden.
"""
from custom_components.energy_management_system.const import (
    CONF_SOLAR_TODAY_FORECAST_SENSOR,
    PV_HOURLY_BIAS_MAX_RATIO,
    PV_HOURLY_BIAS_MIN_KWH,
    PV_HOURLY_BIAS_MIN_RATIO,
)


# --- 1. Verhoudingen uit te kleine getallen ---------------------------


def test_a_tiny_hour_teaches_nothing():
    """De drempel stond op 0,01 kWh - tien wattuur. Een verhouding uit
    zulke getallen is ruis: 0,02 gedeeld door 0,06 geeft 0,33, terwijl
    de absolute fout 0,04 kWh is."""
    assert PV_HOURLY_BIAS_MIN_KWH >= 0.05

    # Het gemeten geval: 0,06 kWh voorspeld haalt de drempel niet.
    assert 0.06 < PV_HOURLY_BIAS_MIN_KWH


def test_the_learning_uses_the_threshold():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def _finalize_pv_hourly_bucket")
    blok = bron[kop : kop + 2500]

    assert "PV_HOURLY_BIAS_MIN_KWH" in blok
    assert "forecast_kwh > 0.01" not in blok


def test_implausible_ratios_are_cleaned_up(make_coordinator, hass):
    """De reeksen die er al staan zijn met de oude drempel gevuld.
    Zonder opruiming duurt het veertien dagen voordat de reparatie
    doorwerkt.

    Het gemeten profiel: 6h op 0,334 en 20h op 0,226 - die horen eruit.
    """
    c = make_coordinator({})
    c.pv_hourly_bias_history = {
        6: [0.334, 0.95, 1.02],
        20: [0.226, 0.98],
        12: [0.92, 0.95, 0.93],
    }

    c._ruim_pv_uurbias_op()

    assert c.pv_hourly_bias_history[6] == [0.95, 1.02]
    assert c.pv_hourly_bias_history[20] == [0.98]
    assert c.pv_hourly_bias_history[12] == [0.92, 0.95, 0.93]


def test_a_real_forecast_error_is_kept(make_coordinator, hass):
    """De opruiming mag geen echte voorspelfouten weggooien - een uur dat
    twintig procent afwijkt is gewoon informatie."""
    c = make_coordinator({})
    c.pv_hourly_bias_history = {13: [0.80, 1.20, 1.05]}

    c._ruim_pv_uurbias_op()

    assert c.pv_hourly_bias_history[13] == [0.80, 1.20, 1.05]


def test_the_cleanup_bounds_are_wide_enough():
    """Te streng zou echte seizoensdrift wegsnijden."""
    assert PV_HOURLY_BIAS_MIN_RATIO <= 0.5
    assert PV_HOURLY_BIAS_MAX_RATIO >= 2.0


# --- 2. De onzekerheid van de dag ------------------------------------


def _met_spreiding(make_coordinator, hass, p10, p90, verwacht):
    """v2.5.0: de percentielen staan als ATTRIBUTEN op de bestaande
    voorspellingssensor, niet in losse entiteiten. Die bestaan niet bij
    Solcast."""
    c = make_coordinator(
        {CONF_SOLAR_TODAY_FORECAST_SENSOR: "sensor.solcast_vandaag"}
    )
    hass.states.set(
        "sensor.solcast_vandaag",
        str(verwacht),
        {"estimate": verwacht, "estimate10": p10, "estimate90": p90},
    )
    return c


def test_a_wide_band_marks_the_day_uncertain(make_coordinator, hass):
    """Wisselende bewolking: p10 en p90 ver uit elkaar."""
    c = _met_spreiding(make_coordinator, hass, 8.0, 24.0, 20.0)

    uitkomst = c.get_pv_forecast_spread()

    assert uitkomst["onzeker"] is True
    assert uitkomst["relatieve_breedte"] == 0.8


def test_a_narrow_band_is_a_predictable_day(make_coordinator, hass):
    c = _met_spreiding(make_coordinator, hass, 19.0, 22.0, 20.0)

    uitkomst = c.get_pv_forecast_spread()

    assert uitkomst["onzeker"] is False
    assert "voorspelbare dag" in uitkomst["reden"]


def test_an_uncertain_day_widens_the_reserve(make_coordinator, hass):
    """Dat is het hele punt: de voorspelling wordt niet beter, maar een
    onzekere dag wordt als onzeker behandeld."""
    c = _met_spreiding(make_coordinator, hass, 8.0, 24.0, 20.0)

    assert c._pv_onzekerheidsmarge_procent() > 0


def test_a_certain_day_adds_nothing(make_coordinator, hass):
    c = _met_spreiding(make_coordinator, hass, 19.0, 22.0, 20.0)

    assert c._pv_onzekerheidsmarge_procent() == 0.0


def test_it_uses_the_existing_margin_not_a_second_one():
    """Twee reserves naast elkaar kostte v1.86.0 tot en met v1.88.0."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("margin_bonus_percent = max(")
    blok = bron[kop - 400 : kop + 300]

    assert "pv_onzeker_percent" in blok


def test_without_the_sensors_nothing_is_claimed(make_coordinator, hass):
    """Niet te meten is iets anders dan zeker."""
    c = make_coordinator({})

    uitkomst = c.get_pv_forecast_spread()

    assert uitkomst["beschikbaar"] is False
    assert c._pv_onzekerheidsmarge_procent() == 0.0


# --- 3. De melding over het goedkope blok ----------------------------


def test_a_half_hour_at_double_the_minimum_is_no_tip():
    """Gemeld om 16:45: "Om 17:00 begint 't goedkoopste blok van
    vandage" - terwijl het dagminimum om 13:00 op 16,4 ct lag en 17:00
    op 30,7 ct.

    De melding klopte binnen zijn eigen logica: het blok is het
    goedkoopste dat er nog RESTEERT. Maar om kwart voor vijf is dat
    alleen nog de avond, en dan is "een goed moment voor apparaten die
    kunnen wachten" precies het verkeerde advies.
    """
    from custom_components.energy_management_system.const import (
        CHEAP_BLOCK_ALERT_MAX_OF_MEDIAN,
    )

    # De echte prijzen van 16 augustus: mediaan rond 30,7 ct.
    dag_mediaan = 0.307
    blok_om_17u = 0.307

    assert not blok_om_17u <= dag_mediaan * CHEAP_BLOCK_ALERT_MAX_OF_MEDIAN * 0.99


def test_a_genuinely_cheap_block_still_alerts():
    """Het middagblok op 16,4 ct hoort wél gemeld te worden."""
    from custom_components.energy_management_system.const import (
        CHEAP_BLOCK_ALERT_MAX_OF_MEDIAN,
    )

    dag_mediaan = 0.307
    middagblok = 0.164

    assert middagblok <= dag_mediaan * CHEAP_BLOCK_ALERT_MAX_OF_MEDIAN


def test_the_message_no_longer_claims_the_whole_day():
    """"van vandaag" suggereerde het dagminimum; het is het goedkoopste
    dat er nog KOMT."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index('"cheap_block_soon",', bron.index("minuten_tot"))
    blok = bron[kop : kop + 700]

    assert "nog komt vandaag" in blok
    assert "dagmediaan" in blok


def test_the_block_price_is_averaged_over_the_block(make_coordinator, hass):
    """Eén kwartier zegt niets over een blok van een half uur."""
    from datetime import datetime, timedelta, timezone

    from custom_components.energy_management_system.const import (
        PRICE_SCALE_FACTOR,
    )

    c = make_coordinator({})
    start = datetime(2026, 8, 16, 17, 0, tzinfo=timezone.utc)
    entries = [
        (start + timedelta(minutes=15 * i), None, prijs * PRICE_SCALE_FACTOR)
        for i, prijs in enumerate((0.30, 0.32, 0.50))
    ]

    gemiddeld = c._gemiddelde_prijs_in_blok(
        entries, start, start + timedelta(minutes=30)
    )

    assert round(gemiddeld, 3) == 0.31
