"""De doorklik achter de cockpit (v5.23).

Uit de cockpit-opdracht: AANDACHT aanklikbaar maken "zodat ik kan zien
welke twee aandachtspunten actief zijn", en "als ik wil weten WAAROM de
reserve bijvoorbeeld 4,60 kWh bedraagt, moet dat liever via doorklik
beschikbaar zijn, gebaseerd op de daadwerkelijke Dynamic Reserve-
berekening".

De plaat staat in een markdown-kaart, en die kent geen tikactie. Dus twee
knoppen onder de plaat, naar de pagina's die er AL waren: Meetkwaliteit
(met de kaart Aandachtspunten) en Reservemarge. Een eigen detailpagina was
dubbel geweest - de dashboardregels vingen dat.
"""
from pathlib import Path

import jinja2
import yaml

import custom_components.energy_management_system as pkg


def test_zonder_verschuiving_en_bodem_geen_zin(make_coordinator, hass):
    c = make_coordinator({})

    assert c._verschuiving_en_bodem_zin({"regelverschuiving_w": 0, "bodem_kwh": None}) == ""


def test_de_uitsplitsing_draagt_de_verschuiving_en_de_bodem(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reserve_margin_breakdown = {
        "base_percent": 10.0, "total_percent": 10.0,
        "needed_kwh_before_margin": 5.21, "reserve_kwh_after_margin": 5.73,
        "regelverschuiving_w": 50, "bodem_kwh": 1.296, "bodem_bindend": False,
    }

    overzicht = c.get_reserve_margin_overview()

    assert overzicht["regelverschuiving_w"] == 50
    assert overzicht["bodem_kwh"] == 1.296
