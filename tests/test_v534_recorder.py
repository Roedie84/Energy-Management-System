"""Dashboard-attributen blijven buiten de recorder (v5.34).

Gemeten op een echte installatie, per sensor: wijzigingen per uur maal de
grootte van de attributen die de recorder bewaarde. Samen ~190 MB per dag:

    NILM bevestigde apparaten   119/u x 16,9 kB   48 MB/dag
    GACS-zelfbeoordeling        119/u x  8,7 kB   25 MB/dag
    Betrouwbaarheid             112/u x  8,1 kB   22 MB/dag
    Energiebrug-check            56/u x  8,6 kB   12 MB/dag
    Klimaat-projectie            32/u x 14,0 kB   11 MB/dag
    ...

Bij GACS stonden twee `_unrecorded_attributes` onder elkaar; de tweede
overschreef de eerste.
"""
import ast
from pathlib import Path

from custom_components.energy_management_system import sensor
from custom_components.energy_management_system.const import (
    GEEN_ATTRIBUTEN_IN_RECORDER,
)

ZWAAR = [
    "NilmConfirmedDevicesSensor", "GacsAssessmentSensor",
    "ReliabilityOverviewSensor", "EnergyBridgeCheckSensor",
    "ClimateForecastSensor", "DigitalTwinAdvisorySensor", "MpcAdvisorySensor",
    "SystemStatusSensor", "BatteryCoolingSensor", "WeatherEnsembleSensor",
    "HourlyConsumptionProfileSensor", "LiveNarrativeSensor",
    "LivingRoomAircoPredictionSensor", "ExplanationSensor",
    "PvHourlyBiasSensor", "KalmanFilterAdvisorySensor",
    "BatteryModuleHealthSensor", "CounterfactualSavingsSensor",
    "WaterUsageSensor", "DigitalTwinAccuracySensor", "MeldingenSensor",
    "MonthlySummarySensor", "PvInstallationProfileSensor",
]


def test_match_all_is_de_waarde_van_home_assistant():
    assert GEEN_ATTRIBUTEN_IN_RECORDER == frozenset({"*"})


def test_de_zware_sensoren_bewaren_geen_eigen_attributen():
    for naam in ZWAAR:
        assert getattr(sensor, naam)._unrecorded_attributes == GEEN_ATTRIBUTEN_IN_RECORDER, naam


def test_geen_klasse_zet_unrecorded_attributes_twee_keer():
    """Een tweede toekenning in dezelfde klasse overschrijft de eerste -
    zo bleef bij GACS 8,7 kB per wijziging toch in de database."""
    boom = ast.parse(Path(sensor.__file__).read_text())
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.ClassDef):
            toekenningen = [
                d for d in knoop.body
                if isinstance(d, ast.Assign)
                and any(getattr(t, "id", None) == "_unrecorded_attributes" for t in d.targets)
            ]
            assert len(toekenningen) <= 1, knoop.name
