"""v5.175.1 - pendeldemping verwijderd (Ruud 03-11 16:16: "Demping er helemaal uit").

03-11 16:04-16:14 hield het 60-s gemiddelde een echte last minutenlang tegen
(regeldoel -190 W terwijl de meter +988 W importeerde). P1 regeldoel geeft nu
altijd de momentwaarde; de pendeldetectie telt alleen nog, als diagnose.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.energy_management_system.const import PENDEL_LOS_S
from tests._coordinator_bron import coordinator_bron

TZ = timezone(timedelta(hours=1))
T0 = datetime(2026, 11, 3, 16, 0, tzinfo=TZ)
BRON = Path("custom_components/energy_management_system")


def _c(make_coordinator, salderen=True):
    c = make_coordinator({})
    c._is_salderen_active = lambda now=None: salderen
    return c


def _pulsen(n, aan=1800, uit=-900, duur=5):
    reeks = []
    for _ in range(n):
        reeks += [aan] * duur + [uit] * duur
    return reeks


def _voer(c, reeks, start=T0):
    uit = []
    for i, w in enumerate(reeks):
        uit.append(c.p1_regeldoel(w, w, start + timedelta(seconds=i)))
    return uit


def test_regeldoel_is_altijd_de_momentwaarde_ook_bij_pendelen(make_coordinator, hass):
    c = _c(make_coordinator)
    reeks = _pulsen(12)
    uit = _voer(c, reeks)
    assert [u["waarde_w"] for u in uit] == [float(w) for w in reeks]
    p = uit[-1]["pendel"]
    assert p["actief"] is True and p["tekenwissels_60s"] >= 3
    assert "gedempt" not in p and "demping_aan" not in p


def test_lastsprong_tijdens_episode_direct_door(make_coordinator, hass):
    """Het geval van 16:04: pendelen, dan een aanhoudende +988 W import."""
    c = _c(make_coordinator)
    _voer(c, _pulsen(6))
    na = T0 + timedelta(seconds=60)
    uit = _voer(c, [988] * 20, start=na)
    assert all(u["waarde_w"] == 988 for u in uit)
    assert uit[0]["pendel"]["actief"] is True  # telt nog wel


def test_2027_ook_zonder_gemiddelde(make_coordinator, hass):
    from custom_components.energy_management_system.regime2027 import P1_DOEL_2027_W

    c = _c(make_coordinator, salderen=False)
    uit = _voer(c, _pulsen(6))
    assert uit[-1]["waarde_w"] == round(-900 - 0.0 - P1_DOEL_2027_W, 1)


def test_tellen_blijft_als_diagnose(make_coordinator, hass):
    c = _c(make_coordinator)
    uit = _voer(c, [400, 420, 380, 410] * 20)
    assert uit[-1]["pendel"]["actief"] is False
    c = _c(make_coordinator)
    uit = _voer(c, [80, -60, 90, -70, 120, -150] * 20)
    assert uit[-1]["pendel"]["tekenwissels_60s"] == 0
    c = _c(make_coordinator)
    uit = _voer(c, _pulsen(6, aan=500, uit=-300))
    assert uit[-1]["pendel"]["tekenwissels_60s"] == 0
    c = _c(make_coordinator)
    uit = _voer(c, _pulsen(6))
    p = uit[-1]["pendel"]
    assert p["keren_vandaag"] == 1
    for sleutel in ("tekenwissels_60s", "gemiddelde_w", "actief_sinds", "minuten_vandaag", "niet_geteld_accu"):
        assert sleutel in p


def test_episode_eindigt_na_rust(make_coordinator, hass):
    c = _c(make_coordinator)
    _voer(c, _pulsen(6))
    uit = _voer(c, [300] * (PENDEL_LOS_S + 5), start=T0 + timedelta(seconds=60))
    assert uit[-1]["pendel"]["actief"] is False
    assert uit[-1]["waarde_w"] == 300


def test_onbekende_meting_valt_niet_om(make_coordinator, hass):
    c = _c(make_coordinator)
    uit = c.p1_regeldoel(None, None, T0)
    assert uit["waarde_w"] is None
    assert uit["pendel"]["actief"] is False


def test_tijdgewogen_gemiddelde_blijft_voor_de_diagnose():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    m = [(T0, 1000.0), (T0 + timedelta(seconds=10), 0.0)]
    assert C._tijdgewogen_gemiddelde(m, T0, T0 + timedelta(seconds=40)) == 250.0
    assert C._tijdgewogen_gemiddelde([], T0, T0) is None


def test_schakelaar_en_vlag_zijn_weg():
    switch = (BRON / "switch.py").read_text(encoding="utf-8")
    coord = coordinator_bron()
    assert "class P1PendeldempingSwitch" not in switch
    assert "P1PendeldempingSwitch(" not in switch
    assert "self.p1_pendeldemping" not in coord
    assert 'pendel["gedempt"]' not in coord


def test_wees_in_het_register_wordt_opgeruimd(monkeypatch):
    import types

    import homeassistant.helpers as helpers

    from custom_components.energy_management_system import switch

    verwijderd = []

    class Register:
        def async_get_entity_id(self, domein, platform, uid):
            return "switch.p1_pendeldemping" if uid == "abc_p1_pendeldemping" else None

        def async_remove(self, entity_id):
            verwijderd.append(entity_id)

    nep = types.SimpleNamespace(async_get=lambda hass: Register())
    monkeypatch.setattr(helpers, "entity_registry", nep, raising=False)
    switch._ruim_pendeldemping_op(object(), "abc")
    switch._ruim_pendeldemping_op(object(), "xyz")
    assert verwijderd == ["switch.p1_pendeldemping"]


def test_opruimen_breekt_het_opstarten_nooit(monkeypatch):
    import types

    import homeassistant.helpers as helpers

    from custom_components.energy_management_system import switch

    def stuk(hass):
        raise RuntimeError("register niet klaar")

    monkeypatch.setattr(helpers, "entity_registry", types.SimpleNamespace(async_get=stuk), raising=False)
    switch._ruim_pendeldemping_op(object(), "abc")  # geen uitzondering
