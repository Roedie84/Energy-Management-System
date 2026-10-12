"""Gemist bedrag per dagdeel in de nabeschouwing (v5.89, L-EMS-019).

Privacykeuze v5.28 blijft: geen kwartierregels met huisverbruik in de
export, alleen sommen per dagdeel.
"""
from custom_components.energy_management_system.nabeschouwing import (
    Kwartier,
    nabeschouwing,
)

ACCU = dict(capaciteit_kwh=2.0, begin_kwh=0.5, bodem_kwh=0.2, laad_kw=2.0,
            ontlaad_kw=1.6, rendement=0.84, slijtage_eur_per_kwh=0.0)


def _dag():
    # 96 kwartieren: avondpiek duur, rest gewoon; zon midden op de dag.
    kw, tijden = [], []
    for i in range(96):
        uur = i // 4
        prijs = 0.45 if 17 <= uur < 21 else 0.25
        pv = 0.4 if 10 <= uur < 15 else 0.0
        kw.append(Kwartier(huis_kwh=0.1, pv_kwh=pv, prijs_eur=prijs, accu_kwh=0.0))
        tijden.append(f"{uur:02d}:{(i % 4) * 15:02d}")
    return kw, tijden


def test_vier_dagdelen_met_alle_kwartieren():
    kw, tijden = _dag()
    uit = nabeschouwing(kw, eind_kwh=0.5, tijdstippen=tijden, **ACCU)
    d = uit["per_dagdeel"]
    assert set(d) == {"nacht", "ochtendpiek", "middag", "avondpiek"}
    assert sum(v["kwartieren"] for v in d.values()) == 96
    assert d["nacht"]["kwartieren"] == 28 and d["avondpiek"]["kwartieren"] == 28


def test_niets_gedaan_mist_vooral_in_de_avondpiek():
    """Zon laden en in de dure avond ontladen: daar zit het verschil."""
    kw, tijden = _dag()
    uit = nabeschouwing(kw, eind_kwh=0.5, tijdstippen=tijden, **ACCU)
    d = uit["per_dagdeel"]
    assert d["avondpiek"]["verschil_eur"] > 0
    assert d["avondpiek"]["vastgehouden_kwh"] > 0
    assert d["avondpiek"]["verschil_abs_eur"] >= max(
        d[n]["verschil_abs_eur"] for n in ("nacht", "ochtendpiek")
    )


def test_geen_huisverbruik_per_kwartier_in_het_dagdeel():
    kw, tijden = _dag()
    uit = nabeschouwing(kw, eind_kwh=0.5, tijdstippen=tijden, **ACCU)
    for v in uit["per_dagdeel"].values():
        assert not any("huis" in k for k in v)
