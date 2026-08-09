"""Wordt de PV-voorspelling daadwerkelijk gecorrigeerd? (v1.17.8)

Gevraagd: "Wordt de PV-verwachting nu wel daadwerkelijk gecorrigeerd of?"

Ja, en op drie niveaus - maar dat was nergens te zien. Een systeem kan
makkelijk iets meten zonder er iets mee te doen, en dan is die vraag
volstrekt terecht.

Deze tests leggen vast dat de correctie ook echt in de berekening landt,
niet alleen in een sensor staat.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent


class _Tracker:
    learned_bias_percent = -11.6


def _met_uurcorrecties(make_coordinator, correcties):
    c = make_coordinator({})
    c.solar_tracker = _Tracker()
    c.pv_hourly_bias_history = {
        uur: [factor] * 5 for uur, factor in correcties.items()
    }
    return c


# --- de correctie wordt toegepast ------------------------------------


def test_the_hourly_ratio_is_applied_to_the_forecast():
    """De kern: `_get_expected_pv_kwh` vermenigvuldigt het segment met
    de geleerde verhouding. Zonder die regel zou de correctie alleen
    getoond worden."""
    bron = (PAKKET / "coordinator.py").read_text()
    start = bron.index("hourly_ratio = self.learned_pv_hourly_ratio")
    blok = bron[start : start + 400]

    assert "segment_kwh *= hourly_ratio" in blok


def test_the_daily_bias_is_the_fallback():
    """Alleen als er voor dat uur nog geen uurcorrectie is."""
    bron = (PAKKET / "coordinator.py").read_text()
    start = bron.index("hourly_ratio = self.learned_pv_hourly_ratio")
    blok = bron[start : start + 400]

    assert "elif daily_bias_percent is not None" in blok
    assert "segment_kwh *= 1 + daily_bias_percent / 100" in blok


def test_todays_remaining_hours_are_rescaled():
    """Vandaag telt wat er al werkelijk is opgewekt zwaarder dan een
    geleerd gemiddelde."""
    bron = (PAKKET / "coordinator.py").read_text()

    assert "remaining_correction_ratio" in bron
    assert "segment_kwh *= remaining_correction_ratio" in bron


# --- de status is zichtbaar ------------------------------------------


def test_the_status_reports_the_hours_with_their_own_correction(
    make_coordinator, hass
):
    c = _met_uurcorrecties(
        make_coordinator, {6: 0.53, 7: 0.74, 10: 1.03, 13: 0.75, 20: 0.29}
    )

    status = c.get_pv_correction_status()

    assert status["actief"] is True
    assert status["uren_met_eigen_correctie"] == 5
    assert status["daggemiddelde_bias_procent"] == -11.6


def test_it_names_the_strongest_and_weakest_hour(make_coordinator, hass):
    """Het punt dat één daggemiddelde zou wegpoetsen: 's avonds wordt de
    voorspelling met 0,29 vermenigvuldigd, rond 10:00 met 1,03."""
    c = _met_uurcorrecties(
        make_coordinator, {6: 0.53, 10: 1.03, 20: 0.29}
    )

    status = c.get_pv_correction_status()

    assert status["sterkste_correctie"] == {"uur": 20, "factor": 0.29}
    assert status["zwakste_correctie"] == {"uur": 10, "factor": 1.03}


def test_it_explains_the_order(make_coordinator, hass):
    """De volgorde doet ertoe: vandaag eerst, dan per uur, dan het
    gemiddelde."""
    c = _met_uurcorrecties(make_coordinator, {10: 1.03})

    volgorde = c.get_pv_correction_status()["volgorde"]

    assert len(volgorde) == 3
    assert "resterende uren" in volgorde[0]
    assert "per uur" in volgorde[1]
    assert "daggemiddelde" in volgorde[2]


def test_it_says_when_nothing_is_learned_yet(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = None
    c.pv_hourly_bias_history = {}

    status = c.get_pv_correction_status()

    assert status["actief"] is False
    assert "ongewijzigd gebruikt" in status["toelichting"]


def test_it_states_that_it_is_actually_used(make_coordinator, hass):
    """Precies de vraag die gesteld werd: meten of ook toepassen?"""
    c = _met_uurcorrecties(make_coordinator, {10: 1.03})

    assert "niet alleen getoond" in c.get_pv_correction_status()["toelichting"]


# --- inbedding -------------------------------------------------------


def test_it_is_in_the_export():
    bron = (PAKKET / "diagnostics.py").read_text()

    assert "pv_correction_status" in bron


def test_it_is_on_the_pv_page():
    import yaml

    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    zon = next(v for v in data["views"] if v["path"] == "detail-zon")
    kaarten = [k for s in zon["sections"] for k in s.get("cards") or []]

    kaart = next(
        k for k in kaarten if "gecorrigeerd" in str(k.get("title", "")).lower()
    )

    assert "uren_met_eigen_correctie" in kaart["content"]
    assert "volgorde" in kaart["content"]
