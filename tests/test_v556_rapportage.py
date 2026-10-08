"""v5.56: rapportage - alleen weergave, uitleg en diagnose; de sturing niet.

1. Proefstand-slijtage: opnieuw uit doorzet x marginale slijtage per kWh,
   uitschieters (meer dan 2x de accucapaciteit op een dag) tellen niet mee.
2. Uitleg en spaarplan: eerst wat er tot het goedkope blok nodig is, daarna
   apart wat er na het blok nodig is (dezelfde blokgrens als Monte Carlo
   sinds v5.47, L-EMS-006).
3. Zendure lokaal meelezen: snelle vermogensvelden alleen vergelijken als ze
   aan beide kanten minstens 5 s stabiel zijn.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import zendure_lokaal as zl
from custom_components.energy_management_system.const import (
    CONF_BATTERY_MODULE_TEMPERATURE_SENSORS,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_MIN_SOC_PERCENT,
    PRICE_SCALE_FACTOR,
    PROEFSTAND_SLIJTAGE_UITSCHIETER_FACTOR,
)

NU = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


# --- 1. proefstand-slijtage ---------------------------------------------------


def _proefstand(make_coordinator, hass):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator(
        {
            CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.cap",
            CONF_MIN_SOC_PERCENT: 10.0,
            CONF_BATTERY_MODULE_TEMPERATURE_SENSORS: ["sensor.m1", "sensor.m2", "sensor.m3"],
        }
    )
    hass.states.set("sensor.cap", "8.6")
    return c


def test_slijtage_rekent_marginaal_uit_de_doorzet(make_coordinator, hass):
    """Oude boekingen met een hoger tarief tellen niet: doorzet x marginaal."""
    c = _proefstand(make_coordinator, hass)
    ct = c.get_wear_cost_overview()["slijtage_ct_per_kwh"]
    assert 4.1 <= ct <= 4.3
    # Boekingen met het oude kalendertarief (11,2 ct) en een gemiste beginstand.
    c.proefstand_ledger = [
        {"datum": "2026-10-01", "slijtage_eur": -0.672, "doorzet_kwh": 6.0},
        {"datum": "2026-10-02", "slijtage_eur": -0.448, "doorzet_kwh": 4.0},
        {"datum": "2026-10-03", "slijtage_eur": -56.0, "doorzet_kwh": 500.0},
    ]

    uit = c._opbrengst_slijtage()

    assert uit["te_becijferen"] is True
    assert uit["dagen"] == 2
    assert uit["dagen_uitgesloten"] == 1
    assert uit["doorzet_kwh"] == 10.0
    assert uit["totaal_eur"] == pytest.approx(-10.0 * ct / 100, abs=0.01)
    assert uit["bedrag_per_dag_eur"] == pytest.approx(-5.0 * ct / 100, abs=0.001)
    assert uit["bedrag_per_jaar_eur"] == pytest.approx(-5.0 * ct / 100 * 365, abs=0.05)
    assert uit["uitschietergrens_kwh_per_dag"] == pytest.approx(
        8.6 * PROEFSTAND_SLIJTAGE_UITSCHIETER_FACTOR
    )
    assert uit["uitgesloten_uitschieters"] == [{"datum": "2026-10-03", "doorzet_kwh": 500.0}]
    assert "niet meegeteld" in uit["toelichting"]


def test_slijtage_hangt_niet_af_van_het_opgeslagen_bedrag(make_coordinator, hass):
    c = _proefstand(make_coordinator, hass)
    c.proefstand_ledger = [{"datum": "2026-10-01", "slijtage_eur": -0.25, "doorzet_kwh": 6.0}]
    eerst = c._opbrengst_slijtage()
    c.proefstand_ledger = [{"datum": "2026-10-01", "slijtage_eur": -99.0, "doorzet_kwh": 6.0}]
    assert c._opbrengst_slijtage()["totaal_eur"] == eerst["totaal_eur"]


def test_boeking_zonder_doorzet_telt_niet(make_coordinator, hass):
    c = _proefstand(make_coordinator, hass)
    c.proefstand_ledger = [
        {"datum": "2026-10-01", "slijtage_eur": -12.0},
        {"datum": "2026-10-02", "slijtage_eur": -0.2, "doorzet_kwh": 5.0},
    ]
    uit = c._opbrengst_slijtage()
    assert uit["dagen"] == 1
    assert uit["uitgesloten_zonder_doorzet"] == 1
    assert uit["dagen_uitgesloten"] == 1


def test_alleen_uitschieters_is_niet_te_becijferen(make_coordinator, hass):
    c = _proefstand(make_coordinator, hass)
    c.proefstand_ledger = [{"datum": "2026-10-01", "slijtage_eur": -50.0, "doorzet_kwh": 400.0}]
    uit = c._opbrengst_slijtage()
    assert uit["te_becijferen"] is False
    assert uit["dagen_uitgesloten"] == 1


def test_geen_boeking_blijft_de_oude_reden(make_coordinator, hass):
    c = _proefstand(make_coordinator, hass)
    c.proefstand_ledger = [{"datum": "2026-10-01", "dagtype_eur": 0.1, "dagtype_kwh": 0.5}]
    uit = c._opbrengst_slijtage()
    assert uit["te_becijferen"] is False
    assert "middernacht" in uit["reden"]


def test_de_kandidaat_draagt_het_nieuwe_bedrag(make_coordinator, hass):
    c = _proefstand(make_coordinator, hass)
    c.proefstand_ledger = [{"datum": "2026-10-01", "slijtage_eur": -9.0, "doorzet_kwh": 6.0}]
    opbrengst = c.get_proefstand()["kandidaten"][0]["zou_hebben_opgeleverd"]
    assert opbrengst["grondslag"].startswith("doorzet x marginale")
    assert opbrengst["bedrag_per_dag_eur"] > -0.3


# --- 2. uitleg en spaarplan: tot het blok / na het blok -----------------------


def _met_blok(make_coordinator, nodig=8.85, na=7.0):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.last_cheap_block_start = NU + timedelta(hours=10)
    c.last_reserve_margin_breakdown = {
        "needed_kwh_before_margin": nodig,
        "lange_horizon_extra_kwh": na,
        "total_percent": 20.0,
        "reserve_kwh_after_margin": 8.64,
    }
    return c


def test_de_zin_splitst_tot_en_na_het_blok(make_coordinator, hass):
    c = _met_blok(make_coordinator)
    zin = c._tot_en_na_blok_zin()
    assert "tot het goedkope blok is 1.85 kWh nodig" in zin
    assert "na het blok nog 7.00 kWh" in zin
    assert c._tot_en_na_blok_velden() == {"nodig_tot_blok_kwh": 1.85, "nodig_na_blok_kwh": 7.0}


def test_zonder_lange_horizon_of_blok_geen_zin(make_coordinator, hass):
    c = _met_blok(make_coordinator, nodig=2.0, na=0.0)
    assert c._tot_en_na_blok_zin() == ""
    c = _met_blok(make_coordinator)
    c.last_cheap_block_start = NU - timedelta(minutes=5)
    assert c._tot_en_na_blok_zin() == ""
    assert c._tot_en_na_blok_velden()["nodig_tot_blok_kwh"] is None


def test_de_uitlegtabel_noemt_eerst_tot_het_blok(make_coordinator, hass):
    c = _met_blok(make_coordinator)
    c.last_needed_kwh_breakdown = {
        "basisverbruik_kwh": 3.1,
        "verwachte_pv_kwh": 1.0,
        "diepste_tekort_kwh": 8.85,
        "veiligheidsmarge_procent": 20.0,
        **c._diepste_tekort_gesplitst(c.last_reserve_margin_breakdown, 8.85),
    }
    c.last_needed_kwh_breakdown_end_time = NU + timedelta(hours=10)
    tabel = c._build_needed_kwh_breakdown_table()
    tot = tabel.index("Diepste tekort tot het blok (telt nu) | 1.85 kWh")
    na = tabel.index("Na het blok nog nodig")
    assert tot < na
    assert "| 7.0 kWh |" in tabel
    assert "Samen, waar de reserve op rust | 8.85 kWh" in tabel


def test_zonder_splitsing_blijft_de_oude_regel(make_coordinator, hass):
    c = _met_blok(make_coordinator)
    c.last_needed_kwh_breakdown = {"diepste_tekort_kwh": 1.2, "veiligheidsmarge_procent": None}
    tabel = c._build_needed_kwh_breakdown_table()
    assert "Diepste tekort onderweg | 1.2 kWh" in tabel


def test_reservemarge_draagt_de_splitsing(make_coordinator, hass):
    c = _met_blok(make_coordinator)
    m = c.get_reserve_margin_overview()
    assert m["diepste_tekort_kwh"] == 8.85
    assert m["diepste_tekort_tot_blok_kwh"] == pytest.approx(1.85)
    assert m["diepste_tekort_na_blok_kwh"] == pytest.approx(7.0)


def test_de_uitleg_zegt_eerst_tot_het_blok(make_coordinator, hass):
    c = _met_blok(make_coordinator)
    c.last_reason = "discharging_window"
    c.last_has_enough_energy = True
    c.last_available_kwh = 9.0
    c.last_needed_kwh_to_bridge = 8.64
    tekst = c._build_explanation()
    assert "geschat nodig: 8.64 kWh" in tekst
    assert "tot het goedkope blok is 1.85 kWh nodig - dat telt nu" in tekst


TZ = timezone(timedelta(hours=2))
AVOND = datetime(2026, 9, 29, 20, 0, tzinfo=TZ)
BLOK = datetime(2026, 9, 30, 11, 45, tzinfo=TZ)


def _reeks():
    def prijs(m):
        if 20 <= m.hour < 21 or 7 <= m.hour < 9:
            return 0.44
        if 21 <= m.hour or m.hour < 7:
            return 0.25 if 1 <= m.hour < 5 else 0.29
        # na het blok: duurder dan bijladen in het blok, telt dus mee
        return 0.20 if m >= BLOK + timedelta(hours=2) else 0.30
    uit, m = [], AVOND
    while m < AVOND + timedelta(hours=24):
        uit.append((m, m + timedelta(minutes=15), prijs(m) * PRICE_SCALE_FACTOR))
        m += timedelta(minutes=15)
    return uit


def _spaar(make_coordinator, beschikbaar):
    c = make_coordinator({})
    c.smart_charging_supported = lambda: True
    c.beschikbare_energie_kwh = lambda: beschikbaar

    def segmenten(begin, eind, veilig=True):
        uren = (eind - begin).total_seconds() / 3600
        return [(0.3 * uren, 0.0)]

    c._segmenten_verbruik_zon = segmenten
    return c


def test_spaarplan_splitst_zonder_de_som_te_veranderen(make_coordinator, hass):
    c = _spaar(make_coordinator, 3.0)
    plan = c.spaarplan(AVOND, _reeks(), BLOK)
    assert plan["nodig_tot_blok_kwh"] + plan["nodig_na_blok_kwh"] == pytest.approx(
        plan["nodig_kwh"], abs=0.02
    )
    kwartieren = c._spaarkwartieren(AVOND, _reeks(), BLOK)
    # nodig_kwh rekent nog precies zoals voorheen
    assert plan["nodig_kwh"] == round(sum(k[3] for k in kwartieren), 2)
    assert plan["nodig_tot_blok_kwh"] == round(
        sum(k[3] for k in kwartieren if k[0] < BLOK), 2
    )


def test_spaarplan_tekst_eerst_tot_het_blok():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )
    getal = lambda w: f"{w:.1f}".replace(".", ",")  # noqa: E731
    plan = {"nodig_kwh": 4.5, "nodig_tot_blok_kwh": 3.0, "nodig_na_blok_kwh": 1.5}
    tekst = C._spaarplan_nodig_tekst(plan, getal)
    assert tekst == "3,0 kWh nodig tot het goedkope blok, na het blok nog 1,5 kWh (samen 4,5)"
    assert C._spaarplan_nodig_tekst({"nodig_kwh": 4.5}, getal) == "4,5 kWh nodig tot het goedkope blok"


def test_melding_haalt_het_blok_wel_maar_niet_erna(make_coordinator, hass):
    c = make_coordinator({})
    verstuurd = []
    c._dispatch_notification = lambda *a, **k: verstuurd.append(a)
    c._meld_spaarplan({
        "actief": True, "blok": BLOK.isoformat(), "beschikbaar_kwh": 3.0,
        "nodig_kwh": 4.5, "nodig_tot_blok_kwh": 2.5, "nodig_na_blok_kwh": 2.0,
        "grensprijs_eur": 0.3, "gedekt": ["20:00-21:00"],
    })
    tekst = verstuurd[0][2]
    assert "haalt het goedkope blok van 11:45 wel, maar niet de dure kwartieren erna" in tekst
    assert "2,5 kWh nodig tot het goedkope blok, na het blok nog 2,0 kWh" in tekst


# --- 3. zendure lokaal: alleen stabiele vermogensvelden ------------------------


def _lokaal(vermogen, soc=84.0):
    return {"apparaat": {"outputPackPower": vermogen, "electricLevel": soc, "inputLimit": 1745.0},
            "modules": {"SN1": {"power": vermogen / 3, "socLevel": soc}}}


def _ha(vermogen, soc="84"):
    w = {(None, "outputPackPower"): str(vermogen), (None, "electricLevel"): soc,
         (None, "inputLimit"): "1745", ("SN1", "power"): str(vermogen / 3), ("SN1", "socLevel"): soc}
    return lambda sn, veld: w.get((sn, veld))


def test_snelle_velden_herkend():
    assert zl.snel_veld("outputPackPower") and zl.snel_veld("SN1.power") and zl.snel_veld("SN1.batcur")
    assert not zl.snel_veld("electricLevel") and not zl.snel_veld("inputLimit")
    assert not zl.snel_veld("SN1.socLevel") and not zl.snel_veld("minSoc")


def test_vermogen_pas_vergeleken_na_vijf_seconden_stabiel():
    stab = {"lokaal": {}, "zendure": {}}
    eerste = {r["sleutel"]: r for r in zl.vergelijk(_lokaal(1745.0), _ha(1200), stab, 0.0)}
    # snel en nog niet stabiel: niet vergelijkbaar, ook al wijkt het af
    assert eerste["outputPackPower"]["vergelijkbaar"] is False
    assert eerste["outputPackPower"]["gelijk"] is None
    assert eerste["SN1.power"]["vergelijkbaar"] is False
    # langzame velden gewoon vergeleken
    assert eerste["electricLevel"]["gelijk"] is True and "vergelijkbaar" not in eerste["electricLevel"]
    assert eerste["inputLimit"]["gelijk"] is True
    zl.vergelijk(_lokaal(1745.0), _ha(1745), stab, 2.0)
    zl.vergelijk(_lokaal(1750.0), _ha(1745), stab, 4.0)
    na_6s = {r["sleutel"]: r for r in zl.vergelijk(_lokaal(1748.0), _ha(1745), stab, 6.0)}
    # Zendure sprong op t=2 naar 1745: pas op t=7 vijf seconden stabiel
    assert na_6s["outputPackPower"]["vergelijkbaar"] is False
    na_8s = {r["sleutel"]: r for r in zl.vergelijk(_lokaal(1748.0), _ha(1745), stab, 8.0)}
    assert "vergelijkbaar" not in na_8s["outputPackPower"]
    assert na_8s["outputPackPower"]["gelijk"] is True


def test_stabiel_maar_verschillend_is_echt_ongelijk():
    stab = {"lokaal": {}, "zendure": {}}
    for t in (0.0, 2.0, 4.0, 6.0):
        regels = {r["sleutel"]: r for r in zl.vergelijk(_lokaal(1745.0), _ha(1200), stab, t)}
    assert regels["outputPackPower"]["gelijk"] is False


def test_een_sprong_begint_het_stabiele_stuk_opnieuw():
    volg = {}
    assert zl.stabiel_sinds(volg, "outputPackPower", 1000.0, 0.0) == 0.0
    assert zl.stabiel_sinds(volg, "outputPackPower", 1010.0, 6.0) == 6.0
    assert zl.stabiel_sinds(volg, "outputPackPower", 1500.0, 8.0) == 0.0
    assert zl.stabiel_sinds(volg, "outputPackPower", 1500.0, 12.0) == 4.0


def test_niet_vergelijkbaar_telt_niet_als_afwijking():
    t = zl.lege_tellingen()
    regels = [
        {"sleutel": "outputPackPower", "lokaal": 1745.0, "zendure": 0.0, "verschil": 1745.0,
         "gelijk": None, "vergelijkbaar": False},
        {"sleutel": "electricLevel", "lokaal": 84.0, "zendure": 84.0, "verschil": 0.0, "gelijk": True},
    ]
    for i in range(zl.MIN_VERGELIJKINGEN + 5):
        zl.verwerk_ronde(t, regels, float(i), 10.0)
    assert t["velden"]["outputPackPower"]["n"] == 0
    assert t["velden"]["outputPackPower"]["niet_vergelijkbaar"] == zl.MIN_VERGELIJKINGEN + 5
    assert zl.oordeel(t) == "gelijk"
    s = zl.samenvatting(t, "host")
    assert s["niet_vergelijkbaar"] == zl.MIN_VERGELIJKINGEN + 5
    assert s["overeenkomst_totaal_procent"] == 100.0
    assert s["per_veld"]["outputPackPower"]["overeenkomst_procent"] is None
    assert "niet vergelijkbaar" in zl.tekst("gelijk", s)


def test_oude_vermogenstellingen_beginnen_een_keer_opnieuw():
    oud = {**zl.lege_tellingen(), "velden": {
        "outputPackPower": {"n": 100, "gelijk": 40},
        "SN1.power": {"n": 100, "gelijk": 40},
        "electricLevel": {"n": 100, "gelijk": 100},
    }, "relais": {"totaal": 7}}
    oud.pop("stabiel_vergelijk")
    uit = zl.herstel(oud)
    assert set(uit["velden"]) == {"electricLevel"}
    assert uit["relais"] == {"totaal": 7}
    assert uit["stabiel_vergelijk"] is True
    # daarna blijft het staan
    uit["velden"]["outputPackPower"] = {"n": 3, "gelijk": 3}
    assert "outputPackPower" in zl.herstel(uit)["velden"]


def test_meelezer_geeft_de_stabiliteit_door():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "zendure_lokaal.py").read_text()
    assert "vergelijk(lokaal, self._zoek_toestand, self._stabiliteit, nu)" in bron
    m = zl.ZendureLokaalMeelezer(object())
    assert m._stabiliteit == {"lokaal": {}, "zendure": {}}
