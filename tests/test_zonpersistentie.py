"""Komt er gedurende de dag informatie bij? (v5.1)

FORECAST RESOLUTION ANALYSIS, maar niet zoals oorspronkelijk gevraagd.

De opzet was: vergelijk de p10/p90-band op 08:00, 11:00, 14:00 en 17:00.
Twee problemen. Die band wordt ALTIJD smaller, grotendeels omdat de
resterende dag korter wordt - om 17:00 dekt de voorspelling twee uur in
plaats van veertien. Dat is geen informatie, dat is de dag die opraakt.
En `_pv_band_kw_per_start` wordt niet bewaard; er is één
voorspellingsmomentopname per dag, om 08:00. De bandversie is dus niet
terug te toetsen EN meet het verkeerde.

De onderliggende vraag is wel te meten, zonder Solcast: voorspelt de
ochtend de rest van de dag? Zo niet, dan weet je om 11:00 niets extra
over de middag en heeft uitstel geen waarde, wat de band ook doet.

Gemeten over acht dagen september:

    dag           ochtend/mediaan   rest/mediaan
    09-09                0,89           1,27
    09-10                1,27           1,62
    09-11                0,98           0,59
    09-12                0,84           0,90
    09-13                0,27           0,56
    09-14                1,33           1,07
    09-15                1,27           1,56
    09-16                1,02           0,92

    correlatie r = +0,69   (n = 8)

Er komt dus informatie bij: een ochtend op 27% wordt gevolgd door een
rest op 56%. Maar twee van de acht dagen gaan de verkeerde kant op, en
bij n=8 is r=0,69 een aanwijzing en geen bewijs.

Deze meting stuurt niets. Ze telt de dagen op en zegt hoeveel er nodig
zijn voordat er een richting uit te lezen is.
"""
import pytest


def _dag(c, datum, per_deel):
    """per_deel: (ochtend, middag1, middag2, avond) in kWh."""
    regels = []
    grenzen = ((0, 11), (11, 14), (14, 17), (17, 24))
    for kwh, (van, tot) in zip(per_deel, grenzen):
        kwartieren = (tot - van) * 4
        per_kwartier = kwh / kwartieren * 4000
        for n in range(kwartieren):
            uur = van + n // 4
            regels.append(
                {"tijd": f"{uur:02d}:{(n % 4) * 15:02d}", "pv_w": per_kwartier}
            )
    c.dagverloop = dict(c.dagverloop or {})
    c.dagverloop[datum] = regels


def test_de_dagdelen_worden_geteld(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}
    _dag(c, "2026-09-16", (2.0, 4.0, 3.0, 1.0))

    uit = c.get_zonpersistentie()

    assert uit["dagen"] == 1
    assert uit["mediane_vorm_kwh"]["ochtend"] == pytest.approx(2.0, abs=0.05)
    assert uit["mediane_vorm_kwh"]["middag1"] == pytest.approx(4.0, abs=0.05)


def test_een_slechte_ochtend_met_een_slechte_middag_geeft_samenhang(make_coordinator, hass):
    """Het gemeten patroon: hoge ochtend, hoge rest; lage ochtend, lage
    rest. Dat is de informatie die om 11:00 beschikbaar komt."""
    from custom_components.energy_management_system.const import (
        ZONPERSISTENTIE_MIN_DAGEN,
    )

    c = make_coordinator({})
    c.dagverloop = {}
    for n, factor in enumerate((0.3, 0.6, 0.9, 1.0, 1.1, 1.4, 1.6, 0.5, 0.8, 1.2)):
        _dag(c, f"2026-09-{n + 1:02d}",
             (2.0 * factor, 4.0 * factor, 3.0 * factor, 1.0 * factor))

    uit = c.get_zonpersistentie()

    assert uit["dagen"] == 10
    assert uit["correlatie"] > 0.9
    assert ZONPERSISTENTIE_MIN_DAGEN >= 20


def test_zonder_samenhang_komt_er_geen_informatie_bij(make_coordinator, hass):
    """Als de ochtend niets zegt over de middag, is uitstel waardeloos -
    hoe smal de band ook wordt."""
    c = make_coordinator({})
    c.dagverloop = {}
    # ochtend en rest bewegen tegengesteld
    for n, (o, r) in enumerate(
        ((0.4, 1.6), (1.6, 0.4), (0.5, 1.5), (1.5, 0.5), (0.6, 1.4),
         (1.4, 0.6), (0.7, 1.3), (1.3, 0.7), (0.8, 1.2), (1.2, 0.8))
    ):
        _dag(c, f"2026-09-{n + 1:02d}", (2.0 * o, 4.0 * r, 3.0 * r, 1.0 * r))

    uit = c.get_zonpersistentie()

    assert uit["correlatie"] < -0.5
    assert "geen" in uit["oordeel"].lower() or "tegengesteld" in uit["oordeel"].lower()


def test_te_weinig_dagen_geeft_geen_richting(make_coordinator, hass):
    """Bij acht dagen was r=0,69 een aanwijzing, geen bewijs. De meting
    hoort dat zelf te zeggen."""
    c = make_coordinator({})
    c.dagverloop = {}
    for n in range(8):
        _dag(c, f"2026-09-{n + 1:02d}", (2.0, 4.0, 3.0, 1.0))

    uit = c.get_zonpersistentie()

    assert uit["betrouwbaar"] is False
    assert "minstens" in uit["oordeel"].lower()


def test_de_dagen_die_de_verkeerde_kant_op_gaan_worden_geteld(make_coordinator, hass):
    """Twee van de acht septemberdagen misleidden. Dat getal hoort erbij,
    want juist daar zou een uitstelregel het verkeerde besluit
    versterken."""
    c = make_coordinator({})
    c.dagverloop = {}
    for n, (o, r) in enumerate(
        ((1.3, 1.3), (1.2, 1.2), (0.7, 0.7), (0.8, 0.8),
         (0.9, 1.4), (1.4, 0.9), (1.1, 1.1), (0.6, 0.6))
    ):
        _dag(c, f"2026-09-{n + 1:02d}", (2.0 * o, 4.0 * r, 3.0 * r, 1.0 * r))

    uit = c.get_zonpersistentie()

    assert uit["dagen_tegengesteld"] == 2


def test_zonder_dagen_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}

    uit = c.get_zonpersistentie()

    assert uit["dagen"] == 0
    assert uit["correlatie"] is None


def test_de_toelichting_noemt_waarom_het_niet_de_band_meet(make_coordinator, hass):
    """Anders vraagt iemand over een maand opnieuw om de p10/p90 per
    moment - en die meet vooral dat de dag korter wordt."""
    c = make_coordinator({})
    c.dagverloop = {}
    _dag(c, "2026-09-16", (2.0, 4.0, 3.0, 1.0))

    uitleg = c.get_zonpersistentie()["toelichting"].lower()

    assert "band" in uitleg
    assert "korter" in uitleg or "opraakt" in uitleg
