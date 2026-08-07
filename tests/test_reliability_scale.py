"""Eén betrouwbaarheidsschaal voor alle gegenereerde data (v1.3.0).

Gevraagd: "ik wil dit eigenlijk voor vele data welke wordt gecreeerd,
hoe betrouwbaar is de gegenereerde data".

Een inventarisatie vond VIJF woordenlijsten naast elkaar voor in wezen
dezelfde vraag, en 40 van de 56 sensoren zonder enige aanduiding -
waaronder het geleerde accu-rendement, dat wél meerekent in de
extra-dip-laadbeslissing.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    RELIABILITY_ALIASES,
    RELIABILITY_INDICATIVE,
    RELIABILITY_INSUFFICIENT,
    RELIABILITY_LABELS,
    RELIABILITY_LADDER,
    RELIABILITY_NOT_CONFIGURED,
    RELIABILITY_RELIABLE,
    RELIABILITY_UNRELIABLE,
    RELIABILITY_UNVERIFIABLE,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


# --- de schaal zelf --------------------------------------------------


def test_every_level_has_a_label_and_explanation():
    """Een niveau zonder uitleg is niet te gebruiken."""
    for niveau, (label, uitleg) in RELIABILITY_LABELS.items():
        assert label and uitleg and len(uitleg) > 20, niveau


def test_every_old_word_maps_onto_the_scale():
    """De vertaling moet volledig zijn - een niet-vertaald woord zou een
    zesde woordenlijst introduceren."""
    for oud, nieuw in RELIABILITY_ALIASES.items():
        assert nieuw in RELIABILITY_LABELS, oud


def test_the_ladder_excludes_the_two_outsiders():
    """`niet_geconfigureerd` en `niet_toetsbaar` horen niet op de ladder:
    het eerste betekent "er is niets", het tweede "er valt principieel
    niets tegen af te zetten". Ze erop zetten zou suggereren dat ze met
    wachten beter worden - precies de verwarring die het oude
    "structureel_beschikbaar" opriep."""
    assert RELIABILITY_NOT_CONFIGURED not in RELIABILITY_LADDER
    assert RELIABILITY_UNVERIFIABLE not in RELIABILITY_LADDER
    assert list(RELIABILITY_LADDER) == [
        RELIABILITY_INSUFFICIENT,
        RELIABILITY_INDICATIVE,
        RELIABILITY_RELIABLE,
    ]


# --- vertaling -------------------------------------------------------


def test_translation_of_each_old_vocabulary(make_coordinator, hass):
    c = make_coordinator({})

    assert c.normalise_reliability("klaar") == RELIABILITY_RELIABLE
    assert c.normalise_reliability("goed") == RELIABILITY_RELIABLE
    assert c.normalise_reliability("betrouwbaar") == RELIABILITY_RELIABLE
    assert c.normalise_reliability("volgt_de_tick") == RELIABILITY_RELIABLE
    assert c.normalise_reliability("slecht") == RELIABILITY_UNRELIABLE
    assert c.normalise_reliability("kwaliteit_te_laag") == RELIABILITY_UNRELIABLE
    assert (
        c.normalise_reliability("structureel_beschikbaar")
        == RELIABILITY_UNVERIFIABLE
    )


def test_none_becomes_not_configured(make_coordinator, hass):
    c = make_coordinator({})

    assert c.normalise_reliability(None) == RELIABILITY_NOT_CONFIGURED


def test_an_unknown_word_is_treated_as_insufficient(make_coordinator, hass):
    """Conservatief: liever "nog niet hard" dan ten onrechte
    "betrouwbaar"."""
    c = make_coordinator({})

    assert c.normalise_reliability("iets_nieuws") == RELIABILITY_INSUFFICIENT


# --- oordeel op basis van aantal metingen ----------------------------


def test_below_the_minimum_is_insufficient(make_coordinator, hass):
    c = make_coordinator({})

    oordeel = c.reliability_from_samples(2, 5, 20, "laadcycli")

    assert oordeel["niveau"] == RELIABILITY_INSUFFICIENT
    assert "2/5" in oordeel["reden"]


def test_between_the_thresholds_is_indicative(make_coordinator, hass):
    c = make_coordinator({})

    oordeel = c.reliability_from_samples(10, 5, 20, "laadcycli")

    assert oordeel["niveau"] == RELIABILITY_INDICATIVE
    assert "betrouwbaar vanaf 20" in oordeel["reden"]


def test_above_the_threshold_is_reliable(make_coordinator, hass):
    c = make_coordinator({})

    assert c.reliability_from_samples(25, 5, 20)["niveau"] == RELIABILITY_RELIABLE


def test_no_data_is_not_configured(make_coordinator, hass):
    c = make_coordinator({})

    assert (
        c.reliability_from_samples(None, 5, 20)["niveau"]
        == RELIABILITY_NOT_CONFIGURED
    )


def test_the_unit_appears_in_the_reason(make_coordinator, hass):
    """"3/14 nachten" leest anders dan "3/14 metingen" - en dat verschil
    bepaalt of je begrijpt hoe lang je nog moet wachten."""
    c = make_coordinator({})

    assert "nachten" in c.reliability_from_samples(3, 14, 30, "nachten")["reden"]


# --- het overzicht ---------------------------------------------------


def test_the_overview_speaks_one_language(make_coordinator, hass):
    """De kern: alles wat erin staat moet een niveau uit de schaal
    hebben, niet uit een van de oude woordenlijsten."""
    c = make_coordinator({})
    c._update_advisory_readiness(NOW)

    for rij in c.get_reliability_overview():
        assert rij["niveau"] in RELIABILITY_LABELS, rij


def test_the_overview_covers_the_learned_values(make_coordinator, hass):
    """Deze hadden tot v1.2.0 helemaal geen oordeel."""
    c = make_coordinator({})

    namen = {rij["naam"] for rij in c.get_reliability_overview()}

    for verwacht in (
        "Accu-rendement",
        "Nachtverbruik",
        "Uurlijks verbruiksprofiel",
        "PV-voorspelling bias",
    ):
        assert verwacht in namen


def test_learned_efficiency_reports_its_maturity(make_coordinator, hass):
    """Het rendement rekent mee in de extra-dip-laadbeslissing, maar liet
    nergens zien of het op zeven of op zeventig metingen rustte."""
    c = make_coordinator({})
    c.learned_efficiency_history = [0.85] * 8

    rij = next(
        r for r in c.get_reliability_overview() if r["naam"] == "Accu-rendement"
    )

    assert rij["niveau"] == RELIABILITY_INDICATIVE
    assert rij["waarde"] == 85.0


def test_every_row_has_a_readable_label(make_coordinator, hass):
    c = make_coordinator({})
    c._update_advisory_readiness(NOW)

    for rij in c.get_reliability_overview():
        assert rij["label"] and rij["label"] != "?"


def test_advisory_modules_appear_in_the_new_language(make_coordinator, hass):
    """MPC staat op "structureel_beschikbaar"; in de schaal hoort dat
    "niet toetsbaar" te zijn."""
    c = make_coordinator({})
    c.mpc_horizon_quarters_used = 96
    c._update_advisory_readiness(NOW)

    rij = next(r for r in c.get_reliability_overview() if r["naam"] == "mpc")

    assert rij["niveau"] == RELIABILITY_UNVERIFIABLE


def test_the_tab_exists_and_shows_the_scale():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    titels = [v["title"] for v in data["views"]]

    assert "Betrouwbaarheid" in titels
