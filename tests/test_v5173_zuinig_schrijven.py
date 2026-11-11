"""v5.173.0: minder databaserijen - alleen schrijven bij een echte wijziging.

Opschoonanalyse 03-11: de GACS-zelfbeoordeling stond 30 minuten op 17 en
schreef 61 rijen. Home Assistant schrijft bij elke state_changed een rij in
`states`, ook als alleen een attribuut verandert dat buiten de recorder
blijft. De poort in zuinig_schrijven.py beslist daarom vóór Home Assistant
of een schrijfbeurt nodig is.
"""
from datetime import datetime, timezone

import pytest

from custom_components.energy_management_system import sensor
from custom_components.energy_management_system import zuinig_schrijven as zs
from custom_components.energy_management_system.const import GEEN_ATTRIBUTEN_IN_RECORDER


class _Basis:
    """Stand-in voor de Home Assistant-entiteit: telt de echte schrijfbeurten."""

    def __init__(self):
        self.geschreven = 0
        self.verwijder_terug = []

    def async_write_ha_state(self):
        self.geschreven += 1

    def async_on_remove(self, fn):
        self.verwijder_terug.append(fn)


class _Bus:
    def __init__(self):
        self.luisteraars = {}

    def async_listen_once(self, soort, fn):
        self.luisteraars[soort] = fn
        return lambda: self.luisteraars.pop(soort, None)


class _Hass:
    def __init__(self):
        self.bus = _Bus()


class _Sensor(zs.ZuinigSchrijven, _Basis):
    _zuinig_attr_interval_s = 600

    def __init__(self):
        super().__init__()
        self.hass = _Hass()
        self.waarde = 17
        self.attrs = {"samenvatting": "goed", "last_successful_update": "t0", "getal": 0.30142}

    @property
    def native_value(self):
        return self.waarde

    @property
    def extra_state_attributes(self):
        return dict(self.attrs)


@pytest.fixture
def klok(monkeypatch):
    stand = {"t": 1000.0}
    monkeypatch.setattr(zs.time, "monotonic", lambda: stand["t"])
    return stand


def test_eerste_keer_schrijft(klok):
    s = _Sensor()
    s.async_write_ha_state()
    assert s.geschreven == 1


def test_alleen_vluchtige_tijdstempel_schrijft_niet(klok):
    s = _Sensor()
    s.async_write_ha_state()
    for i in range(1, 20):  # tien minuten lang elke 30 s
        klok["t"] += 30
        s.attrs["last_successful_update"] = f"t{i}"
        s.async_write_ha_state()
    assert s.geschreven == 1


def test_vluchtig_volgt_bij_de_hartslag(klok):
    s = _Sensor()
    s.async_write_ha_state()
    klok["t"] += zs.ZUINIG_HARTSLAG_S
    s.attrs["last_successful_update"] = "later"
    s.async_write_ha_state()
    assert s.geschreven == 2


def test_afrondingsruis_telt_niet(klok):
    s = _Sensor()
    s.async_write_ha_state()
    klok["t"] += 30
    s.attrs["getal"] = 0.301419999
    s.async_write_ha_state()
    assert s.geschreven == 1


def test_toestand_veranderd_schrijft_meteen(klok):
    s = _Sensor()
    s.async_write_ha_state()
    klok["t"] += 1
    s.waarde = 18
    s.async_write_ha_state()
    assert s.geschreven == 2


def test_kleine_toestandswijziging_wordt_niet_afgerond(klok):
    """Totaalsensoren (statistiek) moeten elke wijziging houden."""
    s = _Sensor()
    s.waarde = 46.0088
    s.async_write_ha_state()
    klok["t"] += 1
    s.waarde = 46.0089
    s.async_write_ha_state()
    assert s.geschreven == 2


def test_betekenisvol_attribuut_wacht_op_interval(klok):
    s = _Sensor()
    s.async_write_ha_state()
    klok["t"] += zs.ZUINIG_OPWARM_S  # v5.178.1: na de opwarmtijd
    s.async_write_ha_state()
    klok["t"] += 30
    s.attrs["samenvatting"] = "let op"
    s.async_write_ha_state()
    assert s.geschreven == 1  # nog binnen het interval
    klok["t"] += 600
    s.async_write_ha_state()
    assert s.geschreven == 2  # de tik pakt het op na het interval


def test_beschikbaarheid_schrijft_meteen(klok):
    s = _Sensor()
    s.async_write_ha_state()
    klok["t"] += 1
    s.available = False
    s.async_write_ha_state()
    assert s.geschreven == 2


def test_tik_en_stop_aangemeld_en_afgemeld(monkeypatch, klok):
    gestart = []
    monkeypatch.setattr(
        zs, "async_track_time_interval", lambda hass, fn, iv: gestart.append(iv) or (lambda: gestart.append("af"))
    )
    s = _Sensor()
    s.async_write_ha_state()
    s.async_write_ha_state()
    assert len([g for g in gestart if g != "af"]) == 1
    assert zs.EVENT_HOMEASSISTANT_STOP in s.hass.bus.luisteraars
    for fn in s.verwijder_terug:
        fn()
    assert "af" in gestart
    assert s._zuinig_vorige is None
    assert zs.EVENT_HOMEASSISTANT_STOP not in s.hass.bus.luisteraars


def test_bij_stop_altijd_de_actuele_stand(klok):
    """Herstelgegevens (RestoreEntity) komen uit de toestandsmachine."""
    s = _Sensor()
    s.async_write_ha_state()
    klok["t"] += zs.ZUINIG_OPWARM_S  # v5.178.1: na de opwarmtijd
    s.async_write_ha_state()
    klok["t"] += 30
    s.attrs["samenvatting"] = "nieuw"
    s.async_write_ha_state()
    assert s.geschreven == 1
    s._zuinig_bij_stop()
    assert s.geschreven == 2


def test_zonder_hass_gewoon_doorgeven():
    s = _Sensor()
    s.hass = None
    s.async_write_ha_state()
    s.async_write_ha_state()
    assert s.geschreven == 2


def test_fout_bij_opbouwen_laat_home_assistant_de_fout_tonen(klok):
    class Kapot(_Sensor):
        @property
        def extra_state_attributes(self):
            raise RuntimeError("stuk")

    s = Kapot()
    s.async_write_ha_state()
    assert s.geschreven == 1


def test_beslis_los():
    a = {"kern": (True, "1", "x"), "betekenis": (1,), "alles": (1, 2)}
    assert zs.beslis(None, a, 0, 600, 900)
    assert not zs.beslis(a, dict(a), 10, 600, 900)
    b = dict(a, alles=(1, 3))
    assert not zs.beslis(a, b, 899, 600, 900)
    assert zs.beslis(a, b, 900, 600, 900)


GEREMD = [
    "SystemStatusSensor", "ExplanationSensor", "GacsAssessmentSensor",
    "DashboardPaginaSensor", "LuchtreinigerLokaalSensor", "ZendureLokaalSensor",
    "BatteryCoolingSensor", "BatteryModuleHealthSensor", "NilmConfirmedDevicesSensor",
    "WaterUsageSensor", "ReliabilityOverviewSensor", "Repetitie2027Sensor",
    "HourlyConsumptionProfileSensor", "PvHourlyBiasSensor", "AircoBesluitSensor",
    "WeatherEnsembleSensor", "MonteCarloAdvisorySensor",
    "NilmUnconfirmedCandidatesSensor",
    "SelfSufficiencySensor", "SelfConsumptionSensor", "LiveNarrativeSensor",
    "CounterfactualSavingsSensor", "SavingsThisMonthSensor",
    "CounterfactualSavingsTotalSensor", "LivingRoomAircoPredictionSensor",
    "ClimateForecastSensor",
    "ApplianceUsageHoursSensor", "MeetlogSensor",
]


@pytest.mark.parametrize("naam", GEREMD)
def test_churnende_sensoren_hebben_de_poort_en_geen_attributen_in_de_recorder(naam):
    klasse = getattr(sensor, naam)
    assert issubclass(klasse, zs.ZuinigSchrijven)
    # De poort moet vóór de Home Assistant-klasse in de MRO staan.
    mro = klasse.__mro__
    assert mro.index(zs.ZuinigSchrijven) < mro.index(sensor.SensorEntity)
    assert klasse._attr_should_poll is False
    assert klasse._unrecorded_attributes == GEEN_ATTRIBUTEN_IN_RECORDER


def test_live_waarden_op_het_dashboard_houden_een_kort_interval():
    assert sensor.SystemStatusSensor._zuinig_attr_interval_s == 60
    assert sensor.ExplanationSensor._zuinig_attr_interval_s == 60
    assert sensor.AircoBesluitSensor._zuinig_attr_interval_s == 60
    assert sensor.BatteryCoolingSensor._zuinig_attr_interval_s <= 120
    assert sensor.DASHBOARD_PAGINA_INTERVAL_S["aanwezigheid"] == 60
    assert "last_successful_update" in sensor.SystemStatusSensor._zuinig_vluchtig


def test_cockpit_draagt_het_tijdstip_voor_bijgewerkt():
    class C:
        last_successful_update = datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)

        def get_cockpit_svg(self, g):
            return "<svg/>"

        def cockpit_gegevens(self):
            return {"status_kort": "GOED", "status_regel": "ok"}

    s = sensor.CockpitSensor(C(), "e")
    assert s.extra_state_attributes["bijgewerkt"].startswith("2026-11-03T14:00")
    js = (
        __import__("pathlib").Path(sensor.__file__).parent / "www" / "ems-cockpit.js"
    ).read_text(encoding="utf-8")
    assert 'attr(this._s("cockpit"), "bijgewerkt")' in js


# v5.178.1: na de herstart van 08:40 stond de modulegezondheid 5 minuten op
# `modules: []` / `aantal_modules: 0` ("Geen modulegegevens" in de cockpit).
# De eerste schrijfbeurt kwam vóór de eerste EMS-ronde; de toestand bleef "0",
# dus de gevulde lijst wachtte op het attribuutinterval (300 s).


class _Modules(zs.ZuinigSchrijven, _Basis):
    _zuinig_attr_interval_s = 300

    def __init__(self):
        super().__init__()
        self.hass = _Hass()
        self.modules = []

    @property
    def native_value(self):
        return 0

    @property
    def extra_state_attributes(self):
        return {"modules": list(self.modules), "aantal_modules": len(self.modules)}


def test_lege_modulelijst_bij_opstarten_volgt_binnen_een_tik(klok):
    s = _Modules()
    s.async_write_ha_state()  # toevoegen aan HA, vóór de eerste ronde
    assert s.geschreven == 1
    klok["t"] += zs.ZUINIG_TIK_S
    s.modules = [{"module": 1, "soc_percent": 16.0}, {"module": 2}, {"module": 3}]
    s.async_write_ha_state()
    assert s.geschreven == 2


def test_leeg_naar_gevuld_ook_na_de_opwarmtijd(klok):
    s = _Modules()
    s.async_write_ha_state()
    klok["t"] += zs.ZUINIG_OPWARM_S + 30
    s.async_write_ha_state()
    klok["t"] += 30
    s.modules = [{"module": 1}]
    s.async_write_ha_state()
    assert s.geschreven == 2


def test_na_opwarmen_blijft_gewone_ruis_geremd(klok):
    s = _Modules()
    s.modules = [{"module": 1, "soc_percent": 16.0}]
    s.async_write_ha_state()
    klok["t"] += zs.ZUINIG_OPWARM_S
    for i in range(8):  # 4 minuten elke 30 s een andere SoC
        klok["t"] += 30
        s.modules = [{"module": 1, "soc_percent": 17.0 + i}]
        s.async_write_ha_state()
    assert s.geschreven == 2  # één keer na het interval van 300 s


def test_gevuld_naar_leeg_wacht_op_het_interval(klok):
    s = _Modules()
    s.modules = [{"module": 1}]
    s.async_write_ha_state()
    klok["t"] += zs.ZUINIG_OPWARM_S
    s.modules = [{"module": 1, "soc_percent": 20.0}]
    s.async_write_ha_state()  # interval verstreken: tweede rij
    klok["t"] += 30
    s.modules = []
    s.async_write_ha_state()
    assert s.geschreven == 2  # gevuld -> leeg wacht op het interval
    klok["t"] += 30
    s.modules = [{"module": 1}]
    s.async_write_ha_state()
    # de laatst geschreven stand was al gevuld: geen extra rij (geen flapperen)
    assert s.geschreven == 2


def test_leeg_naar_gevuld_los():
    assert zs.leeg_naar_gevuld((("m", ()),), (("m", (1,)),))
    assert zs.leeg_naar_gevuld((("m", None),), (("m", 2),))
    assert zs.leeg_naar_gevuld((), (("nieuw", 1),))
    assert not zs.leeg_naar_gevuld((("m", (1,)),), (("m", (2,)),))
    assert not zs.leeg_naar_gevuld((("m", (1,)),), (("m", ()),))


def test_herstart_van_de_entiteit_begint_opnieuw_met_opwarmen(klok):
    s = _Modules()
    s.async_write_ha_state()
    klok["t"] += zs.ZUINIG_OPWARM_S * 3
    s._zuinig_stop()
    assert s._zuinig_eerste is None
