"""Dashboard markdown tables must render as contiguous Markdown tables -
no blank lines between rows.

Regression test for a subtle interaction: YAML's `>` folded scalar style
joins consecutive non-blank lines with a *space* (not a newline), and
only a blank line becomes a real newline. Getting the blank-line
placement wrong either merges table rows onto one line (breaks the
table) or leaves stray blank lines between rows (also breaks the
table - Markdown requires every table row on its own, consecutive
line). This uses the exact same two-step pipeline Home Assistant does
(YAML parse, then Jinja render) to catch either failure mode.
"""
from datetime import datetime
import re
from pathlib import Path

import yaml
from jinja2 import Environment

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = (
    REPO_ROOT
    / "custom_components"
    / "energy_management_system"
    / "dashboard_template.yaml"
)


def _fake_state_attr(entity, attr):
    """Enough fake data to exercise every markdown table's Jinja loops."""
    fake_data = {
        (
            "sensor.woonkamer_energy_management_system_hourly_consumption_profile",
            "profile_watts",
        ): {"0": 264, "9": 497, "23": 346},
        (
            "sensor.woonkamer_energy_management_system_hourly_consumption_profile",
            "previous_profile_watts",
        ): {"0": 250, "9": 480},
        (
            "sensor.energy_management_system_learned_night_consumption",
            "history_kw",
        ): [0.229, 0.407, 0.276],
        (
            "sensor.energy_management_system_pv_forecast_accuracy",
            "deviation_history",
        ): [-37.2, -22.1, -10.3],
        (
            "sensor.energy_management_system_pv_forecast_accuracy",
            "learned_bias_percent",
        ): -11.6,
        (
            "sensor.woonkamer_energy_management_system_pv_hourly_forecast_bias",
            "profile",
        ): {"6": 0.793, "9": 0.284, "20": 0.32},
        (
            "sensor.woonkamer_energy_management_system_pv_hourly_forecast_bias",
            "previous_profile",
        ): {"6": 0.750, "20": 0.35},
        (
            "sensor.woonkamer_energy_management_system_learned_battery_efficiency",
            "history",
        ): [92.9, 85.1, 85.3, 76.8, 76.7, 76.6, 88.2],
        (
            "sensor.woonkamer_energy_management_system_monthly_summary",
            "current_month_discharge_value_eur",
        ): 45.5,
        (
            "sensor.woonkamer_energy_management_system_monthly_summary",
            "current_month_charge_cost_eur",
        ): 12.3,
        (
            "sensor.woonkamer_energy_management_system_monthly_summary",
            "previous_month_net_eur",
        ): 30.0,
        (
            "sensor.energy_management_system_energy_bridge_check",
            "transition_log",
        ): [
            {
                "at": "2026-08-03T09:00:00+02:00",
                "decision": "enough_to_postpone",
                "available_kwh": 2.68,
                "needed_kwh": 0.0,
                "cheap_block_start": "2026-08-04T09:00:00+02:00",
            }
        ],
        (
            "sensor.energy_management_system_upcoming_schedule",
            "transitions",
        ): [
            {
                "start": "2026-08-03T18:30:00+02:00",
                "end": "2026-08-03T23:45:00+02:00",
                "mode": "manual",
                "min_price_per_kwh": 0.3169,
                "max_price_per_kwh": 0.3637,
            }
        ],
        (
            "sensor.woonkamer_energy_management_system_explanation",
            "explanation",
        ): "Er is nu geen speciale reden om in te grijpen.",
        (
            "sensor.woonkamer_energy_management_system_explanation",
            "last_successful_update",
        ): "2026-08-04T07:30:55+02:00",
        (
            "sensor.woonkamer_energy_management_system_explanation",
            "force_manual",
        ): False,
        (
            "sensor.woonkamer_energy_management_system_explanation",
            "expected_mode",
        ): "smart",
        (
            "sensor.woonkamer_energy_management_system_explanation",
            "current_price_per_kwh",
        ): 0.3389,
        (
            "sensor.woonkamer_energy_management_system_explanation",
            "expensive_price_threshold",
        ): 0.378,
        (
            "sensor.woonkamer_energy_management_system_explanation",
            "secondary_price_threshold",
        ): 0.349,
        (
            "sensor.woonkamer_energy_management_system_explanation",
            "effective_expensive_quarters_count",
        ): 8,
        (
            "sensor.woonkamer_energy_management_system_waterverbruik",
            "vandaag_liter",
        ): 220.0,
        (
            "sensor.woonkamer_energy_management_system_waterverbruik",
            "gemiddeld_liter_per_dag",
        ): 190.0,
        (
            "sensor.woonkamer_energy_management_system_waterverbruik",
            "trend_procent",
        ): 15.8,
        (
            "sensor.woonkamer_energy_management_system_waterverbruik",
            "geschiedenis_liter_per_dag",
        ): [180.0, 200.0, 190.0],
        (
            "sensor.woonkamer_energy_management_system_waterverbruik",
            "waterontharder_laatste_regeneratie",
        ): "2026-08-01T03:00:00+00:00",
        (
            "sensor.woonkamer_energy_management_system_waterverbruik",
            "recente_gebruiksmomenten",
        ): [
            {
                "gestart": "2026-08-05T07:12:00+00:00",
                "duur_minuten": 6.5,
                "liter": 48.0,
                "waarschijnlijk_waterontharder": False,
            },
            {
                "gestart": "2026-08-01T03:00:00+00:00",
                "duur_minuten": 42.0,
                "liter": None,
                "waarschijnlijk_waterontharder": True,
            },
        ],
        (
            "sensor.woonkamer_energy_management_system_model_en_parameternauwkeurigheid",
            "zon_voorspelling_spreiding_trend",
        ): {"richting": "dalend", "verschil_procent": -12.5},
        (
            "sensor.woonkamer_energy_management_system_model_en_parameternauwkeurigheid",
            "zon_voorspelling_spreiding_procent",
        ): 14.0,
        (
            "sensor.woonkamer_energy_management_system_model_en_parameternauwkeurigheid",
            "extra_dip_marge_trend",
        ): {"richting": "stijgend", "verschil_procent": 8.0},
        (
            "sensor.woonkamer_energy_management_system_model_en_parameternauwkeurigheid",
            "extra_dip_marge_eur_per_kwh",
        ): 0.07,
        (
            "sensor.woonkamer_energy_management_system_model_en_parameternauwkeurigheid",
            "temperatuur_regressie_nauwkeurigheid_trend",
        ): {"richting": "dalend", "verschil_procent": -20.0},
        (
            "sensor.woonkamer_energy_management_system_model_en_parameternauwkeurigheid",
            "temperatuur_regressie_note",
        ): "Voorspeld 5.2 kWh bij -3.0°C, werkelijk 5.5 kWh (afwijking +5.8%).",
        (
            "sensor.woonkamer_energy_management_system_klimaat_projectie_woonkamertemperatuur",
            "traject",
        ): [
            {
                "tijd": "2026-08-06T08:00:00+02:00",
                "buitentemp_voorspeld_c": 17.1,
                "kort_termijn_temp_c": 23.8,
                "betrouwbaar_temp_c": 23.9,
                "betrouwbaarheid": "indicatief",
                "betrouwbaarheid_streng": "onvoldoende_data",
            },
            {
                "tijd": "2026-08-06T09:00:00+02:00",
                "buitentemp_voorspeld_c": 18.6,
                "kort_termijn_temp_c": 23.6,
                "betrouwbaar_temp_c": 23.9,
                "betrouwbaarheid": "betrouwbaar",
                "betrouwbaarheid_streng": "betrouwbaar",
            },
        ],
        (
            "sensor.woonkamer_energy_management_system_nilm_onbevestigde_kandidaten",
            "kandidaten",
        ): {
            "sensor.a": {"friendly_name": "IPTV Vermogen", "current_power_w": 3.0},
            "sensor.b": {"friendly_name": "Koelkast schuur", "current_power_w": 70.1},
        },
        (
            "sensor.woonkamer_energy_management_system_nilm_onbevestigde_kandidaten",
            "totaal_aantal",
        ): 51,
        (
            "sensor.woonkamer_energy_management_system_nilm_bevestigde_apparaten",
            "waarschijnlijke_duplicaten",
        ): [
            {
                "apparaat_1": "Eetkamer lamp 1 Power",
                "apparaat_2": "Eetkamer lamp 2 Power",
                "gedeelde_dagen": 20,
            },
        ],
        (
            "sensor.woonkamer_energy_management_system_system_status",
            "aandachtspunten",
        ): [
            "51 apparaat/apparaten mogelijk defect: CV-ketel Vermogen.",
            "18 waarschijnlijke NILM-duplicaatpaar/paren gevonden.",
        ],
    }
    return fake_data.get((entity, attr))


def _as_timestamp(value):
    from datetime import datetime

    if isinstance(value, str):
        return datetime.fromisoformat(value).timestamp()
    return value


def _timestamp_custom(value, fmt):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value, tz=timezone.utc).strftime(fmt)


def _as_datetime(value):
    from datetime import datetime

    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _relative_time(value):
    """Minimal fake of HA's relative_time() - exact wording doesn't
    matter here, just that it doesn't error and produces something."""
    return "3 dagen"


def _iter_all_cards(data):
    """Yield every card in the dashboard, whether the view uses a flat
    `cards:` list or a `type: sections` layout with `sections: [{cards:
    [...]}]`."""
    for view in data["views"]:
        if "cards" in view:
            yield from view["cards"]
        for section in view.get("sections", []):
            yield from section.get("cards", [])


def _render_markdown_cards():
    with open(DASHBOARD_PATH) as f:
        data = yaml.safe_load(f)

    env = Environment()
    # v1.6.7: `now()` is een Home Assistant-hulpfunctie die Jinja zelf
    # niet kent. Zonder deze stub loopt elk sjabloon dat hem gebruikt
    # stuk op "now is undefined" - en dan toetst deze test de opmaak van
    # die kaart helemaal niet meer.
    env.globals["now"] = lambda: datetime(2026, 8, 7, 12, 0)
    env.globals["as_timestamp"] = _as_timestamp
    env.filters["timestamp_custom"] = _timestamp_custom
    env.globals["as_datetime"] = _as_datetime
    env.globals["relative_time"] = _relative_time
    rendered = {}
    for i, card in enumerate(_iter_all_cards(data)):
        if card.get("type") == "markdown":
            title = card.get("title") or f"(untitled #{i})"
            rendered[title] = env.from_string(card["content"]).render(
                state_attr=_fake_state_attr
            )
    return rendered


def test_dashboard_yaml_is_valid():
    with open(DASHBOARD_PATH) as f:
        data = yaml.safe_load(f)
    assert len(data["views"]) == 15


def test_markdown_tables_have_no_blank_lines_between_rows():
    rendered = _render_markdown_cards()

    for title, content in rendered.items():
        lines = content.split("\n")
        for i, line in enumerate(lines[:-1]):
            stripped = line.strip()
            next_stripped = lines[i + 1].strip()
            # A blank line between two table rows (both starting with '|')
            # breaks the table - this is exactly the bug that was found.
            if stripped.startswith("|") and next_stripped == "":
                # allow a blank line only if what follows isn't a table row
                if i + 2 < len(lines) and lines[i + 2].strip().startswith("|"):
                    raise AssertionError(
                        f"'{title}': blank line between table rows at "
                        f"line {i} - this breaks Markdown table rendering. "
                        f"Rendered output:\n{content}"
                    )


def test_markdown_tables_have_a_header_and_separator_on_their_own_lines():
    """The header row and the |---|---| separator must each be on their
    own line, immediately following each other - if YAML folding merges
    them onto one line, Markdown won't recognise it as a table at all."""
    rendered = _render_markdown_cards()

    for title, content in rendered.items():
        if "|---" not in content:
            continue
        lines = [line.strip() for line in content.split("\n")]
        separator_lines = [line for line in lines if re.fullmatch(r"\|[-:| ]+\|", line)]
        assert separator_lines, f"'{title}': no standalone separator row found"
        for sep in separator_lines:
            idx = lines.index(sep)
            assert lines[idx - 1].startswith("|"), (
                f"'{title}': separator row not immediately preceded by a "
                f"header row on its own line"
            )
