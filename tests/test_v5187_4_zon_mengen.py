"""v5.187.4: recente zon en uurcorrectie mengen, niet vermenigvuldigen.

Gemeld 05-11 10:33 (onbewolkt): plan 1,54 kW, gemeten 1,20 kW, Solcast 1,67 kW.
De ochtenduren hebben een lage uurcorrectie (09:00 0,58); de zon lag daar boven
die gecorrigeerde verwachting, dus de recente factor kwam op 1,3 en werd
vermenigvuldigd met de correctie van 10:30 (0,80). Nu: recent = meting / RUWE
Solcast (~0,80 die ochtend), gemengd met de uurcorrectie van het doeluur.
"""
from datetime import timedelta

import pytest

from tests.test_v5186_C_zon import DAG, _vandaag


def test_heldere_ochtend_telt_niet_dubbel(make_coordinator, monkeypatch):
    nu = DAG.replace(hour=9, minute=30)
    c = _vandaag(make_coordinator, monkeypatch, nu)
    c.learned_pv_hourly_ratio = lambda uur: 0.80
    c._zon_recent = lambda n: 0.80   # meting / ruwe Solcast van de ochtend
    a = nu + timedelta(hours=1)
    # 2,0 kWh ruw per uur in de testopzet; 0,80 en niet 0,80 x 1,3
    assert c._estimate_pv_kwh_for_period(a, a + timedelta(hours=1)) == pytest.approx(2.0 * 0.80)


def test_recent_ratio_tegen_ruwe_solcast(make_coordinator, monkeypatch):
    nu = DAG.replace(hour=10)
    c = _vandaag(make_coordinator, monkeypatch, nu)
    c.learned_pv_hourly_ratio = lambda uur: 0.5   # mag de verhouding niet meer beinvloeden
    c._pv_hour_duration_hours = 0.0
    c._pv_recente_uren = [{"begin": nu - timedelta(hours=1), "eind": nu, "geldig": True,
                           "werkelijk_kwh": 0.6, "verwacht_kwh": 0.75}]
    assert c._zon_recent(nu) == pytest.approx(0.8)
