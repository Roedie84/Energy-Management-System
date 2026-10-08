"""v5.55: drie punten uit de doorlichting van 8 oktober.

1. Zes sensoren zonder device_class/state_class: Home Assistant hield er
   geen langetermijnstatistieken van bij.
2. De relaisschakelingen van "Zendure lokaal meelezen": na een herstart
   stond "vandaag" op 27 terwijl de accu 48 telde. Nu direct bewaard bij
   elke wijziging, per dag in de tijdzone van Home Assistant, en met de
   eigen teller van de accu ernaast (`apparaat_vandaag`).
3. De nacht van 2 op 3 oktober: 1,9 kWh verkocht tegen 45,3 ct, het tekort
   teruggekocht tegen 33,3 ct - circa € 0,23 winst, en toch LET OP. Nu
   "verkocht met winst", informatief.
"""
import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import sensor as sensor_mod
from custom_components.energy_management_system import zendure_lokaal as zl

MAP = Path(pkg.__file__).parent


# --- 1. statistieken ----------------------------------------------------


class _Coord:
    peak_power_today_w = 2199.04
    living_room_current_temp_c = 21.4
    learned_night_consumption_kw = 0.403
    digital_twin_accuracy_mae_kwh = 0.512

    def _read_corrected_consumption_power(self):
        return 412.36

    def learned_hourly_avg_kw(self, hour):
        return 0.31


def _sensoren():
    c = _Coord()
    return {
        "piek": sensor_mod.PeakPowerSensor(c, "e"),
        "huis": sensor_mod.HouseholdConsumptionSensor(c, "e"),
        "uur": sensor_mod.HourlyConsumptionProfileSensor(c, "e"),
        "nacht": sensor_mod.LearnedNightConsumptionSensor(c, "e"),
        "klimaat": sensor_mod.ClimateForecastSensor(c, "e"),
        "twin": sensor_mod.DigitalTwinAccuracySensor(c, "e"),
    }


def test_vermogenssensoren_krijgen_statistieken():
    s = _sensoren()
    for naam in ("piek", "huis", "uur", "nacht"):
        assert s[naam]._attr_device_class == "power", naam
        assert s[naam]._attr_state_class == "measurement", naam
        assert s[naam]._attr_native_unit_of_measurement == "W", naam


def test_temperatuur_krijgt_statistieken():
    s = _sensoren()["klimaat"]
    assert s._attr_device_class == "temperature"
    assert s._attr_state_class == "measurement"
    assert s._attr_native_unit_of_measurement == "°C"


def test_twin_nauwkeurigheid_is_een_foutmaat_geen_energie():
    """Gemiddelde absolute afwijking in kWh: measurement, geen ENERGY."""
    s = _sensoren()["twin"]
    assert getattr(s, "_attr_device_class", None) is None
    assert s._attr_state_class == "measurement"
    assert s._attr_native_unit_of_measurement == "kWh"


def test_de_toestanden_zijn_getallen():
    for naam, s in _sensoren().items():
        waarde = s.native_value
        assert isinstance(waarde, (int, float)) and not isinstance(waarde, bool), naam


def test_leeg_blijft_none():
    c = _Coord()
    c.living_room_current_temp_c = None
    c.learned_night_consumption_kw = None
    c.digital_twin_accuracy_mae_kwh = None
    c._read_corrected_consumption_power = lambda: None
    c.learned_hourly_avg_kw = lambda hour: None
    assert sensor_mod.ClimateForecastSensor(c, "e").native_value is None
    assert sensor_mod.LearnedNightConsumptionSensor(c, "e").native_value is None
    assert sensor_mod.DigitalTwinAccuracySensor(c, "e").native_value is None
    assert sensor_mod.HouseholdConsumptionSensor(c, "e").native_value is None
    assert sensor_mod.HourlyConsumptionProfileSensor(c, "e").native_value is None


def test_attributen_blijven_buiten_de_recorder():
    for cls in (
        sensor_mod.HourlyConsumptionProfileSensor,
        sensor_mod.ClimateForecastSensor,
        sensor_mod.DigitalTwinAccuracySensor,
    ):
        assert cls._unrecorded_attributes == sensor_mod.GEEN_ATTRIBUTEN_IN_RECORDER


# --- 2. relaisschakelingen ----------------------------------------------


DAG1 = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc).timestamp()


def test_de_accuteller_wordt_gelezen():
    rapport = {"properties": {"acMode": 1, "switchCount": 20114}, "packData": []}
    assert zl.afgeleid(rapport)["apparaat_schakelingen"] == 20114
    assert "apparaat_schakelingen" not in zl.afgeleid({"properties": {"acMode": 1}})


def test_apparaat_vandaag_naast_de_eigen_telling():
    t = zl.lege_tellingen()
    zl.verwerk_afgeleid(t, {"relais_stand": "laden", "apparaat_schakelingen": 20066}, DAG1)
    zl.verwerk_afgeleid(t, {"relais_stand": "ontladen", "apparaat_schakelingen": 20068}, DAG1 + 60)
    zl.verwerk_afgeleid(t, {"relais_stand": "laden", "apparaat_schakelingen": 20070}, DAG1 + 120)
    r = zl.relais_samenvatting(t)
    assert r["vandaag"] == 2
    assert r["apparaat_vandaag"] == 4
    assert r["apparaat_totaal"] == 20070
    # nieuwe dag: begint bij de laatst geziene stand, gisteren per dag bewaard
    zl.verwerk_afgeleid(t, {"relais_stand": "laden", "apparaat_schakelingen": 20071}, DAG1 + 86400)
    r = zl.relais_samenvatting(t)
    assert r["apparaat_vandaag"] == 1
    assert list(r["per_dag_apparaat"].values()) == [4]
    assert list(r["per_dag"].values()) == [2]


def test_teller_die_terugloopt_begint_opnieuw():
    t = zl.lege_tellingen()
    zl.verwerk_afgeleid(t, {"apparaat_schakelingen": 500}, DAG1)
    zl.verwerk_afgeleid(t, {"apparaat_schakelingen": 3}, DAG1 + 60)
    assert zl.relais_samenvatting(t)["apparaat_vandaag"] == 0


def test_een_herstart_raakt_de_tellingen_niet():
    """Wat bewaard is, komt terug - ook de per-dag-tellingen en de
    beginstand van de accuteller."""
    t = zl.lege_tellingen()
    zl.verwerk_afgeleid(t, {"relais_stand": "laden", "apparaat_schakelingen": 100}, DAG1)
    zl.verwerk_afgeleid(t, {"relais_stand": "ontladen", "apparaat_schakelingen": 102}, DAG1 + 60)
    zl.verwerk_afgeleid(t, {"relais_stand": "laden", "apparaat_schakelingen": 104}, DAG1 + 86400)
    import json

    terug = zl.lege_tellingen()
    terug.update(zl.herstel(json.loads(json.dumps(t))))
    assert terug["relais"] == t["relais"]
    zl.verwerk_afgeleid(terug, {"relais_stand": "ontladen", "apparaat_schakelingen": 106}, DAG1 + 86460)
    r = zl.relais_samenvatting(terug)
    assert r["vandaag"] == 2 and r["totaal"] == 3 and r["apparaat_vandaag"] == 4
    assert list(r["per_dag"].values()) == [1]


def test_oude_opslag_zonder_de_nieuwe_velden_laadt():
    oud = {"schema": zl.SCHEMA, "relais": {"dag": "2026-10-08", "vandaag": 27, "totaal": 27,
                                           "stand": "laden", "per_dag": {}}}
    t = zl.lege_tellingen()
    t.update(zl.herstel(oud))
    r = zl.relais_samenvatting(t)
    assert r["vandaag"] == 27 and "apparaat_vandaag" not in r
    zl.verwerk_afgeleid(t, {"relais_stand": "ontladen", "apparaat_schakelingen": 9}, DAG1)
    assert zl.relais_samenvatting(t)["vandaag"] == 28


def test_een_wissel_wordt_meteen_bewaard():
    t = zl.lege_tellingen()
    assert zl.verwerk_afgeleid(t, {"relais_stand": "laden"}, DAG1) is True
    assert zl.verwerk_afgeleid(t, {"relais_stand": "laden"}, DAG1 + 2) is False
    assert zl.verwerk_afgeleid(t, {"relais_stand": "ontladen"}, DAG1 + 4) is True

    class _Opslag:
        def __init__(self):
            self.n = 0

        async def async_save(self, data):
            self.n += 1

    m = zl.ZendureLokaalMeelezer(hass=None)
    m._opslag = _Opslag()

    wissels = [True, False]

    async def _binnen():
        if wissels.pop(0):
            m._relais_gewijzigd = True

    m._ronde_binnen = _binnen
    m.tellingen["rondes"] = 1
    asyncio.run(m._ronde())
    assert m._opslag.n == 1 and m._relais_gewijzigd is False
    asyncio.run(m._ronde())
    assert m._opslag.n == 1, "zonder wissel pas weer na BEWAAR_ELKE_RONDES"


def test_de_dag_volgt_de_tijdzone_van_home_assistant():
    bron = inspect.getsource(zl._lokale_dag)
    assert "as_local" in bron
    assert "datetime.fromtimestamp(nu).date()" not in inspect.getsource(zl.verwerk_afgeleid)


def test_de_kaart_noemt_de_accuteller():
    a = {"accu": {"relais_stand": "laden"}, "relaisschakelingen": {"vandaag": 27, "apparaat_vandaag": 48}}
    assert "(accu telt 48)" in zl.tekst("gelijk", a)


# --- 3. verkocht met winst ----------------------------------------------


def _c(make_coordinator):
    c = make_coordinator({})
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.2}
    return c


def _venster(verkoopprijs, tekortprijs):
    """De nacht naar 3 oktober: niet vol (max 70%), 19:00-20:00 circa 1,9 kWh
    verkocht, vanaf 03:00 leeg en import."""
    dagen = {"2026-10-02": [], "2026-10-03": []}
    for k in range(96):
        moment = datetime(2026, 10, 2, 9, 0) + timedelta(minutes=15 * k)
        tijd = moment.strftime("%H:%M")
        if 40 <= k < 44:
            rij = {"soc": 70 - (k - 40) * 4, "net_w": -1950.0, "accu_w": 2100.0,
                   "prijs_ct": verkoopprijs}
        elif k >= 72:
            rij = {"soc": 9, "net_w": 300.0, "accu_w": 0.0, "prijs_ct": tekortprijs}
        else:
            rij = {"soc": 50, "net_w": -50.0, "accu_w": 250.0, "prijs_ct": 35.0}
        dagen[moment.date().isoformat()].append(
            {"tijd": tijd, "stand": "smart", "reden": "default_smart", **rij}
        )
    return dagen


def _rijen(dagen):
    return [r for d in dagen.values() for r in d]


def test_verkocht_boven_de_terugkoopprijs_is_winst(make_coordinator):
    c = _c(make_coordinator)
    soort, reden = c._deel_nacht_in_met_reden(
        _rijen(_venster(45.3, 33.3)), 97.0, 84.3, 4.2, verschuiving_w=50.0
    )
    assert soort == "verkocht_met_winst"
    assert "verkocht met winst" in reden
    assert "45,3 ct" in reden and "33,3 ct" in reden
    assert "€ 0,2" in reden


def test_gelijke_of_lagere_verkoopprijs_blijft_planning(make_coordinator):
    c = _c(make_coordinator)
    for verkoop in (33.3, 30.0):
        soort, _ = c._deel_nacht_in_met_reden(
            _rijen(_venster(verkoop, 33.3)), 97.0, 84.3, 4.2, verschuiving_w=50.0
        )
        assert soort == "planning", verkoop


def test_vol_en_daarna_met_winst_verkocht(make_coordinator):
    c = _c(make_coordinator)
    dagen = _venster(45.3, 33.3)
    dagen["2026-10-02"][32]["soc"] = 100
    soort, reden = c._deel_nacht_in_met_reden(_rijen(dagen), 97.0, 84.3, 4.2, verschuiving_w=50.0)
    assert soort == "verkocht_met_winst"
    assert reden.startswith("vol geweest, daarna")


def _record(c, dagen):
    c.dagverloop = dagen
    c.reserve_daily_records = [
        {
            "date": "2026-10-03", "shortfall": True, "tekortnacht_kwh": 1.6,
            "tekort_soort": "planning", "tekort_soort_herleid": "v5.44",
            "tekort_reden": "1,9 kWh verkocht terwijl de accu niet vol was "
                            "(gem. 45,3 ct, tekort tegen 33,3 ct)",
        },
    ]


def test_de_bewaarde_nacht_van_3_oktober_wordt_omgezet(make_coordinator):
    c = _c(make_coordinator)
    _record(c, _venster(45.3, 33.3))
    assert c.get_tekortsoorten()["tekortnachten_planning"] == 1
    assert c._tekortnachten_meldingen()[0]

    c._herleid_onbekende_tekortnachten()

    record = c.reserve_daily_records[0]
    assert record["tekort_soort"] == "verkocht_met_winst"
    assert record["winsttoets"] == "v5.55"
    assert record["shortfall"] is True, "de marge telt hem nog mee"
    soorten = c.get_tekortsoorten()
    assert soorten["tekortnachten_planning"] == 0
    assert soorten["tekortnachten_verkocht_met_winst"] == 1
    aandacht, info = c._tekortnachten_meldingen()
    assert not aandacht
    assert any("verkocht met winst" in r and "nacht naar 3 okt" in r for r in info)


def test_een_verliesnacht_blijft_aandacht(make_coordinator):
    c = _c(make_coordinator)
    _record(c, _venster(30.0, 33.3))
    c._herleid_onbekende_tekortnachten()
    assert c.reserve_daily_records[0]["tekort_soort"] == "planning"
    assert c.reserve_daily_records[0]["winsttoets"] == "v5.55"
    assert c._tekortnachten_meldingen()[0]


def test_zonder_dagverloop_blijft_hij_staan_en_later_opnieuw(make_coordinator):
    c = _c(make_coordinator)
    _record(c, {})
    c._herleid_onbekende_tekortnachten()
    assert c.reserve_daily_records[0]["tekort_soort"] == "planning"
    assert "winsttoets" not in c.reserve_daily_records[0]
    c.dagverloop = _venster(45.3, 33.3)
    c._probeer_herleiding(datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc))
    assert c.reserve_daily_records[0]["tekort_soort"] == "verkocht_met_winst"


def test_live_ingedeelde_nacht_met_winst(make_coordinator):
    c = _c(make_coordinator)
    c.dagverloop = _venster(45.3, 33.3)
    c._tekort_soort = lambda *a, **k: "planning"
    c._live_tekortvolging_onvolledig = lambda begin: None
    c._tekort_venster_begin = lambda now: datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)
    c._verkocht_na_vol_kwh = 1.9
    c._vol_voor_nacht = False

    c._deel_afgelopen_nacht_in(datetime(2026, 10, 3, 9, 1, tzinfo=timezone.utc))

    assert c._tekort_soort_vandaag == "verkocht_met_winst"
    assert "verkocht met winst" in c._tekort_reden_vandaag


def test_live_zonder_verkoop_blijft_planning(make_coordinator):
    c = _c(make_coordinator)
    c.dagverloop = _venster(45.3, 33.3)
    c._tekort_soort = lambda *a, **k: "planning"
    c._live_tekortvolging_onvolledig = lambda begin: None
    c._tekort_venster_begin = lambda now: datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)
    c._verkocht_na_vol_kwh = 0.1
    c._vol_voor_nacht = False
    c._laadbesluit_stand = "loont"

    c._deel_afgelopen_nacht_in(datetime(2026, 10, 3, 9, 1, tzinfo=timezone.utc))

    assert c._tekort_soort_vandaag == "planning"
