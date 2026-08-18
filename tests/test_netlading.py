"""De werkelijke netlading, per ronde gemeten (v3.25.0).

Gevraagd: "maar er is vandaag toch wel degelijk bijgekocht?" - en dat
klopte. Er ging 6,90 kWh de accu in, waarvan tussen de 2,02 en 5,93 kWh
van het net.

Op dagniveau is dat niet scherper te krijgen: welk deel precies van het
net kwam hangt af van wat de zon op elk moment leverde. Per ronde wél.

De bijkoop-kandidaat mat het HYPOTHETISCHE geval - had ik moeten laden
bij een verwacht tekort? Maar het laden gebeurde al via de winterguard,
en die meldde zich daar niet. Deze meting rekent de werkelijke handeling
achteraf af.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_PV_POWER_SENSOR,
)

NU = datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc)


def _c(make_coordinator, hass, accu_w, net_w, pv_w, prijs=0.30):
    c = make_coordinator(
        {
            CONF_BATTERY_POWER_SENSOR: "sensor.accu",
            CONF_CONSUMPTION_POWER_SENSOR: "sensor.net",
            CONF_PV_POWER_SENSOR: "sensor.pv",
        }
    )
    hass.states.set("sensor.accu", str(accu_w))
    hass.states.set("sensor.net", str(net_w))
    hass.states.set("sensor.pv", str(pv_w))
    c.last_current_price_per_kwh = prijs
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.22}
    return c


def _twee_rondes(c, minuten=5):
    c._meet_werkelijke_netlading(NU)
    c._meet_werkelijke_netlading(NU + timedelta(minutes=minuten))


def test_charging_from_the_grid_is_counted(make_coordinator, hass):
    """2000 W laden met 2100 W netafname: alles komt van het net."""
    c = _c(make_coordinator, hass, accu_w=2000, net_w=2100, pv_w=0)

    _twee_rondes(c)

    # 2000 W gedurende 5 minuten is 0,167 kWh.
    assert 0.15 < c.netlading_vandaag_kwh < 0.18


def test_charging_from_the_sun_is_not_counted(make_coordinator, hass):
    """Zon in de accu is geen bijkopen - dat is precies het onderscheid
    dat op dagniveau niet te maken was."""
    c = _c(make_coordinator, hass, accu_w=2000, net_w=-100, pv_w=2500)

    _twee_rondes(c)

    assert c.netlading_vandaag_kwh == 0.0


def test_a_mix_counts_only_the_grid_part(make_coordinator, hass):
    """800 W van het net, de rest uit de zon."""
    c = _c(make_coordinator, hass, accu_w=2000, net_w=800, pv_w=1400)

    _twee_rondes(c)

    # 800 W gedurende 5 minuten is 0,067 kWh.
    assert 0.05 < c.netlading_vandaag_kwh < 0.08


def test_discharging_counts_nothing(make_coordinator, hass):
    c = _c(make_coordinator, hass, accu_w=-1600, net_w=-1400, pv_w=0)

    _twee_rondes(c)

    assert c.netlading_vandaag_kwh == 0.0


def test_a_gap_in_the_measurements_is_skipped(make_coordinator, hass):
    """Na een herstart valt er niets betrouwbaars af te leiden - anders
    boekt één ronde uren aan energie."""
    c = _c(make_coordinator, hass, accu_w=2000, net_w=2100, pv_w=0)

    c._meet_werkelijke_netlading(NU)
    c._meet_werkelijke_netlading(NU + timedelta(hours=3))

    assert c.netlading_vandaag_kwh == 0.0


def test_the_cost_price_includes_efficiency_and_wear(
    make_coordinator, hass
):
    """Een kWh in de accu zetten kost meer dan de inkoopprijs."""
    c = _c(make_coordinator, hass, accu_w=2000, net_w=2100, pv_w=0, prijs=0.30)
    c.charge_efficiency_history = [90.0] * 3
    c.discharge_efficiency_history = [90.0] * 3
    _twee_rondes(c)

    o = c.get_netlading_overview()

    assert o["gemiddelde_inkoop_ct"] == 30.0
    assert o["kostprijs_uit_de_accu_ct"] > 30.0


def test_without_charging_it_says_so(make_coordinator, hass):
    c = _c(make_coordinator, hass, accu_w=0, net_w=100, pv_w=0)

    assert c.get_netlading_overview()["beschikbaar"] is False


def test_the_counters_survive_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    for veld in ("netlading_vandaag_kwh", "netlading_kosten_eur"):
        assert veld in PERSISTED_PLAIN_FIELDS


def test_the_counters_reset_at_midnight():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("self.grid_charge_today_kwh = 0.0")
    blok = bron[kop : kop + 220]

    assert "self.netlading_vandaag_kwh = 0.0" in blok
    assert "self.netlading_kosten_eur = 0.0" in blok
