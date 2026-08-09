"""Hoe goed voorspelt Solcast de dagopwek? (v1.17.2)

Gevraagd: "Ook wil ik meer analyse parameters zien, bijvoorbeeld hoe goed
is de voorspellende PV opwek."

Er werd alleen de geleerde BIAS getoond - de gemiddelde afwijking. Die
zegt of de voorspelling structureel te hoog of te laag zit, maar niet hoe
betrouwbaar een losse dag is.

Bij deze installatie: bias -11,6%, maar de gemiddelde ABSOLUTE fout is
15,2% en de slechtste dag zat er 37,2% naast. Corrigeer je de bias, dan
blijft die spreiding over - en dat is wat telt als de reserveberekening
op deze voorspelling vertrouwt.
"""


class _Tracker:
    def __init__(self, afwijkingen):
        self.deviation_history = list(afwijkingen)
        self.learned_bias_percent = -11.6


ECHT = [-37.2, -22.1, 12.9, -9.3, -10.4, -4.5, -10.3]


def _kwaliteit(make_coordinator, afwijkingen=ECHT):
    c = make_coordinator({})
    c.solar_tracker = _Tracker(afwijkingen)
    return c.get_pv_forecast_quality()


# --- bias en fout zijn verschillende dingen -------------------------


def test_bias_and_error_are_separate(make_coordinator, hass):
    """De kern: -11,6% bias naast 15,2% gemiddelde fout. Wie alleen de
    bias ziet, denkt dat corrigeren het probleem oplost."""
    q = _kwaliteit(make_coordinator)

    assert q["bias_procent"] == -11.6
    assert q["gemiddelde_fout_procent"] == 15.2
    assert q["gemiddelde_fout_procent"] > abs(q["bias_procent"])


def test_the_worst_day_is_shown(make_coordinator, hass):
    """Een gemiddelde verbergt de uitschieter die je plan omgooit."""
    q = _kwaliteit(make_coordinator)

    assert q["slechtste_dag_procent"] == 37.2
    assert q["beste_dag_procent"] == 4.5


def test_it_counts_days_within_a_margin(make_coordinator, hass):
    """"2 van de 7 dagen binnen 10%" zegt meer dan een gemiddelde."""
    q = _kwaliteit(make_coordinator)

    assert q["dagen_binnen_10_procent"] == 2
    assert q["dagen_binnen_20_procent"] == 5


def test_the_spread_is_reported(make_coordinator, hass):
    q = _kwaliteit(make_coordinator)

    assert q["spreiding_procent"] == 14.3


# --- duiding ---------------------------------------------------------


def test_it_says_what_the_error_means_in_practice(make_coordinator, hass):
    """"15,2%" is een getal zonder schaal; het gaat erom of je erop kunt
    plannen."""
    q = _kwaliteit(make_coordinator)

    assert "speling" in q["duiding"]
    assert "20 kWh" in q["duiding"]


def test_a_good_forecast_says_so(make_coordinator, hass):
    q = _kwaliteit(make_coordinator, [3.0, -4.0, 2.0, -5.0, 1.0, -2.0])

    assert "bruikbaar om op te plannen" in q["duiding"]


def test_a_bad_forecast_warns(make_coordinator, hass):
    q = _kwaliteit(make_coordinator, [40.0, -35.0, 30.0, -45.0, 25.0])

    assert "riskant" in q["duiding"]


def test_too_few_days_says_so(make_coordinator, hass):
    """Drie dagen zegt niets over betrouwbaarheid."""
    q = _kwaliteit(make_coordinator, [5.0, -3.0, 4.0])

    assert "te weinig" in q["duiding"]


# --- grenzen ---------------------------------------------------------


def test_without_data_it_explains_why(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = _Tracker([])

    q = c.get_pv_forecast_quality()

    assert q["beschikbaar"] is False
    assert "voltooide dagen" in q["reden"]


def test_without_a_tracker_it_does_not_crash(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = None

    assert c.get_pv_forecast_quality()["beschikbaar"] is False


def test_a_single_day_has_no_spread(make_coordinator, hass):
    """Spreiding over één waarde is betekenisloos."""
    q = _kwaliteit(make_coordinator, [-10.0])

    assert q["spreiding_procent"] is None


# --- inbedding -------------------------------------------------------


def test_it_is_in_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "pv_forecast_quality" in bron


def test_it_is_on_the_pv_page():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    zon = next(v for v in data["views"] if v["path"] == "detail-zon")
    kaarten = [k for s in zon["sections"] for k in s.get("cards") or []]

    kaart = next(
        k for k in kaarten if "voorspelling" in str(k.get("title", "")).lower()
    )

    for veld in ("bias_procent", "gemiddelde_fout_procent", "slechtste_dag_procent"):
        assert veld in kaart["content"], veld
