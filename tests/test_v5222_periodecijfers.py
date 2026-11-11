"""v5.222.0: periodecijfers die elkaar tegenspraken (punten 2, 3 en 4 van het onderzoek van 11-11).

- 2: jaar en contractjaar toonden een som over een deel van de dagen.
- 3: zelfvoorziening had twee definities en "week" twee lengtes.
- 4: de besparing per week liet de voorraad in de accu weg.
"""

from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


def _c(make_coordinator, dagen=20, met_prijs=5):
    from custom_components.energy_management_system import coordinator as mod

    nu = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu
    c = make_coordinator({})
    c.energy_daily_history = []
    for n in range(1, dagen + 1):
        rij = {"datum": (nu.date() - timedelta(days=n)).isoformat(), "opwek_kwh": 1.0,
               "verbruik_kwh": 4.0, "import_kwh": 3.0, "export_kwh": 0.0, "zon_export_kwh": 0.0}
        if n <= met_prijs:
            rij.update({"netto_eur": 2.0, "zonder_sturing_eur": 2.5})
        c.energy_daily_history.append(rij)
    c.actual_cost_today_eur = 0.0
    return c, nu


# --- punt 2 ---------------------------------------------------------------


def test_een_som_over_een_deel_van_de_dagen_verdwijnt():
    p = {"dagen": 224, "inkoop_eur": 92.62, "opwek_kwh": 3352.7,
         "dagen_met_waarde": {"inkoop_eur": 48, "opwek_kwh": 224}}
    uit = C._zonder_onvolledige_sommen(p)
    assert uit["inkoop_eur"] is None and uit["onvolledig"] == {"inkoop_eur": "48 van 224 dagen"}
    assert uit["opwek_kwh"] == 3352.7
    assert p["inkoop_eur"] == 92.62  # het origineel blijft ongemoeid


def test_een_volledige_periode_blijft_zoals_hij_was():
    p = {"dagen": 7, "inkoop_eur": 30.82, "dagen_met_waarde": {"inkoop_eur": 7}}
    assert C._zonder_onvolledige_sommen(p) == p


def test_alleen_jaar_en_contractjaar_worden_opgeschoond(make_coordinator):
    c, nu = _c(make_coordinator, dagen=20, met_prijs=5)
    per = c.get_period_overview(nu)["perioden"]
    # week (7 dagen, 5 met saldo): de cockpit toont dit met "5 van 7 dagen", dus blijft
    assert per["week"]["netto_eur"] == 10.0
    assert per["jaar"]["netto_eur"] is None and "netto_eur" in per["jaar"]["onvolledig"]
    assert per["jaar"]["opwek_kwh"] == 20.0


def test_intern_blijven_de_sommen_beschikbaar(make_coordinator):
    c, nu = _c(make_coordinator)
    assert c.get_period_overview(nu, ruw=True)["perioden"]["jaar"]["netto_eur"] == 10.0


# --- punt 3 ---------------------------------------------------------------


def test_zelfvoorziening_is_eigen_zon_gedeeld_door_verbruik():
    assert C._zelfvoorziening_uit_zon(20.0, 8.0, 10.0) == 100.0
    assert C._zelfvoorziening_uit_zon(2.03, 0.38, 6.77) == 24.4
    assert C._zelfvoorziening_uit_zon(0.0, 0.0, 5.0) == 0.0
    assert C._zelfvoorziening_uit_zon(1.0, 5.0, 5.0) == 0.0   # export boven opwek: geen negatief getal
    assert C._zelfvoorziening_uit_zon(1.0, 0.0, 0.0) is None
    assert C._zelfvoorziening_uit_zon("x", 0.0, 1.0) is None


def test_netimport_voor_de_accu_drukt_het_cijfer_niet(make_coordinator):
    c, nu = _c(make_coordinator)
    for r in c.energy_daily_history:
        r["import_kwh"] = 12.0     # veel netlading om later te verkopen
    week = c.get_self_consumption_overview(nu)["perioden"]["week"]
    assert week["zelfvoorziening_procent"] == 25.0   # 1 kWh zon op 4 kWh verbruik


def test_week_is_overal_zeven_afgesloten_dagen(make_coordinator):
    c, nu = _c(make_coordinator)
    assert c.get_self_consumption_overview(nu)["perioden"]["week"]["dagen"] == 7
    assert c.get_period_overview(nu)["perioden"]["week"]["dagen"] == 7


# --- punt 4 ---------------------------------------------------------------


def test_besparing_met_de_voorraad_als_elke_dag_een_dagregel_heeft(make_coordinator):
    c, nu = _c(make_coordinator, dagen=7, met_prijs=7)
    c.besparing_dagen = [
        {"datum": (nu.date() - timedelta(days=n)).isoformat(), "hoofdgetal_eur": 0.3, "rauw_eur": 0.5}
        for n in range(1, 8)
    ]
    week = c.get_period_overview(nu)["perioden"]["week"]
    assert week["besparing_rauw_eur"] == 3.5
    assert week["besparing_eur"] == 2.1 and week["besparing_met_voorraad"] is True


def test_ontbreekt_een_dagregel_dan_blijft_de_rauwe_som(make_coordinator):
    c, nu = _c(make_coordinator, dagen=7, met_prijs=7)
    c.besparing_dagen = [
        {"datum": (nu.date() - timedelta(days=n)).isoformat(), "hoofdgetal_eur": 0.3}
        for n in range(1, 7)
    ]
    week = c.get_period_overview(nu)["perioden"]["week"]
    assert week["besparing_eur"] == 3.5 and week["besparing_met_voorraad"] is False
