"""v5.168.0 - saldering per contractjaar: de positie en de projectie.

Ruud 02-11 22:40: Zonneplan saldeert per contractjaar (start 1 april). In het
lopende contractjaar leverde hij ~1464 kWh terug tegen ~491 kWh afname; met
november en december erbij eindigt hij de saldering (31-12) nog steeds met een
overschot van honderden kWh.
"""
from datetime import date, timedelta

import pytest

from custom_components.energy_management_system import salderingspositie as SP

VANDAAG = date(2026, 11, 2)
START = date(2025, 4, 1)
TOT = date(2026, 12, 31)


def _dagen(van, tot, imp, exp, ruis=0.0):
    uit, d, i = [], van, 0
    while d <= tot:
        r = ruis * (1 if i % 2 else -1)
        uit.append({"datum": d.isoformat(), "import_kwh": imp + r, "export_kwh": exp})
        d += timedelta(days=1)
        i += 1
    return uit


def _reeks(contractjaar_imp, contractjaar_exp, winter_netto=8.0, recent_netto=6.0):
    """Vorig jaar nov-dec `winter_netto` per dag; dit contractjaar tot 4 weken
    terug het opgegeven saldo, de laatste 4 weken `recent_netto` per dag."""
    vorig = _dagen(date(2025, 4, 1), date(2026, 3, 31), winter_netto, 0.0, ruis=2.0)
    dit = _dagen(date(2026, 4, 1), VANDAAG - timedelta(days=29), contractjaar_imp, contractjaar_exp)
    recent = _dagen(VANDAAG - timedelta(days=28), VANDAAG - timedelta(days=1), recent_netto + 1, 1.0, ruis=1.5)
    return vorig + dit + recent


def test_netto_terugleveraar_eindigt_met_overschot():
    """Zoals live: ~-970 kWh tot nu, ~8 kWh per dag erbij tot 31-12."""
    u = SP.bepaal(_reeks(2.0, 7.5), VANDAAG, START, TOT, 10.7, 0.1, 0.95)
    assert u["modus"] == SP.OVERSCHOT
    assert u["contractjaar_begin"] == "2026-04-01"
    assert u["eind"] == "2026-12-31"
    assert u["balans_kwh"] < -800
    assert u["verwachting_bron"] == "vorig_jaar"  # 8 > 6: de voorzichtige kant
    assert u["eindstand_kwh"] == pytest.approx(u["balans_kwh"] + u["verwacht_rest_kwh"], abs=0.2)
    assert u["overschot_kwh"] > u["marge_kwh"] >= SP.MARGE_MIN_KWH


def test_netto_afnemer_tekort():
    u = SP.bepaal(_reeks(6.0, 2.0), VANDAAG, START, TOT)
    assert u["modus"] == SP.TEKORT
    assert u["eindstand_kwh"] > u["marge_kwh"]


def test_rond_nul_onzeker():
    """Een eindstand binnen de marge: voorzichtig de volle prijs."""
    # dit contractjaar -2,5 per dag over 186 dagen + recent +6 x 28: ~-300;
    # de rest ~60 dagen x 6 = +360 -> eindstand rond nul, binnen de marge
    u = SP.bepaal(_reeks(4.0, 6.5, winter_netto=6.0), VANDAAG, START, TOT)
    assert abs(u["eindstand_kwh"]) <= u["marge_kwh"]
    assert u["modus"] == SP.ONZEKER


def test_contractjaargrens():
    assert SP.contractjaar(START, date(2026, 3, 31)) == (date(2025, 4, 1), date(2026, 3, 31))
    assert SP.contractjaar(START, date(2026, 4, 1)) == (date(2026, 4, 1), date(2027, 3, 31))
    # op de eerste dag van het nieuwe jaar telt alleen vandaag
    reeks = _reeks(2.0, 7.5)
    u = SP.bepaal(reeks, date(2026, 4, 1), START, TOT, 3.0, 1.0)
    assert u["balans_kwh"] == pytest.approx(2.0)
    assert u["contractjaar_begin"] == "2026-04-01"


def test_dagen_voor_het_contractjaar_tellen_niet():
    reeks = _reeks(2.0, 7.5) + [{"datum": "2026-03-31", "import_kwh": 9999.0, "export_kwh": 0.0}]
    u = SP.bepaal(reeks, VANDAAG, START, TOT)
    assert u["balans_kwh"] < -800


def test_einde_saldering_voor_einde_contractjaar():
    u = SP.bepaal(_reeks(2.0, 7.5), VANDAAG, START, TOT)
    assert u["contractjaar_eind"] == "2027-03-31"
    assert u["eind"] == "2026-12-31"
    assert u["resterende_dagen"] == pytest.approx(60.0)


def test_einde_contractjaar_voor_einde_saldering():
    u = SP.bepaal(_reeks(2.0, 7.5), VANDAAG, START, date(2027, 12, 31))
    assert u["eind"] == "2027-03-31"


def test_zonder_contractstart_onzeker():
    u = SP.bepaal(_reeks(2.0, 7.5), VANDAAG, None, TOT)
    assert u["modus"] == SP.ONZEKER
    assert "contractstart" in u["reden"]


def test_na_de_saldering():
    assert SP.bepaal([], date(2027, 1, 1), START, TOT)["modus"] == SP.NA_SALDERING


def test_te_veel_ontbrekende_dagen_onzeker():
    reeks = [r for r in _reeks(2.0, 7.5) if not ("2026-06-01" <= r["datum"] <= "2026-07-31")]
    u = SP.bepaal(reeks, VANDAAG, START, TOT)
    assert u["modus"] == SP.ONZEKER
    assert "ontbreken" in u["reden"]


def test_zonder_vorig_jaar_de_recente_dagen():
    reeks = [r for r in _reeks(2.0, 7.5) if r["datum"] >= "2026-04-01"]
    u = SP.bepaal(reeks, VANDAAG, START, TOT)
    assert u["verwachting_bron"] == "recent"
    assert u["modus"] == SP.OVERSCHOT


# --- marginale prijzen ----------------------------------------------------

def test_marginale_prijzen_bij_overschot():
    inkoop, terug = SP.marginale_prijzen(0.377, 0.1108, 0.02, True)
    assert inkoop == pytest.approx(0.2662)
    assert terug == pytest.approx(0.2862)  # premie blijft


def test_zonder_overschot_de_volle_prijs():
    assert SP.marginale_prijzen(0.377, 0.1108, 0.02, False) == pytest.approx((0.377, 0.397))


def test_marginale_prijs_nooit_boven_incl():
    inkoop, _ = SP.marginale_prijzen(0.377, -0.05, 0.02, True)
    assert inkoop == pytest.approx(0.377)


def test_negatieve_prijs_blijft_werken():
    inkoop, terug = SP.marginale_prijzen(-0.05, 0.1108, 0.02, True)
    assert inkoop == pytest.approx(-0.1608)
    assert terug == pytest.approx(-0.1408)


def test_live_02_11():
    """Live: balans ~-962 kWh; vorig jaar 3-11..31-12 12,2 kWh per dag
    (sigma 4,6), de laatste weken ~6,5. Eindstand ~-240, marge ~178."""
    vorig = _dagen(date(2025, 4, 1), date(2026, 3, 31), 12.22, 0.0, ruis=4.61)
    dit = _dagen(date(2026, 4, 1), date(2026, 11, 1), 491.4 / 215, 1464.0 / 215)
    u = SP.bepaal(vorig + dit, VANDAAG, START, TOT, 10.7, 0.1, 0.96)
    assert u["balans_kwh"] == pytest.approx(-962.0, abs=1.0)
    assert u["verwachting_bron"] == "vorig_jaar"
    assert u["eindstand_kwh"] == pytest.approx(-240, abs=15)
    assert u["marge_kwh"] == pytest.approx(178, abs=10)
    assert u["modus"] == SP.OVERSCHOT
