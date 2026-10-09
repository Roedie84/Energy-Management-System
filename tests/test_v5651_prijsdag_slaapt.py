"""De dagbedragen van de leverancier na middernacht (v5.65.1).

Gemeten op 9 oktober: `sensor.zonneplan_gas_delivery_costs_today` en
`sensor.zonneplan_afname_vandaag_excl_btw` stonden 00:02-01:07 op
`unknown`. De configuratiecontrole telde dat als kapotte koppeling. Tot
03:00 hoort dat "slaapt" te zijn, daarna weer een storing.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system import coordinator as coord_mod

ENT = "sensor.zonneplan_gas_delivery_costs_today"


def _regel(make_coordinator, hass, monkeypatch, waarde, uur):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["gas_eur_vandaag_sensor_entity"] = ENT
    hass.states.set(ENT, waarde, {"unit_of_measurement": "EUR"})
    monkeypatch.setattr(
        coord_mod.dt_util, "now", lambda *a: datetime(2026, 10, 9, uur, 30, tzinfo=timezone.utc)
    )
    controle = c.get_configuratiecontrole()
    regel = next(
        r for r in controle["entiteiten"] if r["instelling"] == "gas_eur_vandaag_sensor_entity"
    )
    return regel, controle


def test_na_middernacht_slaapt_het_dagbedrag(make_coordinator, hass, monkeypatch):
    regel, controle = _regel(make_coordinator, hass, monkeypatch, "unknown", 0)
    assert regel["oordeel"] == "slaapt"
    assert controle["aantal_stuk"] == 0


def test_na_drie_uur_is_het_weer_een_storing(make_coordinator, hass, monkeypatch):
    regel, _ = _regel(make_coordinator, hass, monkeypatch, "unknown", 3)
    assert regel["oordeel"] == "geen_waarde"


def test_met_een_waarde_in_orde(make_coordinator, hass, monkeypatch):
    regel, _ = _regel(make_coordinator, hass, monkeypatch, "0.0276", 1)
    assert regel["oordeel"] == "in_orde"
