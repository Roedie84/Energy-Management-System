"""v5.142.0 - sturen op meer eigen gebruik (Ruud 28-10).

De winst die verkopen boven terugladen in het goedkope blok moet opleveren
is instelbaar en staat standaard op 10 ct/kWh (was vast 2 ct). Casus 28-10:
verkopen 55,5 ct, terugladen 41,1 ct / 83,5% + 4,22 ct slijtage = 53,4 ct.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_VERKOOP_MIN_WINST_CT,
    DEFAULT_VERKOOP_MIN_WINST_CT,
    PRICE_SCALE_FACTOR,
    VERKOOP_NA_BLOK_MIN_WINST_EUR,
)

TZ = timezone(timedelta(hours=1))
AVOND = datetime(2026, 10, 28, 18, 0, tzinfo=TZ)
BLOK = datetime(2026, 10, 28, 23, 30, tzinfo=TZ)
BLOK_EIND = datetime(2026, 10, 29, 5, 30, tzinfo=TZ)
U = {"lange_horizon_extra_kwh": 4.0, "total_percent": 25.0,
     "ongekapt_kwh": 10.37, "bodem_kwh": 1.3}


def _reeks(avond=0.555, blok=0.411):
    reeks, t = [], AVOND
    while t < BLOK_EIND + timedelta(hours=12):
        p = blok if BLOK <= t < BLOK_EIND else avond
        reeks.append((t, t + timedelta(minutes=15), p * PRICE_SCALE_FACTOR))
        t += timedelta(minutes=15)
    return reeks


def _c(make_coordinator, monkeypatch, config):
    c = make_coordinator(config)
    c.last_cheap_block_start, c.last_cheap_block_end = BLOK, BLOK_EIND
    monkeypatch.setattr(type(c), "learned_battery_efficiency_percent",
                        property(lambda self: 83.5))
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.22}
    c.bruikbare_capaciteit_kwh = lambda: 11.5
    return c


def test_standaard_tien_cent():
    assert DEFAULT_VERKOOP_MIN_WINST_CT == 10.0
    assert abs(VERKOOP_NA_BLOK_MIN_WINST_EUR - 0.10) < 1e-9


def test_casus_28_10_verkoopt_niet_meer(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch, {})
    uit = c._verkoopreserve_uit(10.37, U, BLOK, BLOK_EIND, 0.555, _reeks())
    assert not uit["toegepast"]
    assert uit["reserve_kwh"] == 10.37
    assert abs(uit["terugladen_eur"] - 0.534) < 0.002
    assert uit["min_winst_eur"] == 0.10


def test_echte_piek_verkoopt_nog_wel(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch, {})
    uit = c._verkoopreserve_uit(10.37, U, BLOK, BLOK_EIND, 0.75, _reeks(avond=0.75))
    assert uit["toegepast"]


def test_instelbaar_twee_cent_is_het_oude_gedrag(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch, {CONF_VERKOOP_MIN_WINST_CT: 2})
    uit = c._verkoopreserve_uit(10.37, U, BLOK, BLOK_EIND, 0.555, _reeks())
    assert uit["toegepast"]


def test_leeg_veld_valt_terug_op_standaard(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch, {CONF_VERKOOP_MIN_WINST_CT: None})
    assert c._verkoop_min_winst_eur() == 0.10


def test_in_de_opties_en_vertalingen():
    bron = open("custom_components/energy_management_system/config_flow.py",
                encoding="utf-8").read()
    assert "CONF_VERKOOP_MIN_WINST_CT" in bron
    for pad in ("strings.json", "translations/nl.json", "translations/en.json"):
        tekst = open(f"custom_components/energy_management_system/{pad}",
                     encoding="utf-8").read()
        assert tekst.count('"verkoop_min_winst_ct"') == 2
