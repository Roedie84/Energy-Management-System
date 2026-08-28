"""Een onvolledige installatie moet je bereiken (v3.67.0).

Gevraagd: "Krijg ik een melding op mijn telefoon of zie ik het bij
aandachtspunten op mijn landingspagina als bepaalde bestanden van een
oude versie zijn? Dit zodat ik getriggerd word."

Nee, en dat was een gat. De bestandscontrole van v3.63.0 zette een regel
in het logboek en een veld in de export - allebei plekken waar je alleen
kijkt als je al vermoedt dat er iets is.

Juist bij deelleveringen is het omgekeerde nodig: je weet niet dat er
iets mis is, want de code draait gewoon.
"""
import pytest

STUK = {
    "beschikbaar": True,
    "in_orde": False,
    "afwijkend": ["sensor.py"],
    "ontbrekend": [],
    "uitleg": "1 bestand(en) wijken af en 0 ontbreken.",
}


# --- de landingspagina -----------------------------------------------


def test_it_shows_up_as_an_attention_point(make_coordinator, hass):
    c = make_coordinator({})
    c.bestandscontrole = dict(STUK)

    punten = c.get_diagnostic_summary()["aandachtspunten"]

    punt = next(p for p in punten if p["titel"] == "Onvolledige installatie")
    assert "sensor.py" in punt["tekst"] or "1 bestand" in punt["tekst"]
    assert "herstart" in punt["actie"].lower()


def test_a_complete_installation_says_nothing(make_coordinator, hass):
    c = make_coordinator({})
    c.bestandscontrole = {"beschikbaar": True, "in_orde": True}

    titels = [
        p["titel"] for p in c.get_diagnostic_summary()["aandachtspunten"]
    ]

    assert "Onvolledige installatie" not in titels


def test_before_startup_it_says_nothing(make_coordinator, hass):
    """Zolang de controle niet is gedraaid valt er niets te melden."""
    c = make_coordinator({})

    titels = [
        p["titel"] for p in c.get_diagnostic_summary()["aandachtspunten"]
    ]

    assert "Onvolledige installatie" not in titels


# --- de zelftoets komt er ook op ------------------------------------


def test_a_self_test_finding_reaches_the_landing_page(
    make_coordinator, hass
):
    """De fout van 28 augustus: zestig vergelijkingen, nul met zon."""
    c = make_coordinator({})
    c.digital_twin_accuracy_history = [
        {"fout_kwh": 1.346, "met_zon": False} for _ in range(60)
    ]

    titels = [
        p["titel"] for p in c.get_diagnostic_summary()["aandachtspunten"]
    ]

    assert "Tweeling: splitsing eenzijdig" in titels


# --- de melding op de telefoon --------------------------------------


def test_the_notification_kind_exists_and_defaults_to_on():
    """Een melding die standaard uit staat, bereikt niemand."""
    from custom_components.energy_management_system.const import (
        LOG_PRIORITEITEN,
        LOG_PRIO_KRITIEK,
        NOTIFICATION_TYPES,
    )

    soorten = {k[0]: k for k in NOTIFICATION_TYPES}

    assert "installatie_onvolledig" in soorten
    assert soorten["installatie_onvolledig"][3] is True
    assert LOG_PRIORITEITEN["installatie_onvolledig"] == LOG_PRIO_KRITIEK


def test_the_message_names_the_files():
    """Zonder de bestandsnamen weet je niet wat je opnieuw moet

    kopieren.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C.async_setup)

    assert "installatie_onvolledig" in bron
    assert "afwijkend" in bron and "ontbrekend" in bron


def test_there_is_a_switch_on_the_dashboard():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    sjabloon = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()

    assert "melding_installatie_onvolledig" in sjabloon
