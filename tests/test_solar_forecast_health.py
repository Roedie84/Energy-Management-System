"""Zelfcontrole op de zonvoorspelling (v1.5.0).

Gevraagd: "Neem je dit zelf mee in een diagnostiek, zodat je dit zelf
detecteert wanneer dit niet correct is" - naar aanleiding van het
handmatig vergelijken van `last_deviation_percent` met
`learned_bias_percent`.

De geleerde bias haalt de systematische afwijking eruit. Wat overblijft
hoort dagruis te zijn, rond nul. Blijven de recente dagen structureel aan
één kant hangen, dan is er iets veranderd aan de installatie -
vervuiling, een uitgevallen streng, een uitgegroeide boom. Dat soort
langzame verslechtering mis je met het blote oog.
"""
from custom_components.energy_management_system.const import (
    RELIABILITY_INSUFFICIENT,
    RELIABILITY_NOT_CONFIGURED,
    RELIABILITY_RELIABLE,
    RELIABILITY_UNRELIABLE,
    SOLAR_BIAS_DRIFT_ATTENTION_PERCENT,
    SOLAR_BIAS_DRIFT_MIN_DAYS,
)


class _Tracker:
    def __init__(self, afwijkingen, bias, verwacht=None, typisch=None):
        self.deviation_history = list(afwijkingen)
        self.learned_bias_percent = bias
        self.pending_predicted_kwh = verwacht
        self.learned_typical_forecast_kwh = typisch
        # De weinig-zon-fractie beweegt mee met hoe consistent de
        # voorspelling recent was; die spreiding hoort er dus bij.
        self.deviation_stdev_percent = 8.0


def _coordinator(make_coordinator, tracker=None):
    c = make_coordinator({})
    c.solar_tracker = tracker
    return c


# --- de zelfcontrole -------------------------------------------------


def test_a_stable_correction_is_reported_as_working(make_coordinator, hass):
    """De situatie in een echte export: recente afwijking -10,3% naast
    een geleerde bias van -11,6%. Dat is precies de bedoeling."""
    c = _coordinator(
        make_coordinator, _Tracker([-10.3] * 7, -11.6)
    )

    gezondheid = c.get_solar_forecast_health()

    assert gezondheid["status"] == RELIABILITY_RELIABLE
    assert abs(gezondheid["drift_percent"]) < SOLAR_BIAS_DRIFT_ATTENTION_PERCENT


def test_a_structural_drift_is_flagged(make_coordinator, hass):
    """De opbrengst blijft structureel achter bij wat de bias al
    verrekent - dat is geen dagruis meer."""
    c = _coordinator(make_coordinator, _Tracker([-45.0] * 6, -11.6))

    gezondheid = c.get_solar_forecast_health()

    assert gezondheid["status"] == RELIABILITY_UNRELIABLE
    assert "vervuiling" in gezondheid["reden"]


def test_drifting_upward_is_also_flagged(make_coordinator, hass):
    """Ook structureel béter dan verwacht is een signaal - dan klopt de
    geleerde bias niet meer."""
    c = _coordinator(make_coordinator, _Tracker([30.0] * 6, -11.6))

    assert c.get_solar_forecast_health()["status"] == RELIABILITY_UNRELIABLE


def test_only_recent_days_count(make_coordinator, hass):
    """Een verslechtering van de laatste dagen mag niet worden
    weggemiddeld door een lange, goede geschiedenis."""
    c = _coordinator(
        make_coordinator,
        _Tracker([-10.0] * 30 + [-50.0] * SOLAR_BIAS_DRIFT_MIN_DAYS, -11.6),
    )

    assert c.get_solar_forecast_health()["status"] == RELIABILITY_UNRELIABLE


def test_no_verdict_below_the_minimum(make_coordinator, hass):
    c = _coordinator(make_coordinator, _Tracker([-40.0] * 2, -11.6))

    assert c.get_solar_forecast_health()["status"] == RELIABILITY_INSUFFICIENT


def test_no_tracker_means_not_configured(make_coordinator, hass):
    c = _coordinator(make_coordinator, None)

    assert c.get_solar_forecast_health()["status"] == RELIABILITY_NOT_CONFIGURED


def test_it_appears_in_the_reliability_overview(make_coordinator, hass):
    """v3.92.3: het label heette "klopt de correctie nog?".

    Gemeld met schermafdruk terwijl er geen correctie liep: de vlakke
    bias is sinds v3.33.0 ingehouden en de vakcorrectie sinds v3.92.2
    ook. De kaart gaat over de voorspelling zelf.
    """
    c = _coordinator(make_coordinator, _Tracker([-10.0] * 7, -11.6))

    namen = {r["naam"] for r in c.get_reliability_overview()}

    assert "Zonvoorspelling (klopt hij nog met de panelen?)" in namen
    assert "Zonvoorspelling (klopt de correctie nog?)" not in namen


# --- hoe dicht bij de weinig-zon-drempel -----------------------------


def test_the_margin_shows_how_close_today_is(make_coordinator, hass):
    """Vandaag zat op ~70% van typisch, vlak op de grens - en dat was
    nergens te zien. Daardoor viel niet te beoordelen of het uitblijven
    van extra-dip-laden terecht was."""
    c = _coordinator(
        make_coordinator,
        _Tracker([-10.0] * 7, -11.6, verwacht=15.44, typisch=21.85),
    )

    marge = c.get_low_solar_margin()

    assert marge["verwacht_kwh"] == 15.44
    assert marge["typisch_kwh"] == 21.85
    assert marge["verhouding"] == 0.71


def test_without_forecast_data_there_is_no_margin(make_coordinator, hass):
    c = _coordinator(make_coordinator, _Tracker([], -11.6))

    assert c.get_low_solar_margin()["verhouding"] is None


def test_the_margin_uses_the_same_fraction_as_the_decision():
    """Het overzicht en de beslissing mogen niet uit elkaar lopen - een
    tweede, eigen drempelberekening zou precies dat risico geven."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("def get_low_solar_margin")
    blok = bron[start : start + 1600]

    assert "_get_low_solar_relative_fraction" in blok


# --- de meldingen die nooit werden verstuurd -------------------------


def test_every_notification_type_is_actually_dispatched():
    """Negen van de eenentwintig soorten hadden wél een schakelaar maar
    werden nergens verstuurd - een schakelaar voor een melding die nooit
    komt is erger dan geen schakelaar.
    """
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    from custom_components.energy_management_system.const import (
        NOTIFICATION_TYPES,
    )

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    verstuurd = set(re.findall(r'kind="([a-z_]+)"', bron))
    verstuurd |= set(re.findall(r'stuur\(\s*"([a-z_]+)"', bron))
    # v1.23.4: de planningsmeldingen gaan via een hulpfunctie die de
    # soort als eerste argument krijgt, niet als letterlijke `kind=`.
    verstuurd |= set(re.findall(r'_meld\(\s*\n?\s*"([a-z_]+)"', bron))

    ontbreekt = {
        k for k, _, _, _, _ in NOTIFICATION_TYPES if k not in verstuurd
    }

    assert ontbreekt == set(), ontbreekt
