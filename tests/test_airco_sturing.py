"""Automatische airco-sturing voor de woonkamer (v5.27).

Gevraagd: "geschikt voor automatische airco sturing, echter nog niet actief
(dus met aan/uit knop)" - "voor zowel stand aan als uit kunnen zien wat de
besluitvorming van het EMS zou zijn" - "standaard zou de sturing uit moeten
staan". "De airco in de slaapkamer verwarmt sowieso nooit." En: "ik heb een
standaard werkweek maar mijn vrouw en dochter niet" - dus geen rooster, maar
de aanwezigheidsdetectie.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import airco_sturing as a

NU = datetime(2026, 11, 20, 18, 0, tzinfo=timezone(timedelta(hours=1)))


def _bakje(kans, richting, genoeg=True):
    return {"probability_percent": kans, "richting": richting, "voldoende_data": genoeg}


# --- leren wanneer en waarop ---------------------------------------------


def test_de_aanzettemperatuur_uit_de_leercurve():
    bakjes = {
        "17.0": _bakje(90, "verwarmen"),
        "18.0": _bakje(60, "verwarmen"),
        "19.0": _bakje(20, "verwarmen"),       # minder kans dan niet
        "26.0": _bakje(80, "koelen"),          # andere richting
        "16.0": _bakje(100, "verwarmen", False),  # te weinig metingen
    }

    assert a.aanzettemperatuur(bakjes) == 18.0


def test_1_oktober_nog_nooit_verwarmen_gezien():
    """De werkelijke leercurve van 1 oktober: 19-24 graden, steeds 0%."""
    bakjes = {f"{t}.0": _bakje(0.0, None) for t in range(19, 25)}

    assert a.aanzettemperatuur(bakjes) is None


def test_de_gewenste_temperatuur_is_de_mediaan_van_jullie_keuzes():
    assert a.gewenste_temperatuur([20.0, 21.0, 21.0, 22.0, 21.5], 5) == 21.0
    assert a.gewenste_temperatuur([21.0, 21.0], 5) is None


# --- het besluit ------------------------------------------------------------


def _besluit(**anders):
    basis = dict(
        woonkamer_c=18.4, aanwezigheid="thuis", aanzet_c=19.0, doel_c=21.0,
        advies="airco", handmatig=False, airco_stand="off", door_ems_aan=False,
        setpunten_gezien=6, setpunten_nodig=5,
    )
    basis.update(anders)
    return a.besluit(**basis)


def test_koud_en_thuis_verwarmen_tot_de_gewenste_temperatuur():
    uit = _besluit()

    assert uit["actie"] == "verwarmen"
    assert uit["doel_c"] == 21.0
    assert "18.4" in uit["tekst"]


def test_nu_leert_hij_nog():
    uit = _besluit(aanzet_c=None)

    assert uit["actie"] == "niets"
    assert uit["tekst"].startswith("Leert nog")


def test_gewenste_temperatuur_nog_niet_geleerd():
    uit = _besluit(doel_c=None, setpunten_gezien=2)

    assert uit["actie"] == "niets"
    assert "2 van 5" in uit["redenen_tekst"]


@pytest.mark.parametrize("aanwezigheid", ["weg", "slaapt", "onbekend", None])
def test_niemand_thuis_dan_uit_als_het_ems_hem_aanzette(aanwezigheid):
    uit = _besluit(aanwezigheid=aanwezigheid, airco_stand="heat", door_ems_aan=True)

    assert uit["actie"] == "uit"


def test_niemand_thuis_maar_een_mens_zette_hem_aan_dan_niets():
    """Wat een mens aanzette, laat het EMS staan."""
    uit = _besluit(aanwezigheid="weg", airco_stand="heat", door_ems_aan=False)

    assert uit["actie"] == "niets"


def test_jullie_bedienen_hem_zelf_dan_niets():
    uit = _besluit(handmatig=True)

    assert uit["actie"] == "niets"
    assert "zelf" in uit["tekst"]


def test_gas_goedkoper_dan_niet_met_de_airco():
    assert _besluit(advies="cv")["actie"] == "niets"
    assert _besluit(advies="cv", airco_stand="heat", door_ems_aan=True)["actie"] == "uit"


def test_warm_genoeg_dan_niets():
    assert _besluit(woonkamer_c=19.5)["actie"] == "niets"


def test_verwarmt_al_dan_niets():
    assert _besluit(airco_stand="heat")["actie"] == "niets"


# --- de koppeling: knop, slaapkamer, jullie bediening ------------------------


def _coordinator(make_coordinator, hass, stand="off", doel=None):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["airco_climate_entity"] = "climate.woonkamer"
    c.config["slaapkamer_climate_entity"] = "climate.slaapkamer"
    hass.states.set("climate.woonkamer", stand, {"temperature": doel} if doel else {})
    c.living_room_current_temp_c = 18.4
    c.presence_state = "thuis"
    c.get_verwarmingsadvies = lambda: {"advies": "airco"}
    c.get_airco_kansen_per_bakje = lambda: {"bakjes": {"19.0": _bakje(80, "verwarmen")}}
    c.airco_setpunten = [21.0] * 5
    aanroepen = []

    async def dienst(domein, dienst, data, blocking=False):
        aanroepen.append((domein, dienst, data))

    hass.services.async_call = dienst
    taken = []
    hass.async_create_task = lambda coro: taken.append(coro)
    return c, aanroepen, taken


def test_standaard_staat_de_knop_uit_en_wordt_er_niets_uitgevoerd(make_coordinator, hass):
    c, aanroepen, taken = _coordinator(make_coordinator, hass)

    c._airco_ronde(NU)

    assert c.airco_automaat_aan is False
    assert c.last_airco_besluit["actie"] == "verwarmen"   # het besluit is er wel
    assert c.last_airco_besluit["toegepast"] is False
    assert "knop Airco automaat staat uit" in c.last_airco_besluit["status_tekst"]
    assert taken == []


@pytest.mark.asyncio
async def test_met_de_knop_aan_wordt_het_uitgevoerd(make_coordinator, hass):
    c, aanroepen, taken = _coordinator(make_coordinator, hass)
    c.airco_automaat_aan = True

    c._airco_ronde(NU)
    for taak in taken:
        await taak

    assert c.last_airco_besluit["toegepast"] is True
    assert aanroepen == [("climate", "set_temperature",
                          {"entity_id": "climate.woonkamer", "temperature": 21.0, "hvac_mode": "heat"})]
    assert c.airco_door_ems is True


def test_de_slaapkamer_wordt_nooit_aangeraakt(make_coordinator, hass):
    """Ook niet als hij per ongeluk als woonkamer-airco is ingesteld."""
    c, aanroepen, taken = _coordinator(make_coordinator, hass)
    c.config["airco_climate_entity"] = "climate.slaapkamer"
    c.airco_automaat_aan = True

    c._airco_ronde(NU)

    assert c.last_airco_besluit["actie"] == "niets"
    assert taken == []


def test_jullie_bediening_wordt_herkend_en_geleerd(make_coordinator, hass):
    c, aanroepen, taken = _coordinator(make_coordinator, hass)
    c.airco_setpunten = []
    c._airco_ronde(NU)                                 # eerste ronde: uit
    hass.states.set("climate.woonkamer", "heat", {"temperature": 21.5})

    c._airco_ronde(NU + timedelta(minutes=5))          # iemand zette hem aan

    assert c.airco_setpunten == [21.5]
    assert c.last_airco_besluit["actie"] == "niets"
    assert "zelf" in c.last_airco_besluit["tekst"]


def test_handmatig_geldt_tot_de_aanwezigheid_verandert(make_coordinator, hass):
    c, aanroepen, taken = _coordinator(make_coordinator, hass)
    c._airco_ronde(NU)
    hass.states.set("climate.woonkamer", "heat", {"temperature": 21.5})
    c._airco_ronde(NU + timedelta(minutes=5))
    assert c._airco_handmatig_bij == "thuis"

    c.presence_state = "weg"
    c._airco_ronde(NU + timedelta(hours=2))

    assert c._airco_handmatig_bij is None
