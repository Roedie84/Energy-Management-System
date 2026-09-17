"""Vier bevindingen uit de meldingenlijst van 15 september (v4.15).

De volledige lijst van twaalf meldingen op één dag, en daarin vier
dingen die niet kloppen.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 15, 10, 36, tzinfo=timezone.utc)


# --- 1. De koelgrens liet de accu oplopen tot de bescherming ----------
#
#   10:27  De koeling geet te vaak an ... De koeling ligt tot
#          middernacht stil - de bescherming boven 35 °C blijft warken.
#   10:36  De koeling geet an. Accu 35.0 °C, buiten 20.4 °C.
#
# Negen minuten na het stilleggen stond de accu op precies de
# beschermingsdrempel. De grens van vier goedkope koelbeurten per dag is
# bedoeld tegen pendelen, maar v4.9.6 heeft al gemeten dat de beurten op
# DEZE installatie werken: acht tot dertien graden daling per keer. De
# grens legde dus een werkende koellus stil, waarna het pakket opliep
# tot 35 en de bescherming het moest overnemen.
#
# De grens geldt nu alleen als de beurten NIET werken - `koeling_pendelt`
# uit v4.9.6 beslist dat, met dezelfde meting.


def _werkende_cyclus(c):
    c.battery_cooling_history = []
    for n in range(4):
        c.battery_cooling_history += [
            {"moment": f"2026-09-15T{8 + n:02d}:00:00+02:00", "actie": "aan", "accu_c": 35.0},
            {"moment": f"2026-09-15T{8 + n:02d}:50:00+02:00", "actie": "uit", "accu_c": 26.0},
        ]


def test_een_werkende_koellus_wordt_niet_stilgelegd(make_coordinator, hass):
    c = make_coordinator({})
    _werkende_cyclus(c)
    c.goedkope_koeling_teldag = NU.date()
    c.goedkope_koeling_teller = 6

    assert c._goedkope_koeling_op_slot(NU) is False


def test_een_pendelende_koellus_wel(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_cooling_history = []
    for n in range(4):
        c.battery_cooling_history += [
            {"moment": f"2026-09-15T{8 + n:02d}:00:00+02:00", "actie": "aan", "accu_c": 28.1},
            {"moment": f"2026-09-15T{8 + n:02d}:04:00+02:00", "actie": "uit", "accu_c": 27.9},
        ]
    c.goedkope_koeling_teldag = NU.date()
    c.goedkope_koeling_teller = 6

    assert c._goedkope_koeling_op_slot(NU) is True


# --- 2. De veroudering rekende met de omvormerwarmte ------------------
#
# Gemeld: "Module 1 zit direct onder de omvormer." De verouderingstelling
# pakte `max(temperaturen)` over de modules, en dat is altijd module 1 -
# dus altijd de omvormerwarmte. De teller "uren boven 30 graden" rekende
# de omvormer mee als celveroudering, en dat getal zit onder de
# slijtagekosten van 11,6 ct/kWh en dus onder elke verkoopbeslissing.
#
# Nu de MEDIAAN over de modules, met de hoogste er apart bij. Eén module
# die van buiten wordt opgewarmd bepaalt de veroudering van het pakket
# niet.


def test_de_veroudering_rekent_met_de_mediaan(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = [
        {"module": 1, "temperatuur_c": 35.0},
        {"module": 2, "temperatuur_c": 27.0},
        {"module": 3, "temperatuur_c": 27.0},
    ]

    assert c.celtemperatuur_voor_veroudering_c() == 27.0
    assert c.hoogste_moduletemperatuur_c() == 35.0


def test_met_een_module_blijft_het_die_ene(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = [{"module": 1, "temperatuur_c": 31.0}]

    assert c.celtemperatuur_voor_veroudering_c() == 31.0


def test_zonder_modules_geen_waarde(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = []

    assert c.celtemperatuur_voor_veroudering_c() is None


# --- 3. De apparaatvlaggen overleefden geen herstart ------------------
#
#   12:34  Steelstofzuiger opgeladen
#   13:01  Steelstofzuiger opgeladen
#
# Twee keer dezelfde melding binnen een half uur. Daartussen zat een
# herstart (v4.14 werd om 12:57 geïnstalleerd), en de vlag "vandaag al
# klaar" wordt niet bewaard. Na de herstart begon het laden opnieuw en
# kwam de melding opnieuw.
#
# Dezelfde klasse als de dagmetingen van v4.7: een dagvlag die alleen in
# het geheugen staat. Daar repareerde ik zes velden en miste deze vier.


def test_de_apparaatvlaggen_worden_bewaard():
    from custom_components.energy_management_system.const import (
        PERSISTED_DATE_FIELDS,
        PERSISTED_PLAIN_FIELDS,
    )

    for apparaat in ("steelstofzuiger", "fietsladers"):
        assert f"_{apparaat}_complete_today" in PERSISTED_PLAIN_FIELDS, apparaat
        assert f"_{apparaat}_complete_date" in PERSISTED_DATE_FIELDS, apparaat


def test_elke_dagvlag_van_een_apparaat_wordt_bewaard():
    """De ratel: een nieuw apparaat met een `_complete_today`-vlag die
    niet bewaard wordt, laat deze toets omvallen."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    from custom_components.energy_management_system.const import (
        PERSISTED_DATE_FIELDS,
        PERSISTED_PLAIN_FIELDS,
    )

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    vlaggen = set(re.findall(r'"(_\w+_complete_today)"', bron))
    datums = set(re.findall(r'"(_\w+_complete_date)"', bron))

    assert vlaggen, "geen vlaggen gevonden - is de vorm veranderd?"
    assert not (vlaggen - set(PERSISTED_PLAIN_FIELDS)), sorted(vlaggen - set(PERSISTED_PLAIN_FIELDS))
    assert not (datums - set(PERSISTED_DATE_FIELDS)), sorted(datums - set(PERSISTED_DATE_FIELDS))


def test_de_vlag_komt_terug_na_een_herstart(make_coordinator, hass):
    bron = make_coordinator({})
    bron._steelstofzuiger_complete_today = True
    bron._steelstofzuiger_complete_date = date(2026, 9, 15)

    verse = make_coordinator({})
    verse._apply_persisted_state(bron._collect_persisted_state())

    assert verse._steelstofzuiger_complete_today is True
    assert verse._steelstofzuiger_complete_date == date(2026, 9, 15)


# --- 4. "Twee soorten dagen" bij één dag van elk ----------------------
#
#   15 Sep 12:00 · De zunne dut minder as verwacht
#   "Twee soorten dagen: 1 van de 5 binnen 10% en 1 meer dan 25%
#    ernaast."
#
# Eén goede dag en één missende dag van de vijf, en daaruit de uitspraak
# "twee soorten dagen" plus een oordeel over de bewolkingsinschatting van
# de voorspelling. `spreiding = bool(goed) and bool(ver_mis)` - één van
# elk is genoeg. Bij vijf dagen is dat toeval dat als patroon wordt
# gepresenteerd, en de melding zegt er wel wat de gebruiker moet DOEN.
#
# Twee van elk als minimum. Daaronder blijft de melding gewoon "de
# opbrengst blijft achter", zonder de verklaring erbij.


def test_een_van_elk_is_nog_geen_patroon(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = type("T", (), {"deviation_history": [-5.0, -30.0, -14.0, -12.0, -11.0]})()

    uit = c.get_solar_forecast_health()

    assert "Twee soorten dagen" not in str(uit.get("reden", ""))


def test_twee_van_elk_wel(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = type(
        "T", (),
        {"deviation_history": [-2.0, -35.0, 4.0, -40.0, -3.0, -30.0, 1.0, -45.0]},
    )()

    uit = c.get_solar_forecast_health()

    assert "Twee soorten dagen" in str(uit.get("reden", ""))
