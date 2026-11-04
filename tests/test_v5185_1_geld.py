"""v5.185.1: netladen-blok, belasting tijdens de saldering, betekenis van 'jaar'.

Onderzoek kosten/besparing 04-11 19:44; Ruud 20:00: "Jij weet wat het beste is".
"""
from datetime import datetime
from pathlib import Path

import custom_components.energy_management_system as pkg

BRON = Path(pkg.__file__).parent


def test_cockpit_netladen_uit_de_accuboekhouding():
    js = (BRON / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert "Netladen deze maand:" in js and "Marge op netladen" in js
    assert "current_month_discharge_value_eur" not in js


def test_accukosten_maandtotaal():
    from custom_components.energy_management_system import accukosten as A
    code = (BRON / "accukosten.py").read_text(encoding="utf-8")
    assert '"netladen_maand": maand,' in code
    assert hasattr(A, "_samenvatting")


def test_saldering_corrigeert_het_scenario_zonder_accu():
    code = (BRON / "financien.py").read_text(encoding="utf-8")
    assert "counterfactual_cost_eur -= self._salderingscorrectie_eur(" in code


def test_jaar_betekenis(make_coordinator):
    c = make_coordinator({})
    c.daily_cost_history = [{"stroom_eur": 1.0, "gas_eur": 0.5}] * 89
    o = c.get_energy_cost_overview()
    assert o["jaar_dagen"] == 89 and "sinds start meting (89 dagen)" in o["periodes"]
    _ = datetime


def test_salderingscorrectie_teken(make_coordinator):
    from datetime import timezone
    c = make_coordinator({})
    c._salderingskorting_eur = lambda now: 0.11
    nu = datetime(2026, 11, 4, 20, 0, tzinfo=timezone.utc)
    assert abs(c._salderingscorrectie_eur(nu, 1000.0, 0.25) - 0.0275) < 1e-9     # ontladen
    assert abs(c._salderingscorrectie_eur(nu, -1000.0, 0.25) + 0.0275) < 1e-9    # laden
    c._salderingskorting_eur = lambda now: 0.0
    assert c._salderingscorrectie_eur(nu, 1000.0, 0.25) == 0.0
