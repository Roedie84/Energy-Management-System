"""De terugtoetsbank: een regel over de opgeslagen dagen (v5.2).

De flessenhals in dit project is niet het bedenken van ideeën maar de
tijd om ze te weerleggen:

    ijklijn                    31 dagen
    bandpositie                16 dagen
    nabeschouwing               8 dagen
    apparaataanwijzing          8 nachten
    safe_sell_shadow           maanden

Elk idee kost weken tot maanden voordat je weet of het klopt. Sinds v5.1
staan er veertig dagen kwartierdata in het dagverloop - prijs, huis,
zon, accu, laadstand en reden per kwartier. Daarmee is een beslisregel
ACHTERAF door te rekenen op echte dagen, in seconden.

De bank neemt een regel als functie, laat hem over alle opgeslagen dagen
lopen, en vergelijkt de uitkomst met de nabeschouwing - dezelfde
maatstaf die er al is. Geen sturing; een manier om regels te verwerpen
voordat ze maanden meten.

Wat hij NIET kan: een regel toetsen die afhangt van informatie die niet
in het dagverloop staat. De voorspelling zoals die op dat moment was,
bijvoorbeeld - daarvan is er één momentopname per dag (08:00). De bank
zegt dat expliciet in plaats van stilzwijgend met de werkelijkheid te
rekenen.
"""
from datetime import datetime, timezone

import pytest


def _dag(c, datum, kwartieren=96, prijs=30.0, huis=250.0, pv=0.0, soc=50.0):
    # zoals de nabeschouwingstoetsen: een verse coordinator kent zijn
    # capaciteit nog niet
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.effective_min_soc_percent = lambda: 10.0
    c.dagverloop = dict(c.dagverloop or {})
    c.dagverloop[datum] = [
        {
            "tijd": f"{i // 4:02d}:{(i % 4) * 15:02d}",
            "prijs_ct": prijs,
            "huis_w": huis,
            "pv_w": pv,
            "accu_w": 0.0,
            "soc": soc,
            "reden": "default_smart",
        }
        for i in range(kwartieren)
    ]


def test_de_bank_loopt_over_alle_volledige_dagen(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}
    for d in range(1, 6):
        _dag(c, f"2026-09-{d:02d}")
    _dag(c, "2026-09-06", kwartieren=40)      # halve dag, hoort eruit

    uit = c.terugtoets(lambda dag, kw, n: 0.0)

    assert uit["dagen"] == 5
    assert "2026-09-06" not in uit["per_dag"]


def test_de_regel_krijgt_de_kwartieren_en_geeft_een_accu_actie(make_coordinator, hass):
    """De regel is een functie: (datum, kwartieren, index) -> kWh accu.
    Positief is ontladen. Meer heeft een terugtoets niet nodig."""
    c = make_coordinator({})
    c.dagverloop = {}
    _dag(c, "2026-09-01", huis=400.0)

    gezien = []

    def regel(dag, kwartieren, n):
        gezien.append((dag, n))
        return 0.1

    uit = c.terugtoets(regel)

    assert len(gezien) == 96
    assert uit["per_dag"]["2026-09-01"]["kosten_eur"] is not None


def test_de_bank_vergelijkt_met_de_nabeschouwing(make_coordinator, hass):
    """Een regel die niets doet hoort duurder uit te komen dan het
    optimum - dat is de maatstaf die er al is."""
    c = make_coordinator({})
    c.dagverloop = {}
    _dag(c, "2026-09-01", prijs=30.0, huis=400.0, pv=2000.0, soc=50.0)

    uit = c.terugtoets(lambda dag, kw, n: 0.0)
    dag = uit["per_dag"]["2026-09-01"]

    assert dag["optimum_eur"] <= dag["kosten_eur"]
    assert dag["gemist_eur"] >= 0


def test_twee_regels_zijn_te_vergelijken(make_coordinator, hass):
    """Waar de bank voor is: regel A tegen regel B op dezelfde dagen."""
    c = make_coordinator({})
    c.dagverloop = {}
    for d in range(1, 4):
        _dag(c, f"2026-09-{d:02d}", prijs=40.0, huis=800.0, soc=80.0)

    niets = c.terugtoets(lambda dag, kw, n: 0.0)
    ontladen = c.terugtoets(lambda dag, kw, n: 0.2)

    assert ontladen["kosten_eur_totaal"] < niets["kosten_eur_totaal"]


def test_de_bank_zegt_wat_hij_niet_kan(make_coordinator, hass):
    """Een regel die de voorspelling van dat moment nodig heeft, is niet
    te toetsen: daarvan is er één momentopname per dag."""
    c = make_coordinator({})
    c.dagverloop = {}
    _dag(c, "2026-09-01")

    uit = c.terugtoets(lambda dag, kw, n: 0.0)

    assert "voorspelling" in uit["beperking"].lower()
    assert "08:00" in uit["beperking"]


def test_zonder_dagen_geen_uitkomst(make_coordinator, hass):
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.dagverloop = {}

    uit = c.terugtoets(lambda dag, kw, n: 0.0)

    assert uit["dagen"] == 0
    assert uit["te_becijferen"] is False


def test_een_regel_die_omvalt_breekt_de_bank_niet(make_coordinator, hass):
    """Een halve uitkomst is bruikbaar; een stacktrace niet."""
    c = make_coordinator({})
    c.dagverloop = {}
    _dag(c, "2026-09-01")
    _dag(c, "2026-09-02")

    def stuk(dag, kwartieren, n):
        if dag == "2026-09-02":
            raise ValueError("stuk")
        return 0.0

    uit = c.terugtoets(stuk)

    assert uit["dagen"] == 1
    assert "2026-09-02" in uit["overgeslagen"]


def test_de_accugrenzen_worden_gerespecteerd(make_coordinator, hass):
    """Een regel mag niet meer ontladen dan er in zit - anders meet de
    bank een uitkomst die fysiek onmogelijk was."""
    c = make_coordinator({})
    c.dagverloop = {}
    _dag(c, "2026-09-01", soc=12.0)

    uit = c.terugtoets(lambda dag, kw, n: 2.0)
    dag = uit["per_dag"]["2026-09-01"]

    assert dag["afgekapt_kwartieren"] > 0
