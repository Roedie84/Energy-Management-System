"""De naburige vakjes werden zes dagen niet geraadpleegd (v3.47.0).

Gevonden bij het nakijken van een schermafdruk van de klimaattabel.

Sinds v3.41.0 beginnen de celsleutels met een `d` - "d-6.0" in plaats
van "6.0" - omdat ze het VERSCHIL met binnen dragen en niet de
buitentemperatuur. De terugval naar naburige vakjes rekende daar nog
mee als getal:

    bucket_waarde = float(outdoor_bucket)   ->  float("d-6.0")

Dat werpt een ValueError, `bucket_waarde` werd None, en de hele stap
werd overgeslagen. Stilzwijgend: geen fout, geen melding, alleen een
terugval die er niet meer was.

Gevolg: de projectie viel meteen door naar de grofste samenvatting, en
dat is precies wat er misging bij een verschil van +8 graden waar geen
cel voor bestond.
"""
import pytest


def _cel(c, verschil, rolluik, airco, waarden):
    c.climate_rate_history[f"d{verschil}|{rolluik}|{airco}"] = list(waarden)


def test_a_neighbouring_bucket_is_used_again(make_coordinator, hass):
    """Twee graden verschil weegt minder zwaar dan een andere

    rolluikstand, dus dit hoort vóór de bredere samenvatting te komen.
    """
    from custom_components.energy_management_system.const import (
        CLIMATE_RATE_MIN_SAMPLES,
    )

    c = make_coordinator({})
    _cel(c, "-4.0", "beide_dicht", "uit", [-0.3] * CLIMATE_RATE_MIN_SAMPLES)

    resultaat = c.get_climate_rate_indicative("d-6.0", "beide_dicht", "uit")

    assert resultaat["basis"] == "naburige_buitentemperatuur"
    assert resultaat["rate_c_per_hour"] == -0.3


def test_the_d_prefix_is_parsed(make_coordinator, hass):
    """De aanleiding, als getal: `float("d-6.0")` werpt een ValueError."""
    c = make_coordinator({})

    with pytest.raises(ValueError):
        float("d-6.0")

    # En de code moet daar nu wél doorheen komen.
    _cel(c, "0.0", "beide_dicht", "uit", [-0.1] * 5)

    assert (
        c.get_climate_rate_indicative("d-2.0", "beide_dicht", "uit")["basis"]
        == "naburige_buitentemperatuur"
    )


def test_far_away_neighbours_are_not_used(make_coordinator, hass):
    """Naburig betekent één vakje, niet het hele bereik."""
    c = make_coordinator({})
    _cel(c, "-10.0", "beide_dicht", "uit", [-0.3] * 5)

    resultaat = c.get_climate_rate_indicative("d-2.0", "beide_dicht", "uit")

    assert resultaat["basis"] != "naburige_buitentemperatuur"
