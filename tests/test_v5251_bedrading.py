"""v5.251.0: elke meting moet ook echt gevoed worden.

Op 23-11 bleken twee metingen sinds hun bouw leeg: reden_afwijkingen
(de nabeschouwing gaf de acties niet door, v5.250.1) en eigen_ingrepen
(`noteer_eigen_ingreep` was getest, maar niets riep hem aan). De
unittests zagen dat niet, want die roepen de functie zelf aan.

Deze toetsen kijken naar de BEDRADING: wordt een functie in de code van
de integratie zelf aangeroepen, niet alleen in een test.
"""
import ast
import io
import re
import tokenize
from datetime import datetime, timezone
from pathlib import Path

import pytest

MAP = Path(__file__).resolve().parents[1] / "custom_components" / "energy_management_system"

# Methodes zonder aanroep in de eigen code die bewust blijven:
# terugroepfuncties van Python/HA (worden van buitenaf aangeroepen) en
# wat bij het besluit over de oude reserve-regels hoort (meetregister 13).
BEWUST = {
    "emit",                      # logging.Handler
    "datagram_received",         # asyncio-protocol
    "error_received",            # asyncio-protocol
    "current_option",            # HA select
    "async_get_options_flow",    # HA config flow
    "async_step_init",           # HA options flow
    "async_step_user",           # HA config flow
    "async_select_option",       # HA select
    "learned_hourly_median_kw",  # maatstaf in de toetsen (v5.74: gemiddelde tegen mediaan)
}


def _code_zonder_tekst(pad: Path) -> str:
    """De broncode zonder commentaar en lange teksten (docstrings), zodat
    een naam in een toelichting niet als aanroep telt."""
    delen = []
    for t in tokenize.generate_tokens(io.StringIO(pad.read_text()).readline):
        if t.type == tokenize.COMMENT:
            continue
        if t.type == tokenize.STRING and len(t.string) >= 60:
            continue
        delen.append(t.string)
    return " ".join(delen)


def _methodes():
    for pad in sorted(MAP.glob("*.py")):
        for knoop in ast.walk(ast.parse(pad.read_text())):
            if isinstance(knoop, ast.ClassDef):
                for f in knoop.body:
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                            and not f.name.startswith("__") \
                            and not any(isinstance(d, ast.Name) and d.id == "property"
                                        for d in f.decorator_list):
                        yield pad.name, f.name


def test_elke_methode_wordt_ergens_gebruikt():
    code = "\n".join(_code_zonder_tekst(p) for p in MAP.glob("*.py"))
    nooit = sorted(
        f"{bestand}:{naam}"
        for bestand, naam in set(_methodes())
        if naam not in BEWUST and len(re.findall(rf"\b{naam}\b", code)) <= 1
    )
    assert not nooit, (
        f"gedefinieerd maar nergens in de integratie gebruikt: {nooit}. "
        "Aansluiten, of weghalen als het niets meer hoort te doen."
    )


def test_elke_bewaakte_meting_heeft_een_aangeroepen_vuller():
    """Bij elke meting uit METING_VERWACHTE_STILTE_DAGEN: de functie die
    `noteer_meting_gevuld(<naam>)` doet, wordt zelf ergens aangeroepen."""
    from custom_components.energy_management_system.const import (
        METING_VERWACHTE_STILTE_DAGEN,
    )

    code = "\n".join(_code_zonder_tekst(p) for p in MAP.glob("*.py"))
    vullers: dict[str, list[str]] = {}
    for pad in MAP.glob("*.py"):
        for knoop in ast.walk(ast.parse(pad.read_text())):
            if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for a in ast.walk(knoop):
                if isinstance(a, ast.Call) and getattr(a.func, "attr", None) == "noteer_meting_gevuld" \
                        and a.args and isinstance(a.args[0], ast.Constant):
                    vullers.setdefault(a.args[0].value, []).append(knoop.name)

    zonder = sorted(set(METING_VERWACHTE_STILTE_DAGEN) - set(vullers))
    assert not zonder, f"bewaakt maar door niets gevuld: {zonder}"
    los = sorted(
        f"{meting} via {f}"
        for meting, functies in vullers.items()
        for f in functies
        if len(re.findall(rf"\b{f}\b", code)) <= 1
    )
    assert not los, f"vulfunctie wordt nergens aangeroepen: {los}"


NU = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_de_handmatige_stand_legt_de_ingreep_vast(make_coordinator, hass):
    c = make_coordinator({})
    c.eigen_ingrepen = []
    c.meting_laatst_gevuld = {}

    async def _niets(*_a, **_k):
        return None

    c._async_apply_manual = _niets
    c._async_apply_operation = _niets
    c.async_set_learning_only = _niets
    c.handmatig_laadvermogen_w = lambda: 2000

    await c.async_set_handmatige_stand("laden", NU)
    assert len(c.eigen_ingrepen) == 1
    assert c.eigen_ingrepen[0]["stand"] == "laden"
    assert "eigen_ingrepen" in c.meting_laatst_gevuld

    await c.async_set_handmatige_stand(None, NU.replace(hour=14))
    assert c.eigen_ingrepen[0].get("geeindigd")
    assert c.eigen_ingrepen[0]["duur_minuten"] == 120


def test_afsluiten_koppelt_de_logopvang_los():
    bron = (MAP / "coordinator.py").read_text()
    blok = bron[bron.index("async def async_unload(self)"):]
    blok = blok[: blok.index("\n    async def ", 10)]
    assert "self._stop_logopvang()" in blok


# --- punt 3: laden bovenin telt als kan_niet --------------------------------

def test_laden_bovenin_met_afbouw_is_kan_niet():
    from custom_components.energy_management_system.opdracht_accu import beoordeel

    # de missers van 23-11: 2,4 kW opgedragen, 1,29 kW gemeten bij 98 %
    assert beoordeel(-2400, -1290, 2, soc=98, ondergrens=10, bovengrens=100) == "kan_niet"
    assert beoordeel(-1950, -1990 + 300, 2, soc=83, ondergrens=10, bovengrens=100) == "gevolgd"
    assert beoordeel(-2000, -1300, 2, soc=85, ondergrens=10, bovengrens=100) == "kan_niet"


def test_onder_de_afbouw_of_zonder_laden_blijft_het_niet_gevolgd():
    from custom_components.energy_management_system.opdracht_accu import beoordeel

    assert beoordeel(-2000, -1000, 2, soc=60, ondergrens=10, bovengrens=100) == "niet_gevolgd"
    assert beoordeel(-2000, 0, 2, soc=90, ondergrens=10, bovengrens=100) == "niet_gevolgd"
    assert beoordeel(-2000, 500, 2, soc=90, ondergrens=10, bovengrens=100) == "niet_gevolgd"
    assert beoordeel(1500, 500, 2, soc=90, ondergrens=10, bovengrens=100) == "niet_gevolgd"


# --- punt 6: jaarafrekening direct verversen --------------------------------

def test_jaarafrekening_ververst_direct_na_een_wijziging(make_coordinator, hass):
    c = make_coordinator({"contract_start_date": "2026-04-01"})
    gestart = []
    c.hass.async_create_background_task = lambda coro, naam: (gestart.append(naam), coro.close())
    c._jaarafrekening_ververst = NU  # net ververst: de uurgrens houdt hem tegen
    c._jaarafrekening_kwartier(NU)
    assert gestart == []

    c.jaarafrekening_direct_verversen(NU)
    assert gestart == ["ems_jaarafrekening"]


def test_tijdens_het_rekenen_komt_er_een_tweede_ronde(make_coordinator, hass):
    c = make_coordinator({"contract_start_date": "2026-04-01"})
    c._jaarafrekening_bezig = True
    c.jaarafrekening_direct_verversen(NU)
    assert c._jaarafrekening_nog_eens is True


def test_opslaan_van_de_instellingen_roept_het_verversen_aan():
    bron = (MAP / "__init__.py").read_text()
    blok = bron[bron.index("async def async_update_options"):]
    blok = blok[: blok.index("\nasync def ", 5)]
    assert "jaarafrekening_direct_verversen()" in blok
