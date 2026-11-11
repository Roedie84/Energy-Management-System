"""v5.225.0: wat binnen een ronde niet verandert, wordt één keer gerekend.

Uit het profiel van 11-11 18:09 (v5.224.0): `_capaciteitsregels_van_opstelling`
290 aanroepen en 171 ms eigen tijd, de witgoedplanning 735 keer, de
NILM-duplicaten 7 keer.
"""
import asyncio
from datetime import datetime, timezone

NU = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)


def _teller(c, naam):
    tel = {"n": 0}
    echt = getattr(c, naam)

    def _geteld(*a, **k):
        tel["n"] += 1
        return echt(*a, **k)

    setattr(c, naam, _geteld)
    return tel


def test_buiten_een_ronde_wordt_gewoon_gerekend(make_coordinator, hass):
    c = make_coordinator({})
    tel = _teller(c, "_bereken_gemeten_capaciteit_kwh")

    assert c._ronde_memo is None
    c.gemeten_capaciteit_kwh()
    c.gemeten_capaciteit_kwh()

    assert tel["n"] == 2


def test_binnen_een_ronde_een_keer(make_coordinator, hass):
    c = make_coordinator({})
    cap = _teller(c, "_bereken_gemeten_capaciteit_kwh")
    wit = _teller(c, "get_planned_appliance_load")
    dup = _teller(c, "_bereken_nilm_duplicate_pairs")

    c._begin_ronde_cache(NU)
    for _ in range(5):
        c.bruikbare_capaciteit_kwh()
        c.geplande_witgoed_kwh_in_periode(NU, NU)
        c.get_nilm_duplicate_pairs()

    assert (cap["n"], wit["n"], dup["n"]) == (1, 1, 1)


def test_een_nieuwe_ronde_rekent_opnieuw(make_coordinator, hass):
    c = make_coordinator({})
    cap = _teller(c, "_bereken_gemeten_capaciteit_kwh")

    c._begin_ronde_cache(NU)
    c.gemeten_capaciteit_kwh()
    c._begin_ronde_cache(NU)
    c.gemeten_capaciteit_kwh()

    assert cap["n"] == 2


def test_na_de_ronde_is_het_geheugen_leeg(make_coordinator, hass):
    c = make_coordinator({})

    async def _niets():
        return None

    gezien = {}

    async def _ronde():
        gezien["tijdens"] = c._ronde_memo is not None

    c._async_ronde = _ronde
    c._meetlaag_na_besluit = lambda: None
    c.async_ververs_pv_model = lambda now: _niets()
    asyncio.run(c.async_update())

    assert gezien["tijdens"] is True
    assert c._ronde_memo is None


def test_de_uitkomst_is_dezelfde(make_coordinator, hass):
    c = make_coordinator({})
    buiten = (c.gemeten_capaciteit_kwh(), c.get_nilm_duplicate_pairs(),
              c.geplande_witgoed_kwh_in_periode(NU, NU))
    c._begin_ronde_cache(NU)
    binnen = (c.gemeten_capaciteit_kwh(), c.get_nilm_duplicate_pairs(),
              c.geplande_witgoed_kwh_in_periode(NU, NU))

    assert buiten == binnen
