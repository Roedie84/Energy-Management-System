"""v5.187.1: laadplanwijzigingen 24 uur bewaren (L-EMS-067) en eerlijke temperatuurnotitie.

Live 05-11 07:00: "Nog niet genoeg geschiedenis (7/4)" terwijl de reeks vol stond.
"""
from datetime import datetime, timedelta, timezone

T0 = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)


def _plan(laden: list[int], t0=T0, n: int = 40) -> list[dict]:
    return [
        {
            "start": (t0 + timedelta(minutes=15 * i)).isoformat(),
            "modus": "manual (laden)" if i in laden else "smart",
        }
        for i in range(n)
    ]


def test_elke_wijziging_blijft_bewaard_en_dashboard_ziet_alleen_de_laatste(make_coordinator):
    c = make_coordinator({})
    c._volg_laadplan(_plan([10]), T0)
    c._volg_laadplan(_plan([10]), T0 + timedelta(minutes=1))  # geen wijziging
    c._volg_laadplan(_plan([12, 13]), T0 + timedelta(minutes=2))
    lijst = c.get_laadplan_wijzigingen()
    assert len(lijst) == 2
    assert lijst[-1]["was"] == lijst[0]["blokken"]
    assert "historie" not in c.get_laadplan_gewijzigd()
    assert "historie" in c.laadplan_gewijzigd  # blijft mee over een herstart


def test_ouder_dan_24_uur_valt_weg_en_maximaal_30(make_coordinator):
    c = make_coordinator({})
    c._volg_laadplan(_plan([20]), T0)
    later = T0 + timedelta(hours=25)
    c._volg_laadplan(_plan([21], later), later)
    assert [r["om"] for r in c.get_laadplan_wijzigingen()] == [later.isoformat()]
    for i in range(40):
        t = later + timedelta(minutes=i + 1)
        c._volg_laadplan(_plan([20 + i % 2], later), t)
    assert len(c.get_laadplan_wijzigingen()) == 30


def test_opstartfase_telt_als_na_herstart(make_coordinator):
    c = make_coordinator({})
    c._volg_laadplan(_plan([10]), T0)
    c._laadplan_grondslag = lambda moment: {"opstart": True, "inhoud_kwh": 0.1}
    c._volg_laadplan(_plan([12]), T0 + timedelta(minutes=5))
    lijst = c.get_laadplan_wijzigingen()
    assert lijst[0]["na_herstart"] is False
    assert lijst[1]["na_herstart"] is True


def test_notitie_noemt_de_echte_reden_bij_volle_reeks(make_coordinator):
    c = make_coordinator({})
    c.temp_consumption_history = [
        {"temp_c": t, "kw": k, "uren": 4.0}
        for t, k in [(20.9, 0.4), (18.9, 0.35), (13.9, 0.3), (16.9, 0.33), (9.0, 0.2), (9.9, 0.22)]
    ]
    c._finalize_temp_consumption_regression([3.2, 3.2], 3.3, 9.0)
    noot = c.last_temp_consumption_note
    assert "Nog niet genoeg" not in noot
    assert "positief" in noot


def test_notitie_bij_te_weinig_metingen_blijft(make_coordinator):
    c = make_coordinator({})
    c.temp_consumption_history = [{"temp_c": 5.0, "kw": 0.3, "uren": 4.0}]
    c._finalize_temp_consumption_regression([5.0, 5.0], 1.2, 4.0)
    assert "Nog niet genoeg geschiedenis (1/4)" in c.last_temp_consumption_note
