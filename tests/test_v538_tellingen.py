"""Tekortnacht tot nu, kWh van oude records, accustekker, slapende koppelingen (v5.38).

Uit de uuranalyse van 7 oktober 14:15:
- `detected_today_so_far` stond vanaf 00:25 op true en las als "vandaag is
  een tekortdag", terwijl er die nacht niets werd bijgekocht;
- `tekort_kwh_per_nacht` gaf 7x 0 bij 4 tekortnachten (records van voor v5.33);
- de grootverbruikers bevatten de eigen accu-meetstekker;
- diagnose zei "config 70/0/1", de cockpit "koppelingen 71/71".
"""


def test_de_lopende_nacht_beslist_niet_het_signaal(make_coordinator, hass):
    c = make_coordinator({})
    c._shortfall_detected_today = True
    c._tekortnacht_lopend_kwh = 0.0

    stand = c.tekortnacht_tot_nu()

    assert stand["tekortnacht_tot_nu_kwh"] == 0.0
    assert stand["telt_als_tekortdag_tot_nu"] is False


def test_een_echt_tekort_telt_wel(make_coordinator, hass):
    c = make_coordinator({})
    c._tekortnacht_lopend_kwh = 1.2
    assert c.tekortnacht_tot_nu()["telt_als_tekortdag_tot_nu"] is True


def test_oude_records_vallen_terug_op_de_netimport(make_coordinator, hass):
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"shortfall": True, "netimport_nacht_kwh": 1.44},
        {"shortfall": False, "netimport_nacht_kwh": 0.79},
        {"shortfall": True, "tekortnacht_kwh": 0.6, "netimport_nacht_kwh": 2.0},
    ]
    v = c.get_monte_carlo_vergelijking()

    assert v["tekort_kwh_per_nacht"] == [1.44, 0.0, 0.6]
    assert v["tekort_kwh_benaderd"] == [True, False, False]
    assert v["tekort_kwh_laatste_7"] == 2.04


def test_de_accusensor_is_geen_grootverbruiker(make_coordinator, hass):
    c = make_coordinator({"battery_power_sensor_entity": "sensor.accu_stekker"})
    assert "sensor.accu_stekker" in c._geen_grootverbruiker()


def test_verdwenen_bronnen_worden_vergeten(make_coordinator, hass):
    from datetime import datetime

    c = make_coordinator({})
    c.grootverbruiker_leer = {"sensor.bestaat_niet": {"naam": "weg"}}
    c._leer_grootverbruikers(datetime(2026, 10, 7, 14, 0))
    assert "sensor.bestaat_niet" not in c.grootverbruiker_leer


def test_de_cockpit_noemt_slapende_koppelingen():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    assert 'f" ({slaapt} slaapt)"' in bron
