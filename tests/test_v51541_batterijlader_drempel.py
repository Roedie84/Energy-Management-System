"""v5.154.1 - batterijlader herkent een zuinig ladende batterij (akkoord Ruud 31-10).

31-10 16:49: batterijen aangesloten vlak voor het einde van een test; de
lader trok 3,4-3,7 W, de geleerde drempel was 4,1 W (mediaan 2,09 + 2 W),
omdat ook het nadruppelen van een volle batterij (3,2-3,3 W) als rust telde.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import BATTERIJLADER_IDLE_ATTR

NU = datetime(2026, 10, 31, 16, 50, tzinfo=timezone(timedelta(hours=1)))
HISTORIE_31_10 = [2.09, 2.26, 2.08, 2.19, 2.14, 3.2, 3.2, 3.24, 3.28, 1.22,
                  0.71, 0.76, 0.79, 1.49, 2.38, 1.63, 1.35, 1.57, 1.16, 3.34]


def test_drempel_uit_het_onderste_kwart(make_coordinator):
    c = make_coordinator({})
    setattr(c, BATTERIJLADER_IDLE_ATTR, list(HISTORIE_31_10))
    drempel = c._get_learned_completion_threshold_w(BATTERIJLADER_IDLE_ATTR, 10.0)
    assert drempel < 3.4          # 3,4-3,7 W laden wordt nu herkend
    assert drempel > 2.5          # en 0,7-1,6 W rust niet


def test_andere_apparaten_houden_de_mediaan(make_coordinator):
    c = make_coordinator({})
    c._fietsladers_idle_power_history = list(HISTORIE_31_10)
    from custom_components.energy_management_system.const import LEARNED_THRESHOLD_MARGIN_W
    import statistics
    assert c._get_learned_completion_threshold_w("_fietsladers_idle_power_history", 10.0) == (
        statistics.median(HISTORIE_31_10) + LEARNED_THRESHOLD_MARGIN_W
    )


def test_alleen_het_minimum_van_een_lege_test_telt(make_coordinator):
    c = make_coordinator({})
    setattr(c, BATTERIJLADER_IDLE_ATTR, [])
    for w in (3.2, 3.3, 0.8, 3.1):
        assert c._noteer_testminimum(BATTERIJLADER_IDLE_ATTR, w) is True
    assert getattr(c, BATTERIJLADER_IDLE_ATTR) == []
    c._leg_testminimum_vast(BATTERIJLADER_IDLE_ATTR)
    assert getattr(c, BATTERIJLADER_IDLE_ATTR) == [0.8]


def test_andere_apparaten_per_meting(make_coordinator):
    c = make_coordinator({})
    assert c._noteer_testminimum("_fietsladers_idle_power_history", 2.0) is False


def test_test_verlengt_eenmalig_bij_oplopend_vermogen(make_coordinator):
    c = make_coordinator({})
    setattr(c, BATTERIJLADER_IDLE_ATTR, list(HISTORIE_31_10))
    c._batterijlader_next_poll = NU
    assert c._test_verlengen(NU, BATTERIJLADER_IDLE_ATTR, 3.5, "_batterijlader_next_poll") is True
    assert c._batterijlader_next_poll > NU
    # tweede keer niet meer
    assert c._test_verlengen(NU, BATTERIJLADER_IDLE_ATTR, 3.5, "_batterijlader_next_poll") is False


def test_geen_verlenging_bij_rustverbruik(make_coordinator):
    c = make_coordinator({})
    setattr(c, BATTERIJLADER_IDLE_ATTR, list(HISTORIE_31_10))
    assert c._test_verlengen(NU, BATTERIJLADER_IDLE_ATTR, 1.3, "_x") is False
