"""v5.31.1 - geen valse drift op de laadstand van een accumodule.

Gemeld op 6 oktober: "Module 2 is niets mis mee?" De diagnose meldde
"Accumodule 2 loopt aanhoudend uit de pas (soc_afwijking_percent)", terwijl
de celdelta 0,00 V was en de temperatuur gelijk aan module 3.

De laadstand komt per hele procent binnen; de afwijking van het gemiddelde
van de andere modules springt in stappen van een half procent. Met een
speling van 0,5% telden een paar dagen +1 à +1,5% op tot 5,5 - boven de
drempel van 5. Nu telt een SoC-afwijking pas vanaf 3% mee.

De reeksen hieronder zijn de echte dagwaarden uit de export van 6 oktober.
"""
from custom_components.energy_management_system.const import (
    BATTERY_MODULE_CUSUM_SLACK_PERCENT,
)

SOC_MODULE_2 = [0.0, 0.0, -1.0, 0.5, 0.0, 0.0, 0.0, -0.5, -0.5, 0.0, -0.5, -0.5, 0.5, 0.0, -0.5, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.5, 0.0, 0.5, 0.5, 0.0, 0.5, 1.0, -1.0, 0.0, 1.0, -0.5, 1.0, -0.5, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.5, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.5, -0.5, 1.0, 0.0, 1.0, -0.5, 1.0, 1.5]
CEL_MODULE_1 = [0.01, 0.03, 0.04, 0.01, 0.02, 0.04, 0.03, 0.04, 0.025, 0.025, 0.03, 0.03, 0.04, 0.01, 0.025, 0.04, 0.04, 0.02, 0.02, 0.04, 0.025, 0.035, 0.02, 0.03, 0.025, 0.02, 0.02, 0.02, 0.025, 0.05, 0.045, 0.02, 0.02, 0.02, 0.025, 0.01, 0.04, 0.015, 0.02, 0.01, 0.02, 0.02, 0.02, 0.01, 0.025, 0.025, 0.01, 0.03, 0.03, 0.04, 0.03, 0.025, 0.02, 0.03, 0.05, 0.03, 0.03, 0.04, 0.05, 0.015]


def _module(veld, reeks, cusum):
    return {"geschiedenis": {veld: list(reeks)}, "cusum": {veld: dict(cusum)}, "dag_metingen": {}, "soc_buckets": {}}


def _doorrekenen(c, veld, reeks):
    staat = {"geschiedenis": {}, "cusum": {}, "dag_metingen": {}, "soc_buckets": {}}
    for dag, waarde in enumerate(reeks):
        staat["geschiedenis"][veld] = list(reeks[: dag + 1])
        c._update_battery_module_cusum(staat, veld, waarde)
    return staat["cusum"][veld]


def test_de_speling_past_bij_hele_procenten():
    assert BATTERY_MODULE_CUSUM_SLACK_PERCENT >= 2.5


def test_module_2_heeft_geen_drift(make_coordinator):
    c = make_coordinator({})
    cusum = _doorrekenen(c, "soc_afwijking_percent", SOC_MODULE_2)
    assert cusum["drift"] is False
    assert cusum["accumulator"] == 0.0


def test_een_echte_soc_afwijking_wordt_nog_gezien(make_coordinator):
    c = make_coordinator({})
    reeks = SOC_MODULE_2[:40] + [4.0, 4.5, 4.0, 5.0, 4.5]
    assert _doorrekenen(c, "soc_afwijking_percent", reeks)["drift"] is True


def test_module_1_celspreiding_blijft_drift(make_coordinator):
    c = make_coordinator({})
    assert _doorrekenen(c, "cel_delta_afwijking_v", CEL_MODULE_1)["drift"] is True


def test_een_opgeslagen_valse_drift_verdwijnt_meteen(make_coordinator):
    """De drift van module 2 staat al in de opslag. Die moet weg zonder op
    middernacht of vijf rustige dagen te wachten."""
    c = make_coordinator({})
    c.battery_module_health = {
        "2": _module(
            "soc_afwijking_percent",
            SOC_MODULE_2,
            {"accumulator": 5.5, "referentie": 0.0, "drift": True, "streak": 0},
        )
    }
    c._herijk_module_cusums()
    cusum = c.battery_module_health["2"]["cusum"]["soc_afwijking_percent"]
    assert cusum["drift"] is False
    assert cusum["parameters"][0] == BATTERY_MODULE_CUSUM_SLACK_PERCENT


def test_herijken_laat_de_echte_drift_van_module_1_staan(make_coordinator):
    c = make_coordinator({})
    c.battery_module_health = {
        "1": _module(
            "cel_delta_afwijking_v",
            CEL_MODULE_1,
            {"accumulator": 0.06, "referentie": 0.025, "drift": True, "streak": 1},
        )
    }
    c._herijk_module_cusums()
    assert c.battery_module_health["1"]["cusum"]["cel_delta_afwijking_v"]["drift"] is True


def test_herijken_gebeurt_maar_een_keer(make_coordinator):
    c = make_coordinator({})
    c.battery_module_health = {
        "2": _module("soc_afwijking_percent", SOC_MODULE_2, {"accumulator": 5.5, "drift": True, "streak": 0})
    }
    c._herijk_module_cusums()
    cusum = c.battery_module_health["2"]["cusum"]["soc_afwijking_percent"]
    cusum["accumulator"] = 1.25   # verder opgebouwd na het herijken
    c._herijk_module_cusums()
    assert c.battery_module_health["2"]["cusum"]["soc_afwijking_percent"]["accumulator"] == 1.25


def test_de_drift_melding_noemt_module_2_niet_meer(make_coordinator):
    c = make_coordinator({})
    c.battery_module_health = {
        "1": _module("cel_delta_afwijking_v", CEL_MODULE_1, {"accumulator": 0.06, "drift": True, "streak": 1}),
        "2": _module("soc_afwijking_percent", SOC_MODULE_2, {"accumulator": 5.5, "drift": True, "streak": 0}),
    }
    c._herijk_module_cusums()
    met_drift = [
        nummer
        for nummer, staat in c.battery_module_health.items()
        if any(v.get("drift") for v in staat["cusum"].values())
    ]
    assert met_drift == ["1"]


def test_andere_velden_worden_niet_opnieuw_doorgerekend(make_coordinator):
    """Alleen de laadstand kreeg een andere speling. Een drift op de
    temperatuur of de celdelta blijft precies zoals hij was opgeslagen."""
    c = make_coordinator({})
    c.battery_module_health = {
        "1": {
            "geschiedenis": {},
            "cusum": {"temperatuur_afwijking_c": {"accumulator": 6.0, "drift": True, "streak": 0}},
            "dag_metingen": {},
            "soc_buckets": {},
        }
    }
    c._herijk_module_cusums()
    cusum = c.battery_module_health["1"]["cusum"]["temperatuur_afwijking_c"]
    assert cusum["drift"] is True and cusum["accumulator"] == 6.0
