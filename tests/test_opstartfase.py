"""Tijdens het opstarten zichtbaar dat de integratie nog opstart (v5.14.5).

Gevraagd: *"Tevens zou ik graag tijdens het opstarten zien dat onder
Energy Management System is nog aan het opstarten."*

Aanleiding, direct na de installatie van v5.14.4:

    v- · fout 64 · storing 0 · zelfctl 2/2 · bestand AFWIJKEND · config 0/63/0

Een minuut later:

    v5.14.4 · fout 0 · storing 0 · zelfctl 2/2 · bestand ok · config 61/0/2

Het eerste beeld was schijn: de andere integraties - Zendure, SolarEdge,
de P1-meter - waren nog niet geladen, dus hun entiteiten bestonden even
niet en elke controle erop leek kapot. Ik trapte er zelf bijna in.

Dezelfde aanlooptijd die sinds v1.6.6 beschikbaarheidsmeldingen dempt
(STARTUP_GRACE_SECONDS), nu ook zichtbaar: de systeemstatus toont
"Opstarten", het dashboard "Energy Management System is nog aan het
opstarten", en de diagnoseregels tonen "opstarten" in plaats van waarden
die op een storing lijken.
"""
from datetime import timedelta

import pytest


def _net_gestart(c, seconden_geleden):
    from homeassistant.util import dt as dt_util

    c._started_at = dt_util.now() - timedelta(seconds=seconden_geleden)
    return c


def test_direct_na_de_start_is_de_status_opstarten(make_coordinator, hass):
    c = _net_gestart(make_coordinator({}), 30)

    assert c.system_status == "Opstarten"
    assert c.in_opstartfase()


def test_na_de_aanlooptijd_niet_meer(make_coordinator, hass):
    from custom_components.energy_management_system.const import STARTUP_GRACE_SECONDS

    c = _net_gestart(make_coordinator({}), STARTUP_GRACE_SECONDS + 5)

    assert c.system_status != "Opstarten"
    assert not c.in_opstartfase()


def test_de_diagnoseregels_tonen_opstarten(make_coordinator, hass):
    """Niet "fout 64 · bestand AFWIJKEND" - dat was schijn."""
    c = _net_gestart(make_coordinator({}), 30)

    for soort in ("gezondheid", "sturing", "leren"):
        regel = c.diagnose_regel(soort)
        assert regel.startswith("opstarten · nog "), regel
        assert "fout" not in regel


def test_de_opstarttekst_noemt_de_integratie(make_coordinator, hass):
    c = _net_gestart(make_coordinator({}), 30)

    assert "Energy Management System is nog aan het opstarten" in c.opstart_tekst()


def test_na_het_opstarten_geen_opstarttekst(make_coordinator, hass):
    from custom_components.energy_management_system.const import STARTUP_GRACE_SECONDS

    c = _net_gestart(make_coordinator({}), STARTUP_GRACE_SECONDS + 5)

    assert c.opstart_tekst() is None


def test_de_statussensor_toont_een_zandloper(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import SystemStatusSensor

    c = _net_gestart(make_coordinator({}), 30)
    s = SystemStatusSensor(c, "x")

    assert s.native_value == "Opstarten"
    assert s.icon == "mdi:timer-sand"
    assert "opstarten" in s.extra_state_attributes


def test_het_dashboard_toont_het_opstarten():
    """De landingskaart: in plaats van aandachtspunten die schijn zijn."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    for pad in (
        Path(pkg.__file__).parent / "dashboard_template.yaml",
        Path(pkg.__file__).parents[2] / "dashboards" / "energy_management_system_dashboard.yaml",
    ):
        tekst = pad.read_text()
        assert "Energy Management System is nog aan het opstarten" in tekst, pad
        assert "mdi:timer-sand" in tekst, pad
