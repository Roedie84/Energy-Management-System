"""v5.202.0: het berekende airco-vermogen zichtbaar.

Ruud 09-11: "Waar zie ik nu het berekende airco vermogen?" - akkoord op een
sensor, de airco-tegel in de cockpit en de diagnose.
"""
from pathlib import Path

from custom_components.energy_management_system.const import CONF_AIRCO_CLIMATE_ENTITY
from custom_components.energy_management_system.sensor import AircoVermogenSensor

PAKKET = Path(__file__).parent.parent / "custom_components" / "energy_management_system"


def test_sensor_uit_de_frequentie(make_coordinator, hass):
    c = make_coordinator({CONF_AIRCO_CLIMATE_ENTITY: "climate.woonkamer"})
    hass.states.set("sensor.woonkamer_compressor_frequency", "30.0", {"unit_of_measurement": "Hz"})
    c._airco_bronnen = {"frequentie": "sensor.woonkamer_compressor_frequency"}
    info = c.get_airco_vermogen()
    assert info["bron"] == "compressorfrequentie"
    assert info["vermogen_w"] == round(31.4 * 30 - 238)
    assert info["omrekening_geleerd"] is False
    s = AircoVermogenSensor(c, "e")
    assert s.native_value == info["vermogen_w"]
    assert "vermogen_w" not in s.extra_state_attributes
    assert s._attr_unique_id == "e_airco_vermogen"


def test_zonder_bronnen_geen_waarde(make_coordinator, hass):
    c = make_coordinator({})
    assert c.get_airco_vermogen()["vermogen_w"] is None


def test_cockpit_en_diagnose():
    bron = (PAKKET / "sensor.py").read_text()
    assert 'bronnen["airco_w"] = eigen["airco_vermogen"]' in bron
    assert '"airco_vermogen": _veilig("get_airco_vermogen"' in (PAKKET / "diagnostics.py").read_text()


def test_cockpit_toont_airco_nu():
    """v5.202.1: airco_w werd geladen maar nergens getoond."""
    js = (PAKKET / "www" / "ems-cockpit.js").read_text()
    assert 'this._s("airco_w")' in js


def test_een_airco_tegel():
    """v5.202.2: Airco, Airco-patroon, Airco nu en Klimaat in een tegel."""
    js = (PAKKET / "www" / "ems-cockpit.js").read_text()
    for oud in ('"Airco-patroon"', '"Airco nu"', 'regel("airco", "Klimaat"'):
        assert oud not in js
    assert 'regel("airco", "Airco", regels.join("<br>")' in js


def test_huis_rendert_twee_samengevoegde_tegels(tmp_path):
    """v5.202.2: Airco-tegels en apparaten elk in een tegel, echt gerenderd."""
    import json
    import shutil
    import subprocess

    import pytest

    if shutil.which("node") is None:
        pytest.skip("Node.js niet aanwezig")
    script = tmp_path / "h.js"
    script.write_text(
        """
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
global.HTMLElement = class {}; global.HTMLTemplateElement = class {};
global.window = { customCards: [] };
global.customElements = { define: (n, c) => { if (!global.K) global.K = c; }, get: () => undefined };
global.document = { createElement: () => ({}) };
console.log = (() => { const echt = console.log; return (...a) => { if (String(a[0]).startsWith("{")) echt(...a); }; })();
eval(src);
const o = Object.create(global.K.prototype);
o._hass = { states: {} };
const S = {
  fietsen: { state: "wacht", attributes: {} },
  vaatwasser: { state: "klaar", attributes: {} },
  aircoBesluit: { state: "niets", attributes: { verwachting: { beschikbaar: true, tot_tekst: "morgen 21:30",
    basis: { tekst: "6 dagen gemeten" }, in_reserve_kwh: 2.33, verwacht: true }, dagritme: { patroon_tekst: "werkdag 15:39" } } },
  klimaat: { state: "x", attributes: { verwarmingsadvies: { advies: "airco", airco_eur_per_kwh_warmte: 0.139, gas_eur_per_kwh_warmte: 0.208 } } },
  airco_w: { state: "327", attributes: { frequentie_hz: 18, w_per_hz: 31.4, omrekening_geleerd: false } },
  temp_binnen: { state: "20.9", attributes: {} }, temp_buiten: { state: "8.6", attributes: {} },
};
o._s = (k) => S[k];
const h = o._huis();
console.log(JSON.stringify({ html: h }));
""",
        encoding="utf-8",
    )
    js = PAKKET / "www" / "ems-cockpit.js"
    uit = subprocess.run(["node", str(script), str(js)], capture_output=True, text=True, check=True)
    html = json.loads(uit.stdout.strip().splitlines()[-1])["html"]
    assert html.count('class="rn">Airco<') == 1
    assert html.count('class="rn">Apparaten<') == 1
    for los in (">Fietsladers<", ">Vaatwasser<", ">Klimaat<", ">Airco nu<", ">Airco-patroon<"):
        assert los not in html
    for tekst in ("compressor 18 Hz", "6 dagen gemeten", "werkdag 15:39", "airco goedkoopst", "Fietsladers:", "Vaatwasser:"):
        assert tekst in html, tekst
