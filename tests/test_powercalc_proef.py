"""Verklaart Powercalc een stuk van het huisverbruik? (v3.97.0)

Gevraagd: "Deze integratie heb ik ook, kunnen we daar nog wat mee" - met
sensoren als `sensor.eetkamer_lamp_3_power`.

Powercalc MEET niet. Het schat vermogen uit een profielbibliotheek of
een lineair model. Zo'n getal in de reserve stoppen zou dezelfde fout
zijn als `available_kwh` (een rekensom die als meting werd gelezen) en
`gemeten_kwh` (de nominale sensor die als gemeten capaciteit gold).

Waar het wel iets kan opleveren is het RESIDU voor NILM. De
apparaatherkenning leest het totaal van de meter en zoekt daarin
startsprongen. Alles wat je onafhankelijk van dat totaal kunt verklaren,
maakt de rest rustiger - en verlichting is precies het soort continu
wisselende ruis waar een startdetectie last van heeft.

Of dat werkelijk zo is, is te meten: wordt het residu (gemeten min
geschat) STILLER dan het gemeten totaal zelf? Zo niet, dan voegt de
schatting ruis toe in plaats van dat ze die wegneemt, en weet je dat
voordat er iets op stuurt.

Deze proef stuurt niets. Hij meet en beoordeelt zichzelf.
"""
import pytest

from custom_components.energy_management_system.const import (
    POWERCALC_MIN_METINGEN,
    RELIABILITY_INSUFFICIENT,
)


def _sensoren(hass, waarden):
    for entity_id, watt in waarden.items():
        hass.states.set(entity_id, str(watt), {"source_entity": "light.x"})


# --- 1. de sensoren vinden -------------------------------------------


def test_powercalc_sensoren_worden_herkend(make_coordinator, hass):
    """Powercalc zet `source_entity` op elke sensor die het maakt. Dat

    is het kenmerk, niet de naam - `sensor.eetkamer_lamp_3_power` is
    verder niet van een echte meter te onderscheiden.
    """
    c = make_coordinator({})
    _sensoren(hass, {"sensor.eetkamer_lamp_3_power": 8.4})
    hass.states.set("sensor.echte_meter_power", "1200")

    gevonden = c.powercalc_sensoren()

    assert gevonden == ["sensor.eetkamer_lamp_3_power"]


def test_alleen_vermogen_geen_energie(make_coordinator, hass):
    """Naast elke `_power` staat een `_energy` in kWh. Die optellen bij

    watts levert onzin op.
    """
    c = make_coordinator({})
    _sensoren(
        hass,
        {
            "sensor.eetkamer_lamp_3_power": 8.4,
            "sensor.eetkamer_lamp_3_energy": 12.9,
        },
    )

    assert c.powercalc_sensoren() == ["sensor.eetkamer_lamp_3_power"]


def test_het_geschatte_totaal_is_de_som(make_coordinator, hass):
    c = make_coordinator({})
    _sensoren(
        hass,
        {
            "sensor.eetkamer_lamp_3_power": 8.4,
            "sensor.gang_lamp_power": 5.1,
        },
    )

    assert c.powercalc_geschat_vermogen_w() == pytest.approx(13.5, abs=0.05)


def test_zonder_powercalc_geen_getal(make_coordinator, hass):
    """Liever niets dan nul: nul leest als "verlichting uit"."""
    c = make_coordinator({})

    assert c.powercalc_geschat_vermogen_w() is None


# --- 2. de vraag die ertoe doet --------------------------------------


def _meet(c, paren):
    c.powercalc_paren = [list(p) for p in paren]


def test_zonder_genoeg_metingen_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    _meet(c, [(300.0, 40.0)] * 5)

    proef = c.get_powercalc_proef()

    assert proef["status"] == RELIABILITY_INSUFFICIENT
    assert proef["mag_regelen"] is False
    assert proef["wat_ontbreekt"]


def test_een_schatting_die_de_ruis_wegneemt_scoort(make_coordinator, hass):
    """Het gunstige geval: de verlichting is de bron van de schommeling,

    en na aftrek blijft een vlakke basislast over.
    """
    c = make_coordinator({})
    paren = [
        (250.0 + 40 * (i % 5), 40.0 * (i % 5))
        for i in range(POWERCALC_MIN_METINGEN + 10)
    ]
    _meet(c, paren)

    proef = c.get_powercalc_proef()

    assert proef["residu_rustiger"] is True
    assert proef["spreiding_residu_w"] < proef["spreiding_gemeten_w"]


def test_een_schatting_die_niets_verklaart_valt_door(make_coordinator, hass):
    """Staat de schatting los van wat de meter doet, dan wordt het

    residu juist onrustiger - en dan is aftrekken schadelijk.
    """
    c = make_coordinator({})
    paren = [
        (250.0 + 40 * (i % 5), 40.0 * ((i + 3) % 5))
        for i in range(POWERCALC_MIN_METINGEN + 10)
    ]
    _meet(c, paren)

    assert c.get_powercalc_proef()["residu_rustiger"] is False


def test_de_proef_stuurt_niets(make_coordinator, hass):
    """Vaste afspraak: kandidaten sturen pas na bewijs, met de hand

    aangezet.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_powercalc_proef")
    blok = bron[kop : kop + 3500]

    assert "async_set" not in blok
    assert "_async_set_switch" not in blok


def test_het_aandeel_van_de_verlichting_staat_erbij(make_coordinator, hass):
    """Hoeveel van het huisverbruik verklaart Powercalc? Zonder dat

    getal is niet te beoordelen of het de moeite waard is.
    """
    c = make_coordinator({})
    _meet(c, [(250.0, 50.0)] * (POWERCALC_MIN_METINGEN + 1))

    proef = c.get_powercalc_proef()

    assert proef["aandeel_procent"] == pytest.approx(20.0, abs=0.5)
