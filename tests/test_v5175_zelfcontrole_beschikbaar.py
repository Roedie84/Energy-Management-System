"""v5.175.0 punt 2 - de zelfcontrole "Beschikbare energie" vergelijkt gelijk
met gelijk, ook in de ronde waarin de moduletoestand omslaat.

Gemeten 03-11 (analysekaart 15:10):
- 08:18, eerste ronde na de herstart van 08:17 (v5.171.0): intern 0,691
  (moduletoestand nog leeg), spiegel 0,140 (de correctie van 0,551 net aan).
- 12:11, module AB3000 00996 op 20 % = hersteld (v5.172.0): intern 0,720
  (nog met correctie), spiegel 1,267 (correctie net los).
`last_available_kwh` werd gezet vóór `_update_battery_module_health`, de
spiegel daarna. De correctie zelf werd wel losgelaten.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tests._coordinator_bron import coordinator_bron

TZ = timezone(timedelta(hours=1))


def _c(make_coordinator, gemeten):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar"})
    c._read_sensor_float = lambda e, *a, **k: gemeten if e == "sensor.beschikbaar" else None
    c._demp_soc_flapperen = lambda v: v
    c.ondergrens_correctie_kwh = lambda: 0.0
    return c


def _regel(c):
    return next(r for r in c.get_spiegelcontrole() if r["naam"] == "Beschikbare energie")


def test_correctie_gaat_aan_na_de_interne_meting(make_coordinator, hass):
    """08:18: intern zonder correctie gezet, daarna slaat de module aan."""
    c = _c(make_coordinator, 0.6912)
    c.module_leeg_correctie_kwh = lambda: 0.0
    c.last_available_kwh = c._beschikbaar_voor_spiegel("sensor.beschikbaar")
    c.module_leeg_correctie_kwh = lambda: 0.551
    r = _regel(c)
    assert r["oordeel"] == "sluit_aan"
    assert round(r["gemeten"], 3) == round(r["intern"], 3) == 0.691


def test_correctie_gaat_los_na_de_interne_meting(make_coordinator, hass):
    """12:11: intern met correctie gezet, daarna herstelt de module."""
    c = _c(make_coordinator, 1.2672)
    c.module_leeg_correctie_kwh = lambda: 0.547
    c.last_available_kwh = c._beschikbaar_voor_spiegel("sensor.beschikbaar")
    c.module_leeg_correctie_kwh = lambda: 0.0
    r = _regel(c)
    assert r["oordeel"] == "sluit_aan"
    assert round(r["intern"], 3) == round(r["gemeten"], 3) == 0.72


def test_een_echte_afwijking_blijft_zichtbaar(make_coordinator, hass):
    c = _c(make_coordinator, 1.2672)
    c.module_leeg_correctie_kwh = lambda: 0.0
    c._beschikbaar_correctie_bij_meting = 0.0
    c.last_available_kwh = 0.2
    assert _regel(c)["oordeel"] == "loopt_uiteen"


def test_zonder_vastgelegde_correctie_de_huidige(make_coordinator, hass):
    c = _c(make_coordinator, 0.576)
    c.module_leeg_correctie_kwh = lambda: 0.551
    c.last_available_kwh = 0.025
    r = _regel(c)
    assert r["oordeel"] == "sluit_aan" and round(r["gemeten"], 3) == 0.025


def test_na_module_leeg_met_opgegeven_correctie(make_coordinator, hass):
    c = _c(make_coordinator, 1.0)
    c.module_leeg_correctie_kwh = lambda: 0.9
    assert c._na_module_leeg(1.0, 0.25) == 0.75
    assert round(c._na_module_leeg(1.0), 3) == 0.1
    assert c.beschikbaar_correctie_kwh() == 0.9


def _module(c, soc_module):
    c.battery_module_live = [
        {"module": 1, "apparaat_id": "01029", "soc_percent": 40.0},
        {"module": 2, "apparaat_id": "00917", "soc_percent": 40.0},
        {"module": 4, "apparaat_id": "00996", "soc_percent": soc_module},
    ]


def test_correctie_gaat_los_als_de_module_herstelt(make_coordinator, hass):
    c = make_coordinator({})
    c._read_sensor_float = lambda *a, **k: 30.0
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c._read_corrected_battery_power = lambda: 0.0
    c.module_leeg_sprongen = [{"kwh": 0.551, "module": "00996"}]
    nu = datetime(2026, 11, 3, 11, 0, tzinfo=TZ)
    _module(c, 11.0)
    c._volg_module_leeg(nu)
    assert c.module_leeg_correctie_kwh() > 0.3
    _module(c, 19.0)                     # nog niet hersteld (15 + 5)
    c._volg_module_leeg(nu + timedelta(minutes=60))
    assert c.module_leeg_correctie_kwh() > 0.3
    _module(c, 20.0)                     # 12:11: hersteld
    c._volg_module_leeg(nu + timedelta(minutes=71))
    assert c.module_leeg_correctie_kwh() == 0.0


def test_de_ronde_zet_de_meting_opnieuw_na_de_moduletoestand():
    bron = coordinator_bron()
    # v5.186.0 (B16): de moduletoestand staat nu als laatste in de afgeschermde
    # leerstappen (`_leerstappen_voor_besluit`); de meting volgt op die lus.
    assert '("accumodules", lambda: self._update_battery_module_health(now))' in bron
    blok = bron[bron.index("        for naam, stap in self._leerstappen_voor_besluit("):][:800]
    assert "self.last_available_kwh = self._beschikbaar_voor_spiegel(" in blok
    assert "_gemeten_beschikbaar = self._spiegel_beschikbaar(" in bron
