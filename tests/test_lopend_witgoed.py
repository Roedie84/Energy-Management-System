"""Een lopende vaatwasser telt één keer mee, met wat er nog rest (v3.99.3).

Vervolg op v3.99.2. Daar werd de vaatwasser uit de correctieverhouding
gehaald, omdat viermaal het profiel over vier uur een afwas van een uur
tot een tekort van tien kilowattuur maakte. Sindsdien telt hij voor nul.
Beide fout; nul was minder fout.

Nu de eerlijke versie: een lopende cyclus heeft een geleerde energie en
een geleerde duur. Wat er nog rest, hoort er één keer bij - verspreid
over de tijd die de cyclus nog nodig heeft. Een oven zonder cyclus-
teller krijgt een vaste post voor het komende uur.

En onderweg gevonden: `geplande_witgoed_kwh_in_periode` (v1.61.0) werd
alleen aangeroepen in de TERUGVAL van de reserve, niet in de wandeling
zelf. "Telt mee in de reserve" gold dus alleen als het uurprofiel een gat
had. Nu in beide.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 2, 13, 37, tzinfo=timezone.utc)


def _vaatwasser_loopt(c, sinds_min, geleerd_kwh=1.2, geleerd_min=51.0, tot_nu_kwh=0.4):
    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: NU
    c._dishwasher_state = "actief"
    c._dishwasher_cycle_started_at = NU - timedelta(minutes=sinds_min)
    c.appliance_cycle_kwh = {"vaatwasser": geleerd_kwh}
    c.dishwasher_cycle_duration_history = [geleerd_min] * 3
    c._cyclus_energie_kwh = lambda naam, a, b: tot_nu_kwh
    c.last_heavy_load_source = "vaatwasser"


def test_wat_er_nog_rest_telt_mee(make_coordinator, hass):
    """Vaatwasser 20 minuten bezig, 0,4 van 1,2 kWh verbruikt: 0,8 rest."""
    c = make_coordinator({})
    _vaatwasser_loopt(c, sinds_min=20)

    kwh = c.lopend_witgoed_kwh_in_periode(NU, NU + timedelta(hours=2))

    assert kwh == pytest.approx(0.8, abs=0.05)


def test_verspreid_over_de_resterende_duur(make_coordinator, hass):
    """31 minuten rest; het eerste kwartier krijgt dus ongeveer de helft."""
    c = make_coordinator({})
    _vaatwasser_loopt(c, sinds_min=20)

    kwh = c.lopend_witgoed_kwh_in_periode(NU, NU + timedelta(minutes=15))

    assert 0.3 < kwh < 0.5


def test_na_de_cyclus_niets_meer(make_coordinator, hass):
    c = make_coordinator({})
    _vaatwasser_loopt(c, sinds_min=20)

    kwh = c.lopend_witgoed_kwh_in_periode(NU + timedelta(hours=1), NU + timedelta(hours=3))

    assert kwh == 0.0


def test_niet_meer_dan_de_cyclus_kost(make_coordinator, hass):
    """Verbruikte al meer dan geleerd: dan rest er niets, geen negatief."""
    c = make_coordinator({})
    _vaatwasser_loopt(c, sinds_min=60, tot_nu_kwh=1.5)

    assert c.lopend_witgoed_kwh_in_periode(NU, NU + timedelta(hours=2)) == 0.0


def test_een_oven_zonder_cyclusteller_krijgt_een_vaste_post(make_coordinator, hass):
    c = make_coordinator({})
    c.last_heavy_load_source = "oven"
    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: NU

    kwh = c.lopend_witgoed_kwh_in_periode(NU, NU + timedelta(hours=2))

    assert 0.5 <= kwh <= 1.5


def test_niets_actief_niets_erbij(make_coordinator, hass):
    c = make_coordinator({})
    c.last_heavy_load_source = None
    c._dishwasher_state = "rustend"

    assert c.lopend_witgoed_kwh_in_periode(NU, NU + timedelta(hours=2)) == 0.0


def test_de_wandeling_telt_lopend_en_gepland_witgoed_mee(make_coordinator, hass):
    """Het geleerde profiel zegt 0,3 kW; met een lopende vaatwasser van

    0,8 kWh en een geplande wasbeurt van 0,8 kWh hoort het diepste
    tekort ruim boven het kale profiel te liggen.
    """
    c = make_coordinator({})
    c.hourly_consumption_profile = {h: [0.3] * 7 for h in range(24)}
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c._get_smoothed_consumption_correction_ratio = lambda h: 1.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.8 if a <= NU + timedelta(minutes=30) < b or a < NU + timedelta(minutes=30) <= b else 0.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.8 if a <= NU + timedelta(hours=3) < b else 0.0

    tekort = c._estimate_worst_case_deficit_kwh(NU, NU + timedelta(hours=6))

    assert tekort == pytest.approx(6 * 0.3 + 0.8 + 0.8, abs=0.15)
