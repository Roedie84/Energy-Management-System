"""v5.61 (L-EMS-010): verkoop onder de reserve nooit "verkocht met winst".

Gevraagd: "Verkoop onder de reserve nooit als 'verkocht met winst / bewust'
labelen. De nachten naar 3 en 4 oktober heten nog steeds zo, maar dat was de
piekregel-bug (hersteld in v5.28.4)."

- Verkoop op of onder de reserve: planning (stuurfout, aandachtspunt), ook
  als de verkoopprijs hoger was dan de terugkoopprijs.
- Alleen verkoop boven de reserve kan "verkocht met winst" zijn.
- Niet na te gaan (reserve of laadstand ontbreekt): onbekend, nooit "bewust".
- De bewaarde nachten worden opnieuw ingedeeld.
"""
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import TEKORT_RESERVETOETS

MAP = Path(pkg.__file__).parent


def _c(make_coordinator):
    c = make_coordinator({})
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.2}
    c._reserve_omrekening = lambda: {"capaciteit_kwh": 8.64, "min_soc": 10.0}
    return c


def _venster(beschikbaar, reserve, verkoopprijs=45.3, tekortprijs=33.3, vol=False, zonder_beschikbaar=False):
    """Het venster 09:00-09:00 naar 4 oktober. `vol`: om 17:00 vol geweest.
    19:00-20:00 vier kwartieren verkocht; vanaf 03:00 leeg en import.
    `beschikbaar(i)` en `reserve` gelden voor de verkoopkwartieren."""
    dagen = {"2026-10-03": [], "2026-10-04": []}
    for k in range(96):
        moment = datetime(2026, 10, 3, 9, 0) + timedelta(minutes=15 * k)
        if vol and k == 32:
            rij = {"soc": 100, "net_w": -50.0, "accu_w": 0.0, "prijs_ct": 33.0}
        elif 40 <= k < 44:
            rij = {"soc": 70 - (k - 40) * 4, "net_w": -1950.0, "accu_w": 2100.0,
                   "prijs_ct": verkoopprijs, "reserve_kwh": reserve}
            if not zonder_beschikbaar:
                rij["beschikbaar_kwh"] = beschikbaar(k - 40)
        elif k >= 72:
            rij = {"soc": 9, "net_w": 300.0, "accu_w": 0.0, "prijs_ct": tekortprijs}
        else:
            rij = {"soc": 50, "net_w": -50.0, "accu_w": 250.0, "prijs_ct": 35.0}
        dagen[moment.date().isoformat()].append(
            {"tijd": moment.strftime("%H:%M"), "stand": "manual",
             "reden": "expensive_quarter_peak", **rij}
        )
    return dagen


def _rijen(dagen):
    return [r for d in dagen.values() for r in d]


def _deel_in(c, dagen):
    return c._deel_nacht_in_met_reden(
        _rijen(dagen), 97.0, 84.3, 4.2, verschuiving_w=50.0, **c._reserve_omrekening()
    )


# --- de regel ------------------------------------------------------------


def test_winstgevend_onder_de_reserve_is_planning(make_coordinator):
    c = _c(make_coordinator)
    # Van 3,0 naar 1,8 kWh beschikbaar, reserve 2,5: twee kwartieren onder.
    soort, reden = _deel_in(c, _venster(lambda i: 3.0 - i * 0.4, 2.5))
    assert soort == "planning"
    assert "onder de reserve" in reden
    assert "met winst" not in reden
    assert "stuurfout" in reden


def test_ook_na_vol_onder_de_reserve_is_planning(make_coordinator):
    c = _c(make_coordinator)
    soort, reden = _deel_in(c, _venster(lambda i: 2.0 - i * 0.4, 2.5, vol=True))
    assert soort == "planning"
    assert reden.startswith("vol geweest, daarna")
    assert "onder de reserve" in reden


def test_precies_op_de_reserve_telt_als_onder(make_coordinator):
    c = _c(make_coordinator)
    soort, _ = _deel_in(c, _venster(lambda i: 2.5 if i == 3 else 4.0, 2.5))
    assert soort == "planning"


def test_winstgevend_boven_de_reserve_blijft_winst(make_coordinator):
    c = _c(make_coordinator)
    soort, reden = _deel_in(c, _venster(lambda i: 5.0 - i * 0.4, 2.0))
    assert soort == "verkocht_met_winst"
    assert "boven de reserve verkocht met winst" in reden
    assert "45,3 ct" in reden and "33,3 ct" in reden


def test_verlies_onder_de_reserve_blijft_planning_met_vermelding(make_coordinator):
    c = _c(make_coordinator)
    soort, reden = _deel_in(c, _venster(lambda i: 2.0, 2.5, verkoopprijs=30.0))
    assert soort == "planning"
    assert reden.startswith("1,9 kWh verkocht terwijl de accu niet vol was")
    assert "onder de reserve" in reden


def test_zonder_reserve_onbekend_niet_bewust(make_coordinator):
    c = _c(make_coordinator)
    soort, reden = _deel_in(c, _venster(lambda i: 5.0, None))
    assert soort == "onbekend"
    assert "niet na te gaan" in reden
    assert "met winst" not in reden


def test_zonder_laadstand_omrekening_onbekend(make_coordinator):
    c = _c(make_coordinator)
    soort, _ = c._deel_nacht_in_met_reden(
        _rijen(_venster(None, 2.0, zonder_beschikbaar=True)), 97.0, 84.3, 4.2, verschuiving_w=50.0
    )
    assert soort == "onbekend"


def test_oude_regels_rekenen_om_uit_de_laadstand(make_coordinator):
    """Regels van vóór v5.61 hebben geen `beschikbaar_kwh`: capaciteit x
    (laadstand - minimum) / 100. Laadstand 70..58% bij 8,64 kWh en 10% min
    is 5,18..4,15 kWh."""
    c = _c(make_coordinator)
    boven = _venster(None, 4.0, zonder_beschikbaar=True)
    onder = _venster(None, 4.5, zonder_beschikbaar=True)
    assert _deel_in(c, boven)[0] == "verkocht_met_winst"
    assert _deel_in(c, onder)[0] == "planning"


# --- de bewaarde nachten ------------------------------------------------


def _records(c, dagen):
    c.dagverloop = dagen
    c.reserve_daily_records = [
        {
            "date": "2026-10-04", "shortfall": True, "tekortnacht_kwh": 1.68,
            "tekort_soort": "verkocht_met_winst", "winsttoets": "v5.55",
            "tekort_reden": "vol geweest, daarna 4,6 kWh verkocht met winst (gem. ...)",
        },
    ]


def test_bewaarde_winstnacht_onder_de_reserve_wordt_stuurfout(make_coordinator):
    c = _c(make_coordinator)
    _records(c, _venster(lambda i: 2.0 - i * 0.4, 2.5, vol=True))
    assert c.get_tekortsoorten()["tekortnachten_verkocht_met_winst"] == 1

    c._probeer_herleiding(datetime(2026, 10, 9, 13, 0, tzinfo=timezone.utc))

    r = c.reserve_daily_records[0]
    assert r["tekort_soort"] == "planning"
    assert r["reservetoets"] == TEKORT_RESERVETOETS
    assert r["shortfall"] is True, "de marge telt hem nog mee"
    soorten = c.get_tekortsoorten()
    assert soorten["tekortnachten_verkocht_met_winst"] == 0
    assert soorten["tekortnachten_planning"] == 1
    aandacht, info = c._tekortnachten_meldingen()
    assert any("nacht naar 4 okt" in a and "onder de reserve" in a for a in aandacht)
    assert not any("met winst" in i for i in info)


def test_bewaarde_winstnacht_boven_de_reserve_blijft(make_coordinator):
    c = _c(make_coordinator)
    _records(c, _venster(lambda i: 5.0 - i * 0.4, 2.0, vol=True))
    c._probeer_herleiding(datetime(2026, 10, 9, 13, 0, tzinfo=timezone.utc))
    r = c.reserve_daily_records[0]
    assert r["tekort_soort"] == "verkocht_met_winst"
    assert r["reservetoets"] == TEKORT_RESERVETOETS
    # Eén keer: daarna niet meer opnieuw.
    assert not c._wacht_op_reservetoets(r)


def test_bewaarde_winstnacht_zonder_dagverloop_wordt_onbekend(make_coordinator):
    c = _c(make_coordinator)
    _records(c, {})
    c._probeer_herleiding(datetime(2026, 10, 9, 13, 0, tzinfo=timezone.utc))
    r = c.reserve_daily_records[0]
    assert r["tekort_soort"] == "onbekend"
    assert r["reservetoets"] == "open"
    aandacht, info = c._tekortnachten_meldingen()
    assert not any("Bewust" in i and "met winst" in i for i in info)
    # Komt het dagverloop later toch, dan alsnog ingedeeld.
    c.dagverloop = _venster(lambda i: 2.0, 2.5, vol=True)
    c._probeer_herleiding(datetime(2026, 10, 9, 14, 0, tzinfo=timezone.utc))
    assert r["tekort_soort"] == "planning"
    assert r["reservetoets"] == TEKORT_RESERVETOETS


def test_bewaarde_winstnacht_zonder_reserve_wordt_onbekend(make_coordinator):
    c = _c(make_coordinator)
    _records(c, _venster(lambda i: 5.0, None, vol=True))
    c._probeer_herleiding(datetime(2026, 10, 9, 13, 0, tzinfo=timezone.utc))
    r = c.reserve_daily_records[0]
    assert r["tekort_soort"] == "onbekend"
    assert "niet na te gaan" in r["tekort_reden"]


# --- live ---------------------------------------------------------------


def _live(c, dagen):
    c.dagverloop = dagen
    c._tekort_soort = lambda *a, **k: "planning"
    c._live_tekortvolging_onvolledig = lambda begin: None
    c._tekort_venster_begin = lambda now: datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)
    c._verkocht_na_vol_kwh = 1.9
    c._vol_voor_nacht = False
    c._deel_afgelopen_nacht_in(datetime(2026, 10, 4, 9, 1, tzinfo=timezone.utc))


def test_live_onder_de_reserve_blijft_planning_met_reden(make_coordinator):
    c = _c(make_coordinator)
    _live(c, _venster(lambda i: 2.0, 2.5))
    assert c._tekort_soort_vandaag == "planning"
    assert "onder de reserve" in c._tekort_reden_vandaag


def test_live_boven_de_reserve_met_winst(make_coordinator):
    c = _c(make_coordinator)
    _live(c, _venster(lambda i: 5.0, 2.0))
    assert c._tekort_soort_vandaag == "verkocht_met_winst"


def test_live_zonder_reserve_niet_bewust(make_coordinator):
    c = _c(make_coordinator)
    _live(c, _venster(lambda i: 5.0, None))
    assert c._tekort_soort_vandaag == "onbekend"


# --- vastlegging ------------------------------------------------


def test_dagverloop_legt_beschikbare_energie_vast():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator,
    )

    bron = inspect.getsource(EnergyManagementSystemCoordinator._leg_dagverloop_vast)
    assert '"beschikbaar_kwh"' in bron
    assert '"reserve_kwh"' in bron

