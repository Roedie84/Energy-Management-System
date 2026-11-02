"""v5.165.0 punt 1 - datacorrectie op netladen in het waardeplan (akkoord Ruud 02-11).

Het oude laadbesluit eist dat netladen de datacorrectie goedmaakt (gemeten
netladingen leverden minder op dan voorspeld). Het waardeplan negeerde die;
op 02-11 laadde het om 14:00-14:45 voor 34,6/37,3/36,9 ct voor een avond
van 50-51 ct. Met de correctie blijft alleen 14:00 over.
"""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from custom_components.energy_management_system import waardeplan as W

NU = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)


def _kw(prijzen, verbruik=0.1, zon=0.0):
    return [W.Kwartier(NU + timedelta(minutes=15 * i), verbruik, zon, p, 0.0) for i, p in enumerate(prijzen)]


def _accu(**k):
    return W.Accu(inhoud_kwh=0.0, bruikbaar_kwh=2.0, rendement=0.83, slijtage_eur=0.053, verkopen=False, **k)


PRIJZEN_0211 = [0.300, 0.346, 0.373, 0.369] + [0.40] * 12 + [0.505] * 8 + [0.30] * 8


def _laadkwartieren(u):
    return [i for i, r in enumerate(u.kwartieren) if r["actie"] == "laden_net"]


def test_zonder_correctie_laadt_het_plan_ook_duurdere_kwartieren():
    u = W.plan(_kw(PRIJZEN_0211), _accu())
    assert len(_laadkwartieren(u)) >= 2


def test_met_correctie_blijft_alleen_het_goedkoopste_kwartier():
    u = W.plan(_kw(PRIJZEN_0211), _accu(netlaadmarge_eur=0.05))
    assert _laadkwartieren(u) == [0]


def test_correctie_alleen_boven_het_zonoverschot():
    accu = _accu(netlaadmarge_eur=0.05)
    # 0,4 kWh zon over, 0,3 kWh de accu in: niets uit het net, geen correctie
    zonder = W._kosten_stap(0.1, 0.5, 0.3, 0.07, np.array([0.3]), _accu())
    met = W._kosten_stap(0.1, 0.5, 0.3, 0.07, np.array([0.3]), accu)
    assert met[0] == pytest.approx(zonder[0])
    # 0,6 kWh erin bij 0,4 overschot: 0,2 kWh uit het net kost 0,2 x 5 ct extra
    zonder = W._kosten_stap(0.1, 0.5, 0.3, 0.07, np.array([0.6]), _accu())
    met = W._kosten_stap(0.1, 0.5, 0.3, 0.07, np.array([0.6]), accu)
    assert met[0] - zonder[0] == pytest.approx(0.2 * 0.05)


def test_coordinator_geeft_de_datacorrectie_van_het_laadbesluit_mee(make_coordinator, hass):
    c = make_coordinator({})
    c.laadcorrectie_ct = lambda: 5.0
    c.get_rendement_per_band = lambda now=None: {}
    assert c._waardeplan_rendementen(NU)["netlaadmarge_eur"] == pytest.approx(0.05)
    c.laadcorrectie_ct = lambda: 0.0
    assert c._waardeplan_rendementen(NU)["netlaadmarge_eur"] == 0.0


def test_fout_in_de_correctie_breekt_het_plan_niet(make_coordinator, hass):
    c = make_coordinator({})

    def kapot():
        raise RuntimeError("geen nacalculatie")

    c.laadcorrectie_ct = kapot
    c.get_rendement_per_band = lambda now=None: {}
    assert "netlaadmarge_eur" not in c._waardeplan_rendementen(NU)
