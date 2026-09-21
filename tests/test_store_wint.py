"""De opslag van de coördinator is de bron, niet de sensoren (v5.9).

Gevonden in de export van 21 september. De tekortdagen waren
herbeoordeeld - `herbeoordeeld: v5.8` stond erbij - en toch stonden ze
op `shortfall=True`. Die twee kunnen volgens de code niet samen bestaan.

De oorzaak zat in de opstartvolgorde van `__init__.py`:

    await coordinator.async_load_persisted_state()     # 1. opslag laden
    await hass.config_entries.async_forward_entry_setups(...)  # 2. sensoren

In stap 1 laadt de coördinator zijn opslag en herbeoordeelt. In stap 2
worden 22 sensoren toegevoegd, en elk herstelt in `async_added_to_hass`
zijn door Home Assistant bewaarde toestand - en zet die over de
coördinator heen. De sensor wint altijd, want hij komt later.

Voor de tekortdagen deed `_merge_reserve_daily_records` dat met
`dict(r)` - dat houdt de tag vast en overschrijft `shortfall` met de oude
waarde. Vandaar tag én True.

38 velden hebben zo twee bronnen. Het commentaar in `__init__.py` noemt
zelf waarom dat gevaarlijk is: *"die entiteit-attributen zijn met opzet
afgekapt op 20 items"*. Voor NILM is dat in v0.63.115 opgelost, voor de
andere 22 sensoren niet.

Sinds v1.0.4 bewaart de coördinator zijn toestand zelf. Het herstel via
de sensoren was nodig vóór die tijd; nu is het een tweede bron die bij
elke herstart elke correctie ongedaan maakt die de coördinator bij het
laden doet.

De reparatie op één plek: na het toevoegen van de sensoren zet de
coördinator zijn opslag nog een keer terug. De opslag wint. De sensoren
blijven herstellen voor wat de opslag NIET heeft - een allereerste
installatie zonder opslag.
"""
import copy
from datetime import datetime, timezone

import pytest


def test_de_opslag_wint_van_een_sensorherstel(make_coordinator, hass):
    """Het gemeten geval: herbeoordeeld, en toch terug op True."""
    c = make_coordinator({})
    opgeslagen = {
        "reserve_daily_records": [
            {"date": "2026-09-14", "shortfall": True, "netimport_nacht_kwh": 0.10},
        ]
    }
    c._apply_persisted_state(copy.deepcopy(opgeslagen))
    c._bewaar_geladen_opslag(copy.deepcopy(opgeslagen))
    assert c.reserve_daily_records[0]["shortfall"] is False

    # de sensor herstelt zijn oude kopie eroverheen, zoals in bedrijf
    c.reserve_daily_records[0]["shortfall"] = True

    c.herstel_de_opslag_na_de_sensoren()

    assert c.reserve_daily_records[0]["shortfall"] is False
    assert c.reserve_daily_records[0]["herbeoordeeld"] == "v5.8"


def test_een_ingekort_sensorherstel_wordt_ongedaan_gemaakt(make_coordinator, hass):
    """De sensorattributen zijn afgekapt op 20 items. Een sensor die
    herstelt, zet dan een ingekorte reeks over de volledige opslag."""
    c = make_coordinator({})
    volledig = {"night_consumption_history": [float(i) for i in range(30)]}
    c._apply_persisted_state(copy.deepcopy(volledig))
    c._bewaar_geladen_opslag(copy.deepcopy(volledig))

    c.night_consumption_history = c.night_consumption_history[-20:]

    c.herstel_de_opslag_na_de_sensoren()

    assert len(c.night_consumption_history) == 30


def test_zonder_opslag_mag_de_sensor_herstellen(make_coordinator, hass):
    """Bij een allereerste installatie is er geen opslag, en dan is het
    sensorherstel de enige bron - dat moet blijven werken."""
    c = make_coordinator({})
    c._bewaar_geladen_opslag(None)
    c.night_consumption_history = [1.0, 2.0, 3.0]

    c.herstel_de_opslag_na_de_sensoren()

    assert c.night_consumption_history == [1.0, 2.0, 3.0]


def test_de_herstelstap_gebeurt_na_de_platforms():
    """De ratel: de volgorde in __init__.py. Eerst de platforms, dan de
    opslag nog eens terugzetten."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "__init__.py").read_text()
    platforms = bron.index("async_forward_entry_setups")
    herstel = bron.index("herstel_de_opslag_na_de_sensoren")

    assert herstel > platforms


def test_het_geheugen_van_de_opslag_wordt_daarna_losgelaten(make_coordinator, hass):
    """Een kopie van de hele opslag hoort niet het hele bedrijf in het
    geheugen te blijven."""
    c = make_coordinator({})
    c._bewaar_geladen_opslag({"night_consumption_history": [1.0]})

    c.herstel_de_opslag_na_de_sensoren()

    assert c._geladen_opslag is None
