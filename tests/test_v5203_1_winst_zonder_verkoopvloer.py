"""v5.203.1: na v5.198.0 is verkopen onder de (oude) huisreserve geen stuurfout.

Ruud 09-11 11:40: "doen wat economisch voor mij het voordeligste is". Sinds
v5.198.0 is de huisreserve geen verkoopvloer meer. De tekortindeling (v5.61)
noemde een winstgevende verkoop onder de reserve nog "het huis gaat voor:
stuurfout" - zo zou de nacht naar 10-11 (verkocht 15:45-19:15 tegen 63-88 ct,
teruggekocht tegen 40-66 ct) een vals aandachtspunt geven.
"""
import custom_components.energy_management_system.coordinator as co
from tests.test_v561_verkoop_onder_reserve import _c, _deel_in, _venster


def test_vlag_staat_uit():
    assert co.WAARDEPLAN_VERKOOPVLOER_RESERVE is False


def test_winstgevend_onder_de_reserve_is_winst(make_coordinator, monkeypatch):
    monkeypatch.setattr(co, "WAARDEPLAN_VERKOOPVLOER_RESERVE", False)
    c = _c(make_coordinator)
    soort, reden = _deel_in(c, _venster(lambda i: 3.0 - i * 0.4, 2.5, vol=True))
    assert soort == "verkocht_met_winst"
    assert "met winst" in reden
    assert "stuurfout" not in reden


def test_verlieslatend_onder_de_reserve_blijft_planning(make_coordinator, monkeypatch):
    monkeypatch.setattr(co, "WAARDEPLAN_VERKOOPVLOER_RESERVE", False)
    c = _c(make_coordinator)
    soort, _reden = _deel_in(
        c, _venster(lambda i: 3.0 - i * 0.4, 2.5, verkoopprijs=30.0, tekortprijs=40.0, vol=True))
    assert soort == "planning"


def test_zonder_reserve_toch_winst(make_coordinator, monkeypatch):
    """Zonder verkoopvloer doet de reserve er niet toe: geen 'onbekend' meer."""
    monkeypatch.setattr(co, "WAARDEPLAN_VERKOOPVLOER_RESERVE", False)
    c = _c(make_coordinator)
    soort, _reden = _deel_in(c, _venster(lambda i: 3.0, None, vol=True))
    assert soort == "verkocht_met_winst"


# --- vol na het tekort wist de avondverkoop niet ------------------------------

def _venster_met_nachtlading():
    """Avond verkocht (vol om 17:00), 03:00-05:00 tekort, daarna vol geladen."""
    from datetime import datetime, timedelta
    dagen = _venster(lambda i: 3.0 - i * 0.4, 2.5, vol=True)
    rijen = [r for d in dagen.values() for r in d]
    for k, r in enumerate(rijen):
        moment = datetime(2026, 10, 3, 9, 0) + timedelta(minutes=15 * k)
        if moment.hour >= 6 and moment.date().day == 4:
            r.update(soc=99, net_w=150.0, accu_w=0.0, prijs_ct=50.0)
        elif moment.hour == 5 and moment.date().day == 4:
            r.update(soc=60, net_w=2500.0, accu_w=-2350.0, prijs_ct=30.0)
    return rijen


def test_vol_na_het_tekort_telt_niet_als_vol(make_coordinator, monkeypatch):
    monkeypatch.setattr(co, "WAARDEPLAN_VERKOOPVLOER_RESERVE", False)
    c = _c(make_coordinator)
    soort, reden = c._deel_nacht_in_met_reden(
        _venster_met_nachtlading(), 97.0, 84.3, 4.2, verschuiving_w=50.0, **c._reserve_omrekening())
    assert soort == "verkocht_met_winst", reden
    assert "niets verkocht" not in reden


def test_live_vol_na_tekort_houdt_de_verkoop(make_coordinator, monkeypatch):
    from datetime import datetime, timezone
    c = make_coordinator({})
    monkeypatch.setattr(c, "_volg_gat_bij", lambda now: None)
    monkeypatch.setattr(c, "accustand_procent", lambda: 99.0)
    monkeypatch.setattr(c, "_bovengrens_procent", lambda: 100.0)
    c._vol_voor_nacht = True
    c._verkocht_na_vol_kwh = 3.5
    c._tekortnacht_lopend_kwh = 0.54
    c._volg_vol_en_verkoop(datetime(2026, 11, 10, 5, 45, tzinfo=timezone.utc))
    assert c._verkocht_na_vol_kwh == 3.5
    # zonder tekort vannacht: vol wist de teller zoals voorheen
    c._tekortnacht_lopend_kwh = 0.0
    c._volg_vol_en_verkoop(datetime(2026, 11, 10, 5, 50, tzinfo=timezone.utc))
    assert c._verkocht_na_vol_kwh == 0.0
