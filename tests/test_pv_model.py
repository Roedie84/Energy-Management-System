"""Een regressiewoud voor de zonvoorspelling (v2.9.0).

Gevraagd: "Is verder optimaliseren middels een Random Forest Regressor
nog een idee?" - en na mijn bezwaren: "Proberen kan altijd toch?"

Terecht. De bezwaren gingen over scikit-learn (numpy en scipy erbij,
zo'n 100 MB op een Raspberry Pi), niet over de techniek.
"""
import random

from custom_components.energy_management_system.pv_model import (
    RegressieWoud,
    gemiddelde_absolute_fout,
)


def test_it_learns_a_simple_relation():
    """Het minimum: een rechte lijn moet een woud kunnen volgen."""
    rijen = [[x] for x in range(50)]
    doelen = [2.0 * x + 3 for x in range(50)]

    woud = RegressieWoud(bomen=20, max_diepte=8)
    woud.leer(rijen, doelen)

    assert abs(woud.voorspel([25]) - 53) < 8


def test_it_uses_more_than_one_feature():
    """Zonder dat zou het woud niets toevoegen boven een uurcorrectie."""
    rng = random.Random(1)
    rijen, doelen = [], []
    for _ in range(200):
        zon, bewolking = rng.uniform(0, 3), rng.uniform(0, 100)
        rijen.append([zon, bewolking])
        doelen.append(zon * (1 - bewolking / 200))

    woud = RegressieWoud(bomen=25, max_diepte=6)
    woud.leer(rijen, doelen)

    helder = woud.voorspel([2.0, 5.0])
    bewolkt = woud.voorspel([2.0, 95.0])

    assert helder > bewolkt


def test_an_untrained_forest_says_nothing():
    """Geen voorspelling is beter dan een verzonnen voorspelling."""
    assert RegressieWoud().voorspel([1.0]) is None


def test_empty_input_does_not_crash():
    woud = RegressieWoud()
    woud.leer([], [])

    assert woud.voorspel([1.0]) is None


def test_the_error_measure_ignores_gaps():
    fout = gemiddelde_absolute_fout([1.0, 2.0, 3.0], [1.5, None, 2.5])

    assert fout == 0.5


# --- de eerlijke toetsing --------------------------------------------


def test_the_evaluation_needs_enough_days(make_coordinator, hass):
    """Met tweehonderd waarnemingen leert een woud de gegevens uit zijn
    hoofd. Onder de drempel wordt er niets beweerd."""
    c = make_coordinator({})
    c.pv_model_samples = []

    assert c.get_pv_model_evaluation()["beschikbaar"] is False


def test_the_split_is_on_time_not_at_random(make_coordinator, hass):
    """Willekeurig splitsen zou uren van dezelfde dag in beide helften
    laten belanden, en die lijken sterk op elkaar. Dan lijkt elk model
    goed."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_pv_model_evaluation")
    blok = bron[kop : bron.index("\n    def ", kop + 10)]

    assert 'm["datum"] < grens' in blok
    assert "shuffle" not in blok


def test_it_is_compared_against_the_current_method(make_coordinator, hass):
    """Een foutmaat zonder vergelijking zegt niets: de vraag is of het
    woud het BETER doet dan wat er al staat."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_pv_model_evaluation")
    blok = bron[kop : bron.index("\n    def ", kop + 10)]

    assert "door_huidig" in blok
    assert "fout_huidig" in blok


def test_a_small_gain_is_not_good_enough():
    """Een woud is niet uit te leggen, en dat is een echte prijs. Vijf
    procent minder fout weegt daar niet tegenop."""
    from custom_components.energy_management_system.const import (
        PV_MODEL_MIN_WINST_PROCENT,
    )

    assert PV_MODEL_MIN_WINST_PROCENT >= 10.0


def test_it_steers_nothing():
    """Op de proefstand tot de cijfers iets anders zeggen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_pv_model_evaluation")
    blok = bron[kop : bron.index("\n    def ", kop + 10)]
    code = "\n".join(r.split("#")[0] for r in blok.splitlines())

    for verboden in ("self.pv_hourly_bias", "_async_apply_operation", "reserve"):
        assert verboden not in code, verboden


def test_no_external_library_is_used():
    """Het bezwaar ging over scikit-learn, niet over de techniek."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "pv_model.py").read_text()
    # De toelichting noemt die bibliotheken bij naam; het gaat om de
    # IMPORTS.
    imports = "\n".join(
        r for r in bron.splitlines() if r.startswith(("import ", "from "))
    )

    for verboden in ("sklearn", "numpy", "scipy", "pandas"):
        assert verboden not in imports


# --- v3.3.0: bewolking en onenigheid als kenmerk ---------------------


def test_the_disagreement_between_sources_is_measured(
    make_coordinator, hass
):
    """Gevraagd of een integratie die bewolking per uur voorspelt kan
    helpen. Die bestaat, maar Solcast VERWERKT bewolking al - hun
    voorspelling is een bewerking van satellietbeelden en weermodellen.

    De ONENIGHEID tussen bronnen is iets anders. Op 16 augustus stond de
    een op 100% en de ander op 15%. Dat zegt niets over de bewolking,
    maar wel dat de dag moeilijk te voorspellen is.
    """
    from custom_components.energy_management_system.const import (
        CONF_KNMI_WEATHER_ENTITY,
        CONF_OPENWEATHERMAP_WEATHER_ENTITY,
    )

    c = make_coordinator(
        {
            CONF_KNMI_WEATHER_ENTITY: "weather.knmi",
            CONF_OPENWEATHERMAP_WEATHER_ENTITY: "weather.owm",
        }
    )
    hass.states.set("weather.knmi", "cloudy", {"cloud_coverage": 100})
    hass.states.set("weather.owm", "sunny", {"cloud_coverage": 15})

    assert c._weather_cloud_disagreement_pp() == 85.0


def test_one_source_gives_no_disagreement(make_coordinator, hass):
    """Met één bron valt er niets te vergelijken - dan geen getal in
    plaats van een verzonnen nul."""
    from custom_components.energy_management_system.const import (
        CONF_KNMI_WEATHER_ENTITY,
    )

    c = make_coordinator({CONF_KNMI_WEATHER_ENTITY: "weather.knmi"})
    hass.states.set("weather.knmi", "cloudy", {"cloud_coverage": 80})

    assert c._weather_cloud_disagreement_pp() is None


def test_a_missing_optional_feature_drops_the_column_not_the_rows(
    make_coordinator, hass
):
    """Een ontbrekend kenmerk maakte de hele rij onbruikbaar. Wie maar
    één weerbron heeft ingesteld krijgt nooit een onenigheidsgetal - en
    dan zou het model NOOIT iets leren."""
    c = make_coordinator({})
    monsters = [
        {
            "voorspeld_kwh": 1.0,
            "uur": 12,
            "hoogte": 50.0,
            "maand": 8,
            "bewolking": None,
            "bewolking_onenigheid": None,
        }
        for _ in range(5)
    ]

    kenmerken = c._bruikbare_kenmerken(monsters)

    assert "bewolking_onenigheid" not in kenmerken
    assert c._model_rij(monsters[0], kenmerken) is not None


def test_a_present_optional_feature_is_used(make_coordinator, hass):
    c = make_coordinator({})
    monsters = [
        {
            "voorspeld_kwh": 1.0,
            "uur": 12,
            "hoogte": 50.0,
            "maand": 8,
            "bewolking": 40.0,
            "bewolking_onenigheid": 12.0,
        }
    ]

    kenmerken = c._bruikbare_kenmerken(monsters)

    assert "bewolking" in kenmerken
    assert "bewolking_onenigheid" in kenmerken


def test_a_required_feature_still_drops_the_row(make_coordinator, hass):
    """Zonder voorspelling of uur valt er niets te leren."""
    c = make_coordinator({})

    assert c._model_rij(
        {"uur": 12, "hoogte": 50.0, "maand": 8}, ("voorspeld_kwh", "uur")
    ) is None
