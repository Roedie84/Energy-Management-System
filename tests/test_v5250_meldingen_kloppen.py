"""v5.250.0 - twee meldingen die niet klopten (dagcontrole 20-11).

1. De planningssamenvatting zei 20-11 06:45 "De aansturing verkoopt op dit
   moment niet: de planning voorziet een tekort", terwijl het waardeplan
   19-11 18:00-19:30 verkocht en voor 20-11 tien verkoopkwartieren plant. De
   oude rem geldt niet meer sinds het waardeplan stuurt (v5.198.0).
2. 'Nieuw apparaat gevonden' meldde 19-11 16:01 drie instelknoppen
   'Beeldherkenning' van de camera's als "schakelaar of stekker".
"""
from custom_components.energy_management_system import ontdekking as O
from custom_components.energy_management_system.const import (
    PLAN_SHORTFALL_ALERT_MIN_QUARTERS,
)


def _met_waardeplan(make_coordinator, tegengehouden=None):
    c = make_coordinator({})
    c.last_plan_shortfall = {"kwartieren": PLAN_SHORTFALL_ALERT_MIN_QUARTERS + 10, "perioden": ["20:30-00:00"]}
    c.last_waardeplan = {"beschikbaar": True, "verkoop_tegengehouden": tegengehouden}
    c._waardeplan_rijen = [{"van": "18:00", "actie": "verkopen"}]
    return c


def test_waardeplan_stuurt_oude_rem_meldt_geen_blokkade(make_coordinator, hass):
    c = _met_waardeplan(make_coordinator)
    assert c.verkoop_geblokkeerd_door_tekort() is False
    assert c.verkoop_blokkade_reden() is None


def test_waardeplan_dat_echt_wordt_tegengehouden_meldt_het_wel(make_coordinator, hass):
    c = _met_waardeplan(make_coordinator, tegengehouden="onder de verkoopreserve")
    assert c.verkoop_geblokkeerd_door_tekort() is True
    reden = c.verkoop_blokkade_reden()
    assert "tegengehouden" in reden and "onder de verkoopreserve" in reden


def test_zonder_waardeplan_blijft_de_oude_rem(make_coordinator, hass):
    c = make_coordinator({})
    c.last_plan_shortfall = {"kwartieren": PLAN_SHORTFALL_ALERT_MIN_QUARTERS, "perioden": []}
    assert c.verkoop_geblokkeerd_door_tekort() is True
    assert "verkoopt op dit moment niet" in c.verkoop_blokkade_reden()


CAMERA = [
    {"entity_id": "switch.zolder_beeldherkenning", "platform": "eufy_lokaal", "apparaat": "Zolder"},
    {"entity_id": "switch.voortuin_deurbel_beeldherkenning", "platform": "eufy_lokaal", "apparaat": "Deurbel"},
    {"entity_id": "sensor.zolder_personen_vandaag", "platform": "eufy_lokaal", "apparaat": "Zolder"},
]


def test_instelknop_zonder_meting_is_geen_stekker():
    uit = O.beoordeel(CAMERA, {}, [])
    assert uit["bevindingen"] == []


def test_stekker_met_vermogensmeting_wordt_wel_gemeld():
    inv = CAMERA + [
        {"entity_id": "switch.stekker_schuur", "apparaat": "Stekker schuur"},
        {"entity_id": "sensor.stekker_schuur_vermogen", "device_class": "power", "apparaat": "Stekker schuur"},
    ]
    soorten = sorted((b["soort"], b["naam"]) for b in O.beoordeel(inv, {}, [])["bevindingen"])
    assert soorten == [("schakelaar of stekker", "Stekker schuur"), ("vermogensmeting", "Stekker schuur")]


def test_outlet_zonder_meting_telt_als_stekker():
    inv = [{"entity_id": "switch.wandcontact", "device_class": "outlet", "apparaat": "Wandcontact"}]
    [b] = O.beoordeel(inv, {}, [])["bevindingen"]
    assert b["soort"] == "schakelaar of stekker"


def test_meting_van_een_ander_apparaat_telt_niet():
    inv = [{"entity_id": "switch.zolder_beeldherkenning", "apparaat": "Zolder"},
           {"entity_id": "sensor.p1_vermogen", "device_class": "power", "apparaat": "P1 meter"}]
    assert O.beoordeel(inv, {}, ["sensor.p1_vermogen"])["bevindingen"] == []
