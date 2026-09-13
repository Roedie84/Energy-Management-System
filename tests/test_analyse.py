"""De analyse bovenaan de export (v3.62.0).

Gevraagd: "Uit de diagnostiek dient uiteraard ook een analyse voor jou
te komen zodat ik de data ook aan jou kan aanbieden."

Terecht, en het zou op 28 augustus vier keer geholpen hebben. Bij het
nalopen van de exports is vier keer een ONTBREKENDE sleutel als `null`
gelezen - `wear_cost` in plaats van `wear_cost_overview`,
`hourly_consumption_profile` dat alleen in de momentopname staat - en
elke keer volgde er een verkeerde diagnose uit:

- "de slijtageberekening werkt niet"      (werkte wel)
- "het uurprofiel is leeg"                (stond op 24 uren)
- "de dagteller is stuk"                  (stond op 1)
- "last_plan_shortfall wordt niet gezet"  (stond gevuld)

Dit blok verzamelt de oordelen die er al zijn, op een plek en bovenaan.
Het verzint niets nieuws: elke regel komt uit een controle die zichzelf
al uitspreekt.
"""
import pytest


def test_a_healthy_system_says_so(make_coordinator, hass):
    c = make_coordinator({})

    analyse = c.get_analyse()

    assert analyse["aantal_fouten"] == 0
    assert analyse["samenvatting"] == "Geen bijzonderheden."


def test_an_internal_failure_is_listed(make_coordinator, hass):
    """De storing van 26 augustus: vijf onderdelen tegelijk."""
    c = make_coordinator({})
    c.internal_failures = {"ronde:accukoeling": "viel om in de laatste ronde"}

    analyse = c.get_analyse()

    assert analyse["aantal_fouten"] == 1
    assert "accukoeling" in analyse["punten"][0]["wat"]


def test_an_unreachable_battery_is_listed(make_coordinator, hass):
    """De storing van 28 augustus: de Zendure zonder verbinding."""
    c = make_coordinator({})
    c.aansturing_onbereikbaar = {
        "reden": "select.zendure_manager_operation is unavailable",
        "sinds": "2026-08-28T10:00:00",
    }

    analyse = c.get_analyse()

    assert analyse["aantal_fouten"] == 1
    assert "unavailable" in analyse["punten"][0]["wat"]


def test_a_drifting_field_is_listed(make_coordinator, hass):
    """Het geval van 27 augustus: 38% tegenover 6%."""
    from custom_components.energy_management_system.const import (
        CONF_SOC_SENSOR,
    )

    c = make_coordinator({CONF_SOC_SENSOR: "sensor.soc"})
    hass.states.set("sensor.soc", "6.0")
    c.last_soc_percent = 38.0

    analyse = c.get_analyse()

    punt = next(p for p in analyse["punten"] if "Spiegel" in p["onderwerp"])
    assert "38" in punt["wat"] and "6" in punt["wat"]


def test_a_missing_entity_is_listed(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_SOC_SENSOR,
    )

    c = make_coordinator({CONF_SOC_SENSOR: "sensor.weg"})

    analyse = c.get_analyse()

    assert any(
        p["onderwerp"] == "Entiteit bestaat niet" for p in analyse["punten"]
    )


def test_a_low_cell_is_listed(make_coordinator, hass):
    """De cel van 28 augustus: 2,71 V terwijl de rest op 3,20 stond."""
    c = make_coordinator({})
    c.battery_module_live = [
        {"module": 1, "cel_min_v": 2.71, "cel_max_v": 3.20},
        {"module": 2, "cel_min_v": 3.21, "cel_max_v": 3.21},
    ]

    analyse = c.get_analyse()

    punt = next(p for p in analyse["punten"] if p["onderwerp"] == "Celspanning")
    assert punt["ernst"] == "fout"


def test_the_spiegel_findings_are_not_listed_twice(make_coordinator, hass):
    """De zelfcontrole draagt ze ook; dubbel melden maakt de lijst

    langer zonder er iets aan toe te voegen.
    """
    from custom_components.energy_management_system.const import (
        CONF_SOC_SENSOR,
    )

    c = make_coordinator({CONF_SOC_SENSOR: "sensor.soc"})
    hass.states.set("sensor.soc", "6.0")
    c.last_soc_percent = 38.0

    spiegels = [
        p for p in c.get_analyse()["punten"] if "Accustand" in p["onderwerp"]
    ]

    assert len(spiegels) == 1


# --- de context ------------------------------------------------------


def test_it_says_what_the_steering_is_doing(make_coordinator, hass):
    """De eerste vraag bij elke export: stuurt hij eigenlijk wel?

    Op 28 augustus stond de leermodus een halve dag aan zonder dat dat
    ergens bovenaan stond.
    """
    c = make_coordinator({})
    c.learning_only = True
    c.last_reason = "default_smart"

    sturing = c.get_analyse()["sturing"]

    assert sturing["leermodus"] is True
    assert sturing["reden"] == "default_smart"


def test_it_says_what_is_in_the_battery(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_SOC_SENSOR,
    )

    c = make_coordinator({CONF_SOC_SENSOR: "sensor.soc"})
    hass.states.set("sensor.soc", "47.0")

    assert c.get_analyse()["accu"]["laadstand_procent"] == 47.0


def test_it_is_the_first_key_in_the_export():
    """Bovenaan, anders wordt het net zo goed overgeslagen als de rest."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()
    # v3.63.0: op ruimte zoeken brak zodra er een sleutel bijkwam - de
    # bestandscontrole duwde `"config"` voorbij de 600 tekens. Zoeken op
    # de VOLGORDE in plaats van op afstand.
    start = bron.index("diagnostics: dict[str, Any] = {")

    assert bron.index('"analyse"', start) < bron.index('"config"', start)
