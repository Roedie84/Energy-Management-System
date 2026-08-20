"""De opstartcode en de diensten (v3.37.0).

Gevraagd naar aanleiding van de dekkingsmeting: 50% van `__init__.py`
werd door geen enkele test uitgevoerd. Dat is de bedrading - het
kopiëren van het dashboard, het registreren van de diensten, het
ontladen - en juist bedrading valt op als hij het niet doet, niet als
hij het verkeerd doet.

Twee dingen die hier stil kunnen misgaan:

- de dienstenregistratie draait per config-entry maar mag maar één keer
  gebeuren; twee keer betekent een "service already registered"-fout bij
  het herladen van de instellingen
- de dienst zoekt de coordinator op in `hass.data`, waar óók de
  zonvoorspelling-tracker staat. Wordt die meegenomen, dan slaat elke
  dienst stuk op een object dat de methode niet heeft
"""
import asyncio
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import (
    SERVICE_CONFIRM_NILM_DEVICE,
)
from custom_components.energy_management_system.const import DOMAIN


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _NepConfig:
    def __init__(self, map_pad):
        self._map = Path(map_pad)

    def path(self, *delen):
        return str(self._map.joinpath(*delen))


class _NepCoordinator:
    """Alleen de NILM-acties die de diensten aanroepen."""

    def __init__(self, kent=()):
        self.kent = set(kent)
        self.gedaan = []

    def confirm_nilm_device(self, entity_id):
        self.gedaan.append(("bevestig", entity_id))
        return entity_id in self.kent

    def reject_nilm_device(self, entity_id):
        self.gedaan.append(("afwijzen", entity_id))
        return entity_id in self.kent

    def unconfirm_nilm_device(self, entity_id):
        self.gedaan.append(("terugdraaien", entity_id))
        return entity_id in self.kent

    def dismiss_nilm_duplicate_pair(self, een, twee):
        self.gedaan.append(("dubbel_weg", een, twee))
        return True

    def confirm_nilm_duplicate_pair(self, een, twee):
        self.gedaan.append(("dubbel_bevestig", een, twee))
        return twee in self.kent

    def accept_nilm_device_drift(self, entity_id):
        self.gedaan.append(("drift", entity_id))
        return entity_id in self.kent


class _Oproep:
    def __init__(self, **data):
        self.data = data


# --- 1. het dashboard klaarzetten ------------------------------------


def test_the_dashboard_is_copied_into_the_config_directory(hass, tmp_path):
    """Zonder deze kopie moet elke gebruiker het dashboard met de hand

    uit de repository halen.
    """
    hass.config = _NepConfig(tmp_path)

    pkg._copy_dashboard_template(hass)

    doel = tmp_path / "energy_management_system_dashboard.yaml"
    assert doel.exists()
    assert "Energy Management System" in doel.read_text()


def test_copying_the_dashboard_overwrites_on_purpose(hass, tmp_path):
    """Bewuste keuze, en het staat met zoveel woorden in de toelichting:

    handmatige wijzigingen gaan verloren zodat het meegeleverde
    dashboard de waarheid blijft.
    """
    hass.config = _NepConfig(tmp_path)
    doel = tmp_path / "energy_management_system_dashboard.yaml"
    doel.write_text("eigen versie")

    pkg._copy_dashboard_template(hass)

    assert doel.read_text() != "eigen versie"


def test_an_unwritable_directory_does_not_break_the_start(hass, tmp_path):
    """Deze routine draait tijdens het opstarten. Een schijf die vol zit

    mag de integratie niet meenemen.
    """
    hass.config = _NepConfig(tmp_path / "bestaat_niet" / "diep")

    pkg._copy_dashboard_template(hass)


def test_a_missing_template_is_skipped(hass, tmp_path, monkeypatch):
    hass.config = _NepConfig(tmp_path)
    monkeypatch.setattr(pkg, "__file__", str(tmp_path / "nep" / "__init__.py"))

    pkg._copy_dashboard_template(hass)

    assert not (tmp_path / "energy_management_system_dashboard.yaml").exists()


# --- 2. de achtergrondtekening ---------------------------------------


def test_the_background_lands_in_the_www_folder(hass, tmp_path):
    """Home Assistant serveert alleen `<config>/www/` als `/local/`.

    Staat de tekening daar niet, dan toont de kaart een gebroken
    afbeelding met alle waarden er wél overheen - verwarrender dan een
    lege kaart.
    """
    hass.config = _NepConfig(tmp_path)

    pkg._copy_overview_background(hass)

    gevonden = list((tmp_path / "www").glob("*"))
    assert gevonden, "niets in www/ terechtgekomen"


def test_the_www_folder_is_created_when_missing(hass, tmp_path):
    hass.config = _NepConfig(tmp_path)

    assert not (tmp_path / "www").exists()

    pkg._copy_overview_background(hass)

    assert (tmp_path / "www").is_dir()


def test_a_broken_background_copy_does_not_break_the_start(hass, tmp_path):
    hass.config = _NepConfig(tmp_path / "www")
    (tmp_path / "www").write_text("dit is een bestand, geen map")

    pkg._copy_overview_background(hass)


# --- 3. de diensten --------------------------------------------------


def _registreer(hass, *coordinators):
    hass.data = {DOMAIN: {}}
    for i, c in enumerate(coordinators):
        hass.data[DOMAIN][f"entry{i}"] = c
    hass.data[DOMAIN]["entry0_solar_tracker"] = object()
    pkg._async_register_nilm_services(hass)
    return hass.services._registered


def test_the_services_are_registered_once(hass):
    """Twee keer registreren levert bij het herladen van de instellingen

    een "service already registered"-fout op.
    """
    c = _NepCoordinator()
    registraties = _registreer(hass, c)
    aantal = len(registraties)

    pkg._async_register_nilm_services(hass)

    assert len(hass.services._registered) == aantal
    assert (DOMAIN, SERVICE_CONFIRM_NILM_DEVICE) in registraties


def test_the_solar_tracker_is_never_mistaken_for_a_coordinator(hass):
    """In `hass.data` staat naast de coordinator ook de zonvoorspelling-

    tracker. Wordt die meegenomen, dan slaat elke dienst stuk op een
    object dat de methode niet heeft.
    """
    c = _NepCoordinator(kent={"sensor.vaatwasser"})
    registraties = _registreer(hass, c)
    handler = registraties[(DOMAIN, SERVICE_CONFIRM_NILM_DEVICE)]

    _run(handler(_Oproep(entity_id="sensor.vaatwasser")))

    assert ("bevestig", "sensor.vaatwasser") in c.gedaan


@pytest.mark.parametrize(
    "dienst,sleutels,verwacht",
    [
        ("confirm_nilm_device", {"entity_id": "sensor.x"}, "bevestig"),
        ("reject_nilm_device", {"entity_id": "sensor.x"}, "afwijzen"),
        ("unconfirm_nilm_device", {"entity_id": "sensor.x"}, "terugdraaien"),
        ("accept_nilm_device_drift", {"entity_id": "sensor.x"}, "drift"),
    ],
)
def test_each_service_reaches_the_coordinator(hass, dienst, sleutels, verwacht):
    c = _NepCoordinator(kent={"sensor.x"})
    registraties = _registreer(hass, c)
    handler = registraties[(DOMAIN, dienst)]

    _run(handler(_Oproep(**sleutels)))

    assert c.gedaan[0][0] == verwacht


def test_the_duplicate_services_pass_both_entities(hass):
    c = _NepCoordinator(kent={"sensor.twee"})
    registraties = _registreer(hass, c)

    _run(
        registraties[(DOMAIN, "dismiss_nilm_duplicate_pair")](
            _Oproep(entity_id_1="sensor.een", entity_id_2="sensor.twee")
        )
    )
    _run(
        registraties[(DOMAIN, "confirm_nilm_duplicate_pair")](
            _Oproep(entity_id_1="sensor.een", entity_id_2="sensor.twee")
        )
    )

    assert ("dubbel_weg", "sensor.een", "sensor.twee") in c.gedaan
    assert ("dubbel_bevestig", "sensor.een", "sensor.twee") in c.gedaan


def test_an_unknown_entity_is_harmless(hass):
    """Bevestigen van iets dat deze coordinator niet kent, hoort een

    waarschuwing te zijn en geen fout.
    """
    c = _NepCoordinator(kent=set())
    registraties = _registreer(hass, c)

    _run(
        registraties[(DOMAIN, SERVICE_CONFIRM_NILM_DEVICE)](
            _Oproep(entity_id="sensor.onbekend")
        )
    )

    assert c.gedaan == [("bevestig", "sensor.onbekend")]


def test_every_coordinator_gets_the_action(hass):
    """Meerdere config-entries in één huishouden komt zelden voor, maar

    de dienst is er wel op gebouwd.
    """
    een, twee = _NepCoordinator(kent={"sensor.x"}), _NepCoordinator()
    registraties = _registreer(hass, een, twee)

    _run(
        registraties[(DOMAIN, SERVICE_CONFIRM_NILM_DEVICE)](
            _Oproep(entity_id="sensor.x")
        )
    )

    assert een.gedaan and twee.gedaan
