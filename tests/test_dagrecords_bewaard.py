"""De dagrecords overleven een herstart alleen half (v3.99.1).

Gevonden bij de volledige doorlichting.

`reserve_daily_records` staat in geen enkele bewaarlijst. Hij overleeft
een herstart doordat twee SENSOREN elk hun helft in hun eigen
entiteitsattributen bewaren en bij het opstarten weer samenvoegen:
ReserveShortfallSensor de tekortdagen, ReserveExcessSensor de
overschotdagen. Dat werkt - voor die twee velden.

In v3.99.0 zijn er twee velden bijgekomen: `vermogensgrens` en
`max_ontlaad_w`. Die staan in geen enkele sensor. Na elke herstart zijn
ze weg, en dat is precies de informatie waarmee de kookpieken van de
echte tekortdagen onderscheiden moesten worden.

Dit is het patroon dat v3.42.1 al voor de kalibratie afkeurde: twee
bronnen voor hetzelfde gegeven. De records gaan nu in de opslag; de
sensorherstel-route blijft als vangnet en overschrijft niets.
"""
from custom_components.energy_management_system.const import (
    PERSISTED_PLAIN_FIELDS,
)


def test_de_dagrecords_staan_in_de_opslag():
    assert "reserve_daily_records" in PERSISTED_PLAIN_FIELDS


def test_de_sensorroute_bewaart_de_extra_velden(make_coordinator, hass):
    """Komt de opslag eerst en daarna de sensor, dan mag de sensor de

    velden uit de opslag niet wegpoetsen.
    """
    from custom_components.energy_management_system.sensor import (
        _merge_reserve_daily_records,
    )

    uit_opslag = [
        {
            "date": "2026-09-01",
            "shortfall": True,
            "excess": False,
            "vermogensgrens": True,
            "max_ontlaad_w": {"handmatig": 1580, "slim": 1940},
        }
    ]

    samen = _merge_reserve_daily_records(
        uit_opslag, ["2026-09-01"], shortfall_values=[True]
    )

    assert samen[0]["vermogensgrens"] is True
    assert samen[0]["max_ontlaad_w"] == {"handmatig": 1580, "slim": 1940}
