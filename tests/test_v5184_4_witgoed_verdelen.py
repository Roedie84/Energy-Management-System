"""v5.184.4: een geplande cyclus telt over zijn duur, niet in zijn eerste kwartier.

Kaart claude-controle 04-11 19:18: vaatwasser gepland 05:00 -> huis 5.112 W in
het kwartier van 05:00. `geplande_witgoed_kwh_in_periode` boekte de hele cyclus
op het startmoment.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.coordinator import witgoed_kwh_in_periode

T = datetime(2026, 11, 5, 4, 0, tzinfo=timezone.utc)


def _kwartieren(regel, n=16):
    return [witgoed_kwh_in_periode(regel, T + timedelta(minutes=15 * i), T + timedelta(minutes=15 * (i + 1)))
            for i in range(n)]


def test_verdeeld_tot_het_eind():
    regel = {"start": T.isoformat(), "eind": (T + timedelta(hours=2)).isoformat(), "kwh": 1.2}
    q = _kwartieren(regel)
    assert abs(sum(q) - 1.2) < 1e-9
    assert all(abs(x - 0.15) < 1e-9 for x in q[:8]) and all(x == 0 for x in q[8:])


def test_zonder_eind_de_duur_of_de_standaard():
    regel = {"start": T.isoformat(), "duur_minuten": 60, "kwh": 1.0}
    assert abs(_kwartieren(regel)[0] - 0.25) < 1e-9
    regel = {"start": T.isoformat(), "kwh": 1.0}
    assert abs(_kwartieren(regel)[0] - 1.0 / 8) < 1e-9


def test_lange_periode_telt_alles():
    regel = {"start": T.isoformat(), "eind": (T + timedelta(hours=3)).isoformat(), "kwh": 1.5}
    assert abs(witgoed_kwh_in_periode(regel, T - timedelta(hours=1), T + timedelta(hours=10)) - 1.5) < 1e-9


# --- v5.184.4: het geleerde profiel ---------------------------------------

from custom_components.energy_management_system import witgoedprofiel as P  # noqa: E402

# 5-minutengemiddelden (W) van een vaatwasbeurt zoals 27-10 (~1,25 kWh, 50 min)
AFWAS = [1900, 1900, 1240, 1300, 1200, 1340, 1500, 1500, 1360, 600, 560, 520] + [5] * 8


def test_profiel_uit_een_afwas():
    prof = P.profiel([3] * 6 + AFWAS + AFWAS)
    assert prof is not None and abs(sum(prof) - 1) < 1e-3
    assert len(prof) == 4 and prof[0] > prof[3]


def test_gepland_volgt_het_profiel():
    prof = [0.34, 0.25, 0.31, 0.10]
    regel = {"start": T.isoformat(), "kwh": 1.2}
    q = [witgoed_kwh_in_periode(regel, T + timedelta(minutes=15 * i), T + timedelta(minutes=15 * (i + 1)), prof)
         for i in range(6)]
    assert [round(x, 3) for x in q] == [0.408, 0.3, 0.372, 0.12, 0.0, 0.0]


def test_rest_van_een_lopende_cyclus():
    prof = [0.4, 0.2, 0.2, 0.2]
    rest = P.rest_fracties(prof, 15)          # eerste kwartier voorbij
    assert [round(x, 3) for x in rest] == [0.333, 0.333, 0.333]
    rest = P.rest_fracties(prof, 7.5)         # halverwege het eerste kwartier
    assert abs(sum(rest) - 1) < 1e-9 and rest[0] > rest[-1]
