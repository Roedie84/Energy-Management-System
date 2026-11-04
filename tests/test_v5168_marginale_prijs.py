"""v5.168.0 - tijdens salderen met de marginale prijs rekenen bij een verwacht
overschot in het contractjaar (Ruud 02-11 22:40).

Het voorbeeld van 02-11 avond (live prijzen): nacht 37,7-39 ct, ochtend
48,5-52,4 ct, belastingdeel 11,08 ct (gemeten), laadrendement 81,9 %,
ontladen 95,8 %, slijtage 4,22 ct per kWh uit de cellen, datacorrectie 1,66 ct.
Met de volle prijs laadt het plan niets; met de prijs zonder belastingdeel
(je eindigt het salderingsjaar met een overschot) loont netladen 's nachts.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system import salderingspositie as SP
from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.const import (
    CONF_CONTRACT_START_DATE,
    FEEDIN_PREMIUM_EUR_PER_KWH,
    PRICE_SCALE_FACTOR,
)

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 2, 23, 0, tzinfo=TZ)
DEEL = 0.1108

# 02-11 23:00 t/m 03-11 23:45, de live kwartierprijzen incl. belasting
PRIJZEN = [
    0.417, 0.4123, 0.4056, 0.3954, 0.3968, 0.3922, 0.3851, 0.3818, 0.3937, 0.3861, 0.381, 0.3772,
    0.3774, 0.3962, 0.3964, 0.3989, 0.4011, 0.4009, 0.4001, 0.3995, 0.4006, 0.4011, 0.4015, 0.4028,
    0.3947, 0.3966, 0.3982, 0.4114, 0.3998, 0.4293, 0.4628, 0.4715, 0.4853, 0.4939, 0.494, 0.4971,
    0.5244, 0.5014, 0.4832, 0.4778, 0.5011, 0.4728, 0.4497, 0.4156, 0.4455, 0.4146, 0.3971, 0.3969,
    0.4147, 0.4033, 0.4031, 0.4005, 0.3977, 0.3978, 0.4007, 0.4018, 0.4038, 0.4075, 0.4023, 0.3956,
    0.3987, 0.4056, 0.409, 0.4123, 0.4056, 0.4133, 0.4569, 0.4817, 0.4632, 0.4924, 0.489, 0.4987,
    0.4959, 0.5085, 0.5241, 0.5133, 0.4971, 0.5013, 0.5046, 0.5067, 0.4982, 0.4995, 0.4902, 0.4905,
    0.4896, 0.4764, 0.4561, 0.4372, 0.439, 0.4305, 0.4102, 0.4008, 0.4174, 0.4062, 0.4084, 0.4,
    0.414, 0.4054, 0.4057, 0.4015,
]


def _kwartieren(overschot: bool, deel: float = DEEL):
    uit = []
    for i, p in enumerate(PRIJZEN):
        t = NU + timedelta(minutes=15 * i)
        inkoop, terug = SP.marginale_prijzen(p, deel, FEEDIN_PREMIUM_EUR_PER_KWH, overschot)
        uit.append(W.Kwartier(
            t, 0.1 if t.hour < 6 else 0.15, 0.15 if 10 <= t.hour < 15 else 0.0, inkoop, terug,
            prijs_incl_eur=p if inkoop != p else None,
        ))
    return uit


def _accu():
    return W.Accu(
        inhoud_kwh=0.02, bruikbaar_kwh=10.37, rendement=0.81, slijtage_eur=0.0422,
        netlaadmarge_eur=0.0166, rendement_laden=0.819, rendement_ontladen=0.958,
    )


def _laden(u):
    return [r for r in u.kwartieren if r["actie"] == "laden_net"]


def test_vanavond_volle_prijs_laadt_niet():
    u = W.plan(_kwartieren(overschot=False), _accu())
    assert _laden(u) == []


def test_vanavond_marginale_prijs_laadt_s_nachts():
    u = W.plan(_kwartieren(overschot=True), _accu())
    lading = _laden(u)
    assert sum(r["kwh"] for r in lading) >= 1.0
    assert all(r["begin"].hour < 6 for r in lading)
    # weergave: de prijs incl. belasting; gerekend met de marginale prijs
    r = lading[0]
    assert r["prijs_eur"] - r["rekenprijs_eur"] == pytest.approx(DEEL, abs=1e-4)
    assert u.kosten_plan_eur < u.kosten_zonder_accu_eur


def test_met_belastingdeel_13_ct_ook():
    u = W.plan(_kwartieren(overschot=True, deel=0.13), _accu())
    assert sum(r["kwh"] for r in _laden(u)) >= 1.0


# --- de coordinator -------------------------------------------------------

def _historie(imp, exp):
    uit = []
    d = datetime(2025, 4, 1).date()
    while d < NU.date():
        winter = d.month in (11, 12, 1, 2, 3) and d.year == 2025 or d < datetime(2026, 4, 1).date()
        uit.append({
            "datum": d.isoformat(),
            "import_kwh": 9.0 if winter else imp,
            "export_kwh": 1.0 if winter else exp,
        })
        d += timedelta(days=1)
    return uit


def _coordinator(make_coordinator, imp=2.3, exp=6.8, deel=DEEL):
    c = make_coordinator({CONF_CONTRACT_START_DATE: "2025-04-01"})
    c.energy_daily_history = _historie(imp, exp)
    c.grid_import_today_kwh = 10.7
    c.pv_export_today_kwh = 0.1
    c._gemeten_belastingdeel_eur_per_kwh = lambda: deel
    return c


def test_coordinator_overschot_geeft_korting(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    pos = c.salderingspositie(NU)
    assert pos["modus"] == SP.OVERSCHOT
    assert pos["rekent_marginaal"] is True
    assert pos["belastingdeel_eur_per_kwh"] == pytest.approx(DEEL)
    c.salderingspositie = lambda now=None: pos
    assert c._salderingskorting_eur(NU) == pytest.approx(DEEL)
    assert c._marginale_prijs(0.377, NU) == pytest.approx(0.377 - DEEL)
    # na het einde van de saldering geen korting
    assert c._salderingskorting_eur(datetime(2027, 1, 1, 1, 0, tzinfo=TZ)) == 0.0
    zin = c._saldering_uitlegzin()
    assert zin.startswith("tot 31-12 rekent het plan met de prijs zonder energiebelasting")
    assert "kWh overschot" in zin
    weergave = c.salderingspositie_weergave()
    for veld in ("modus", "balans_kwh", "eindstand_kwh", "marge_kwh", "belastingdeel_eur_per_kwh", "eind"):
        assert veld in weergave


def test_coordinator_tekort_geen_korting(make_coordinator, hass):
    c = _coordinator(make_coordinator, imp=7.0, exp=2.0)
    pos = c.salderingspositie(NU)
    assert pos["modus"] == SP.TEKORT
    c.salderingspositie = lambda now=None: pos
    assert c._salderingskorting_eur(NU) == 0.0
    assert c._saldering_uitlegzin() is None


@pytest.mark.parametrize("deel", [0.0, 0.5])
def test_zonder_aannemelijk_belastingdeel_de_volle_prijs(make_coordinator, hass, deel):
    c = _coordinator(make_coordinator, deel=deel)
    pos = c.salderingspositie(NU)
    assert pos["modus"] == SP.OVERSCHOT
    assert pos["rekent_marginaal"] is False
    c.salderingspositie = lambda now=None: pos
    assert c._salderingskorting_eur(NU) == 0.0


def test_fout_in_het_belastingdeel_breekt_niets(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    def kapot():
        raise RuntimeError("geen kale prijs")

    c._gemeten_belastingdeel_eur_per_kwh = kapot
    pos = c.salderingspositie(NU)
    assert pos["rekent_marginaal"] is False


def test_zonder_contractstart_geen_korting(make_coordinator, hass):
    c = make_coordinator({})
    c._gemeten_belastingdeel_eur_per_kwh = lambda: DEEL
    assert c._salderingskorting_eur(NU) == 0.0


def _waardeplan_coordinator(make_coordinator, korting):
    c = make_coordinator({})
    c._salderingskorting_eur = lambda moment: korting
    c._segmenten_verbruik_zon = lambda van, eind, veilig=False: [(0.1, 0.0)]
    c._estimate_pv_kwh_for_period = lambda van, eind, veilig=False: 0.0
    c._planning_verkoopreserve_kwh = lambda begin, cache, entries, inkoop: 0.0
    c._kale_entries = lambda: []
    entries = [
        (NU + timedelta(minutes=15 * i), NU + timedelta(minutes=15 * (i + 1)), p * PRICE_SCALE_FACTOR)
        for i, p in enumerate(PRIJZEN[:8])
    ]
    return c, entries


def test_waardeplan_kwartieren_rekenen_marginaal(make_coordinator, hass):
    c, entries = _waardeplan_coordinator(make_coordinator, DEEL)
    kw = c._waardeplan_kwartieren(NU, entries)
    assert kw[0].inkoop_eur == pytest.approx(PRIJZEN[0] - DEEL)
    assert kw[0].teruglever_eur == pytest.approx(PRIJZEN[0] - DEEL + FEEDIN_PREMIUM_EUR_PER_KWH)
    assert kw[0].prijs_incl_eur == pytest.approx(PRIJZEN[0])


def test_waardeplan_kwartieren_zonder_korting_ongewijzigd(make_coordinator, hass):
    c, entries = _waardeplan_coordinator(make_coordinator, 0.0)
    kw = c._waardeplan_kwartieren(NU, entries)
    assert kw[0].inkoop_eur == pytest.approx(PRIJZEN[0])
    assert kw[0].teruglever_eur == pytest.approx(PRIJZEN[0] + FEEDIN_PREMIUM_EUR_PER_KWH)
    assert kw[0].prijs_incl_eur is None


def test_weergegeven_kosten_blijven_incl_belasting(make_coordinator, hass):
    """De terugleverwaarde van de kostenboeking en de prijs van het kwartier
    veranderen niet: alleen de beslissingen rekenen marginaal."""
    c, entries = _waardeplan_coordinator(make_coordinator, DEEL)
    assert c._get_feedin_value_per_kwh(entries, NU + timedelta(minutes=1)) == pytest.approx(
        PRIJZEN[0] + FEEDIN_PREMIUM_EUR_PER_KWH
    )
    assert c._get_current_price_per_kwh(entries, NU + timedelta(minutes=1)) == pytest.approx(PRIJZEN[0])


def test_dipbesluit_rekent_marginaal(make_coordinator, hass):
    """Nacht 37,7 ct tegen een ongedekte piek van 52,4 ct (rondrit 81 %):
    met de volle prijs niet, zonder belastingdeel wel."""
    blok = NU + timedelta(hours=14)

    def stel_in(korting):
        c = make_coordinator({})
        c.spaarplan = lambda now, entries, b, marge=1.0: {
            "actief": True, "beschikbaar_kwh": 0.0, "nodig_kwh": 3.0,
            "duurste_ongedekt_eur": 0.524, "blok": blok.isoformat(),
            "duurste_ongedekt_om": (NU + timedelta(hours=9)).isoformat(),
        }
        c._get_forecast_entries = lambda **kw: []
        c.huidige_prijs_eur_per_kwh = lambda: 0.377
        c._resterende_laadruimte_kwh = lambda: 6.0
        c.charge_efficiency_history = [81.0] * 7
        c.discharge_efficiency_history = [100.0] * 7
        c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.22}
        c.laadcorrectie_ct = lambda: 1.66
        c._salderingskorting_eur = lambda moment: korting
        return c

    assert stel_in(0.0)._dipbesluit(NU, blok)["laden"] is False
    met = stel_in(DEEL)._dipbesluit(NU, blok)
    assert met["laden"] is True
    assert met["prijs_nu_eur"] == pytest.approx(0.377 - DEEL, abs=1e-4)


# --- de nacalculatie (accukosten) -----------------------------------------

def _rij(tijd, inhoud, prijs_ct, accu_w, korting=None, verwacht=None, reden="grid_charging_profitable"):
    r = {"tijd": tijd, "beschikbaar_kwh": inhoud, "prijs_ct": prijs_ct, "accu_w": accu_w,
         "net_w": max(0.0, -accu_w), "huis_w": 300.0, "pv_w": 0.0, "reden": reden,
         "laad_waarde_ct": verwacht, "laad_waarde_bron": "waardeplan"}  # v5.183.0
    if korting is not None:
        r["korting_ct"] = korting
    return r


def _dagverloop(korting_laden, korting_ontladen, verwacht_ct):
    laden = [_rij(f"0{h}:{m:02d}", 0.5 * (i + 1), 37.7, -2000.0, korting_laden, verwacht_ct)
             for i, (h, m) in enumerate((h, m) for h in (1, 2) for m in (0, 15, 30, 45))]
    ontladen = [_rij(f"0{h}:{m:02d}", 4.0 - 0.5 * (i + 1), 52.4, 2000.0, korting_ontladen, None, "huis")
                for i, (h, m) in enumerate((h, m) for h in (7, 8) for m in (0, 15, 30, 45))]
    return {"2026-11-03": laden + ontladen}


def test_nacalculatie_op_dezelfde_grondslag():
    """Verwacht en gerealiseerd allebei zonder belastingdeel: geen schijnbaar
    tekort van belastingdeel x (1 - rendement)."""
    k = DEEL * 100
    verwacht = 0.9 * (0.9 * (52.4 - k) - 4.22)  # per kWh die erin ging
    uit = A.doorreken(_dagverloop(k, k, verwacht), 0.9, 0.9, 0.0422)
    net = uit["net"]
    assert net["inkoop_ct"] == pytest.approx(37.7 - k, abs=0.1)
    assert net["gerealiseerd_ct"] == pytest.approx(verwacht, abs=0.5)


def test_nacalculatie_oude_regels_ongewijzigd():
    verwacht = 0.9 * (0.9 * 52.4 - 4.22)
    uit = A.doorreken(_dagverloop(None, None, verwacht), 0.9, 0.9, 0.0422)
    assert uit["net"]["inkoop_ct"] == pytest.approx(37.7, abs=0.1)
    assert uit["net"]["gerealiseerd_ct"] == pytest.approx(verwacht, abs=0.5)


def test_nacalculatie_omslag_tussen_laden_en_ontladen():
    """Geladen met de volle prijs (oude regel), ontladen terwijl er korting
    geldt: de partij wordt op zijn eigen grondslag vergeleken."""
    verwacht = 0.9 * (0.9 * 52.4 - 4.22)
    uit = A.doorreken(_dagverloop(None, DEEL * 100, verwacht), 0.9, 0.9, 0.0422)
    assert uit["net"]["gerealiseerd_ct"] == pytest.approx(verwacht, abs=0.5)


def test_voorraadkostprijs_blijft_incl_belasting():
    """De dagbesparing waardeert de voorraad tegen wat er betaald is."""
    dv = {"2026-11-03": [r for r in _dagverloop(DEEL * 100, None, None)["2026-11-03"] if r["accu_w"] < 0]}
    uit = A.doorreken(dv, 0.9, 0.9, 0.0422)
    assert uit["voorraad_kostprijs"]["eur_per_kwh"] == pytest.approx(0.377 / 0.9, abs=0.002)
