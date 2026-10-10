"""v5.72 (akkoord Ruud 10-10): zes punten uit de leerronde.

1. Zelfcontrole nachtrondes: een nacht telt alleen als de accu bij het begin
   energie had. Een lege accu is niet te beoordelen - geen melding.
2. Reserve en laadstand altijd in het dagverloop; ontbreken ze, dan de eerder
   bewaarde waarde (of de bodem). Een onbekende tekortnacht verhoogt de marge
   niet (zoals economisch) en wordt één keer opnieuw ingedeeld.
3. Dagtotalen (kosten vandaag, "_today") slapen na middernacht: geen melding
   "'n Sensor is d'r neet meer".
4. L-EMS-015: de live tekortsoort over de hele nacht, zoals het dagrecord.
5. L-EMS-013: economische nachten tellen niet mee in de marge (al sinds v5.70).
6. L-EMS-014: een bijna lege module - de sprong gaat vooraf van de
   beschikbare energie af; zonder moduledata geen correctie.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import coordinator as mod
from custom_components.energy_management_system.const import (
    MARGE_TELT_NIET_MEE_SOORTEN,
    MODULE_LEEG_SPRONG_KWH,
    TEKORTSOORT_ECONOMISCH,
    TEKORTSOORT_ONBEKEND,
    TEKORTSOORT_PLANNING,
)

TZ = timezone(timedelta(hours=2))


def _dag(datum: str, shortfall: bool, soort=None) -> dict:
    return {"date": datum, "shortfall": shortfall, "tekort_soort": soort, "excess": False}


# --- 1. zelfcontrole nachtrondes ------------------------------------------


def _nacht_coordinator(make_coordinator, hass, soc):
    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    c.effective_min_soc_percent = lambda: 10.0
    hass.states.set("sensor.soc", soc)
    return c


def test_nacht_met_lege_accu_is_niet_te_beoordelen(make_coordinator, hass):
    c = _nacht_coordinator(make_coordinator, hass, 10)
    begin = datetime(2026, 10, 9, 22, 0, tzinfo=TZ)
    for i in range(240):
        c._tel_nachtronde(begin + timedelta(minutes=2 * i), "default_smart", net_w=400.0)

    uit = c.zelfcontrole_nacht_gecontroleerd()

    assert uit["in_orde"] is True
    assert uit["beoordeelbaar"] is False
    assert "Niet te beoordelen" in uit["uitleg"]
    assert "Nul van" not in uit["uitleg"]
    assert not any(
        "Nacht gecontroleerd" in p for p in c._zelfcontrole_aandachtspunten()
    )


def test_nacht_met_energie_en_nul_zelfvoorzienend_blijft_een_bevinding(make_coordinator, hass):
    c = _nacht_coordinator(make_coordinator, hass, 60)
    begin = datetime(2026, 10, 9, 22, 0, tzinfo=TZ)
    for i in range(240):
        c._tel_nachtronde(begin + timedelta(minutes=2 * i), "default_smart", net_w=400.0)

    uit = c.zelfcontrole_nacht_gecontroleerd()

    assert uit["in_orde"] is False
    assert "Nul van 240" in uit["uitleg"]


def test_elke_nacht_wordt_apart_beoordeeld(make_coordinator, hass):
    """De ene nacht leeg, de volgende met energie: de telling begint opnieuw."""
    c = _nacht_coordinator(make_coordinator, hass, 10)
    c._tel_nachtronde(datetime(2026, 10, 8, 23, 0, tzinfo=TZ), "x", net_w=400.0)
    assert c._nacht_beoordeling["beoordeelbaar"] is False
    hass.states.set("sensor.soc", 70)
    c._tel_nachtronde(datetime(2026, 10, 9, 22, 5, tzinfo=TZ), "x", net_w=-20.0)
    assert c._nacht_beoordeling["beoordeelbaar"] is True
    assert c._nachtrondes == {"totaal": 1, "zelfvoorzienend": 1}
    assert c._nachtrondes_nacht == "2026-10-09"


def test_onbekende_laadstand_telt_zoals_voorheen(make_coordinator, hass):
    c = make_coordinator({})
    c._tel_nachtronde(datetime(2026, 10, 9, 23, 0, tzinfo=TZ), "x", net_w=400.0)
    assert c._nachtrondes == {"totaal": 1, "zelfvoorzienend": 0}


# --- 2. reserve en laadstand in het dagverloop -----------------------------


def test_onbekend_telt_niet_mee_in_de_marge(make_coordinator):
    assert TEKORTSOORT_ONBEKEND in MARGE_TELT_NIET_MEE_SOORTEN
    c = make_coordinator({})
    c.reserve_daily_records = [
        _dag("2026-10-03", True, TEKORTSOORT_ONBEKEND),
        _dag("2026-10-04", True, TEKORTSOORT_ONBEKEND),
        _dag("2026-10-05", True, TEKORTSOORT_PLANNING),
    ]
    assert c.marge_tekortnachten() == 1
    # Wel vastgelegd en gemeld.
    assert c.get_tekortsoorten()["tekortnachten_onbekend"] == 2
    _aandacht, info = c._tekortnachten_meldingen()
    assert any("Telt niet mee in de reservemarge" in r for r in info)


def test_regel_zonder_blok_krijgt_de_bodem(make_coordinator, monkeypatch):
    c = make_coordinator({})
    nu = datetime(2026, 10, 9, 19, 0, tzinfo=TZ)
    monkeypatch.setattr(mod.dt_util, "now", lambda: nu)
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.last_cheap_block_start = None
    c.last_reserve_margin_breakdown = {}
    regel = {"tijd": "19:00", "soc": 50.0, "reserve_kwh": None}

    c._vul_reserve_en_laadstand_aan(regel, [])

    assert regel["reserve_kwh"] == pytest.approx(c._reserve_bodem_kwh(), abs=0.001)
    assert regel["reserve_bron"].startswith("bodem")


def test_regel_met_blok_maar_zonder_reserve_krijgt_de_vorige(make_coordinator, monkeypatch):
    c = make_coordinator({})
    nu = datetime(2026, 10, 9, 19, 0, tzinfo=TZ)
    monkeypatch.setattr(mod.dt_util, "now", lambda: nu)
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.last_cheap_block_start = nu + timedelta(hours=15)
    reeks = [{"tijd": "18:30", "soc": 52.0, "reserve_kwh": 3.2}, {"tijd": "18:45", "soc": None}]
    regel = {"tijd": "19:00", "soc": None, "reserve_kwh": None}

    c._vul_reserve_en_laadstand_aan(regel, reeks)

    assert regel["reserve_kwh"] == 3.2
    assert regel["reserve_bron"] == "vorige regel"
    # Laadstand: de vorige regel, als die hooguit een half uur oud is.
    assert regel["soc"] == 52.0
    assert regel["soc_bron"] == "vorige regel"


def test_te_oude_laadstand_wordt_niet_doorgeschoven(make_coordinator):
    c = make_coordinator({})
    regel = {"tijd": "19:00", "soc": None, "reserve_kwh": 1.0}
    c._vul_reserve_en_laadstand_aan(regel, [{"tijd": "17:00", "soc": 52.0}])
    assert regel["soc"] is None


def _verkoopvenster(reserve_bij_verkoop):
    """Avond: eerst een kwartier met reserve 3,0, dan vier verkoopkwartieren
    zonder reserve (zoals 03-10/04-10), beschikbaar 2,5 kWh."""
    rijen = [{"tijd": "18:45", "soc": 40, "net_w": -50.0, "accu_w": 200.0,
              "prijs_ct": 30.0, "reserve_kwh": 3.0, "beschikbaar_kwh": 2.9}]
    for k in range(4):
        rijen.append({"tijd": f"19:{15 * k:02d}", "soc": 38 - k, "net_w": -1950.0,
                      "accu_w": 2100.0, "prijs_ct": 45.3,
                      "reserve_kwh": reserve_bij_verkoop, "beschikbaar_kwh": 2.5})
    return rijen


def test_verkoop_zonder_reserve_valt_terug_op_de_eerder_bewaarde(make_coordinator):
    c = make_coordinator({})
    onder, onbepaald = c._verkocht_onder_reserve(_verkoopvenster(None), 50.0, 8.64, 10.0)
    assert onbepaald == 0.0
    assert onder > 0  # 2,5 kWh beschikbaar onder de reserve van 3,0


def test_verkoop_zonder_enige_reserve_valt_terug_op_de_bodem(make_coordinator):
    c = make_coordinator({})
    rijen = [dict(r, reserve_kwh=None) for r in _verkoopvenster(None)]
    onder, onbepaald = c._verkocht_onder_reserve(rijen, 50.0, 8.64, 10.0, bodem_kwh=1.3)
    assert onbepaald == 0.0
    assert onder == 0.0  # 2,5 kWh ligt boven de bodem
    # Zonder bodem blijft het onbepaald (v5.61).
    _o, onbepaald = c._verkocht_onder_reserve(rijen, 50.0, 8.64, 10.0)
    assert onbepaald > 0


def test_onbekende_nacht_wordt_een_keer_opnieuw_ingedeeld(make_coordinator):
    c = make_coordinator({})
    c.dagverloop = {}
    record = _dag("2026-10-04", True, TEKORTSOORT_ONBEKEND)
    record["reservetoets"] = "v5.61"
    c.reserve_daily_records = [record]
    assert c._wacht_op_reservetoets(record)
    c._verkoop_uit_verloop = lambda dag: (TEKORTSOORT_PLANNING, "verkocht onder de reserve")

    c._toets_winstnachten_op_reserve()

    assert record["tekort_soort"] == TEKORTSOORT_PLANNING
    assert record["onbekend_hertoets"] == "v5.72"


def test_onbekende_nacht_die_onbekend_blijft_wordt_niet_elk_uur_herhaald(make_coordinator):
    c = make_coordinator({})
    c.dagverloop = {}
    record = _dag("2026-10-04", True, TEKORTSOORT_ONBEKEND)
    record["reservetoets"] = "v5.61"
    c.reserve_daily_records = [record]
    c._verkoop_uit_verloop = lambda dag: (None, None)

    c._toets_winstnachten_op_reserve()

    assert record["tekort_soort"] == TEKORTSOORT_ONBEKEND
    assert not c._wacht_op_reservetoets(record)


def test_omrekening_draagt_de_bodem(make_coordinator):
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.effective_min_soc_percent = lambda: 10.0
    assert c._reserve_omrekening()["bodem_kwh"] == pytest.approx(c._reserve_bodem_kwh())


def test_recorder_vult_lege_laadstand_aan(make_coordinator, monkeypatch):
    """Best effort: zonder recorder (zoals hier) gewoon niets, geen fout."""
    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    nu = datetime(2026, 10, 10, 11, 0, tzinfo=TZ)
    c.dagverloop = {"2026-10-10": [{"tijd": "10:00", "soc": None}]}
    uit = asyncio.run(c.async_vul_dagverloop_aan_uit_recorder(nu))
    assert uit >= 0
    # Eens per uur.
    assert asyncio.run(c.async_vul_dagverloop_aan_uit_recorder(nu)) == 0


# --- 3. dagtotalen rond middernacht -------------------------------------


@pytest.mark.parametrize(
    "tijd, verwacht",
    [((0, 19), True), ((0, 44), True), ((0, 46), False), ((23, 50), False)],
)
def test_dagtotaal_slaapt_tot_kwart_voor_een(make_coordinator, tijd, verwacht):
    c = make_coordinator({})
    nu = datetime(2026, 10, 10, tijd[0], tijd[1], tzinfo=TZ)
    assert c._dagtotaal_slaapt(
        "eigen_sensor_entity", "sensor.zonneplan_electricity_delivery_costs_today", nu
    ) is verwacht


def test_geen_dagtotaal_slaapt_niet(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 10, 0, 10, tzinfo=TZ)
    assert c._dagtotaal_slaapt("price_sensor_entity", "sensor.zonneplan_current_price", nu) is False


def test_dagbedrag_van_de_leverancier_houdt_het_ruime_venster(make_coordinator):
    from custom_components.energy_management_system.const import (
        CONF_GAS_EUR_VANDAAG_SENSOR,
    )

    c = make_coordinator({})
    nu = datetime(2026, 10, 10, 1, 5, tzinfo=TZ)
    assert c._dagtotaal_slaapt(
        CONF_GAS_EUR_VANDAAG_SENSOR, "sensor.zonneplan_gas_delivery_costs_today", nu
    )


def test_middernacht_geeft_geen_melding_over_een_dagbedrag(make_coordinator, hass, monkeypatch):
    """Het geval van 10-10 00:19: drie Zonneplan-dagbedragen op unknown."""
    from custom_components.energy_management_system.const import (
        CONF_GAS_EUR_VANDAAG_SENSOR,
    )

    entiteit = "sensor.zonneplan_gas_delivery_costs_today"
    c = make_coordinator({CONF_GAS_EUR_VANDAAG_SENSOR: entiteit})
    hass.states.set(entiteit, "unknown")
    begin = datetime(2026, 10, 10, 0, 3, tzinfo=TZ)
    for minuut in range(0, 40, 2):
        nu = begin + timedelta(minutes=minuut)
        monkeypatch.setattr(mod.dt_util, "now", lambda nu=nu: nu)
        c._volg_beschikbaarheid_van_de_invoer(nu)
    assert c.weggevallen_invoer(begin + timedelta(minutes=38)) == []


def test_na_het_venster_wordt_wel_gemeld(make_coordinator, hass, monkeypatch):
    entiteit = "sensor.iets_kosten_today"
    c = make_coordinator({"eigen_kosten_sensor_entity": entiteit})
    hass.states.set(entiteit, "unavailable")
    begin = datetime(2026, 10, 10, 0, 30, tzinfo=TZ)
    for minuut in range(0, 40, 2):
        nu = begin + timedelta(minutes=minuut)
        monkeypatch.setattr(mod.dt_util, "now", lambda nu=nu: nu)
        c._volg_beschikbaarheid_van_de_invoer(nu)
    # Pas vanaf 00:45 telt het; om 01:08 is dat 23 minuten > 15.
    weg = c.weggevallen_invoer(begin + timedelta(minutes=38))
    assert [r["entiteit"] for r in weg] == [entiteit]
    # En het telt pas vanaf het einde van het venster.
    assert c._sensor_unavailable_since[entiteit] >= datetime(2026, 10, 10, 0, 45, tzinfo=TZ)


# --- 4. L-EMS-015: soort over de hele nacht -------------------------------


def test_soort_blijft_economisch_als_het_restant_klein_is(make_coordinator):
    c = make_coordinator({})
    c._nodig_tot_en_na_blok_kwh = lambda: (1.0, 0.0)
    c.beschikbare_energie_kwh = lambda: 0.7  # restant 0,3 kWh: onder de drempel
    c._netladen_economisch_afgewezen = lambda: True
    c._vol_voor_nacht = False
    c._verkocht_na_vol_kwh = 0.0
    c._live_tekortvolging_onvolledig = lambda begin: None
    c.bruikbaar_tussen_grenzen_kwh = lambda: 7.0

    c._tekortnacht_lopend_kwh = 0.0
    assert c.verwacht_tekort()["tekort_soort"] is None  # nog geen tekortnacht

    c._tekortnacht_lopend_kwh = 2.1  # vannacht al 2,1 kWh als tekort bijgekocht
    uit = c.verwacht_tekort()
    assert uit["tekort_soort"] == TEKORTSOORT_ECONOMISCH
    assert uit["tekort_kwh"] == 0.3  # het restant blijft het restant
    assert uit["tekort_hele_nacht_kwh"] == 2.4
    assert "economisch" in c._tekort_soort_zin()


# --- 5. L-EMS-013 (al sinds v5.70) ----------------------------------------


def test_economisch_telt_niet_mee_in_de_marge(make_coordinator):
    c = make_coordinator({})
    c.reserve_daily_records = [_dag("2026-10-09", True, TEKORTSOORT_ECONOMISCH)]
    assert c.marge_tekortnachten() == 0
    assert c.get_tekortsoorten()["tekortnachten_economisch"] == 1


# --- 6. L-EMS-014: een bijna lege module ----------------------------------


def _module_coordinator(make_coordinator, hass, module_soc=20.0, cel=3.2, soc=14.0):
    c = make_coordinator(
        {
            "battery_soc_sensor_entity": "sensor.soc",
            "available_energy_sensor_entity": "sensor.beschikbaar",
            "battery_module_soc_sensor_entities": ["sensor.m1_soc", "sensor.m2_soc"],
            "battery_module_cell_voltage_min_sensor_entities": ["sensor.m1_min", "sensor.m2_min"],
        }
    )
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c._read_corrected_battery_power = lambda: 300.0
    hass.states.set("sensor.soc", soc)
    hass.states.set("sensor.beschikbaar", 0.9)
    hass.states.set("sensor.m1_soc", module_soc)
    hass.states.set("sensor.m2_soc", 25.0)
    hass.states.set("sensor.m1_min", cel)
    hass.states.set("sensor.m2_min", 3.25)
    return c


def _ronde(c, nu):
    c.battery_module_live = c._read_battery_modules()
    c._volg_module_leeg(nu)


def test_geen_correctie_boven_de_grens(make_coordinator, hass):
    c = _module_coordinator(make_coordinator, hass, module_soc=20.0)
    _ronde(c, datetime(2026, 10, 10, 3, 0, tzinfo=TZ))
    assert c.module_leeg_correctie_kwh() == 0.0
    assert c.beschikbare_energie_kwh() == 0.9


def test_module_onder_15_procent_verlaagt_de_beschikbare_energie(make_coordinator, hass):
    c = _module_coordinator(make_coordinator, hass, module_soc=14.0)
    _ronde(c, datetime(2026, 10, 10, 3, 0, tzinfo=TZ))
    assert c.module_leeg_correctie_kwh() == MODULE_LEEG_SPRONG_KWH
    assert c.beschikbare_energie_kwh() == pytest.approx(0.9 - MODULE_LEEG_SPRONG_KWH)
    assert c.get_module_leeg()["actief"] is True


def test_cel_onder_3_volt_verlaagt_ook(make_coordinator, hass):
    c = _module_coordinator(make_coordinator, hass, module_soc=20.0, cel=2.98)
    _ronde(c, datetime(2026, 10, 10, 3, 0, tzinfo=TZ))
    assert c.module_leeg_correctie_kwh() == MODULE_LEEG_SPRONG_KWH


def test_nooit_onder_nul(make_coordinator, hass):
    c = _module_coordinator(make_coordinator, hass, module_soc=12.0)
    hass.states.set("sensor.beschikbaar", 0.2)
    _ronde(c, datetime(2026, 10, 10, 3, 0, tzinfo=TZ))
    assert c.beschikbare_energie_kwh() == 0.0


def test_na_de_sprong_geen_dubbele_correctie_en_de_sprong_wordt_geleerd(make_coordinator, hass):
    c = _module_coordinator(make_coordinator, hass, module_soc=14.0, soc=15.0)
    t = datetime(2026, 10, 10, 3, 0, tzinfo=TZ)
    _ronde(c, t)
    assert c.module_leeg_correctie_kwh() > 0
    # Vijf minuten later springt de laadstand 15 -> 10,5%.
    hass.states.set("sensor.soc", 10.5)
    _ronde(c, t + timedelta(minutes=5))
    assert c.module_leeg_correctie_kwh() == 0.0
    assert len(c.module_leeg_sprongen) == 1
    gemeten = c.module_leeg_sprongen[0]["kwh"]
    # 4,5% min wat 300 W in vijf minuten verklaart (0,29%) van 8,64 kWh.
    assert gemeten == pytest.approx(8.64 * (4.5 - 0.025 / 8.64 * 100) / 100, abs=0.01)
    # De volgende keer geldt de gemeten sprong in plaats van de constante.
    hass.states.set("sensor.m1_soc", 30.0)
    hass.states.set("sensor.m1_min", 3.3)
    _ronde(c, t + timedelta(hours=8))
    assert c._module_leeg is None
    hass.states.set("sensor.m1_soc", 14.0)
    _ronde(c, t + timedelta(days=1))
    assert c.module_leeg_correctie_kwh() == pytest.approx(gemeten)
    assert c.get_module_leeg()["bron"] == "gemeten"


def test_sprong_die_al_voor_het_aanslaan_kwam_telt_niet_dubbel(make_coordinator, hass):
    c = _module_coordinator(make_coordinator, hass, module_soc=16.0, soc=15.0)
    t = datetime(2026, 10, 10, 3, 0, tzinfo=TZ)
    _ronde(c, t)
    hass.states.set("sensor.soc", 10.5)
    hass.states.set("sensor.m1_soc", 14.0)  # module meldt het in dezelfde ronde
    _ronde(c, t + timedelta(minutes=5))
    assert c.get_module_leeg()["actief"] is True
    assert c.module_leeg_correctie_kwh() == 0.0


def test_gewoon_snel_ontladen_is_geen_sprong(make_coordinator, hass):
    c = _module_coordinator(make_coordinator, hass, module_soc=14.0, soc=15.0)
    c._read_corrected_battery_power = lambda: 2400.0
    t = datetime(2026, 10, 10, 19, 0, tzinfo=TZ)
    _ronde(c, t)
    hass.states.set("sensor.soc", 12.0)  # 3% in 5 min, 2,4 kW verklaart 2,3%
    _ronde(c, t + timedelta(minutes=5))
    assert c.module_leeg_correctie_kwh() == MODULE_LEEG_SPRONG_KWH


def test_zonder_moduledata_geen_correctie(make_coordinator, hass):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar"})
    hass.states.set("sensor.beschikbaar", 0.9)
    _ronde(c, datetime(2026, 10, 10, 3, 0, tzinfo=TZ))
    assert c.module_leeg_correctie_kwh() == 0.0
    assert c.beschikbare_energie_kwh() == 0.9


def test_onleesbare_modulesensoren_geen_correctie(make_coordinator, hass):
    c = _module_coordinator(make_coordinator, hass)
    for e in ("sensor.m1_soc", "sensor.m2_soc", "sensor.m1_min", "sensor.m2_min"):
        hass.states.set(e, "unavailable")
    _ronde(c, datetime(2026, 10, 10, 3, 0, tzinfo=TZ))
    assert c.module_leeg_correctie_kwh() == 0.0


def test_de_sprong_is_een_constante_en_wordt_bewaard():
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    assert MODULE_LEEG_SPRONG_KWH == 0.35
    assert "module_leeg_sprongen" in PERSISTED_FIELDS
