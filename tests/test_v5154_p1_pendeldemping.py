"""v5.154.0 - pendeldemping in P1 regeldoel (akkoord Ruud 31-10).

De accu pendelt tegen apparaten die in pulsen van ~2 kW aan en uit gaan. Bij
minstens 3 tekenwissels per minuut met sprongen > 1 kW krijgt de Zendure het
tijdgewogen gemiddelde van de laatste minuut.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PENDEL_LOS_S

TZ = timezone(timedelta(hours=1))
T0 = datetime(2026, 11, 2, 18, 0, tzinfo=TZ)
SALDEREN = datetime(2026, 11, 2, tzinfo=TZ)


def _c(make_coordinator):
    c = make_coordinator({})
    c._is_salderen_active = lambda now=None: True
    return c


def _voer(c, reeks, start=T0, stap_s=1):
    """reeks: waarden per stap; geeft de laatste uitkomst."""
    uit = None
    for i, w in enumerate(reeks):
        uit = c.p1_regeldoel(w, w, start + timedelta(seconds=i * stap_s))
    return uit


def _pulsen(n, aan=1800, uit=-900, duur=5):
    reeks = []
    for _ in range(n):
        reeks += [aan] * duur + [uit] * duur
    return reeks


def test_rustig_verbruik_blijft_de_momentwaarde(make_coordinator, hass):
    c = _c(make_coordinator)
    uit = _voer(c, [400, 420, 380, 410] * 20)
    assert uit["pendel"]["actief"] is False
    assert uit["waarde_w"] == 410


def test_kleine_schommeling_rond_nul_telt_niet(make_coordinator, hass):
    c = _c(make_coordinator)
    uit = _voer(c, [80, -60, 90, -70, 120, -150] * 20)
    assert uit["pendel"]["tekenwissels_60s"] == 0
    assert uit["pendel"]["actief"] is False


def test_wissels_zonder_grote_sprong_tellen_niet(make_coordinator, hass):
    c = _c(make_coordinator)
    uit = _voer(c, _pulsen(6, aan=500, uit=-300))
    assert uit["pendel"]["tekenwissels_60s"] == 0
    assert uit["waarde_w"] == -300


def test_pendelen_geeft_het_gemiddelde(make_coordinator, hass):
    c = _c(make_coordinator)
    uit = _voer(c, _pulsen(6))
    p = uit["pendel"]
    assert p["tekenwissels_60s"] >= 3
    assert p["actief"] is True and p["gedempt"] is True
    # 5 s 1800 W en 5 s -900 W: gemiddeld ~450 W, niet de momentwaarde -900.
    assert 300 < uit["waarde_w"] < 600
    assert p["keren_vandaag"] == 1


def test_schakelaar_uit_alleen_tellen(make_coordinator, hass):
    c = _c(make_coordinator)
    c.p1_pendeldemping = False
    uit = _voer(c, _pulsen(6))
    assert uit["pendel"]["actief"] is True
    assert uit["pendel"]["gedempt"] is False
    assert uit["waarde_w"] == -900


def test_na_rust_weer_de_momentwaarde(make_coordinator, hass):
    c = _c(make_coordinator)
    reeks = _pulsen(6)
    _voer(c, reeks)
    na = T0 + timedelta(seconds=len(reeks))
    uit = _voer(c, [300] * (PENDEL_LOS_S + 5), start=na)
    assert uit["pendel"]["actief"] is False
    assert uit["waarde_w"] == 300


def test_blijft_gedempt_kort_na_de_laatste_wissel(make_coordinator, hass):
    c = _c(make_coordinator)
    reeks = _pulsen(6)
    _voer(c, reeks)
    na = T0 + timedelta(seconds=len(reeks))
    uit = _voer(c, [300] * 30, start=na)
    assert uit["pendel"]["actief"] is True
    assert uit["pendel"]["gedempt"] is True


def test_2027_dempt_voor_de_verschuiving(make_coordinator, hass):
    from custom_components.energy_management_system.regime2027 import P1_DOEL_2027_W

    c = make_coordinator({})
    c._is_salderen_active = lambda now=None: False
    uit = _voer(c, _pulsen(6))
    gem = uit["pendel"]["gemiddelde_w"]
    assert uit["waarde_w"] == round(gem - 0.0 - P1_DOEL_2027_W, 1)


def test_tijdgewogen_gemiddelde():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    m = [(T0, 1000.0), (T0 + timedelta(seconds=10), 0.0)]
    assert C._tijdgewogen_gemiddelde(m, T0, T0 + timedelta(seconds=40)) == 250.0
    assert C._tijdgewogen_gemiddelde([], T0, T0) is None


def test_onbekende_meting_valt_niet_om(make_coordinator, hass):
    c = _c(make_coordinator)
    uit = c.p1_regeldoel(None, None, T0)
    assert uit["waarde_w"] is None
    assert uit["pendel"]["actief"] is False


def test_schakelaar_bestaat():
    bron = open("custom_components/energy_management_system/switch.py", encoding="utf-8").read()
    assert "P1PendeldempingSwitch(coordinator, entry_id=entry.entry_id)" in bron
