"""v5.101: de airco overdag en 's avonds - geleerd uit jullie eigen bediening."""
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system import airco_ritme as A

TZ = timezone(timedelta(hours=2))


def _t(dag, uur, minuut=0):
    return datetime(2026, 10, dag, uur, minuut, tzinfo=TZ)


def _ritme_zoals_19_oktober():
    """De echte geschiedenis van 9 t/m 18 oktober."""
    r = A.leeg()
    overgangen = []
    for dag, uur, minuut in ((9, 14, 26), (10, 18, 23), (11, 13, 50), (13, 12, 19),
                             (14, 18, 38), (15, 19, 39), (17, 16, 30), (18, 18, 37)):
        overgangen += [(_t(dag, uur, minuut), "heat", 21), (_t(dag, 22, 0), "off", 21)]
    overgangen.sort()
    dagen = [date(2026, 10, d) for d in range(9, 19)]
    assert A.zaai_dag_uit_historie(r, overgangen, dagen) == 8
    return r


def test_zaaien_kent_het_patroon_meteen():
    r = _ritme_zoals_19_oktober()
    werk = A.geleerd_dag(r, "werkdag")
    weekend = A.geleerd_dag(r, "weekend")
    assert werk["keer_aan"] == 4 and werk["dagen"] == 6 and werk["kans"] == 0.67
    assert A.klok(werk["aan_om"]) == "16:32" and werk["doel_c"] == 21.0
    assert weekend["keer_aan"] == 4 and weekend["kans"] == 1.0 and A.klok(weekend["aan_om"]) == "17:26"
    assert r["dag_gezaaid"] is True
    # nog een keer zaaien verandert niets
    assert A.zaai_dag_uit_historie(r, [(_t(9, 15), "heat", 22)], []) == 0


def test_besluit_dag_warmt_op_tijd_voor():
    r = _ritme_zoals_19_oktober()
    arg = dict(woonkamer_c=18.5, verwacht_om=lambda m: 18.4, tempo_c_per_uur=2.0,
               aanwezigheid="thuis", advies="airco", airco_stand="off")
    # maandag 19-10: aan om 16:32, 2,6 °C tekort bij 2 °C/uur = 78 min -> start 15:14
    assert A.besluit_dag(r, nu=_t(19, 15, 0), **arg) is None
    uit = A.besluit_dag(r, nu=_t(19, 15, 20), **arg)
    assert uit["actie"] == "verwarmen" and uit["doel_c"] == 21.0 and uit["dag"]
    assert "rond 16:32" in uit["tekst"]


def test_besluit_dag_niet_als_niemand_thuis_of_al_aan():
    r = _ritme_zoals_19_oktober()
    basis = dict(woonkamer_c=18.5, verwacht_om=None, tempo_c_per_uur=2.0, advies="airco")
    nu = _t(19, 16, 0)
    assert A.besluit_dag(r, nu=nu, aanwezigheid="weg", airco_stand="off", **basis) is None
    assert A.besluit_dag(r, nu=nu, aanwezigheid="slaapt", airco_stand="off", **basis) is None
    assert A.besluit_dag(r, nu=nu, aanwezigheid="thuis", airco_stand="heat", **basis) is None
    assert A.besluit_dag(r, nu=nu, aanwezigheid="thuis", airco_stand="off",
                         **{**basis, "advies": "gas"}) is None
    warm = dict(basis, woonkamer_c=21.0)
    assert A.besluit_dag(r, nu=nu, aanwezigheid="thuis", airco_stand="off", **warm) is None


def test_eens_per_dag_en_uitzetten_telt_als_niet_gewenst():
    r = _ritme_zoals_19_oktober()
    A.noteer_ems_dag_aan(r, _t(19, 15, 20))
    arg = dict(woonkamer_c=18.5, verwacht_om=None, tempo_c_per_uur=2.0,
               aanwezigheid="thuis", advies="airco", airco_stand="off")
    assert A.besluit_dag(r, nu=_t(19, 16, 0), **arg) is None
    A.noteer_bediening(r, _t(19, 16, 5), "off", 21)
    assert "2026-10-19" not in r["dag_aan"]["werkdag"]


def test_eigen_bediening_overdag_wordt_geleerd():
    r = A.leeg()
    A.noteer_bediening(r, _t(19, 17, 45), "heat", 20.5)
    A.noteer_bediening(r, _t(19, 18, 10), "heat", 21)
    assert r["dag_aan"]["werkdag"]["2026-10-19"] == {"minuut": 17 * 60 + 45, "doel": 20.5}
    assert "2026-10-19" in r["dagen_thuis"]["werkdag"]
    # de ochtend blijft van het ochtendritme
    A.noteer_bediening(r, _t(20, 7, 0), "heat", 19)
    assert "2026-10-20" in r["aan"]["werkdag"] and "2026-10-20" not in r["dag_aan"]["werkdag"]


def test_geldig_bewaart_het_dagritme_en_overzicht_toont_het():
    r = A.geldig(_ritme_zoals_19_oktober())
    assert r["dag_gezaaid"] and len(r["dag_aan"]["weekend"]) == 4
    o = A.overzicht(r)
    assert o["werkdag"]["dag_aan_om_klok"] == "16:32" and o["werkdag"]["dag_tussen"] == "12:19-19:39"
    assert A.geldig({"ems": {"dag_aan": "2026-10-19"}})["ems"]["dag_aan"] == "2026-10-19"


def test_patroon_tekst():
    o = A.overzicht(_ritme_zoals_19_oktober())
    assert o["patroon_tekst"] == (
        "Aan op verwarmen: werkdag rond 16:32 (12:19-19:39, 67% van de dagen); "
        "weekend rond 17:26 (13:50-18:37, 100% van de dagen)"
    )
    assert A.overzicht(A.leeg())["patroon_tekst"].startswith("Nog geen patroon")
