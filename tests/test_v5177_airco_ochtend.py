"""v5.177.0 (A16, L-EMS-063) - 's ochtends alleen verwarmen als jullie dat
op dit soort dag ook doen."""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import airco_ritme as R
from custom_components.energy_management_system import airco_sturing as S
from custom_components.energy_management_system.const import AIRCO_OCHTEND_MIN_KANS

TZ = timezone(timedelta(hours=1))
WOENSDAG_7 = datetime(2026, 11, 4, 7, 0, tzinfo=TZ)


def _besluit(ochtend=None, woonkamer=17.5):
    return S.besluit(
        woonkamer_c=woonkamer, aanwezigheid="thuis", aanzet_c=18.5, doel_c=20.0,
        advies="airco", handmatig=False, airco_stand="off", door_ems_aan=False,
        setpunten_gezien=10, setpunten_nodig=5, ochtend=ochtend,
    )


def _ritme(werkdag_aan=0, werkdag_ochtenden=18):
    r = R.leeg()
    for i in range(werkdag_ochtenden):
        dag = (WOENSDAG_7 - timedelta(days=7 * (i + 1))).date().isoformat()
        r["ochtenden"]["werkdag"].append(dag)
        if i < werkdag_aan:
            r["aan"]["werkdag"][dag] = {"minuut": 420, "doel": 20.0}
    return R.geldig(r)


def test_grens():
    assert AIRCO_OCHTEND_MIN_KANS == 0.30


def test_zelden_aan_dan_niets():
    o = R.ochtend_kans(_ritme(0, 18), WOENSDAG_7)
    assert o["kans"] == 0 and o["keer"] == 0 and o["ochtenden"] == 18
    uit = _besluit(o)
    assert uit["actie"] == "niets"
    assert "zelden aan (0 van 18 ochtenden)" in uit["tekst"]


def test_vaak_aan_dan_verwarmen():
    o = R.ochtend_kans(_ritme(9, 18), WOENSDAG_7)
    assert o["kans"] >= 0.30
    assert _besluit(o)["actie"] == "verwarmen"


def test_buiten_de_ochtend_ongewijzigd():
    assert R.ochtend_kans(_ritme(0, 18), WOENSDAG_7.replace(hour=15)) is None
    assert _besluit(None)["actie"] == "verwarmen"


def test_zonder_ochtenden_geen_rem():
    assert R.ochtend_kans(R.leeg(), WOENSDAG_7) is None
