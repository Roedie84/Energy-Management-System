"""v5.167.0 punt 1 - de meetlaag voedt de accu-meetreeks (banden, accukosten).

Live 02-11: `kwartieren_uit_de_meetlaag` = 0, terwijl de meetlaag schreef
(31 dagen kwartierregels, kwaliteit partially_estimated). De sleutels kloppen
(dagverloop 'HH:MM' = begin van het kwartier, inhoud aan zijn eind; meetlaag
'HH:MM' = begin van het kwartier, tellers over dat kwartier). Oorzaak: na een
herstart leest de meetlaag zijn dagen in de achtergrond terug; de eerste
opbouw van de meetreeks viel daarvoor en werd voor het hele uur bewaard. Nu
pas bewaard als het terugladen klaar is, en de energie per kwartier staat ook
in het dagverloop zelf (opgeteld accuvermogen).
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system import kwartierenergie as K
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C
from custom_components.energy_management_system.meetlog import MeetLog
from tests._coordinator_bron import coordinator_bron

TZ = timezone(timedelta(hours=1))
DAG = "2026-11-02"


def _kwartierrecord(start: datetime, uit_kwh: float, in_kwh: float) -> dict:
    """Een meetlaagregel zoals `Meetlaag._kwartiergrens` hem wegschrijft."""
    def st(w, vers=True):
        return {"waarde": w, "vers": vers, "leeftijd_s": 4 if vers else 666}

    begin = {"grid_import": st(100.0), "grid_export": st(50.0), "pv": st(10.0),
             "battery_out": st(20.0, False), "battery_in": st(30.0, False)}
    eind = {"grid_import": st(100.1), "grid_export": st(50.0), "pv": st(10.0),
            "battery_out": st(20.0 + uit_kwh, False), "battery_in": st(30.0 + in_kwh, False)}
    record = K.kwartier(start, begin, eind, 0.25)
    kort = K.compact(record)
    kort["bron"] = "n"
    return kort


def _laag(geladen=True):
    log = MeetLog()
    for i, (uit, erin) in enumerate([(0.0, 0.6), (0.0, 0.6), (0.06, 0.0), (0.06, 0.0)]):
        start = datetime(2026, 11, 2, 10, 0, tzinfo=TZ) + timedelta(minutes=15 * i)
        log.voeg_toe("kwartier", start, _kwartierrecord(start, uit, erin))
    return SimpleNamespace(log=log, _laden_klaar=geladen)


def _dagverloop():
    inhoud = [5.0, 5.5, 6.0, 5.9, 5.9]   # 09:45 (eind 10:00) ... 10:45 (eind 11:00)
    return {DAG: [{"tijd": t, "beschikbaar_kwh": v, "accu_w": w, "soc": 50}
                  for t, v, w in zip(["09:45", "10:00", "10:15", "10:30", "10:45"], inhoud,
                                     [0.0, -2400.0, -2400.0, 240.0, 240.0])]}


def test_gemeten_kwartieren_met_de_echte_sleutels():
    c = SimpleNamespace(_meetlaag=_laag())
    gemeten = C._gemeten_kwartieren(c, DAG)
    assert sorted(gemeten) == ["10:00", "10:15", "10:30", "10:45"]
    assert gemeten["10:00"]["accu_in_kwh"] == pytest.approx(0.6)
    assert gemeten["10:30"]["accu_uit_kwh"] == pytest.approx(0.06)
    assert gemeten["10:00"]["accu_kwh"] == pytest.approx(-0.6)


def test_kwartierreeks_gebruikt_de_meetlaag_uitgelijnd():
    gemeten = {DAG: C._gemeten_kwartieren(SimpleNamespace(_meetlaag=_laag()), DAG)}
    reeks = A.kwartierreeks(_dagverloop(), gemeten)
    assert [q["bron"] for q in reeks] == ["meetlaag"] * 4
    # kwartier 10:00: inhoud 5,0 -> 5,5 en 0,6 kWh erin (begin- en eindsleutel gelijk)
    assert reeks[0]["tijd"] == "10:00" and reeks[0]["delta_kwh"] == pytest.approx(0.5)
    assert reeks[0]["in_kwh"] == pytest.approx(0.6) and reeks[0]["uit_kwh"] == 0.0
    assert reeks[2]["accu_kwh"] == pytest.approx(0.06)


def _coord(laag):
    c = SimpleNamespace(_meetlaag=laag, dagverloop=_dagverloop())
    c._gemeten_kwartieren = lambda d: C._gemeten_kwartieren(c, d)
    return c


def test_meetreeks_niet_een_uur_leeg_bewaard_tijdens_het_terugladen():
    laag = _laag(geladen=False)
    echte_log, laag.log = laag.log, MeetLog()      # nog niets teruggelezen
    c = _coord(laag)
    nu = datetime(2026, 11, 2, 22, 4, tzinfo=TZ)
    eerst = C._accu_meetreeks(c, nu)
    assert all(q["bron"] == "vermogen" for q in eerst)
    # terugladen klaar, dezelfde minuut en hetzelfde uur: nu wel uit de meetlaag
    laag.log, laag._laden_klaar = echte_log, True
    daarna = C._accu_meetreeks(c, nu + timedelta(minutes=1))
    assert [q["bron"] for q in daarna] == ["meetlaag"] * 4
    # en vanaf dan per uur bewaard
    assert C._accu_meetreeks(c, nu + timedelta(minutes=20)) is daarna


def test_eigen_kwartiermeting_gaat_voor_de_meetlaag():
    verloop = _dagverloop()
    verloop[DAG][1].update(accu_in_kwh=0.61, accu_uit_kwh=0.0, accu_dekking=0.97)
    verloop[DAG][2].update(accu_in_kwh=0.61, accu_uit_kwh=0.0, accu_dekking=0.5)   # te weinig gedekt
    gemeten = {DAG: C._gemeten_kwartieren(SimpleNamespace(_meetlaag=_laag()), DAG)}
    reeks = A.kwartierreeks(verloop, gemeten)
    assert [q["bron"] for q in reeks] == ["kwartiermeting", "meetlaag", "meetlaag", "meetlaag"]
    assert reeks[0]["in_kwh"] == pytest.approx(0.61)


def test_kwartiermeting_telt_het_accuvermogen_op():
    """Elke minuut een ronde met -2400 W (laden): 0,6 kWh erin per kwartier."""
    c = SimpleNamespace(ACCU_KWARTIER_MAX_STAP_S=C.ACCU_KWARTIER_MAX_STAP_S,
                        _accu_kwartier_tel=C._accu_kwartier_tel)
    w = {"v": -2400.0}
    c._read_corrected_battery_power = lambda: w["v"]
    begin = datetime(2026, 11, 2, 10, 0, 20, tzinfo=TZ)
    uit = {}
    for i in range(30):
        nu = begin + timedelta(minutes=i)
        kwartier = nu.replace(minute=nu.minute // 15 * 15, second=0)
        if nu.minute >= 15:
            w["v"] = 240.0       # tweede kwartier: ontladen
        uit[kwartier.strftime("%H:%M")] = C._accu_kwartiermeting(c, nu, kwartier)
    # eerste kwartier: van 10:00:20 tot 10:14:20 gemeten, opgeschaald
    assert uit["10:00"]["accu_in_kwh"] == pytest.approx(0.6, abs=0.01)
    assert uit["10:00"]["accu_uit_kwh"] == 0.0
    assert uit["10:00"]["accu_dekking"] >= 0.9
    # tweede kwartier: de eerste 20 s nog met -2400 W (vorige ronde), daarna 240 W
    assert uit["10:15"]["accu_uit_kwh"] == pytest.approx(0.06 * (860 - 20) / 900 * 900 / 860, abs=0.01)
    assert uit["10:15"]["accu_in_kwh"] == pytest.approx(2.4 * 20 / 3600 * 900 / 860, abs=0.003)


def test_kwartiermeting_slaat_een_lange_pauze_over():
    c = SimpleNamespace(ACCU_KWARTIER_MAX_STAP_S=C.ACCU_KWARTIER_MAX_STAP_S,
                        _accu_kwartier_tel=C._accu_kwartier_tel,
                        _read_corrected_battery_power=lambda: 1000.0)
    k = datetime(2026, 11, 2, 10, 0, tzinfo=TZ)
    C._accu_kwartiermeting(c, k + timedelta(seconds=10), k)
    uit = C._accu_kwartiermeting(c, k + timedelta(minutes=10), k)   # 590 s stil: niet gemeten
    assert uit == {}
    uit = C._accu_kwartiermeting(c, k + timedelta(minutes=11), k)
    assert uit["accu_dekking"] == pytest.approx(60 / 900, abs=0.01)


def test_sluimer_meldt_de_bronnen():
    from pathlib import Path
    bron = coordinator_bron()
    assert 'uit["kwartieren_uit_de_kwartiermeting"]' in bron
    assert 'regel.update(self._accu_kwartiermeting(now, kwartier))' in bron
