"""Een mislukte schrijfactie breekt de ronde niet af (v4.11).

Doorloop 5 van de audit. Vier `hass.services.async_call`-aanroepen staan
buiten een try/except, en dat zijn juist de vier die naar de ACCU
schrijven:

    coordinator.py:3902   _async_set_switch
    coordinator.py:34800  _async_apply_operation
    coordinator.py:35434  _async_apply_manual
    coordinator.py:35443  _async_apply_manual

Werpt de Zendure-integratie daar een fout - cloud weg, entiteit
unavailable, dienst verdwenen - dan klimt die op tot `async_update`. Die
heeft een brede try/except, dus de integratie blijft leven en de fout
komt in het logboek en op `sensor.system_status`. Zo ver is het goed.

Maar de rest van de ronde wordt overgeslagen: geen financiële
boekhouding, geen leerstap, geen moduswisselregel, geen
tekortdetectie. Eén onbereikbare accu betekent dus ook dat die minuut
niet wordt geleerd - en bij een cloudstoring van een uur zijn dat
zestig ontbrekende rondes in de geschiedenis, zonder dat ergens staat
dat ze ontbreken.

De schrijfactie wordt nu apart afgeschermd: de fout wordt vastgelegd
als `opdracht_niet_aangekomen` (die melding bestaat al sinds v1.x), en
de ronde loopt door. De accu staat dan in de oude stand, wat de
veiligste terugval is.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _breek(c, hass):
    async def stuk(*a, **kw):
        raise RuntimeError("Zendure niet bereikbaar")

    hass.services.async_call = stuk


@pytest.mark.asyncio
async def test_een_mislukte_standwijziging_breekt_de_ronde_niet(make_coordinator, hass):
    c = make_coordinator({
        "operation_select_entity": "select.modus",
        "manual_power_number_entity": "number.vermogen",
    })
    hass.states.set("select.modus", "smart")
    _breek(c, hass)

    await c._async_apply_operation("manual")

    assert c.internal_failures.get("accu_aansturing")


@pytest.mark.asyncio
async def test_een_mislukt_handmatig_vermogen_ook_niet(make_coordinator, hass):
    c = make_coordinator({
        "operation_select_entity": "select.modus",
        "manual_power_number_entity": "number.vermogen",
    })
    hass.states.set("select.modus", "smart")
    _breek(c, hass)

    await c._async_apply_manual(-2000)

    assert c.internal_failures.get("accu_aansturing")


@pytest.mark.asyncio
async def test_een_gelukte_opdracht_ruimt_de_fout_op(make_coordinator, hass):
    c = make_coordinator({
        "operation_select_entity": "select.modus",
        "manual_power_number_entity": "number.vermogen",
    })
    hass.states.set("select.modus", "smart")
    c.internal_failures["accu_aansturing"] = "oud"

    await c._async_apply_operation("manual")

    assert "accu_aansturing" not in c.internal_failures


def test_elke_schrijfactie_naar_de_accu_is_afgeschermd():
    """De ratel: geen `async_call` naar de accu buiten een try/except."""
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    boom = ast.parse((Path(pkg.__file__).parent / "coordinator.py").read_text())

    class Zoek(ast.NodeVisitor):
        def __init__(self):
            self.onbeschermd, self.diep = [], 0

        def visit_Try(self, n):
            self.diep += 1
            self.generic_visit(n)
            self.diep -= 1

        def visit_Call(self, n):
            if getattr(n.func, "attr", None) == "async_call" and not self.diep:
                self.onbeschermd.append(n.lineno)
            self.generic_visit(n)

    z = Zoek()
    z.visit(boom)
    assert not z.onbeschermd, z.onbeschermd
