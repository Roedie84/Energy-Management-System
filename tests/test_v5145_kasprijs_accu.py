"""v5.145.0 - de kasprijs van de stroom in de accu.

Gevraagd 29-10: "Kun je ook bijhouden wat de gemiddelde prijs van de stroom
in de accu is? Stel 8 kWh van net = 30 cent, resterend kWh is zonne-energie
= 0 cent." Netinkoop telt tegen de kwartierprijs, zon gratis, gedeeld door
wat er werkelijk in de accu kwam (laadverlies inbegrepen). Alleen
rapportage; de kostprijs voor de sturing blijft ongewijzigd.
"""
import pytest


def test_voorbeeld_van_ruud(make_coordinator, hass):
    """8 kWh van het net à 30 ct en 2 kWh zon, 80 % laadrendement: er komt
    8 kWh in de accu, betaald € 2,40 -> 30 ct per kWh in de accu."""
    c = make_coordinator({})
    c.battery_cash_basis_eur_per_kwh = None
    c.battery_cost_basis_eur_per_kwh = None

    c._werk_kasprijs_bij(8 * 0.30, 8.0, available_kwh=8.0)

    assert c.battery_cash_basis_eur_per_kwh == pytest.approx(0.30)


def test_zon_alleen_is_gratis(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_cash_basis_eur_per_kwh = None
    c.battery_cost_basis_eur_per_kwh = None

    c._werk_kasprijs_bij(0.0, 3.0, available_kwh=3.0)

    assert c.battery_cash_basis_eur_per_kwh == 0.0


def test_gewogen_met_wat_er_al_in_zat(make_coordinator, hass):
    """4 kWh à 30 ct in de accu, daarna 4 kWh zon erbij -> 15 ct."""
    c = make_coordinator({})
    c.battery_cash_basis_eur_per_kwh = 0.30

    c._werk_kasprijs_bij(0.0, 4.0, available_kwh=8.0)

    assert c.battery_cash_basis_eur_per_kwh == pytest.approx(0.15)


def test_niets_opgeslagen_verandert_niets(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_cash_basis_eur_per_kwh = 0.25

    c._werk_kasprijs_bij(1.0, 0.0, available_kwh=5.0)

    assert c.battery_cash_basis_eur_per_kwh == 0.25


def test_overleeft_een_herstart():
    """Ruud: een herstart mag geen parameters kwijtraken."""
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    assert "battery_cash_basis_eur_per_kwh" in PERSISTED_FIELDS


def test_de_cockpit_toont_hem_in_de_accutegel():
    from pathlib import Path

    js = (
        Path(__file__).resolve().parent.parent
        / "custom_components/energy_management_system/www/ems-cockpit.js"
    ).read_text()
    assert 'accuprijs: "battery_savings"' in js
    assert "kasprijs_eur_per_kwh" in js
    assert "this._accuPrijsRegel()" in js


def test_eerste_keer_begint_bij_de_kostprijs(make_coordinator, hass):
    """Na de update is onbekend wat de stroom die er al in zat kostte; dan
    telt die tegen de kostprijs, en elke lading weegt daarna mee."""
    c = make_coordinator({})
    c.battery_cash_basis_eur_per_kwh = None
    c.battery_cost_basis_eur_per_kwh = 0.40

    c._werk_kasprijs_bij(0.0, 2.0, available_kwh=8.0)

    assert c.battery_cash_basis_eur_per_kwh == pytest.approx(0.40 * 6 / 8)
