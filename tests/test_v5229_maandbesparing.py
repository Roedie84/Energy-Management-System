"""v5.229.0: maandbesparing in het periodeoverzicht uit dezelfde bron als de sensor.

12-11: sensor "Besparing deze maand" EUR 3,49 tegen periodeoverzicht EUR 6,02.
"""

from datetime import datetime, timedelta, timezone
import inspect

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


def _c(make_coordinator, *, correctie=None):
    from custom_components.energy_management_system import coordinator as mod

    nu = datetime(2026, 11, 12, 8, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu
    c = make_coordinator({})
    c.energy_daily_history = [
        {"datum": (nu.date() - timedelta(days=n)).isoformat(), "opwek_kwh": 1.0, "verbruik_kwh": 4.0,
         "import_kwh": 3.0, "export_kwh": 0.0, "zon_export_kwh": 0.0,
         "netto_eur": 2.0, "zonder_sturing_eur": 2.5}
        for n in range(1, 12)
    ]
    c.actual_cost_today_eur = 2.46
    c.counterfactual_cost_today_eur = 1.60
    c.get_savings_correction = lambda: correctie or {"correctie_beschikbaar": False}
    return c, nu


def test_maand_plus_vandaag_is_de_maandsensor(make_coordinator):
    c, nu = _c(make_coordinator, correctie={"correctie_beschikbaar": True, "voorraadwaarde_exact_eur": 1.47})
    c.besparing_maand = {"maand": "2026-11", "waarde_eur": 3.48}
    per = c.get_period_overview(nu)["perioden"]
    assert per["vandaag"]["besparing_eur"] == 0.61 and per["vandaag"]["besparing_rauw_eur"] == -0.86
    assert per["maand"]["besparing_eur"] == 2.87
    assert round(per["maand"]["besparing_eur"] + per["vandaag"]["besparing_eur"], 2) == 3.48
    assert per["maand"]["besparing_rauw_eur"] == 5.5          # de rauwe som blijft zichtbaar
    assert per["maand"]["besparing_met_voorraad"] is True
    assert per["maand"]["gemiddeld_per_dag"]["besparing_eur"] == round(2.87 / 11, 2)


def test_zonder_voorraadcorrectie_het_rauwe_dagcijfer(make_coordinator):
    c, nu = _c(make_coordinator)
    c.besparing_maand = {"maand": "2026-11", "waarde_eur": 3.0}
    per = c.get_period_overview(nu)["perioden"]
    assert per["vandaag"]["besparing_eur"] == -0.86 and per["vandaag"]["besparing_met_voorraad"] is False
    assert per["maand"]["besparing_eur"] == 3.86


def test_maandteller_van_een_andere_maand_telt_niet(make_coordinator):
    c, nu = _c(make_coordinator)
    c.besparing_maand = {"maand": "2026-10", "waarde_eur": 9.0}
    assert c.get_period_overview(nu)["perioden"]["maand"]["besparing_eur"] == 5.5
    c.besparing_maand = None
    assert c.get_period_overview(nu)["perioden"]["maand"]["besparing_eur"] == 5.5


def test_intern_ruw_blijft_de_som_van_de_dagregels(make_coordinator):
    c, nu = _c(make_coordinator, correctie={"correctie_beschikbaar": True, "voorraadwaarde_exact_eur": 1.47})
    c.besparing_maand = {"maand": "2026-11", "waarde_eur": 3.48}
    per = c.get_period_overview(nu, ruw=True)["perioden"]
    assert per["maand"]["besparing_eur"] == 5.5 and per["vandaag"]["besparing_eur"] == -0.86


def test_een_fout_in_de_correctie_breekt_het_overzicht_niet(make_coordinator):
    c, nu = _c(make_coordinator)
    c.besparing_maand = {"maand": "2026-11", "waarde_eur": 3.0}

    def stuk():
        raise RuntimeError("accu weg")

    c.get_savings_correction = stuk
    assert c.get_period_overview(nu)["perioden"]["maand"]["besparing_eur"] == 5.5


def test_week_en_jaar_blijven_zoals_ze_waren(make_coordinator):
    c, nu = _c(make_coordinator)
    c.besparing_maand = {"maand": "2026-11", "waarde_eur": 3.0}
    per = c.get_period_overview(nu)["perioden"]
    assert per["week"]["besparing_eur"] == 3.5 and "besparing_bron" not in per["week"]


def test_de_dagstand_loopt_mee_tijdens_de_kalibratie():
    bron = inspect.getsource(C)
    tak = bron[bron.index("if await self._kalibratie_ronde(now):"):]
    tak = tak[: tak.index("if self.force_manual:")]
    assert "self._onthoud_energiedagstand(now.date())" in tak
