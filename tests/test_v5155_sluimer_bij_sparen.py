"""Sluimerverbruik meetellen bij lang vasthouden (v5.155.0, akkoord Ruud 31-10).

Gemeld 31-10 21:10: het plan hield 1,38 kWh ~18,5 uur vast (47,9 ct nu,
49,3-50 ct morgen). Sparen kost 7,8 W uit de cellen (~0,14 kWh, ~EUR 0,07),
de prijswinst was ~EUR 0,02. Dan nu gebruiken.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 10, 31, 21, 15, tzinfo=TZ)
BLOK = datetime(2026, 11, 1, 13, 0, tzinfo=TZ)


def _reeks(prijs_nu=0.479, prijs_piek=0.50):
    kwartieren, moment = [], NU
    eind = datetime(2026, 11, 1, 21, 0, tzinfo=TZ)
    while moment < eind:
        if moment >= datetime(2026, 11, 1, 15, 45, tzinfo=TZ) and moment.hour < 20:
            p = prijs_piek
        elif BLOK <= moment < BLOK + timedelta(hours=1, minutes=15):
            p = 0.39
        else:
            p = prijs_nu
        kwartieren.append((moment, moment + timedelta(minutes=15), p * PRICE_SCALE_FACTOR))
        moment += timedelta(minutes=15)
    return kwartieren


def _stel_in(c, sluimer_w=7.8, betrouwbaar=True, beschikbaar=1.2):
    c.smart_charging_supported = lambda: True
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c._piek_vervangprijs = lambda entries, blok: 0.60  # bijladen in het blok loont niet
    c._spaarkwartieren_op_verkooptoets = lambda k, b: (k, {})

    def segmenten(begin, eind, veilig=True):
        uren = (eind - begin).total_seconds() / 3600
        return [(0.3 * uren, 0.0)]

    c._segmenten_verbruik_zon = segmenten
    c.get_sluimerverbruik = lambda now=None: {
        "per_stand": {
            "sparen": {"uren": 51.8, "gemiddeld_w": sluimer_w, "betrouwbaar": betrouwbaar},
            "leeg": {"uren": 10, "gemiddeld_w": 0.3, "betrouwbaar": True},
        }
    }
    return c


def test_lang_vasthouden_kost_meer_dan_het_oplevert(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    plan = c.spaarplan(NU, _reeks(), BLOK)
    assert plan["actief"] is True
    s = plan["sluimer"]
    assert s["nu_gebruiken"] is True
    assert s["verlies_eur"] > s["winst_eur"]
    assert s["uren_tot_gebruik"] > 15
    assert plan["sparen_nu"] is False
    assert plan["gespaard"] == []          # het plan rekent "smart"
    assert "sluimer" in plan["reden"]


def test_groot_prijsverschil_blijft_sparen(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))
    plan = c.spaarplan(NU, _reeks(prijs_nu=0.30, prijs_piek=0.50), BLOK)
    assert plan["sluimer"]["nu_gebruiken"] is False
    assert plan["sparen_nu"] is True
    assert plan["gespaard"]


def test_zonder_betrouwbare_meting_zoals_voorheen(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), betrouwbaar=False)
    plan = c.spaarplan(NU, _reeks(), BLOK)
    assert plan["sluimer"]["nu_gebruiken"] is False
    assert plan["sparen_nu"] is True


def test_zonder_sluimer_zoals_voorheen(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), sluimer_w=0.3)
    plan = c.spaarplan(NU, _reeks(), BLOK)
    assert plan["sluimer"]["nu_gebruiken"] is False
    assert plan["sparen_nu"] is True


def test_fout_in_de_meting_raakt_de_sturing_niet(make_coordinator, hass):
    c = _stel_in(make_coordinator({}))

    def kapot(now=None):
        raise RuntimeError("meetlaag weg")

    c.get_sluimerverbruik = kapot
    plan = c.spaarplan(NU, _reeks(), BLOK)
    assert plan["sluimer"] == {"nu_gebruiken": False}
    assert plan["sparen_nu"] is True


def test_besluit_per_kwartier_met_sluimer(make_coordinator, hass):
    c = make_coordinator({})
    k = (NU, NU + timedelta(minutes=15), 0.30, 0.07)
    assert c._spaarbesluit_dit_kwartier(k, set(), 0.40, True) is False
    c._spaar_kwartier = None
    assert c._spaarbesluit_dit_kwartier(k, set(), 0.40) is True
