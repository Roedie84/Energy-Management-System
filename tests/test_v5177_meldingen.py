"""v5.177.0 (B2) - stille uren, "Niets" naar het dagoverzicht, geen
tekortmeldingen onder het waardeplan."""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import CONF_APPLIANCE_NOTIFY_SERVICE

TZ = timezone(timedelta(hours=1))


@pytest.fixture
def c(make_coordinator, coordinator_cls):
    c = make_coordinator({CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon"})
    # de echte klokregel (conftest zet hem standaard uit)
    c._stille_uren = coordinator_cls._stille_uren.__get__(c)
    return c


def _stuur(c, kind, now):
    from custom_components.energy_management_system import coordinator as mod

    origineel = mod.dt_util.now
    mod.dt_util.now = lambda: now
    try:
        c._dispatch_notification("notify.telefoon", f"titel {kind}", "tekst", f"ems_{kind}", kind=kind)
    finally:
        mod.dt_util.now = origineel


def _pushes(hass):
    return [x for x in hass.services.calls if x[0] == "notify"]


def test_stille_uren_alleen_kritiek(c, hass):
    nacht = datetime(2026, 11, 4, 2, 0, tzinfo=TZ)
    _stuur(c, "sluipverbruik", nacht)
    assert _pushes(hass) == []
    assert c.notification_history[-1]["reden_niet_verstuurd"] == "stille uren"
    _stuur(c, "interne_fout", nacht)
    assert c.notification_history[-1]["verstuurd"] is True


def test_overdag_gaat_het_wel(c, hass):
    _stuur(c, "sluipverbruik", datetime(2026, 11, 4, 12, 0, tzinfo=TZ))
    assert c.notification_history[-1]["verstuurd"] is True


def test_niets_alleen_in_het_dagoverzicht(c, hass):
    dag = datetime(2026, 11, 4, 12, 0, tzinfo=TZ)
    c.set_notification_enabled("mode_change", True)
    _stuur(c, "mode_change", dag)
    assert _pushes(hass) == []
    assert c.notification_history[-1]["reden_niet_verstuurd"] == "alleen in het dagoverzicht"
    assert "titel mode_change" in c._dagoverzicht_meldingen(dag + timedelta(hours=10))
    # het dagoverzicht zelf gaat wel (ook al is zijn advies "Niets")
    assert c._push_tegenhouden("daily_summary", dag) is None


def test_herstel_volgt_het_advies_van_de_probleemmelding(c, hass):
    dag = datetime(2026, 11, 4, 12, 0, tzinfo=TZ)
    assert c._push_tegenhouden("battery_wont_last_night_hersteld", dag) == "alleen in het dagoverzicht"
    assert c._push_tegenhouden("sensor_unavailable_hersteld", dag) is None
    assert c._push_tegenhouden("sensor_unavailable_hersteld", dag.replace(hour=3)) is None
    assert c._push_tegenhouden("cost_mismatch_hersteld", dag.replace(hour=3)) == "stille uren"


def test_dagoverzicht_telt_compact(c):
    dag = datetime(2026, 11, 4, 12, 0, tzinfo=TZ)
    for i in range(3):
        c.notification_history.append({
            "moment": (dag + timedelta(minutes=i)).isoformat(), "soort": "mode_change",
            "titel": "Accu: slim", "reden_niet_verstuurd": "alleen in het dagoverzicht",
        })
    tekst = c._dagoverzicht_meldingen(dag + timedelta(hours=1))
    assert "Accu: slim (3x)" in tekst


def test_geen_nachttekort_onder_het_waardeplan(c):
    c._plan_volgt_waardeplan = lambda: True
    gestuurd = []
    c.last_available_kwh = 0.1
    c._nodig_tot_en_na_blok_kwh = lambda: (5.0, 0.0)
    c._meld_nacht_tekort(datetime(2026, 11, 4, 22, 0, tzinfo=TZ), lambda *a: gestuurd.append(a))
    assert gestuurd == []


def test_herstel_verdwijnt_stil_onder_het_waardeplan(c, hass):
    """Geen "Accu haalt de nacht weer" voor een melding die niet meer bestaat."""
    c._plan_volgt_waardeplan = lambda: True
    c.notification_active_conditions = ["battery_wont_last_night"]
    c._voorwaarde_weg_sinds = {"battery_wont_last_night": datetime(2026, 11, 4, 1, 0, tzinfo=TZ)}
    c._evaluate_new_notifications(datetime(2026, 11, 4, 12, 0, tzinfo=TZ))
    assert "battery_wont_last_night" not in c.notification_active_conditions
    assert not any(str(r.get("soort", "")).startswith("battery_wont_last_night") for r in c.notification_history)
