"""v5.224.0: de ronde onder de profiler, de fasen, weesmetingen weg, kostprijs
boekt door tijdens de kalibratie.

Ruud 11-11 17:44 ("Alle 5 oppakken").
"""
import asyncio
import inspect
from pathlib import Path

from custom_components.energy_management_system import rondeprofiel
from custom_components.energy_management_system import const
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

MAP = Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"


# --- het profiel -----------------------------------------------------


def test_het_profiel_noemt_de_zwaarste_functies():
    profiel = rondeprofiel.start()
    assert profiel is not None
    rondeprofiel._naam("~", 0, "x")
    sorted(range(20000), key=lambda x: -x)
    uit = rondeprofiel.samenvatting(profiel, "2026-11-11T18:00:00")

    assert uit["beschikbaar"] is True
    assert uit["moment"] == "2026-11-11T18:00:00"
    assert uit["zwaarste_eigen"] and len(uit["zwaarste_eigen"]) <= rondeprofiel.TOP_EIGEN
    assert len(uit["zwaarste_totaal"]) <= rondeprofiel.TOP_TOTAAL
    # alleen de integratie zelf in de totaallijst
    assert all(r["functie"].startswith("rondeprofiel.") for r in uit["zwaarste_totaal"])
    assert {"functie", "aanroepen", "eigen_ms", "totaal_ms"} <= set(uit["zwaarste_eigen"][0])


def test_een_tweede_profiler_breekt_niets():
    eerste = rondeprofiel.start()
    tweede = rondeprofiel.start()  # Python 3.12+: weigert een tweede; dan None
    if tweede is not None:
        tweede.disable()
    assert rondeprofiel.samenvatting(eerste)["beschikbaar"] is True


def test_de_ronde_na_de_start_en_op_verzoek(make_coordinator, hass):
    c = make_coordinator({})

    async def _niets():
        return None

    c._async_ronde = _niets
    c._meetlaag_na_besluit = lambda: None
    c.async_ververs_pv_model = lambda now: _niets()
    c._rondes_sinds_start = rondeprofiel.RONDE_NA_START - 2

    asyncio.run(c.async_update())
    assert not c.rondeprofiel
    assert len(c.tick_duration_history) == 1
    assert "lus_ms" in c.tick_duration_history[0]

    asyncio.run(c.async_update())  # de ronde na de start
    assert c.rondeprofiel["beschikbaar"] is True
    # een ronde onder de profiler telt niet mee in de rondeduur
    assert len(c.tick_duration_history) == 1

    c.rondeprofiel = {}
    c.vraag_rondeprofiel()
    asyncio.run(c.async_update())
    assert c.rondeprofiel["beschikbaar"] is True
    assert c._profiel_gevraagd is False
    asyncio.run(c.async_update())
    assert len(c.tick_duration_history) == 2


def test_de_fasen_staan_apart_van_de_onderdelen(make_coordinator, hass):
    c = make_coordinator({})

    async def _niets():
        return None

    c._async_ronde = _niets
    c._meetlaag_na_besluit = lambda: None
    c.async_ververs_pv_model = lambda now: _niets()
    for _ in range(3):
        asyncio.run(c.async_update())

    uit = c.get_tick_performance()
    assert uit["beschikbaar"] is True
    assert {"besluit en sturen", "meetlaag", "sensoren bijwerken", "opslag plannen"} <= set(uit["fasen_ms"])
    assert not set(uit["fasen_ms"]) & set(uit["onderdelen_ms"])
    assert uit["lus_mediaan_ms"] is not None
    assert uit["profiel"]["beschikbaar"] is False


def test_de_service_staat_in_de_lijst_en_in_services_yaml():
    from custom_components.energy_management_system import EIGEN_SERVICES

    assert "profiel_ronde" in EIGEN_SERVICES
    assert "\nprofiel_ronde:" in (MAP / "services.yaml").read_text(encoding="utf-8")


# --- weesmetingen ----------------------------------------------------

WEG = (
    "_meet_langere_horizon", "_meet_vooruitplan", "_meet_scenarioplan", "_zon_band_factoren",
    "_vooruitplan_opbrengst", "_saldering_opbrengst", "_vooruitplan_invoer",
    "_meet_bijkopen_bij_tekort",
)
VELDEN = ("langere_horizon_history", "vooruitplan_history", "bijkoop_history", "_eerder_rijpe_kandidaten")


def test_de_weesmetingen_zijn_weg(make_coordinator, hass):
    c = make_coordinator({})
    for naam in WEG:
        assert not hasattr(C, naam), naam
    for veld in VELDEN + ("_laatste_meetherinnering",):
        assert not hasattr(c, veld), veld
        assert veld not in const.PERSISTED_FIELDS if hasattr(const, "PERSISTED_FIELDS") else True


def test_geen_verwijzing_meer_in_de_bron():
    for pad in MAP.glob("*.py"):
        tekst = pad.read_text(encoding="utf-8")
        for naam in WEG + VELDEN:
            assert naam not in tekst, (pad.name, naam)


def test_wat_stuurt_of_gelezen_wordt_blijft(make_coordinator, hass):
    c = make_coordinator({})
    # de lange reserve stuurt (`_lange_reserve_extra_kwh`) en staat in de export
    assert hasattr(C, "_meet_lange_reserve") and hasattr(C, "lange_reserve_per_uur")
    assert c.lange_reserve_history == []
    assert hasattr(C, "_meet_werkelijke_netlading")
    assert hasattr(C, "_update_capaciteitstrend")


def test_een_oude_opslag_met_de_vervallen_velden_laadt(make_coordinator, hass):
    c = make_coordinator({})
    laad = getattr(c, "_apply_persisted_state", None) or getattr(c, "_herstel_opslag", None)
    if laad is None:
        return
    laad({"bijkoop_history": [{"moment": "x"}], "vooruitplan_history": [{"dag": "x"}],
          "langere_horizon_history": [], "_eerder_rijpe_kandidaten": ["a"]})
    assert not hasattr(c, "bijkoop_history")


# --- kostprijs tijdens de kalibratie ---------------------------------


def test_de_kalibratieronde_boekt_het_kostprijsmodel():
    bron = inspect.getsource(C._async_update_locked)
    tak = bron[bron.index("if self.kalibratie:"):bron.index("if self.force_manual:")]

    assert "self._update_battery_cost_basis_and_savings(now, entries)" in tak
    # en nog steeds niet de tegenfeitelijke of de netladingstelling apart
    assert "_update_financial_tracking" not in tak
