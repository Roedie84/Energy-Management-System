"""v5.99.4: dagoverzicht gecorrigeerd voor de accu-inhoud.

Gemeld 15-10 22:00: "Kosten 0.62 € tegenover 0.05 € zonder accu - dat scheelt
-0.57 €" terwijl de accu voor de ochtend was geladen.
"""
from test_notifications import _coordinator, _met_klok


def _bericht(c):
    return [m["bericht"] for m in c.notification_history if "Dagoverzicht" in m["titel"]][-1]


def test_dagoverzicht_telt_de_accu_mee(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("daily_summary", True)
    c.achterhoeks_meldingen = False
    c.config["achterhoeks_meldingen"] = False
    c.actual_cost_today_eur = 0.62
    c.counterfactual_cost_today_eur = 0.05
    c.get_savings_correction = lambda: {
        "correctie_beschikbaar": True, "voorraadwaarde_eur": 1.10, "voorraadverschil_kwh": 2.4,
    }
    _met_klok(c, uur=22)
    b = _bericht(c)
    assert "0.53" in b and "-0.57" in b and "+2.4 kWh" in b


def test_dagoverzicht_zonder_correctie(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("daily_summary", True)
    c.actual_cost_today_eur = 1.20
    c.counterfactual_cost_today_eur = 3.50
    c.get_savings_correction = lambda: {"correctie_beschikbaar": False}
    _met_klok(c, uur=22)
    assert "2.30" in _bericht(c)
