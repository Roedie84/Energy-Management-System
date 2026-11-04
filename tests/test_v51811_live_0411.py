"""Bevindingen uit de live-geschiedenis van 04-11 (v5.181.1).

1. Terugleveren niet uitgevoerd: de leermodus (knop "Handmatig smart
   charge") hield de opdracht tegen; nu staat dat bij het besluit.
2. Laadvermogen niet bijgeschreven: elke ronde de rest van het kwartier,
   met een marge tegen het huidige getal; planvolging tegen de opdracht.
3. Netladen met genoeg zon: alleen het deel boven het zonoverschot kost
   netstroom.
4. Cockpit: een momentopname voor de tegel en de planvolging.
5. Laadplanning gewijzigd: met reden.
6. Opstartfase: geen opdrachten tot de eerste volle ronde.
7. Planvolging 'nu' elke ronde via de cockpitsensor.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import custom_components.energy_management_system as pkg
from homeassistant.util import dt as dt_util
from custom_components.energy_management_system import planvolging as pv
from custom_components.energy_management_system.const import (
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_MANUAL_CHARGE_POWER,
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
    CONF_PV_POWER_SENSOR,
    HANDMATIGE_STAND_SMART_CHARGE,
)

SELECT = "select.zendure_manager_operation"
NUMBER = "number.zendure_manager_manual_power"
T0 = datetime(2026, 11, 4, 10, 17, 45, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _config(**extra):
    return {CONF_OPERATION_SELECT: SELECT, CONF_MANUAL_POWER_NUMBER: NUMBER, **extra}


# --- 1. niet gestuurd: zichtbaar bij het besluit ---------------------------


def test_leermodus_staat_bij_het_besluit(make_coordinator, hass):
    c = make_coordinator(_config())
    c.learning_only = True
    c.handmatige_stand = HANDMATIGE_STAND_SMART_CHARGE
    zin = c._waardeplan_niet_gestuurd(T0)
    assert zin.startswith("leermodus") and HANDMATIGE_STAND_SMART_CHARGE in zin
    c.last_waardeplan = {"niet_gestuurd": zin}
    assert "Niet naar de accu gestuurd" in c._reden_uitleg("waardeplan_terugleveren")


def test_zonder_leermodus_niets_vermeld(make_coordinator, hass):
    c = make_coordinator(_config())
    assert c._waardeplan_niet_gestuurd(T0) is None
    c.last_waardeplan = {"niet_gestuurd": None}
    assert "Niet naar de accu" not in c._reden_uitleg("waardeplan_terugleveren")


# --- 2. het laadvermogen volgt de rest van het kwartier ----------------------


def _plan(berekend=T0, inhoud=3.0):
    rij = {"actie": "laden_net", "accu_kwh": 0.4, "uren": 0.2042, "vol_vermogen": False}
    return rij, {"berekend_om": berekend.isoformat(), "inhoud_kwh": inhoud,
                 "laadrendement_procent": 100, "nu": rij}


def test_vermogen_in_dezelfde_ronde_is_de_rij(make_coordinator, hass):
    c = make_coordinator(_config(**{CONF_MANUAL_CHARGE_POWER: 2400}))
    c.beschikbare_energie_kwh = lambda: 3.0
    rij, plan = _plan()
    assert round(c._waardeplan_laadvermogen_nu_w(rij, plan, T0)) == round(0.4 * 1000 / 0.2042)


def test_vermogen_later_in_het_kwartier_naar_de_rest(make_coordinator, hass):
    """10:21, nog niets geladen (smart_charging tussendoor): 0,4 kWh in 9 min
    is meer dan 2400 W, dus vol vermogen in plaats van de oude 1782 W."""
    c = make_coordinator(_config(**{CONF_MANUAL_CHARGE_POWER: 2400}))
    c.beschikbare_energie_kwh = lambda: 3.0
    rij, plan = _plan()
    later = T0.replace(minute=21, second=0)
    assert c._waardeplan_laadvermogen_nu_w(rij, plan, later) == 2400


def test_vermogen_na_een_deel_geladen(make_coordinator, hass):
    c = make_coordinator(_config(**{CONF_MANUAL_CHARGE_POWER: 2400}))
    c.beschikbare_energie_kwh = lambda: 3.3  # 0,3 van 0,4 kWh al geladen
    rij, plan = _plan()
    later = T0.replace(minute=24, second=0)  # nog 6 minuten
    assert round(c._waardeplan_laadvermogen_nu_w(rij, plan, later)) == 1000


def test_marge_tegen_het_huidige_getal(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "manual")
    hass.states.set(NUMBER, "-1782.0")
    assert c._als_al_ingesteld(-1800) == -1782.0
    assert c._als_al_ingesteld(-2400) == -2400
    hass.states.set(SELECT, "smart_charging")
    assert c._als_al_ingesteld(-1800) == -1800


def test_planvolging_tegen_de_opdracht():
    """De Zendure volgt de -1782 W van het EMS exact; het plan noemde 2400 W."""
    gepland = {"accu_w": -2400, "zon_w": 1480, "huis_w": 200, "modus": "manual (laden)"}
    oordeel = pv.beoordeel(gepland, -1775, 1480, 200, stand="manual", opdracht_w=-1782)
    assert oordeel["status"] == "volgens plan"
    assert oordeel["gepland_accu_w"] == -1782 and oordeel["plan_accu_w"] == -2400
    zonder = pv.beoordeel(gepland, -1775, 1480, 200, stand="manual")
    assert zonder["status"] == "afwijking accu"


# --- 3. netladen met zon --------------------------------------------------


def test_netladen_boven_het_zonoverschot(make_coordinator, hass):
    c = make_coordinator(_config(**{CONF_PV_POWER_SENSOR: "sensor.pv"}))
    c._get_current_price_per_kwh = lambda entries, now: 0.25
    c._gemeten_accu_w = lambda opdracht, richting: 2000.0
    c._read_sensor_float = lambda e: 1500.0  # zon
    c._read_corrected_consumption_power = lambda: 500.0  # huis -> 1 kW overschot
    c._last_value_calc_time = T0
    c.total_charge_cost_eur = 0.0
    c._update_financial_tracking(T0 + timedelta(hours=1), [], "waardeplan_laden", None, -2000)
    # 2 kWh geladen, 1 kWh uit de zon: alleen 1 kWh netstroom
    assert abs(c.total_charge_cost_eur - 0.25) < 1e-9
    assert c.last_laadsplitsing["zon_kwh"] == 1.0


# --- 4 en 7. een momentopname voor tegel en planvolging ----------------------


def _met_metingen(make_coordinator):
    c = make_coordinator(_config(**{CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1"}))
    c._read_corrected_battery_power = lambda: -1160.0
    c._live_pv_w = lambda: 1480.0
    c._read_sensor_float = lambda e: -120.0 if e == "sensor.p1" else None
    c._read_corrected_consumption_power = lambda: 200.0
    return c


def test_momentopname_een_bron(make_coordinator, hass):
    c = _met_metingen(make_coordinator)
    m = c._live_momentopname(T0)
    assert (m["accu_w"], m["zon_w"], m["net_w"], m["huis_w"]) == (-1160.0, 1480.0, -120.0, 200.0)
    assert c.live_momentopname is m


def test_huis_uit_dezelfde_opname_als_het_huis_ontbreekt(make_coordinator, hass):
    c = _met_metingen(make_coordinator)
    c._read_corrected_consumption_power = lambda: None
    assert c._live_momentopname(T0)["huis_w"] == 200.0  # 1480 - 120 - 1160


def test_planvolging_nu_uit_de_momentopname(make_coordinator, hass):
    c = _met_metingen(make_coordinator)
    c._planvolging = {"begin": T0.isoformat(), "monsters": [],
                      "gepland": {"accu_w": -1160, "zon_w": 1480, "huis_w": 200, "modus": "smart"}}
    c._planvolging["monsters"].append(c._live_momentopname(T0))
    nu = c.planvolging_nu()
    assert nu["gemeten_accu_w"] == -1160 and nu["status"] == "volgens plan"
    assert nu["moment"] == T0.isoformat()
    assert c.get_planvolging()["nu"] == nu


def test_cockpitsensor_draagt_opname_en_planvolging():
    bron = (Path(pkg.__file__).parent / "sensor.py").read_text(encoding="utf-8")
    assert '"stroom": gegevens.get("stroom")' in bron
    assert '"planvolging_nu": gegevens.get("planvolging_nu")' in bron


def test_cockpit_leest_de_opname_en_tekent_bij_elke_ronde():
    js = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert '"cockpit", "accu_vermogen", "pv", "net", "modus"]' in js
    assert "planvolgingLive(" in js and "_live()" in js
    assert 'attr(this._s("cockpit"), "planvolging_nu")' in js
    assert 'attr(this._s("cockpit"), "stroom")' in js
    assert "w.reden" in js


# --- 5. laadplanning gewijzigd: met reden -----------------------------------


def _laadplan(laden):
    return [{"start": (T0.replace(minute=15, second=0) + timedelta(minutes=15 * i)).isoformat(),
             "modus": "manual (laden)" if i in laden else "smart"} for i in range(12)]


def test_laadplan_wijziging_door_nieuwe_prijzen(make_coordinator, hass):
    c = make_coordinator(_config())
    c.in_opstartfase = lambda now=None: False
    c.beschikbare_energie_kwh = lambda: 3.0
    c._zon_vandaag_totaal = lambda now: (6.0, 2.0, 4.0)
    eind = T0 + timedelta(hours=10)
    c._get_forecast_entries = lambda: [(T0, eind, 0.20)]
    c._volg_laadplan(_laadplan([1, 2, 3]), T0)
    assert c.get_laadplan_gewijzigd()["reden"] == "eerste planning"
    c._get_forecast_entries = lambda: [(T0, eind + timedelta(hours=12), 0.18)]
    c._volg_laadplan(_laadplan([]), T0 + timedelta(minutes=13))
    assert "nieuwe prijzen" in c.get_laadplan_gewijzigd()["reden"]


def test_laadplan_reden_zon_en_huis_eerst():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    oud = {"prijzen_tot": "x", "prijzen": 1.0, "zon_kwh": 6.0, "huis_eerst": False, "inhoud_kwh": 3.0}
    nu = {**oud, "zon_kwh": 4.0, "huis_eerst": True}
    reden = C._laadplan_reden(oud, nu)
    assert "zonverwachting" in reden and "huis-eerst-regel aan" in reden
    assert C._laadplan_reden(oud, dict(oud)) == "verbruik bijgesteld (live correctie)"


# --- 6. opstartfase: geen opdrachten ----------------------------------------


def test_geen_opdrachten_in_de_opstartfase(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "smart_charging")
    hass.states.set(NUMBER, "0")
    c._opstart_stil_tot = dt_util.now() + timedelta(minutes=3)
    _run(c._async_apply_manual(-1782))
    _run(c._async_apply_operation("smart_charging"))
    assert hass.services.calls == []
    assert c.last_simulated_action.startswith("opstartfase")


def test_na_de_opstartfase_weer_sturen(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "smart_charging")
    hass.states.set(NUMBER, "0")
    c._opstart_stil_tot = dt_util.now() - timedelta(seconds=1)
    _run(c._async_apply_manual(-2400))
    assert any(d == "number" for d, _s, _x in hass.services.calls)
    assert c._opstart_stil_tot is None


def test_knop_van_de_gebruiker_gaat_door_in_de_opstartfase(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(SELECT, "manual")
    hass.states.set(NUMBER, "0")
    c._opstart_stil_tot = dt_util.now() + timedelta(minutes=3)
    c.async_set_learning_only = lambda waarde: asyncio.sleep(0)
    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_SMART_CHARGE, T0))
    assert ("select", "select_option", {"entity_id": SELECT, "option": "smart_charging"}) in hass.services.calls
    assert c._gebruikersopdracht is False


def test_plan_uit_de_opstartfase_wordt_niet_vastgehouden(make_coordinator, hass):
    c = make_coordinator(_config())
    c._opstart_stil_tot = dt_util.now() + timedelta(minutes=3)
    c.beschikbare_energie_kwh = lambda: 3.0
    c.bereken_waardeplan = lambda now, entries: {"beschikbaar": True, "inhoud_kwh": 3.0, "nu": {}}
    c._waardeplan_nu(dt_util.now(), [])
    assert c._waardeplan_cache is None
    c._opstart_stil_tot = None
    c._waardeplan_nu(dt_util.now(), [])
    assert c._waardeplan_cache is not None


def test_opstart_stil_gezet_bij_het_laden_van_de_opslag():
    """v5.186.0 (B21): het laden van de opslag zet de stille fase klaar; hij
    begint pas bij de eerste ronde (zie tests/test_v5186_B_ronde.py)."""
    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text(encoding="utf-8")
    assert "self._opstart_stil_wacht_op_ronde = True" in bron
    assert "self._opstart_stil_tot = now + timedelta(seconds=STARTUP_GRACE_SECONDS)" in bron


# --- 8. alles live -----------------------------------------------------------


def test_opnieuw_plannen_als_de_accu_afwijkt_van_het_plan_voor_nu(make_coordinator, hass):
    """10:56: plan verwachtte ~19 %, de accu stond op ~31 %: direct opnieuw."""
    from custom_components.energy_management_system.waardeplan_sturing import WaardeplanSturingMixin as W

    plan = {"berekend_om": T0.isoformat(), "inhoud_kwh": 1.0, "nu": {"inhoud_kwh": 1.0, "uren": 0.25}}
    assert W._waardeplan_wijkt_live_af(T0 + timedelta(minutes=5), plan, 1.05) is False
    assert W._waardeplan_wijkt_live_af(T0 + timedelta(minutes=5), plan, 1.9) is True
    # halverwege een geplande lading van 0,4 kWh is 1,2 kWh verwacht
    plan["nu"]["inhoud_kwh"] = 1.4
    halverwege = T0 + timedelta(minutes=7, seconds=30)
    assert W._waardeplan_wijkt_live_af(halverwege, plan, 1.2) is False
    assert W._waardeplan_wijkt_live_af(halverwege, plan, 1.0) is True


def test_waardeplan_rekent_opnieuw_bij_afwijking(make_coordinator, hass):
    c = make_coordinator(_config())
    teller = []
    inhoud = {"kwh": 1.0}
    c.beschikbare_energie_kwh = lambda: inhoud["kwh"]

    def reken(now, entries):
        teller.append(now)
        return {"beschikbaar": True, "berekend_om": now.isoformat(), "inhoud_kwh": inhoud["kwh"],
                "nu": {"inhoud_kwh": inhoud["kwh"], "uren": 0.25, "accu_kwh": 0.0}}

    c.bereken_waardeplan = reken
    c._waardeplan_nu(T0, [])
    c._waardeplan_nu(T0 + timedelta(minutes=1), [])
    assert len(teller) == 1
    inhoud["kwh"] = 1.3  # de zon vult meer dan gepland
    c._waardeplan_nu(T0 + timedelta(minutes=2), [])
    assert len(teller) == 2


def test_cockpitsensoren_elke_ronde():
    from custom_components.energy_management_system import sensor

    for klasse in sensor.COCKPIT_SENSOREN:
        assert klasse._zuinig_attr_interval_s <= 60, klasse.__name__
    assert sensor.DASHBOARD_PAGINA_INTERVAL_S["kwartierplanning_tabel"] <= 60


def test_bronnen_voor_de_live_cockpit():
    from custom_components.energy_management_system.cockpit_bronnen import externe_bronnen
    from custom_components.energy_management_system.const import (
        CONF_BATTERY_MODULE_POWER_SENSORS,
        CONF_DISHWASHER_POWER_SENSOR,
    )

    uit = externe_bronnen({CONF_BATTERY_MODULE_POWER_SENSORS: ["sensor.w1"],
                           CONF_DISHWASHER_POWER_SENSOR: "sensor.vw"})
    assert uit["modules_vermogen"] == ["sensor.w1"]
    assert uit["vaatwasser_w"] == "sensor.vw"
    assert uit["accu_teken"] == "positief_is_ontladen"


def test_cockpit_tekent_hoogstens_twee_keer_per_seconde_en_soc_lijn_live():
    js = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert "const TEKEN_MIN_MS = 500;" in js
    assert "const socLive = getal(this._s(\"soc\"));" in js
    assert "live.zon + live.net + live.accu" in js


# --- 9. een weergave van de stand ----------------------------------------------


def test_standweergave():
    from custom_components.energy_management_system.standweergave import weergave

    assert weergave("waardeplan_houden", "smart_charging", -1290) == {
        "k": "zon", "label": "Zon laden – lading bewaren voor later"}
    assert weergave("waardeplan_houden", "smart_charging", 10)["label"] == "Bewaren voor later"
    assert weergave("waardeplan_huis", "smart", 600)["label"] == "Huis voeden"
    assert weergave("waardeplan_laden", "manual (laden)", -2400)["k"] == "net"
    assert weergave("waardeplan_terugleveren", "manual (terugleveren)", 0)["k"] == "terug"
    assert weergave("waardeplan_leeg", "smart_charging", 0)["k"] == "leeg"


def test_standweergave_in_cockpit_gelijk_aan_python():
    import re

    from custom_components.energy_management_system import standweergave as sw

    js = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")

    def tabel(naam):
        blok = js.split(f"const {naam} = {{", 1)[1].split("};", 1)[0]
        return dict(re.findall(r'(\w+): "([^"]+)"', blok))

    assert tabel("STAND_TOELICHTING") == sw.TOELICHTING
    assert tabel("STAND_RUST") == sw.RUST_LABEL
    doen = js.split("const DOEN = {", 1)[1].split("};", 1)[0]
    labels = dict(re.findall(r'(\w+): \{ label: "([^"]+)"', doen))
    assert labels == sw.STANDEN


def test_kop_en_melding_zeggen_wat_er_gebeurt(make_coordinator, hass):
    c = make_coordinator(_config())
    c._read_corrected_battery_power = lambda: -1290.0
    c.last_reason = "waardeplan_houden"
    c.last_waardeplan = {"nu": {"actie": "houden"}}
    assert c._waarom_kop("waardeplan_houden") == "Zon laden – lading bewaren voor later"
    assert c._modusmelding_titel().endswith("Accu: Zon laden – lading bewaren voor later")
    c._read_corrected_battery_power = lambda: 5.0
    assert c._waarom_kop("waardeplan_houden") == "Bewaren voor later"
