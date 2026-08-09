"""De export mag nooit een 500 geven (v1.19.4).

Gemeld: de download leverde een "500 Internal Server Error" op, en:
"ik had nu ook ergens een melding verwacht dat het systeem niet correct
functioneert."

Twee gaten:

1. De afscherming van v1.19.3 ving fouten in de AANROEPEN, maar Home
   Assistant serialiseert het resultaat pas daarna. Zit er een waarde in
   die JSON niet aankan, dan mislukt dat alsnog - en dan krijg je een
   foutpagina in plaats van een bestand.

2. Afschermen zonder melden laat een storing stil doorlopen. Dat is
   precies de fout die het afschermen moest voorkomen, één laag hoger.
"""
import json
from datetime import date, datetime, timezone

from custom_components.energy_management_system.diagnostics import _json_veilig


# --- serialisatie ----------------------------------------------------


def test_dates_become_text():
    assert _json_veilig(date(2026, 8, 10)) == "2026-08-10"
    assert _json_veilig(
        datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
    ).startswith("2026-08-10T09:00")


def test_sets_become_lists():
    assert sorted(_json_veilig({3, 1, 2})) == [1, 2, 3]


def test_unknown_objects_become_text():
    """Liever een leesbare tekenreeks dan geen bestand."""

    class Raar:
        def __str__(self):
            return "een raar object"

    assert _json_veilig(Raar()) == "een raar object"


def test_nested_values_are_handled():
    """Eén verkeerd type diep in een structuur zou de hele export
    slopen."""
    resultaat = _json_veilig({"a": [{"b": date(2026, 1, 1)}]})

    assert resultaat == {"a": [{"b": "2026-01-01"}]}


def test_normal_values_stay_themselves():
    """De vangnet mag geen getallen in tekst veranderen."""
    for waarde in (None, True, 42, 1.5, "tekst"):
        assert _json_veilig(waarde) == waarde


def test_non_string_keys_become_strings():
    """JSON kent alleen tekstsleutels."""
    assert _json_veilig({42: "x"}) == {"42": "x"}


def test_the_whole_export_passes_through_it():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "return _json_veilig(diagnostics)" in bron


# --- melden in plaats van stil afschermen ----------------------------


def _met_fout(make_coordinator):
    import custom_components.energy_management_system.sensor as m

    klasse = next(
        getattr(m, naam)
        for naam in dir(m)
        if "acs" in naam.lower() and naam.endswith("Sensor")
    )
    c = make_coordinator({})

    def stuk():
        raise KeyError("gesimuleerd")

    c.get_pv_forecast_quality = stuk
    klasse(c, "x").extra_state_attributes
    return c


def test_a_failure_is_recorded(make_coordinator, hass):
    c = _met_fout(make_coordinator)

    assert "pv_voorspelkwaliteit" in c.internal_failures
    assert "KeyError" in c.internal_failures["pv_voorspelkwaliteit"]


def test_a_failure_becomes_a_finding(make_coordinator, hass):
    """Afschermen zonder melden laat een storing stil doorlopen."""
    c = _met_fout(make_coordinator)

    bevinding = next(
        b for b in c.get_self_evaluation() if "falen" in b["onderwerp"]
    )

    assert "pv_voorspelkwaliteit" in bevinding["bewijs"]
    assert "vangnettekst" in bevinding["voorstel"]


def test_a_healthy_system_reports_nothing(make_coordinator, hass):
    """Melden waar niets aan de hand is, maakt de melding waardeloos."""
    c = make_coordinator({})

    assert not any(
        "falen" in b["onderwerp"] for b in c.get_self_evaluation()
    )


def test_the_failures_are_in_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "internal_failures" in bron
