"""De accu sparen voor de duurste kwartieren (v5.25).

Gevraagd op 29 september: "is het dan wijs om de accu alleen op de dure
uren het huis te laten ondersteunen, bijvoorbeeld vanavond tot 9 uur en
morgenvroeg van 7 tot 9?" - en daarna: "ik vind dit een must voor mijn
EMS, tevens bijbehorende meldingen".

De situatie van die avond: ~3 kWh in de accu, dure avond tot 21:00, een
goedkopere nacht, een dure ochtendpiek van 07:00 tot 09:00, het goedkope
blok om 11:45. In `smart` raakte de accu leeg in de nacht en kwam de
ochtendpiek van het net.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    GRID_CHEAPER_MARGIN_EUR,
    OPTION_SMART_CHARGING,
    PRICE_SCALE_FACTOR,
)

TZ = timezone(timedelta(hours=2))
AVOND = datetime(2026, 9, 29, 20, 0, tzinfo=TZ)
BLOK = datetime(2026, 9, 30, 11, 45, tzinfo=TZ)


def _prijs(moment: datetime) -> float:
    uur = moment.hour
    if 20 <= uur < 21 or 7 <= uur < 9:
        return 0.44                      # de dure uren
    if 21 <= uur or uur < 7:
        # de nacht: goedkoper, en in de kleine uurtjes het goedkoopst
        return 0.25 if 1 <= uur < 5 else 0.29
    return 0.30


def _reeks():
    kwartieren, moment = [], AVOND
    while moment < BLOK + timedelta(hours=2):
        kwartieren.append(
            (moment, moment + timedelta(minutes=15), _prijs(moment) * PRICE_SCALE_FACTOR)
        )
        moment += timedelta(minutes=15)
    return kwartieren


def _stel_in(c, beschikbaar=3.0, smart_charging=True):
    c.smart_charging_supported = lambda: smart_charging
    c.beschikbare_energie_kwh = lambda: beschikbaar

    def segmenten(begin, eind, veilig=True):
        # 300 W huis (incl. de -50 W); vanaf 09:30 dekt de zon het huis
        uren = (eind - begin).total_seconds() / 3600
        overdag = (begin.hour, begin.minute) >= (9, 30) and begin.hour < 18
        zon = 0.3 * uren if overdag else 0.0
        return [(0.3 * uren, zon)]

    c._segmenten_verbruik_zon = segmenten
    return c


def test_haalt_de_accu_het_blok_dan_niets(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), beschikbaar=5.0)

    plan = c.spaarplan(AVOND + timedelta(hours=6), _reeks(), BLOK)

    assert plan["actief"] is False
    assert plan["reden"] == "de accu haalt het goedkope blok"


def test_de_dure_uren_worden_gedekt(make_coordinator, hass):
    """Met 3 kWh tegen 4,05 kWh nodig: de avond en de ochtendpiek krijgen
    de lading, en de duurste nachtkwartieren wat er overblijft."""
    c = _stel_in(make_coordinator({}))

    plan = c.spaarplan(AVOND, _reeks(), BLOK)

    assert plan["actief"] is True
    assert plan["nodig_kwh"] == pytest.approx(4.05, abs=0.01)
    # Alles behalve de goedkoopste nachturen (25 ct): die komen van het
    # net, zodat de accu de dure ochtendpiek nog haalt.
    assert plan["gedekt"] == ["20:00-01:30", "05:00-09:30"]


def test_in_de_goedkoopste_nachtkwartieren_wordt_gespaard(make_coordinator, hass):
    """03:00, 25 ct, nog 1,0 kWh in de accu tegen 1,95 kWh nodig tot de zon
    om 09:30. De ochtendpiek en de duurste nachtkwartieren (29 ct) krijgen
    de lading; dit kwartier van 25 ct komt van het net."""
    c = _stel_in(make_coordinator({}), beschikbaar=1.0)

    plan = c.spaarplan(datetime(2026, 9, 30, 3, 0, tzinfo=TZ), _reeks(), BLOK)

    assert plan["sparen_nu"] is True
    assert plan["prijs_nu_eur"] == 0.25


def test_in_de_ochtendpiek_dekt_de_accu(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), beschikbaar=0.6)

    plan = c.spaarplan(datetime(2026, 9, 30, 7, 15, tzinfo=TZ), _reeks(), BLOK)

    assert plan["sparen_nu"] is False


def test_een_besluit_per_kwartier_voorkomt_heen_en_weer_schakelen(make_coordinator, hass):
    """v5.27.4 - VERWACHTING BEWUST GEWIJZIGD. De marge van 2 ct is vervangen
    door een besluit per kwartier: binnen een kwartier blijft het besluit
    staan, ook als de berekening wat verschuift."""
    c = make_coordinator({})
    kwartier = (datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 10, 1, 0, 15, tzinfo=timezone.utc), 0.318, 0.07)

    eerst = c._spaarbesluit_dit_kwartier(kwartier, set(), 0.325)
    dan = c._spaarbesluit_dit_kwartier(kwartier, {kwartier[0]}, 0.30)

    assert eerst is True
    assert dan is True        # zelfde kwartier: zelfde besluit


def test_ook_een_klein_verschil_wordt_gespaard(make_coordinator, hass):
    """1 oktober: 31,8 ct tegen een grens van 32,5 ct viel binnen de marge -
    en het tekort schoof door naar de late avond tegen 38-43 ct."""
    c = make_coordinator({})
    kwartier = (datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 10, 1, 0, 15, tzinfo=timezone.utc), 0.318, 0.07)

    assert c._spaarbesluit_dit_kwartier(kwartier, set(), 0.325) is True

def test_zonder_smart_charging_geen_sparen(make_coordinator, hass):
    """De eerste grendel: de stand moet op deze accu bestaan."""
    c = _stel_in(make_coordinator({}), smart_charging=False)

    plan = c.spaarplan(datetime(2026, 9, 30, 3, 0, tzinfo=TZ), _reeks(), BLOK)

    assert plan["actief"] is False


def test_zonder_goedkoop_blok_geen_sparen(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))

    assert c.spaarplan(AVOND, _reeks(), None)["actief"] is False


@pytest.mark.asyncio
async def test_de_beslissing_zet_de_accu_op_alleen_zon(make_coordinator, hass):
    """Sparen is `smart_charging`: zon opnemen, niets afgeven."""
    c = _stel_in(make_coordinator({}), beschikbaar=1.0)
    toegepast = []

    async def pas_toe(stand):
        toegepast.append(stand)

    c._async_apply_operation = pas_toe
    c._update_financial_tracking = lambda *a, **k: None
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda now: None
    c._dispatch_notification = lambda *a, **k: None

    gespaard = await c._spaar_accu_als_nodig(
        datetime(2026, 9, 30, 3, 0, tzinfo=TZ), _reeks(), BLOK
    )

    assert gespaard is True
    assert toegepast == [OPTION_SMART_CHARGING]
    assert c.last_reason == "battery_saved_for_peak"


def test_een_melding_per_overbrugging(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), beschikbaar=1.0)
    verstuurd = []
    c._dispatch_notification = lambda *a, **k: verstuurd.append((a, k))
    plan = c.spaarplan(datetime(2026, 9, 30, 3, 0, tzinfo=TZ), _reeks(), BLOK)

    c._meld_spaarplan(plan)
    c._meld_spaarplan(plan)

    assert len(verstuurd) == 1
    (_dienst, titel, tekst, _id), soort = verstuurd[0][0], verstuurd[0][1]["kind"]
    assert soort == "accu_sparen"
    assert "11:45" in tekst and "1,0 kWh" in tekst
    assert "07:00-09:30" in tekst  # 09:00-09:30 kost 30 ct, boven de grens
    assert "." not in tekst.replace("...", "").split("nodig")[0].split("in, er is")[1]


def test_de_waarom_regels_van_het_sparen(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), beschikbaar=1.0)
    c.last_spaarplan = c.spaarplan(datetime(2026, 9, 30, 3, 0, tzinfo=TZ), _reeks(), BLOK)

    regels = " · ".join(c._waarom_bij_laden("battery_saved_for_peak", [], None))

    assert "1.0 kWh in de accu" in regels
    assert "25.0 ct" in regels
    assert "gedekt:" in regels


def test_het_kwartierplan_toont_de_gespaarde_kwartieren(make_coordinator, hass):
    """Zodat "volgende actie" vooraf laat zien wanneer de accu gespaard
    wordt - net als bij laden en piekverkoop."""
    c = _stel_in(make_coordinator({}), beschikbaar=3.0)
    c.last_spaarplan = c.spaarplan(AVOND, _reeks(), BLOK)

    netregels = c._plan_netregels(AVOND, _reeks(), lambda begin: 0.10)

    assert datetime(2026, 9, 30, 2, 0, tzinfo=TZ) in netregels["gespaard"]
    assert datetime(2026, 9, 30, 7, 0, tzinfo=TZ) not in netregels["gespaard"]


# --- v5.25: de uitkomst na afloop ----------------------------------------

from datetime import datetime as _dt, timedelta as _td, timezone as _tz

_TZ = _tz(_td(hours=2))
_BLOK = _dt(2026, 9, 30, 11, 45, tzinfo=_TZ)
_VANAF = _dt(2026, 9, 29, 20, 0, tzinfo=_TZ)


def _nacht(c, hass, rijen, ondergrens="10"):
    """Een spaarnacht in het dagverloop, per kwartier."""
    c.config = dict(c.config or {})
    c.config["battery_min_soc_number_entity"] = "number.min_soc"
    hass.states.set("number.min_soc", ondergrens)
    c.dagverloop = rijen
    c.spaar_uitkomst = {"blok": _BLOK.isoformat(), "vanaf": _VANAF.isoformat(), "gemeld": False}
    verzonden = []
    c._dispatch_notification = lambda *a, **k: verzonden.append((a, k))
    return verzonden


def _rij(tijd, reden, soc, net_w, prijs):
    return {"tijd": tijd, "reden": reden, "soc": soc, "net_w": net_w, "prijs_ct": prijs}


def test_gelukt_na_afloop_melden(make_coordinator, hass):
    c = make_coordinator({})
    verzonden = _nacht(c, hass, {
        "2026-09-30": [
            _rij("02:00", "battery_saved_for_peak", 30.0, 400.0, 26.0),
            _rij("02:15", "battery_saved_for_peak", 30.0, 400.0, 28.0),
            _rij("07:30", "default_smart", 18.0, -50.0, 40.0),
        ]
    })

    c._meld_spaaruitkomst(_BLOK + _td(minutes=5))

    assert len(verzonden) == 1
    tekst = verzonden[0][0][2]
    assert tekst.startswith("Gelukt")
    assert "0,2 kWh" in tekst  # 2 x 400 W x een kwartier
    assert "27,0 ct" in tekst
    assert verzonden[0][1]["kind"] == "accu_sparen"


def test_eerder_leeg_dan_gepland_eerlijk_melden(make_coordinator, hass):
    c = make_coordinator({})
    verzonden = _nacht(c, hass, {
        "2026-09-30": [
            _rij("02:00", "battery_saved_for_peak", 30.0, 300.0, 26.0),
            _rij("06:45", "default_smart", 10.0, 400.0, 38.0),
            _rij("07:00", "default_smart", 10.0, 400.0, 41.0),
        ]
    })

    c._meld_spaaruitkomst(_BLOK + _td(minutes=5))

    tekst = verzonden[0][0][2]
    assert "06:45 leeg" in tekst
    assert "0,2 kWh" in tekst  # 2 x 400 W x een kwartier in dure kwartieren


def test_niet_voor_het_blok_en_maar_een_keer(make_coordinator, hass):
    c = make_coordinator({})
    verzonden = _nacht(c, hass, {
        "2026-09-30": [_rij("02:00", "battery_saved_for_peak", 30.0, 300.0, 26.0)]
    })

    c._meld_spaaruitkomst(_BLOK - _td(minutes=5))
    assert verzonden == []

    c._meld_spaaruitkomst(_BLOK + _td(minutes=5))
    c._meld_spaaruitkomst(_BLOK + _td(minutes=10))
    assert len(verzonden) == 1


def test_niets_gespaard_dan_geen_melding(make_coordinator, hass):
    """Het plan was actief maar alle kwartieren werden gedekt."""
    c = make_coordinator({})
    verzonden = _nacht(c, hass, {
        "2026-09-30": [_rij("02:00", "default_smart", 40.0, -50.0, 26.0)]
    })

    c._meld_spaaruitkomst(_BLOK + _td(minutes=5))

    assert verzonden == []


def test_het_plan_onthoudt_zijn_blok_voor_de_uitkomst(make_coordinator, hass):
    c = make_coordinator({})
    c._dispatch_notification = lambda *a, **k: None
    c._last_plan_alert = {}

    c._meld_spaarplan({
        "actief": True, "blok": _BLOK.isoformat(), "beschikbaar_kwh": 3.0,
        "nodig_kwh": 4.0, "grensprijs_eur": 0.29, "gedekt": ["20:00-21:00"],
    })

    assert c.spaar_uitkomst["blok"] == _BLOK.isoformat()
    assert c.spaar_uitkomst["gemeld"] is False


# --- v5.27.4: tot de accu werkelijk weer wordt bijgevuld ------------------

from datetime import timedelta as _td2
from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR as _PSF

_NACHT = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
_BLOK = _NACHT + _td2(hours=10, minutes=45)


def _plan(make_coordinator, *, blokprijs, avondprijs, zon_na_blok=0.0, met_einde=True):
    c = make_coordinator({})
    c.smart_charging_supported = lambda: True
    c.charge_efficiency_history = [83.7] * 7
    c.discharge_efficiency_history = [100.0] * 7
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 11.40}
    c.beschikbare_energie_kwh = lambda: 1.0
    c.last_cheap_block_end = _BLOK + _td2(hours=4) if met_einde else None
    entries = []
    for i in range(96):
        b = _NACHT + _td2(minutes=15 * i)
        uur = b.hour + b.minute / 60
        if uur < 10.75: p = 0.33
        elif uur < 14.75: p = blokprijs
        else: p = avondprijs
        entries.append((b, b + _td2(minutes=15), p * _PSF))

    def segmenten(a, b, veilig=True):
        uur = a.hour + a.minute / 60
        zon = zon_na_blok / 16 if 10.75 <= uur < 14.75 else 0.0
        return [(0.1, zon)]

    c._segmenten_verbruik_zon = segmenten
    return c, entries


def test_vult_het_blok_niet_bij_dan_telt_de_avond_mee(make_coordinator, hass):
    """Blok 31,2 ct: bijladen kost 31,2 / 83,7% + 11,4 = 48,7 ct. Een avond
    van 42 ct vult het blok dus niet zinvol bij - die telt mee."""
    c, entries = _plan(make_coordinator, blokprijs=0.312, avondprijs=0.42)

    plan = c.spaarplan(_NACHT, entries, _BLOK)

    assert plan["actief"] is True
    assert plan["nodig_kwh"] > 4.3          # nacht + ochtend + avond
    assert plan["sparen_nu"] is True        # de nacht van 33 ct wordt gespaard


def test_vult_het_blok_goedkoop_bij_dan_telt_de_avond_niet(make_coordinator, hass):
    """Zonnige dag, blok 15 ct: bijladen kost 29,3 ct - de avond van 42 ct
    wordt door het blok gedekt; zoals voorheen alleen tot het blok."""
    c, entries = _plan(make_coordinator, blokprijs=0.15, avondprijs=0.42)

    plan = c.spaarplan(_NACHT, entries, _BLOK)

    assert plan["nodig_kwh"] < 4.4          # alleen nacht en ochtend


def test_zon_na_het_blok_vult_ook_bij(make_coordinator, hass):
    c, entries = _plan(make_coordinator, blokprijs=0.312, avondprijs=0.42, zon_na_blok=5.0)
    zonder, _ = _plan(make_coordinator, blokprijs=0.312, avondprijs=0.42)

    met_zon = c.spaarplan(_NACHT, entries, _BLOK)["nodig_kwh"]
    zonder_zon = zonder.spaarplan(_NACHT, entries, _BLOK)["nodig_kwh"]

    assert met_zon < zonder_zon


def test_zonder_bloktijden_zoals_voorheen(make_coordinator, hass):
    c, entries = _plan(make_coordinator, blokprijs=0.312, avondprijs=0.42, met_einde=False)

    assert c.spaarplan(_NACHT, entries, _BLOK)["nodig_kwh"] < 4.4
