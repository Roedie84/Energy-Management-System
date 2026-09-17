"""Intraday-herschaling: als SCHADUW, niet als sturing (v5.2).

De code zei het zelf al, in `_duid_plan_review`: "Dit is het punt waar
stap twee - zelf bijstellen - op zou kunnen aanhaken. Voorlopig alleen
benoemen."

Het idee: om 11:00 weet het EMS hoeveel er al binnen is tegen wat er
voorspeld was. Die verhouding zegt iets over de rest van de dag, en de
resterende voorspelling wordt nu NIET bijgesteld - `al_opgewekt` en
`nog_te_komen` worden alleen bij elkaar opgeteld.

Aantrekkelijk omdat het de dominante foutbron aanvalt: na v4.12 valt het
gemiste bedrag vrijwel volledig op de voorspelling (0,87 van 0,92 euro
op 10 september).

MAAR: het bewijs is er nog niet. De zonpersistentiemeting van v5.1 gaf
r = +0,69 over acht dagen, met twee dagen die de verkeerde kant op
gingen, en noemt zelf pas een richting bij twintig dagen. Dus meet deze
versie wat de herschaling ZOU hebben gedaan, en stuurt niets.

De terugtoetsbank van deze versie beoordeelt hem: de herschaalde
voorspelling tegen de kale, op de opgeslagen dagen.
"""
import pytest


def test_de_herschaling_gebruikt_de_verhouding_tot_nu_toe(make_coordinator, hass):
    """Ochtend deed 60% van wat er voorspeld was, dus de rest van de dag
    wordt met 0,6 herschaald."""
    c = make_coordinator({})

    uit = c.herschaalde_zon_rest_van_de_dag(
        voorspeld_tot_nu=4.0, gerealiseerd_tot_nu=2.4, voorspeld_rest=5.0
    )

    assert uit["verhouding"] == pytest.approx(0.6, abs=0.01)
    assert uit["herschaald_kwh"] == pytest.approx(3.0, abs=0.01)
    assert uit["kaal_kwh"] == 5.0


def test_de_herschaling_wordt_begrensd(make_coordinator, hass):
    """Een ochtend die 300% doet mag de middag niet verdrievoudigen - de
    persistentiemeting gaf r=0,69, niet r=1,0."""
    from custom_components.energy_management_system.const import (
        HERSCHALING_MAX_FACTOR,
        HERSCHALING_MIN_FACTOR,
    )

    c = make_coordinator({})

    hoog = c.herschaalde_zon_rest_van_de_dag(1.0, 3.0, 5.0)
    laag = c.herschaalde_zon_rest_van_de_dag(4.0, 0.1, 5.0)

    assert hoog["factor_gebruikt"] == HERSCHALING_MAX_FACTOR
    assert laag["factor_gebruikt"] == HERSCHALING_MIN_FACTOR
    assert HERSCHALING_MAX_FACTOR < 2.0


def test_te_vroeg_op_de_dag_geen_herschaling(make_coordinator, hass):
    """Om 08:00 is er nog vrijwel niets binnen; dan zegt de verhouding
    niets en is herschalen ruis versterken."""
    from custom_components.energy_management_system.const import (
        HERSCHALING_MIN_VOORSPELD_KWH,
    )

    c = make_coordinator({})

    uit = c.herschaalde_zon_rest_van_de_dag(0.2, 0.05, 6.0)

    assert uit["herschaald_kwh"] == 6.0
    assert "te weinig" in uit["reden"].lower()
    assert HERSCHALING_MIN_VOORSPELD_KWH >= 0.5


def test_de_schaduw_stuurt_niets(make_coordinator, hass):
    """De ratel: de herschaling mag nergens in een beslispad staan
    zolang de persistentiemeting geen twintig dagen heeft."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    aanroepen = bron.count("herschaalde_zon_rest_van_de_dag(")

    # eenmaal de definitie, eenmaal de terugtoetsregel - nergens anders
    assert aanroepen <= 3, aanroepen
    for beslisser in ("_async_update_locked", "may_sell_now", "get_quarter_plan"):
        i = bron.index(f"def {beslisser}")
        j = bron.index("\n    def ", i + 10)
        assert "herschaalde_zon" not in bron[i:j], beslisser


def test_de_terugtoets_vergelijkt_herschaald_met_kaal(make_coordinator, hass):
    """Waar de bank voor is: het idee beoordelen voordat het maanden
    meet."""
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.effective_min_soc_percent = lambda: 10.0
    c.dagverloop = {
        f"2026-09-{d:02d}": [
            {
                "tijd": f"{i // 4:02d}:{(i % 4) * 15:02d}",
                "prijs_ct": 25.0 + (i % 8),
                "huis_w": 300.0,
                "pv_w": 1500.0 if 8 <= i // 4 < 17 else 0.0,
                "accu_w": 0.0,
                "soc": 50.0,
                "reden": "default_smart",
            }
            for i in range(96)
        ]
        for d in range(1, 5)
    }

    uit = c.terugtoets_intraday_herschaling()

    assert uit["dagen"] == 4
    assert "kaal" in uit
    assert "herschaald" in uit
    assert uit["verschil_eur_per_dag"] is not None


def test_de_terugtoets_zegt_dat_het_bewijs_nog_ontbreekt(make_coordinator, hass):
    """Anders leest iemand het verschil als groen licht."""
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.dagverloop = {}

    uit = c.terugtoets_intraday_herschaling()

    assert "persistentie" in uit["voorbehoud"].lower()
    assert "20" in uit["voorbehoud"]
