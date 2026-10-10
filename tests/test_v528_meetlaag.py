"""v5.28 - meet- en benchmarkrelease.

Uit de goedkeuring: "Geen wijziging aan de actieve productiebeslissingen."
Nieuwe modules lezen productie, wijzigen nooit actieve toestand, en een fout
in meetlog, tarief, kwartierenergie, spiegel of schaduw blokkeert de
control-loop nooit. Historische snapshots zijn onveranderlijk. Geschatte of
ontbrekende gegevens houden hun kwaliteitsstatus.
"""
import copy
import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import kwartierenergie, meetlog, schaduw, tarief
from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR
from gouden_scenarios import SCENARIOS, draai

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 1, 0, 0, tzinfo=TZ)
GOUD = json.loads((Path(__file__).parent / "fixtures" / "gouden_v5274.json").read_text())
MAP = Path(pkg.__file__).parent


# =========================================================================
# productie onveranderd
# =========================================================================

def test_de_meetlaag_verandert_geen_productiekenmerk(make_coordinator, hass):
    """De toestand van de coördinator buiten de meetlaag is voor en na de
    haak identiek. Alleen rekencaches die per ronde dezelfde uitkomst geven
    mogen erbij komen."""
    draai(make_coordinator, hass, "avondpiek_vol")
    c = draai.laatste
    toegestaan = {"_meetlaag", "_pv_vast_cache", "_pv_starts_cache", "_forecast_cache", "_kwartierplan_cache"}
    voor = {k: repr(v) for k, v in vars(c).items() if k not in toegestaan}
    c._meetlaag.invoer = (NU.replace(hour=19, minute=30), c._get_forecast_entries())
    c._meetlaag_na_besluit()
    na = {k: repr(v) for k, v in vars(c).items() if k not in toegestaan}
    assert voor == na


@pytest.mark.parametrize("module", ["meetlog.py", "tarief.py", "schaduw.py", "kwartierenergie.py", "meetlaag.py"])
def test_nieuwe_modules_sturen_nooit(module):
    bron = (MAP / module).read_text()
    for verboden in ("async_call", "select_option", "set_value", "services.", "_async_apply"):
        assert verboden not in bron, f"{module}: {verboden}"


@pytest.mark.parametrize("plek", ["spiegel", "waarde"])
def test_een_fout_in_schaduw_of_tarief_verandert_productie_niet(make_coordinator, hass, monkeypatch, plek):
    doel = schaduw if plek == "spiegel" else tarief

    def kapot(*a, **k):
        raise RuntimeError("proef")

    monkeypatch.setattr(doel, plek, kapot)
    for naam in ("avondpiek_vol", "negatieve_prijs", "nacht_03u_accu_half"):
        nu = draai(make_coordinator, hass, naam)
        assert nu == GOUD[naam]
    assert draai.laatste._meetlaag.log.fouten >= 1


def test_de_meetlaag_aanroep_zelf_kan_niet_mislukken(make_coordinator, hass, monkeypatch):
    draai(make_coordinator, hass, "avondpiek_vol")
    c = draai.laatste
    c._meetlaag.invoer = "geen tupel"         # onzin-invoer
    c._meetlaag_na_besluit()                  # mag niets gooien


# =========================================================================
# productiespiegel (tweelingtoets)
# =========================================================================

def _reeks(rng, start, n=192):
    return [(start + timedelta(minutes=15 * i), start + timedelta(minutes=15 * (i + 1)),
             round(rng.uniform(0.15, 0.55), 4) * PRICE_SCALE_FACTOR) for i in range(n)]


@pytest.mark.parametrize("zaad", range(25))
def test_spiegel_rekent_de_piekregel_exact_na(make_coordinator, hass, monkeypatch, zaad):
    """Productie's eigen _piekverkoop tegen de spiegel, op willekeurige
    prijzen, met en zonder blok - met de productieslijtage hetzelfde besluit."""
    rng = random.Random(zaad)
    c = make_coordinator({})
    monkeypatch.setattr(type(c), "get_wear_cost_overview", lambda self: {"slijtage_ct_per_kwh": 11.28})
    c.charge_efficiency_history = [round(rng.uniform(80, 95), 1)] * 7
    c.discharge_efficiency_history = [round(rng.uniform(88, 98), 1)] * 7
    entries = _reeks(rng, NU)
    nu = entries[rng.randint(0, 60)][0] + timedelta(minutes=rng.choice([0, 7]))
    blok = entries[rng.randint(61, 150)][0] if zaad % 5 else None
    c.last_cheap_block_end = blok + timedelta(hours=4) if blok else None
    productie = c._piekverkoop(nu, entries, blok, 3.0)
    if "prijs_nu_eur" not in productie:
        pytest.skip("geen piekafweging in dit scenario")
    reeks = [(b, p / PRICE_SCALE_FACTOR) for b, _e, p in entries]
    spiegel = schaduw.spiegel({
        "productie_categorie": "huis_dekken", "piek": productie, "moment": nu, "reeks": reeks,
        "blok": blok, "blokprijzen": [p for b, p in reeks if blok and blok <= b < c.last_cheap_block_end],
        "rendement_procent": c.learned_battery_efficiency_percent,
    }, 11.28)
    assert spiegel["piek"]["verkopen"] == productie["verkopen"]
    assert spiegel["piek"]["duurste_later_eur"] == productie["duurste_later_eur"]
    assert spiegel["doorgegeven"] is False


@pytest.mark.parametrize("zaad", range(25))
def test_spiegel_rekent_de_laadregel_exact_na(make_coordinator, hass, zaad):
    rng = random.Random(100 + zaad)
    c = make_coordinator({})
    prijs_nu = round(rng.uniform(0.10, 0.35), 4)
    later = sorted(((round(rng.uniform(0.25, 0.60), 4), NU + timedelta(minutes=15 * (40 + i))) for i in range(30)),
                   key=lambda x: x[0], reverse=True)
    rendement = round(rng.uniform(78, 92), 1)
    productie = c._laadregel(prijs_nu=prijs_nu, beschikbaar=rng.uniform(0.5, 3), ruimte=rng.uniform(1, 6),
                             later=later, rendement=rendement, slijtage_ct=11.28, per_kwartier=0.5,
                             zonoverschot=lambda tot: 0.0)
    if "latere_prijs_eur" not in productie:
        pytest.skip("geen laadafweging in dit scenario")
    spiegel = schaduw.spiegel({"productie_categorie": "laden" if productie["laden"] else "huis_dekken",
                               "laadbesluit": productie, "moment": NU}, 11.28)
    assert spiegel["laden"] == productie["laden"]


def test_spiegel_op_de_gouden_scenarios_gelijk_aan_productie(make_coordinator, hass, coordinator_cls, monkeypatch):
    monkeypatch.setattr(coordinator_cls, "get_wear_cost_overview", lambda self: {"slijtage_ct_per_kwh": 11.28})
    for naam in SCENARIOS:
        draai(make_coordinator, hass, naam)
        e = draai.laatste._meetlaag.laatste_evaluatie
        assert e["mirror_matches_production"] is True, naam


# =========================================================================
# economisch schaduwoptimum
# =========================================================================

def _kwartieren(nacht=0.31, avond=0.51, n=96):
    uit = []
    for i in range(n):
        uur = (i // 4) % 24
        prijs = avond if 18 <= uur < 21 else (0.25 if 11 <= uur < 16 else nacht)
        uit.append({"import": prijs, "export": prijs, "verbruik": 0.07, "zon": 0.0,
                    "verbruik_p10": 0.05, "verbruik_p90": 0.10, "zon_laag": 0.0, "zon_hoog": 0.0})
    return uit


def _opt(kw, slijtage_ct):
    return schaduw.optimaliseer(kw, emax_kwh=7.78, laad_kwh=0.5, ontlaad_kwh=0.4, rendement_procent=83.8, slijtage_ct=slijtage_ct)


def test_het_optimum_bewaart_de_nacht_voor_de_avond():
    """00:00, 2 kWh in de accu, avond 51 ct: de huidige lading is 's avonds
    meer waard dan nu - het optimum dekt het huis niet uit de accu."""
    kw = _kwartieren()
    waarden = schaduw.alternatieven(_opt(kw, 2.0), kw, 0, 2.0)
    assert schaduw.beste_twee(waarden)[0] in ("bewaren", "laden")
    assert waarden["bewaren"] > waarden["huis_dekken"]


def test_hoge_slijtage_maakt_cycli_onrendabel():
    kw = _kwartieren(nacht=0.31, avond=0.36)
    waarden = schaduw.alternatieven(_opt(kw, 30.0), kw, 0, 2.0)
    assert waarden["laden"] < waarden["bewaren"]


def test_het_optimum_trekt_de_accu_niet_leeg_om_beter_te_lijken():
    kw = _kwartieren()
    opt = _opt(kw, 2.0)
    assert opt["eindwaarde_eur"] > 0


# =========================================================================
# risicoreserve
# =========================================================================

def test_risicoreserve_is_kleiner_naarmate_verkopen_meer_oplevert():
    kw = _kwartieren()
    verdeling = schaduw.tekortverdeling(kw, 40, zaad="x")
    goedkoop = schaduw.risicoreserve(verdeling, 0.20, 83.8)["kwh"]
    duur = schaduw.risicoreserve(verdeling, 0.60, 83.8)["kwh"]
    assert duur < goedkoop


def test_risicoreserve_zelfde_snapshot_zelfde_uitkomst():
    kw = _kwartieren()
    assert schaduw.tekortverdeling(kw, 40, zaad="s") == schaduw.tekortverdeling(kw, 40, zaad="s")


def test_risicoreserve_zonder_band_is_onbekend():
    kw = [dict(k, verbruik_p10=None) for k in _kwartieren()]
    assert schaduw.risicoreserve(schaduw.tekortverdeling(kw, 40, zaad="s"), 0.4, 83.8)["kwh"] is None


# =========================================================================
# snapshots: onveranderlijk
# =========================================================================

def test_een_snapshot_is_onveranderlijk():
    log = meetlog.MeetLog()
    inhoud = {"prijzen": [0.31, 0.51], "ems_version": "5.28"}
    sid = log.leg_snapshot_vast(inhoud, NU)
    inhoud["prijzen"].append(9.99)                      # het origineel achteraf wijzigen
    kopie = log.snapshot(sid)
    kopie["inhoud"]["prijzen"].append(8.88)             # de teruggegeven kopie wijzigen
    assert log.snapshot(sid)["inhoud"]["prijzen"] == [0.31, 0.51]


def test_zelfde_id_andere_inhoud_wordt_nooit_overschreven():
    log = meetlog.MeetLog()
    sid = log.leg_snapshot_vast({"a": 1}, NU)
    regel = log._dagen[("snapshot", NU.date().isoformat())][sid]
    regel["inhoud"]["a"] = 2                            # opslag beschadigd
    with pytest.raises(meetlog.SnapshotConflict):
        log.leg_snapshot_vast({"a": 1}, NU)


def test_nieuwe_informatie_is_een_nieuw_snapshot_en_het_oude_blijft():
    log = meetlog.MeetLog()
    oud = log.leg_snapshot_vast({"pv": [1.0], "config_hash": "a", "ems_version": "5.28"}, NU)
    nieuw_pv = log.leg_snapshot_vast({"pv": [1.2], "config_hash": "a", "ems_version": "5.28"}, NU + timedelta(hours=1))
    nieuwe_config = log.leg_snapshot_vast({"pv": [1.0], "config_hash": "b", "ems_version": "5.28"}, NU + timedelta(hours=2))
    nieuwe_versie = log.leg_snapshot_vast({"pv": [1.0], "config_hash": "a", "ems_version": "5.29"}, NU + timedelta(hours=3))
    assert len({oud, nieuw_pv, nieuwe_config, nieuwe_versie}) == 4
    assert log.snapshot(oud)["inhoud"]["pv"] == [1.0]


def test_een_evaluatie_verwijst_naar_het_gebruikte_snapshot(make_coordinator, hass):
    draai(make_coordinator, hass, "avondpiek_vol")
    laag = draai.laatste._meetlaag
    e = laag.laatste_evaluatie
    assert e["snapshot_id"] is not None
    assert laag.log.snapshot(e["snapshot_id"]) is not None


def test_een_latere_voorspelling_verandert_eerdere_records_niet(make_coordinator, hass):
    draai(make_coordinator, hass, "avondpiek_vol")
    c = draai.laatste
    laag = c._meetlaag
    eerste = copy.deepcopy(laag.laatste_evaluatie)
    oud_snapshot = laag.log.snapshot(eerste["snapshot_id"])
    hass.states.set("sensor.price", "0", {"forecast": []})          # nieuwe (lege) prijsreeks
    laag.invoer = (NU.replace(hour=19, minute=45), [])
    c._meetlaag_na_besluit()
    records = laag.log.regels("evaluatie", NU.date())
    assert records[0]["snapshot_id"] == eerste["snapshot_id"]
    assert laag.log.snapshot(eerste["snapshot_id"]) == oud_snapshot


# =========================================================================
# evaluatie, besluit, actie
# =========================================================================

def test_evaluatie_zonder_en_met_actiewijziging(make_coordinator, hass):
    draai(make_coordinator, hass, "nacht_03u_accu_half")
    c = draai.laatste
    laag = c._meetlaag
    eerste = laag.laatste_evaluatie
    assert eerste["action_changed"] is False                    # geen vorige stand
    # tweede ronde, zelfde besluit
    laag.invoer = (NU.replace(hour=3, minute=5), c._get_forecast_entries())
    c._meetlaag_na_besluit()
    tweede = laag.laatste_evaluatie
    assert tweede["action_changed"] is False
    assert tweede["command_sent"] is False
    # derde ronde: productie wisselt naar verkopen
    c.last_reason, c.last_expected_mode, c.last_discharge_power_applied = "expensive_quarter", "manual", 1600
    laag.invoer = (NU.replace(hour=3, minute=10), c._get_forecast_entries())
    c._meetlaag_na_besluit()
    derde = laag.laatste_evaluatie
    assert derde["action_changed"] is True
    assert derde["previous_action"] == {"stand": "smart_discharging", "vermogen_w": None}
    assert derde["new_action"] == {"stand": "manual", "vermogen_w": 1600}


def test_een_verstuurde_opdracht_wordt_vastgelegd(make_coordinator, hass):
    draai(make_coordinator, hass, "avondpiek_vol")
    e = draai.laatste._meetlaag.laatste_evaluatie
    assert e["command_sent"] is True
    assert {"entiteit": "number.pow", "verwacht": 1600, "wat": "handmatig vermogen"} in e["commands"]


def test_compacte_records_tussen_de_kwartieren(make_coordinator, hass):
    draai(make_coordinator, hass, "nacht_03u_accu_half")
    c = draai.laatste
    laag = c._meetlaag
    laag.invoer = (NU.replace(hour=3, minute=5), c._get_forecast_entries())
    c._meetlaag_na_besluit()
    records = laag.log.regels("evaluatie", NU.date())
    assert records[0]["record"] == "volledig"
    assert records[-1]["record"] == "compact"


# =========================================================================
# kwartierenergie
# =========================================================================

GRENS = datetime(2026, 10, 1, 12, 15, tzinfo=TZ)


def _standen(waarden, vers=True, grens=GRENS):
    tijd = grens - timedelta(seconds=10 if vers else 600)
    return {k: (kwartierenergie.stand(v, tijd, grens) if v is not None else None) for k, v in waarden.items()}


BEGIN = {"grid_import": 100.0, "grid_export": 50.0, "pv": 200.0, "battery_out": 30.0, "battery_in": 40.0}


def test_een_gemeten_kwartier():
    eind = {"grid_import": 100.1, "grid_export": 50.0, "pv": 200.4, "battery_out": 30.0, "battery_in": 40.3}
    k = kwartierenergie.kwartier(GRENS, _standen(BEGIN, grens=GRENS - timedelta(minutes=15)), _standen(eind), 0.25)
    assert k["quality"] == "measured" and k["coverage_percent"] == 100.0
    assert k["house_kwh"] == pytest.approx(0.2)


def test_een_tellerreset_is_invalid_nooit_een_verkeerde_waarde():
    eind = dict(BEGIN, grid_import=0.4)
    k = kwartierenergie.kwartier(GRENS, _standen(BEGIN, grens=GRENS - timedelta(minutes=15)), _standen(eind), 0.25)
    assert k["grid_import_kwh"] is None
    assert k["kwaliteit_per_teller"]["grid_import"] == "invalid"
    assert k["house_kwh"] is None


def test_een_oude_stand_geeft_partially_estimated():
    eind = dict(BEGIN, pv=200.5)
    k = kwartierenergie.kwartier(GRENS, _standen(BEGIN, grens=GRENS - timedelta(minutes=15)), _standen(eind, vers=False), 0.25)
    assert k["quality"] == "partially_estimated"


def test_zonder_laadteller_wordt_accu_in_geschat_en_gemarkeerd():
    begin = dict(BEGIN, battery_in=None)
    eind = {"grid_import": 100.1, "grid_export": 50.0, "pv": 200.4, "battery_out": 30.0, "battery_in": None}
    k = kwartierenergie.kwartier(GRENS, _standen(begin, grens=GRENS - timedelta(minutes=15)), _standen(eind), 0.25,
                                 accu_in_geschat_kwh=0.3)
    assert k["kwaliteit_per_teller"]["battery_in"] == "estimated"
    assert k["quality"] == "estimated"
    assert k["coverage_percent"] < 100


def test_onbekende_teller_is_invalid():
    eind = dict(BEGIN, pv="unavailable")
    k = kwartierenergie.kwartier(GRENS, _standen(BEGIN, grens=GRENS - timedelta(minutes=15)), _standen(eind), 0.25)
    assert k["kwaliteit_per_teller"]["pv"] == "invalid"


def test_de_naamgenoot_van_de_ontlaadteller_wordt_gevonden(make_coordinator, hass):
    c = make_coordinator({"battery_discharge_energy_sensor_entity": "sensor.solarflow_2400_ac_aggr_discharge"})
    hass.states.set("sensor.solarflow_2400_ac_aggr_charge", "2270.07",
                    {"unit_of_measurement": "kWh", "state_class": "total_increasing"})
    from custom_components.energy_management_system.meetlaag import Meetlaag

    assert Meetlaag(c)._tellers()["battery_in"] == "sensor.solarflow_2400_ac_aggr_charge"


def test_kwartiergrens_zomer_wintertijd_en_middernacht(make_coordinator, hass):
    """25 oktober: de klok gaat van 03:00 terug naar 02:00. Kwartieren
    worden op tijdstip met tijdzone vastgelegd, dus het dubbele uur geeft
    twee verschillende kwartieren."""
    zomer = datetime(2026, 10, 25, 2, 45, tzinfo=timezone(timedelta(hours=2)))
    winter = datetime(2026, 10, 25, 2, 45, tzinfo=timezone(timedelta(hours=1)))
    assert zomer.isoformat() != winter.isoformat()
    middernacht = datetime(2026, 10, 2, 0, 0, tzinfo=TZ)
    k = kwartierenergie.kwartier(middernacht - timedelta(minutes=15),
                                 _standen(BEGIN, grens=middernacht - timedelta(minutes=15)),
                                 _standen(dict(BEGIN, grid_import=100.05), grens=middernacht), 0.3)
    assert k["kwartier"].startswith("2026-10-01T23:45")


# =========================================================================
# tarieflaag
# =========================================================================

def test_tarief_binnen_boven_en_onbekend():
    m = datetime(2026, 10, 1, 19, 30, tzinfo=TZ)
    binnen = tarief.waarde(m, 0.51, saldeerruimte_kwh=800)
    boven = tarief.waarde(m, 0.51, saldeerruimte_kwh=-5, vergoeding_boven_eur=0.07)
    boven_zonder = tarief.waarde(m, 0.51, saldeerruimte_kwh=-5)
    onbekend = tarief.waarde(m, 0.51, saldeerruimte_kwh=None)
    assert (binnen["export_eur"], binnen["kwaliteit"]) == (0.51, "ok")
    assert (boven["export_eur"], boven["regime"]) == (0.07, "boven_saldering")
    assert (boven_zonder["export_eur"], boven_zonder["kwaliteit"]) == (None, "unknown")
    assert (onbekend["export_eur"], onbekend["kwaliteit"]) == (0.51, "onzeker")


def test_tarief_vanaf_2027():
    m = datetime(2027, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=1)))
    zonder = tarief.waarde(m, 0.31, saldeerruimte_kwh=500)
    met = tarief.waarde(m, 0.31, saldeerruimte_kwh=500, marktprijs_eur=0.09, exportkosten_2027_eur=0.02)
    assert zonder["regime"] == "na_saldering" and zonder["export_eur"] is None and zonder["kwaliteit"] == "unknown"
    assert met["export_eur"] == pytest.approx(0.07)


def test_saldeerruimte_zonder_beginstand_is_onbekend():
    assert tarief.saldeerruimte(None, 1200.0) == {"kwh": None, "status": "unknown"}
    assert tarief.saldeerruimte(3000.0, 1200.0) == {"kwh": 1800.0, "status": "ok"}


# =========================================================================
# opslag en tijdsbudget
# =========================================================================

def test_bewaartermijnen():
    log = meetlog.MeetLog()
    vandaag = datetime(2026, 12, 31, tzinfo=TZ)
    for dagen_terug in (10, 31, 200, 401):
        m = vandaag - timedelta(days=dagen_terug)
        log.voeg_toe("evaluatie", m, {"x": 1})
        log.voeg_toe("kwartier", m, {"x": 1})
    log.opruimen(vandaag.date())
    over = {(s, d) for s, d in log._groottes}
    assert ("evaluatie", (vandaag - timedelta(days=10)).date().isoformat()) in over
    assert ("evaluatie", (vandaag - timedelta(days=31)).date().isoformat()) not in over
    assert ("kwartier", (vandaag - timedelta(days=200)).date().isoformat()) in over
    assert ("kwartier", (vandaag - timedelta(days=401)).date().isoformat()) not in over


def test_de_opslaglimiet_wist_eerst_oude_details_nooit_kwartieren():
    log = meetlog.MeetLog(limiet_bytes=20_000)
    vandaag = datetime(2026, 10, 20, tzinfo=TZ)
    groot = {"x": "a" * 3000}
    for d in range(10, 0, -1):
        m = vandaag - timedelta(days=d)
        log.voeg_toe("evaluatie", m, groot)
        log.voeg_toe("kwartier", m, {"k": 1})
    log.opruimen(vandaag.date())
    assert log.grootte_bytes() <= 20_000
    assert sum(1 for s, _ in log._groottes if s == "kwartier") == 10
    assert log.door_limiet_gewist and log.door_limiet_gewist[0].startswith("evaluatie")


def test_zware_berekeningen_draaien_in_de_executor(make_coordinator, hass, monkeypatch):
    gebruikt = []
    origineel = hass.async_add_executor_job

    async def spion(func, *args):
        gebruikt.append(getattr(func, "__name__", ""))
        return await origineel(func, *args)

    monkeypatch.setattr(hass, "async_add_executor_job", spion)
    draai(make_coordinator, hass, "avondpiek_vol")
    laag = draai.laatste._meetlaag
    # de schaduw is gestart; de berekening loopt via de executor
    assert laag._snapshot_id in laag._schaduw
    bron = (MAP / "meetlaag.py").read_text()
    assert "async_add_executor_job(rekenen)" in bron
    assert "schaduw.optimaliseer" in bron.split("def rekenen")[1].split("async def klaar")[0]


def test_tijdsbudget_in_de_event_loop(make_coordinator, hass):
    duren = []
    for naam in SCENARIOS:
        draai(make_coordinator, hass, naam)
        duren += draai.laatste._meetlaag.duur_ms
    duren.sort()
    assert duren[len(duren) // 2] < 20.0, duren


def test_een_fout_in_de_executorberekening_blijft_in_de_meetlaag(make_coordinator, hass, monkeypatch):
    """Het schaduwoptimum draait in de executor; een fout daar wordt geteld
    en de schaduw meldt zich onbeschikbaar - productie merkt niets."""
    import asyncio

    from custom_components.energy_management_system.meetlaag import Meetlaag

    def kapot(*a, **k):
        raise RuntimeError("proef")

    monkeypatch.setattr(schaduw, "optimaliseer", kapot)
    c = make_coordinator({})
    laag = Meetlaag(c)
    kw = _kwartieren()
    for i, k in enumerate(kw):
        k["begin"] = (NU + timedelta(minutes=15 * i)).isoformat()
    taken = []
    hass.async_create_task = lambda coro: taken.append(coro)
    laag._start_schaduw("abc", kw, {"capacity_kwh": 8.64, "min_soc": 10, "learned_efficiency": 83.8,
                                    "max_charge_kw": 2.0, "max_discharge_kw": 1.6})
    for taak in taken:
        asyncio.run(taak)
    assert laag.log.fouten == 1
    assert laag._schaduw["abc"]["beschikbaar"] is False


# =========================================================================
# gevonden bij de dagmeting
# =========================================================================

def test_kwartier_compact_opslaan_en_terug():
    eind = {"grid_import": 100.1, "grid_export": 50.0, "pv": 200.4, "battery_out": 30.0, "battery_in": 40.3}
    k = kwartierenergie.kwartier(GRENS, _standen(BEGIN, grens=GRENS - timedelta(minutes=15)), _standen(eind), 0.25)
    kort = kwartierenergie.compact(k)
    assert len(json.dumps(kort)) < 200
    terug = kwartierenergie.uitpakken(kort)
    assert {s: terug[s] for s in terug} == {s: k[s] for s in terug}


def test_een_stilstaande_teller_met_recente_melding_is_gemeten(make_coordinator, hass):
    """Teruglevering staat 's nachts stil: last_updated is oud, maar
    last_reported is vers - de waarde is exact."""
    from custom_components.energy_management_system.meetlaag import Meetlaag

    c = make_coordinator({"grid_export_energy_sensor_entity": "sensor.terug"})
    laag = Meetlaag(c)
    for grens, stand in ((GRENS - timedelta(minutes=15), "50.000"), (GRENS, "50.000")):
        hass.states.set("sensor.terug", stand, {"unit_of_measurement": "kWh"})
        toestand = hass.states.get("sensor.terug")
        toestand.last_updated = GRENS - timedelta(hours=6)
        toestand.last_reported = grens - timedelta(seconds=5)
        laag.kwartiergrens(grens)
    assert laag.laatste_kwartier["kwaliteit_per_teller"]["grid_export"] == "measured"
    assert laag.laatste_kwartier["grid_export_kwh"] == 0.0


def test_het_snapshot_blijft_gelijk_zolang_de_invoer_gelijk_blijft(make_coordinator, hass):
    """De hele prijshorizon, niet 'vanaf nu': een latere ronde op dezelfde dag
    met dezelfde invoer geeft hetzelfde snapshot."""
    draai(make_coordinator, hass, "nacht_03u_accu_half")
    c = draai.laatste
    laag = c._meetlaag
    eerste = laag._snapshot_id
    laag.invoer = (NU.replace(hour=3, minute=40), c._get_forecast_entries())
    c._meetlaag_na_besluit()
    assert laag._snapshot_id == eerste


def test_de_risicoreserve_van_het_volgende_kwartier_wordt_vooruit_gerekend(make_coordinator, hass):
    from custom_components.energy_management_system.meetlaag import Meetlaag

    c = make_coordinator({})
    laag = Meetlaag(c)
    kw = _kwartieren()
    for i, k in enumerate(kw):
        k["begin"] = (NU + timedelta(minutes=15 * i)).isoformat()
    laag._snapshot_id, laag._kwartieren = "s", kw
    hass.async_create_task = lambda coro: coro.close()
    laag._risico(NU + timedelta(minutes=2), 0.31)
    assert ("s", 0) in laag._risico_cache and ("s", 1) in laag._risico_cache


# =========================================================================
# v5.28.1 - gevonden in de eerste echte export (2 oktober 09:15)
# =========================================================================

def test_een_teller_in_wh_wordt_naar_kwh_omgezet():
    """De SolarEdge-teller meldt in Wh: 57 Wh in een kwartier las als 57 kWh."""
    begin = {"pv": kwartierenergie.stand("107", GRENS - timedelta(minutes=15, seconds=5), GRENS - timedelta(minutes=15), "Wh")}
    eind = {"pv": kwartierenergie.stand("164", GRENS - timedelta(seconds=5), GRENS, "Wh")}
    k = kwartierenergie.kwartier(GRENS - timedelta(minutes=15), begin, eind, 0.44)
    assert k["pv_kwh"] == pytest.approx(0.057)


def test_een_onbekende_eenheid_is_geen_meting():
    assert kwartierenergie.stand("12", GRENS, GRENS, "kWh/h")["waarde"] is None


def test_de_dagelijkse_reset_van_de_solaredge_teller_is_invalid():
    begin = {"pv": kwartierenergie.stand("6400", GRENS - timedelta(minutes=15), GRENS - timedelta(minutes=15), "Wh")}
    eind = {"pv": kwartierenergie.stand("0", GRENS, GRENS, "Wh")}
    k = kwartierenergie.kwartier(GRENS - timedelta(minutes=15), begin, eind, 0.30)
    assert k["pv_kwh"] is None and k["kwaliteit_per_teller"]["pv"] == "invalid"


def test_een_melding_net_na_de_grens_is_ook_vers():
    s = kwartierenergie.stand("10", GRENS + timedelta(seconds=8), GRENS)
    assert s["vers"] is True and s["leeftijd_s"] == -8


def test_de_leeftijd_per_teller_wordt_bewaard():
    eind = dict(BEGIN, pv=200.4)
    k = kwartierenergie.kwartier(GRENS, _standen(BEGIN, grens=GRENS - timedelta(minutes=15)), _standen(eind, vers=False), 0.25)
    assert k["leeftijd_s"]["pv"] == 600
    assert kwartierenergie.uitpakken(kwartierenergie.compact(k))["leeftijd_s"]["pv"] == 600


def test_de_kwartiertimer_draait_op_de_event_loop():
    bron = (MAP / "coordinator.py").read_text()
    assert "    @callback\n    def _meetlaag_kwartier(" in bron


def test_de_bron_van_accu_in_wordt_niet_afgekapt(make_coordinator, hass):
    from custom_components.energy_management_system.meetlaag import Meetlaag

    c = make_coordinator({"battery_discharge_energy_sensor_entity": "sensor.solarflow_2400_ac_aggr_discharge"})
    laag = Meetlaag(c)
    for grens, waarde in ((GRENS - timedelta(minutes=15), "2270.000"), (GRENS, "2270.050")):
        hass.states.set("sensor.solarflow_2400_ac_aggr_charge", waarde,
                        {"unit_of_measurement": "kWh", "state_class": "total_increasing"})
        hass.states.get("sensor.solarflow_2400_ac_aggr_charge").last_reported = grens
        laag.kwartiergrens(grens)
    opgeslagen = laag.log.regels("kwartier", GRENS.date())[-1]
    assert opgeslagen["bron"] == "n"            # naamgenoot van de ontlaadteller


# =========================================================================
# v5.28.2 - terugladen na een herstart
# =========================================================================

class _Opslag:
    """Nep-opslag die bijhoudt wat er geladen en bewaard wordt."""
    bestanden: dict = {}
    log: list = []

    def __init__(self, sleutel):
        self.sleutel = sleutel

    async def async_load(self):
        _Opslag.log.append(("laden", self.sleutel))
        return copy.deepcopy(_Opslag.bestanden.get(self.sleutel))

    async def async_save(self, inhoud):
        _Opslag.log.append(("bewaren", self.sleutel))
        _Opslag.bestanden[self.sleutel] = copy.deepcopy(inhoud)

    async def async_remove(self):
        _Opslag.bestanden.pop(self.sleutel, None)


def test_terugladen_voegt_samen_in_plaats_van_te_vervangen():
    log = meetlog.MeetLog()
    log.voeg_toe("evaluatie", NU + timedelta(hours=2), {"t": "na de herstart"})
    log.laad_dag("evaluatie", NU.date().isoformat(), {"regels": [{"t": "08:40"}, {"t": "09:15"}]})
    regels = [r["t"] for r in log.regels("evaluatie", NU.date())]
    assert regels == ["08:40", "09:15", "na de herstart"]
    log.laad_dag("evaluatie", NU.date().isoformat(), {"regels": [{"t": "08:40"}, {"t": "09:15"}]})
    assert len(log.regels("evaluatie", NU.date())) == 3      # geen dubbele


def test_niets_wegschrijven_voordat_het_terugladen_klaar_is(make_coordinator, hass):
    """De oorzaak van '3 evaluaties': het eerste wegschrijven na de herstart
    kon het terugladen inhalen en het bestand van vandaag overschrijven."""
    import asyncio

    from custom_components.energy_management_system.meetlaag import Meetlaag

    sleutel = meetlog.MeetLog.opslagsleutel("evaluatie", NU.date().isoformat())
    _Opslag.bestanden = {sleutel: {"regels": [{"evaluation_timestamp": f"oud {i}"} for i in range(23)]}}
    _Opslag.log = []
    c = make_coordinator({})
    laag = Meetlaag(c, opslag_factory=_Opslag)
    taken = []
    hass.async_create_task = lambda coro: taken.append(coro)
    laag._start_laden(NU)
    laag.log.voeg_toe("evaluatie", NU, {"evaluation_timestamp": "nieuw"})
    laag._bewaar_af_en_toe()                                 # terugladen loopt nog
    assert not any(soort == "bewaren" for soort, _ in _Opslag.log)
    for taak in taken:
        asyncio.run(taak)
    taken.clear()
    laag._bewaar_af_en_toe()
    for taak in taken:
        asyncio.run(taak)
    assert len(_Opslag.bestanden[sleutel]["regels"]) == 24   # 23 bewaarde + 1 nieuwe


def test_terugladen_op_de_datum_van_de_ronde(make_coordinator, hass):
    import asyncio

    from custom_components.energy_management_system.meetlaag import Meetlaag

    _Opslag.bestanden, _Opslag.log = {}, []
    laag = Meetlaag(make_coordinator({}), opslag_factory=_Opslag)
    taken = []
    hass.async_create_task = lambda coro: taken.append(coro)
    laag._start_laden(datetime(2026, 10, 2, 0, 30, tzinfo=TZ))
    for taak in taken:
        asyncio.run(taak)
    assert ("laden", "energy_management_system_meetlog_evaluatie_20261002") in _Opslag.log


def test_kwartieren_van_v528_tellen_als_ongeldig_en_niet_mee():
    oud = {"t": "2026-10-02T09:00:00+02:00", "i": 0.006, "e": 0.017, "p": 57.0, "o": 0.0, "c": 0.009,
           "h": 56.98, "pr": 0.4456, "q": "mmppp", "cov": 0.0}
    terug = kwartierenergie.uitpakken(oud)
    assert terug["quality"] == "invalid" and terug["pv_kwh"] is None
    assert oud["p"] == 57.0                                   # het record zelf blijft ongewijzigd


def test_de_dekking_in_de_status_slaat_v528_kwartieren_over(make_coordinator, hass):
    from custom_components.energy_management_system.meetlaag import Meetlaag

    laag = Meetlaag(make_coordinator({}))
    laag._dag = NU.date()
    laag.log.voeg_toe("kwartier", NU, {"t": "x", "i": 0.0, "e": 0.0, "p": 57.0, "o": 0.0, "c": 0.0,
                                         "h": 57.0, "pr": 0.4, "q": "mmppp", "cov": 0.0})
    laag.log.voeg_toe("kwartier", NU, {"t": "y", "i": 0.1, "e": 0.0, "p": 0.0, "o": 0.0, "c": 0.0,
                                         "h": 0.1, "pr": 0.4, "q": "mmmmm", "cov": 100.0, "a": [5, 5, 5, 5, 5]})
    assert "dekking 100%" in laag.status_tekst()


# =========================================================================
# v5.28.3 - accu op een eigen groep: 2400 W
# =========================================================================

def test_nu_laden_volgt_het_ingestelde_laadvermogen(make_coordinator, hass):
    """'Nu laden' had een eigen vaste 2000 W; nu volgt hij de instelling."""
    assert make_coordinator({"manual_charge_power": -2400}).handmatig_laadvermogen_w() == 2400.0
    assert make_coordinator({}).handmatig_laadvermogen_w() == 2000.0          # terugval


def test_het_dagrapport_rekent_met_de_ingestelde_grenzen():
    from custom_components.energy_management_system.meetlaag import schaduw_dagrapport

    ev = [{"evaluation_timestamp": "2026-10-02T19:00:00+02:00", "production_action": {"categorie": "huis_dekken"},
           "economic_per_slijtage": {ct: "verkopen" for ct in schaduw.SLIJTAGEVARIANTEN_CT},
           "measurements": {"beschikbaar_kwh": 5.0}}]
    kw = [{"kwartier": "2026-10-02T19:00:00+02:00", "house_kwh": 0.1, "pv_kwh": 0.0, "prijs_eur": 0.5, "coverage_percent": 100}]
    langzaam = schaduw_dagrapport(ev, kw, 7.78, 83.8, laad_kwh=0.5, ontlaad_kwh=0.4)
    snel = schaduw_dagrapport(ev, kw, 7.78, 83.8, laad_kwh=0.6, ontlaad_kwh=0.6)
    assert snel["varianten"][11.28]["doorzet_kwh"] > langzaam["varianten"][11.28]["doorzet_kwh"]


# =========================================================================
# v5.28.4 - het huis gaat voor
# =========================================================================

def test_onder_de_reserve_wordt_nooit_verkocht(make_coordinator, hass):
    """3 oktober: 19:45-22:00 'expensive_quarter_peak' onder de reserve tot 25%;
    vannacht en vanochtend 2,9 kWh van het net."""
    c = make_coordinator({})
    c.last_reserve_margin_breakdown = {"bodem_kwh": 1.30}
    reeks = [(NU + timedelta(minutes=15 * i), NU + timedelta(minutes=15 * (i + 1)),
              (0.413 if i == 0 else 0.35) * PRICE_SCALE_FACTOR) for i in range(60)]
    assert c._geen_ruimte_boven_reserve(NU, reeks, NU + timedelta(hours=14), 4.3, 5.8, 2400.0, 0.25) is None


def test_het_plan_verkoopt_alleen_boven_de_reserve():
    bron = (MAP / "coordinator.py").read_text()
    # v5.70: boven de VERKOOPreserve - het deel tot het blok blijft beschermd,
    # zie test_v570_verkoopreserve.py.
    assert (
        "uit = min(soc - self._planning_verkoopreserve_kwh(start, reserve_cache, "
        "entries, prijs), duur_kwh)" in bron
    )
    assert 'prijs > netregels["duurste_tot_blok"]' not in bron
