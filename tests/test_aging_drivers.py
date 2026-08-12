"""Wat veroudering versnelt, per dag geteld (v1.59.0).

Van een degradatiemodel is bewust afgezien: capaciteitsverlies is enkele
procenten per JAAR, en de capaciteitssensor is zelf een schatting die
met de temperatuur meebeweegt. Uit elf dagen valt daar niets uit af te
leiden.

Wat wél kan is de oorzaken meten: lang op hoge stand staan en hoge
celtemperatuur.
"""
from datetime import datetime, timedelta, timezone

NU = datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, stand=98.0, temp=31.0):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.accustand_procent = lambda: stand
    c.battery_module_live = [{"temperatuur_c": temp}]
    return c


def test_hours_at_a_high_level_are_counted(make_coordinator, hass):
    """De accu stond gisteren uren op 98% - dat is de belangrijkste
    versneller die je zelf kunt beïnvloeden."""
    c = _coordinator(make_coordinator, stand=98.0)

    c._update_verouderingsdrijvers(NU)
    c._update_verouderingsdrijvers(NU + timedelta(minutes=15))
    c._update_verouderingsdrijvers(NU + timedelta(minutes=30))

    assert c._veroudering_vandaag["uren_boven_hoge_stand"] == 0.5


def test_a_normal_level_counts_nothing(make_coordinator, hass):
    c = _coordinator(make_coordinator, stand=55.0)

    c._update_verouderingsdrijvers(NU)
    c._update_verouderingsdrijvers(NU + timedelta(minutes=15))

    assert "uren_boven_hoge_stand" not in c._veroudering_vandaag


def test_warm_cells_are_counted(make_coordinator, hass):
    """31 °C gemeten, 10,9 graden boven buiten - bij 1637 W laden
    verklaarbaar, maar wel de belangrijkste versneller."""
    c = _coordinator(make_coordinator, temp=31.0)

    c._update_verouderingsdrijvers(NU)
    c._update_verouderingsdrijvers(NU + timedelta(minutes=30))

    assert c._veroudering_vandaag["uren_boven_warme_temperatuur"] == 0.5
    assert c._veroudering_vandaag["hoogste_temperatuur_c"] == 31.0


def test_a_gap_is_not_counted(make_coordinator, hass):
    """Een gat betekent dat we niet weten wat er tussendoor gebeurde;
    dan liever niets tellen dan gokken."""
    c = _coordinator(make_coordinator)

    c._update_verouderingsdrijvers(NU)
    c._update_verouderingsdrijvers(NU + timedelta(hours=4))

    assert c._veroudering_vandaag.get("uren_boven_hoge_stand") is None


def test_the_day_is_closed_at_midnight(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c._update_verouderingsdrijvers(NU)
    c._update_verouderingsdrijvers(NU + timedelta(minutes=30))

    c._update_verouderingsdrijvers(NU + timedelta(days=1))

    assert len(c.veroudering_history) == 1
    assert c.veroudering_history[0]["uren_boven_hoge_stand"] == 0.5


def test_it_claims_nothing_about_the_future(make_coordinator, hass):
    """Geen voorspelling van capaciteitsverlies - dat vraagt jaren aan
    metingen. Alleen wat het versnelt."""
    c = _coordinator(make_coordinator)

    overzicht = c.get_aging_drivers()

    assert "VERSNELT" in overzicht["toelichting"]
    assert "niet voorspeld" in overzicht["toelichting"]
    assert overzicht["beschikbaar"] is False


def test_the_series_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "veroudering_history" in PERSISTED_PLAIN_FIELDS
