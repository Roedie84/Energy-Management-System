"""Wat kostte deze wasbeurt, en wat scheelde de zon? (v4.14)

Naar aanleiding van ha-home-energy-advisor, dat per apparaat uitrekent
wat het kostte en hoeveel de eigen opwek scheelde. Dat is een vraag die
dit EMS niet kon beantwoorden: het rekent de tegenfeitelijke kosten op
HUISNIVEAU (`counterfactual_cost_all_time_eur`) en weet wel welke
apparaten er zijn, maar niet wat een vaatwasbeurt kostte.

Dat maakt de uitstelbeslissingen oncontroleerbaar. Het EMS zegt
"wasmachine uitstellen tot 13:00"; het kan niet zeggen wat dat heeft
gescheeld.

Nu wel. Bij het afsluiten van een cyclus is alles bekend: starttijd,
eindtijd en de gemeten kWh. Het dagverloop heeft per kwartier de prijs
en het zonoverschot. Daarmee zijn drie getallen te berekenen:

- wat de cyclus KOSTTE: het deel uit het net maal de prijs per kwartier
- wat hij op pure NETSTROOM had gekost: alles maal de prijs
- het verschil: wat de zon en de accu scheelden

En omdat het dagverloop de hele dag bevat, is ook te zeggen wat het
DUURSTE en het GOEDKOOPSTE moment van die dag was geweest - dus wat het
uitstel opleverde, of had kunnen opleveren.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc)


def _dag(c):
    """Ochtend duur en zonder zon, middag goedkoop met overschot."""
    regels = []
    for kwartier in range(96):
        uur = kwartier // 4
        zon = 2500.0 if 11 <= uur < 16 else 0.0
        prijs = 45.0 if uur < 10 else (22.0 if uur < 16 else 38.0)
        regels.append({
            "tijd": f"{uur:02d}:{(kwartier % 4) * 15:02d}",
            "pv_w": zon, "huis_w": 300.0, "accu_w": 0.0,
            "net_w": 300.0 - zon, "soc": 50.0, "prijs_ct": prijs,
        })
    c.dagverloop = {"2026-09-15": regels}


def test_de_kosten_van_een_cyclus_in_de_zon(make_coordinator, hass):
    """Anderhalf uur draaien om 13:00, 1,0 kWh, met 2,5 kW zon en 300 W
    huis: alles uit de zon, dus geen netkosten."""
    c = make_coordinator({})
    _dag(c)

    uit = c.cycluskosten("wasmachine", NU - timedelta(hours=1), NU, 1.0)

    assert uit["kwh"] == 1.0
    assert uit["kosten_eur"] == pytest.approx(0.0, abs=0.01)
    assert uit["op_netstroom_eur"] == pytest.approx(0.22, abs=0.01)
    assert uit["eigen_opwek_eur"] == pytest.approx(0.22, abs=0.01)


def test_de_kosten_van_een_cyclus_zonder_zon(make_coordinator, hass):
    """Om 08:00, 45 ct, geen zon: alles uit het net."""
    c = make_coordinator({})
    _dag(c)
    start = NU.replace(hour=7)

    uit = c.cycluskosten("vaatwasser", start, start + timedelta(hours=1), 1.0)

    assert uit["kosten_eur"] == pytest.approx(0.45, abs=0.01)
    assert uit["eigen_opwek_eur"] == pytest.approx(0.0, abs=0.01)


def test_wat_het_uitstel_opleverde(make_coordinator, hass):
    """Dezelfde cyclus op het duurste moment van de dag zou meer hebben
    gekost - dat verschil is wat het uitstel opleverde."""
    c = make_coordinator({})
    _dag(c)

    uit = c.cycluskosten("wasmachine", NU - timedelta(hours=1), NU, 1.0)

    assert uit["duurste_moment_eur"] == pytest.approx(0.45, abs=0.02)
    assert uit["uitstel_leverde_op_eur"] == pytest.approx(0.45, abs=0.02)
    # het goedkope blok begint om 10:00 (22 ct), dus dat is het
    # goedkoopste venster van die dag
    assert uit["goedkoopste_moment"] == "10:00"
    assert uit["goedkoopste_moment_eur"] == pytest.approx(0.22, abs=0.01)


def test_zonder_dagverloop_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}

    uit = c.cycluskosten("wasmachine", NU - timedelta(hours=1), NU, 1.0)

    assert uit["te_becijferen"] is False


def test_de_geschiedenis_bewaart_de_laatste_beurten(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CYCLUSKOSTEN_LENGTE,
    )

    c = make_coordinator({})
    _dag(c)
    c.cycluskosten_geschiedenis = {}
    for n in range(CYCLUSKOSTEN_LENGTE + 5):
        c.noteer_cycluskosten(
            "wasmachine", NU - timedelta(hours=1), NU + timedelta(minutes=n), 1.0
        )

    assert len(c.cycluskosten_geschiedenis["wasmachine"]) == CYCLUSKOSTEN_LENGTE


def test_het_overzicht_telt_per_apparaat(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c)
    c.cycluskosten_geschiedenis = {}
    c.noteer_cycluskosten("wasmachine", NU - timedelta(hours=1), NU, 1.0)
    c.noteer_cycluskosten("vaatwasser", NU.replace(hour=7), NU.replace(hour=8), 1.0)

    o = c.get_cycluskosten_overzicht()

    assert o["wasmachine"]["beurten"] == 1
    assert o["vaatwasser"]["gemiddeld_eur"] == pytest.approx(0.45, abs=0.02)
    assert o["wasmachine"]["eigen_opwek_eur_totaal"] > 0


def test_het_overzicht_staat_in_de_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "get_cycluskosten_overzicht" in bron


def test_de_kaart_toont_de_cycluskosten():
    import yaml
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    kaart = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()

    assert "cycluskosten" in kaart
