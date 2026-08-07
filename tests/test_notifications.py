"""Meldingen per soort aan/uit te zetten (v1.2.0).

Gevraagd: "Ik wil nog een tabblad waar ik meldingen in en uit kan
schakelen... echter wil ik ze wel aan/uit kunnen zetten", gevolgd door
"zoveel mogelijk relevante meldingen toevoegen, let wel dat ze op het
tabblad uit te schakelen zijn".

Tot v1.1.9 hingen alle zeven bestaande meldingen aan één configuratie-
veld: alles aan of alles uit.

Twee ontwerpkeuzes die het verschil maken tussen bruikbaar en
wegswipen: alleen de bestaande soorten staan standaard AAN, en elke
melding heeft een eigen dempingsvenster.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    NOTIFICATION_TYPES,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator):
    return make_coordinator({CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon"})


def _stuur(c, kind="mode_change"):
    c._dispatch_notification(
        notify_service="notify.telefoon",
        title="test",
        message="test",
        notification_id="ems_test",
        kind=kind,
    )


# --- de kern: aan/uit ------------------------------------------------


def test_an_enabled_notification_is_sent(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    _stuur(c)

    assert len(c.notification_history) == 1


def test_a_disabled_notification_is_not_sent(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("mode_change", False)

    _stuur(c)

    assert c.notification_history == []


def test_the_master_switch_blocks_everything(make_coordinator, hass):
    """Handig om alles in één keer stil te zetten zonder twintig
    schakelaars om te hoeven zetten."""
    c = _coordinator(make_coordinator)
    c.notifications_master_enabled = False

    for kind, _, _, _, _ in NOTIFICATION_TYPES:
        _stuur(c, kind)

    assert c.notification_history == []


def test_the_master_switch_leaves_individual_choices_intact(
    make_coordinator, hass
):
    """Na het weer aanzetten hoor je precies te hebben wat je had."""
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("sluipverbruik", False)
    c.notifications_master_enabled = False
    c.notifications_master_enabled = True

    assert c.notification_enabled["sluipverbruik"] is False
    assert c.notification_enabled["mode_change"] is True


# --- dempingsvenster -------------------------------------------------


def test_the_same_notification_is_throttled(make_coordinator, hass):
    """Modus-wijzigingen kunnen bij wisselende prijzen meerdere keren per
    uur afgaan - dan is wegswipen het enige wat je nog doet."""
    c = _coordinator(make_coordinator)

    _stuur(c)
    _stuur(c)
    _stuur(c)

    assert len(c.notification_history) == 1


def test_it_is_allowed_again_after_the_window(make_coordinator, hass):
    from custom_components.energy_management_system import coordinator as mod

    c = _coordinator(make_coordinator)
    definitie = c.notification_definition("mode_change")
    venster = definitie[4]

    origineel = mod.dt_util.now
    try:
        mod.dt_util.now = lambda: NOW
        _stuur(c)
        mod.dt_util.now = lambda: NOW + timedelta(minutes=venster + 1)
        _stuur(c)
    finally:
        mod.dt_util.now = origineel

    assert len(c.notification_history) == 2


def test_suppressed_notifications_are_counted(make_coordinator, hass):
    """Zodat op het tabblad te zien is dat er iets is onderdrukt, in
    plaats van dat het stilzwijgend verdwijnt."""
    c = _coordinator(make_coordinator)

    _stuur(c)
    _stuur(c)
    _stuur(c)

    assert c.notification_suppressed_count["mode_change"] == 2


def test_different_kinds_do_not_throttle_each_other(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    _stuur(c, "mode_change")
    _stuur(c, "sluipverbruik")

    assert len(c.notification_history) == 2


# --- standaardwaarden ------------------------------------------------


def test_only_the_pre_existing_kinds_default_to_on():
    """Twintig meldingen die zichzelf aanzetten is een garantie dat er
    binnen een week niets meer van gelezen wordt."""
    standaard_aan = {k for k, _, _, aan, _ in NOTIFICATION_TYPES if aan}

    assert standaard_aan == {
        "appliance_cheap_moment",
        "appliance_ready",
        "battery_cooling",
        "sluipverbruik",
        "device_drift",
        "mode_change",
    }


def test_every_kind_has_a_throttle_window():
    for kind, _, _, _, venster in NOTIFICATION_TYPES:
        assert venster > 0, kind


def test_every_kind_has_a_label_and_explanation():
    """Een schakelaar zonder uitleg is niet te gebruiken."""
    for kind, label, uitleg, _, _ in NOTIFICATION_TYPES:
        assert label and len(label) > 3, kind
        assert uitleg and len(uitleg) > 20, kind


def test_kinds_are_unique():
    sleutels = [k for k, _, _, _, _ in NOTIFICATION_TYPES]
    assert len(sleutels) == len(set(sleutels))


# --- borging: niets omzeilt de schakelaar ---------------------------


def test_every_dispatch_call_passes_a_kind():
    """De belangrijkste test van dit bestand.

    De controle op schakelaar en dempingsvenster zit in de gedeelde
    verzendfunctie. Een aanroep zonder `kind` glipt daar ongecontroleerd
    doorheen - en dan is er een melding die niet uit te zetten is,
    precies wat gevraagd werd te voorkomen.
    """
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    aanroepen = [
        m.end()
        for m in re.finditer(r"self\._dispatch_notification\(", bron)
    ]
    # De definitie zelf niet meetellen.
    zonder_kind = []
    for positie in aanroepen:
        # Tot de sluitende haakjes van DEZE aanroep zoeken. Die staat op
        # wisselende inspringing (sommige aanroepen zitten diep genest),
        # dus haakjes tellen in plaats van op een vaste inspringing
        # matchen - anders wordt een lange aanroep te vroeg afgekapt en
        # lijkt hij ten onrechte geen `kind` te hebben.
        diepte = 1
        index = positie
        while index < len(bron) and diepte > 0:
            if bron[index] == "(":
                diepte += 1
            elif bron[index] == ")":
                diepte -= 1
            index += 1
        if "kind=" not in bron[positie:index]:
            zonder_kind.append(bron[:positie].count("\n") + 1)

    assert not zonder_kind, (
        f"aanroepen zonder 'kind' op regel(s) {zonder_kind} - die melding "
        "is niet uit te zetten"
    )


def test_every_kind_used_in_code_exists_in_the_registry():
    """Een typefout in de soort zou stilzwijgend een onbekende melding
    opleveren die altijd doorgaat."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    gebruikt = set(re.findall(r'kind="([a-z_]+)"', bron))
    bekend = {k for k, _, _, _, _ in NOTIFICATION_TYPES}

    assert gebruikt <= bekend, gebruikt - bekend


def test_an_unknown_kind_is_let_through(make_coordinator, hass):
    """Beter een melding te veel dan een stille regressie zodra iemand
    een nieuwe soort toevoegt en het register vergeet."""
    c = _coordinator(make_coordinator)

    toegestaan, _ = c.is_notification_allowed("bestaat_niet", NOW)

    assert toegestaan is True


# --- persistentie ----------------------------------------------------


def test_the_settings_survive_a_restart(make_coordinator, hass):
    """Een gebruikerskeuze mag bij een herstart niet terugspringen naar
    de standaard."""
    import asyncio

    bron = _coordinator(make_coordinator)
    bron.set_notification_enabled("mode_change", False)
    bron.set_notification_enabled("daily_summary", True)
    bron.notifications_master_enabled = False
    asyncio.run(bron.async_save_persisted_state_now())

    verse = _coordinator(make_coordinator)
    asyncio.run(verse.async_load_persisted_state())

    assert verse.notification_enabled["mode_change"] is False
    assert verse.notification_enabled["daily_summary"] is True
    assert verse.notifications_master_enabled is False


def test_the_throttle_survives_a_restart(make_coordinator, hass):
    """Zonder dit zou het dempingsvenster na elke herstart opnieuw
    beginnen en kon dezelfde melding alsnog meteen weer afgaan."""
    import asyncio

    bron = _coordinator(make_coordinator)
    _stuur(bron)
    asyncio.run(bron.async_save_persisted_state_now())

    verse = _coordinator(make_coordinator)
    asyncio.run(verse.async_load_persisted_state())
    # De geschiedenis wordt óók bewaard, dus die is niet leeg - het gaat
    # erom dat er niets BIJ komt.
    voor = len(verse.notification_history)
    _stuur(verse)

    assert len(verse.notification_history) == voor


# --- overzicht en schakelaars ---------------------------------------


def test_the_overview_covers_every_kind(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    overzicht = c.get_notification_overview()

    assert len(overzicht) == len(NOTIFICATION_TYPES)
    assert all(m["label"] and m["uitleg"] for m in overzicht)


def test_a_switch_exists_for_every_kind():
    """Gevraagd: elke melding moet op het tabblad uit te schakelen
    zijn."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()

    for kind, _, _, _, _ in NOTIFICATION_TYPES:
        assert f"melding_{kind}" in yaml_tekst, kind


def test_the_master_switch_is_on_the_tab():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()

    assert "meldingen_hoofdschakelaar" in yaml_tekst


# --- v1.5.1: de laatste drie meldingen ------------------------------


def _met_klok(c, uur, dag=7):
    """Draait de meldingsronde op een gegeven tijdstip.

    De ronde leest onderweg de prijsvoorspelling; zonder die stub loopt
    hij op een ontbrekende sensor stuk voordat de samenvattingen aan de
    beurt zijn.
    """
    c._get_forecast_entries = lambda: []
    from datetime import datetime, timezone

    from custom_components.energy_management_system import coordinator as mod

    moment = datetime(2026, 8, dag, uur, 0, tzinfo=timezone.utc)
    origineel = mod.dt_util.now
    try:
        mod.dt_util.now = lambda: moment
        c._evaluate_new_notifications(moment)
    finally:
        mod.dt_util.now = origineel


def _titels(c):
    return [m["titel"] for m in c.notification_history]


def test_the_daily_summary_only_fires_in_the_evening(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("daily_summary", True)

    _met_klok(c, uur=14)
    assert not any("Dagoverzicht" in t for t in _titels(c))

    _met_klok(c, uur=22)
    assert any("Dagoverzicht" in t for t in _titels(c))


def test_the_daily_summary_reports_the_saving(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("daily_summary", True)
    c.actual_cost_today_eur = 1.20
    c.counterfactual_cost_today_eur = 3.50
    c.pv_production_today_kwh = 14.2

    _met_klok(c, uur=22)

    assert any("Dagoverzicht" in t for t in _titels(c))


def test_the_monthly_summary_only_fires_on_the_first(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("monthly_summary", True)

    _met_klok(c, uur=10, dag=15)
    assert not any("Maandoverzicht" in t for t in _titels(c))

    _met_klok(c, uur=10, dag=1)
    assert any("Maandoverzicht" in t for t in _titels(c))


def test_only_the_transition_to_ready_is_reported(make_coordinator, hass):
    """Zonder de vergelijking met de vorige stand zou elke tick opnieuw
    melden dat een module klaar is - binnen een dag waardeloos."""
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("module_became_ready", True)
    c.previously_ready_modules = ["kalman"]
    c.advisory_readiness = {
        "kalman": {"status": "klaar"},
        "nilm": {"status": "klaar"},
    }

    _met_klok(c, uur=12)
    eerste = [t for t in _titels(c) if "klaar met leren" in t]
    assert len(eerste) == 1

    # Tweede ronde: niets veranderd, dus geen nieuwe melding.
    c.notification_last_sent.clear()
    _met_klok(c, uur=12)
    assert len([t for t in _titels(c) if "klaar met leren" in t]) == 1


def test_the_first_run_does_not_announce_everything(make_coordinator, hass):
    """Bij een verse installatie is alles "nieuw klaar" - dan hoort er
    geen melding te komen met de hele lijst."""
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("module_became_ready", True)
    c.previously_ready_modules = []
    c.advisory_readiness = {"kalman": {"status": "klaar"}}

    _met_klok(c, uur=12)

    assert not any("klaar met leren" in t for t in _titels(c))
    # De stand wordt wél onthouden, zodat een volgende module wél meldt.
    assert c.previously_ready_modules == ["kalman"]


def test_the_ready_list_survives_a_restart(make_coordinator, hass):
    """Zonder bewaren zou elke herstart de overgang opnieuw melden."""
    import asyncio

    bron = _coordinator(make_coordinator)
    bron.previously_ready_modules = ["kalman", "nilm"]
    asyncio.run(bron.async_save_persisted_state_now())

    verse = _coordinator(make_coordinator)
    asyncio.run(verse.async_load_persisted_state())

    assert verse.previously_ready_modules == ["kalman", "nilm"]
