"""v5.186.0 (spoor D): geld, perioden, meldingen en schrijflast.

Punten 44-60 uit de doorlichting van 04-11; elk testje noemt zijn punt.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import custom_components.energy_management_system as pkg

BRON = Path(pkg.__file__).parent
JS = (BRON / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _met_klok(mod, moment):
    oud = mod.dt_util.now
    mod.dt_util.now = lambda: moment
    return oud


# --- 44: maandmelding over de afgesloten maand ---------------------------------


def test_44_maandwissel_bewaart_de_vorige_maand(make_coordinator):
    c = make_coordinator({})
    c._counterfactual_month_key = 202610
    c.actual_cost_current_month_eur = 12.345
    c.counterfactual_cost_current_month_eur = 20.0
    c._wissel_tegenfeit_maand(202611)
    assert c.actual_cost_current_month_eur == 0.0
    assert c.maand_vorige["maand"] == "2026-10"
    assert c.maand_vorige["werkelijk_eur"] == 12.35
    assert c.maand_vorige["besparing_rauw_eur"] == 7.65


def test_44_gecorrigeerde_maandbesparing_komt_erbij(make_coordinator):
    c = make_coordinator({})
    c._bewaar_vorige_maand("2026-10", werkelijk_eur=10.0, zonder_accu_eur=14.0)
    c._bewaar_vorige_maand("2026-10", besparing_gecorrigeerd_eur=3.5)
    assert c.maand_vorige["besparing_gecorrigeerd_eur"] == 3.5
    assert c.maand_vorige["werkelijk_eur"] == 10.0


def test_44_tekst_gaat_over_de_vorige_maand(make_coordinator):
    c = make_coordinator({})
    c.maand_vorige = {"maand": "2026-10", "werkelijk_eur": 30.0, "zonder_accu_eur": 42.5,
                      "besparing_gecorrigeerd_eur": 11.0}
    tekst = c.maandoverzicht_tekst(datetime(2026, 11, 1, 10, tzinfo=timezone.utc))
    assert "30.00 €" in tekst and "42.50 €" in tekst and "12.50 €" in tekst and "11.00" in tekst


def test_44_zonder_bewaarde_maand_geen_tekst(make_coordinator):
    c = make_coordinator({})
    c.maand_vorige = {"maand": "2026-09", "werkelijk_eur": 1.0, "zonder_accu_eur": 2.0}
    assert c.maandoverzicht_tekst(datetime(2026, 11, 1, 10, tzinfo=timezone.utc)) is None


def test_44_januari_kijkt_naar_december(make_coordinator):
    c = make_coordinator({})
    c.maand_vorige = {"maand": "2025-12", "werkelijk_eur": 1.0, "zonder_accu_eur": 2.0}
    assert c.maandoverzicht_tekst(datetime(2026, 1, 1, 10, tzinfo=timezone.utc))


def test_44_maand_vorige_wordt_bewaard():
    from custom_components.energy_management_system.const import PERSISTED_FIELDS
    assert "maand_vorige" in PERSISTED_FIELDS


# --- 45: dagsensor die laat reset ---------------------------------------------


def test_45_late_reset_zet_het_ijkpunt_op_nul(make_coordinator, hass):
    from custom_components.energy_management_system import coordinator as mod
    from custom_components.energy_management_system.const import CONF_COST_ENERGY_SENSOR

    c = make_coordinator({CONF_COST_ENERGY_SENSOR: "sensor.kosten_vandaag"})
    oud = _met_klok(mod, datetime(2026, 11, 5, 0, 20, tzinfo=timezone.utc))
    try:
        c._kosten_meter_dagbegin = 3.50          # stand van gisteren om 00:00
        hass.states.set("sensor.kosten_vandaag", "0.10")   # leverancier reset nu
        assert c._kosten_vandaag_uit_meter() == 0.10
        assert c._kosten_meter_dagbegin == 0.0
        hass.states.set("sensor.kosten_vandaag", "3.60")   # later op de dag
        assert c._kosten_vandaag_uit_meter() == 3.60      # was 0,10
        assert c._kosten_meter_ijkpunt() == 0.0           # volgende dagwissel
    finally:
        mod.dt_util.now = oud


def test_45_last_reset_betekent_dagsensor(make_coordinator, hass):
    from custom_components.energy_management_system.const import CONF_COST_ENERGY_SENSOR

    c = make_coordinator({CONF_COST_ENERGY_SENSOR: "sensor.k"})
    hass.states.set("sensor.k", "2.0", {"last_reset": "2026-11-04T00:00:00+01:00"})
    assert c._kosten_meter_ijkpunt() == 0.0
    hass.states.set("sensor.k", "1234.5")
    assert c._kosten_meter_ijkpunt() == 1234.5


# --- 46/53: besparing totaal ----------------------------------------------------


def test_46_cockpit_leest_het_gecorrigeerde_totaal():
    assert 'attr(bes, "besparing_totaal_gecorrigeerd_eur")' in JS
    code = (BRON / "sensor.py").read_text(encoding="utf-8")
    assert '"besparing_totaal_gecorrigeerd_eur": round(' in code
    assert "Maand- en all-time-totalen zijn rauw." not in code


def test_53_totaal_op_twee_decimalen():
    from custom_components.energy_management_system.sensor import CounterfactualSavingsTotalSensor
    c = SimpleNamespace(besparing_totaal_gecorrigeerd_eur=lambda: 42.33449, _wacht_op_eerste_ronde=False)
    assert CounterfactualSavingsTotalSensor(c, "e").native_value == 42.33


# --- 47/50: perioden ------------------------------------------------------------


def _perioden(make_coordinator, dagen=20):
    from custom_components.energy_management_system import coordinator as mod
    nu = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu
    c = make_coordinator({})
    c.energy_daily_history = [
        {"datum": (nu.date() - timedelta(days=n)).isoformat(), "opwek_kwh": 1.0, "netto_eur": 2.0}
        for n in range(1, dagen + 1)
    ]
    c.actual_cost_today_eur = -0.456
    return c, nu


def test_47_vandaag_heeft_saldo_en_telt_eerlijk(make_coordinator):
    c, nu = _perioden(make_coordinator)
    c.prijs_vandaag = {"dag": nu.date().isoformat(), "inkoop_eur": 1.23}
    v = c.get_period_overview(nu)["perioden"]["vandaag"]
    assert v["netto_eur"] == -0.46
    assert v["inkoop_eur"] == 1.23
    assert v["dagen_met_waarde"]["netto_eur"] == 1
    assert v["dagen_met_waarde"]["inkoop_eur"] == 1
    assert v["dagen_met_waarde"]["gas_eur"] == 0


def test_50_week_is_zeven_afgesloten_dagen(make_coordinator):
    c, nu = _perioden(make_coordinator)
    c.energy_daily_history.append({"datum": nu.date().isoformat(), "opwek_kwh": 99.0})
    week = c.get_period_overview(nu)["perioden"]["week"]
    assert week["dagen"] == 7 and week["opwek_kwh"] == 7.0


def test_50_cockpit_noemt_de_dagen_met_saldo():
    assert "dagen_met_waarde || {}).netto_eur" in JS
    assert "Saldo van de laatste 7 afgesloten dagen" in JS


# --- 48: verouderde sensoren ----------------------------------------------------


def test_48_cockpit_abonneert_niet_meer_op_de_maandsensor():
    assert 'maand: "monthly_summary"' not in JS
    assert 'geld: ["besparing", "maand",' not in JS


def test_48_oude_sensoren_zeggen_dat_ze_verouderd_zijn():
    from custom_components.energy_management_system.sensor import ChargeCostSensor, DischargeValueSensor
    c = SimpleNamespace(total_charge_cost_eur=1.0, total_discharge_value_eur=2.0)
    for klasse in (ChargeCostSensor, DischargeValueSensor):
        assert klasse(c, "e").extra_state_attributes["verouderd"] is True


# --- 49: daily_cost_history -----------------------------------------------------


def test_49_gat_wordt_met_lege_dagen_gevuld(make_coordinator):
    c = make_coordinator({})
    c._daily_cost_day_key = date(2026, 11, 1)
    c._laatste_dagstand = {"stroom_eur": 1.5, "gas_eur": 0.5, "datum": "2026-11-01"}
    c._update_daily_cost_history(datetime(2026, 11, 4, 0, 1, tzinfo=timezone.utc))
    rijen = c.daily_cost_history[-3:]
    assert [r["datum"] for r in rijen] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert rijen[0]["stroom_eur"] == 1.5 and rijen[1]["stroom_eur"] is None


def test_49_stand_van_een_andere_dag_telt_niet(make_coordinator):
    c = make_coordinator({})
    c._daily_cost_day_key = date(2026, 11, 3)
    c._laatste_dagstand = {"stroom_eur": 9.0, "gas_eur": 1.0, "datum": "2026-11-02"}
    c._update_daily_cost_history(datetime(2026, 11, 4, 0, 1, tzinfo=timezone.utc))
    assert c.daily_cost_history[-1] == {"datum": "2026-11-03", "stroom_eur": None, "gas_eur": None}


def test_49_lopende_stand_wordt_bewaard():
    from custom_components.energy_management_system.const import PERSISTED_FIELDS
    assert "_laatste_dagstand" in PERSISTED_FIELDS


def test_49_week_op_datum(make_coordinator):
    c = make_coordinator({})
    c.daily_cost_history = [{"datum": f"2026-10-{d:02d}", "stroom_eur": 1.0, "gas_eur": None}
                            for d in range(1, 21) if d not in (15, 16, 17)]
    c._huidige_dagkosten = lambda: {"stroom_eur": 0.0, "gas_eur": None}
    # 14-20 okt: 15, 16, 17 ontbreken -> 4 dagen, niet de laatste 7 regels
    assert c.get_energy_cost_overview()["stroom"]["week"] == 4.0


# --- 52: modulemelding ----------------------------------------------------------


def test_52_oude_modulesleutel_meldt_niet(make_coordinator):
    c = make_coordinator({})
    c.battery_module_live = [{"module": i, "naam": f"Accu module {i}", "apparaat_id": f"AB3000 0{i}"}
                             for i in (1, 2, 3)]
    drift = {"cusum": {"temperatuur_afwijking_c": {"drift": True}}}
    c.battery_module_health = {"1": dict(drift), "4": dict(drift)}
    assert c._modules_met_drift() == ["1"]
    assert c._module_drift_labels(["1"]) == ["Accu module 1 (AB3000 01)"]


# --- 54: attributen per ronde ---------------------------------------------------


def test_54_attributen_een_keer_per_schrijfbeurt():
    from custom_components.energy_management_system.zuinig_schrijven import ZuinigSchrijven

    class Basis:
        geschreven = 0

        def async_write_ha_state(self):
            Basis.geschreven += 1
            _ = self.extra_state_attributes

    teller = {"n": 0}

    class S(ZuinigSchrijven, Basis):
        hass = None
        native_value = 1

        @property
        def extra_state_attributes(self):
            teller["n"] += 1
            return {"a": teller["n"]}

    s = S()
    s.hass = SimpleNamespace()
    s._zuinig_start_tik = lambda: None
    s.async_write_ha_state()
    assert Basis.geschreven == 1 and teller["n"] == 1
    # buiten een schrijfbeurt (en zonder ronde) vers
    assert s.extra_state_attributes == {"a": 2}


def test_54_tik_hergebruikt_binnen_dezelfde_ronde():
    from custom_components.energy_management_system.zuinig_schrijven import ZuinigSchrijven

    teller = {"n": 0}
    ronde = datetime(2026, 11, 4, 20, tzinfo=timezone.utc)

    class S(ZuinigSchrijven):
        @property
        def extra_state_attributes(self):
            teller["n"] += 1
            return {}

    s = S()
    s._coordinator = SimpleNamespace(last_successful_update=ronde)
    s.__dict__["_zuinig_via_tik"] = True
    _ = s.extra_state_attributes
    _ = s.extra_state_attributes
    assert teller["n"] == 1
    s._coordinator.last_successful_update = ronde + timedelta(seconds=30)
    _ = s.extra_state_attributes
    assert teller["n"] == 2


# --- 55: lichtere attributen ----------------------------------------------------


def test_55_planregel_compacter(make_coordinator):
    c = make_coordinator({})
    r = c._compacte_planregel({"van": "08:00", "zon_kwh": 0.1234, "cumulatief_eur": -0.456,
                               "accu_w": None, "net_w": None, "zon_w": 0, "huis_w": 300})
    assert r == {"van": "08:00", "zon_kwh": 0.12, "cumulatief_eur": -0.46, "zon_w": 0, "huis_w": 300}


# --- 56: netladen op de laaddag -------------------------------------------------


def test_56_marge_bij_de_laaddag():
    from custom_components.energy_management_system import accukosten as A
    tel = A._Teller()
    partijen = []
    A._boek_lading(partijen, tel, "2026-10-31", {"reden": "grid_charging_dip"}, 1.0, 1.0, 0.10)
    A._boek_levering(partijen, tel, "2026-11-01", 1.0, 1.0, 1.0, 0.30, 0.0)
    nu = datetime(2026, 11, 2, tzinfo=timezone.utc)
    okt = A._samenvatting(tel, partijen, 0.9, 0.0, datetime(2026, 10, 31, tzinfo=timezone.utc))["netladen_maand"]
    nov = A._samenvatting(tel, partijen, 0.9, 0.0, nu)["netladen_maand"]
    assert okt["net_inkoop_eur"] == 0.1 and okt["net_marge_eur"] == pytest.approx(0.2)
    assert nov["net_marge_eur"] == 0.0 and nov["net_marge_ontlaaddag_eur"] == pytest.approx(0.2)


# --- 57: generale repetitie -----------------------------------------------------


def test_57_per_dag_deelt_door_dagen_met_waarde():
    from custom_components.energy_management_system import regime2027 as R
    dagen = [{"te_becijferen": True, "accu_levert_op_2027_eur": 1.0, "regels_laten_liggen_eur": 0.5},
             {"te_becijferen": True, "accu_levert_op_2027_eur": 3.0, "regels_laten_liggen_eur": None},
             {"te_becijferen": True}]
    s = R.samenvatting(dagen)
    assert s["per_dag_2027_eur"] == 2.0
    # aandeel alleen over de dag met beide waarden: 0,5 / (1,0 + 0,5)
    assert s["gemist_aandeel_procent"] == pytest.approx(33.3)


# --- 58: cockpitscript ----------------------------------------------------------


def test_58_vaste_url_en_niet_dubbel_geladen(monkeypatch):
    import asyncio
    import sys
    import types

    from custom_components.energy_management_system import cockpit_frontend as cf

    extra = []
    mods = {
        "homeassistant.components.frontend": types.SimpleNamespace(add_extra_js_url=lambda h, u: extra.append(u)),
        "homeassistant.components.http": types.SimpleNamespace(StaticPathConfig=lambda *a, **k: None),
    }
    for naam, mod in mods.items():
        monkeypatch.setitem(sys.modules, naam, mod)

    class Bronnen:
        def __init__(self):
            self.items = []

        def async_items(self):
            return self.items

        async def async_create_item(self, item):
            self.items.append({"id": "1", **item})

    class Http:
        async def async_register_static_paths(self, paden):
            pass

    bronnen = Bronnen()
    h = types.SimpleNamespace(data={"lovelace": types.SimpleNamespace(resources=bronnen)}, http=Http())
    lus = asyncio.new_event_loop()
    lus.run_until_complete(cf.async_registreer_cockpit(h, "5.186.0"))
    eerste = bronnen.items[0]["url"]
    lus.run_until_complete(cf.async_registreer_cockpit(h, "5.186.0"))
    assert bronnen.items[0]["url"] == eerste and "&t=" not in eerste
    assert eerste.startswith("/energy_management_system/ems-cockpit.js?v=5.186.0-")
    assert extra == []


# --- 59: contractstart ----------------------------------------------------------


def test_59_schrikkeldag_valt_terug_op_28_februari(make_coordinator):
    from custom_components.energy_management_system.const import CONF_CONTRACT_START_DATE
    c = make_coordinator({CONF_CONTRACT_START_DATE: "2024-02-29"})
    assert c._huidig_contractjaar_begin(date(2026, 11, 4)) == date(2026, 2, 28)
    assert c._huidig_contractjaar_begin(date(2028, 3, 1)) == date(2028, 2, 29)


def test_59_config_controleert_de_datum():
    code = (BRON / "config_flow.py").read_text(encoding="utf-8")
    assert 'errors[CONF_CONTRACT_START_DATE] = "invalid_date"' in code


# --- 60: opruimen ---------------------------------------------------------------


def test_60_pv_daily_history_is_weg():
    from custom_components.energy_management_system.const import PERSISTED_FIELDS
    assert "pv_daily_history" not in PERSISTED_FIELDS
    assert "self.pv_daily_history" not in (BRON / "coordinator.py").read_text(encoding="utf-8")


def test_60_oude_opslag_met_pv_daily_history_laadt(make_coordinator):
    c = make_coordinator({})
    c._apply_persisted_state({"pv_daily_history": [{"datum": "2026-01-01"}]})
    assert not hasattr(c, "pv_daily_history")


def test_60_eenheden_en_co2():
    from custom_components.energy_management_system.sensor import CO2IntensitySensor
    code = (BRON / "sensor.py").read_text(encoding="utf-8")
    assert '_attr_native_unit_of_measurement = "EUR"' not in code
    assert CO2IntensitySensor._attr_state_class == "total_increasing"


# --- meldingen: negatieve prijzen en weinig zon --------------------------------


def test_negatieve_prijzen_alleen_komende_kwartieren(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 11, 4, 14, 5, tzinfo=timezone.utc)
    entries = [(nu.replace(hour=h, minute=0), None, -0.01) for h in (10, 11, 14, 15)]
    berichten = []
    c._meld_negatieve_prijzen(nu, entries, lambda k, t, b: berichten.append(b))
    assert berichten and berichten[0].startswith("Nog 2 kwartier(en)")


def test_negatieve_prijzen_een_keer_per_dag(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 11, 4, 14, 5, tzinfo=timezone.utc)
    c.notification_last_sent["negative_prices"] = (nu - timedelta(hours=3)).isoformat()
    berichten = []
    c._meld_negatieve_prijzen(nu, [(nu.replace(hour=15), None, -0.01)], lambda *a: berichten.append(a))
    assert berichten == []
    assert c._al_vandaag_gemeld("negative_prices", nu)
    assert not c._al_vandaag_gemeld("negative_prices", nu + timedelta(days=1))
