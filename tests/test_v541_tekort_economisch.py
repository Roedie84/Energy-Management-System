"""Een derde tekortsoort: economisch, en de oude nachten ingedeeld (v5.41).

Gemeld op 7 oktober: de accu stond op 93% en laadde niet verder uit het net,
omdat dat niet loonde. Het tekort dat volgde telde als planning en zette de
cockpit op LET OP. Economisch is informatief, net als capaciteit. En de vier
nachten van vóór v5.40 (zonder soort) worden uit het dagverloop ingedeeld;
wat niet te bepalen is, is onbekend en ook informatief.
"""
from datetime import datetime, timedelta, timezone

DAG = datetime(2026, 10, 7, tzinfo=timezone.utc)

LOONT_NIET = {
    "laden": False,
    "prijs_nu_eur": 0.30,
    "waarde_eur": 0.25,
    "marge_ct": -5.0,
    "reden": "loont niet: straks minder waard dan hij nu kost",
}
LOONT = {**LOONT_NIET, "waarde_eur": 0.35, "laden": True}
ZON = {"laden": False, "gat_kwh": -1.0, "reden": "de zon vult de accu vandaag vanzelf"}


def _c(make_coordinator, hass, soc="93", net="0", accu="0"):
    c = make_coordinator(
        {
            "battery_soc_sensor_entity": "sensor.soc",
            "consumption_power_sensor_entity": "sensor.p1",
            "battery_power_sensor_entity": "sensor.accu",
        }
    )
    hass.states.set("sensor.soc", soc)
    hass.states.set("sensor.p1", net)
    hass.states.set("sensor.accu", accu)
    return c


def _rondes(c, besluit, uur=13, aantal=12):
    c.last_laadbesluit = besluit
    moment = DAG.replace(hour=uur)
    for _ in range(aantal):
        moment += timedelta(minutes=5)
        c._volg_vol_en_verkoop(moment)


# --- live: het laadbesluit en de zon -----------------------------------


def test_netladen_afgewezen_op_de_marge_is_economisch(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="93")
    _rondes(c, LOONT_NIET)

    assert c._laadbesluit_stand == "loont_niet"
    assert c._netladen_economisch_afgewezen() is True
    assert (
        c._tekort_soort(1.4, c._vol_voor_nacht, c._verkocht_na_vol_kwh, economisch=True)
        == "economisch"
    )


def test_zon_het_net_op_met_ruimte_is_planning(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="70", net="-1500", accu="-500")
    _rondes(c, LOONT_NIET)

    assert c._pv_export_met_ruimte_kwh > 1.0
    assert c._netladen_economisch_afgewezen() is False


def test_teruglevering_terwijl_de_accu_op_vol_vermogen_laadt_telt_niet(
    make_coordinator, hass
):
    # Laadvermogen standaard 2000 W; de accu laadt met 1950 W - er kon niet meer in.
    c = _c(make_coordinator, hass, soc="70", net="-1500", accu="-1950")
    _rondes(c, LOONT_NIET)

    assert c._pv_export_met_ruimte_kwh == 0.0
    assert c._netladen_economisch_afgewezen() is True


def test_laden_dat_loonde_is_geen_economisch_tekort(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="80")
    _rondes(c, LOONT)

    assert c._laadbesluit_stand == "loont"
    assert c._netladen_economisch_afgewezen() is False


def test_het_laatste_besluit_telt_laden_tot_het_niet_meer_loont(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="80")
    _rondes(c, LOONT, uur=13)
    _rondes(c, LOONT_NIET, uur=15)

    assert c._netladen_economisch_afgewezen() is True


def test_zon_verwacht_in_het_blok_en_toch_niet_vol_is_planning(make_coordinator, hass):
    """Een dipbesluit buiten het blok overschrijft de zonverwachting niet."""
    c = _c(make_coordinator, hass, soc="80")
    _rondes(c, ZON, uur=13)
    _rondes(c, {**LOONT_NIET, "soort": "dip"}, uur=21)

    assert c._laadbesluit_stand == "zon"
    assert c._netladen_economisch_afgewezen() is False


def test_vol_blijft_capaciteit_ook_met_een_afgewezen_marge(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="100")
    _rondes(c, LOONT_NIET)

    assert (
        c._tekort_soort(1.4, True, 0.0, economisch=True) == "capaciteit"
    )


def test_de_nacht_wordt_economisch_ingedeeld_en_het_venster_begint_opnieuw(
    make_coordinator, hass
):
    c = _c(make_coordinator, hass, soc="93")
    _rondes(c, LOONT_NIET, uur=14)
    c._tekortnacht_vandaag_kwh = 1.4
    volgende = DAG + timedelta(days=1)
    c.last_laadbesluit = {"laden": False, "reden": "niet in het goedkope blok"}
    c._volg_vol_en_verkoop(volgende.replace(hour=9, minute=1))

    assert c._tekort_soort_vandaag == "economisch"
    assert c._laadbesluit_stand is None
    assert c._pv_export_met_ruimte_kwh == 0.0


def test_economisch_is_informatief(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.reserve_daily_records = [
        {"date": "2026-10-05", "shortfall": True, "tekort_soort": "economisch"},
        {"date": "2026-10-06", "shortfall": False},
    ]

    samenvatting = c.get_diagnostic_summary()
    soorten = c.get_tekortsoorten()

    assert soorten["tekortnachten_economisch"] == 1
    assert soorten["tekortnachten_planning"] == 0
    assert not any("tekort-dag" in str(p) for p in samenvatting["aandachtspunten"])
    assert any("economisch" in p for p in samenvatting["informatief"])


def test_verwacht_economisch_tekort(make_coordinator, hass):
    c = _c(make_coordinator, hass, soc="93")
    _rondes(c, LOONT_NIET)
    c.last_reserve_margin_breakdown = {"needed_kwh_before_margin": 6.11}
    c.beschikbare_energie_kwh = lambda: 5.0

    verwacht = c.verwacht_tekort()

    assert verwacht["tekort_soort"] == "economisch"
    assert verwacht["laadbesluit_sinds_9u"] == "loont_niet"
    assert "economisch" in c._tekort_soort_zin()
    assert any(
        "economisch" in p for p in c.get_diagnostic_summary()["informatief"]
    )


def test_de_sensor_toont_economisch_en_onbekend(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import ReserveShortfallSensor

    c = _c(make_coordinator, hass)
    c.reserve_daily_records = [
        {"date": "2026-10-05", "shortfall": True, "tekort_soort": "economisch"},
        {"date": "2026-10-06", "shortfall": True},
    ]

    attrs = ReserveShortfallSensor(c, "x").extra_state_attributes

    assert attrs["tekortnachten_economisch"] == 1
    assert attrs["tekortnachten_onbekend"] == 1
    assert attrs["tekortnachten_planning"] == 0


def test_de_nieuwe_velden_overleven_een_herstart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "_laadbesluit_stand" in PERSISTED_PLAIN_FIELDS
    assert "_pv_export_met_ruimte_kwh" in PERSISTED_PLAIN_FIELDS


# --- achteraf: de oude nachten uit het dagverloop -----------------------


def _verloop(soc, prijs=30.0, net=0.0, accu=0.0, reden="default_smart", piek=None):
    """Een venster 09:00-09:00 als dagverloop, voor de nacht van 3 oktober."""
    dagen = {"2026-10-02": [], "2026-10-03": []}
    for k in range(96):
        moment = datetime(2026, 10, 2, 9, 0) + timedelta(minutes=15 * k)
        p = piek if (piek is not None and moment.hour in (18, 19)) else prijs
        dagen[moment.date().isoformat()].append(
            {
                "tijd": moment.strftime("%H:%M"),
                "soc": soc(k) if callable(soc) else soc,
                "net_w": net,
                "accu_w": accu,
                "prijs_ct": p,
                "reden": reden,
            }
        )
    return dagen


def _oud(c, verloop):
    c.dagverloop = verloop
    c.reserve_daily_records = [
        {"date": "2026-10-03", "shortfall": True, "tekortnacht_kwh": 1.2},
        {"date": "2026-10-04", "shortfall": False},
    ]
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 11.2}


def test_oude_nacht_vol_en_niets_verkocht_wordt_capaciteit(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _oud(c, _verloop(lambda k: 100 if k == 20 else 50))

    assert c._herleid_onbekende_tekortnachten() == 1
    assert c.reserve_daily_records[0]["tekort_soort"] == "capaciteit"
    assert c.reserve_daily_records[0]["tekort_soort_herleid"] == "v5.41"
    assert c.reserve_daily_records[0]["shortfall"] is True, "de marge telt hem nog mee"


def test_oude_nacht_vol_en_daarna_verkocht_wordt_planning(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _oud(c, _verloop(lambda k: 100 if k == 20 else 50, net=-800, accu=900))

    c._herleid_onbekende_tekortnachten()

    assert c.reserve_daily_records[0]["tekort_soort"] == "planning"


def test_oude_nacht_waarin_laden_nooit_loonde_wordt_economisch(make_coordinator, hass):
    # 30 ct nu, 44 ct piek: 44 x 0,84 - 11,2 = 25,8 ct < 30 ct.
    c = _c(make_coordinator, hass)
    _oud(c, _verloop(55, prijs=30.0, piek=44.0))

    c._herleid_onbekende_tekortnachten()

    assert c.reserve_daily_records[0]["tekort_soort"] == "economisch"
    assert c.get_tekortsoorten()["tekortnachten_planning"] == 0


def test_oude_nacht_waarin_laden_loonde_en_niet_geladen_wordt_planning(
    make_coordinator, hass
):
    # 20 ct nu, 44 ct piek: 25,8 ct > 20 ct.
    c = _c(make_coordinator, hass)
    _oud(c, _verloop(55, prijs=20.0, piek=44.0))

    c._herleid_onbekende_tekortnachten()

    assert c.reserve_daily_records[0]["tekort_soort"] == "planning"


def test_oude_nacht_met_zon_het_net_op_wordt_planning(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _oud(c, _verloop(55, prijs=30.0, piek=44.0, net=-600, accu=-200))

    c._herleid_onbekende_tekortnachten()

    assert c.reserve_daily_records[0]["tekort_soort"] == "planning"


def test_oude_nacht_waarin_geladen_werd_blijft_onbekend(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _oud(c, _verloop(55, prijs=20.0, piek=44.0, reden="grid_charging_profitable"))

    assert c._herleid_onbekende_tekortnachten() == 0
    assert "tekort_soort" not in c.reserve_daily_records[0]
    soorten = c.get_tekortsoorten()
    assert soorten["tekortnachten_onbekend"] == 1
    assert soorten["tekortnachten_planning"] == 0
    samenvatting = c.get_diagnostic_summary()
    assert not any("tekort-dag" in str(p) for p in samenvatting["aandachtspunten"])
    assert any("zonder soort" in p for p in samenvatting["informatief"])


def test_oude_nacht_zonder_dagverloop_blijft_onbekend(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _oud(c, {})

    assert c._herleid_onbekende_tekortnachten() == 0
    assert c.get_tekortsoorten()["tekort_soort_per_nacht"][0] == "onbekend"


def test_zonder_slijtage_is_economisch_niet_te_bepalen(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _oud(c, _verloop(55, prijs=30.0, piek=44.0))
    c.get_wear_cost_overview = lambda: {"beschikbaar": False}

    assert c._herleid_onbekende_tekortnachten() == 0


def test_herleiden_bij_het_laden_van_de_opslag(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 11.2}
    c._apply_persisted_state(
        {
            "dagverloop": _verloop(lambda k: 100 if k == 20 else 50),
            "reserve_daily_records": [
                {"date": "2026-10-03", "shortfall": True, "tekortnacht_kwh": 1.2},
            ],
        }
    )

    assert c.reserve_daily_records[0]["tekort_soort"] == "capaciteit"


def test_een_ingedeelde_nacht_wordt_niet_opnieuw_ingedeeld(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _oud(c, _verloop(55, prijs=30.0, piek=44.0))
    c.reserve_daily_records[0]["tekort_soort"] = "planning"

    assert c._herleid_onbekende_tekortnachten() == 0
    assert c.reserve_daily_records[0]["tekort_soort"] == "planning"


def test_herleiden_hooguit_eens_per_uur(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _oud(c, {})
    aanroepen = []
    c._herleid_onbekende_tekortnachten = lambda: aanroepen.append(1) or 0

    c._probeer_herleiding(DAG.replace(hour=10, minute=1))
    c._probeer_herleiding(DAG.replace(hour=10, minute=30))
    c._probeer_herleiding(DAG.replace(hour=11, minute=0))

    assert len(aanroepen) == 2
