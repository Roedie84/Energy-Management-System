"""v5.73 (akkoord Ruud 10-10): sparen BINNEN het goedkope blok.

Gezien op 10-10 11:44: blok 10:45-16:45, 13,4 ct, de EMS laadt niet uit het
net en zet `smart`. De accu (24%, laadt ~1,2 kW uit zon) gaf het huis stroom
zodra het verbruik boven de zon kwam - tegen 13,4 ct, terwijl die kWh
vanavond 25-35 ct vervangt.

Nu: in het blok, zonder netladen, `smart_charging` (alleen zon laden, huis van
het net) als de accu vandaag niet vol raakt EN de lading na het blok meer
waard is dan de stroom nu plus een marge.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    OPTION_SMART_CHARGING,
    PRICE_SCALE_FACTOR,
    REASON_REGISTRY,
    REASON_TO_MODE,
    REDENEN_BEWUSTE_NETAFNAME,
    SPAREN_IN_BLOK_MIN_WINST_EUR,
)

TZ = timezone(timedelta(hours=2))
BLOK = datetime(2026, 10, 10, 10, 45, tzinfo=TZ)
BLOK_EIND = datetime(2026, 10, 10, 16, 45, tzinfo=TZ)
NU = datetime(2026, 10, 10, 11, 44, tzinfo=TZ)


def _prijs(moment: datetime, avond=0.35, nacht=0.25, ochtend=0.30) -> float:
    if BLOK <= moment < BLOK_EIND:
        return 0.134
    uur = moment.hour
    if 17 <= uur < 22:
        return avond
    if uur >= 22 or uur < 7:
        return nacht
    if 7 <= uur < 10:
        return ochtend
    return 0.20


def _reeks(**prijzen):
    kwartieren, moment = [], datetime(2026, 10, 10, 9, 0, tzinfo=TZ)
    while moment < datetime(2026, 10, 11, 18, 0, tzinfo=TZ):
        kwartieren.append(
            (moment, moment + timedelta(minutes=15), _prijs(moment, **prijzen) * PRICE_SCALE_FACTOR)
        )
        moment += timedelta(minutes=15)
    return kwartieren


def _stel_in(c, beschikbaar=1.5, ruimte=7.0, smart_charging=True):
    c.smart_charging_supported = lambda: smart_charging
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c.bruikbaar_tussen_grenzen_kwh = lambda: ruimte
    c.last_cheap_block_end = BLOK_EIND

    def segmenten(begin, eind, veilig=True):
        # 500 W huis; tussen 10:00 en 17:00 1,2 kW zon (ook morgen).
        uit, cursor = [], begin
        while cursor < eind:
            volgend = min(eind, cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            uren = (volgend - cursor).total_seconds() / 3600
            zon = 1.2 * uren if 10 <= cursor.hour < 17 else 0.0
            uit.append((0.5 * uren, zon))
            cursor = volgend
        return uit

    c._segmenten_verbruik_zon = segmenten
    return c


def test_sparen_als_de_accu_niet_vol_raakt_en_het_loont(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))

    a = c.sparen_in_blok(NU, _reeks(), BLOK)

    assert a["vol_voor_blokeinde"] is False
    assert a["prijs_nu_eur"] == 0.134
    # De lading in smart dekt de avond (35 ct) en de ochtend (30 ct); de
    # extra kWh dekt de duurste nachtkwartieren die nog openstaan.
    assert a["waarde_na_blok_eur"] == 0.25
    assert a["besluit"] is True
    assert a["kwartieren"][0] == datetime(2026, 10, 10, 11, 30, tzinfo=TZ).isoformat()


def test_raakt_de_accu_vol_dan_smart(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), beschikbaar=6.0)

    a = c.sparen_in_blok(NU, _reeks(), BLOK)

    assert a["vol_voor_blokeinde"] is True
    assert a["besluit"] is False
    assert "vol" in a["reden"]


def test_loont_het_niet_dan_smart(make_coordinator, hass):
    """Na het blok 14 ct: minder dan 13,4 ct plus de marge van 2 ct."""
    c = _stel_in(make_coordinator({}))

    a = c.sparen_in_blok(NU, _reeks(avond=0.14, nacht=0.14, ochtend=0.14), BLOK)

    assert a["waarde_na_blok_eur"] == 0.14
    assert a["waarde_na_blok_eur"] < a["prijs_nu_eur"] + SPAREN_IN_BLOK_MIN_WINST_EUR
    assert a["besluit"] is False


def test_dekt_de_lading_alles_al_dan_is_een_extra_kwh_niets_waard(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), beschikbaar=10.0, ruimte=30.0)

    a = c.sparen_in_blok(NU, _reeks(), BLOK)

    assert a["vol_voor_blokeinde"] is False
    assert a["waarde_na_blok_eur"] is None
    assert a["besluit"] is False


def test_buiten_het_blok_niets(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    a = c.sparen_in_blok(datetime(2026, 10, 10, 18, 0, tzinfo=TZ), _reeks(), BLOK)
    assert a["besluit"] is False
    assert a["reden"] == "niet in het goedkope blok"


def test_zonder_smart_charging_niets(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), smart_charging=False)
    assert c.sparen_in_blok(NU, _reeks(), BLOK)["besluit"] is False


def test_zonder_gemeten_getallen_niets(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    c.beschikbare_energie_kwh = lambda: None
    assert c.sparen_in_blok(NU, _reeks(), BLOK)["besluit"] is False
    c = _stel_in(make_coordinator({}))
    c._segmenten_verbruik_zon = lambda *a, **k: None
    assert c.sparen_in_blok(NU, _reeks(), BLOK)["besluit"] is False


def test_een_besluit_per_kwartier(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    eerst = c.sparen_in_blok(NU - timedelta(minutes=10), _reeks(), BLOK)
    # Binnen hetzelfde kwartier: ook als de accu ineens vol zou raken.
    c.beschikbare_energie_kwh = lambda: 6.5
    dan = c.sparen_in_blok(NU, _reeks(), BLOK)
    assert eerst["besluit"] is True and dan["besluit"] is True
    # Het volgende kwartier opnieuw.
    later = c.sparen_in_blok(NU + timedelta(minutes=5), _reeks(), BLOK)
    assert later["besluit"] is False


def _beslissing(c):
    toegepast = []

    async def pas_toe(stand):
        toegepast.append(stand)

    c._async_apply_operation = pas_toe
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda now: None
    c._dispatch_notification = lambda *a, **k: None
    return toegepast


def test_de_beslissing_zet_smart_charging_met_eigen_reden(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    toegepast = _beslissing(c)

    gespaard = asyncio.run(c._spaar_accu_als_nodig(NU, _reeks(), BLOK))

    assert gespaard is True
    assert toegepast == [OPTION_SMART_CHARGING]
    assert c.last_reason == "sparen_in_blok"
    assert c.last_sparen_in_blok["besluit"] is True
    # Het spaarplan van vóór het blok doet in het blok niets.
    assert c.last_spaarplan["reden"] == "geen goedkoop blok in zicht"


def test_loont_het_niet_dan_valt_de_beslissing_door(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), beschikbaar=6.0)
    toegepast = _beslissing(c)

    assert asyncio.run(c._spaar_accu_als_nodig(NU, _reeks(), BLOK)) is False
    assert toegepast == []
    assert c.last_sparen_in_blok["vol_voor_blokeinde"] is True


def test_de_reden_is_volledig_geregistreerd():
    assert REASON_TO_MODE["sparen_in_blok"] == OPTION_SMART_CHARGING
    assert "sparen_in_blok" in REDENEN_BEWUSTE_NETAFNAME
    for veld in ("titel", "uitleg", "ernst", "label", "waarom_vraag", "korte_naam", "emoji"):
        assert REASON_REGISTRY["sparen_in_blok"][veld]


def test_de_uitleg_noemt_de_getallen(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    c.last_sparen_in_blok = c.sparen_in_blok(NU, _reeks(), BLOK)
    c.last_reason = "sparen_in_blok"

    tekst = c._build_explanation()

    assert "Goedkoop blok: het huis draait op het net (13.4 ct)" in tekst
    assert "na het blok 25.0 ct waard" in tekst
    assert "De accu raakt vandaag niet vol." in tekst
    regels = " · ".join(c._waarom_bij_laden("sparen_in_blok", [], None))
    assert "13.4 ct" in regels and "25.0 ct" in regels


def test_de_uitleg_zonder_afweging_valt_terug_op_de_registry(make_coordinator, hass):
    c = make_coordinator({})
    c.last_sparen_in_blok = None
    assert c._reden_uitleg("sparen_in_blok") == REASON_REGISTRY["sparen_in_blok"]["uitleg"]
    assert c._reden_uitleg("default_smart") == REASON_REGISTRY["default_smart"]["uitleg"]


def test_financiele_registratie_telt_niets(make_coordinator, hass):
    """Geen ontladen, geen netladen: de waarde- en kostentellers blijven staan."""
    c = make_coordinator({})
    c._get_current_price_per_kwh = lambda entries, now: 0.134
    c._last_value_calc_time = NU - timedelta(minutes=5)
    voor = (c.total_discharge_value_eur, c.total_charge_cost_eur)

    c._update_financial_tracking(NU, _reeks(), "sparen_in_blok", None, None)

    assert (c.total_discharge_value_eur, c.total_charge_cost_eur) == voor
    assert c._last_value_calc_time == NU


def test_het_kwartierplan_toont_sparen_in_het_blok(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    c.last_sparen_in_blok = c.sparen_in_blok(NU, _reeks(), BLOK)

    netregels = c._plan_netregels(NU, _reeks(), lambda begin: 0.10)

    assert datetime(2026, 10, 10, 12, 0, tzinfo=TZ) in netregels["gespaard"]
    assert datetime(2026, 10, 10, 17, 0, tzinfo=TZ) not in netregels["gespaard"]


def test_het_plan_vangt_bij_sparen_de_zon_op():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    # 0,3 kWh zon, 0,125 verbruik: 0,175 de accu in, niets van het net.
    soc, net = C._plan_sparen(2.0, 0.125, 0.3, 7.0, 0.5)
    assert soc == pytest.approx(2.175)
    assert net == 0.0
    # Meer verbruik dan zon: het verschil van het net, de accu geeft niets.
    soc, net = C._plan_sparen(2.0, 0.4, 0.1, 7.0, 0.5)
    assert soc == 2.0
    assert net == pytest.approx(0.3)
    # Vol: het overschot gaat het net op.
    soc, net = C._plan_sparen(7.0, 0.1, 0.3, 7.0, 0.5)
    assert soc == 7.0
    assert net == pytest.approx(-0.2)
