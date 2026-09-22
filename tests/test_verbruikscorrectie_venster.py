"""De verbruikscorrectie dempte over 4 minuten in plaats van 20 (v5.14.2).

Gevonden in de export van 22 september 07:02, na de eerste volle nacht met
alle reparaties. "Accu haalt de nacht niet" ging nog twee keer af - terwijl
de accu de nacht met 44% over haalde. De energiebrug liet zien waarom:

    02:23  nodig 4,74 -> bijladen nodig        (beschikbaar 4,23)
    02:27  nodig 3,84 -> genoeg                 4 minuten later
    04:12  nodig 4,15 -> bijladen nodig
    04:21  nodig 3,12 -> genoeg                 9 minuten later
    04:33  nodig 4,68 -> bijladen nodig
    04:46  nodig 3,01 -> genoeg                 13 minuten later

De behoefte sprong 1 tot 1,7 kWh in een paar minuten, en de beslissing
wisselde elk kwartier tussen discharging_window en default_smart.

De oorzaak: de live verbruikscorrectie telt verbruik boven het geleerde
profiel door over de hele overbruggingsperiode, tot 1,5 kWh extra. Ze dempt
met een mediaan over CONSUMPTION_CORRECTION_SMOOTHING_SAMPLES metingen - en
het commentaar erbij zegt:

    "at the ~5 minute update interval, this is roughly 15-25 minutes"

Vier metingen waren 15 tot 25 minuten, toen de ronde elke vijf minuten
liep. Nu loopt hij elke 60 seconden, en werden het 4 MINUTEN. Een
koelkast- of vriezercompressor draait 10 tot 20 minuten en telde toen als
"aanhoudend". De sprongen duurden 4, 9 en 13 minuten - precies een
compressorbeurt.

De constante telde metingen, geen tijd, en veranderde stil van betekenis
toen het interval veranderde. Nu is het venster in MINUTEN, omgerekend met
het werkelijke interval. Zo kan een ander interval dit niet meer stil
veranderen.
"""
import pytest

GELEERD_KW = 0.27        # nachtverbruik zoals geleerd
COMPRESSOR_KW = 0.40     # met een koelkast- of vriezercompressor erbij


def _met_interval(c, seconden):
    c.config = dict(c.config or {})
    c.config["update_interval_seconds"] = seconden
    return c


def _meet(c, reeks_kw):
    c._recent_consumption_readings_kw = []
    for kw in reeks_kw:
        c._read_corrected_consumption_power = lambda k=kw: k * 1000
        c._track_recent_consumption_reading(None)


def test_bij_60_seconden_beslaat_het_venster_een_half_uur(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONSUMPTION_CORRECTION_WINDOW_MINUTES,
    )

    c = _met_interval(make_coordinator({}), 60)

    assert c._correctie_monsters() == CONSUMPTION_CORRECTION_WINDOW_MINUTES


def test_bij_vijf_minuten_hetzelfde_halve_uur(make_coordinator, hass):
    """Het venster is TIJD. Bij een langzamer interval zijn het minder
    metingen, maar dezelfde tijdspanne."""
    from custom_components.energy_management_system.const import (
        CONSUMPTION_CORRECTION_WINDOW_MINUTES,
    )

    c = _met_interval(make_coordinator({}), 300)

    assert c._correctie_monsters() * 5 >= CONSUMPTION_CORRECTION_WINDOW_MINUTES


def test_een_compressorbeurt_tilt_de_nacht_niet_op(make_coordinator, hass):
    """Het gemeten geval: 20 minuten normaal, dan 13 minuten compressor -
    de langste sprong van vannacht."""
    c = _met_interval(make_coordinator({}), 60)
    c.learned_hourly_avg_kw = lambda uur: GELEERD_KW
    _meet(c, [GELEERD_KW] * 20 + [COMPRESSOR_KW] * 13)

    assert c._get_smoothed_consumption_correction_ratio(4) == 1.0


def test_een_echte_aanhoudende_verandering_komt_er_wel_door(make_coordinator, hass):
    """Wat de correctie wél moet zien: een airco die een uur draait."""
    c = _met_interval(make_coordinator({}), 60)
    c.learned_hourly_avg_kw = lambda uur: GELEERD_KW
    _meet(c, [0.9] * 40)

    assert c._get_smoothed_consumption_correction_ratio(20) > 1.5


def test_met_het_oude_venster_had_de_compressor_wel_doorgewerkt(make_coordinator, hass):
    """Het bewijs dat dit de oorzaak was: over de laatste 4 metingen - het
    oude venster bij 60 seconden - telt de compressor volledig."""
    import statistics

    laatste_vier = ([GELEERD_KW] * 20 + [COMPRESSOR_KW] * 13)[-4:]

    assert statistics.median(laatste_vier) / GELEERD_KW > 1.4


# --- de klasse: tijdvensters die in rondes telden -----------------------


@pytest.mark.parametrize(
    "venster,uren",
    [
        ("correctie", 0.5),
        ("cyclus", 5.0),
        ("nilm", 8.0),
    ],
)
def test_een_tijdvenster_blijft_even_lang_bij_elk_interval(make_coordinator, hass, venster, uren):
    """De ratel op de hele klasse: verander het interval, en elk tijdvenster
    moet dezelfde TIJD blijven beslaan. Drie constanten deden dat niet - ze
    telden rondes en krompen stil toen de ronde van vijf minuten naar zestig
    seconden ging."""
    from custom_components.energy_management_system.const import (
        APPLIANCE_POWER_SAMPLE_LIMIT,
        APPLIANCE_POWER_SAMPLE_UREN,
        CONSUMPTION_CORRECTION_SMOOTHING_SAMPLES,
        CONSUMPTION_CORRECTION_WINDOW_MINUTES,
        NILM_MIN_SAMPLES_FOR_DAY,
        NILM_MIN_UREN_VOOR_DAG,
    )

    parameters = {
        "correctie": (CONSUMPTION_CORRECTION_WINDOW_MINUTES / 60, CONSUMPTION_CORRECTION_SMOOTHING_SAMPLES),
        "cyclus": (APPLIANCE_POWER_SAMPLE_UREN, APPLIANCE_POWER_SAMPLE_LIMIT),
        "nilm": (NILM_MIN_UREN_VOOR_DAG, NILM_MIN_SAMPLES_FOR_DAY),
    }
    duur_uren, minimum = parameters[venster]
    assert duur_uren == uren

    for interval in (60, 120, 300):
        c = _met_interval(make_coordinator({}), interval)
        metingen = c._metingen_voor(duur_uren, minimum)
        beslaat_uren = metingen * interval / 3600
        # minstens de bedoelde tijd - bij een langzaam interval mag het
        # minimum in metingen het iets langer maken, nooit korter
        assert beslaat_uren >= duur_uren - 1e-9, (venster, interval, beslaat_uren)
