"""v5.200.0: het airco-vermogen uit de compressorfrequentie.

Ruud 09-11: het verbruik van de airco beter analyseren met
sensor.woonkamer_compressor_frequency - akkoord op: (1) live vermogen uit de
frequentie, zelf bijgeleerd uit de energieteller; (2) opwarmen en
vasthouden apart; (3) het uurverbruik uit de teller.
"""
import math
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import airco_frequentie as F
from custom_components.energy_management_system import airco_ritme as R
from custom_components.energy_management_system import airco_sturing as A


def _simuleer(model, loop, a=28.0, b=-150.0, uren=6.0, stap_s=60):
    """Een compressor die tussen 16 en 66 Hz golft; de teller loopt in
    stappen van 0,1 kWh mee met het echte vermogen a*Hz+b."""
    echt = 0.0
    n = int(uren * 3600 / stap_s)
    for i in range(n):
        hz = 0.0 if (i // 40) % 4 == 3 else 41 + 25 * math.sin(i / 7)
        dt = stap_s / 3600
        F.ronde(model, loop, hz=hz, teller_kwh=math.floor(echt * 10) / 10, uren=dt)
        echt += (max(a * hz + b, F.MIN_DRAAI_W) if hz > 0 else 0.0) / 1000 * dt
    return echt


def test_standaard_08_11():
    assert F.vermogen_w(F.leeg(), 0) == 0.0
    assert round(F.vermogen_w(F.leeg(), 16)) == round(31.4 * 16 - 238)
    assert 1700 < F.vermogen_w(F.leeg(), 66) < 1900
    assert F.vermogen_w(F.leeg(), None) is None


def test_leert_eigen_omrekening_uit_teller():
    model, loop = F.leeg(), F.nieuwe_teller()
    _simuleer(model, loop)
    a, b, geleerd = F.coefficienten(model)
    assert geleerd and len(model["vensters"]) >= F.VENSTERS_MIN
    assert abs(a - 28.0) < 2.5 and abs(b + 150) < 120


def test_onredelijke_fit_valt_terug():
    model = {"vensters": [[10.0, 1.0, 5.0]] * 10, "opwarm_w": [], "houd_w_per_graad": []}
    a, b, geleerd = F.coefficienten(model)
    assert not geleerd and a == F.STANDAARD_W_PER_HZ


def test_middernacht_breekt_venster_niet_het_totaal():
    model, loop = F.leeg(), F.nieuwe_teller()
    for teller in (6.0, 6.1, 6.2):
        F.ronde(model, loop, hz=30, teller_kwh=teller, uren=0.1)
    voor = F.stand_kwh(loop)
    F.ronde(model, loop, hz=30, teller_kwh=0.0, uren=0.05)
    assert not loop["begonnen"]
    F.ronde(model, loop, hz=30, teller_kwh=0.1, uren=0.1)
    assert F.stand_kwh(loop) >= voor


def test_uurstand_teller_plus_rest():
    model, loop = F.leeg(), F.nieuwe_teller()
    F.ronde(model, loop, hz=0, teller_kwh=1.0, uren=0.01)
    F.ronde(model, loop, hz=40, teller_kwh=1.0, uren=0.05)
    rest = F.vermogen_w(model, 40) / 1000 * 0.05
    assert abs(F.stand_kwh(loop) - rest) < 1e-9
    # nooit meer dan één stap rest
    F.ronde(model, loop, hz=66, teller_kwh=1.0, uren=0.2)
    assert F.stand_kwh(loop) < F.TELLER_STAP_KWH


def test_opwarmen_en_vasthouden_apart():
    model, loop = F.leeg(), F.nieuwe_teller()
    for _ in range(15):  # kamer koud: opwarmen op 60 Hz
        F.ronde(model, loop, hz=60, teller_kwh=None, uren=1 / 60,
                binnen_c=18.0, buiten_c=8.0, doel_c=21.0, verwarmt=True)
    assert F.opwarm_kw(model) == round(F.vermogen_w(model, 60)) / 1000
    for _ in range(3):  # drie uur op temperatuur, 18 Hz, verschil 13 graden
        for _ in range(60):
            F.ronde(model, loop, hz=18, teller_kwh=None, uren=1 / 60,
                    binnen_c=21.0, buiten_c=8.0, doel_c=21.0, verwarmt=True)
    verwacht = F.vermogen_w(model, 18) / 13
    assert abs(F.houd_w_per_graad(model) - verwacht) < 0.5


def test_dagritme_bewaart_en_gebruikt_opwarmvermogen():
    ritme = R.leeg()
    ritme["frequentie"]["opwarm_w"] = [1600.0] * 12
    ritme["vermogens"] = [1010.0] * 10
    terug = R.geldig(ritme)
    assert terug["frequentie"]["opwarm_w"] == [1600.0] * 12
    assert R.verwarmvermogen_kw(terug) == 1.6
    assert R.geldig({})["frequentie"] == F.leeg()


def test_weg_keuze_met_gemeten_vasthouden():
    basis = dict(binnen_c=21.0, buiten_c=5.0, doel_c=21.0, tempo_c_per_uur=2.0,
                 uren_weg=10.0, kost_vast=0.40, kost_terug=0.40)
    zuinig = A.weg_keuze(**basis, houd_w_graad=5.0, vermogen_kw=1.6)
    duur = A.weg_keuze(**basis, houd_w_graad=80.0, vermogen_kw=1.6)
    assert zuinig["kosten_vast_eur"] < duur["kosten_vast_eur"]
    assert zuinig["kosten_uit_eur"] == duur["kosten_uit_eur"]
