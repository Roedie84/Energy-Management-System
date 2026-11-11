"""v5.214.0 (Ruud 11-11 11:55, punten 2 en 3): meetlat verbruiksverwachting,
opbouw per plankwartier en de wisselregel op de waarde van de inhoud."""
from custom_components.energy_management_system import coordinator as C
from custom_components.energy_management_system.verbruiksmeetlat import Verbruiksmeetlat

Coord = C.EnergyManagementSystemCoordinator


def _rijen(start_uur=11, n=16, kw=0.9):
    uit = []
    for i in range(n):
        minuut = i * 15
        uit.append({"begin": f"2026-11-11T{start_uur + minuut // 60:02d}:{minuut % 60:02d}:00+01:00",
                    "verbruik_kwh": kw * 0.25, "uren": 0.25})
    return uit


def test_fout_per_horizon():
    lat = Verbruiksmeetlat()
    assert lat.noteer_plan("2026-11-11T11:00", _rijen()) is True
    assert lat.sluit_kwartier("2026-11-11T11:00:00+01:00", 1700.0) == {
        "kwartier": "2026-11-11T11:00", "gemeten_w": 1700, "dit_kwartier": 900}
    lat.sluit_kwartier("2026-11-11T12:00:00+01:00", 500.0)
    lat.sluit_kwartier("2026-11-11T14:00:00+01:00", 900.0)
    o = lat.overzicht()
    assert o["dit_kwartier"] == {"kwartieren": 1, "fout_w": 800, "afwijking_w": -800}
    assert o["1_uur"] == {"kwartieren": 1, "fout_w": 400, "afwijking_w": 400}
    assert o["3_uur"] == {"kwartieren": 1, "fout_w": 0, "afwijking_w": 0}


def test_alleen_het_eerste_plan_van_een_kwartier_telt():
    lat = Verbruiksmeetlat()
    lat.noteer_plan("2026-11-11T11:00", _rijen(kw=0.9))
    assert lat.noteer_plan("2026-11-11T11:00", _rijen(kw=2.0)) is False
    lat.sluit_kwartier("2026-11-11T11:00", 900.0)
    assert lat.overzicht()["dit_kwartier"]["fout_w"] == 0


def test_lopend_kwartier_rekent_per_uur():
    lat = Verbruiksmeetlat()
    rijen = _rijen()
    rijen[0].update(verbruik_kwh=0.094, uren=0.1043)   # 901 W in het restant
    lat.noteer_plan("2026-11-11T11:00", rijen)
    assert lat.sluit_kwartier("2026-11-11T11:00", 901.0)["dit_kwartier"] == 901


def test_zonder_meting_of_zonder_verwachting_niets():
    lat = Verbruiksmeetlat()
    assert lat.sluit_kwartier("2026-11-11T11:00", 500.0) is None
    lat.noteer_plan("2026-11-11T11:00", _rijen())
    assert lat.sluit_kwartier("2026-11-11T11:00", None) is None
    assert lat.overzicht()["dit_kwartier"]["kwartieren"] == 0


def test_kort_plan_en_begrensde_wachtrij():
    lat = Verbruiksmeetlat()
    lat.noteer_plan("a", _rijen(n=3))
    assert set(lat._open) == {"2026-11-11T11:00"}
    for i in range(80):
        lat.noteer_plan(f"k{i}", [{"begin": f"2026-11-12T{i:04d}", "verbruik_kwh": 0.1, "uren": 0.25}])
    assert len(lat._open) <= 40


def test_coordinator_sluit_het_kwartier_met_het_gemiddelde():
    c = Coord.__new__(Coord)
    c._verbruiksmeetlat_noteer(_rijen())
    c._verbruiksmeetlat_sluit({"begin": "2026-11-11T11:00:00+01:00",
                               "monsters": [{"huis_w": 1600.0}, {"huis_w": 1700.0}, {"huis_w": 1800.0}, {"huis_w": None}]})
    assert c._meetlat().overzicht()["dit_kwartier"] == {"kwartieren": 1, "fout_w": 800, "afwijking_w": -800}
    c._verbruiksmeetlat_sluit({"begin": "2026-11-11T12:00:00+01:00", "monsters": [{"huis_w": 100.0}]})   # te weinig
    assert c._meetlat().overzicht()["1_uur"]["kwartieren"] == 0
    c._verbruiksmeetlat_sluit(None)


def test_opbouw_per_plankwartier():
    c = Coord.__new__(Coord)
    c._laatste_verbruik_opbouw = {"profiel_kwh": 0.124, "omlaag_kwh": 0.0, "live_kwh": 0.101,
                                  "witgoed_kwh": 0.0, "verschuiving_kwh": 0.0125}
    c._noteer_verbruik_opbouw("b1", 0.05)
    assert c._verbruik_opbouw_van("b1") == {"verbruik_opbouw": {
        "profiel_kwh": 0.124, "live_kwh": 0.101, "verschuiving_kwh": 0.013, "klimaat_kwh": 0.05}}
    assert c._verbruik_opbouw_van("onbekend") == {}


def test_wisselregel_rekent_met_de_waarde_van_de_inhoud():
    """Punt 2: 0,3 kWh verschil; prijs 0,462, inhoud 0,431 waard (eind 0,316)."""
    nieuw = {"nu": {"uren": 0.2, "accu_kwh": -0.3, "rekenprijs_eur": 0.462, "waarde_inhoud_eur_per_kwh": 0.431},
             "eindwaarde_eur_per_kwh": 0.316}
    oud = {"nu": {"uren": 0.25, "accu_kwh": 0.0}}
    assert round(Coord._midkwartier_voordeel_eur(nieuw, oud), 4) == round(0.3 * (0.462 - 0.431), 4)
    del nieuw["nu"]["waarde_inhoud_eur_per_kwh"]
    assert round(Coord._midkwartier_voordeel_eur(nieuw, oud), 4) == round(0.3 * (0.462 - 0.316), 4)
