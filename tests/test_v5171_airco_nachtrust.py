"""v5.171.0 (L-EMS-057) - het airco-besluit verwarmt 's nachts niet meer.

31-10 t/m 02-11 (n=3 nachten): met iemand 'thuis' en onder de 19 °C werd het
gewone besluit om 23:25 en 01:08 'verwarmen'. Tussen de vaste uit (22:00) en
het ochtendvenster (04:00) nu 'niets'; handmatig gaat voor, ochtend en dag
blijven zoals ze waren.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import airco_ritme
from custom_components.energy_management_system import airco_sturing as a

TZ = timezone(timedelta(hours=1))


def _besluit(**anders):
    basis = dict(
        woonkamer_c=18.4, aanwezigheid="thuis", aanzet_c=19.0, doel_c=21.0,
        advies="airco", handmatig=False, airco_stand="off", door_ems_aan=False,
        setpunten_gezien=6, setpunten_nodig=5,
    )
    basis.update(anders)
    return a.besluit(**basis)


@pytest.mark.parametrize(
    "uur,minuut,verwacht",
    [(22, 0, True), (23, 25, True), (0, 0, True), (1, 8, True), (3, 59, True),
     (4, 0, False), (12, 0, False), (21, 59, False)],
)
def test_nachtrust_van_22_tot_04(uur, minuut, verwacht):
    assert a.in_nachtrust(uur * 60 + minuut, 22 * 60) is verwacht


def test_zonder_uittijd_geen_nachtrust():
    assert a.in_nachtrust(23 * 60, None) is False


def test_uittijd_na_middernacht():
    assert a.in_nachtrust(1 * 60, 0 * 60 + 30) is True
    assert a.in_nachtrust(0, 30) is False


def test_het_ochtendvenster_is_dezelfde_grens():
    assert a.NACHTRUST_TOT_MIN == airco_ritme.OCHTEND_VAN


def test_nachtrust_geen_verwarmen():
    uit = _besluit(nachtrust=True)
    assert uit["actie"] == "niets"
    assert "Nachtrust" in uit["tekst"]


def test_nachtrust_ook_geen_vooruit_verwarmen():
    uit = _besluit(woonkamer_c=19.5, vooruit={"verwacht_c": 18.5}, nachtrust=True)
    assert uit["actie"] == "niets"


def test_handmatig_gaat_voor():
    uit = _besluit(handmatig=True, nachtrust=True)
    assert uit["actie"] == "niets"
    assert "zelf" in uit["tekst"]


def test_overdag_ongewijzigd():
    assert _besluit()["actie"] == "verwarmen"


def _coordinator(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["airco_climate_entity"] = "climate.woonkamer"
    c.config["slaapkamer_climate_entity"] = "climate.slaapkamer"
    hass.states.set("climate.woonkamer", "off", {})
    c.living_room_current_temp_c = 18.4
    c.presence_state = "thuis"
    c.get_verwarmingsadvies = lambda: {"advies": "airco"}
    c.get_airco_kansen_per_bakje = lambda: {
        "bakjes": {"19.0": {"probability_percent": 80, "richting": "verwarmen", "voldoende_data": True}}
    }
    c.airco_setpunten = [21.0] * 5
    hass.async_create_task = lambda coro: coro.close()
    return c


def test_coordinator_om_23_25_niets(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c._airco_ronde(datetime(2026, 11, 2, 23, 25, tzinfo=TZ))
    assert c.last_airco_besluit["actie"] != "verwarmen"
    assert "nachtrust" in c.last_airco_besluit["redenen_tekst"]


def test_coordinator_om_18_00_verwarmen(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c._airco_ronde(datetime(2026, 11, 2, 18, 0, tzinfo=TZ))
    assert c.last_airco_besluit["actie"] == "verwarmen"
