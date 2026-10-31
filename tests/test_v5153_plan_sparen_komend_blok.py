"""v5.153.0 - het plan spaart ook in een goedkoop blok dat nog komt (akkoord Ruud 31-10).

Gemeld 31-10 15:08: het plan voor 1-11 liet de accu in het blok 13:00-14:15
(38,7-40,4 ct) van 17 naar 10 % ontladen; daarna kwam 15:15-23:45 alles van
het net tegen 44-50 ct. De sturing spaart in dat blok (`sparen_in_blok`,
v5.73), maar die rekent alleen als het blok loopt; het plan rekende er
"smart".
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    PRICE_SCALE_FACTOR,
    SPAREN_IN_BLOK_MIN_WINST_EUR,
)

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 10, 31, 16, 0, tzinfo=TZ)
BLOK = (datetime(2026, 11, 1, 13, 0, tzinfo=TZ), datetime(2026, 11, 1, 14, 15, tzinfo=TZ))


def _prijs(t: datetime, na=0.49) -> float:
    if BLOK[0] <= t < BLOK[1]:
        return 0.395
    if t >= BLOK[1]:
        return na
    return 0.42


def _entries(**k):
    t, uit = NU, []
    while t < datetime(2026, 11, 2, 0, 0, tzinfo=TZ):
        uit.append((t, t + timedelta(minutes=15), _prijs(t, **k) * PRICE_SCALE_FACTOR))
        t += timedelta(minutes=15)
    return uit


def _c(make_coordinator, zon_kw=0.5, smart_charging=True):
    c = make_coordinator({})
    c.smart_charging_supported = lambda: smart_charging

    def segmenten(begin, eind, veilig=True):
        # 1 kW huis; overdag zon_kw (minder dan het huis: niets naar de accu).
        uit, cursor = [], begin
        while cursor < eind:
            volgend = min(eind, cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            uren = (volgend - cursor).total_seconds() / 3600
            zon = zon_kw * uren if 10 <= cursor.hour < 16 else 0.0
            uit.append((1.0 * uren, zon))
            cursor = volgend
        return uit

    c._segmenten_verbruik_zon = segmenten
    return c


def _spaart(c, start, soc=0.8, bruikbaar=8.0, entries=None, blok=BLOK, nu=NU):
    netregels = {"blok": blok}
    prijs = _prijs(start)
    return c._plan_sparen_in_komend_blok(
        netregels, nu, start, prijs, soc, bruikbaar, entries or _entries()
    )


def test_spaart_in_het_komende_blok(make_coordinator, hass):
    c = _c(make_coordinator)
    for m in (0, 15, 30, 45):
        assert _spaart(c, BLOK[0] + timedelta(minutes=m)) is True


def test_niet_buiten_het_blok(make_coordinator, hass):
    c = _c(make_coordinator)
    assert _spaart(c, BLOK[0] - timedelta(minutes=15)) is False
    assert _spaart(c, BLOK[1]) is False


def test_niet_als_het_blok_al_loopt(make_coordinator, hass):
    """Een lopend blok komt uit `last_sparen_in_blok` van de sturing."""
    c = _c(make_coordinator)
    assert _spaart(c, BLOK[0] + timedelta(minutes=30), nu=BLOK[0] + timedelta(minutes=5)) is False


def test_niet_als_het_niet_loont(make_coordinator, hass):
    c = _c(make_coordinator)
    entries = _entries(na=0.395 + SPAREN_IN_BLOK_MIN_WINST_EUR - 0.005)
    assert _spaart(c, BLOK[0], entries=entries) is False


def test_niet_als_de_lading_alles_na_het_blok_dekt(make_coordinator, hass):
    c = _c(make_coordinator)
    assert _spaart(c, BLOK[0], soc=30.0, bruikbaar=40.0) is False


def test_niet_als_de_accu_met_zon_vol_raakt(make_coordinator, hass):
    c = _c(make_coordinator, zon_kw=3.0)
    assert _spaart(c, BLOK[0], soc=7.5, bruikbaar=8.0) is False


def test_zonder_smart_charging_of_blok_niets(make_coordinator, hass):
    assert _spaart(_c(make_coordinator, smart_charging=False), BLOK[0]) is False
    assert _spaart(_c(make_coordinator), BLOK[0], blok=(None, None)) is False


def test_zonder_verbruiksinschatting_niets(make_coordinator, hass):
    c = _c(make_coordinator)
    c._segmenten_verbruik_zon = lambda *a, **k: None
    assert _spaart(c, BLOK[0]) is False


def test_waarde_na_blok_ongewijzigd(make_coordinator, hass):
    """De opsplitsing verandert de rekensom van de sturing niet."""
    c = _c(make_coordinator)
    waarde, om = c._waarde_na_blok(BLOK[0], _entries(), BLOK[1], 0.8)
    assert waarde == 0.49 and om >= BLOK[1]
    assert c._waarde_na_blok(BLOK[0], _entries(), BLOK[1], 100.0) == (None, None)


def test_kwartierplan_spaart_in_het_blok(make_coordinator, hass):
    c = _c(make_coordinator)
    entries = _entries()
    c._get_forecast_entries = lambda *a, **k: entries
    c._read_sensor_float = lambda *a, **k: 10.0
    c.beschikbare_energie_kwh = lambda: 0.8
    c.effective_min_soc_percent = lambda: 0
    c._estimate_pv_kwh_for_period = lambda *a, **k: 0.0
    c._verbruik_met_terugval = lambda *a, **k: 0.25
    c._plan_netregels = lambda *a, **k: {"gespaard": set(), "blok": BLOK}
    c._plan_verkoopruimte = lambda *a, **k: None
    c._plan_laadt = lambda *a, **k: 0.0
    c._plan_dip_laadt = lambda *a, **k: 0.0
    plan = c._bouw_kwartierplan(NU)
    for r in plan:
        start = datetime.fromisoformat(r["start"])
        assert ("sparen" in r["modus"]) == (BLOK[0] <= start < BLOK[1]), (r["start"], r["modus"])
