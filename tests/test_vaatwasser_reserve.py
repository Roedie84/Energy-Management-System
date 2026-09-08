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


# --- v3.99.15: de verkooptoets was niet gekapt -------------------------
#
# 7 september 16:37: "'t huus heeft 17.96 kWh neudeg tot 't goedkope blok
# en d'r is 7.52 kWh". Een accu van 8,64. v3.99.2 kapte
# `_get_dynamic_discharge_reserve_kwh` op de capaciteit; `may_sell_now`
# rekent `veilig` zelf uit en was niet gekapt. Twee minuten later zei de
# nachtmelding 13,44 - derde getal.


def test_de_verkooptoets_gaat_niet_boven_de_accu(make_coordinator, hass):
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.beschikbare_energie_kwh = lambda: 7.52
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 11.1
    c._reserve_margin_factor = lambda: 1.616
    c.last_cheap_block_start = NU + timedelta(hours=20)

    uitkomst = c.may_sell_now(NU)

    assert uitkomst["nodig_voor_woning_kwh"] <= 8.64
    assert uitkomst["mag_verkopen"] is False


# --- v3.99.21: de verhouding zonder bevestigd apparaat, begrensd -------
#
# 8 september 15:18, met de Home Connect-cloud in storing:
#
#     battery_wont_last_night   5,53 beschikbaar, 12,24 kWh nodig
#     plan_verkoop_geblokkeerd  6,01 nodig
#     15:40                     "Vaatwasser is klaor na ongeveer 51 minuten"
#
# De vaatwasser draaide, maar `binary_sensor.vaatwasser_remote_start`
# bestond niet (cloudstoring), dus was hij niet BEVESTIGD. Dan geldt de
# regel van v3.99.2 niet en schaalt de verhouding het profiel weer 4x
# over vier uur: 10,6 kWh tekort, exact het geval van 2 september. De
# brug is bovendien niet gekapt op de accu, vandaar 12,24 in een accu
# van 8,64.
#
# Een onbekende zware last is hooguit een apparaat. Wat de verhouding er
# over de hele wandeling bij mag doen, is begrensd op wat een apparaat
# kost - en de brug wordt gekapt zoals de reserve en de verkooptoets.


def test_de_verhouding_voegt_hooguit_een_apparaat_toe(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONSUMPTION_CORRECTION_MAX_EXTRA_KWH,
    )

    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: NU  # de uitdemping rekent vanaf "nu"
    c = make_coordinator({})
    c.hourly_consumption_profile = {h: [0.4] * 7 for h in range(24)}
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c._get_smoothed_consumption_correction_ratio = lambda h: 4.3
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.last_heavy_load_source = None

    met = c._estimate_worst_case_deficit_kwh(NU, NU + timedelta(hours=20))
    c._get_smoothed_consumption_correction_ratio = lambda h: 1.0
    zonder = c._estimate_worst_case_deficit_kwh(NU, NU + timedelta(hours=20))

    assert met - zonder <= CONSUMPTION_CORRECTION_MAX_EXTRA_KWH + 0.01
    assert met > zonder


def test_de_brug_gaat_niet_boven_de_accu(make_coordinator, hass):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.avail"})
    hass.states.set("sensor.avail", "5.53")
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 10.6
    c.last_cheap_block_start = NU + timedelta(hours=20)
    c.last_cheap_block_end = NU + timedelta(hours=22)

    c._should_postpone_charging(
        [(NU + timedelta(hours=20), NU + timedelta(hours=22), 500)], NU, NU + timedelta(hours=20)
    )

    assert c.last_needed_kwh_to_bridge is not None
    assert c.last_needed_kwh_to_bridge <= 8.64
