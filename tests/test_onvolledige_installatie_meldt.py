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

    # v3.70.0: het zijn TEKSTEN, geen dicts - `_narrate_attention` doet
    # er `" ".join(...)` overheen, en dat werpt een TypeError op een
    # dict. Dat brak het Live-verhaal en de hele export.
    punt = next(p for p in punten if "Onvolledige installatie" in p)
    assert "1 bestand" in punt
    assert "herstart" in punt.lower()


def test_a_complete_installation_says_nothing(make_coordinator, hass):
    c = make_coordinator({})
    c.bestandscontrole = {"beschikbaar": True, "in_orde": True}

    titels = c.get_diagnostic_summary()["aandachtspunten"]

    assert not any("Onvolledige installatie" in p for p in titels)


def test_before_startup_it_says_nothing(make_coordinator, hass):
    """Zolang de controle niet is gedraaid valt er niets te melden."""
    c = make_coordinator({})

    titels = c.get_diagnostic_summary()["aandachtspunten"]

    assert not any("Onvolledige installatie" in p for p in titels)


# --- de zelftoets komt er ook op ------------------------------------


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


