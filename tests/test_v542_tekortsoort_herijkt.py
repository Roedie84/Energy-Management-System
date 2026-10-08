"""De oude tekortnachten opnieuw ingedeeld (v5.42).

v5.41 deelde de vier nachten van 30 september tot 4 oktober allemaal in als
planning. Nagerekend tegen het dagverloop klopten twee daarvan niet:

- 30 september: "zon het net op" was 1,0 kWh in de momentopnamen - de vaste
  -50 W op de P1-meter (v5.20) en kwartieren waarin de Zendure in `smart`
  even achterliep bij een wolk. De P1-meter zag die dag buiten de
  verschuiving bijna niets. En "laden loonde" rekende een extra kWh tegen de
  avondpiek van 42,8 ct, terwijl de accu die piek zelf al dekte: het tekort
  werd om vier uur 's nachts betaald, tegen 24 tot 36 ct.
- 2 oktober: een donkere dag, alles boven de 31 ct. Ook hier telde de
  avondpiek van 51,2 ct; het tekort kostte 33 tot 41 ct.

De andere twee waren wel planning, maar om een andere reden dan de regels
zagen: de accu verkocht in de dure kwartieren meer dan de nacht kon missen.
"""
from datetime import datetime, timedelta, timezone

DAG = datetime(2026, 10, 7, tzinfo=timezone.utc)


def _c(make_coordinator, hass):
    c = make_coordinator({})
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 11.22}
    return c


def _venster(rij):
    """96 kwartieren 09:00-09:00 voor de nacht naar 3 oktober; `rij(k, tijd)`
    geeft de velden."""
    dagen = {"2026-10-02": [], "2026-10-03": []}
    for k in range(96):
        moment = datetime(2026, 10, 2, 9, 0) + timedelta(minutes=15 * k)
        tijd = moment.strftime("%H:%M")
        dagen[moment.date().isoformat()].append(
            {"tijd": tijd, "stand": "smart", "reden": "default_smart", **rij(k, tijd)}
        )
    return dagen


def _nacht_30_september(k, tijd):
    """Het patroon van 29/30 september: overdag laden uit de zon in `smart`
    met de vaste -50 W en twee regelpieken, 's avonds piek, vanaf 04:00 leeg
    en import tegen 24-36 ct."""
    if k < 36:  # 09:00-17:45: zon de accu in
        net = -1450.0 if k in (7, 15) else -50.0
        accu = 0.0 if k in (7, 15) else -900.0
        prijs = 21.0 if 18 <= k < 24 else 30.0
        return {"soc": 15 + k, "net_w": net, "accu_w": accu, "prijs_ct": prijs}
    if k < 76:  # 18:00-03:45: de accu levert het huis, piek tot 42,8 ct
        prijs = 42.8 if k < 44 else 27.0
        return {"soc": max(8, 50 - (k - 36)), "net_w": -50.0, "accu_w": 300.0, "prijs_ct": prijs}
    return {"soc": 7, "net_w": 200.0, "accu_w": 0.0, "prijs_ct": 25.0 + (k - 76) * 0.5}


def _records(c, verloop, herleid="v5.41"):
    c.dagverloop = verloop
    c.reserve_daily_records = [
        {
            "date": "2026-10-03", "shortfall": True, "tekortnacht_kwh": 1.44,
            "tekort_soort": "planning", "tekort_soort_herleid": herleid,
        },
    ]


def test_de_nacht_van_30_september_is_economisch(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.regelverschuiving_kw = lambda: 0.05
    _records(c, _venster(_nacht_30_september))

    assert c._herleid_onbekende_tekortnachten() == 1

    record = c.reserve_daily_records[0]
    assert record["tekort_soort"] == "economisch", record
    assert record["tekort_soort_herleid"] == "v5.42"
    assert "laden loonde nergens" in record["tekort_reden"]
    assert record["shortfall"] is True, "de marge telt hem nog mee"


def test_de_avondpiek_bepaalt_de_waarde_van_een_extra_kwh_niet(make_coordinator, hass):
    """v5.41: 42,8 x 0,843 - 11,22 = 24,9 ct > 21 ct, dus 'loonde'. Maar die
    piek dekte de accu zelf; het tekort kostte 25-31 ct, waard 10-15 ct."""
    c = _c(make_coordinator, hass)
    rijen = [r for dag in _venster(_nacht_30_september).values() for r in dag]
    for r in rijen:
        r["net_w"] = 200.0 if r["net_w"] > 0 else 0.0  # geen export: alleen de prijsregel

    soort, reden = c._deel_nacht_in_met_reden(rijen, 97.0, 84.3, 11.22)

    assert soort == "economisch", reden


def test_de_verschuiving_op_de_p1_meter_is_geen_zon_en_geen_verkoop(make_coordinator, hass):
    """Een verschuiving van 150 W: de hele avond 150 W 'verkocht'."""
    rijen = [r for dag in _venster(lambda k, t: {
        "soc": 100 if k == 10 else 60, "net_w": -150.0, "accu_w": 350.0 if k > 10 else -800.0,
        "prijs_ct": 30.0,
    }).values() for r in dag]

    c = _c(make_coordinator, hass)
    soort, _ = c._deel_nacht_in_met_reden(rijen, 97.0, 84.3, 11.22, verschuiving_w=150.0)
    assert soort == "capaciteit"
    soort, _ = c._deel_nacht_in_met_reden(rijen, 97.0, 84.3, 11.22, verschuiving_w=0.0)
    assert soort == "planning", "zonder de verschuiving lijkt het verkoop"


def test_de_ruisvloer_vangt_een_weggevallen_verschuiving(make_coordinator, hass):
    """Meet de verschuiving bij het opstarten even nul, dan telt de -50 W
    alsnog niet als verkoop."""
    rijen = [r for dag in _venster(lambda k, t: {
        "soc": 100 if k == 10 else 60, "net_w": -50.0, "accu_w": 250.0 if k > 10 else -800.0,
        "prijs_ct": 30.0,
    }).values() for r in dag]

    c = _c(make_coordinator, hass)
    assert c._deel_nacht_in_met_reden(rijen, 97.0, 84.3, 11.22)[0] == "capaciteit"


def test_zon_het_net_op_telt_alleen_als_het_ems_de_accu_dichthield(make_coordinator, hass):
    def rij(k, tijd, stand):
        if k >= 72:
            return {"soc": 9, "net_w": 200.0, "accu_w": 0.0, "prijs_ct": 30.0}
        return {"soc": 50, "net_w": -800.0, "accu_w": -300.0, "prijs_ct": 30.0, "stand": stand}

    c = _c(make_coordinator, hass)
    in_smart = [r for d in _venster(lambda k, t: rij(k, t, "smart")).values() for r in d]
    uitgesteld = [
        r for d in _venster(lambda k, t: rij(k, t, "smart_discharging")).values() for r in d
    ]

    assert c._deel_nacht_in_met_reden(in_smart, 97.0, 84.3, 11.22)[0] == "economisch"
    soort, reden = c._deel_nacht_in_met_reden(uitgesteld, 97.0, 84.3, 11.22)
    assert soort == "planning"
    assert "zon het net op" in reden


def test_verkopen_terwijl_de_accu_niet_vol_was_is_planning(make_coordinator, hass):
    """2/3 oktober: 19:00-19:45 1,4 kWh verkocht tegen 51 ct, bij 73% - de
    accu werd nooit vol. v5.41 keek bij een niet-volle accu niet naar
    verkoop.

    v5.55: het tekort hier tegen 52 ct, boven de verkoopprijs - anders is het
    "verkocht met winst" (test_v555_doorlichting.py)."""
    def rij(k, tijd):
        if 40 <= k < 44:
            return {"soc": 63 - (k - 40) * 4, "net_w": -1450.0, "accu_w": 1636.0,
                    "prijs_ct": 51.5, "stand": "manual", "reden": "expensive_quarter_peak"}
        if k >= 72:
            return {"soc": 9, "net_w": 200.0, "accu_w": 0.0, "prijs_ct": 52.0}
        return {"soc": 50, "net_w": -50.0, "accu_w": 250.0, "prijs_ct": 35.0}

    c = _c(make_coordinator, hass)
    rijen = [r for d in _venster(rij).values() for r in d]
    soort, reden = c._deel_nacht_in_met_reden(rijen, 97.0, 84.3, 11.22, verschuiving_w=50.0)

    assert soort == "planning"
    assert reden.startswith("1,4 kWh verkocht terwijl de accu niet vol was")
    assert "51,5 ct" in reden


def test_vol_en_daarna_verkocht_noemt_hoeveel(make_coordinator, hass):
    # v5.55: tekort tegen 41 ct, boven de verkoopprijs van 40,6 ct: geen
    # winst, dus planning.
    def rij(k, tijd):
        if k == 32:
            return {"soc": 100, "net_w": -50.0, "accu_w": 0.0, "prijs_ct": 33.0}
        if 39 <= k < 50:
            return {"soc": 90 - (k - 39) * 6, "net_w": -1750.0, "accu_w": 2035.0,
                    "prijs_ct": 40.6, "stand": "manual"}
        if k >= 72:
            return {"soc": 9, "net_w": 200.0, "accu_w": 0.0, "prijs_ct": 41.0}
        return {"soc": 60, "net_w": -50.0, "accu_w": 200.0, "prijs_ct": 35.0}

    c = _c(make_coordinator, hass)
    rijen = [r for d in _venster(rij).values() for r in d]
    soort, reden = c._deel_nacht_in_met_reden(rijen, 97.0, 84.3, 11.22, verschuiving_w=50.0)

    assert soort == "planning"
    assert reden.startswith("vol geweest, daarna 4,7 kWh verkocht")


def test_een_live_ingedeelde_nacht_blijft_staan(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _records(c, _venster(_nacht_30_september), herleid=None)
    del c.reserve_daily_records[0]["tekort_soort_herleid"]

    assert c._herleid_onbekende_tekortnachten() == 0
    assert c.reserve_daily_records[0]["tekort_soort"] == "planning"


def test_niet_meer_te_bepalen_wordt_onbekend_en_niet_planning(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _records(c, _venster(_nacht_30_september))
    c.get_wear_cost_overview = lambda: {"beschikbaar": False}

    assert c._herleid_onbekende_tekortnachten() == 0
    assert "tekort_soort" not in c.reserve_daily_records[0]
    assert c.get_tekortsoorten()["tekortnachten_planning"] == 0


def test_het_aandachtspunt_noemt_de_nachten_en_waarom(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.reserve_daily_records = [
        {"date": "2026-10-03", "shortfall": True, "tekort_soort": "planning",
         "tekort_reden": "1,4 kWh verkocht terwijl de accu niet vol was"},
        {"date": "2026-10-04", "shortfall": True, "tekort_soort": "planning",
         "tekort_reden": "vol geweest, daarna 4,6 kWh verkocht"},
        {"date": "2026-10-05", "shortfall": True, "tekort_soort": "economisch",
         "tekort_reden": "laden loonde nergens"},
        {"date": "2026-10-06", "shortfall": False},
    ]

    aandacht, _info = c._tekortnachten_meldingen()

    assert aandacht == [
        "2 onverwachte tekort-dag(en) in de laatste 4 dagen. Planning - "
        "nacht naar 3 okt: 1,4 kWh verkocht terwijl de accu niet vol was; "
        "nacht naar 4 okt: vol geweest, daarna 4,6 kWh verkocht."
    ]


def test_live_verkoop_zonder_vol_is_geen_economisch_tekort(make_coordinator, hass):
    c = make_coordinator(
        {
            "battery_soc_sensor_entity": "sensor.soc",
            "consumption_power_sensor_entity": "sensor.p1",
            "battery_power_sensor_entity": "sensor.accu",
        }
    )
    hass.states.set("sensor.soc", "60")
    hass.states.set("sensor.p1", "-1500")
    hass.states.set("sensor.accu", "1700")
    c._live_tekortvolging_onvolledig = lambda begin: None  # v5.44: live volledig
    c.last_laadbesluit = {"laden": False, "prijs_nu_eur": 0.30, "waarde_eur": 0.25}
    moment = DAG.replace(hour=19)
    for _ in range(12):
        moment += timedelta(minutes=5)
        c._volg_vol_en_verkoop(moment)

    assert c._verkocht_na_vol_kwh > 1.0
    assert c._netladen_economisch_afgewezen() is False
    c._tekortnacht_vandaag_kwh = 1.4
    c._volg_vol_en_verkoop((DAG + timedelta(days=1)).replace(hour=9, minute=1))
    assert c._tekort_soort_vandaag == "planning"
    assert "verkocht terwijl de accu niet vol was" in c._tekort_reden_vandaag


def test_de_reden_overleeft_een_herstart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "_tekort_reden_vandaag" in PERSISTED_PLAIN_FIELDS
