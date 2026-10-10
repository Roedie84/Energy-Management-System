"""v5.78 (Ruud 10-10 16:31): "pas uit na 5 minuten als er iets open gaat".

Heeft het EMS de airco aangezet en gaat een raam open, dan zet het EMS hem pas
uit als het raam 5 minuten open is (gelijk met de HA-automatisering).
Aanzetten met een raam open blijft altijd geblokkeerd.
"""
from datetime import timedelta

from custom_components.energy_management_system import airco_sturing

from tests.test_airco_sturing import NU
from tests.test_v577 import RAMEN, _met_ramen


def _ems_aan(make_coordinator, hass):
    c = _met_ramen(make_coordinator, hass, keuken="on", stand="heat", doel=21.0)
    c.airco_automaat_aan = True
    c.airco_door_ems = True
    c._airco_laatste_ems = {"stand": "heat", "doel": 21.0, "basis": 21.0}
    c._airco_laatst_gezien = ("heat", 21.0)
    hass.states.get(RAMEN[2]).last_changed = NU
    return c


def test_raam_net_open_dan_nog_niet_uit(make_coordinator, hass):
    c = _ems_aan(make_coordinator, hass)
    c._airco_ronde(NU + timedelta(minutes=2))
    b = c.last_airco_besluit
    assert b["actie"] == "niets" and b["raam_open"] is True
    assert "over 3 min uit" in b["tekst"]


def test_raam_vijf_minuten_open_dan_uit(make_coordinator, hass):
    c = _ems_aan(make_coordinator, hass)
    c._airco_ronde(NU + timedelta(minutes=5, seconds=1))
    assert c.last_airco_besluit["actie"] == "uit"


def test_aanzetten_blijft_direct_geblokkeerd():
    uit = {"actie": "verwarmen", "tekst": "Aanzetten.", "redenen": []}
    b = airco_sturing.raam_open(
        uit, {"open": ["Raam"], "onbekend": []}, airco_stand="off", door_ems_aan=False,
        open_sinds_s=5, uitstel_s=300,
    )
    assert b["actie"] == "niets"
