"""v5.209.0 (akkoord Ruud 10-11 16:45): versterkingsfactor op "P1 regeldoel".

Gemeten 10-11 16:20-16:41: na een lastsprong corrigeert de accu ongeveer twee
keer de afwijking en pendelt dan minutenlang. Boven 150 W krijgt de Zendure
nog maar het deel `factor` van wat erboven zit; daaronder verandert er niets.
Geen filter in de tijd. En als diagnose: de pendelenergie op de echte meter.
"""
from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone(timedelta(hours=1))
T0 = datetime(2026, 11, 10, 16, 20, tzinfo=TZ)


def _c(make_coordinator, factor=None):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    if factor is not None:
        c.config["p1_regeldoel_factor"] = factor
    c._is_salderen_active = lambda now=None: True
    return c


def test_standaard_uit_de_momentwaarde(make_coordinator, hass):
    c = _c(make_coordinator)
    for w in (-1069.0, 876.0, 40.0):
        uit = c.p1_regeldoel(w, w, T0)
        assert uit["waarde_w"] == w and uit["factor"] == 1.0


@pytest.mark.parametrize("w, verwacht", [
    (1000.0, 575.0), (-1000.0, -575.0), (150.0, 150.0), (100.0, 100.0), (-60.0, -60.0), (250.0, 200.0),
])
def test_alleen_het_deel_boven_150_w_wordt_gehalveerd(make_coordinator, hass, w, verwacht):
    c = _c(make_coordinator, 0.5)
    uit = c.p1_regeldoel(w, w, T0)
    assert uit["waarde_w"] == verwacht
    assert uit["ongedempt_w"] == w


def test_geen_filter_in_de_tijd(make_coordinator, hass):
    """Een aanhoudende last komt elke meting meteen (geschaald) door."""
    c = _c(make_coordinator, 0.5)
    for i in range(20):
        assert c.p1_regeldoel(988.0, 988.0, T0 + timedelta(seconds=i))["waarde_w"] == 569.0


@pytest.mark.parametrize("ingesteld, factor", [(0.1, 0.3), (2.0, 1.0), ("x", 1.0), (None, 1.0)])
def test_factor_blijft_binnen_de_grenzen(make_coordinator, hass, ingesteld, factor):
    c = _c(make_coordinator)
    c.config["p1_regeldoel_factor"] = ingesteld
    assert c.p1_regeldoel(10.0, 10.0, T0)["factor"] == factor


def test_pendelenergie_telt_heen_en_weer_binnen_een_minuut(make_coordinator, hass):
    c = _c(make_coordinator)
    for i in range(60):                     # 30 s afname, 30 s teruglevering van 1 kW
        c.p1_regeldoel(0.0, 1000.0 if i < 30 else -1000.0, T0 + timedelta(seconds=i))
    uit = c.p1_regeldoel(0.0, 0.0, T0 + timedelta(seconds=60))
    assert uit["pendel_wh_vandaag"] == pytest.approx(16.7, abs=0.2)


def test_pendelenergie_telt_gewone_afname_of_teruglevering_niet(make_coordinator, hass):
    c = _c(make_coordinator)
    for i in range(300):
        uit = c.p1_regeldoel(0.0, 1500.0 if i < 150 else -1500.0, T0 + timedelta(seconds=i * 2))
    # alleen het ene blok waarin het teken omsloeg kan iets tellen
    assert uit["pendel_wh_vandaag"] == 0.0


def test_pendelenergie_schuift_bij_de_dagwissel_naar_gisteren(make_coordinator, hass):
    c = _c(make_coordinator)
    for i in range(61):
        c.p1_regeldoel(0.0, 1000.0 if i < 30 else -1000.0, T0 + timedelta(seconds=i))
    uit = c.p1_regeldoel(0.0, 0.0, T0 + timedelta(days=1))
    assert uit["pendel_wh_gisteren"] == pytest.approx(16.7, abs=0.2)
    assert uit["pendel_wh_vandaag"] == 0.0
