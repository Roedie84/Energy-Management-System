"""v5.253.0: op werkdagen 's ochtends warm op een ingesteld tijdstip.

Ruud 24-11: "Ik wil graag dat het smorgens tussen 7 en 8 door de week ook
behaaglijk is" en "het energieverbruik van mijn woning wordt daardoor
natuurlijk anders". Uit jullie eigen bediening leerde het EMS dat niet: op
1 van de 20 werkdagochtenden ging de airco aan.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.energy_management_system import airco_ritme as R

TZ = timezone(timedelta(hours=1))
DI = datetime(2026, 11, 24, tzinfo=TZ)          # dinsdag
ZA = datetime(2026, 11, 28, tzinfo=TZ)          # zaterdag
MAP = Path(R.__file__).parent


def _ritme(vast=True):
    r = R.leeg()
    if vast:
        r["vast_ochtend"] = {"werkdag": {"warm_om": 7 * 60, "doel_c": 21.0}}
    return r


def _vraag(r, nu, stand="off", aanwezigheid="slaapt", woonkamer=16.5, advies="airco", tempo=3.0):
    return R.besluit(r, nu=nu, woonkamer_c=woonkamer, verwacht_bij_warm_om=lambda m: woonkamer,
                     tempo_c_per_uur=tempo, aanwezigheid=aanwezigheid, advies=advies, airco_stand=stand)


def test_de_instelling_gaat_voor_wat_geleerd_is():
    leer = R.geleerd(_ritme(), "werkdag")
    assert (leer["warm_om"], leer["ochtend_doel_c"], leer["kans"], leer["vast"]) == (420, 21.0, 1.0, True)
    assert R.geleerd(_ritme(), "weekend")["warm_om"] is None
    assert R.geleerd(_ritme(vast=False), "werkdag")["warm_om"] is None


def test_op_tijd_beginnen_zodat_het_om_zeven_uur_warm_is():
    r = _ritme()
    # 4,5 graad tekort bij 3 graden per uur = 1,5 uur, maar een ingestelde
    # ochtend begint hooguit een uur vooraf (v5.254.0): vanaf 06:00
    assert _vraag(r, DI.replace(hour=5, minute=45)) is None
    v = _vraag(r, DI.replace(hour=6, minute=0))
    assert v["actie"] == "verwarmen" and v["doel_c"] == 21.0
    assert "ingesteld" in v["reden"] and "07:00" in v["tekst"]


def test_ook_als_de_aanwezigheid_weg_zegt_mits_er_vannacht_iemand_was():
    r = _ritme()
    # het huis was de hele nacht leeg: niet verwarmen (v5.254.0)
    assert _vraag(r, DI.replace(hour=6, minute=30), aanwezigheid="weg") is None
    # om 05:00 sliep er iemand; Ruud vertrekt en de stand wordt 'weg'
    R.noteer_ochtend_thuis(r, DI.replace(hour=5, minute=0))
    assert _vraag(r, DI.replace(hour=6, minute=30), aanwezigheid="weg")["actie"] == "verwarmen"
    # zonder instelling blijft 'weg' niets doen, ook met een geleerd ritme
    r = _ritme(vast=False)
    for d in range(1, 6):
        dag = (DI - timedelta(days=7 * d)).date().isoformat()
        r["aan"]["werkdag"][dag] = {"minuut": 420, "doel": 21.0}
        r["ochtenden"]["werkdag"].append(dag)
    assert _vraag(r, DI.replace(hour=6, minute=30), aanwezigheid="weg") is None
    assert _vraag(r, DI.replace(hour=6, minute=30), aanwezigheid="slaapt")["actie"] == "verwarmen"


def test_vasthouden_tot_acht_uur_en_daarna_los():
    r = _ritme()
    R.noteer_ems_aan(r, DI.replace(hour=5, minute=30))
    v = _vraag(r, DI.replace(hour=7, minute=45), stand="heat", woonkamer=21.0)
    assert v["houd_aan"] is True
    assert _vraag(r, DI.replace(hour=8, minute=0), stand="heat", woonkamer=21.0) is None


def test_niet_in_het_weekend_niet_als_gas_goedkoper_is_niet_als_het_al_warm_is():
    assert _vraag(_ritme(), ZA.replace(hour=6, minute=30)) is None
    assert _vraag(_ritme(), DI.replace(hour=6, minute=30), advies="cv") is None
    assert _vraag(_ritme(), DI.replace(hour=6, minute=30), woonkamer=21.0) is None


def test_het_verbruik_van_de_ochtend_zit_in_de_verwachting():
    r = _ritme()
    r["vermogens"] = [1.3] * 5
    kwh = R.ochtend_kwh(r, DI.replace(hour=0), DI.replace(hour=12), lambda t: 16.5, 3.0)
    vermogen = R.verwarmvermogen_kw(r)
    assert vermogen and kwh > vermogen * 1.2           # een uur opwarmen + een uur vasthouden
    assert R.ochtend_kwh(_ritme(vast=False) | {"vermogens": [1.3] * 5}, DI.replace(hour=0),
                         DI.replace(hour=12), lambda t: 16.5, 3.0) == 0.0


def test_de_coordinator_zet_de_instelling_in_het_ritme(make_coordinator, hass):
    c = make_coordinator({"airco_werkdag_warm_om": "07:00"})
    assert c._airco_ritme()["vast_ochtend"] == {"werkdag": {"warm_om": 420, "doel_c": 21.0}}
    c.vacation_mode = True
    assert c._airco_ritme()["vast_ochtend"] == {}
    assert make_coordinator({})._airco_ritme()["vast_ochtend"] == {}
    assert make_coordinator({"airco_werkdag_warm_om": "22:00"})._airco_ritme()["vast_ochtend"] == {}


def test_het_veld_staat_in_de_instellingen_en_de_vertalingen():
    assert "CONF_AIRCO_WERKDAG_WARM_OM" in (MAP / "config_flow.py").read_text()
    for bestand in ("strings.json", "translations/nl.json", "translations/en.json"):
        assert json.dumps(json.loads((MAP / bestand).read_text())).count("airco_werkdag_warm_om") == 2
        assert json.dumps(json.loads((MAP / bestand).read_text())).count("airco_middag_doel_c") == 2


# --- v5.254.0: overdag naar het ingestelde doel -----------------------------

def test_het_dagdoel_gaat_voor_het_geleerde():
    r = R.leeg()
    for d in range(1, 5):
        r["dag_aan"]["werkdag"][f"2026-11-1{d}"] = {"minuut": 930, "doel": 21.0}
    assert R.geleerd_dag(r, "werkdag")["doel_c"] == 21.0
    r["vast_dag_doel"] = 23.0
    assert R.geleerd_dag(r, "werkdag")["doel_c"] == 23.0
    assert R.geleerd_dag(r, "weekend")["doel_c"] == 23.0


def test_de_coordinator_kiest_overdag_het_ingestelde_doel(make_coordinator, hass):
    c = make_coordinator({"airco_middag_doel_c": 23.0, "airco_werkdag_warm_om": "07:00"})
    c.airco_setpunten = [21.0] * 6
    assert c._airco_doel_nu(DI.replace(hour=14)) == 23.0
    assert c._airco_doel_nu(DI.replace(hour=8)) == 21.0          # 's ochtends het geleerde
    assert c._airco_doel_nu(DI.replace(hour=21, minute=45)) == 21.0
    r = c._airco_ritme()
    assert r["vast_dag_doel"] == 23.0
    assert r["vast_ochtend"]["werkdag"]["doel_c"] == 21.0        # de ochtend blijft 21
    zonder = make_coordinator({})
    zonder.airco_setpunten = [21.0] * 6
    assert zonder._airco_doel_nu(DI.replace(hour=14)) == 21.0
    assert zonder._airco_ritme()["vast_dag_doel"] is None
    assert make_coordinator({"airco_middag_doel_c": 40})._airco_middag_doel() is None


def test_een_airco_van_de_ochtend_gaat_overdag_mee_naar_het_dagdoel(make_coordinator, hass, monkeypatch):
    from homeassistant.util import dt as dt_util

    c = make_coordinator({"airco_middag_doel_c": 23.0})
    c.airco_door_ems = True
    c._airco_handmatig_bij = None
    c._airco_laatste_ems = {"stand": "heat", "doel": 21.0, "basis": 21.0}
    c._get_forecast_entries = lambda *a, **k: []
    c.huidige_prijs_eur_per_kwh = lambda *_a: 0.30
    uit = c._airco_buffer_ronde(DI.replace(hour=11, minute=5), {"actie": "niets", "doel_c": 23.0}, "heat")
    assert uit["actie"] == "verwarmen" and uit["doel_c"] >= 23.0
    # de lage stand voor 'lang weg' (18 graden) blijft
    c._airco_laatste_ems = {"stand": "heat", "doel": 18.0, "basis": 18.0}
    uit = c._airco_buffer_ronde(DI.replace(hour=11, minute=5), {"actie": "niets", "doel_c": 23.0}, "heat")
    assert uit.get("actie") == "niets"
    # en 's ochtends verandert er niets
    c._airco_laatste_ems = {"stand": "heat", "doel": 21.0, "basis": 21.0}
    uit = c._airco_buffer_ronde(DI.replace(hour=8, minute=30), {"actie": "niets", "doel_c": 21.0}, "heat")
    assert uit.get("actie") == "niets"
