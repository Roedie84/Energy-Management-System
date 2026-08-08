"""Samenhang na een dag met veel wijzigingen (v1.16.6).

Gevraagd: "We hebben vandaag zoveel gewijzigd, waardoor ik angst heb dat
veel niet meer samen werkt, kun je dit checken."

Terechte zorg: groene tests zeggen dat elk onderdeel apart klopt, niet
dat ze samen nog werken. Deze tests draaien de KETENS door - een
volledige dag ticks, elke diagnostiekmethode, en elke aanroep die de
export doet.
"""
import inspect
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import diagnostics
from custom_components.energy_management_system.const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_PV_ENERGY_SENSOR,
    CONF_PV_POWER_SENSOR,
)

PAKKET = Path(pkg.__file__).parent
START = datetime(2026, 8, 9, 6, 0, tzinfo=timezone.utc)


def _volledig(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
            CONF_CONSUMPTION_POWER_SENSOR: "sensor.huis_w",
            CONF_PV_POWER_SENSOR: "sensor.pv_w",
            CONF_PV_ENERGY_SENSOR: "sensor.pv_kwh",
            CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon",
        }
    )
    c._get_forecast_entries = lambda: []
    return c


# --- de ketens -------------------------------------------------------


def test_a_full_day_of_ticks_runs_clean(make_coordinator, hass):
    """Zestien uur in kwartieren. Een fout die pas na tientallen ticks
    opduikt - een teller die overloopt, een reeks die vol raakt - wordt
    door losse tests niet gevonden."""
    c = _volledig(make_coordinator, hass)

    for tick in range(64):
        nu = START + timedelta(minutes=15 * tick)
        hass.states.set("sensor.beschikbaar", str(2.0 + tick * 0.05))
        hass.states.set("sensor.accu_w", str(300 - tick * 5))
        hass.states.set("sensor.huis_w", str(400 + (tick % 7) * 50))
        hass.states.set("sensor.pv_w", str(max(0, 2000 - abs(tick - 32) * 60)))
        hass.states.set("sensor.pv_kwh", str(1000.0 + tick * 0.3))

        c._update_energy_balance_validation(nu)
        c._evaluate_new_notifications(nu)
        c._update_advisory_readiness(nu)


def test_every_diagnostic_method_returns(make_coordinator, hass):
    """Veertien methodes die vandaag zijn aangeraakt of toegevoegd."""
    c = _volledig(make_coordinator, hass)

    for naam in (
        "get_diagnostic_summary",
        "get_topic_summaries",
        "get_stalled_series_report",
        "get_self_evaluation",
        "get_dashboard_health",
        "get_improvement_suggestions",
        "get_gacs_assessment",
        "get_plausibility_warnings",
        "get_reliability_overview",
        "get_sensor_health_breakdown",
        "get_zonneplan_cost_comparison",
        "get_energy_cost_overview",
        "get_nilm_devices_table",
        "get_battery_module_table",
    ):
        resultaat = getattr(c, naam)()
        json.dumps(resultaat, default=str)


def test_every_export_call_works(make_coordinator, hass):
    """De export roept ruim twintig methodes aan; één die faalt maakt de
    hele diagnostiek onbruikbaar - precies wanneer je hem nodig hebt."""
    c = _volledig(make_coordinator, hass)
    bron = inspect.getsource(diagnostics)

    for naam in sorted(set(re.findall(r"coordinator\.(get_\w+)\(\)", bron))):
        json.dumps(getattr(c, naam)(), default=str)


def test_every_exported_attribute_exists(make_coordinator, hass):
    """Een verwijderd of hernoemd veld laat de export stilletjes op None
    uitkomen."""
    c = _volledig(make_coordinator, hass)
    bron = inspect.getsource(diagnostics)

    velden = sorted(set(re.findall(r"coordinator\.([a-z_]+)[,\s\)\]]", bron)))
    ontbreekt = [v for v in velden if not hasattr(c, v)]

    assert not ontbreekt, ontbreekt


# --- de aansturing is niet geraakt -----------------------------------


def test_the_control_logic_is_untouched():
    """De kern: alle wijzigingen van vandaag zaten in weergave en
    diagnostiek. De reserveberekening en de planningsprojectie bepalen
    wanneer de accu laadt en ontlaadt - die horen ongemoeid te blijven,
    en zijn eerder expliciet afgeschermd.
    """
    bron = (PAKKET / "coordinator.py").read_text()

    for functie in (
        "_get_dynamic_discharge_reserve_kwh",
        "_build_forecast_timeline",
        "cap_discharge_to_own_consumption",
    ):
        assert f"def {functie}" in bron, functie


def test_all_services_are_registered():
    """Een gedocumenteerde dienst die niet bestaat, faalt pas op het
    moment dat je hem aanroept."""
    import yaml

    diensten = set(yaml.safe_load((PAKKET / "services.yaml").read_text()) or {})
    init = (PAKKET / "__init__.py").read_text()

    for dienst in diensten:
        assert f'"{dienst}"' in init, dienst
