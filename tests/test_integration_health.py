"""Integratiegezondheid in vier onderdelen (v2.2.0).

Voorgesteld: een score van 0-100% op basis van API-beschikbaarheid,
updatefrequentie, aantal fouten en dataconsistentie.

De vier onderdelen zijn goed gekozen en alle vier meetbaar. Het
SAMENVOEGEN tot één percentage is dat niet: dat vraagt wegingen die
nergens vandaan komen. Is 90% beschikbaarheid met perfecte consistentie
beter of slechter dan 100% beschikbaarheid met een rekenfout? Elk
antwoord daarop is verzonnen - dezelfde reden waarom de
netkwaliteitsscore eerder is afgevallen.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    HEALTH_STATUS_AANDACHT,
    HEALTH_STATUS_GOED,
    HEALTH_STATUS_SLECHT,
)

NU = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    from custom_components.energy_management_system.const import (
        CONF_PRICE_SENSOR,
    )

    c = make_coordinator({CONF_PRICE_SENSOR: "sensor.prijs"})
    c.last_successful_update = NU.isoformat()
    c.internal_failures = {}
    c.last_consistency_checks = {"bevindingen": []}
    c.is_sensor_genuinely_unavailable = lambda entity_id: False
    return c


def test_a_healthy_integration_reports_good(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    assert c.get_integration_health(NU)["status"] == HEALTH_STATUS_GOED


def test_all_four_components_are_present(make_coordinator, hass):
    """De vier onderdelen uit het voorstel, elk apart beoordeeld."""
    c = _coordinator(make_coordinator, hass)

    namen = [o["naam"] for o in c.get_integration_health(NU)["onderdelen"]]

    assert namen == [
        "Bronnen bereikbaar",
        "Updatefrequentie",
        "Interne fouten",
        "Dataconsistentie",
    ]


def test_the_worst_component_decides(make_coordinator, hass):
    """Een ketting is zo sterk als de zwakste schakel - dat is geen
    aanname maar een definitie."""
    c = _coordinator(make_coordinator, hass)
    c.internal_failures = {"iets": "Onderdeel X is vastgelopen."}

    uitkomst = c.get_integration_health(NU)

    assert uitkomst["status"] == HEALTH_STATUS_SLECHT
    assert uitkomst["bepaald_door"] == "Interne fouten"


def test_a_stalled_tick_lowers_the_status(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c.last_successful_update = (NU - timedelta(minutes=12)).isoformat()

    uitkomst = c.get_integration_health(NU)

    assert uitkomst["status"] == HEALTH_STATUS_AANDACHT
    assert uitkomst["bepaald_door"] == "Updatefrequentie"


def test_no_composite_percentage_is_produced(make_coordinator, hass):
    """Het samenvoegen tot één getal vraagt wegingen die nergens vandaan
    komen. Dat is de kern van deze keuze en hoort niet stilletjes terug
    te sluipen."""
    c = _coordinator(make_coordinator, hass)

    uitkomst = c.get_integration_health(NU)

    assert "score" not in uitkomst
    assert "procent" not in json_sleutels(uitkomst)
    assert "wegingen" in uitkomst["toelichting"]


def json_sleutels(o, pad=""):
    if isinstance(o, dict):
        return " ".join(list(o) + [json_sleutels(v) for v in o.values()])
    if isinstance(o, list):
        return " ".join(json_sleutels(v) for v in o)
    return ""


def test_the_watchdog_runs_on_its_own_clock():
    """Op dezelfde klok meeliften zou betekenen dat hij zwijgt als juist
    die klok het begeeft."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "self._watchdog," in bron
    assert bron.count("async_track_time_interval(") >= 2


def test_the_watchdog_forces_a_round(make_coordinator, hass):
    """Melden is niet herstellen - de zelfcontrole meldt al, deze grijpt
    in."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("async def _watchdog")
    blok = bron[kop : bron.index("\n    def ", kop)]

    assert "await self.async_update()" in blok
