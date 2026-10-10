"""v5.70 - winstgevend verkopen, het huis gaat voor (akkoord Ruud 10-10).

1. L-EMS-013: economische tekortnachten verhogen de marge niet meer.
2. De verkoopreserve: bij verkopen hoeft het deel van de reserve dat pas NA
   het volgende goedkope blok nodig is niet vast te blijven, als het blok dat
   goedkoper teruglaadt dan verkopen nu oplevert. Het deel tot het blok blijft
   met de volle marge en de bodem beschermd.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    PRICE_SCALE_FACTOR,
    SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY,
    TEKORTSOORT_ECONOMISCH,
    TEKORTSOORT_ONBEKEND,
    TEKORTSOORT_PLANNING,
    VERKOOP_NA_BLOK_MIN_WINST_EUR,
)

TZ = timezone(timedelta(hours=2))
AVOND = datetime(2026, 10, 10, 18, 45, tzinfo=TZ)
BLOK = datetime(2026, 10, 11, 12, 0, tzinfo=TZ)
BLOK_EIND = datetime(2026, 10, 11, 15, 0, tzinfo=TZ)


def _dag(datum: str, shortfall: bool, soort=None) -> dict:
    return {"date": datum, "shortfall": shortfall, "tekort_soort": soort, "excess": False}


# --- 1. L-EMS-013 -----------------------------------------------------------


def test_economische_nacht_telt_niet_mee_in_de_marge(make_coordinator):
    c = make_coordinator({})
    c.reserve_daily_records = [
        _dag("2026-10-04", True, TEKORTSOORT_ONBEKEND),
        _dag("2026-10-05", True, TEKORTSOORT_ONBEKEND),
        _dag("2026-10-06", False),
        _dag("2026-10-09", True, TEKORTSOORT_ECONOMISCH),
    ]
    # v5.72: onbekend telt ook niet meer mee (zie test_v572.py).
    assert c.marge_tekortnachten() == 0


def test_planning_telt_wel_onbekend_niet_meer(make_coordinator):
    """Huis gaat voor: planning telt. v5.72: onbekend (ook een oud record
    zonder soort) valt er net als economisch uit."""
    c = make_coordinator({})
    c.reserve_daily_records = [
        _dag("2026-10-04", True, TEKORTSOORT_PLANNING),
        _dag("2026-10-05", True, None),  # oud record zonder soort = onbekend
        _dag("2026-10-06", True, TEKORTSOORT_ONBEKEND),
    ]
    assert c.marge_tekortnachten() == 1


def test_de_reserve_rekent_met_de_marge_tekortnachten(make_coordinator):
    bron = open(
        "custom_components/energy_management_system/coordinator.py", encoding="utf-8"
    ).read()
    assert "recent_shortfalls = self.marge_tekortnachten()" in bron
    assert SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY == 5.0


def test_let_op_zin_zegt_dat_economisch_niet_meetelt(make_coordinator):
    c = make_coordinator({})
    c.reserve_daily_records = [_dag("2026-10-09", True, TEKORTSOORT_ECONOMISCH)]
    zin = c._let_op_tekortnachten_tekst(1)
    assert "verhoogt de veiligheidsmarge niet" in zin
    c.reserve_daily_records.append(_dag("2026-10-08", True, TEKORTSOORT_PLANNING))
    zin = c._let_op_tekortnachten_tekst(2)
    assert "1 tellen mee" in zin


# --- 2. De verkoopreserve ---------------------------------------------------


def _reeks(blokprijs=0.125, avondprijs=0.337):
    """Avond 18:45 duur, morgen 12:00-15:00 het blok."""
    reeks = []
    t = AVOND
    while t < BLOK_EIND + timedelta(hours=9):
        prijs = blokprijs if BLOK <= t < BLOK_EIND else avondprijs
        reeks.append((t, t + timedelta(minutes=15), prijs * PRICE_SCALE_FACTOR))
        t += timedelta(minutes=15)
    return reeks


def _coordinator(make_coordinator, monkeypatch, laad_w=2000.0):
    c = make_coordinator({})
    c.last_cheap_block_start = BLOK
    c.last_cheap_block_end = BLOK_EIND
    monkeypatch.setattr(
        type(c), "learned_battery_efficiency_percent", property(lambda self: 85.0)
    )
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 3.0}
    c.instelling = lambda sleutel, standaard=None: laad_w
    c.bruikbare_capaciteit_kwh = lambda: 7.78
    return c


# 10-10 avond: tot het blok 3,0 kWh nodig, na het blok nog 3,1 (lange horizon);
# marge 35% -> reserve 8,2 gekapt op de accu. Daarom werd er niets verkocht.
UITSPLITSING = {
    "lange_horizon_extra_kwh": 3.1,
    "total_percent": 35.0,
    "ongekapt_kwh": (3.0 + 3.1) * 1.35,
    "bodem_kwh": 1.30,
}


def test_het_deel_na_het_blok_mag_verkocht_worden(make_coordinator, monkeypatch):
    c = _coordinator(make_coordinator, monkeypatch)
    uit = c._verkoopreserve_uit(7.78, UITSPLITSING, BLOK, BLOK_EIND, 0.337, _reeks())
    assert uit["toegepast"]
    # Tot het blok blijft volledig beschermd: 3,0 x 1,35 = 4,05 kWh.
    assert abs(uit["reserve_kwh"] - 3.0 * 1.35) < 0.01
    assert uit["vrij_na_blok_kwh"] > 3.0


def test_nooit_onder_het_deel_tot_het_blok_of_de_bodem(make_coordinator, monkeypatch):
    c = _coordinator(make_coordinator, monkeypatch)
    u = {**UITSPLITSING, "ongekapt_kwh": (0.2 + 3.1) * 1.35}
    uit = c._verkoopreserve_uit(4.46, u, BLOK, BLOK_EIND, 0.337, _reeks())
    assert uit["reserve_kwh"] >= 1.30  # de bodem
    assert uit["reserve_kwh"] >= 0.2 * 1.35


def test_niet_als_terugladen_duurder_is_dan_verkopen(make_coordinator, monkeypatch):
    """Blok 25 ct / 0,85 + 3 ct = 32,4 ct terugladen; verkopen 33,7 ct is
    minder dan 2 ct winst - dan blijft alles vast, zoals voorheen."""
    c = _coordinator(make_coordinator, monkeypatch)
    uit = c._verkoopreserve_uit(
        7.78, UITSPLITSING, BLOK, BLOK_EIND, 0.337, _reeks(blokprijs=0.25)
    )
    assert not uit["toegepast"]
    assert uit["reserve_kwh"] == 7.78
    assert uit["terugladen_eur"] + VERKOOP_NA_BLOK_MIN_WINST_EUR > 0.337


def test_niet_meer_dan_het_blok_kan_terugladen(make_coordinator, monkeypatch):
    """Laadvermogen 400 W x 3 uur x 85% = 1,02 kWh terug te laden."""
    c = _coordinator(make_coordinator, monkeypatch, laad_w=400.0)
    uit = c._verkoopreserve_uit(7.78, UITSPLITSING, BLOK, BLOK_EIND, 0.337, _reeks())
    assert uit["toegepast"]
    assert abs(uit["laadbaar_in_blok_kwh"] - 1.02) < 0.01
    verwacht = min(7.78, (3.0 + 3.1) * 1.35 - 1.02 * 1.35)
    assert abs(uit["reserve_kwh"] - verwacht) < 0.01


def test_zonder_lange_horizon_verandert_er_niets(make_coordinator, monkeypatch):
    c = _coordinator(make_coordinator, monkeypatch)
    u = {**UITSPLITSING, "lange_horizon_extra_kwh": 0.0}
    uit = c._verkoopreserve_uit(4.05, u, BLOK, BLOK_EIND, 0.337, _reeks())
    assert not uit["toegepast"] and uit["reserve_kwh"] == 4.05


def test_onbekende_blokprijs_of_slijtage_verandert_niets(make_coordinator, monkeypatch):
    c = _coordinator(make_coordinator, monkeypatch)
    c.get_wear_cost_overview = lambda: {}
    uit = c._verkoopreserve_uit(7.78, UITSPLITSING, BLOK, BLOK_EIND, 0.337, _reeks())
    assert not uit["toegepast"] and uit["reserve_kwh"] == 7.78


def test_blok_van_morgen_zonder_eind_krijgt_de_duur_van_nu(make_coordinator, monkeypatch):
    """Het plan kent 's avonds soms alleen het begin van het blok van morgen."""
    c = _coordinator(make_coordinator, monkeypatch)
    uit = c._verkoopreserve_uit(7.78, UITSPLITSING, BLOK, None, 0.337, _reeks())
    assert uit["toegepast"]


def test_nooit_boven_de_gewone_reserve(make_coordinator, monkeypatch):
    c = _coordinator(make_coordinator, monkeypatch)
    uit = c._verkoopreserve_uit(2.0, UITSPLITSING, BLOK, BLOK_EIND, 0.337, _reeks())
    assert uit["reserve_kwh"] <= 2.0


def test_verkooptoets_plan_en_vermogen_gebruiken_de_verkoopreserve():
    bron = open(
        "custom_components/energy_management_system/coordinator.py", encoding="utf-8"
    ).read()
    # verkooptoets
    assert "verkoopinfo = self.verkoopreserve(now, blok_start)" in bron
    # plan
    assert "soc > self._planning_verkoopreserve_kwh(start, reserve_cache, entries, prijs)" in bron
    # verkoopvermogen en de tweede laag
    assert bron.count("_verkoop = self.verkoopreserve(") == 2


def test_de_zin_noemt_wat_er_vrijkomt(make_coordinator, monkeypatch):
    c = _coordinator(make_coordinator, monkeypatch)
    uit = c._verkoopreserve_uit(7.78, UITSPLITSING, BLOK, BLOK_EIND, 0.337, _reeks())
    zin = c._verkoopreserve_zin(uit)
    assert "na het blok" in zin and "33.7 ct" in zin
    assert c._verkoopreserve_zin({"toegepast": False}) == ""


# --- 3. v5.70.1: accustand in "Komend schema" -------------------------------


def _plan_rij(kwartier: int, modus: str, soc: int) -> dict:
    begin = datetime(2026, 10, 10, 12, 0, tzinfo=TZ) + timedelta(minutes=15 * kwartier)
    return {"start": begin.isoformat(), "modus": modus, "prijs_ct": 12.6, "soc_procent": soc}


def test_blokken_dragen_de_accustand_van_begin_tot_eind(make_coordinator):
    c = make_coordinator({})
    c.accustand_procent = lambda: 38.0
    c.get_quarter_plan = lambda now=None: [
        _plan_rij(0, "manual (laden)", 45),
        _plan_rij(1, "manual (laden)", 52),
        _plan_rij(2, "smart", 53),
        _plan_rij(3, "smart", 54),
    ]
    blokken = c.get_plan_blokken()
    assert (blokken[0]["soc_begin"], blokken[0]["soc_eind"]) == (38, 52)
    assert (blokken[1]["soc_begin"], blokken[1]["soc_eind"]) == (52, 54)
    assert blokken[0]["accu_tekst"] == "38 → 52%"
    assert c._accu_tekst(100, 100) == "100%"
    assert c._accu_tekst(None, None) == "—"


def test_de_kaart_toont_de_accukolom():
    import yaml
    from jinja2 import Environment

    data = yaml.safe_load(
        open(
            "custom_components/energy_management_system/dashboard_template.yaml",
            encoding="utf-8",
        )
    )
    kaart = next(
        k
        for v in data["views"]
        for s in v.get("sections") or []
        for k in s.get("cards") or []
        if k.get("title") == "Komend schema"
    )
    inhoud = kaart["content"].replace(
        "state_attr('sensor.energy_management_system_upcoming_schedule', 'transitions')",
        "BLOKKEN",
    )
    uit = Environment().from_string(inhoud).render(
        BLOKKEN=[
            {"van_tekst": "12:00", "tot_tekst": "13:00", "mode": "manual (laden)",
             "min_price_per_kwh": 0.125, "max_price_per_kwh": 0.127,
             "soc_begin": 38, "soc_eind": 66, "accu_tekst": "38 → 66%"},
            {"van_tekst": "13:00", "tot_tekst": "14:00", "mode": "smart",
             "min_price_per_kwh": 0.13, "max_price_per_kwh": 0.13,
             "soc_begin": None, "soc_eind": None},
        ]
    )
    assert "| Accu |" in uit
    assert "38 → 66%" in uit
    assert "| — |" in uit
