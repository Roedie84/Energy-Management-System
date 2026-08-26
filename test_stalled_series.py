"""Stilstaande geleerde reeksen (v1.11.1).

Gevraagd: "kijken naar alle waarden welke gegenereerd worden en mogelijk
niet goed werken doordat ze lang stilstaan of juist al zo betrouwbaar
zijn dat ze niet meer wijzigen."

In een export stond `steelstofzuiger_idle_power_history_w` op acht keer
0,0. Een ruststroom van nul is volstrekt plausibel - een lader die niets
doet verbruikt niets - maar het is niet te onderscheiden van een meting
die stilletjes is gestopt. Beide zien er in de export identiek uit.
"""
from custom_components.energy_management_system.const import (
    STALLED_SERIES_CONSTANT_IS_NORMAL,
    STALLED_SERIES_MIN_SAMPLES,
)


# --- het onderscheid dat gevraagd werd -------------------------------


def test_a_constant_idle_power_is_expected(make_coordinator, hass):
    """Het gerapporteerde geval: acht keer 0,0 W ruststroom."""
    c = make_coordinator({})
    c.steelstofzuiger_idle_power_history_w = [0.0] * 8

    regel = next(
        r
        for r in c.get_stalled_series_report()
        if "steelstofzuiger" in r["reeks"]
    )

    assert regel["constante_is_normaal"] is True
    assert "geen aanwijzing dat er iets mis is" in regel["duiding"]


def test_a_constant_learned_value_is_suspect(make_coordinator, hass):
    """Het accu-rendement hoort per laadcyclus te verschillen. Blijft het
    identiek, dan kan de meting zijn gestopt."""
    c = make_coordinator({})
    c.learned_efficiency_history = [82.9] * 12

    regel = next(
        r
        for r in c.get_stalled_series_report()
        if r["reeks"] == "learned_efficiency_history"
    )

    assert regel["constante_is_normaal"] is False
    assert "hoort te fluctueren" in regel["duiding"]


def test_only_the_suspect_ones_are_reported(make_coordinator, hass):
    """Melden dat een ruststroom constant is, zou de melding waardeloos
    maken - dat is juist wat je verwacht."""
    c = make_coordinator({})
    c.steelstofzuiger_idle_power_history_w = [0.0] * 8
    c.learned_efficiency_history = [82.9] * 12

    meldingen = [
        p for p in c.get_diagnostic_summary()["informatief"] if "metingen op" in p
    ]

    assert len(meldingen) == 1
    assert "learned_efficiency_history" in meldingen[0]


# --- grenzen ---------------------------------------------------------


def test_a_varying_series_is_not_reported(make_coordinator, hass):
    c = make_coordinator({})
    c.learned_efficiency_history = [80.0, 82.0, 84.0] * 5

    assert not any(
        r["reeks"] == "learned_efficiency_history"
        for r in c.get_stalled_series_report()
    )


def test_a_short_series_is_not_judged(make_coordinator, hass):
    """Drie identieke waarden zegt niets; dat kan gewoon toeval zijn."""
    c = make_coordinator({})
    c.learned_efficiency_history = [82.9] * (STALLED_SERIES_MIN_SAMPLES - 1)

    assert c.get_stalled_series_report() == []


def test_the_sample_count_is_included(make_coordinator, hass):
    """Acht identieke waarden zegt weinig, tachtig zegt veel - dus het
    aantal hoort erbij."""
    c = make_coordinator({})
    c.learned_efficiency_history = [82.9] * 40

    regel = next(
        r
        for r in c.get_stalled_series_report()
        if r["reeks"] == "learned_efficiency_history"
    )

    assert regel["metingen"] == 40


def test_booleans_are_not_treated_as_numbers(make_coordinator, hass):
    """Een lijst van True/False "staat stil" per definitie vaak en is
    geen meetreeks - die hoort niet als verdacht te gelden."""
    c = make_coordinator({})
    c.iets_history = [False] * 20

    assert not any(
        r["reeks"] == "iets_history" for r in c.get_stalled_series_report()
    )


def test_the_exception_list_is_explicit():
    """Wie hier iets aan toevoegt moet kunnen uitleggen waarom stilstand
    daar te verwachten is, in plaats van dat het stilzwijgend
    meeglipt."""
    assert len(STALLED_SERIES_CONSTANT_IS_NORMAL) <= 5
    for fragment in STALLED_SERIES_CONSTANT_IS_NORMAL:
        assert "history" in fragment or "duration" in fragment


def test_it_is_in_the_diagnostics_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "stalled_series" in bron


# --- v1.14.3: interne velden werden overgeslagen --------------------


def test_underscore_fields_are_checked(make_coordinator, hass):
    """In een export stond `_steelstofzuiger_idle_power_history` op tien
    identieke waarden terwijl het rapport leeg bleef - precies de reeks
    waarvoor deze controle is gemaakt.

    De detectie sloeg alles over dat met een underscore begon. Interne
    naamgeving zegt niets over of een reeks het bewaken waard is; wat
    telt is of het een meetreeks is.
    """
    c = make_coordinator({})
    c._steelstofzuiger_idle_power_history = [0.0] * 10

    reeksen = {r["reeks"] for r in c.get_stalled_series_report()}

    assert "steelstofzuiger_idle_power_history" in reeksen


def test_the_exception_matches_the_internal_name(make_coordinator, hass):
    """Het fragment moet op de ECHTE veldnaam passen. Het stond op
    "idle_power_history_w", maar dat achtervoegsel wordt pas in de
    export toegevoegd - waardoor een verwachte constante toch als
    verdacht gold."""
    c = make_coordinator({})
    c._steelstofzuiger_idle_power_history = [0.0] * 10

    regel = next(
        r
        for r in c.get_stalled_series_report()
        if "steelstofzuiger" in r["reeks"]
    )

    assert regel["constante_is_normaal"] is True


def test_dunder_fields_are_still_skipped(make_coordinator, hass):
    """Python-interne velden (`__dict__` en dergelijke) zijn geen
    meetreeksen."""
    c = make_coordinator({})

    for regel in c.get_stalled_series_report():
        assert not regel["reeks"].startswith("_")


# --- v1.15.4: werkbuffers zijn geen meetreeksen ---------------------


def test_a_working_buffer_is_not_reported(make_coordinator, hass):
    """Gemeld: "balance_power_samples staat al 27 metingen op -0.0."

    Dat is een werkbuffer die accuvermogens verzamelt tussen twee
    balanscontroles en zichzelf daarna leegt - geen geleerde reeks.
    27x -0,0 W betekent daar gewoon dat de accu stilstond, wat 's nachts
    bij een volle accu volstrekt normaal is.

    Deze meldingen kwamen binnen door de correctie van v1.14.3, waarin
    underscore-velden werden meegenomen om
    `_steelstofzuiger_idle_power_history` te vinden.
    """
    c = make_coordinator({})
    c._balance_power_samples = [-0.0] * 27

    reeksen = {r["reeks"] for r in c.get_stalled_series_report()}

    assert "balance_power_samples" not in reeksen


def test_real_series_are_still_found(make_coordinator, hass):
    """De uitsluiting mag de detectie niet uithollen."""
    c = make_coordinator({})
    c._balance_power_samples = [-0.0] * 27
    c._steelstofzuiger_idle_power_history = [0.0] * 10
    c.learned_efficiency_history = [82.9] * 12

    reeksen = {r["reeks"] for r in c.get_stalled_series_report()}

    assert "steelstofzuiger_idle_power_history" in reeksen
    assert "learned_efficiency_history" in reeksen


def test_the_distinction_is_in_the_name():
    """Een reeks die iets LEERT heet `_history` of `_records`; een buffer
    heet `_samples` of `_buffer`. Dat onderscheid staat in de naamgeving
    en is daarmee te controleren zonder elke reeks apart te kennen."""
    from custom_components.energy_management_system.const import (
        STALLED_SERIES_WORKING_BUFFERS,
    )

    for fragment in STALLED_SERIES_WORKING_BUFFERS:
        assert fragment.startswith("_")
        assert "history" not in fragment
        assert "records" not in fragment
