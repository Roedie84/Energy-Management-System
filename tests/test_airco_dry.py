"""De airco in ontvochtigingsstand wordt niet gezien (v5.5).

Vier standen uitgelezen in de ontwikkelaarstools:

    stand   status   hvac_action      gezien als zware verbruiker?
    off     off      'off'            nee, terecht
    cool    cool     idle             nee, compressor staat stil
    cool    cool     cooling          JA
    heat    heat     heating          JA
    dry     dry      ONTBREEKT        nee - en dat is het gat

In ontvochtigingsstand levert deze unit HELEMAAL GEEN `hvac_action`; het
attribuut is er niet. De herkenning leest dan `None`, en dat zit niet in
`{"heating", "cooling"}`. De airco draait dus, gebruikt stroom, en de
integratie ziet hem niet.

`drying` aan de lijst toevoegen helpt niet - er komt niets. De juiste
regel is: ontbreekt `hvac_action` terwijl de STAND een verwarmende of
koelende modus is, dan telt de airco als actief. Ontbrekende informatie
is hier geen bewijs van stilstand.

Wat NIET meetelt, en waarom:
- `idle` en `off`: de compressor staat werkelijk stil
- `fan_only`: een ventilator van enkele tientallen watts, geen zware
  verbruiker

Dit raakt de sturing: de reserve houdt rekening met wat er aan staat.
"""
import pytest


def _airco(hass, stand, hvac_action="__weglaten__"):
    attributen = {"friendly_name": "Airco Woonkamer"}
    if hvac_action != "__weglaten__":
        attributen["hvac_action"] = hvac_action
    hass.states.set("climate.woonkamer", stand, attributen)


def _coordinator(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["airco_climate_entity"] = "climate.woonkamer"
    return c


@pytest.mark.parametrize(
    "stand,actie,verwacht",
    [
        ("cool", "cooling", "airco"),
        ("heat", "heating", "airco"),
        # het gat: dry stuurt geen hvac_action
        ("dry", "__weglaten__", "airco"),
        # deze horen NIET mee te tellen
        ("cool", "idle", None),
        ("off", "off", None),
        ("fan_only", "fan", None),
        ("fan_only", "__weglaten__", None),
        ("off", "__weglaten__", None),
    ],
)
def test_de_vier_standen(make_coordinator, hass, stand, actie, verwacht):
    c = _coordinator(make_coordinator, hass)
    _airco(hass, stand, actie)

    assert c._get_confirmed_heavy_load_source(None) == verwacht


def test_een_onbekende_stand_zonder_actie_telt_niet(make_coordinator, hass):
    """Alleen de standen waarvan we weten dat ze de compressor gebruiken.
    Een onbekende stand zonder informatie is geen bewijs van verbruik."""
    c = _coordinator(make_coordinator, hass)
    _airco(hass, "iets_nieuws", "__weglaten__")

    assert c._get_confirmed_heavy_load_source(None) is None


def test_de_slaapkamerairco_volgt_dezelfde_regel(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["slaapkamer_climate_entity"] = "climate.slaapkamer"
    hass.states.set("climate.slaapkamer", "dry", {"friendly_name": "Slaapkamer"})

    assert c._get_confirmed_heavy_load_source(None) == "slaapkamer"


def test_de_standenlijst_bevat_geen_ventilatorstand():
    from custom_components.energy_management_system.const import (
        AIRCO_ACTIEVE_STANDEN_ZONDER_ACTIE,
    )

    assert "fan_only" not in AIRCO_ACTIEVE_STANDEN_ZONDER_ACTIE
    assert "off" not in AIRCO_ACTIEVE_STANDEN_ZONDER_ACTIE
    assert "dry" in AIRCO_ACTIEVE_STANDEN_ZONDER_ACTIE
