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
    """v1.12.5: uitzetten stopt de melding naar de telefoon, maar hij
    blijft wél in de geschiedenis staan - gevraagd omdat uitzetten
    anders hetzelfde is als weggooien."""
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("mode_change", False)

    _stuur(c)

    assert hass.services.calls == []
    regel = c.notification_history[-1]
    assert regel["verstuurd"] is False
    assert "staat uit" in regel["reden_niet_verstuurd"]


def test_the_master_switch_blocks_everything(make_coordinator, hass):
    """Handig om alles in één keer stil te zetten zonder twintig
    schakelaars om te hoeven zetten."""
    c = _coordinator(make_coordinator)
    c.notifications_master_enabled = False

    for kind, _, _, _, _ in NOTIFICATION_TYPES:
        _stuur(c, kind)

    # v1.12.5: niets naar de telefoon, alles wél nalees baar.
    assert hass.services.calls == []
    assert len(c.notification_history) == len(NOTIFICATION_TYPES)
    assert all(m["verstuurd"] is False for m in c.notification_history)


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
    binnen een week niets meer van gelezen wordt.

    v1.20.1: `vakantie_beweging` staat er wél standaard bij, en dat is
    geen uitzondering op de regel maar een gevolg ervan. Deze melding
    vuurt alléén als de vakantiestand aan staat - een bewuste handeling.
    Stond hij standaard uit, dan zet je de vakantiestand aan, gebeurt er
    niets, en vraag je je af waarom. De ruis die deze regel wil
    voorkomen kan hier niet ontstaan.
    """
    standaard_aan = {k for k, _, _, aan, _ in NOTIFICATION_TYPES if aan}

    assert standaard_aan == {
        # v1.23.4: "Accu haalt de nacht mogelijk niet" staat standaard
        # aan, net als vakantie_beweging en om dezelfde reden: hij vuurt
        # alleen als er werkelijk iets misgaat. De twee andere
        # planningsmeldingen (uitstel, verkoop geblokkeerd) zijn
        # informatief en staan uit - die kunnen wél ruis worden.
        "plan_tekort",
        "vakantie_beweging",
        "appliance_cheap_moment",
        "appliance_ready",
        "battery_cooling",
        "sluipverbruik",
        "device_drift",
        "mode_change",
        # v1.29.0: "Onderdeel van de integratie faalt" staat aan om
        # dezelfde reden. Gemeld: "Dat er een txt wordt gemaakt is een
        # error, ik had daar graag een melding van verwacht zoals eerder
        # afgesproken." Een integratie die stiekem half werkt is geen
        # ruis - en stond hij uit, dan zou je er pas achter komen door
        # de export regel voor regel te lezen.
        "interne_fout",
        # v2.0.0: de zelfcontrole hoort bij dezelfde uitzondering. Ze
        # meldt alleen als twee getallen die elkaar moeten kloppen dat
        # niet doen - dat is per definitie geen ruis, en stond ze uit
        # dan zou je er pas achter komen door de export regel voor
        # regel te lezen. Precies wat deze week een paar keer nodig was.
        "zelfcontrole",
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


# --- v1.29.0: een falend onderdeel meldt zichzelf --------------------


def test_an_internal_failure_sends_a_notification(make_coordinator, hass):
    """Gemeld: "Dat er een txt wordt gemaakt is een error, ik had daar
    graag een melding van verwacht zoals eerder afgesproken."

    `internal_failures` bestaat sinds v1.19.4 maar verscheen alleen als
    aandachtspunt op een dashboardpagina. Afschermen zonder melden laat
    een storing stil doorlopen.
    """
    c = _coordinator(make_coordinator)
    c.internal_failures["diagnostiek:live_narrative"] = "TypeError: kapot"

    c._evaluate_new_notifications(NOW)

    soorten = [m["soort"] for m in c.notification_history]
    assert "interne_fout" in soorten


def test_the_message_names_the_broken_part(make_coordinator, hass):
    """Een melding "er is iets stuk" zonder te zeggen wát, kost meer tijd
    dan hij bespaart."""
    c = _coordinator(make_coordinator)
    c.internal_failures["diagnostiek:live_narrative"] = "TypeError: kapot"

    c._evaluate_new_notifications(NOW)

    melding = next(
        m for m in c.notification_history if m["soort"] == "interne_fout"
    )
    assert "live_narrative" in melding.get("bericht", "")
    assert "TypeError" in melding.get("bericht", "")


def test_no_failures_means_no_notification(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    c._evaluate_new_notifications(NOW)

    assert "interne_fout" not in [m["soort"] for m in c.notification_history]


def test_it_can_recover(make_coordinator, hass):
    """Zonder herstelmelding blijft de laatste stand "er is iets stuk",
    ook als het allang weer werkt."""
    from custom_components.energy_management_system.const import (
        NOTIFICATION_RECOVERY_KINDS,
    )

    assert "interne_fout" in NOTIFICATION_RECOVERY_KINDS


def test_it_has_an_achterhoeks_title():
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_TITELS,
    )

    assert "interne_fout" in ACHTERHOEKS_TITELS


# --- v1.40.0: ook melden dat het weer goed is ------------------------


def test_the_shortfall_warning_has_a_recovery(make_coordinator, hass):
    """Gemeld: "Ik krijg wel de melding dat er niet genoeg is, maar niet
    dat er wel weer genoeg zou zijn."

    Dat is de vervelende helft: je blijft achter met een waarschuwing
    die misschien allang niet meer geldt, en dan ga je zelf kijken - of
    je zet de melding uit.
    """
    c = _coordinator(make_coordinator)
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 11,
        "laagste_soc_procent": 10,
    }
    c._meld_planningswijzigingen(NOW)

    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 0,
        "laagste_soc_procent": 28,
    }
    # v3.9.0: het herstel komt pas na een stabiele periode. De planning
    # schommelt rond de grens; om 06:44 stond "hersteld" met om 06:45
    # weer "tekort". Twee rondes: de eerste start de klok, de tweede
    # meldt.
    c._meld_planningswijzigingen(NOW + timedelta(hours=1))
    c._meld_planningswijzigingen(NOW + timedelta(hours=2))

    titels = [m["titel"] for m in c.notification_history]
    # v3.9.0: "haalt de nacht weer" is vervangen. Die tekst sloeg
    # nergens op om half tien 's ochtends - het tekort kan op elk moment
    # binnen de horizon liggen.
    assert any("niet meer tekort" in t for t in titels)


def test_no_recovery_without_a_warning_first(make_coordinator, hass):
    """Anders krijg je elke ochtend een opgewekt bericht dat er niets aan
    de hand is."""
    c = _coordinator(make_coordinator)
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 0,
        "laagste_soc_procent": 28,
    }

    c._meld_planningswijzigingen(NOW)
    c._meld_planningswijzigingen(NOW + timedelta(hours=1))

    assert c.notification_history == []


def test_the_house_is_neuter_in_achterhoeks():
    """Gezien in de melding van 11 augustus: "de huus aan 't net hunk".
    Huis is onzijdig."""
    from custom_components.energy_management_system.const import (
        ACHTERHOEKS_WOORDEN,
    )

    tabel = dict(ACHTERHOEKS_WOORDEN)
    sleutels = [k for k, _ in ACHTERHOEKS_WOORDEN]

    assert tabel["de woning"] == "'t huus"
    assert sleutels.index("de woning") < sleutels.index("woning")
