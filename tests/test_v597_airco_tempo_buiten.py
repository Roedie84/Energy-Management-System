"""v5.97.0: het opwarmtempo van de airco hangt af van het verschil buiten-binnen."""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import airco_ritme as ar

def _c(make_coordinator):
    c = make_coordinator({})
    koud = c._climate_verschil_bucket(3.0, 18.0)    # verschil -15
    mild = c._climate_verschil_bucket(13.0, 18.0)   # verschil -5
    assert koud != mild
    c.climate_rate_history = {
        f"{koud}|beide_dicht|verwarmen": [0.8, 0.9, 1.0, 1.1, 1.2],
        f"{mild}|beide_dicht|verwarmen": [2.4, 2.5, 2.6, 2.5, 2.5],
    }
    return c


def test_tempo_volgt_het_verschil(make_coordinator):
    c = _c(make_coordinator)
    assert c._airco_opwarmtempo(3.0, 18.0) == 1.0     # verschil -15
    assert c._airco_opwarmtempo(13.0, 18.0) == 2.5    # verschil -5


def test_te_weinig_in_het_vakje_valt_terug_op_het_geheel(make_coordinator):
    c = _c(make_coordinator)
    alles = c._airco_opwarmtempo()
    assert c._airco_opwarmtempo(18.0, 18.0) == alles   # vakje d0 leeg


def test_zonder_temperaturen_ongewijzigd(make_coordinator):
    c = _c(make_coordinator)
    assert abs(c._airco_opwarmtempo() - 1.8) < 1e-9


def test_ochtendtempo_gebruikt_de_verwachting_op_het_warm_moment(make_coordinator):
    c = _c(make_coordinator)
    r = ar.leeg()
    ma = datetime(2026, 10, 12, tzinfo=timezone.utc)   # maandag
    for d in range(3):
        ar.noteer_ochtend_thuis(r, ma + timedelta(days=d, hours=6))
        ar.noteer_bediening(r, ma + timedelta(days=d, hours=6, minutes=45), "heat", 19)
    c.airco_ritme = r
    c._buiten_verwacht_op = lambda moment: 3.0
    c._woonkamer_verwacht_op = lambda moment: 18.0
    nu = ma + timedelta(days=3, hours=1)                 # donderdag 01:00
    assert c._airco_ochtend_tempo(nu) == 1.0


def test_tempo_nu_uit_de_projectie(make_coordinator):
    c = _c(make_coordinator)
    c.climate_forecast_trajectory = [{"tijd": "2026-10-14T19:00", "buitentemp_voorspeld_c": 13.0}]
    c.living_room_current_temp_c = 18.0
    assert c._airco_tempo_nu() == 2.5


def test_koppelingen():
    from pathlib import Path
    bron = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
            / "coordinator.py").read_text(encoding="utf-8")
    assert "tempo_c_per_uur=self._airco_ochtend_tempo(now)," in bron
    assert "tempo_c_per_uur=self._airco_tempo_nu()," in bron
    assert "self._woonkamer_verwacht_op, self._airco_ochtend_tempo(now)" in bron
