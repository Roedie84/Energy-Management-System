"""SAFE_SELL_SHADOW: wat zou de verkooptoets met de veilige zon doen? (v4.22)

Twee signalen wijzen dezelfde kant op, en dat is deze week niet eerder
gebeurd.

MEETSIGNAAL, over acht nabeschouwde dagen:

    expensive_quarter   17 kwartieren
                        mediaan afwijking  -0,408 kWh
                        totaal             4,91 kWh méér vasthouden

Het optimum wilde tijdens `expensive_quarter` structureel meer energie
behouden dan het EMS deed. Niet één dag, steeds dezelfde richting.

CODESIGNAAL, in `may_sell_now`:

    reserve = self._get_dynamic_discharge_reserve_kwh(now, blok_start)
    if reserve is None:
        nodig = self._estimate_consumption_kwh_for_period(now, blok_start)
        zon = self._estimate_pv_kwh_for_period(now, blok_start)   # geen band
        nodig = max(0.0, nodig - zon)

De reserve rekent met de VEILIGE positie in de Solcast-band (p10 + 0,29
x de breedte, geleerd over 31 dagen). Dit terugvalpad rekent met de
VERWACHTING. Bij een bandbreedte van 59% ligt dat 30 tot 40% hoger.

Dat terugvalpad geldt precies wanneer er geen goedkoop blok in zicht is
- dus 's avonds en 's nachts, wanneer verkopen aan de orde is en de
nacht nog moet worden gehaald. Hetzelfde beslispad rekent daar dus
voorzichtig voor de reserve en optimistisch voor de verkoop.

WAT HIER NIET STAAT

Dat `expensive_quarter` te veel verkoopt. Dat is niet bewezen. Wat
bewezen is: de afwijking is negatief, relatief groot, en er bestaat een
codepad dat optimistischer rekent dan de rest van de
onzekerheidsarchitectuur.

Deze meting stuurt niets. Ze legt per verkoopmoment vast wat er zou zijn
besloten met de veilige zon, zodat over enkele weken te zien is of de
twee signalen bij elkaar blijven.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 18, 19, 45, tzinfo=timezone.utc)


def _situatie(c, verwacht=3.0, veilig=1.8, reserve=None):
    c._estimate_consumption_kwh_for_period = lambda a, b: 2.4
    c._estimate_pv_kwh_for_period = (
        lambda a, b, veilig=False: (veilig and veilig_kwh) or verwacht
    )
    veilig_kwh = veilig

    def zon(a, b, veilig_=False, **kw):
        return veilig if kw.get("veilig") or veilig_ else verwacht

    c._estimate_pv_kwh_for_period = zon
    c._get_dynamic_discharge_reserve_kwh = lambda *a, **kw: reserve
    c.last_available_kwh = 2.0
    c.bruikbare_capaciteit_kwh = lambda: 8.64


def test_de_schaduw_legt_beide_schattingen_vast(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c, verwacht=3.0, veilig=1.8)
    c.safe_sell_shadow = []

    c.noteer_safe_sell_shadow(NU, verkocht_kwh=0.4, nodig_verwacht=0.0, nodig_veilig=0.6)

    s = c.safe_sell_shadow[-1]
    assert s["nodig_verwacht_kwh"] == 0.0
    assert s["nodig_veilig_kwh"] == 0.6
    assert s["verkocht_kwh"] == 0.4


def test_de_schaduw_zegt_wat_er_anders_zou_zijn_gegaan(make_coordinator, hass):
    """Met de veilige zon was er 0,6 kWh nodig en lag er 2,0 beschikbaar,
    dus mocht er 1,4 verkocht worden. Er is 1,8 verkocht - 0,4 te veel."""
    c = make_coordinator({})
    _situatie(c)
    c.safe_sell_shadow = []

    c.noteer_safe_sell_shadow(NU, verkocht_kwh=1.8, nodig_verwacht=0.0, nodig_veilig=0.6)

    s = c.safe_sell_shadow[-1]
    assert s["uitkomst"] == "minder verkoop"
    assert s["verschil_kwh"] == pytest.approx(0.4, abs=0.01)


def test_zelfde_beslissing_als_de_band_niets_verandert(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c)
    c.safe_sell_shadow = []

    c.noteer_safe_sell_shadow(NU, verkocht_kwh=0.4, nodig_verwacht=0.5, nodig_veilig=0.5)

    assert c.safe_sell_shadow[-1]["uitkomst"] == "zelfde beslissing"


def test_geen_verkoop_als_de_veilige_behoefte_alles_opeist(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c)
    c.safe_sell_shadow = []

    c.noteer_safe_sell_shadow(NU, verkocht_kwh=0.4, nodig_verwacht=0.0, nodig_veilig=2.5)

    assert c.safe_sell_shadow[-1]["uitkomst"] == "geen verkoop"


def test_het_overzicht_telt_de_uitkomsten(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c)
    c.safe_sell_shadow = []
    for nodig_veilig, verkocht in ((0.6, 1.8), (0.5, 0.4), (2.5, 0.4)):
        c.noteer_safe_sell_shadow(
            NU, verkocht_kwh=verkocht, nodig_verwacht=0.5 if nodig_veilig == 0.5 else 0.0,
            nodig_veilig=nodig_veilig,
        )

    o = c.get_safe_sell_shadow_overzicht()

    assert o["momenten"] == 3
    assert o["minder_verkoop"] == 1
    assert o["geen_verkoop"] == 1
    assert o["zelfde_beslissing"] == 1
    assert "stuurt niets" in o["toelichting"]


def test_zonder_momenten_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    c.safe_sell_shadow = []

    o = c.get_safe_sell_shadow_overzicht()

    assert o["momenten"] == 0
    assert "nog geen" in o["oordeel"].lower()


def test_de_geschiedenis_blijft_begrensd(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        SAFE_SELL_SHADOW_LENGTE,
    )

    c = make_coordinator({})
    _situatie(c)
    c.safe_sell_shadow = []
    for n in range(SAFE_SELL_SHADOW_LENGTE + 10):
        c.noteer_safe_sell_shadow(
            NU + timedelta(minutes=15 * n), verkocht_kwh=0.4,
            nodig_verwacht=0.0, nodig_veilig=0.6,
        )

    assert len(c.safe_sell_shadow) == SAFE_SELL_SHADOW_LENGTE


# --- v4.23: de nacht erna erbij --------------------------------------
#
# De schaduw zegt hoeveel er zou VERANDEREN, niet of het BETER zou zijn.
# De veilige positie van 0,29 is geijkt als de waarde die in 20% van de
# dagen werd gehaald - bewust pessimistisch. In de verkooptoets zal die
# dus vrijwel altijd "minder verkoop" zeggen, en dat is dan een
# eigenschap van de ijking en geen bevinding.
#
# Om te weten of minder verkopen beter was, moet je weten of de nacht
# erna krap liep. Dat staat al in de dagrecords sinds v4.7:
#
#     09-10   ochtendstand 18 %   netimport 's nachts 0,01 kWh
#     09-11   ochtendstand 37 %   netimport 's nachts 0,11 kWh
#     09-12   ochtendstand 10 %   netimport 's nachts 1,05 kWh
#
# Dat is de derde meting die de lus sluit: ging de nacht slecht op de
# avonden waar de schaduw "minder verkoop" zei? Zo niet, dan was
# verkopen goed en zou de veilige positie geld hebben gekost - precies
# wat doorloop 5 voor de reserve als geheel aantoonde.


def _met_nacht(c, datum, ochtendstand, netimport):
    c.reserve_daily_records = (c.reserve_daily_records or []) + [
        {
            "date": datum,
            "laagste_soc_ochtend": ochtendstand,
            "netimport_nacht_kwh": netimport,
        }
    ]


def test_de_nacht_erna_wordt_erbij_geschreven(make_coordinator, hass):
    """De schaduw van 18 september kijkt naar het dagrecord van 19
    september - de nacht die erop volgde."""
    c = make_coordinator({})
    _situatie(c)
    c.safe_sell_shadow = []
    c.reserve_daily_records = []
    c.noteer_safe_sell_shadow(NU, verkocht_kwh=1.8, nodig_verwacht=0.0, nodig_veilig=0.6)
    _met_nacht(c, "2026-09-19", ochtendstand=11.0, netimport=0.9)

    o = c.get_safe_sell_shadow_overzicht()

    assert o["laatste"]["nacht_erna"]["laagste_soc_ochtend"] == 11.0
    assert o["laatste"]["nacht_erna"]["krap"] is True


def test_een_ruime_nacht_is_niet_krap(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c)
    c.safe_sell_shadow = []
    c.reserve_daily_records = []
    c.noteer_safe_sell_shadow(NU, verkocht_kwh=1.8, nodig_verwacht=0.0, nodig_veilig=0.6)
    _met_nacht(c, "2026-09-19", ochtendstand=37.0, netimport=0.11)

    o = c.get_safe_sell_shadow_overzicht()

    assert o["laatste"]["nacht_erna"]["krap"] is False


def test_het_oordeel_scheidt_verandering_van_verbetering(make_coordinator, hass):
    """Niet "acht keer minder verkoop" maar "acht keer minder verkoop,
    waarvan twee nachten krap". Dat is het verschil tussen een
    verandering en een verbetering."""
    c = make_coordinator({})
    _situatie(c)
    c.safe_sell_shadow = []
    c.reserve_daily_records = []
    for n, (stand, netimport) in enumerate(
        ((37.0, 0.1), (11.0, 0.9), (30.0, 0.0), (9.0, 1.2))
    ):
        moment = NU + timedelta(days=n)
        c.noteer_safe_sell_shadow(
            moment, verkocht_kwh=1.8, nodig_verwacht=0.0, nodig_veilig=0.6
        )
        _met_nacht(c, (moment + timedelta(days=1)).date().isoformat(), stand, netimport)

    o = c.get_safe_sell_shadow_overzicht()

    assert o["minder_verkoop"] == 4
    assert o["daarvan_krappe_nacht"] == 2
    assert "krap" in o["oordeel"]
    uitleg = o["toelichting"].lower()
    assert "veranderen" in uitleg and "beter" in uitleg


def test_zonder_dagrecord_blijft_de_nacht_onbekend(make_coordinator, hass):
    """De nacht erna komt pas bij de dagwissel; tot dan is hij leeg en
    dat mag geen conclusie worden."""
    c = make_coordinator({})
    _situatie(c)
    c.safe_sell_shadow = []
    c.reserve_daily_records = []
    c.noteer_safe_sell_shadow(NU, verkocht_kwh=1.8, nodig_verwacht=0.0, nodig_veilig=0.6)

    o = c.get_safe_sell_shadow_overzicht()

    assert o["laatste"]["nacht_erna"] is None
    assert o["daarvan_krappe_nacht"] == 0
    assert o["nacht_nog_onbekend"] == 1
