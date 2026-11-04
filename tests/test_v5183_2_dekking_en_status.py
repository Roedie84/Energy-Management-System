"""v5.183.2: volle dekking in de slimme stand; leermodus is geen GOED/OK.

Kaart claude-ems 04-11: (1) plantabel 18:00 accu 693 W + net 292 W bij een
huis van 684 W; (2) cockpit/systeemstatus 'GOED'/'OK' terwijl de leermodus
niet stuurt.
"""
from datetime import datetime, timedelta

from custom_components.energy_management_system import waardeplan as W

T0 = datetime(2026, 11, 4, 18, 0)


def test_huis_rij_accu_plus_net_is_huis():
    kw = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.171, 0.0, 0.50, 0.52) for i in range(16)]
    res = W.plan(kw, W.Accu(inhoud_kwh=1.5, bruikbaar_kwh=7.7, rendement=0.834, slijtage_eur=0.042,
                            netladen=False, verkopen=False))
    for r in res.kwartieren:
        if r["actie"] == "huis":
            assert abs(-r["accu_kwh"] + r["net_kwh"] - 0.171) < 0.002
            assert r["accu_ac_w"] == round(-r["accu_kwh"] * 4000)
    # geen halve dekking: de inhoud zakt per kwartier minstens met het tekort (op de stap)
    for r in res.kwartieren:
        if r["actie"] == "huis" and r["inhoud_kwh"] > 0:
            assert -r["inhoud_delta_kwh"] >= 0.2 - 1e-9


def test_leermodus_geen_goed(make_coordinator, hass):
    c = make_coordinator({})
    c.learning_only = True
    c.handmatige_stand = "smart_charge"
    assert c._stuurt_niet_tekst() == "stuurt niet: handmatig slim laden"
    c.handmatige_stand = None
    assert c._stuurt_niet_tekst() == "stuurt niet: leermodus"


def test_status_regels_in_de_code():
    from pathlib import Path
    import custom_components.energy_management_system as pkg
    code = (Path(pkg.__file__).parent / "coordinator.py").read_text(encoding="utf-8")
    status = code.split("    def _ems_status(self)", 1)[1].split("\n    def ", 1)[0]
    assert 'return "LET OP", met_reden(self._stuurt_niet_tekst())' in status
    sysst = code.split("    def system_status(self)", 1)[1].split("\n    def ", 1)[0]
    assert 'return "Stuurt niet ("' in sysst


# Ruud 04-11 15:06 ("waarom hier sparen ipv slim?"): de planprijzen van 05-11
# 04:00-24:00 (prijs ct, zon W, huis W); 's ochtends 06:00-08:15 bewaarde het
# plan bij 42-51 ct terwijl het huis op het net draaide. De bewaarmarge werkte
# niet bij een klein huisverbruik (< 600 W): een half gedekt kwartier telde als
# dekken, en een stap boven het tekort was een mini-verkoop die verboden werd.
OCHTEND = [[37.5,0,212],[37.6,0,212],[37.8,0,212],[37.3,0,212],[36,0,180],[35.7,0,180],[35,0,180],[34.9,0,180],[37.1,0,248],[42,0,248],[42.7,0,248],[43.4,0,248],[46.7,0,292],[48.3,0,292],[49,12,292],[49.2,12,292],[50.9,128,224],[49,128,224],[48.2,240,224],[47,240,224],[47.6,368,224],[45.7,368,224],[43.4,504,224],[39.8,504,224],[43,872,292],[39.6,872,292],[39.3,1220,292],[39,1220,292],[38.1,1380,596],[37.6,1380,596],[37.9,1204,596],[37.1,1204,596],[37.3,1476,444],[37.4,1476,444],[37.2,1004,444],[37.6,1004,444],[37.3,1812,776],[38.3,1812,776],[37.4,1312,776],[37.3,1312,776],[37.4,1284,536],[38.4,1284,536],[41.2,1004,536],[45.8,1004,536],[43.2,512,760],[47.8,512,760],[49.4,604,760],[52.7,604,760],[50.2,252,804],[54,252,804],[55.1,32,804],[54.8,32,804],[55.8,0,1224],[55.7,0,1224],[55.2,0,1224],[55.1,0,1224],[55.4,0,684],[55.2,0,684],[55.3,0,684],[54.3,0,684],[55.3,0,672],[54.6,0,672],[54,0,672],[53.1,0,672],[53.3,0,604],[53,0,604],[50.8,0,604],[49.8,0,604],[50.2,0,668],[48.8,0,668],[48.4,0,668],[47.1,0,668],[47.3,0,312],[46.2,0,312],[46.1,0,312],[44.4,0,312],[44.2,0,236],[43.5,0,236],[43.1,0,236],[41.8,0,236]]


def test_ochtend_voedt_het_huis_met_bewaarmarge():
    t0 = datetime(2026, 11, 5, 4, 0)
    kw = [W.Kwartier(t0 + timedelta(minutes=15 * i), h / 4000, z / 4000, (p - 11) / 100, (p - 9) / 100,
                     prijs_incl_eur=p / 100) for i, (p, z, h) in enumerate(OCHTEND)]
    acc = W.Accu(inhoud_kwh=0.05, bruikbaar_kwh=7.78, rendement=0.834, slijtage_eur=0.0422,
                 verkoopmarge_eur=0.05, min_actie_w=200, min_laad_w=500, huis_eerst=True,
                 eindprijs_eur=0.40, bewaarmarge_eur=0.05, bewaarkost_eur_per_kwh_uur=0.002,
                 zon_export_afdwingbaar=True)
    rijen = W.plan(kw, acc).kwartieren
    ochtend = rijen[9:17]                      # 06:15-08:00
    assert all(r["actie"] == "huis" for r in ochtend if r["inhoud_kwh"] > 0.05)
    assert any(r["actie"] == "huis" for r in ochtend)
    assert max(r["inhoud_kwh"] for r in rijen) > 7.0     # en 's middags toch vol voor de avond
    assert W.te_duur_bewaard(rijen, kw, acc) == []
