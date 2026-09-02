"""Een kookpiek is geen tekortdag (v3.99.0).

Uit het eigen logboek in de export van 2 september:

    18:56  WARNING  Unexpected grid import detected (2064W) during a
                    supposedly self-sufficient period
                    (expensive_quarter_soc_protected) - the reserve
                    estimate for today may have been too optimistic.

Om 18:56 trekt de keuken 2064 W. De accu levert hooguit 1600 W. Het
verschil komt van het net - dat kan niet anders, hoeveel energie er ook
in de accu zit. Dat is een VERMOGENSgrens, geen ENERGIEtekort.

En toch telt het als tekortdag. De regel was: netimport boven 100 W in
een zelfvoorzienende periode, klaar. Vijf van de zeven dagen stonden zo
op "tekort", en die vijf tellen samen voor 25 procentpunt extra marge op
de reserve. De reserve wordt dus opgehoogd om een probleem dat hij niet
kan oplossen: een grotere reserve maakt de accu niet sterker.

Een tekort is pas een tekort als de accu MINDER levert dan hij kan en er
toch import is. Levert hij op zijn grens, dan is de import verklaard.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 9, 1, 18, 56, tzinfo=timezone.utc)


def _opzet(c, hass, net_w, accu_w, ontlaadgrens_w=1600):
    hass.states.set("sensor.net", str(net_w))
    hass.states.set("sensor.accu", str(accu_w))
    c.config = dict(c.config or {})
    c.config["consumption_power_sensor_entity"] = "sensor.net"
    c.config["battery_power_sensor_entity"] = "sensor.accu"
    c.config["manual_discharge_power"] = ontlaadgrens_w
    c._shortfall_detected_today = False
    c._shortfall_check_date = NU.date()


def _toets(c):
    c._update_shortfall_detection(NU, "expensive_quarter_soc_protected", 2.0, 1.0)
    return c._shortfall_detected_today


def test_import_boven_de_ontlaadgrens_is_geen_tekort(make_coordinator, hass):
    """Het geval van 18:56: keuken 2064 W, accu op 1600 W, rest van het net."""
    c = make_coordinator({})
    _opzet(c, hass, net_w=464, accu_w=1600)

    assert _toets(c) is False


def test_import_terwijl_de_accu_niets_levert_is_wel_een_tekort(
    make_coordinator, hass
):
    """De accu had kunnen leveren en deed het niet: dat is het geval

    waar de reserve iets aan kan doen.
    """
    c = make_coordinator({})
    _opzet(c, hass, net_w=464, accu_w=0)

    assert _toets(c) is True


def test_import_met_de_accu_halverwege_is_ook_een_tekort(
    make_coordinator, hass
):
    """Ruimte over op de accu en toch import: onverklaard."""
    c = make_coordinator({})
    _opzet(c, hass, net_w=300, accu_w=800)

    assert _toets(c) is True


def test_een_kleine_marge_op_de_grens_telt_als_op_de_grens(
    make_coordinator, hass
):
    """1550 W bij een grens van 1600 is de grens - regelfouten van

    tientallen watt zijn normaal.
    """
    c = make_coordinator({})
    _opzet(c, hass, net_w=500, accu_w=1550)

    assert _toets(c) is False


def test_de_soort_wordt_vastgelegd(make_coordinator, hass):
    """Anders is achteraf niet te zien wat voor dag het was, en dat is

    precies wat er vijf van de zeven dagen mis was.
    """
    c = make_coordinator({})
    _opzet(c, hass, net_w=464, accu_w=1600)

    _toets(c)

    assert c._vermogensgrens_gezien_today is True


# --- de grens hangt van de stand af ------------------------------------
#
# Gemeld: "in de smart modus mag de accu 2000W leveren, in de manual max
# 1600 W leveren." Dus wat als "op de grens" telt, verschilt per stand.


def _toets_slim(c):
    c._update_shortfall_detection(NU, "smart_discharging", 2.0, 1.0)
    return c._shortfall_detected_today


def test_in_de_slimme_stand_ligt_de_grens_op_2000(make_coordinator, hass):
    """Accu op 1950 W, 114 W van het net: dat is de grens."""
    c = make_coordinator({})
    _opzet(c, hass, net_w=114, accu_w=1950)

    assert _toets_slim(c) is False


def test_in_de_slimme_stand_is_1600_nog_geen_grens(make_coordinator, hass):
    """Dezelfde 1600 W die in de handmatige stand de grens is, laat in de

    slimme stand nog 400 W ruimte. Import is dan onverklaard.
    """
    c = make_coordinator({})
    _opzet(c, hass, net_w=464, accu_w=1600)

    assert _toets_slim(c) is True


def test_in_de_handmatige_stand_blijft_1600_de_grens(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c, hass, net_w=464, accu_w=1600)

    assert _toets(c) is False


def test_het_hoogste_ontlaadvermogen_per_stand_wordt_vastgelegd(
    make_coordinator, hass
):
    """Gevraagd: "Als het goed is kun je dit ook in de data zien." Dat

    kon niet: de export is een momentopname. Nu staat het per dag in
    het dagrecord, per stand.
    """
    c = make_coordinator({})
    _opzet(c, hass, net_w=0, accu_w=1580)
    _toets(c)
    _opzet(c, hass, net_w=0, accu_w=1940)
    _toets_slim(c)

    assert c._max_ontlaad_w_vandaag == {"handmatig": 1580.0, "slim": 1940.0}
