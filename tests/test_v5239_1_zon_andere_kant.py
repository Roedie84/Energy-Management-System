"""Dagcontrole 19-11 (v5.239.1).

Zonvoorspelling 'klopt hij nog met de panelen?': een dag die de ANDERE kant
op ver ernaast zit, spreekt een verschuiving tegen. Gemeld 19-11 00:00
(melding solar_underperforming) met de reeks -51,5 / -53,6 / -43,4 / -29,3 /
+41,0 %: "structureel 43 procentpunt lager ... en dat geldt voor élke dag".
Op 18-11 leverden de panelen 41 % meer dan voorspeld.
"""
from custom_components.energy_management_system.const import (
    RELIABILITY_INSUFFICIENT,
    RELIABILITY_UNRELIABLE,
)


class _Tracker:
    def __init__(self, afwijkingen, bias=None):
        self.deviation_history = list(afwijkingen)
        self.learned_bias_percent = bias
        self.pending_predicted_kwh = None
        self.learned_typical_forecast_kwh = None
        self.deviation_stdev_percent = 8.0


def test_reeks_van_19_11_wijst_de_installatie_niet_aan(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = _Tracker([-51.5, -53.6, -43.4, -29.3, 41.0])

    gezondheid = c.get_solar_forecast_health()

    assert gezondheid["status"] == RELIABILITY_INSUFFICIENT
    assert gezondheid["soort"] == "wisselend"
    assert "geen goede dag ertussen" not in gezondheid["reden"]
    assert "1 de andere kant op" in gezondheid["reden"]
    assert "hoger" in gezondheid["reden"]


def test_geen_melding_bij_een_dag_de_andere_kant_op(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = _Tracker([-51.5, -53.6, -43.4, -29.3, 41.0])

    assert c.get_solar_forecast_health()["status"] != RELIABILITY_UNRELIABLE


def test_kleine_uitschieter_de_andere_kant_op_telt_niet(make_coordinator, hass):
    """Alle dagen aan dezelfde kant: de echte verschuiving blijft gemeld."""
    c = make_coordinator({})
    c.solar_tracker = _Tracker([-18.0, -22.0, -16.0, -30.0, -19.0])

    gezondheid = c.get_solar_forecast_health()

    assert gezondheid["status"] == RELIABILITY_UNRELIABLE
    assert gezondheid["soort"] == "verschuiving"


def test_verschuiving_omhoog_met_een_dag_lager_is_wisselend(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = _Tracker([30.0, 28.0, -35.0, 40.0, 26.0])

    gezondheid = c.get_solar_forecast_health()

    assert gezondheid["soort"] == "wisselend"
    assert "lager" in gezondheid["reden"]
