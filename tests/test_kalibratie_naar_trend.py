"""De kalibratiemeting bereikte de capaciteitstrend nooit (v3.99.3).

v3.29.0 meet tijdens een kalibratie hoeveel kWh er in de accu gaat en
over welk deel van de schaal, en rekent daaruit een capaciteit. Die
meting landde in `kalibratie_momentopname` - en nergens anders.
`capacity_trend_history`, waar `gemeten_capaciteit_kwh()` uit leest,
kreeg elke dag opnieuw de nominale sensor (v3.92.5). De bron bestond, de
verbinding niet.

Op 19 augustus: 71 naar 99 procent, 3,1 kWh geladen. Dat is 28% van de
schaal - onder de eis van 70%, dus terecht geen meting. Een volgende
kalibratie moet onder de 30% beginnen om te tellen.

En wat er in gaat is meer dan wat er in blijft: laadverlies. De
gemeten capaciteit wordt gecorrigeerd met de wortel van het geleerde
rondgangsrendement - de aanname dat laden en ontladen elk de helft van
het verlies dragen. Dat is een AANNAME, en zo staat hij er ook bij.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)


def _meting(c, begin_soc, eind_soc, kwh_in, rendement=84.0):
    c.kalibratie_meting = {
        "begin_soc": begin_soc,
        "eind_soc": eind_soc,
        "kwh_in": kwh_in,
        "gemeten_capaciteit_kwh": round(kwh_in / ((eind_soc - begin_soc) / 100), 2),
    }
    type(c).learned_battery_efficiency_percent = property(lambda self: rendement)


def test_een_geldige_meting_komt_in_de_trend(make_coordinator, hass, monkeypatch):
    c = make_coordinator({})
    c.capacity_trend_history = []
    monkeypatch.setattr(type(c), "learned_battery_efficiency_percent", property(lambda self: 84.0))
    c.kalibratie_meting = {"begin_soc": 12.0, "eind_soc": 99.0, "kwh_in": 8.2,
                           "gemeten_capaciteit_kwh": round(8.2 / 0.87, 2)}

    c._kalibratie_naar_trend(NU)

    assert len(c.capacity_trend_history) == 1
    regel = c.capacity_trend_history[0]
    assert regel["bron"] == "kalibratie"
    # 9,43 nominaal-equivalent x sqrt(0,84) = 8,64
    assert regel["capaciteit_kwh"] == pytest.approx(9.43 * 0.84 ** 0.5, abs=0.05)
    assert regel["laadrendement_aanname"] == pytest.approx(0.84 ** 0.5, abs=0.001)


def test_zonder_gemeten_capaciteit_niets(make_coordinator, hass):
    """Het geval van 19 augustus: 28% van de schaal, geen meting."""
    c = make_coordinator({})
    c.capacity_trend_history = []
    c.kalibratie_meting = {"begin_soc": 71.0, "eind_soc": 99.0, "kwh_in": 3.1,
                           "gemeten_capaciteit_kwh": None}

    c._kalibratie_naar_trend(NU)

    assert c.capacity_trend_history == []


def test_dezelfde_kalibratie_niet_twee_keer(make_coordinator, hass, monkeypatch):
    c = make_coordinator({})
    c.capacity_trend_history = []
    monkeypatch.setattr(type(c), "learned_battery_efficiency_percent", property(lambda self: 84.0))
    c.kalibratie_meting = {"begin_soc": 12.0, "eind_soc": 99.0, "kwh_in": 8.2,
                           "gemeten_capaciteit_kwh": 9.43}

    c._kalibratie_naar_trend(NU)
    c._kalibratie_naar_trend(NU)

    assert len(c.capacity_trend_history) == 1


def test_de_kalibratieregel_wint_van_de_nominale(make_coordinator, hass):
    """`gemeten_capaciteit_kwh()` neemt de mediaan van de reeks. Eén

    kalibratie tussen 29 nominale regels verdwijnt daarin. Kalibratie-
    regels tellen daarom apart, en als die er zijn winnen ze.
    """
    c = make_coordinator({"battery_total_capacity_sensor_entity": "sensor.capaciteit"})
    hass.states.set("sensor.capaciteit", "8.64")
    c.capacity_trend_history = [
        {"datum": f"2026-08-{d:02d}", "capaciteit_kwh": 8.64, "doorzet_kwh": 1.0}
        for d in range(1, 30)
    ] + [{"datum": "2026-09-02", "capaciteit_kwh": 7.9, "doorzet_kwh": 1.0, "bron": "kalibratie"}]

    assert c.gemeten_capaciteit_kwh() == pytest.approx(7.9, abs=0.01)
