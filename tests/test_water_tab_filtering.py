"""Waterverbruik: samenvatting in plaats van tabellen (v1.12.0).

Eerder gevraagd: gebruiksmomenten alleen van vandaag tonen,
daggeschiedenis alleen zeven dagen. Nu gemeld: "Ik vind de dashboards
veel te druk... Het de meeste info (tabellen) graag in een zin
weergeven."

Beide tabellen zijn daarom vervallen. De gegevens zelf blijven volledig
beschikbaar in de sensorattributen en de diagnostiek-export; alleen de
CONCLUSIE staat nog op het tabblad.
"""


def test_the_water_summary_is_one_sentence(make_coordinator, hass):
    c = make_coordinator({})
    c.water_sessions_today_count = 4
    c.water_daily_total_l = 82.3

    zin = c.get_topic_summaries()["water"]["zin"]

    assert "4 gebruiksmoment" in zin
    assert "82 liter" in zin
    # Eén zin, geen tabel.
    assert "|" not in zin and len(zin) < 120


def test_an_empty_day_still_produces_a_sentence(make_coordinator, hass):
    """Geen gebruik is ook informatie; een lege kaart zou lijken alsof
    de detectie stuk is."""
    c = make_coordinator({})

    zin = c.get_topic_summaries()["water"]["zin"]

    assert "0 gebruiksmoment" in zin


def test_the_underlying_sessions_are_still_recorded(make_coordinator, hass):
    """De tabel is weg, de gegevens niet - anders zou er in de
    diagnostiek-export niets meer te analyseren zijn."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "water_session_history" in bron
