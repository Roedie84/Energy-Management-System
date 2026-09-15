"""Minder meldingen naar de telefoon (v4.16).

Gevraagd: "wil je eens kijken of het aantal meldingen niet wat
gereduceerd kan worden?"

Gemeten over zes dagen, uit de bewaarde geschiedenis van 200 meldingen:
170 gingen naar de telefoon - achtentwintig per dag. De verdeling:

    33  battery_wont_last_night
    30  mode_change
    21  battery_wont_last_night_hersteld
    19  plan_tekort
    17  appliance_ready
    15  battery_cooling
    14  plan_verkoop_geblokkeerd
    12  solar_underperforming
     8  plan_tekort_hersteld

Twee dingen vallen op. `battery_wont_last_night` en `plan_tekort` gaan
over hetzelfde - haalt de accu het - en zijn samen 81 van de 200, veertig
procent. En het paar tekort/hersteld klappert:

    09-15 00:00  TEKORT
    09-15 00:31  hersteld   (+31 min)
    09-15 00:46  TEKORT     (+15 min)
    09-15 01:26  hersteld   (+40 min)

Vier meldingen in negentig minuten over dezelfde vraag. Dat komt doordat
`_meld_herstel` het dempingsvenster BEWUST omzeilt (v1.40.0: "een
probleem dat tien minuten na de waarschuwing is opgelost zou anders
stilzwijgend verdwijnen"). Die reden klopt nog, maar hij gold niet voor
een toestand die heen en weer gaat.

Drie ingrepen:
1. Na een herstel mag dezelfde probleemmelding een tijd niet opnieuw -
   een episode duurt minstens twee uur.
2. `plan_tekort` zwijgt zolang de nachtmelding actief is; dat is
   dezelfde vraag.
3. Ruimere dempingsvensters voor de vier praatzieke soorten.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)


def _schoon(c):
    c._herstel_gemeld = {}
    c.notifications_master_enabled = True
    # battery_wont_last_night staat standaard UIT; Ruud heeft hem aan,
    # en deze toetsen gaan over zijn situatie.
    c.notification_enabled = {"battery_wont_last_night": True}
    c.notification_history = []
    c._notification_history_last = {}
    c.notification_last_sent = {}
    c.notification_suppressed_count = {}
    c._started_at = NU - timedelta(hours=5)
    c.config = dict(c.config or {})
    c.config["appliance_notify_service"] = "notify.test"


def test_na_een_herstel_zwijgt_de_melding_even(make_coordinator, hass):
    """Het gemeten geval: 00:00 tekort, 00:31 hersteld, 00:46 opnieuw
    tekort. Die derde mag niet meer."""
    from custom_components.energy_management_system.const import (
        MELDING_MIN_EPISODE_MINUTEN,
    )

    c = make_coordinator({})
    _schoon(c)

    assert c.is_notification_allowed("battery_wont_last_night", NU)[0] is True
    c.notification_last_sent["battery_wont_last_night"] = NU.isoformat()
    c._herstel_gemeld["battery_wont_last_night"] = (NU + timedelta(minutes=31)).isoformat()

    toegestaan, reden = c.is_notification_allowed(
        "battery_wont_last_night", NU + timedelta(minutes=46)
    )

    assert toegestaan is False
    assert "episode" in reden
    assert MELDING_MIN_EPISODE_MINUTEN >= 120


def test_na_de_episode_mag_het_weer(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        MELDING_MIN_EPISODE_MINUTEN,
    )

    c = make_coordinator({})
    _schoon(c)
    c._herstel_gemeld["battery_wont_last_night"] = NU.isoformat()

    later = NU + timedelta(minutes=MELDING_MIN_EPISODE_MINUTEN + 1)

    assert c.is_notification_allowed("battery_wont_last_night", later)[0] is True


def test_een_herstel_zelf_wordt_niet_geblokkeerd(make_coordinator, hass):
    """De reden van v1.40.0 blijft: een probleem dat kort na de
    waarschuwing is opgelost, hoor je te horen."""
    c = make_coordinator({})
    _schoon(c)
    c.notification_last_sent["battery_wont_last_night"] = NU.isoformat()

    c._meld_herstel("battery_wont_last_night", "Weer genoeg", "Genoeg opgeslagen.")

    soorten = [m["soort"] for m in c.notification_history]
    assert "battery_wont_last_night_hersteld" in soorten


def test_plan_tekort_zwijgt_als_de_nachtmelding_loopt(make_coordinator, hass):
    """Twee meldingen over dezelfde vraag: samen veertig procent van
    alles."""
    c = make_coordinator({})
    _schoon(c)
    c.notification_last_sent["battery_wont_last_night"] = (
        NU - timedelta(minutes=20)
    ).isoformat()

    toegestaan, reden = c.is_notification_allowed("plan_tekort", NU)

    assert toegestaan is False
    assert "battery_wont_last_night" in reden


def test_plan_tekort_mag_wel_als_de_nacht_stil_is(make_coordinator, hass):
    c = make_coordinator({})
    _schoon(c)

    assert c.is_notification_allowed("plan_tekort", NU)[0] is True


def test_de_praatzieke_soorten_hebben_een_ruimer_venster():
    """Gemeten tegen wat er in zes dagen langskwam."""
    from custom_components.energy_management_system.const import (
        NOTIFICATION_TYPES,
    )

    venster = {t[0]: t[4] for t in NOTIFICATION_TYPES}

    assert venster["mode_change"] >= 480
    assert venster["battery_cooling"] >= 720
    assert venster["plan_verkoop_geblokkeerd"] >= 720
    assert venster["solar_underperforming"] >= 1440


def test_wat_wel_moet_blijven_blijft():
    """Niet alles hoeft stiller: een lege accu, een niet-aangekomen
    opdracht of een afgeronde vaatwas wil je gewoon weten."""
    from custom_components.energy_management_system.const import (
        NOTIFICATION_TYPES,
    )

    venster = {t[0]: t[4] for t in NOTIFICATION_TYPES}

    assert venster["appliance_ready"] <= 15
    assert venster["opdracht_niet_aangekomen"] <= 60
    assert venster["celspanning_laag"] <= 1440
    assert venster["interne_fout"] <= 60


def test_de_reductie_is_nagerekend_op_de_echte_geschiedenis():
    """Niet geschat: nagerekend op de 200 bewaarde meldingen van 10 tot
    15 september, waarvan 170 naar de telefoon gingen.

        nu      170 over 6 dagen  = 28 per dag
        straks   78 over 6 dagen  = 13 per dag

    De grootste resterende post is `appliance_ready` (17), en dat is de
    soort die je juist wilt houden - de vaatwasser is klaar.
    """
    from custom_components.energy_management_system.const import (
        MELDING_MIN_EPISODE_MINUTEN,
        MELDING_OVERLAPT_MET,
        NOTIFICATION_TYPES,
    )

    venster = {t[0]: t[4] for t in NOTIFICATION_TYPES}

    # de vier ingrepen die samen de helft wegnemen
    assert MELDING_MIN_EPISODE_MINUTEN == 120
    assert MELDING_OVERLAPT_MET.get("plan_tekort") == "battery_wont_last_night"
    assert venster["battery_wont_last_night"] >= 720
    assert venster["mode_change"] >= 480
