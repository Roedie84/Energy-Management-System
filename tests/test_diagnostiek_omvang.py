"""De diagnostiek-export mag geen dubbele last dragen (v3.31.0).

Gevraagd: "Is de generatie van de diagnostiek nu ook helemaal
geoptimaliseerd?"

Nee. Gemeten aan de export van 19 augustus 11:22:

    totaal                      1.243 KB
      persisted_state_snapshot    604 KB   ← de helft
      battery_module_health       109 KB
      notification_history         84 KB

Van die 604 KB is 496 KB een tweede afdruk van reeksen die er al los in
staan - maar dan ONGEKORT. De export knipt `energy_daily_history` netjes
af op 30 regels; de momentopname ernaast draagt alle 400. Hetzelfde geldt
voor `bijkoop_history` (30 tegen 300) en `lange_reserve_history`.

Die momentopname is er om te zien wat een herstart overleeft. Daarvoor is
de VORM genoeg: welke velden, hoeveel regels, hoe groot. De inhoud staat
er verderop al, en waar hij er niet staat is een samenvatting genoeg om
te zien dat het veld gevuld is.

Daarnaast 1.298 kommagetallen met tien of meer decimalen -
0.024999999999999998 waar 0.025 bedoeld is. Dat is een artefact van
drijvendekomma-rekenwerk en kost per stuk vijftien tekens.
"""
import json

from custom_components.energy_management_system.diagnostics import (
    _beknopt,
    _kort_af,
)


# --- 1. lange reeksen worden samengevat ------------------------------


def test_a_long_series_becomes_a_summary():
    """400 dagregels in de momentopname naast 30 in de export ernaast."""
    reeks = [{"datum": f"2026-08-{d:02d}", "opwek_kwh": 20.0} for d in range(1, 29)]

    uit = _beknopt(reeks, drempel=10)

    assert uit["soort"] == "lijst"
    assert uit["regels"] == 28
    assert "voorbeeld" in uit


def test_a_short_series_is_left_alone():
    """Onder de drempel is samenvatten alleen maar verlies."""
    reeks = [1, 2, 3]

    assert _beknopt(reeks, drempel=10) == [1, 2, 3]


def test_a_big_dictionary_becomes_a_summary():
    groot = {str(i): [0.1] * 200 for i in range(3)}

    uit = _beknopt(groot, drempel=10)

    assert uit["soort"] == "map"
    assert uit["sleutels"] == 3


def test_plain_values_pass_through():
    for waarde in (None, True, 3, "tekst", 1.5):
        assert _beknopt(waarde, drempel=10) == waarde


def test_the_summary_says_how_big_it_was():
    """Zonder omvang is niet te zien of een veld vol of bijna leeg is."""
    uit = _beknopt([{"x": 1}] * 50, drempel=10)

    assert uit["ongeveer_kb"] > 0


# --- 2. kommagetallen afronden ---------------------------------------


def test_a_float_artefact_is_rounded():
    """0.024999999999999998 is 0,025 met vijftien tekens ruis erachter."""
    assert _kort_af(0.024999999999999998) == 0.025


def test_meaningful_precision_survives():
    """Zes decimalen is ruim voor alles wat hier gemeten wordt: watt,

    kWh, euro's en graden.
    """
    assert _kort_af(0.123456789) == 0.123457
    assert _kort_af(2024.5) == 2024.5


def test_rounding_reaches_into_nested_structures():
    ruw = {"reeks": [0.024999999999999998, {"diep": 1.0000000000000002}]}

    uit = _kort_af(ruw)

    assert uit["reeks"][0] == 0.025
    assert uit["reeks"][1]["diep"] == 1.0


def test_rounding_leaves_everything_else_alone():
    ruw = {"tekst": "0.024999999999999998", "waar": True, "niets": None, "n": 7}

    assert _kort_af(ruw) == ruw


def test_booleans_do_not_become_numbers():
    """In Python is True een int; afronden zou er 1 van maken."""
    uit = _kort_af([True, False])

    assert uit == [True, False]
    assert isinstance(uit[0], bool)


# --- 3. het effect ---------------------------------------------------


def test_a_realistic_snapshot_shrinks_a_lot():
    """De gemeten verhoudingen van 19 augustus, klein nagebouwd."""
    momentopname = {
        "energy_daily_history": [
            {"datum": f"d{i}", "opwek_kwh": 20.123456789012345} for i in range(400)
        ],
        "bijkoop_history": [{"moment": f"m{i}", "ct": 1.0} for i in range(300)],
        "kalibratie": True,
        "learned_night_consumption_kw": 0.19700000000000001,
    }
    voor = len(json.dumps(momentopname))

    na = len(
        json.dumps(
            _kort_af({k: _beknopt(v, drempel=25) for k, v in momentopname.items()})
        )
    )

    assert na < voor / 10
    # en de kleine velden blijven gewoon leesbaar
    beknopt = {k: _beknopt(v, drempel=25) for k, v in momentopname.items()}
    assert beknopt["kalibratie"] is True


# --- 4. de ruwe modulemetingen ---------------------------------------


def test_raw_module_samples_become_a_range():
    """De vijf reeksen van 740 monsters per module waren samen 70 KB.

    Wat er bij de diagnose van 19 augustus uit gelezen werd was het
    bereik - "celspreiding liep deze week op van 0,190 naar 0,460 V" -
    en de laatste waarde.
    """
    from custom_components.energy_management_system.diagnostics import (
        _beknopte_modulegezondheid,
    )

    gezondheid = {
        "1": {
            "dag_metingen": {"cel_delta_v": [0.03, 0.46, 0.19, 0.01]},
            "soc_buckets": {"70": [0.0, 0.01, 0.01]},
            "geschiedenis": {"cel_delta_afwijking_v": [0.015, 0.01]},
            "waarschuwingen": ["celspanningsverschil 0.460 V bij 12%"],
        }
    }

    uit = _beknopte_modulegezondheid(gezondheid)
    reeks = uit["1"]["dag_metingen"]["cel_delta_v"]

    assert reeks["metingen"] == 4
    assert reeks["hoogste"] == 0.46
    assert reeks["laatste"] == 0.01


def test_the_daily_series_and_the_warnings_stay_whole():
    """Het dagoverzicht draagt de trend over dagen en is klein; de

    waarschuwing is het hele punt van die kaart.
    """
    from custom_components.energy_management_system.diagnostics import (
        _beknopte_modulegezondheid,
    )

    gezondheid = {
        "1": {
            "geschiedenis": {"cel_delta_afwijking_v": [0.015, 0.01, 0.03]},
            "waarschuwingen": ["celspanningsverschil 0.460 V bij 12%"],
        }
    }

    uit = _beknopte_modulegezondheid(gezondheid)

    assert uit["1"]["geschiedenis"]["cel_delta_afwijking_v"] == [0.015, 0.01, 0.03]
    assert uit["1"]["waarschuwingen"] == [
        "celspanningsverschil 0.460 V bij 12%"
    ]


def test_an_empty_series_does_not_crash():
    from custom_components.energy_management_system.diagnostics import (
        _reeks_samenvatting,
    )

    assert _reeks_samenvatting([])["metingen"] == 0
    assert _reeks_samenvatting([None, "x"])["metingen"] == 2
