""""Accu haalt de nacht niet" was vooral vals alarm (v5.13).

Gevraagd: *"Heb je nog meer zaken gevonden?"* De sensor Meldingen stond
live op precies 200. Dat bleek de afkapgrens van de meldingengeschiedenis
- zodra die vol is, staat er altijd 200. En daarachter:

    verstuurd per dag:  18  30  12  19  23  20  20

In v4.16 gingen we van 28 naar 13 per dag. Het was teruggekropen naar
ongeveer twintig, en de sensor die dat had moeten tonen, stond vast.

De grootste post: `battery_wont_last_night`, 3,2 keer per dag - en
binnen één nacht telkens opnieuw:

    18 sep  18:28 -> 21:28 -> 23:20 -> 00:00 -> ...
            180 min    112 min    40 min

TWEE FOUTEN:

1. De waarschuwing vergeleek het beschikbare met de reserve INCLUSIEF
   veiligheidsmarge. Op 18 september 06:58:

       beschikbaar         1,21 kWh
       nodig (met marge)   2,43 kWh   -> "haalt de nacht niet"
       nodig (werkelijk)   1,52 kWh   -> onder de drempel

   En de accu haalde die nacht met 18% over. De marge stond op 60% -
   zelf al opgeblazen door de valse tekortdagen van v5.7. Een dubbele
   opblazing. De marge is er om te STUREN, niet om te waarschuwen.

2. Geen hysterese. Een herstelmelding wist het dempingsvenster van de
   probleemmelding, zodat een terugkerend probleem direct weer gemeld
   wordt. Met één grens voor beide kant op zweefde het tekort 's nachts
   eromheen: probleem, herstel, probleem, herstel. Twee meldingen per
   wissel, over dezelfde vraag.

Nu vergelijkt de waarschuwing met wat er werkelijk nodig is, en herstelt
hij pas als er ook echt genoeg is.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 18, 6, 58, tzinfo=timezone.utc)


def _situatie(c, beschikbaar, met_marge, ruw, actief=False):
    c.last_available_kwh = beschikbaar
    c.last_needed_kwh_to_bridge = met_marge
    c.last_reserve_margin_breakdown = {
        "needed_kwh_before_margin": ruw,
        "reserve_kwh_after_margin": met_marge,
    }
    c.notification_active_conditions = (
        ["battery_wont_last_night"] if actief else []
    )


def _verstuurd(c):
    gestuurd = []
    c._dispatch_notification = lambda **kw: gestuurd.append(kw.get("kind"))
    return gestuurd


def test_de_marge_alleen_geeft_geen_nachtwaarschuwing(make_coordinator, hass):
    """Het gemeten geval van 18 september 06:58."""
    c = make_coordinator({})
    _situatie(c, beschikbaar=1.21, met_marge=2.43, ruw=1.52)
    gestuurd = _verstuurd(c)

    c._evaluate_new_notifications(NU)

    assert "battery_wont_last_night" not in gestuurd


def test_een_echt_tekort_geeft_wel_een_waarschuwing(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c, beschikbaar=0.4, met_marge=2.4, ruw=1.5)
    gestuurd = _verstuurd(c)

    c._evaluate_new_notifications(NU)

    assert "battery_wont_last_night" in gestuurd


def test_een_actieve_waarschuwing_blijft_staan_zolang_er_te_weinig_is(make_coordinator, hass):
    """De hysterese: net onder de drempel is nog geen herstel. Pas als er
    werkelijk genoeg is, gaat hij uit - anders wisselt hij de hele nacht."""
    c = make_coordinator({})
    # tekort 0,3 kWh: onder de drempel van 0,5, maar nog steeds te weinig
    _situatie(c, beschikbaar=1.2, met_marge=2.4, ruw=1.5, actief=True)
    gestuurd = _verstuurd(c)

    c._evaluate_new_notifications(NU)

    assert "battery_wont_last_night" in c.notification_active_conditions


def test_pas_bij_genoeg_volgt_het_herstel(make_coordinator, hass):
    """Het herstel heeft al een bevestigingstijd - een toestand moet een
    tijdje weg zijn. Mijn eerste versie van deze toets keek na een ronde;
    het gedrag was goed, de toets niet."""
    from custom_components.energy_management_system.const import (
        HERSTEL_BEVESTIGING_MINUTEN,
    )

    c = make_coordinator({})
    _situatie(c, beschikbaar=1.8, met_marge=2.4, ruw=1.5, actief=True)
    _verstuurd(c)

    # de voorwaarde is weg: eerst gezien, dan na de bevestigingstijd
    # opnieuw - met een eigen klok, niet die van de rest van de reeks
    c._dispatch_recovery_notifications([], now=NU)
    c._dispatch_recovery_notifications(
        [], now=NU + timedelta(minutes=HERSTEL_BEVESTIGING_MINUTEN + 1)
    )

    assert "battery_wont_last_night" not in c.notification_active_conditions


def test_zonder_blok_in_zicht_geen_waarschuwing(make_coordinator, hass):
    """Geen nacht om te overbruggen: dan valt er niets te waarschuwen."""
    c = make_coordinator({})
    c.last_available_kwh = 0.3
    c.last_needed_kwh_to_bridge = None
    c.last_reserve_margin_breakdown = {}
    c.notification_active_conditions = []
    gestuurd = _verstuurd(c)

    c._evaluate_new_notifications(NU)

    assert "battery_wont_last_night" not in gestuurd


# --- de meldingensensor -------------------------------------------------


def test_de_meldingensensor_telt_de_laatste_24_uur(make_coordinator, hass, monkeypatch):
    """Hij toonde de lengte van de geschiedenis, en die wordt op 200
    afgekapt - dus stond hij vast op 200. Het aantal PER DAG was waar het
    in v4.16 om ging."""
    from custom_components.energy_management_system.sensor import (
        MeldingenSensor,
    )

    import custom_components.energy_management_system.sensor as sensormod

    # een vaste klok: in de volledige reeks liet een eerdere toets de klok
    # anders staan, en dan telde deze toets verkeerd
    nu = datetime(2026, 9, 21, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(sensormod.dt_util, "now", lambda: nu)
    c = make_coordinator({})
    c.notification_history = (
        [{"moment": (nu - timedelta(days=3)).isoformat(), "verstuurd": True}] * 180
        + [{"moment": (nu - timedelta(hours=2)).isoformat(), "verstuurd": True}] * 15
        + [{"moment": (nu - timedelta(hours=1)).isoformat(), "verstuurd": False}] * 5
    )
    s = MeldingenSensor(c, "x")

    assert s.native_value == 15
    assert s.extra_state_attributes["in_geschiedenis"] == 200
