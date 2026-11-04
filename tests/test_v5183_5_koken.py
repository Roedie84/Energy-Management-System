"""v5.183.5: de accu dekt het huis ook bij een groot verbruik (koken).

Ruud 04-11 16:47: "waarom nu sparen? Nu ben ik juist aan het koken". Huis
2,2-4,6 kW, accu 2,6 kWh, plan: sparen tot 17:45. Twee oorzaken:
1. de volle-dekkingsregel (v5.183.2) eiste een stap tot de ontlaadgrens (0,3
   kWh bij 1,2 kW); met een rendement boven 1 viel 0,3 kWh net buiten de grens
   en 0,2 kWh onder de eis: geen ontlaadstap over, dus bewaren;
2. het plan rekende het huis dekken met het handmatige vermogen (1,2 kW, voor
   verkopen) in plaats van de grens van de slimme stand (2,4 kW).
"""
from dataclasses import replace
from datetime import datetime, timedelta

from custom_components.energy_management_system import waardeplan as W

F = [[50.6,24,1816],[46.8,0,2232],[49.4,0,2232],[50.1,0,2232],[50.9,0,1232],[49.5,0,692],[49.7,0,692],[49.9,0,692],[50.0,0,692],[49.9,0,684],[49.7,0,684],[48.8,0,684],[48.7,0,684],[47.6,0,616],[46.5,0,616],[46.0,0,616],[44.6,0,616],[44.3,0,680],[42.3,0,680],[41.5,0,680],[38.9,0,680],[41.3,0,324],[40.8,0,324],[39.6,0,324],[40.1,0,324],[39.8,0,248],[39.7,0,248],[40.2,0,248],[39.8,0,248],[37.6,0,228],[37.1,0,228],[36.5,0,228],[36.3,0,228],[36.7,0,220],[37.4,0,220],[37.7,0,220],[38.1,0,220],[38.2,0,188],[38.0,0,188],[37.6,0,188],[37.8,0,188],[37.8,0,220],[37.6,0,220],[37.7,0,220],[37.4,0,220],[37.5,0,220],[37.6,0,220],[37.8,0,220],[37.3,0,220],[36.0,0,192],[35.7,0,192],[35.0,0,192],[34.9,0,192],[37.1,0,260],[42.0,0,260],[42.7,0,260],[43.4,0,260],[46.7,0,300],[48.3,0,300],[49.0,12,300],[49.2,12,300],[50.9,128,236],[49.0,128,236],[48.2,240,236],[47.0,240,236],[47.6,368,232],[45.7,368,232],[43.4,504,232],[39.8,504,232],[43.0,872,304],[39.6,872,304],[39.3,1220,304],[39.0,1220,304],[38.1,1380,604],[37.6,1380,604],[37.9,1204,604],[37.1,1204,604],[37.3,1476,452],[37.4,1476,452],[37.2,1004,452],[37.6,1004,452],[37.3,1812,788],[38.3,1812,788],[37.4,1312,788],[37.3,1312,788],[37.4,1284,548],[38.4,1284,548],[41.2,1004,548],[45.8,1004,548],[43.2,512,752],[47.8,512,752],[49.4,604,752],[52.7,604,752],[50.2,252,816],[54.0,252,816],[55.1,32,816],[54.8,32,816],[55.8,0,1232],[55.7,0,1232],[55.2,0,1232],[55.1,0,1232],[55.4,0,692],[55.2,0,692],[55.3,0,692],[54.3,0,692],[55.3,0,684],[54.6,0,684],[54.0,0,684],[53.1,0,684],[53.3,0,616],[53.0,0,616],[50.8,0,616],[49.8,0,616],[50.2,0,680],[48.8,0,680],[48.4,0,680],[47.1,0,680],[47.3,0,324],[46.2,0,324],[46.1,0,324],[44.4,0,324],[44.2,0,248],[43.5,0,248],[43.1,0,248],[41.8,0,248]]
BANDEN = ((500.0, 0.999), (1500.0, 1.047), (float("inf"), None))


def _kw():
    t0 = datetime(2026, 11, 4, 16, 45)
    return [W.Kwartier(t0 + timedelta(minutes=15 * i), h / 4000, z / 4000, (p - 11.08) / 100, (p - 9.08) / 100,
                       prijs_incl_eur=p / 100) for i, (p, z, h) in enumerate(F)]


def _accu(**x):
    basis = dict(inhoud_kwh=2.59, bruikbaar_kwh=7.78, rendement=0.834, slijtage_eur=0.0422,
                 verkoopmarge_eur=0.05, min_actie_w=200, min_laad_w=500, huis_eerst=True,
                 eindprijs_eur=0.38, bewaarmarge_eur=0.05, bewaarkost_eur_per_kwh_uur=0.002,
                 zon_export_afdwingbaar=True, ontlaadbanden=BANDEN)
    basis.update(x)
    return W.Accu(**basis)


def test_ook_met_1_2_kw_dekt_de_accu_nu():
    rijen = W.plan(_kw(), _accu(ontladen_kw=1.2)).kwartieren
    assert [r["actie"] for r in rijen[:4]] == ["huis"] * 4


def test_slimme_stand_dekt_tot_2_4_kw_verkopen_op_1_2_kw():
    kw, acc = _kw(), _accu(ontladen_kw=2.4, verkoop_kw=1.2)
    rijen = W.plan(kw, acc).kwartieren
    # v5.186.0: het koken (16:45-17:30) grotendeels uit de accu; 2,2 kW huis gaat
    # tot 2,4 kW helemaal uit de accu. Was: precies kwartier 17:00. Nu kiest het
    # plan zelf het goedkoopste kookkwartier (46,8 ct) om te bewaren als de
    # lading later minstens de bewaarmarge meer waard is (marginale waarde uit
    # het plan, `te_duur_bewaard` blijft leeg).
    koken = [r for r in rijen[:4] if r["actie"] == "huis"]
    assert len(koken) >= 3
    assert all(-r["accu_kwh"] > 0.4 for r in koken if r["verbruik_kwh"] > 0.5)
    assert W.te_duur_bewaard(rijen, kw, acc) == []
    for r in rijen:
        if r["actie"] == "verkopen":
            assert -r.get("accu_stap_kwh", r["accu_kwh"]) <= 0.3 + 1e-6
