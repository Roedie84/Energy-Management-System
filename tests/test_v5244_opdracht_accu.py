"""v5.244.0 - deed de accu zelf wat het EMS opdroeg? (alleen meten)

Stap a van "Zendure lokaal aansturen" (Ruud 19-11): een opgedragen handmatig
vermogen vergeleken met de eigen lezing van de accu.
"""
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import opdracht_accu as O
from custom_components.energy_management_system.const import (
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
    OPDRACHT_BEVESTIGING_SECONDEN,
    OPTION_MANUAL,
)

NU = datetime(2026, 11, 19, 12, 0)
T0 = 1000.0
T_LATER = T0 + OPDRACHT_BEVESTIGING_SECONDEN + 10


def test_beoordeel_binnen_de_marge():
    assert O.beoordeel(-2400, -2310, 2.0) == "gevolgd"          # 15 % van 2400 = 360 W
    assert O.beoordeel(1200, 1050, 2.0) == "gevolgd"            # 150 W of 15 %
    assert O.beoordeel(1200, 0, 2.0) == "niet_gevolgd"
    assert O.beoordeel(-2400, 800, 2.0) == "niet_gevolgd"       # verkeerde kant op


def test_volle_of_lege_accu_is_geen_afwijking():
    assert O.beoordeel(-2400, 0, 2.0, soc=100, ondergrens=10, bovengrens=100) == "kan_niet"
    assert O.beoordeel(2000, 0, 2.0, soc=10, ondergrens=10, bovengrens=100) == "kan_niet"
    # halfvol en toch niets doen is wel een afwijking
    assert O.beoordeel(-2400, 0, 2.0, soc=50, ondergrens=10, bovengrens=100) == "niet_gevolgd"


def test_zonder_verse_lezing_geen_oordeel():
    assert O.beoordeel(-2400, None, 2.0) == "onbekend"
    assert O.beoordeel(-2400, -2400, None) == "onbekend"
    assert O.beoordeel(-2400, -2400, O.MAX_LEEFTIJD_S + 1) == "onbekend"
    assert O.beoordeel(20, 0, 2.0) == "onbekend"                 # te klein om te beoordelen
    assert O.beoordeel("x", 0, 2.0) == "onbekend"


def test_tellen_per_dag_en_afwijkingen():
    t = O.leeg()
    for i in range(3):
        O.noteer(t, "gevolgd", dag="2026-11-19", moment=f"m{i}")
    O.noteer(t, "niet_gevolgd", dag="2026-11-19", moment="m3", verwacht_w=-2400, gemeten_w=12.4, soc=50)
    O.noteer(t, "kan_niet", dag="2026-11-20", moment="m4")
    O.noteer(t, "iets anders", dag="2026-11-20", moment="m5")
    o = O.overzicht(t)
    assert o["gevolgd"] == 3 and o["niet_gevolgd"] == 1 and o["kan_niet"] == 1 and o["beoordeeld"] == 4
    assert o["aandeel_gevolgd_procent"] == 75.0
    assert o["per_dag"]["2026-11-19"] == {"gevolgd": 3, "niet_gevolgd": 1}
    assert o["laatste_afwijkingen"] == [{"moment": "m3", "verwacht_w": -2400, "gemeten_w": 12, "soc": 50}]
    assert O.overzicht(None)["aandeel_gevolgd_procent"] is None


def test_bewaart_hooguit_dertig_dagen_en_tien_afwijkingen():
    t = O.leeg()
    for d in range(40):
        O.noteer(t, "niet_gevolgd", dag=(datetime(2026, 1, 1) + timedelta(days=d)).date().isoformat(),
                 moment=str(d), verwacht_w=1000, gemeten_w=0)
    assert len(t["dagen"]) == O.DAGEN and len(t["afwijkingen"]) == O.LAATSTE_AFWIJKINGEN
    assert t["totaal"]["niet_gevolgd"] == 40


def _coordinator(make_coordinator, hass, gemeten_w, modus=OPTION_MANUAL, leeftijd=1.0):
    c = make_coordinator({CONF_OPERATION_SELECT: "select.modus", CONF_MANUAL_POWER_NUMBER: "number.vermogen"})
    hass.states.set("select.modus", modus)
    hass.states.set("number.vermogen", "-2400")
    c._dispatch_notification = lambda **kw: None
    c.last_soc_percent = 50.0
    c.zendure_lokaal = SimpleNamespace(
        tellingen={},
        laatste={"apparaat": {"outputHomePower": max(0.0, gemeten_w), "gridInputPower": max(0.0, -gemeten_w)}},
        laatste_t=time.monotonic() - leeftijd,
    )
    return c


def test_gevolgde_opdracht_wordt_geteld(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, -2350.0)
    c._noteer_opdracht("number.vermogen", -2400.0, "handmatig vermogen", nu_seconden=T0)
    c.controleer_opdrachten(NU, nu_seconden=T_LATER)
    accu = c.get_opdrachtcontrole()["accu_zelf"]
    assert accu["gevolgd"] == 1 and accu["niet_gevolgd"] == 0
    # de bestaande controle op de entiteit loopt gewoon door
    assert c.opdracht_bevestigingen["gelukt"] == 1


def test_entiteit_goed_maar_accu_doet_niets(make_coordinator, hass):
    """Waar het om gaat: de integratie toont de waarde, de accu staat stil."""
    c = _coordinator(make_coordinator, hass, 0.0)
    c._noteer_opdracht("number.vermogen", -2400.0, "handmatig vermogen", nu_seconden=T0)
    c.controleer_opdrachten(NU, nu_seconden=T_LATER)
    accu = c.get_opdrachtcontrole()["accu_zelf"]
    assert c.opdracht_bevestigingen["gelukt"] == 1
    assert accu["niet_gevolgd"] == 1 and accu["laatste_afwijkingen"][0]["verwacht_w"] == -2400


def test_niet_meer_handmatig_telt_niet(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, 0.0, modus="smart")
    c._noteer_opdracht("number.vermogen", -2400.0, "handmatig vermogen", nu_seconden=T0)
    c.controleer_opdrachten(NU, nu_seconden=T_LATER)
    assert c.get_opdrachtcontrole()["accu_zelf"]["beoordeeld"] == 0


def test_oude_lezing_en_zonder_meelezer(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, 0.0, leeftijd=120.0)
    c._noteer_opdracht("number.vermogen", -2400.0, "handmatig vermogen", nu_seconden=T0)
    c.controleer_opdrachten(NU, nu_seconden=T_LATER)
    assert c.get_opdrachtcontrole()["accu_zelf"]["onbekend"] == 1
    c.zendure_lokaal = None
    c._noteer_opdracht("number.vermogen", -2400.0, "handmatig vermogen", nu_seconden=T0)
    c.controleer_opdrachten(NU, nu_seconden=T_LATER)          # mag niets breken
    assert c.get_opdrachtcontrole()["accu_zelf"]["beoordeeld"] == 0


def test_een_modusopdracht_wordt_niet_tegen_het_vermogen_gelegd(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, 0.0)
    c._noteer_opdracht("select.modus", OPTION_MANUAL, "modus", nu_seconden=T0)
    c.controleer_opdrachten(NU, nu_seconden=T_LATER)
    assert sum(c.get_opdrachtcontrole()["accu_zelf"][u] for u in O.UITKOMSTEN) == 0


def test_de_module_schrijft_niet_naar_de_accu():
    bron = (Path(pkg.__file__).parent / "opdracht_accu.py").read_text(encoding="utf-8")
    for verboden in (".post(", ".put(", "properties/write", "async_call", "hass."):
        assert verboden not in bron, verboden
