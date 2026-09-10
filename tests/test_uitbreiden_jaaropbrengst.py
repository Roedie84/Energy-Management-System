"""De jaaropbrengst van de accu (v4.9).

Gemeld met een schermafdruk van "Loont uitbreiden?":

    Opbrengst accu per jaar        1222.0 EUR
    Opbrengst extra module         204.0 EUR/jaar
    Terugverdientijd module        3.6 jaar
    Terugverdientijd omvormer      1.8 jaar

De berekening was:

    dagen_gemeten = max(1, len(self.reserve_daily_records))
    voordeel      = counterfactual_cost_all_time - actual_cost_all_time
    per_jaar      = voordeel / dagen_gemeten * 365

`reserve_daily_records` wordt op zeven dagen afgekapt
(LEARNING_HISTORY_DAYS) - dat is het venster voor de tekortdagen, en
daarom staat er op dezelfde kaart "Tekort-nachten 6 van 7". Maar
`voordeel` is de ALLE-TIJDEN besparing. De opbrengst van maanden werd
dus door zeven gedeeld en met 365 vermenigvuldigd.

Erger: het loopt weg. De teller groeit met elke dag, de deler blijft
zeven. Na een jaar zou er iets van 2800 EUR staan.

De juiste deler is het aantal dagen sinds `first_seen_date` - dat veld
bestaat al en wordt elders voor precies dit doel gebruikt (de
kalenderveroudering in de slijtageberekening).
"""
from datetime import date, datetime, timezone

import pytest


def _situatie(c, hass, dagen_geleden, voordeel_eur):
    from custom_components.energy_management_system import coordinator as mod

    nu = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu
    c.first_seen_date = nu.date() - __import__("datetime").timedelta(days=dagen_geleden - 1)
    c.counterfactual_cost_all_time_eur = voordeel_eur
    c.actual_cost_all_time_eur = 0.0
    c.reserve_daily_records = [
        {"date": f"d{i}", "shortfall": False, "excess": False} for i in range(7)
    ]


def test_de_deler_is_de_looptijd_niet_het_venster(make_coordinator, hass):
    """161 dagen, 72 euro besparing: dat is 163 EUR/jaar, niet 3754."""
    c = make_coordinator({})
    _situatie(c, hass, dagen_geleden=161, voordeel_eur=72.0)

    per_jaar = c._opbrengst_accu_per_jaar_eur()

    assert per_jaar == pytest.approx(72.0 / 161 * 365, abs=0.5)
    assert 150 < per_jaar < 180


def test_het_getal_loopt_niet_weg(make_coordinator, hass):
    """Twee keer zo lang met dezelfde dagopbrengst geeft hetzelfde
    jaarcijfer - dat was juist wat er misging."""
    c = make_coordinator({})
    _situatie(c, hass, dagen_geleden=100, voordeel_eur=45.0)
    kort = c._opbrengst_accu_per_jaar_eur()
    _situatie(c, hass, dagen_geleden=200, voordeel_eur=90.0)
    lang = c._opbrengst_accu_per_jaar_eur()

    assert kort == pytest.approx(lang, abs=0.5)


def test_te_kort_gemeten_geeft_geen_jaarcijfer(make_coordinator, hass):
    """Een week extrapoleren naar een jaar zegt niets - de winter zit er
    niet in."""
    from custom_components.energy_management_system.const import (
        JAAROPBRENGST_MIN_DAGEN,
    )

    c = make_coordinator({})
    _situatie(c, hass, dagen_geleden=JAAROPBRENGST_MIN_DAGEN - 1, voordeel_eur=10.0)

    assert c._opbrengst_accu_per_jaar_eur() is None


def test_zonder_startdatum_geen_jaarcijfer(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c, hass, dagen_geleden=161, voordeel_eur=72.0)
    c.first_seen_date = None

    assert c._opbrengst_accu_per_jaar_eur() is None


def test_de_kaart_noemt_de_looptijd(make_coordinator, hass):
    """Een jaarcijfer uit 161 dagen is een extrapolatie; dat hoort er te
    staan."""
    c = make_coordinator({})
    _situatie(c, hass, dagen_geleden=161, voordeel_eur=72.0)
    c.hourly_consumption_profile = {h: [0.4] * 7 for h in range(24)}
    c.bruikbare_capaciteit_kwh = lambda: 8.64

    uit = c.get_expansion_advice()

    assert uit.get("gemeten_dagen") == 161
    assert "161" in str(uit.get("jaaropbrengst_toelichting", ""))
