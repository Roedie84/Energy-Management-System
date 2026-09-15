"""Het gebied van een entiteit uit Home Assistant zelf (v4.14).

Overgenomen van ha-home-energy-advisor: dat leest het GEBIED van de
sensor uit het entiteitenregister, zodat kosten per kamer werken zonder
dat de gebruiker iets instelt. Dit EMS gebruikte het entiteitenregister
nergens - het kent 22 NILM-apparaten en weet van geen van hen in welke
kamer ze staan.

Waar dat iets oplevert: in de meldingen. "Sluipverbruik gestegen: 40 W"
wordt "Sluipverbruik gestegen: 40 W, sensor.koelkast_vermogen (Keuken)".
Een kamer erbij maakt het verschil tussen zoeken en weten.

Het register is niet altijd beschikbaar (een sensor kan er los van
staan, en in toetsen bestaat het soms niet), dus dit mag nooit een
storing geven - zonder gebied gewoon geen gebied.
"""
import pytest


def test_een_entiteit_met_een_gebied(make_coordinator, hass):
    c = make_coordinator({})
    hass.states.set("sensor.koelkast_vermogen", "42", {"unit_of_measurement": "W"})

    class _Item:
        area_id = "keuken"
        device_id = None

    class _Reg:
        @staticmethod
        def async_get(entity_id):
            return _Item() if entity_id == "sensor.koelkast_vermogen" else None

    class _Gebieden:
        @staticmethod
        def async_get_area(area_id):
            return type("A", (), {"name": "Keuken"})() if area_id == "keuken" else None

    c._entiteitenregister = lambda: _Reg()
    c._gebiedenregister = lambda: _Gebieden()

    assert c.gebied_van("sensor.koelkast_vermogen") == "Keuken"


def test_zonder_register_geen_gebied(make_coordinator, hass):
    """In toetsen en bij een losse sensor bestaat het register niet - dat
    mag nooit een storing geven."""
    c = make_coordinator({})
    c._entiteitenregister = lambda: None

    assert c.gebied_van("sensor.wat_dan_ook") is None


def test_een_onbekende_entiteit_geeft_niets(make_coordinator, hass):
    c = make_coordinator({})

    assert c.gebied_van("sensor.bestaat_niet") is None
    assert c.gebied_van(None) is None


def test_het_gebied_komt_in_de_apparaatnaam(make_coordinator, hass):
    """Wat de melding uiteindelijk toont."""
    c = make_coordinator({})
    c.gebied_van = lambda e: "Keuken" if "koelkast" in str(e) else None

    assert c.met_gebied("sensor.koelkast_vermogen") == "sensor.koelkast_vermogen (Keuken)"
    assert c.met_gebied("sensor.losse_meter") == "sensor.losse_meter"


def test_een_storing_in_het_register_breekt_niets(make_coordinator, hass):
    c = make_coordinator({})

    def stuk():
        raise RuntimeError("register weg")

    c._entiteitenregister = stuk

    assert c.gebied_van("sensor.x") is None


def test_de_apparaataanwijzing_noemt_de_kamer(make_coordinator, hass):
    """Waar het iets oplevert: "Sluipverbruik gestegen: 40 W" wordt
    "sensor.koelkast_vermogen (Keuken) (12 → 52 W)"."""
    c = make_coordinator({})
    c.met_gebied = lambda e: f"{e} (Keuken)" if "koelkast" in str(e) else str(e)
    c.welke_apparaten_stegen = lambda: {
        "beschikbaar": True,
        "stijgers": [
            {"entiteit": "sensor.koelkast_vermogen", "toen_w": 12.0, "nu_w": 52.0,
             "nieuw": False},
        ],
    }

    tekst = c._sluipverbruik_verdachten_zin()

    assert "(Keuken)" in tekst
    assert "12 → 52 W" in tekst
