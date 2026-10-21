"""v5.115.0 - inkoop, opbrengst, rendement en marge van de accu uit de eigen
gegevens, en een datacorrectie op netladen.

Gevraagd 21-10: "Kijk vooral nog even naar of het rendabel is om bij te laden
met kleinere prijsverschillen en het accu rendement" en "Op basis van data
dus inkoop/ontlaadt/rendement kosten etc bepalen".
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.energy_management_system import accukosten as A

PKG = Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
ETA_L, ETA_O, SLIJT = 0.92, 0.927, 0.042


def _r(tijd, inhoud, prijs, accu_w=0.0, net_w=0.0, huis_w=300.0, pv_w=0.0, **extra):
    return {"tijd": tijd, "beschikbaar_kwh": inhoud, "prijs_ct": prijs, "accu_w": accu_w,
            "net_w": net_w, "huis_w": huis_w, "pv_w": pv_w, **extra}


def _kwartieren(begin_uur, n):
    for i in range(n):
        m = begin_uur * 60 + i * 15
        yield f"{m // 60:02d}:{m % 60:02d}"


def _netdag(dag="2026-10-20", inkoop=23.0, verkoop=45.0, verwacht=None):
    """2 kWh laden uit het net om 03:00, ontladen om 19:00."""
    regels = [_r("02:45", 0.0, inkoop)]
    inhoud = 0.0
    for t in _kwartieren(3, 4):
        inhoud += 0.5
        regels.append(_r(t, inhoud, inkoop, accu_w=-2400, net_w=2700, laad_waarde_ct=verwacht))
    for t in _kwartieren(4, 59):            # 04:00 - 18:30 stil
        regels.append(_r(t, inhoud, 30.0))
    regels.append(_r("18:45", inhoud, verkoop))
    for t in _kwartieren(19, 4):
        inhoud -= 0.5
        regels.append(_r(t, inhoud, verkoop, accu_w=2000, huis_w=2000))
    return {dag: regels}


def test_netlading_marge_zoals_het_laadbesluit_rekent():
    uit = A.doorreken(_netdag(), ETA_L, ETA_O, SLIJT)
    net = uit["net"]
    assert net["erin_kwh"] == pytest.approx(2 / ETA_L, abs=0.01)
    assert net["inkoop_ct"] == pytest.approx(23.0)
    assert net["opbrengst_ct"] == pytest.approx(45.0)
    # per kWh die erin ging: 45 x rendement - slijtage - 23
    assert net["marge_ct_per_kwh"] == pytest.approx(45 * ETA_L * ETA_O - 4.2 - 23, abs=0.15)
    assert uit["zon"]["erin_kwh"] == 0


def test_kleine_spreiding_is_verlies():
    uit = A.doorreken(_netdag(inkoop=30.0, verkoop=36.0), ETA_L, ETA_O, SLIJT)
    assert uit["net"]["marge_eur"] < 0


def test_herkomst_uit_de_netmeter():
    # laden met 2000 W terwijl het net maar 500 W levert: 25% net, 75% zon
    regels = [_r("12:00", 2.0, 20.0), _r("12:15", 2.5, 20.0, accu_w=-2000, net_w=500, pv_w=2800)]
    uit = A.doorreken({"2026-10-20": regels}, ETA_L, ETA_O, SLIJT)
    assert uit["net"]["erin_kwh"] == pytest.approx(0.125 / ETA_L, abs=0.01)
    assert uit["zon"]["erin_kwh"] == pytest.approx(0.375 / ETA_L, abs=0.01)


def test_rustverbruik_levert_niets_op():
    regels = [_r("12:00", 2.0, 20.0), _r("12:15", 2.5, 20.0, accu_w=-2000, net_w=2300),
              _r("13:00", 2.4, 40.0, accu_w=0, huis_w=0, pv_w=500)]
    uit = A.doorreken({"2026-10-20": regels}, ETA_L, ETA_O, SLIJT)
    assert uit["rust_kwh"] == pytest.approx(0.1, abs=0.01)
    assert uit["net"]["ontladen_kwh"] == 0


def test_gat_begint_opnieuw_zonder_inkoop():
    regels = [_r("01:00", 3.0, 20.0), _r("05:00", 2.0, 40.0, accu_w=2000)]
    uit = A.doorreken({"2026-10-20": regels}, ETA_L, ETA_O, SLIJT)
    assert uit["net"]["ontladen_kwh"] == 0 and uit["nog_in_accu_kwh"]["begin"] == 2.0


def test_eerst_erin_eerst_eruit_begin_telt_niet():
    regels = [_r("02:45", 1.0, 23.0), _r("03:00", 1.5, 23.0, accu_w=-2400, net_w=2700),
              _r("03:15", 0.5, 45.0, accu_w=2000, huis_w=2000)]
    uit = A.doorreken({"2026-10-20": regels}, ETA_L, ETA_O, SLIJT)
    # de eerste kWh (begin, onbekende inkoop) gaat eerst; de netlading zit er nog in
    assert uit["net"]["ontladen_kwh"] == 0
    assert uit["nog_in_accu_kwh"]["net"] == pytest.approx(0.5)


def _maand(verwacht, dagen=6):
    data = {}
    for d in range(dagen):
        data.update(_netdag(f"2026-10-{10 + d:02d}", verwacht=verwacht))
    return data


def test_datacorrectie_als_netladen_tegenvalt():
    realisatie = 45 * ETA_L * ETA_O - 4.2
    uit = A.doorreken(_maand(verwacht=realisatie + 3.0), ETA_L, ETA_O, SLIJT, datetime(2026, 10, 21))
    c = uit["correctie"]
    assert c["dagen"] == 6 and c["kwh"] >= 10
    assert c["eur"] == pytest.approx(0.03, abs=0.002)
    assert uit["net"]["verwacht_ct"] > uit["net"]["gerealiseerd_ct"]


def test_datacorrectie_nooit_negatief_en_begrensd():
    realisatie = 45 * ETA_L * ETA_O - 4.2
    mee = A.doorreken(_maand(verwacht=realisatie - 5), ETA_L, ETA_O, SLIJT, datetime(2026, 10, 21))
    assert mee["correctie"]["eur"] == 0.0
    tegen = A.doorreken(_maand(verwacht=realisatie + 20), ETA_L, ETA_O, SLIJT, datetime(2026, 10, 21))
    assert tegen["correctie"]["eur"] == A.CORRECTIE_MAX_EUR


def test_te_weinig_gemeten_geen_correctie():
    uit = A.doorreken(_maand(verwacht=60.0, dagen=3), ETA_L, ETA_O, SLIJT, datetime(2026, 10, 21))
    assert uit["correctie"]["eur"] == 0.0 and "te weinig" in uit["correctie"]["status"]


def test_oude_dagen_tellen_niet_mee_voor_de_correctie():
    uit = A.doorreken(_maand(verwacht=60.0), ETA_L, ETA_O, SLIJT, datetime(2026, 12, 31))
    assert uit["correctie"]["dagen"] == 0


def test_zonder_laadverwachting_wel_nacalculatie_geen_correctie():
    uit = A.doorreken(_maand(verwacht=None), ETA_L, ETA_O, SLIJT, datetime(2026, 10, 21))
    assert uit["net"]["ontladen_kwh"] > 0 and uit["correctie"]["eur"] == 0.0


def _bron(naam):
    return (PKG / naam).read_text(encoding="utf-8")


def test_coordinator_gebruikt_de_correctie_alleen_bij_netladen():
    bron = _bron("coordinator.py")
    assert bron.count("slijtage_ct = self._laadkosten_ct()") == 2       # laadbesluit en dip
    assert '"slijtage_ct": self._laadkosten_ct(),' in bron               # kwartierplan
    # verkopen blijft op de slijtage alleen
    assert bron.count('slijtage_ct = (self.get_wear_cost_overview() or {}).get("slijtage_ct_per_kwh")') == 4
    assert '"laad_waarde_ct": self._laad_waarde_ct(),' in bron
    assert '"accukosten": _veilig("get_accukosten"' in _bron("diagnostics.py")
    assert '"accukosten": self._coordinator.get_accukosten(),' in _bron("sensor.py")
    assert "_accukosten()" in _bron("www/ems-cockpit.js")


def test_laadwaarde_zonder_correctie_vastgelegd():
    from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C

    c = SimpleNamespace(last_laadbesluit={"laden": True, "waarde_eur": 0.30, "datacorrectie_ct": 1.5})
    assert C._laad_waarde_ct(c) == pytest.approx(31.5)
    c.last_laadbesluit = {"laden": False, "waarde_eur": 0.30}
    assert C._laad_waarde_ct(c) is None
    c.last_laadbesluit = {"laden": True, "waarde_eur": 0.25, "verdringt_zon": True}
    assert C._laad_waarde_ct(c) is None


def test_laadkosten_is_slijtage_plus_correctie():
    from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C

    c = SimpleNamespace(get_wear_cost_overview=lambda: {"slijtage_ct_per_kwh": 4.2},
                        laadcorrectie_ct=lambda: 1.3)
    assert C._laadkosten_ct(c) == pytest.approx(5.5)
    c.get_wear_cost_overview = lambda: {}
    assert C._laadkosten_ct(c) is None
