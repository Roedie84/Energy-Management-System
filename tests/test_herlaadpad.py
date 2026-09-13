"""Het herlaadpad laat niets achter (v4.11).

Doorloop 4 van de audit: de Home Assistant-laag. Dit is de laag die
deze week drie keer faalde op het entiteitenregister, en de laag waar
de toetsen het minst over zeggen - de suite draait zonder echte Home
Assistant.

Twee bevindingen, beide in het herlaadpad:

1. `_unsub_motion_state` wordt aangemaakt (coordinator.py:2033) en
   nergens opgezegd. Bij elke herlaad blijft een listener op de
   bewegingssensoren achter die naar de OUDE coordinator schrijft. Dat
   is precies de fout die in v3.29.0 bij de zonhelling is gevonden en
   daar wel is opgelost - hier bleef hij staan. Na tien herlaadacties
   liggen er tien listeners die allemaal de aanwezigheid bijwerken van
   coordinators die niemand meer leest.

2. De services worden bij `async_setup_entry` geregistreerd en bij
   `async_unload_entry` niet verwijderd. Bij de laatste config-entry
   blijven ze bestaan en verwijzen ze naar een opgeruimde coordinator.
"""
import ast
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent


def test_elke_listener_wordt_opgezegd():
    """De ratel: elk `_unsub_`-veld dat wordt GEZET, moet in
    `async_unload` worden opgezegd."""
    bron = (PAKKET / "coordinator.py").read_text()
    gezet = set(re.findall(r"self\.(_unsub_\w+) = async_track", bron))
    i = bron.index("async def async_unload(self)")
    j = bron.index("\n    async def ", i + 10)
    opgezegd = set(re.findall(r"self\.(_unsub_\w+)", bron[i:j]))

    assert not (gezet - opgezegd), sorted(gezet - opgezegd)


def test_de_bewegingslistener_wordt_opgezegd():
    """Het gevonden geval."""
    bron = (PAKKET / "coordinator.py").read_text()
    i = bron.index("async def async_unload(self)")
    j = bron.index("\n    async def ", i + 10)

    assert "_unsub_motion_state" in bron[i:j]


def test_de_services_verdwijnen_met_de_laatste_entry():
    """Geregistreerde services die naar een opgeruimde coordinator
    wijzen, geven een stille fout bij de eerstvolgende aanroep."""
    bron = (PAKKET / "__init__.py").read_text()
    i = bron.index("async def async_unload_entry")

    assert "services.async_remove" in bron[i:]


def test_de_services_blijven_zolang_er_een_entry_is():
    """Met twee entries mag het opruimen van de ene de services van de
    andere niet weghalen."""
    bron = (PAKKET / "__init__.py").read_text()
    i = bron.index("async def async_unload_entry")
    staart = bron[i:]

    # de opruiming gebeurt alleen als er geen entry meer over is
    assert "resterend" in staart, "geen controle op resterende entries"
    assert "if not resterend:" in staart


def test_elke_geregistreerde_service_staat_in_de_opruimlijst():
    """De ratel: een nieuwe service die niet in EIGEN_SERVICES staat,
    blijft bij het opruimen achter."""
    import custom_components.energy_management_system as mod

    bron = (PAKKET / "__init__.py").read_text()
    boom = ast.parse(bron)
    geregistreerd = set()
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Call):
            continue
        if getattr(knoop.func, "attr", None) != "async_register":
            continue
        if len(knoop.args) < 2:
            continue
        naam = knoop.args[1]
        if isinstance(naam, ast.Constant):
            geregistreerd.add(naam.value)
        elif isinstance(naam, ast.Name):
            geregistreerd.add(getattr(mod, naam.id, naam.id))

    ontbreekt = geregistreerd - set(mod.EIGEN_SERVICES)
    assert not ontbreekt, sorted(ontbreekt)
