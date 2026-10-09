"""v5.57 - leerronde 9 oktober: meten over een herstart heen.

Op 8 oktober (20 herstarts) stonden 74 van de 96 kwartieren in de meetlog:
het kwartier waarin Home Assistant herstartte had geen beginstand. De
tellers lopen in de apparaten door, dus met de bewaarde stand van de laatste
grens is dat kwartier wel te meten. Stuurt niets.
"""
import json
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import kwartierenergie
from custom_components.energy_management_system.meetlaag import (
    Meetlaag,
    _kwartieren_op_dag,
    schaduw_dagrapport,
)

TELLERS = {
    "grid_import_energy_sensor_entity": "sensor.p1_import",
    "grid_export_energy_sensor_entity": "sensor.p1_export",
    "pv_energy_sensor_entity": "sensor.pv_totaal",
    "battery_discharge_energy_sensor_entity": "sensor.accu_uit",
    "battery_charge_energy_sensor_entity": "sensor.accu_in",
}


def _zet(hass, waarden):
    for entiteit, waarde in waarden.items():
        hass.states.set(entiteit, str(waarde), {"unit_of_measurement": "kWh", "state_class": "total_increasing"})


def _grens():
    nu = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=2)))
    return nu.replace(minute=nu.minute // 15 * 15, second=0, microsecond=0)


BEGIN = {"sensor.p1_import": 100.0, "sensor.p1_export": 50.0, "sensor.pv_totaal": 200.0,
         "sensor.accu_uit": 30.0, "sensor.accu_in": 40.0}
EIND = {"sensor.p1_import": 100.1, "sensor.p1_export": 50.0, "sensor.pv_totaal": 200.4,
        "sensor.accu_uit": 30.0, "sensor.accu_in": 40.3}


def _herstart(c):
    """Wat de opslag na een herstart teruggeeft: JSON, geen Python-objecten."""
    c.meetlaag_kwartierstanden = json.loads(json.dumps(c.meetlaag_kwartierstanden))
    return Meetlaag(c)


def test_het_kwartier_van_een_herstart_wordt_gemeten(make_coordinator, hass):
    c = make_coordinator(dict(TELLERS))
    g = _grens()
    _zet(hass, BEGIN)
    Meetlaag(c)._kwartiergrens(g - timedelta(minutes=15))
    assert c.meetlaag_kwartierstanden["grens"] == (g - timedelta(minutes=15)).isoformat()

    m = _herstart(c)
    _zet(hass, EIND)
    m._kwartiergrens(g)
    k = m.laatste_kwartier
    assert k is not None and k["over_herstart"] is True
    assert k["house_kwh"] == 0.2
    assert k["kwaliteit_per_teller"]["grid_import"] != "invalid"
    # accutellers van zendure_ha telden tijdens de herstart niet: nooit "measured"
    assert k["kwaliteit_per_teller"]["battery_in"] == "partially_estimated"
    assert k["kwaliteit_per_teller"]["battery_out"] == "partially_estimated"
    assert m.kwartieren_over_herstart == 1


def test_een_langere_onderbreking_blijft_ongemeten(make_coordinator, hass):
    c = make_coordinator(dict(TELLERS))
    g = _grens()
    _zet(hass, BEGIN)
    Meetlaag(c)._kwartiergrens(g - timedelta(minutes=30))
    m = _herstart(c)
    _zet(hass, EIND)
    m._kwartiergrens(g)
    assert m.laatste_kwartier is None


def test_een_andere_teller_geeft_nooit_een_verschil(make_coordinator, hass):
    """L-EMS-003: van de cloud-dagteller naar de Modbus-levensteller gaf een
    verschil van 23.414 kWh. Een bewaarde stand van een andere teller telt
    dus nooit."""
    c = make_coordinator(dict(TELLERS))
    g = _grens()
    _zet(hass, BEGIN)
    Meetlaag(c)._kwartiergrens(g - timedelta(minutes=15))
    c.config["pv_energy_sensor_entity"] = "sensor.pv_modbus"
    m = _herstart(c)
    _zet(hass, dict(EIND, **{"sensor.pv_modbus": 23426.0}))
    m._kwartiergrens(g)
    assert m.laatste_kwartier is None


def test_alleen_de_eerste_grens_na_de_start_gebruikt_de_bewaarde_stand(make_coordinator, hass):
    c = make_coordinator(dict(TELLERS))
    g = _grens()
    _zet(hass, BEGIN)
    Meetlaag(c)._kwartiergrens(g - timedelta(minutes=15))
    m = _herstart(c)
    _zet(hass, EIND)
    m._kwartiergrens(g)
    m._kwartiergrens(g + timedelta(minutes=15))
    assert not m.laatste_kwartier.get("over_herstart")


def test_het_kenmerk_overleeft_de_opslagvorm():
    g = datetime(2026, 10, 9, 12, 15, tzinfo=timezone(timedelta(hours=2)))
    begin = {t: kwartierenergie.stand(v, g - timedelta(minutes=15), g - timedelta(minutes=15))
             for t, v in zip(kwartierenergie.TELLERS, (100.0, 50.0, 200.0, 30.0, 40.0))}
    eind = {t: kwartierenergie.stand(v, g, g)
            for t, v in zip(kwartierenergie.TELLERS, (100.1, 50.0, 200.4, 30.0, 40.3))}
    record = kwartierenergie.kwartier(g - timedelta(minutes=15), begin, eind, 0.25)
    assert "over_herstart" not in kwartierenergie.uitpakken(kwartierenergie.compact(record))
    record["over_herstart"] = True
    assert kwartierenergie.uitpakken(kwartierenergie.compact(record))["over_herstart"] is True


def test_kwartieren_op_een_dag_ook_bij_de_klokwissel():
    zomer = timezone(timedelta(hours=2))
    assert _kwartieren_op_dag([{"kwartier": "2026-10-08T00:00:00+02:00"}]) == 96
    assert _kwartieren_op_dag([{"kwartier": "2026-10-25T00:00:00+02:00"}]) == 100
    assert _kwartieren_op_dag([{"kwartier": "2026-03-29T00:00:00+01:00"}]) == 92
    assert zomer  # tijdzone met vaste afwijking: de dag volgt Europe/Amsterdam


def test_het_dagrapport_telt_wat_er_ontbreekt():
    g = datetime(2026, 10, 8, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    kwartieren = []
    for i in range(74):
        k = {"kwartier": (g + timedelta(minutes=15 * i)).isoformat(), "house_kwh": 0.1, "pv_kwh": 0.0,
             "prijs_eur": 0.25, "coverage_percent": 100.0}
        if i == 3:
            k["over_herstart"] = True
        kwartieren.append(k)
    uit = schaduw_dagrapport([], kwartieren, 8.64, 84.2)
    assert uit["kwartieren_gemeten"] == 74
    assert uit["kwartieren_niet_gemeten"] == 22
    assert uit["kwartieren_over_herstart"] == 1


def test_kalibratie_toont_de_laatste_avond_al_dezelfde_avond(make_coordinator):
    c = make_coordinator({})
    c.mc_22u_per_avond = {
        "2026-10-07": {"tijd": "22:00", "kans_pct": 14.6, "basis": "oud"},
        "2026-10-08": {"tijd": "22:00", "kans_pct": 0.0, "basis": "tot_blok",
                       "kans_incl_lange_horizon_pct": 100, "beschikbaar_kwh": 3.9},
    }
    k = c.get_mc_kalibratie_22u()
    assert k["laatste_avond"]["avond"] == "2026-10-08"
    assert k["laatste_avond"]["kans_pct"] == 0.0
    assert k["avonden_bewaard"] == 2
    leeg = make_coordinator({}).get_mc_kalibratie_22u()
    assert leeg["laatste_avond"] is None and leeg["avonden_bewaard"] == 0
