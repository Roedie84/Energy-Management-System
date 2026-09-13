"""Wat de diagnostiek miste (v3.4.0).

Gevraagd: "Kun je nog wat verbeteren aan de diagnostiek van mijn EMS
zodat we hem nog beter kunnen maken?"

Drie dingen die deze week aantoonbaar tijd kostten.
"""


def test_the_running_version_is_in_the_export(make_coordinator, hass):
    """De grootste vondst: de VERSIE stond er niet in.

    Op 17 augustus kwam een koelmelding binnen met de oude tekst, terwijl
    de reparatie was opgeleverd. Om te bepalen of de nieuwe code draaide
    moest worden afgeleid welke FUNCTIES aanwezig waren - twee ronden
    werk voor iets wat één regel had kunnen zijn.
    """
    c = make_coordinator({})

    feiten = c.get_installation_facts()

    for sleutel in ("versie", "gestart_op", "home_assistant", "python"):
        assert sleutel in feiten


def test_the_version_is_read_outside_the_event_loop():
    """Een bestand lezen in de event loop is verboden (v2.0.6) - en de
    eigen test ving dat meteen bij het bouwen hiervan."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_installation_facts")
    blok = bron[kop : bron.index("\n    @staticmethod", kop)]

    assert "read_text" not in blok
    assert "_manifest_versie" in blok


def test_own_warnings_are_captured(make_coordinator, hass):
    """Tweede vondst: alles wat via `_LOGGER.warning` wordt weggeschreven
    verdwijnt in het logboek van Home Assistant, en dat zit niet in de
    export.

    De NameError die het inlezen van de geschiedenis bij ELKE start liet
    omvallen stond alleen daar; het duurde drie diagnostieken en twee
    versies voordat die boven water kwam.
    """
    import logging

    c = make_coordinator({})
    c._start_logopvang()
    try:
        logging.getLogger(
            "custom_components.energy_management_system.coordinator"
        ).warning("proefmelding %s", 42)

        assert c.eigen_logregels
        assert "proefmelding 42" in c.eigen_logregels[-1]["tekst"]
        assert c.eigen_logregels[-1]["niveau"] == "WARNING"
    finally:
        c._stop_logopvang()


def test_only_warnings_and_worse_are_kept(make_coordinator, hass):
    """Elke informatieregel opvangen zou de export laten volstromen."""
    import logging

    c = make_coordinator({})
    c._start_logopvang()
    try:
        logging.getLogger(
            "custom_components.energy_management_system.coordinator"
        ).info("dit is maar informatie")

        assert not c.eigen_logregels
    finally:
        c._stop_logopvang()


def test_other_integrations_are_not_captured(make_coordinator, hass):
    """Wat andere integraties loggen blijft onzichtbaar - daar heeft deze
    integratie niets te zoeken."""
    import logging

    c = make_coordinator({})
    c._start_logopvang()
    try:
        logging.getLogger("homeassistant.components.zendure").warning("iets")

        assert not c.eigen_logregels
    finally:
        c._stop_logopvang()


def test_a_half_installed_update_is_detected(make_coordinator, hass):
    """Derde vondst. Tijdens de GitHub-storing van 17 augustus (50%
    foutkans op downloads) kan een installatie half aankomen: het ene
    bestand nieuw, het andere oud. Dat is aan de buitenkant niet te zien.
    """
    from datetime import datetime, timedelta, timezone

    import custom_components.energy_management_system.coordinator as mod

    nu = datetime(2026, 8, 17, 21, 0, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu

    c = make_coordinator({})
    c.last_successful_update = nu.isoformat()
    c.gross_consumption_today_kwh = 0.0
    c.energy_daily_history = []
    c._bestandsinfo = {
        "coordinator.py": {"gewijzigd": nu.isoformat()},
        "const.py": {"gewijzigd": (nu - timedelta(days=2)).isoformat()},
    }

    namen = [b["naam"] for b in c.get_consistency_checks(nu)["bevindingen"]]

    assert "Installatie" in namen


def test_a_normal_install_passes(make_coordinator, hass):
    """Een normale installatie schrijft alle bestanden binnen enkele
    minuten."""
    from datetime import datetime, timedelta, timezone

    import custom_components.energy_management_system.coordinator as mod

    nu = datetime(2026, 8, 17, 21, 0, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu

    c = make_coordinator({})
    c.last_successful_update = nu.isoformat()
    c.gross_consumption_today_kwh = 0.0
    c.energy_daily_history = []
    c._bestandsinfo = {
        "coordinator.py": {"gewijzigd": nu.isoformat()},
        "const.py": {"gewijzigd": (nu - timedelta(minutes=3)).isoformat()},
    }

    namen = [b["naam"] for b in c.get_consistency_checks(nu)["bevindingen"]]

    assert "Installatie" not in namen


def test_the_export_carries_all_three():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert '"installation"' in bron
    assert '"own_log"' in bron
