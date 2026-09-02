""""Accu: handmatig" zegt niet wat de accu doet (v3.99.7).

Gemeld met de export van 21:18: "Meldingen accu status lijken nog niet
correct: zie laatste melding accu modus."

    20:04  💰⬇️ Accu: handmatig     "de accu ontlaadt nu actief op 1600W"
    21:17  ⏳ Accu: ontladen        "🔌 Vermogen: 1600 W" ...
                                    "zonder actief te verkopen"

Drie dingen.

1. "handmatig" is de STAND, niet wat de accu doet. Handmatig kan laden
   uit het net zijn of verkopen tegen de dure prijs - tegengestelde
   dingen met dezelfde naam. Het emoji wist het (💰⬇️), het woord niet.
   De REDEN weet het wel: `expensive_quarter` is verkopen,
   `grid_charging_low_solar` is laden. De titel volgt nu de reden.

2. "Vermogen: 1600 W" bij slim ontladen. Dat is het ontlaadvermogen dat
   nog stond van de handmatige stand ervoor. In een slimme stand regelt
   het apparaat het vermogen zelf; er is dan niets om te melden.

3. "Daarom wordt laden uitgesteld" om kwart over negen 's avonds. De
   energiebrug-tekst gaat over of de accu de nacht haalt, niet over
   laden. Dat is de uitleg, niet de titel; die staat op de lijst.
"""
import pytest


def _titel(c, reden, modus):
    c.last_reason = reden
    c.last_expected_mode = modus
    return c._modusmelding_titel()


def test_verkopen_heet_verkopen(make_coordinator, hass):
    c = make_coordinator({})
    assert "verkopen" in _titel(c, "expensive_quarter", "manual")


def test_laden_uit_het_net_heet_zo(make_coordinator, hass):
    c = make_coordinator({})
    assert "laden" in _titel(c, "grid_charging_low_solar", "manual")
    assert "verkopen" not in _titel(c, "grid_charging_low_solar", "manual")


def test_slim_ontladen_heet_huis_dekken(make_coordinator, hass):
    """"ontladen" naast "verkopen" leest als hetzelfde. De accu dekt het

    huis en verkoopt niet; dat verschil is precies waar de melding om
    gaat.
    """
    c = make_coordinator({})
    t = _titel(c, "discharging_window", "smart_discharging")
    assert "huis" in t.lower()


def test_onbekende_reden_valt_terug_op_de_stand(make_coordinator, hass):
    c = make_coordinator({})
    assert "slim" in _titel(c, "iets_nieuws", "smart")


def test_geen_vermogensregel_in_een_slimme_stand(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reason = "discharging_window"
    c.last_expected_mode = "smart_discharging"
    c.last_discharge_power_applied = 1600.0

    assert c._modusmelding_vermogen() is None


def test_wel_vermogensregel_in_de_handmatige_stand(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reason = "expensive_quarter"
    c.last_expected_mode = "manual"
    c.last_discharge_power_applied = 1600.0

    assert c._modusmelding_vermogen() == "1600 W"
