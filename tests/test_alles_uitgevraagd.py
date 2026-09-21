"""Elke entiteit volledig uitvragen, zoals Home Assistant dat doet (v5.14).

Gevraagd: *"Kunnen we een mechanisme bedenken om ten allertijde dit soort
fouten te voorkomen?"*

De fouten van de afgelopen weken hadden één ding gemeen: de code werd
nooit uitgevoerd zoals Home Assistant hem uitvoert.

- v5.8: de export riep een functie aan zonder zijn verplichte argument.
  Drie dagen in bedrijf voordat het opviel.
- v5.14: een attribuut op "PV forecast accuracy", een sensor die geen
  coördinator heeft. Had in bedrijf de hele attributenlijst laten omvallen.
  Geen enkele toets vroeg die attributen op.
- v5.14: een attribuut in de verkeerde klasse, ingevoegd op regelnummer.
- v5.9: "nul metingen" - een veld dat niet in de export stond.

Een tekstscan had geen van deze gevonden. Wat ze allemaal had gevonden:
alles AANROEPEN, precies zoals Home Assistant het aanroept.

Dit bestand maakt elke entiteit aan via de echte `async_setup_entry` van
elk platform, en vraagt van elke entiteit de waarde, de attributen, het
icoon en de beschikbaarheid op. En het draait de volledige export. Twee
keer:

1. op een LEGE installatie - daar vallen functies om die op gevulde
   gegevens rekenen;
2. op de ECHTE opgeslagen toestand van deze installatie - daar vallen
   functies om die op lege gegevens rekenen, en daar komen attributen
   boven de 16 kB van de recorder uit.

Wat er gecontroleerd wordt, per entiteit:

- geen uitzondering bij het opvragen van enige eigenschap;
- attributen zijn om te zetten naar JSON;
- attributen blijven onder de 16 kB die de recorder van Home Assistant
  accepteert - daarboven worden ze stil niet meer bewaard.

En de export: geen enkel onderdeel mag in `internal_failures` belanden.

De echte toestand staat in `tests/fixtures/opslag_echt.json`, gemaakt uit
een diagnostiek-export. Ontbreekt dat bestand, dan slaat dat deel over -
zo kan het buiten een openbare repository blijven.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "opslag_echt.json"

# De recorder van Home Assistant bewaart de attributen van een toestand niet
# meer als ze samen boven deze grens komen - en zegt dat alleen in het log.
RECORDER_ATTRIBUTEN_MAX_BYTES = 16384

# Home Assistant weigert een toestand boven deze lengte.
TOESTAND_MAX_TEKENS = 255

EIGENSCHAPPEN = (
    "native_value",
    "is_on",
    "extra_state_attributes",
    "icon",
    "available",
    "native_unit_of_measurement",
)


def _verplicht():
    """Een net ingestelde installatie: de vier verplichte velden, verder
    niets. Een lege configuratie is geen installatie - zonder prijssensor
    kan de integratie niet eens worden ingesteld."""
    from custom_components.energy_management_system.const import (
        CONF_MANUAL_POWER_NUMBER,
        CONF_OPERATION_SELECT,
        CONF_PRICE_ATTRIBUTE,
        CONF_PRICE_SENSOR,
        DEFAULT_PRICE_ATTRIBUTE,
    )

    return {
        CONF_PRICE_SENSOR: "sensor.prijs",
        CONF_PRICE_ATTRIBUTE: DEFAULT_PRICE_ATTRIBUTE,
        CONF_OPERATION_SELECT: "select.modus",
        CONF_MANUAL_POWER_NUMBER: "number.vermogen",
    }


def _maximaal():
    """Een installatie waarin elke voorwaardelijke entiteit bestaat.

    Sommige entiteiten maakt een platform alleen aan als er iets is
    ingesteld. De zonvolger bijvoorbeeld alleen met een voorspel- en een
    opbrengstsensor. Zonder die instelling wordt de entiteit niet
    aangemaakt, en dan ook niet uitgevraagd. Zie
    `test_elke_entiteitklasse_is_uitgevraagd`: die faalt als er ooit een
    voorwaardelijke entiteit bijkomt die hier niet aan staat.
    """
    from custom_components.energy_management_system.const import (
        CONF_SOLAR_ACTUAL_SENSOR,
        CONF_SOLAR_FORECAST_SENSOR,
    )

    return {
        **_verplicht(),
        CONF_SOLAR_FORECAST_SENSOR: "sensor.zon_morgen",
        CONF_SOLAR_ACTUAL_SENSOR: "sensor.zon_vandaag",
    }


def _echte_toestand():
    if not FIXTURE.exists():
        pytest.skip("geen echte toestand in tests/fixtures - dat deel slaat over")
    return json.loads(FIXTURE.read_text())


async def _alle_entiteiten(hass, coordinator):
    """Maakt alle entiteiten aan via de echte setup van elk platform."""
    from custom_components.energy_management_system import button, sensor, switch
    from custom_components.energy_management_system.const import DOMAIN
    from custom_components.energy_management_system.solar_forecast import (
        SolarForecastAccuracyTracker,
    )

    entry = SimpleNamespace(entry_id="toets", data={}, options={})
    # De zonvolger met DEZELFDE configuratie als de coördinator: alleen dan
    # staat hij aan, en alleen dan maakt het sensorplatform zijn
    # `PvForecastAccuracySensor` aan. Met een lege configuratie ontsnapte die
    # sensor aan dit mechanisme - en juist op die sensor zat de fout van
    # v5.14.
    tracker = coordinator.solar_tracker or SolarForecastAccuracyTracker(
        hass, dict(coordinator.config or {})
    )
    if not hasattr(hass, "data"):
        hass.data = {}
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["toets"] = coordinator
    hass.data[DOMAIN]["toets_solar_tracker"] = tracker
    verzameld = []

    def _voeg_toe(entiteiten, *args, **kwargs):
        verzameld.extend(entiteiten)

    for platform in (sensor, switch, button):
        await platform.async_setup_entry(hass, entry, _voeg_toe)
    for entiteit in verzameld:
        entiteit.hass = hass
    return verzameld


def _vraag_uit(entiteit) -> list[str]:
    """Vraagt alles op wat Home Assistant opvraagt. Geeft de fouten terug."""
    naam = type(entiteit).__name__
    fouten = []
    for eigenschap in EIGENSCHAPPEN:
        if not hasattr(type(entiteit), eigenschap):
            continue
        try:
            waarde = getattr(entiteit, eigenschap)
        except Exception as fout:  # noqa: BLE001 - juist die willen we zien
            fouten.append(f"{naam}.{eigenschap}: {type(fout).__name__}: {fout}")
            continue
        # v5.14: Home Assistant weigert een toestand boven de 255 tekens -
        # de sensor valt dan terug op "unknown". Geldt voor elke sensor,
        # maar werd pas zichtbaar met de diagnoseregels, die die ruimte
        # bewust vullen.
        if (
            eigenschap == "native_value"
            and isinstance(waarde, str)
            and len(waarde) > TOESTAND_MAX_TEKENS
        ):
            fouten.append(
                f"{naam}: toestand {len(waarde)} tekens, boven de "
                f"{TOESTAND_MAX_TEKENS} die Home Assistant accepteert"
            )
        if eigenschap != "extra_state_attributes" or not waarde:
            continue
        try:
            json.dumps(waarde, default=str)
        except Exception as fout:  # noqa: BLE001
            fouten.append(f"{naam}: attributen niet naar JSON: {fout}")
            continue
        # Wat de entiteit zelf van de recorder uitsluit, telt niet mee - dat
        # blijft live beschikbaar maar gaat niet naar de database. Het
        # Home Assistant-mechanisme daarvoor is `_unrecorded_attributes`.
        uitgesloten = getattr(type(entiteit), "_unrecorded_attributes", frozenset())
        bewaard = {k: v for k, v in waarde.items() if k not in uitgesloten}
        tekst = json.dumps(bewaard, default=str)
        grootte = len(tekst.encode("utf-8"))
        if grootte > RECORDER_ATTRIBUTEN_MAX_BYTES:
            fouten.append(
                f"{naam}: attributen {grootte} bytes, boven de "
                f"{RECORDER_ATTRIBUTEN_MAX_BYTES} die de recorder bewaart"
            )
    return fouten


async def _draai_de_export(hass, coordinator) -> dict:
    from custom_components.energy_management_system import diagnostics

    coordinator.internal_failures = {}
    entry = SimpleNamespace(entry_id="toets", data={}, options={})
    uit = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
    json.dumps(uit, default=str)
    return {
        k: v
        for k, v in (coordinator.internal_failures or {}).items()
        if k.startswith("diagnostiek:")
    }


# --- een lege installatie -----------------------------------------------


@pytest.mark.asyncio
async def test_elke_entiteit_op_een_lege_installatie(make_coordinator, hass):
    c = make_coordinator(_maximaal())
    entiteiten = await _alle_entiteiten(hass, c)

    assert len(entiteiten) > 100, len(entiteiten)
    fouten = [f for e in entiteiten for f in _vraag_uit(e)]
    assert not fouten, "\n".join(fouten)


@pytest.mark.asyncio
async def test_de_export_op_een_lege_installatie(make_coordinator, hass):
    c = make_coordinator(_maximaal())
    await _alle_entiteiten(hass, c)

    mislukt = await _draai_de_export(hass, c)

    assert not mislukt, mislukt


# --- de echte opgeslagen toestand ---------------------------------------


@pytest.mark.asyncio
async def test_elke_entiteit_op_de_echte_toestand(make_coordinator, hass):
    toestand = _echte_toestand()
    c = make_coordinator(_maximaal())
    c._apply_persisted_state(toestand)
    entiteiten = await _alle_entiteiten(hass, c)

    fouten = [f for e in entiteiten for f in _vraag_uit(e)]
    assert not fouten, "\n".join(fouten)


@pytest.mark.asyncio
async def test_de_export_op_de_echte_toestand(make_coordinator, hass):
    toestand = _echte_toestand()
    c = make_coordinator(_maximaal())
    c._apply_persisted_state(toestand)
    await _alle_entiteiten(hass, c)

    mislukt = await _draai_de_export(hass, c)

    assert not mislukt, mislukt


# --- het mechanisme bewaakt zichzelf ------------------------------------


def test_het_mechanisme_vangt_een_attribuut_op_een_sensor_zonder_coordinator():
    """De fout die dit mechanisme uitlokte, moet het ook echt vangen."""

    class Kapot:
        @property
        def extra_state_attributes(self):
            return {"x": self._coordinator.bestaat_niet}

    assert _vraag_uit(Kapot())


def test_het_mechanisme_vangt_te_grote_attributen():
    class Groot:
        @property
        def extra_state_attributes(self):
            return {"lijst": ["x" * 100] * 200}

    fouten = _vraag_uit(Groot())
    assert fouten and "recorder" in fouten[0]


# --- valideren bij binnenkomst ------------------------------------------


@pytest.mark.asyncio
async def test_een_opslag_in_de_verkeerde_vorm_laat_niets_omvallen(make_coordinator, hass):
    """Gevonden toen dit mechanisme voor het eerst op de echte toestand
    draaide. De export zet onder `sensor_cadence` het RAPPORT, niet de
    opgeslagen toestand - en in die vorm geladen vielen vier sensoren om
    met `KeyError: 'wijzigingen'`.

    In bedrijf komt de opslag nooit in die vorm. Maar het principe van dit
    project is: valideer externe waarheid bij binnenkomst. Een opslag is
    een externe bron."""
    c = make_coordinator(_maximaal())
    c._apply_persisted_state(
        {
            "sensor_cadence": {
                "sensor.hw_p1_vermogen": {
                    "status": "volgt_de_tick",
                    "beweegt_percent": 97.9,
                    "ticks": 282,
                },
                "sensor.goed": {"ticks": 300, "wijzigingen": 280, "laatste": 1.0},
            }
        }
    )
    entiteiten = await _alle_entiteiten(hass, c)

    assert "sensor.hw_p1_vermogen" not in c.sensor_cadence
    assert "sensor.goed" in c.sensor_cadence
    fouten = [f for e in entiteiten for f in _vraag_uit(e)]
    assert not fouten, "\n".join(fouten)


# --- het mechanisme is volledig -----------------------------------------


def _klassen_die_een_platform_kan_aanmaken() -> set:
    """Elke klasse die in een `async_setup_entry` wordt aangemaakt - ook
    binnen een voorwaarde. Op de syntaxboom, niet op tekst."""
    import ast

    import custom_components.energy_management_system as pkg

    namen = set()
    for platform in ("sensor", "switch", "button"):
        bron = (Path(pkg.__file__).parent / f"{platform}.py").read_text()
        boom = ast.parse(bron)
        klassen = {k.name for k in ast.walk(boom) if isinstance(k, ast.ClassDef)}
        setup = next(
            k
            for k in ast.walk(boom)
            if isinstance(k, ast.AsyncFunctionDef) and k.name == "async_setup_entry"
        )
        for knoop in ast.walk(setup):
            if (
                isinstance(knoop, ast.Call)
                and isinstance(knoop.func, ast.Name)
                and knoop.func.id in klassen
            ):
                namen.add(knoop.func.id)
    return namen


@pytest.mark.asyncio
async def test_elke_entiteitklasse_is_uitgevraagd(make_coordinator, hass):
    """Geen entiteit mag aan dit mechanisme ontsnappen. De eerste versie
    miste `PvForecastAccuracySensor`, die alleen bestaat als de zonvolger
    aanstaat - en toen ik de fout van v5.14 er opzettelijk weer in zette,
    bleef alles groen. Deze toets maakt dat onmogelijk: komt er een
    voorwaardelijke entiteit bij die `_maximaal()` niet aanzet, dan faalt
    hij."""
    c = make_coordinator(_maximaal())
    uitgevraagd = {type(e).__name__ for e in await _alle_entiteiten(hass, c)}

    ontsnapt = _klassen_die_een_platform_kan_aanmaken() - uitgevraagd

    assert not ontsnapt, sorted(ontsnapt)
