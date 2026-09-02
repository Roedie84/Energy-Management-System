"""De vaatwasser blaast de reserve op tot boven de accu (v3.99.2).

Gemeld om 13:36: "Den accu haalt de nacht neet. D'r is 5.27 kWh
beschikbaor, terwiel er 9.74 kWh neudeg is om tot 't goedkope blok te
overbruggen. Er wödt zo neudeg bi-j-elaojen." Met de opmerking:
"Waarschijnlijk komt dit omdat de vaatwasser aan staat."

Dat klopt. Uit de export van 13:37:

    huisverbruik nu               2414 W       (vaatwasser, bevestigd)
    geleerd profiel uur 13         559 W
    verhouding                    4,3x         begrensd op 5
    diepste tekort                10,39 kWh
    reserve na 61,6% marge        16,80 kWh    accu: 8,64 kWh
    volgende goedkope blok        morgen 12:15, 23 uur verderop

De correctieverhouding vervaagt over vier uur, maar de eerste uren
tellen bijna vol mee - en 4,3 keer het middagverbruik is meer dan de
zon van een bewolkte middag dekt. Zo wordt een afwas van een uur een
tekort van tien kilowattuur.

v0.63.78 had dit al gezien en de vaatwasser uit het "direct
vertrouwen"-pad gehaald. Maar de mediaan van vier metingen vangt een
verwarmingsfase van twintig minuten net zo goed, en dan is de uitkomst
hetzelfde.

Een bevestigd kortlopend apparaat is geen verandering in het
verbruiksniveau van het huis. Het is een cyclus met een bekende
energie, en die hoort er EEN keer bij - niet als vermenigvuldiger over
vier uur.

En een reserve van 16,8 kWh in een accu van 8,64 is geen reserve. Dan
kan de accu de periode per definitie niet overbruggen, en dat is een
andere boodschap dan "haalt de nacht niet, er wordt bijgeladen".
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 2, 13, 37, tzinfo=timezone.utc)


def _verbruik(c, live_kw, profiel_kw=0.559):
    c._recent_consumption_readings_kw = [live_kw] * 4
    c.hourly_consumption_profile = {NU.hour: [profiel_kw] * 7}


def test_een_bevestigde_vaatwasser_schaalt_het_profiel_niet(
    make_coordinator, hass
):
    """Het geval van 13:37."""
    c = make_coordinator({})
    _verbruik(c, live_kw=2.414)
    c.last_heavy_load_source = "vaatwasser"

    assert c._get_smoothed_consumption_correction_ratio(NU.hour) == 1.0


def test_een_onbekende_verhoging_schaalt_nog_wel(make_coordinator, hass):
    """Zonder bevestigd apparaat weet de code niet hoe lang het duurt,

    en dan is de vervagende verhouding het beste dat er is.
    """
    c = make_coordinator({})
    _verbruik(c, live_kw=2.414)
    c.last_heavy_load_source = None

    assert c._get_smoothed_consumption_correction_ratio(NU.hour) > 1.0


def test_de_airco_schaalt_nog_wel(make_coordinator, hass):
    """Koelen duurt uren; daar is de verhouding juist voor bedoeld."""
    c = make_coordinator({})
    _verbruik(c, live_kw=1.2)
    c.last_heavy_load_source = "airco"

    assert c._get_smoothed_consumption_correction_ratio(NU.hour) > 1.0


def test_de_reserve_gaat_niet_boven_de_accu(make_coordinator, hass):
    """16,8 kWh in een accu van 8,64 is geen reserve."""
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 10.394

    reserve = c._get_dynamic_discharge_reserve_kwh(NU, NU + timedelta(hours=23))

    assert reserve <= 8.64
    assert c.last_reserve_margin_breakdown["boven_capaciteit"] is True
    # Het ongekapte getal blijft zichtbaar: dat is wat de export toonde.
    assert c.last_reserve_margin_breakdown["ongekapt_kwh"] > 8.64


def test_een_gewone_reserve_wordt_niet_geraakt(make_coordinator, hass):
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 2.0

    reserve = c._get_dynamic_discharge_reserve_kwh(NU, NU + timedelta(hours=13))

    assert 2.0 <= reserve < 8.64
    assert c.last_reserve_margin_breakdown["boven_capaciteit"] is False
    assert c.last_reserve_margin_breakdown["ongekapt_kwh"] == pytest.approx(reserve, abs=0.001)
