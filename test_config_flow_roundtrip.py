"""Configuratieformulier overleeft opslaan én heropenen (v1.15.1).

Gemeld met screenshot: bij het bewerken van de configuratie toonden de
PV-oriëntatie en hellingshoek "expected str", en het formulier was niet
te verzenden.

Dit is het spiegelbeeld van v1.4.2. Toen gaf een leeg NumberSelector
"expected float", dus werden het tekstvelden. Maar `_validate_input`
slaat een ingevulde waarde op als GETAL (200.0), en bij het heropenen
kreeg het tekstveld dat getal terug.

Beide keren werd het HELE formulier geblokkeerd - ook alle andere
instellingen erop. Er was geen test die de volledige heen-en-terugweg
afliep, en daardoor kon dezelfde fout twee keer ontstaan.
"""
from custom_components.energy_management_system.config_flow import (
    _as_text,
    _validate_input,
)
from custom_components.energy_management_system.const import (
    CONF_PV_ACTUAL_AZIMUTH_DEGREES,
    CONF_PV_ACTUAL_TILT_DEGREES,
)


# --- de heen-en-terugweg ---------------------------------------------


def test_a_saved_value_is_shown_as_text():
    """De kern: opslaan als getal, tonen als tekst."""
    invoer = {CONF_PV_ACTUAL_AZIMUTH_DEGREES: "200"}
    assert _validate_input(invoer) == {}

    opgeslagen = invoer[CONF_PV_ACTUAL_AZIMUTH_DEGREES]
    assert opgeslagen == 200.0

    getoond = _as_text(opgeslagen)
    assert isinstance(getoond, str)
    assert getoond == "200"


def test_the_round_trip_is_stable():
    """Opslaan, tonen, opnieuw opslaan: de waarde mag niet verlopen."""
    invoer = {CONF_PV_ACTUAL_TILT_DEGREES: "12"}
    _validate_input(invoer)

    tweede = {CONF_PV_ACTUAL_TILT_DEGREES: _as_text(invoer[CONF_PV_ACTUAL_TILT_DEGREES])}
    assert _validate_input(tweede) == {}

    assert tweede[CONF_PV_ACTUAL_TILT_DEGREES] == 12.0


def test_a_decimal_survives_the_round_trip():
    invoer = {CONF_PV_ACTUAL_TILT_DEGREES: "12,5"}
    _validate_input(invoer)

    assert _as_text(invoer[CONF_PV_ACTUAL_TILT_DEGREES]) == "12.5"


# --- de weergavehelper -----------------------------------------------


def test_whole_numbers_lose_their_decimal():
    """"200" leest prettiger dan "200.0"."""
    assert _as_text(200.0) == "200"
    assert _as_text(12.0) == "12"


def test_empty_stays_empty():
    """Leeg laten betekent "geen ijkpunt" - dat mag geen "None"
    worden."""
    assert _as_text(None) == ""
    assert _as_text("") == ""


def test_it_always_returns_a_string():
    """Een TextSelector weigert alles wat geen tekst is, en blokkeert
    daarmee het hele formulier."""
    for waarde in (None, "", 0, 200, 200.0, 12.5, "200"):
        assert isinstance(_as_text(waarde), str), waarde


# --- borging tegen herhaling -----------------------------------------


def test_every_text_field_shows_its_default_as_text():
    """Beide keren dat dit misging, ontbrak een test die de
    standaardwaarde van een tekstveld controleerde. Deze scant het
    formulier: een TextSelector mag zijn standaard nooit rechtstreeks
    uit de opslag halen, want daar kan een getal in staan.
    """
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "config_flow.py").read_text()

    for blok in re.finditer(
        r"default=([^\n]+),\n\s*\): selector\.TextSelector", bron
    ):
        standaard = blok.group(1)
        assert "_as_text(" in standaard, (
            f"tekstveld met onbewerkte standaard: {standaard}"
        )
