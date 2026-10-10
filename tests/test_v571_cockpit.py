"""v5.71 - de energiecockpit (kaart, strategie en de sensor Dashboardbronnen)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.cockpit_bronnen import (
    EXTERNE_BRONNEN,
    eigen_entiteiten,
    externe_bronnen,
)
from custom_components.energy_management_system.const import (
    CONF_BATTERY_MODULE_SOC_SENSORS,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_INVERT_BATTERY_POWER_SIGN,
    CONF_SOC_SENSOR,
)

PAKKET = Path(pkg.__file__).parent
SCRIPT = PAKKET / "www" / "ems-cockpit.js"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


# --- de bronnen -------------------------------------------------------------


def test_externe_bronnen_onder_de_namen_van_de_kaart():
    uit = externe_bronnen(
        {
            CONF_SOC_SENSOR: "sensor.soc",
            CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1",
            CONF_BATTERY_MODULE_SOC_SENSORS: ["sensor.m1", "sensor.m2", 3],
            CONF_INVERT_BATTERY_POWER_SIGN: True,
        }
    )
    assert uit["soc"] == "sensor.soc"
    assert uit["net"] == "sensor.p1"
    assert uit["modules_soc"] == ["sensor.m1", "sensor.m2"]
    assert uit["accu_omkeren"] is True
    assert "pv" not in uit  # niet ingesteld = niet meegeven


def test_lege_configuratie_geeft_alleen_de_tekenvlag():
    assert externe_bronnen({}) == {"accu_omkeren": False}


def test_eigen_entiteiten_op_hun_vaste_sleutel():
    uit = eigen_entiteiten(
        "ABC",
        [
            ("ABC_kwartierplanning_tabel", "sensor.woonkamer_ems_kwartierplanning"),
            ("ABC_nu_laden", "switch.ems_nu_laden"),
            ("XYZ_vreemd", "sensor.andere_integratie"),
            (None, "sensor.zonder_id"),
        ],
    )
    assert uit == {
        "kwartierplanning_tabel": "sensor.woonkamer_ems_kwartierplanning",
        "nu_laden": "switch.ems_nu_laden",
    }


def test_de_kaart_kent_elke_externe_bron():
    """Elke bron die de sensor levert, kent de kaart (prijs en water onder
    een alias, omdat die namen ook eigen sleutels zijn)."""
    script = _script()
    for sleutel in EXTERNE_BRONNEN:
        assert f'"{sleutel}"' in script, sleutel


def test_elke_eigen_sleutel_van_de_kaart_bestaat_in_de_integratie():
    """De kaart zoekt eigen entiteiten op hun unique_id-sleutel. Bestaat die
    sleutel niet (meer), dan blijft een paneel stil leeg."""
    script = _script()
    blok = script[script.index("const EIGEN = {"): script.index("};", script.index("const EIGEN = {"))]
    sleutels = re.findall(r':\s*"([a-z0-9_]+)"', blok)
    assert len(sleutels) >= 40
    bron = "\n".join(
        (PAKKET / naam).read_text(encoding="utf-8") for naam in ("sensor.py", "switch.py", "const.py")
    )
    # De twee handmatige standen staan als f"{entry_id}_handmatig_{stand}"
    bron += "\nhandmatig_laden handmatig_smart_charge"
    # En de drie diagnosesensoren als f"diagnose_{soort}"
    bron += "\ndiagnose_gezondheid diagnose_sturing diagnose_leren"
    ontbreekt = [s for s in sleutels if f'"{s}"' not in bron and f"_{s}\"" not in bron and s not in bron]
    assert not ontbreekt, ontbreekt


# --- het script -------------------------------------------------------------


def test_alleen_ascii():
    """Zoals StormchaseNL: een editor met de verkeerde codering verminkt
    anders de tekens en dan registreert de module niets meer."""
    script = _script()
    assert all(ord(c) < 128 for c in script)


def test_registreert_kaart_en_strategie():
    script = _script()
    assert 'const KAART = "ems-cockpit-card"' in script
    assert 'registreer("ll-strategy-dashboard-ems"' in script
    assert 'registreer("ll-strategy-view-ems"' in script


def test_geen_externe_bestanden_of_hacs_kaarten():
    script = _script()
    assert not re.search(r"https?://", script)
    for kaart in ("mushroom", "apexcharts", "card-mod", "button-card"):
        assert kaart not in script


def test_schakelt_alleen_eigen_schakelaars():
    script = _script()
    assert 'callService("switch", aan ? "turn_off" : "turn_on"' in script
    assert "window.confirm(" in script  # standen die de sturing overnemen


def test_accuvermogen_zoals_het_ems_rekent():
    """Na correctie negatief = laden, positief = ontladen
    (`_read_corrected_battery_power`)."""
    assert "return this._omkeren ? -v : v;" in _script()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js niet aanwezig")
def test_het_script_is_geldige_javascript():
    uit = subprocess.run(["node", "--check", str(SCRIPT)], capture_output=True, text=True)
    assert uit.returncode == 0, uit.stderr


# --- registratie --------------------------------------------------------------


def test_de_integratie_serveert_het_script():
    from custom_components.energy_management_system.cockpit_frontend import (
        COCKPIT_FILE,
        COCKPIT_URL,
    )

    assert (PAKKET / "www" / COCKPIT_FILE).is_file()
    assert COCKPIT_URL == "/energy_management_system/ems-cockpit.js"
    init = (PAKKET / "__init__.py").read_text(encoding="utf-8")
    assert "async_registreer_cockpit" in init


def test_overzicht_heeft_een_tegel_naar_de_cockpit():
    tekst = (PAKKET / "dashboard_template.yaml").read_text(encoding="utf-8")
    assert "navigation_path: /ems-cockpit" in tekst
    assert "sensor.woonkamer_energy_management_system_dashboardbronnen" in tekst


# --- v5.71.1: niet verspringen tijdens scrollen ------------------------------


def test_panelen_vergelijken_met_de_vorige_opbouw():
    """Vergelijken met innerHTML is altijd 'anders' (de browser schrijft het
    anders terug), dus dan werd elk paneel bij elke update vervangen."""
    script = _script()
    assert "el.innerHTML !== html" not in script
    assert "if (this._html[paneel] === html) continue;" in script


def test_tekenen_wacht_tot_het_scrollen_klaar_is():
    script = _script()
    assert "const scrolltNog = () =>" in script
    assert "if (scrolltNog()) {" in script
    for gebeurtenis in ("scroll", "touchstart", "touchmove", "touchend", "touchcancel", "wheel"):
        assert f'window.addEventListener("{gebeurtenis}"' in script
