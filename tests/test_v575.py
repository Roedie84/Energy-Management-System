"""v5.75 (akkoord Ruud 10-10): niet ontladen vóór netladen in hetzelfde blok.

Gezien op 10-10 13:23: goedkoop blok 12:00-16:45 tegen 13,0 ct, zon 0,18 kW,
de accu (54%) gaf in `smart` 0,53 kW aan het huis. Het kwartierplan liet
vanaf 13:30 tot 14:45 netladen zien tot 96-100% (12,6-12,7 ct). Elke kWh die
nu naar het huis gaat, wordt straks teruggeladen tegen blokprijs / rendement
+ slijtage: een rondtrip met puur verlies. `sparen_in_blok` zei "na het blok
dekt de lading alles al" en bleef op smart.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    OPTION_SMART_CHARGING,
    PRICE_SCALE_FACTOR,
)

TZ = timezone(timedelta(hours=2))
BLOK = datetime(2026, 10, 10, 12, 0, tzinfo=TZ)
BLOK_EIND = datetime(2026, 10, 10, 16, 45, tzinfo=TZ)
NU = datetime(2026, 10, 10, 13, 23, tzinfo=TZ)
LADEN = (datetime(2026, 10, 10, 13, 30, tzinfo=TZ), datetime(2026, 10, 10, 14, 45, tzinfo=TZ))


def _prijs(moment):
    if LADEN[0] <= moment < LADEN[1]:
        return 0.126
    if BLOK <= moment < BLOK_EIND:
        return 0.130
    return 0.30


def _reeks():
    uit, t = [], datetime(2026, 10, 10, 10, 0, tzinfo=TZ)
    while t < datetime(2026, 10, 11, 12, 0, tzinfo=TZ):
        uit.append((t, t + timedelta(minutes=15), _prijs(t) * PRICE_SCALE_FACTOR))
        t += timedelta(minutes=15)
    return uit


def _plan(laden=LADEN):
    rijen, t = [], datetime(2026, 10, 10, 13, 15, tzinfo=TZ)
    while t < datetime(2026, 10, 10, 20, 0, tzinfo=TZ):
        modus = "manual (laden)" if laden and laden[0] <= t < laden[1] else "smart"
        rijen.append({"start": t.isoformat(), "modus": modus, "prijs_ct": round(_prijs(t) * 100, 1)})
        t += timedelta(minutes=15)
    return rijen


def _stel_in(c, plan=None, rendement=84.2, slijtage=4.22):
    c.smart_charging_supported = lambda: True
    c.beschikbare_energie_kwh = lambda: 3.9
    c.bruikbaar_tussen_grenzen_kwh = lambda: 7.0
    c.last_cheap_block_end = BLOK_EIND
    # het geleerde rendement is een eigenschap; via een subklasse vastzetten
    c.__class__ = type(
        "MetRendement", (type(c),),
        {"learned_battery_efficiency_percent": property(lambda self: rendement)},
    )
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": slijtage}
    c.get_quarter_plan = lambda now=None: _plan() if plan is None else plan

    def segmenten(begin, eind, veilig=True):
        uren = (eind - begin).total_seconds() / 3600
        return [(0.5 * uren, 0.18 * uren)]

    c._segmenten_verbruik_zon = segmenten
    return c


def test_het_scenario_van_10_10_spaart_tot_het_laadmoment(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))

    a = c.sparen_in_blok(NU, _reeks(), BLOK)

    assert a["besluit"] is True
    assert a["grond"] == "netladen_in_blok"
    assert a["netladen_om"] == LADEN[0].isoformat()
    assert a["prijs_nu_ct"] == 13.0
    # 12,6 / 0,842 + 4,22 = 19,2 ct terugladen tegen 13,0 ct nu
    assert a["rondtrip_ct"] == pytest.approx(12.6 / 0.842 + 4.22, abs=0.05)
    assert "netladen volgt om 13:30 in dit blok" in a["reden"]
    assert "19,2 ct tegen 13,0 ct" in a["reden"]
    # sparen tot het laadmoment: het lopende kwartier wel, 13:30 niet
    assert datetime(2026, 10, 10, 13, 15, tzinfo=TZ).isoformat() in a["kwartieren"]
    assert LADEN[0].isoformat() not in a["kwartieren"]


def test_de_beslissing_zet_smart_charging(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    toegepast = []

    async def pas_toe(stand):
        toegepast.append(stand)

    c._async_apply_operation = pas_toe
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda now: None
    c._dispatch_notification = lambda *a, **k: None

    assert asyncio.run(c._spaar_accu_als_nodig(NU, _reeks(), BLOK)) is True
    assert toegepast == [OPTION_SMART_CHARGING]
    assert c.last_reason == "sparen_in_blok"


def test_zonder_gepland_netladen_geldt_v573(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), plan=_plan(laden=None))

    a = c.sparen_in_blok(NU, _reeks(), BLOK)

    assert a.get("grond") != "netladen_in_blok"
    assert "netladen_om" not in a
    assert "vol_voor_blokeinde" in a  # de rekensom van v5.73 liep


def test_netladen_na_het_blok_telt_niet(make_coordinator, hass):
    later = (BLOK_EIND + timedelta(hours=1), BLOK_EIND + timedelta(hours=2))
    c = _stel_in(make_coordinator({}), plan=_plan(laden=later))
    a = c.sparen_in_blok(NU, _reeks(), BLOK)
    assert a.get("grond") != "netladen_in_blok"


def test_loont_terugladen_niet_dan_niet_op_deze_grond(make_coordinator, hass):
    """Rendement 100% en geen slijtage: 12,6 ct terugladen tegen 13,0 ct nu."""
    c = _stel_in(make_coordinator({}), rendement=100.0, slijtage=0.0)
    a = c.sparen_in_blok(NU, _reeks(), BLOK)
    assert a.get("grond") != "netladen_in_blok"
    assert a["netladen_in_blok"]["besluit"] is False
    assert a["netladen_in_blok"]["rondtrip_ct"] == 12.6


def test_zonder_rendement_of_slijtage_geen_besluit_op_deze_grond(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), rendement=None)
    a = c.sparen_in_blok(NU, _reeks(), BLOK)
    assert a.get("grond") != "netladen_in_blok"
    assert "onbekend" in a["netladen_in_blok"]["reden"]


def test_zonder_smart_charging_niets(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    c.smart_charging_supported = lambda: False
    assert c.sparen_in_blok(NU, _reeks(), BLOK)["besluit"] is False


def test_een_besluit_per_kwartier(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    eerst = c.sparen_in_blok(NU - timedelta(minutes=5), _reeks(), BLOK)
    c.get_quarter_plan = lambda now=None: _plan(laden=None)
    dan = c.sparen_in_blok(NU, _reeks(), BLOK)
    assert eerst["besluit"] is True and dan["besluit"] is True


def test_het_kwartierplan_toont_sparen_tot_het_laadmoment(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    c.last_sparen_in_blok = c.sparen_in_blok(NU, _reeks(), BLOK)

    netregels = c._plan_netregels(NU, _reeks(), lambda begin: 0.10)

    assert datetime(2026, 10, 10, 13, 15, tzinfo=TZ) in netregels["gespaard"]
    assert LADEN[0] not in netregels["gespaard"]


def test_de_uitleg_en_waarom(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    c.last_sparen_in_blok = c.sparen_in_blok(NU, _reeks(), BLOK)
    c.last_reason = "sparen_in_blok"

    tekst = c._build_explanation()

    assert "om 13:30 laadt de accu uit het net" in tekst
    assert "spaart 13,0 ct" in tekst and "kost 19,2 ct" in tekst
    regels = " · ".join(c._waarom_bij_laden("sparen_in_blok", [], None))
    assert "13:30" in regels and "19.2 ct" in regels
