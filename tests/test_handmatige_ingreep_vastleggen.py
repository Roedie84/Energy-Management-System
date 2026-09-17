"""Wat er gebeurde toen jij zelf ingreep (v4.18).

Gemeld: "Gister moest ik even manueel bijladen, omdat ik de wasmachine
en vaatwasser aan had. Hoe kun je hier van leren?" - en daarna, terecht:
"Dit kun je toch uit de diagnostiek halen?"

Nee, en dat is het probleem. Wat er wél in de export staat, van 13
september:

    12:31  handmatige_stand: laden, accu 38%
    13:31  nog aan, accu 38%
    14:31  nog aan, accu 59%

Twee meldingen, en verder niets. De reserve die het EMS op dat moment
aanhield staat er niet bij, het beschikbare niet, welke apparaten liepen
niet, en hoeveel er is bijgeladen niet. In het dagverloop staat bij die
kwartieren `default_smart` - want het EMS stuurde niet - dus uit de
kwartierregels is niet te zien dat de gebruiker aan het stuur stond.

Daardoor heb ik de netpiek van 13 september eerst verkeerd verklaard:
ik schreef dat het `grid_charging_low_solar` was en dus bewust EMS-
gedrag. Het was een handmatige lading. En de nabeschouwing van die dag
heeft die kwartieren beoordeeld als EMS-beslissing, dus ze zitten in het
gemiste bedrag.

Een handmatige ingreep is het waardevolste signaal dat het EMS kan
krijgen: de gebruiker zegt "je zat ernaast". Dat hoort te worden
vastgelegd met de omstandigheden erbij, en de kwartieren horen als
`handmatig` in het dagverloop zodat de nabeschouwing ze niet op de
rekening van de sturing schrijft.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 16, 12, 31, tzinfo=timezone.utc)


def _situatie(c, hass):
    c.last_available_kwh = 3.32
    c.last_reserve_margin_breakdown = {"reserve_kwh_after_margin": 5.2}
    c.accustand_procent = lambda: 38.0
    c.appliance_cycle_kwh = {"vaatwasser": 1.1, "wasmachine": 0.9}
    c.config = dict(c.config or {})
    c.config["dishwasher_power_sensor_entity"] = "sensor.vaatwasser_w"
    c.config["washing_machine_power_sensor_entity"] = "sensor.wasmachine_w"
    hass.states.set("sensor.vaatwasser_w", "1850", {"unit_of_measurement": "W"})
    hass.states.set("sensor.wasmachine_w", "420", {"unit_of_measurement": "W"})


def test_de_ingreep_wordt_vastgelegd_met_omstandigheden(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c, hass)
    c.handmatige_ingrepen = []

    c.noteer_handmatige_ingreep("laden", NU)

    ingreep = c.handmatige_ingrepen[-1]
    assert ingreep["stand"] == "laden"
    assert ingreep["soc"] == 38.0
    assert ingreep["beschikbaar_kwh"] == 3.32
    assert ingreep["reserve_kwh"] == 5.2
    # het EMS hield 5,2 kWh nodig en had 3,32: dat verklaart de ingreep
    assert ingreep["tekort_kwh"] == pytest.approx(1.88, abs=0.01)


def test_de_lopende_apparaten_staan_erbij(make_coordinator, hass):
    """Het antwoord op "waarom greep je in": de wasmachine en de
    vaatwasser stonden aan."""
    c = make_coordinator({})
    _situatie(c, hass)
    c.handmatige_ingrepen = []

    c.noteer_handmatige_ingreep("laden", NU)

    apparaten = c.handmatige_ingrepen[-1]["apparaten_aan"]
    assert "vaatwasser" in apparaten
    assert apparaten["vaatwasser"] == 1850.0


def test_het_einde_wordt_erbij_geschreven(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c, hass)
    c.handmatige_ingrepen = []
    c.noteer_handmatige_ingreep("laden", NU)

    c.accustand_procent = lambda: 59.0
    c.noteer_handmatige_ingreep(None, NU + timedelta(hours=2))

    ingreep = c.handmatige_ingrepen[-1]
    assert ingreep["geeindigd"] == (NU + timedelta(hours=2)).isoformat()
    assert ingreep["duur_minuten"] == 120
    assert ingreep["soc_eind"] == 59.0
    assert ingreep["bijgeladen_procent"] == 21.0


def test_het_dagverloop_noemt_de_handmatige_stand(make_coordinator, hass):
    """Anders rekent de nabeschouwing die kwartieren als EMS-beslissing."""
    c = make_coordinator({})
    c.force_manual = True
    c.handmatige_stand = "laden"
    c.last_reason = "default_smart"

    assert c.reden_voor_het_dagverloop() == "handmatig_laden"


def test_zonder_handmatige_stand_gewoon_de_reden(make_coordinator, hass):
    c = make_coordinator({})
    c.force_manual = False
    c.last_reason = "arbitrage_solar_capture"

    assert c.reden_voor_het_dagverloop() == "arbitrage_solar_capture"


def test_de_nabeschouwing_slaat_handmatige_kwartieren_over(make_coordinator, hass):
    """Wat de gebruiker zelf deed, hoort niet in het gemiste bedrag van
    het EMS."""
    c = make_coordinator({})
    c.dagverloop = {
        "2026-09-16": [
            {"tijd": "12:00", "reden": "default_smart", "prijs_ct": 30.0,
             "huis_w": 200, "pv_w": 0, "accu_w": 100, "soc": 40.0},
            {"tijd": "12:15", "reden": "handmatig_laden", "prijs_ct": 30.0,
             "huis_w": 200, "pv_w": 0, "accu_w": -2000, "soc": 45.0},
        ]
    }

    uit = c.handmatige_kwartieren("2026-09-16")

    assert uit == 1


def test_het_overzicht_telt_de_ingrepen(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c, hass)
    c.handmatige_ingrepen = []
    c.noteer_handmatige_ingreep("laden", NU)
    c.noteer_handmatige_ingreep(None, NU + timedelta(hours=1))

    o = c.get_handmatige_ingrepen_overzicht()

    assert o["aantal"] == 1
    assert o["laatste"]["stand"] == "laden"
    assert "tekort" in o["patroon"].lower() or "te weinig" in o["patroon"].lower()


def test_de_geschiedenis_blijft_begrensd(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        HANDMATIGE_INGREPEN_LENGTE,
    )

    c = make_coordinator({})
    _situatie(c, hass)
    c.handmatige_ingrepen = []
    for n in range(HANDMATIGE_INGREPEN_LENGTE + 5):
        c.noteer_handmatige_ingreep("laden", NU + timedelta(hours=n))
        c.noteer_handmatige_ingreep(None, NU + timedelta(hours=n, minutes=30))

    assert len(c.handmatige_ingrepen) == HANDMATIGE_INGREPEN_LENGTE


def test_de_nabeschouwing_meldt_de_handmatige_kwartieren(make_coordinator, hass):
    """Niet stil verrekenen maar melden: dan blijft het cijfer
    navolgbaar. De handmatige lading van 13 september zat in het gemiste
    bedrag van die dag zonder dat er iets over stond."""
    c = make_coordinator({})
    c.dagverloop = {
        "2026-09-16": [
            {"tijd": f"{u:02d}:00", "reden": "handmatig_laden" if u < 3 else "default_smart",
             "prijs_ct": 30.0, "huis_w": 200, "pv_w": 0, "accu_w": 100, "soc": 40.0}
            for u in range(24)
        ]
    }

    assert c.handmatige_kwartieren("2026-09-16") == 3
