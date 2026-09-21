"""De leermodus bleef na een herstart aanstaan zonder handmatige stand
(v5.9).

In de export van 17 september 14:25, net na de installatie van v5.2.1:

    learning_only = True
    handmatige_stand = None

Leermodus aan, zonder handmatige stand. Zolang die aanstond, stuurde het
EMS de accu niet.

De keten:

1. Een handmatige stand gaat aan. De integratie zet dan ook de
   leermodus aan, en onthoudt in `_leermodus_door_handmatige_stand` dat
   ZIJ dat deed - zodat hij bij het uitzetten weer uit kan.
2. Home Assistant herstart.
3. De leermodusschakelaar herstelt zijn toestand uit Home Assistant:
   AAN.
4. `handmatige_stand` en `_leermodus_door_handmatige_stand` worden NIET
   bewaard: beide weg.
5. De leermodus staat aan en niemand weet meer dat hij bij een
   handmatige stand hoorde. Hij blijft aan tot iemand hem uitzet.

Het verklaart ook de logregel van 18 september 13:15, *"Accukoeling aan -
wél uitgevoerd ondanks learning only"*. Dat gedrag was correct - de
koeling grijpt als bescherming in, ook in leermodus. De leermodus had er
alleen niet moeten staan.

Twee reparaties: de handmatige stand en de vlag worden bewaard, en bij
het opstarten wordt een inconsistente toestand opgeruimd.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 9, 17, 14, 25, tzinfo=timezone.utc)


def test_alleen_de_vlag_wordt_bewaard_niet_de_stand():
    """De handmatige stand overleeft met opzet geen herstart: "na een
    herstart hoort de accu NIET uren later nog handmatig te laden zonder
    dat iemand eraan denkt". Mijn eerste reparatie bewaarde de stand en
    draaide die veiligheidskeuze om; de toets over vluchtige velden
    keurde dat af. Alleen de vlag hoort bewaard te worden."""
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    assert "_leermodus_door_handmatige_stand" in PERSISTED_FIELDS
    assert "handmatige_stand" not in PERSISTED_FIELDS
    assert "handmatige_stand_sinds" not in PERSISTED_FIELDS


def test_na_een_herstart_is_de_stand_weg_maar_de_vlag_niet(make_coordinator, hass):
    """Precies de toestand van 17 september - en nu kan die worden
    opgeruimd, want de vlag weet waar de leermodus bij hoorde."""
    bron = make_coordinator({})
    bron.handmatige_stand = "laden"
    bron._leermodus_door_handmatige_stand = True

    verse = make_coordinator({})
    verse._apply_persisted_state(bron._collect_persisted_state())
    verse.learning_only = True   # zoals de schakelaar hem herstelt

    assert verse.handmatige_stand is None
    assert verse._leermodus_door_handmatige_stand is True
    assert verse.ruim_vastgelopen_leermodus_op() is True
    assert verse.learning_only is False


def test_een_vastgelopen_leermodus_wordt_opgeruimd(make_coordinator, hass):
    """Het gemeten geval: leermodus aan, vlag zegt dat de handmatige
    stand hem aanzette, maar de handmatige stand is weg."""
    c = make_coordinator({})
    c.learning_only = True
    c._leermodus_door_handmatige_stand = True
    c.handmatige_stand = None

    opgeruimd = c.ruim_vastgelopen_leermodus_op()

    assert opgeruimd is True
    assert c.learning_only is False
    assert c._leermodus_door_handmatige_stand is False


def test_een_bewust_aangezette_leermodus_blijft_staan(make_coordinator, hass):
    """Heeft de gebruiker de leermodus ZELF aangezet, dan is de vlag
    False en hoort hij te blijven staan."""
    c = make_coordinator({})
    c.learning_only = True
    c._leermodus_door_handmatige_stand = False
    c.handmatige_stand = None

    assert c.ruim_vastgelopen_leermodus_op() is False
    assert c.learning_only is True


def test_leermodus_met_een_lopende_handmatige_stand_blijft_staan(make_coordinator, hass):
    c = make_coordinator({})
    c.learning_only = True
    c._leermodus_door_handmatige_stand = True
    c.handmatige_stand = "laden"

    assert c.ruim_vastgelopen_leermodus_op() is False
    assert c.learning_only is True


def test_het_opruimen_gebeurt_na_het_herstel(make_coordinator, hass):
    """De ratel: pas NA het sensorherstel weet de integratie wat de
    schakelaar herstelde. Daarvoor is de leermodus nog niet teruggezet."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("def herstel_de_opslag_na_de_sensoren")
    j = bron.index("\n    def ", i + 10)

    assert "ruim_vastgelopen_leermodus_op" in bron[i:j]
