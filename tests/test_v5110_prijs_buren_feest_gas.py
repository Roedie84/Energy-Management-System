"""v5.110.0: prijsverwachting met buurlanden, feestdagen en gassprongen.

Gevraagd 20-10: "Meenemen buurlanden, feestdagen en plotselinge sprongen in
de gasprijzen".
"""
import math
import random
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system import prijsverwachting as P


def test_pasen_en_feestdagen():
    assert P._pasen(2026) == date(2026, 4, 5)
    assert P._pasen(2027) == date(2027, 3, 28)
    f = P.feestdagen(2026)
    for d in (date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 27),
              date(2026, 5, 1), date(2026, 5, 14), date(2026, 5, 25), date(2026, 10, 3),
              date(2026, 12, 25), date(2026, 12, 26)):
        assert d in f, d
    assert date(2026, 5, 5) not in f and date(2025, 5, 5) in P.feestdagen(2025)
    # Koningsdag op zondag: de 26e
    assert date(2025, 4, 26) in P.feestdagen(2025)   # 27-4-2025 was een zondag
    assert date(2025, 4, 27) not in P.feestdagen(2025)


def test_feestdag_telt_als_weekend():
    weer = {"2026-12-25T11": {"wind": 10, "zon": 100, "temp": 5}}
    rij = P.kenmerken("2026-12-25T11", weer, 0.3)   # vrijdag, eerste kerstdag
    assert rij[5] == 1.0
    weer2 = {"2026-12-22T11": {"wind": 10, "zon": 100, "temp": 5}}
    assert P.kenmerken("2026-12-22T11", weer2, 0.3)[5] == 0.0


def test_buurlanden_apart_en_zonder_terugval_op_nederland():
    def punt(wind, zon):
        return {"hourly": {"time": ["2026-10-21T12:00"], "wind_speed_100m": [wind],
                           "shortwave_radiation": [zon], "temperature_2m": [12]}}
    antwoord = [punt(20, 100)] * len(P.PUNTEN) + [punt(40, 300)] * len(P.BUUR_PUNTEN)
    w = P.weer_uit_open_meteo(antwoord)["2026-10-21T12"]
    assert w["wind"] == 20 and w["wind_buur"] == 40 and w["zon_buur"] == 300
    rij = P.kenmerken("2026-10-21T12", {"2026-10-21T12": w}, 0.3)
    assert rij[7] == 4.0 and rij[8] == 3.0
    # oud bewaard weer zonder buurlanden: de Nederlandse waarden
    oud = {"2026-10-21T12": {"wind": 20, "zon": 100, "temp": 12}}
    assert P.kenmerken("2026-10-21T12", oud, 0.3)[7:9] == [2.0, 1.0]
    assert str(len(P.PUNTEN + P.BUUR_PUNTEN)) and P.open_meteo_url().count(",") >= 2 * 7


def test_gassprong():
    gas = {date(2026, 10, d): 1.80 for d in range(10, 20)}
    gas[date(2026, 10, 20)] = 2.10
    assert abs(P.gas_sprong(gas, date(2026, 10, 20)) - 0.30) < 1e-9
    # toekomst: de laatst bekende prijs tegen de week ervoor
    assert P.gas_sprong(gas, date(2026, 10, 23)) > 0.2
    assert P.gas_sprong(None, date(2026, 10, 20)) == 0.0
    assert P.gas_sprong({date(2026, 10, 30): 2.0}, date(2026, 10, 20)) == 0.0


def test_gas_uit_statistiek_gasdag_vanaf_zes_uur():
    begin = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)   # 00:00 lokaal op 20-10
    rijen = [{"start": (begin + timedelta(hours=h)).timestamp(), "mean": 1.0 if h < 6 else 2.0}
             for h in range(24)]
    assert P.gas_uit_statistiek(rijen) == {date(2026, 10, 20): 2.0}


def test_model_leert_de_gassprong():
    """Synthetisch: een gassprong tilt de stroomprijs meteen op; met gas in het
    model zit de verwachting van de dagen na de sprong er dichter bij."""
    rnd = random.Random(3)
    begin = datetime(2026, 7, 1, tzinfo=timezone.utc)
    weer, prijzen, gas = {}, {}, {}
    for d in range(61):
        dag = date(2026, 7, 1) + timedelta(days=d)
        gas[dag] = 1.5 + (0.6 if 30 <= d < 36 or d >= 52 else 0.0) + rnd.uniform(-0.02, 0.02)
    for h in range(60 * 24):
        t = begin + timedelta(hours=h)
        s = P.uur_sleutel(t)
        lok = t.astimezone(P.TZ)
        wind = 15 + 15 * math.sin(h / 37.0)
        weer[s] = {"wind": wind, "zon": 0.0, "temp": 12.0}
        g = gas[lok.date()]
        prijzen[s] = 0.10 + 0.15 * g - 0.003 * wind + rnd.gauss(0, 0.005)
    met = P.backtest(prijzen, weer, dagen=6, vooruit=1, gas=gas)
    zonder = P.backtest(prijzen, weer, dagen=6, vooruit=1)
    assert met["afwijking_model_ct"] < zonder["afwijking_model_ct"]


def test_gevoeligheid_toont_de_nieuwe_kenmerken():
    rnd = random.Random(1)
    begin = datetime(2026, 7, 1, tzinfo=timezone.utc)
    weer, prijzen = {}, {}
    for h in range(40 * 24):
        t = begin + timedelta(hours=h)
        s = P.uur_sleutel(t)
        weer[s] = {"wind": 10 + rnd.uniform(0, 20), "zon": 0.0, "temp": 12.0,
                   "wind_buur": 10 + rnd.uniform(0, 20), "zon_buur": 0.0}
        prijzen[s] = 0.3 - 0.004 * weer[s]["wind_buur"] + rnd.gauss(0, 0.005)
    laatste = max(P._lokaal(s).date() for s in prijzen)
    uit = P.maak_verwachting(prijzen, weer, laatste, laatste)
    g = uit["gevoeligheid"]
    assert g["buurlanden_wind_ct_per_10_kmh"] < -2
    assert "gas_ct_per_10_ct_m3" in g and uit["gas_dagen"] == 0
