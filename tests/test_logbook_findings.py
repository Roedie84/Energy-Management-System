"""Vondsten uit het logboek van Home Assistant (v2.0.5).

Gevraagd: "Logboek controle?" - en toen vijf meldingen gedeeld. Vier
daarvan waren echte fouten die geen enkele test ving.

Het patroon is telkens hetzelfde: de testomgeving is milder dan Home
Assistant zelf. Een nabootsing met de verkeerde handtekening, een
attribuutfunctie die nooit werd aangeroepen, een YAML-lader die dubbele
sleutels slikt.
"""
import inspect
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import CONF_PRICE_SENSOR
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as Coordinator,
)

PAKKET = Path(pkg.__file__).parent


def test_the_health_overview_can_be_computed(make_coordinator, hass):
    """Gemeld: "Kon gezondheid niet berekenen (...) missing 1 required
    positional argument: 'entity_id'" - 27 keer in dertien minuten.

    De gezondheidssensor was sinds zijn invoering stuk. Dat viel niet op
    omdat het attributenblok elke sleutel apart afvangt (v1.16.x): de
    rest van de tegels bleef werken en er stond alleen dit ene attribuut
    niet.
    """
    c = make_coordinator({CONF_PRICE_SENSOR: "sensor.prijs"})

    uitkomst = c.get_integration_health()

    assert uitkomst["onderdelen"]


def test_every_sensor_attribute_can_actually_be_produced(
    make_coordinator, hass
):
    """De brede versie: elke functie in het attributenblok wordt echt
    aangeroepen.

    Zonder deze toets komt zo'n fout pas boven water als je de
    diagnostiek regel voor regel leest, want de foutafvanging zorgt dat
    de sensor blijft werken met één attribuut minder.
    """
    import re

    bron = (PAKKET / "sensor.py").read_text()
    c = make_coordinator({CONF_PRICE_SENSOR: "sensor.prijs"})

    aangeroepen = set(re.findall(r'\(\s*"[a-z_]+",\s*self\._coordinator\.(\w+)', bron))
    assert aangeroepen, "geen attribuutfuncties gevonden"

    mislukt = []
    for naam in sorted(aangeroepen):
        functie = getattr(c, naam, None)
        if functie is None:
            mislukt.append(f"{naam}: bestaat niet")
            continue
        try:
            functie()
        except TypeError as fout:
            mislukt.append(f"{naam}: {fout}")

    assert not mislukt, mislukt


def test_no_task_is_created_from_a_thread(make_coordinator, hass):
    """Gemeld: "calls hass.async_create_task from a thread other than the
    event loop, which may cause Home Assistant to crash or data to
    corrupt."

    En de gevolgmelding uit hetzelfde logboek: "coroutine 'async_update'
    was never awaited" - de coroutine werd wél aangemaakt maar nooit
    uitgevoerd.
    """
    import re

    bron = (PAKKET / "coordinator.py").read_text()

    for naam in ("_handle_interval", "_handle_state_change"):
        kop = bron.index(f"    def {naam}(")
        # Tot de volgende definitie, met of zonder decorator ervoor.
        volgende = min(
            x
            for x in (
                bron.find("\n    def ", kop + 10),
                bron.find("\n    @", kop + 10),
                bron.find("\n    async def ", kop + 10),
            )
            if x > 0
        )
        blok = bron[kop:volgende]
        # Commentaar en toelichting eruit: die noemen de fout bij naam.
        zonder_uitleg = re.sub(r'"""..*?"""', "", blok, flags=re.S)
        code = "\n".join(
            r.split("#")[0] for r in zonder_uitleg.splitlines()
        )

        assert "async_create_task" not in code, naam
        assert "add_job" in code, naam


def test_test_doubles_match_the_real_signature():
    """De diepere oorzaak van de gezondheidsfout: de testopstelling
    bootste `is_sensor_genuinely_unavailable` na met één argument,
    terwijl de echte functie er twee wil. Daardoor bleef de fout in de
    tests onzichtbaar.

    Deze toets vergelijkt de nabootsingen in de testbestanden met de
    echte handtekening.
    """
    import re

    tests = Path(__file__).resolve().parent
    fouten = []

    for pad in sorted(tests.glob("test_*.py")):
        for regel in pad.read_text().splitlines():
            m = re.search(
                r"\.(\w+)\s*=\s*lambda\s*([^:]*):", regel
            )
            if not m:
                continue
            naam, parameters = m.group(1), m.group(2)
            echt = getattr(Coordinator, naam, None)
            if echt is None or not callable(echt):
                continue
            if isinstance(
                inspect.getattr_static(Coordinator, naam), property
            ):
                continue

            verwacht = [
                p
                for p in inspect.signature(echt).parameters.values()
                if p.name != "self"
                and p.default is inspect.Parameter.empty
                and p.kind
                in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
            gegeven = [
                p.strip()
                for p in parameters.split(",")
                if p.strip() and not p.strip().startswith(("*", "**"))
            ]
            heeft_ster = "*" in parameters
            if heeft_ster:
                continue
            if len(gegeven) < len(verwacht):
                fouten.append(
                    f"{pad.name}: {naam} nagebootst met {len(gegeven)} "
                    f"argument(en), echt zijn er {len(verwacht)}"
                )

    assert not fouten, fouten


def test_no_blocking_file_access_outside_the_executor():
    """Gemeld uit het logboek:

        Detected blocking call to read_text (...) inside the event loop
        by custom integration 'energy_management_system'

    Een bestand lezen duurt milliseconden, maar in de event loop staat in
    die tijd ALLES stil - elke andere integratie, elke automatisering.
    Home Assistant verbiedt dat daarom.

    Het viel op bij het downloaden van de diagnostiek. Deze toets weert
    bestandstoegang buiten een `async_add_executor_job`.
    """
    import re

    overtredingen = []
    for bestand in (
        "coordinator.py",
        "sensor.py",
        "switch.py",
        "diagnostics.py",
        "__init__.py",
    ):
        pad = PAKKET / bestand
        if not pad.exists():
            continue
        regels = pad.read_text().splitlines()
        for nummer, regel in enumerate(regels, 1):
            code = regel.split("#")[0]
            if not re.search(r"\.(read_text|write_text|read_bytes)\(", code):
                continue

            # Toegestaan binnen een hulpfunctie die aan een executor
            # wordt meegegeven. Die herkennen we aan de dichtstbijzijnde
            # `def` erboven én een `async_add_executor_job` eronder.
            omgeving = "\n".join(regels[max(0, nummer - 12) : nummer + 12])
            if "async_add_executor_job" in omgeving:
                continue
            overtredingen.append(f"{bestand}:{nummer}: {code.strip()}")

    assert not overtredingen, overtredingen


def test_the_dashboard_template_is_read_once_at_startup():
    """Het sjabloon verandert alleen bij een update, dus het hoeft maar
    één keer gelezen te worden."""
    bron = (PAKKET / "coordinator.py").read_text()

    assert "async_load_dashboard_template" in bron
    assert "_dashboard_template_cache" in bron

    kop = bron.index("    async def async_setup(self) -> None:")
    blok = bron[kop : bron.index("\n    async def ", kop + 40)]
    assert "async_load_dashboard_template()" in blok


def test_a_swallowed_startup_error_becomes_visible():
    """v2.2.4: de try/except rond het inlezen ving drie dagen lang een
    NameError op zonder dat er iets van te zien was.

    De geschiedenis vulde zich niet, de inleesmelding bleef leeg, en er
    stond geen fout in de diagnostiek. Alleen het logboek wist ervan, en
    dat zit niet in de export - dus kostte het drie diagnostieken en twee
    versies om erachter te komen.

    Opvangen blijft goed; het opstarten mag hier niet op stuklopen. Maar
    zwijgen niet.
    """
    bron = (PAKKET / "coordinator.py").read_text()
    kop = bron.index("await self.async_bootstrap_energy_history()")
    blok = bron[kop : kop + 1200]

    assert "internal_failures" in blok
    assert "energy_history_bootstrap_note" in blok


def test_every_startup_step_that_is_caught_reports_itself():
    """De brede versie: een opstartstap die wordt afgevangen, hoort de
    fout ergens achter te laten waar hij in de diagnostiek terechtkomt."""
    import re

    bron = (PAKKET / "coordinator.py").read_text()
    kop = bron.index("    async def async_setup(self) -> None:")
    blok = bron[kop : bron.index("\n    async def ", kop + 40)]

    for m in re.finditer(r"except Exception[^\n]*:\n((?:\s{12}[^\n]*\n)+)", blok):
        afhandeling = m.group(1)
        assert (
            "internal_failures" in afhandeling
            or "_note" in afhandeling
            or "raise" in afhandeling
        ), f"stille afvanging in async_setup: {afhandeling.strip()[:80]}"
