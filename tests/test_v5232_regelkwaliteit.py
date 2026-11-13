"""v5.232.0: hoe goed houdt de accu de netmeter op nul - per dag bijgehouden (alleen meten)."""

from datetime import datetime, timezone

from custom_components.energy_management_system import regelkwaliteit as rk


def _loop(metingen, staat=None, vorige=None, dag="2026-11-13"):
    """metingen: (t, p1_w, regelend, quooker_w[, dag])."""
    for m in metingen:
        t, w, regelend, q = m[:4]
        d = m[4] if len(m) > 4 else dag
        staat, vorige = rk.verwerk(staat, vorige, nu_ts=float(t), dag=d, p1_w=w, regelend=regelend, quooker_w=q)
    return staat, vorige


def test_regelend_alleen_in_smart_en_tussen_de_grenzen():
    assert rk.is_regelend("smart", 800.0) is True
    assert rk.is_regelend("smart", 10.0) is False        # accu doet niets (leeg of geen vraag)
    assert rk.is_regelend("smart", 2400.0) is False      # op zijn maximum
    assert rk.is_regelend("smart", -500.0) is False      # laadt
    assert rk.is_regelend("manual", 800.0) is False
    assert rk.is_regelend("smart", None) is False


def test_afname_en_teruglevering_per_tijdsduur():
    # 60 s lang +120 W, dan 60 s lang -60 W
    staat, _ = _loop([(0, 120, True, 0), (20, 120, True, 0), (40, 120, True, 0), (60, -60, True, 0),
                      (80, -60, True, 0), (100, -60, True, 0), (120, 0, True, 0)])
    bak = staat["vandaag"]["rustig"]
    assert bak["s"] == 120
    assert round(bak["afname_wh"], 3) == 2.0 and round(bak["teruglevering_wh"], 3) == 1.0
    assert staat["vandaag"]["quooker"]["s"] == 0


def test_niet_regelend_telt_niet():
    staat, _ = _loop([(0, 900, False, 0), (20, 900, False, 0), (40, 50, True, 0), (60, 50, True, 0)])
    assert staat["vandaag"]["rustig"]["s"] == 20
    assert round(staat["vandaag"]["rustig"]["afname_wh"], 4) == round(50 * 20 / 3600, 4)


def test_quooker_en_de_nasleep_in_een_eigen_bak():
    staat, _ = _loop([(0, 10, True, 0), (10, 2100, True, 2100), (20, 300, True, 1), (30, -400, True, 1),
                      (40, 0, True, 1), (55, 0, True, 1), (70, 5, True, 1)])
    # 0-10 rustig; 10-20 quooker aan; 20-50 nasleep (30 s na 20); 55 valt net buiten
    assert staat["vandaag"]["rustig"]["s"] == 10 + 15
    assert staat["vandaag"]["quooker"]["s"] == 10 + 10 + 10 + 15
    assert staat["vandaag"]["quooker"]["afname_wh"] > 5


def test_een_gat_telt_hooguit_dertig_seconden():
    staat, _ = _loop([(0, 360, True, 0), (600, 0, True, 0)])
    assert staat["vandaag"]["rustig"]["s"] == rk.MAX_GAT_S
    assert round(staat["vandaag"]["rustig"]["afname_wh"], 3) == 3.0


def test_dagwissel_bewaart_de_dag_en_begint_opnieuw():
    staat, vorige = _loop([(0, 100, True, 0), (20, 100, True, 0)], dag="2026-11-12")
    staat, vorige = _loop([(40, 100, True, 0, "2026-11-13"), (60, 100, True, 0, "2026-11-13")], staat, vorige)
    assert [d["dag"] for d in staat["dagen"]] == ["2026-11-12"]
    assert staat["dagen"][0]["rustig"]["s"] == 40          # ook het laatste stuk van de oude dag
    assert staat["vandaag"]["dag"] == "2026-11-13" and staat["vandaag"]["rustig"]["s"] == 20


def test_een_lege_dag_wordt_niet_bewaard_en_er_blijven_veertien_dagen():
    staat = {"vandaag": rk.lege_dag("2026-10-01"), "dagen": [
        {**rk.lege_dag(f"2026-09-{n:02d}"), "rustig": {"s": 60.0, "afname_wh": 1.0, "teruglevering_wh": 0.0}}
        for n in range(1, 21)
    ]}
    staat, _ = rk.verwerk(staat, None, nu_ts=0.0, dag="2026-10-02", p1_w=0, regelend=True, quooker_w=0)
    assert len(staat["dagen"]) == rk.DAGEN_BEWAARD
    assert "2026-10-01" not in [d["dag"] for d in staat["dagen"]]


def test_na_een_herstart_zonder_voorganger_telt_de_eerste_meting_niet():
    staat = {"vandaag": {**rk.lege_dag("2026-11-13"), "rustig": {"s": 100.0, "afname_wh": 2.0, "teruglevering_wh": 0.5}}, "dagen": []}
    staat, vorige = rk.verwerk(staat, None, nu_ts=5000.0, dag="2026-11-13", p1_w=400, regelend=True, quooker_w=0)
    assert staat["vandaag"]["rustig"] == {"s": 100.0, "afname_wh": 2.0, "teruglevering_wh": 0.5}
    assert vorige["regelend"] is True


def test_kapotte_bewaarde_staat_breekt_niets():
    for kapot in (None, "x", {"vandaag": 3, "dagen": "y"}, {"vandaag": {"dag": "2026-11-13"}}):
        staat, _ = rk.verwerk(kapot, {"t": "x"}, nu_ts=10.0, dag="2026-11-13", p1_w=None, regelend=True, quooker_w=None)
        assert staat["vandaag"]["dag"] == "2026-11-13"
        assert rk.overzicht(staat)["vandaag"]["totaal"]["uren"] == 0


def test_samenvatting_met_gemiddelde_en_totaal():
    dag = {"dag": "2026-11-13", "rustig": {"s": 7200.0, "afname_wh": 20.0, "teruglevering_wh": 6.0},
           "quooker": {"s": 3600.0, "afname_wh": 100.0, "teruglevering_wh": 0.0}}
    s = rk.dag_samenvatting(dag)
    assert s["rustig"] == {"uren": 2.0, "afname_wh": 20.0, "teruglevering_wh": 6.0, "gemiddeld_w": 7.0}
    assert s["quooker"]["gemiddeld_w"] == 100.0
    assert s["totaal"]["uren"] == 3.0 and s["totaal"]["gemiddeld_w"] == 38.0
    assert rk.dag_samenvatting({"dag": "x"})["totaal"]["gemiddeld_w"] is None


def test_coordinator_telt_mee_met_het_regeldoel(make_coordinator):
    c = make_coordinator({})
    c.last_expected_mode = "smart"
    c._read_corrected_battery_power = lambda: 900.0
    c._read_sensor_float = lambda entity_id: 0.0
    t0 = datetime(2026, 11, 13, 17, 0, tzinfo=timezone.utc)
    for n, w in enumerate((60.0, 60.0, 60.0, 60.0)):
        c.p1_regeldoel(w + 10, w, t0.replace(second=n * 10))
    assert c.regelkwaliteit["vandaag"]["rustig"]["s"] == 30
    uit = c.p1_regeldoel(70.0, 60.0, t0.replace(second=40))
    assert uit["regelkwaliteit_vandaag"]["rustig"]["gemiddeld_w"] is None   # nog geen minuut
    assert c.get_regelkwaliteit()["vandaag"]["totaal"]["afname_wh"] > 0


def test_een_fout_in_de_meting_raakt_het_regeldoel_niet(make_coordinator):
    c = make_coordinator({})

    def stuk():
        raise RuntimeError("accu weg")

    c._read_corrected_battery_power = stuk
    uit = c.p1_regeldoel(110.0, 100.0, datetime(2026, 11, 13, 17, 0, tzinfo=timezone.utc))
    assert uit["waarde_w"] == 110.0


def test_bewaard_en_in_de_diagnose():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS

    assert "regelkwaliteit" in PERSISTED_PLAIN_FIELDS
    assert '"regelkwaliteit": _veilig("get_regelkwaliteit"' in (Path(pkg.__file__).parent / "diagnostics.py").read_text()
