"""Bevindingen uit doorloop 1 en 2 van de audit (v4.10).

Vier kleinere zaken die geen gedrag veranderen maar wel een risico of
een verspilling waren.
"""
import ast
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent


def test_de_modulelezer_bindt_zijn_lusvariabele(make_coordinator, hass):
    """HOOG uit doorloop 1, coordinator.py:25361.

        for index in range(aantal):
            def lees(lijst):
                if index >= len(lijst):   # niet gebonden

    `lees` leest `index` bij AANROEP, niet bij definitie. Het valt goed
    uit omdat hij binnen dezelfde iteratie wordt gebruikt, maar het is
    fragiel: zodra de aanroep verplaatst of uitgesteld wordt, lezen alle
    modules de laatste index. Dit is de celspanningsuitlezing per
    accumodule - een verkeerde waarde belandt als "module wijkt af" bij
    de leverancier.
    """
    bron = (PAKKET / "coordinator.py").read_text()
    i = bron.index("for index in range(aantal):")
    blok = bron[i : i + 400]

    assert "def lees(lijst, index=index)" in blok, blok[:200]


def test_geen_dubbele_sleutel_in_een_dict(make_coordinator, hass):
    """MIDDEL uit doorloop 1, switch.py:326: `vermogen_w` stond twee keer
    in hetzelfde literal. De tweede overschreef de eerste."""
    for naam in ("switch.py", "sensor.py", "button.py", "coordinator.py"):
        boom = ast.parse((PAKKET / naam).read_text())
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.Dict):
                continue
            sleutels = [
                k.value for k in knoop.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            ]
            dubbel = {s for s in sleutels if sleutels.count(s) > 1}
            assert not dubbel, f"{naam}:{knoop.lineno} {dubbel}"


def test_de_statussensor_roept_de_samenvatting_een_keer_aan():
    """MIDDEL uit doorloop 1, sensor.py:654 en 662: twee keer dezelfde
    aanroep in dezelfde attributenopbouw."""
    bron = (PAKKET / "sensor.py").read_text()
    i = bron.index("class SystemStatusSensor")
    j = bron.index("\nclass ", i + 10)

    assert bron[i:j].count("get_diagnostic_summary()") <= 1


def test_geen_berekening_zonder_lezer(make_coordinator, hass):
    """MIDDEL uit doorloop 1: vier variabelen werden berekend en nooit
    gebruikt - restanten van v4.2, toen de brug stopte met de kaarttabel
    schrijven. Twee overbodige berekeningen per ronde."""
    boom = ast.parse((PAKKET / "coordinator.py").read_text())
    dood = []
    for fn in ast.walk(boom):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        gezet, gelezen = {}, set()
        # Namen uit een tuple-uitpakking tellen niet: `a, b, c = ...` mag
        # een deel weggooien, daar is geen andere vorm voor.
        uitgepakt = {
            el.id
            for n in ast.walk(fn)
            if isinstance(n, (ast.Assign, ast.For))
            for doel in ([n.targets[0]] if isinstance(n, ast.Assign) else [n.target])
            if isinstance(doel, (ast.Tuple, ast.List))
            for el in doel.elts
            if isinstance(el, ast.Name)
        }
        for n in ast.walk(fn):
            if isinstance(n, ast.Name):
                if isinstance(n.ctx, ast.Store):
                    gezet.setdefault(n.id, n.lineno)
                else:
                    gelezen.add(n.id)
        gelezen |= uitgepakt
        for naam, regel in gezet.items():
            if naam.startswith("_") or naam in gelezen:
                continue
            dood.append(f"{fn.name}:{regel} {naam}")
    assert not dood, dood


def test_de_afwijkingsreeks_bewaart_een_maand():
    """LAAG uit doorloop 3: de reeks bewaarde zeven dagen, en voor de
    nauwkeurigheidsanalyse moest ik zes exports samenvoegen om aan
    twintig dagen te komen.

    De LEREN gebeurt nog steeds over zeven dagen - dat venster is
    bewust, want de zonnestanden schuiven met het seizoen. Wat er nu
    langer wordt bewaard is alleen de GESCHIEDENIS, zodat gemiddelde,
    mediaan, p90 en het grootste geval uit één export te halen zijn.
    """
    from custom_components.energy_management_system.const import (
        DEVIATION_HISTORY_DAYS,
        LEARNING_HISTORY_DAYS,
    )

    assert DEVIATION_HISTORY_DAYS >= 30
    assert LEARNING_HISTORY_DAYS == 7

    bron = (PAKKET / "solar_forecast.py").read_text()
    i = bron.index("self.deviation_history = self.deviation_history[")
    assert "DEVIATION_HISTORY_DAYS" in bron[i : i + 120]
    j = bron.index("self.deviation_context = self.deviation_context[")
    assert "DEVIATION_HISTORY_DAYS" in bron[j : j + 120]


def test_het_leervenster_blijft_zeven_dagen(make_coordinator, hass):
    """De reeks is langer, maar wat ermee GELEERD wordt niet - anders
    schuift de biascorrectie mee met seizoenen die niet meer gelden."""
    bron = (PAKKET / "solar_forecast.py").read_text()
    i = bron.index("def _bruikbare_afwijkingen")
    j = bron.index("\n    @property", i)

    # de reeks wordt afgesneden op het leervenster, niet in zijn geheel
    # gebruikt - anders verzesvoudigt het venster stilzwijgend.
    assert "self.deviation_history[-LEARNING_HISTORY_DAYS:]" in bron[i:j]
