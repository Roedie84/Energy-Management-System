"""v5.65: het dagritme van de airco, geleerd uit jullie eigen bediening.

Gevraagd 09-10: "Ik wil dat het EMS dit gaat regelen, dus leert van mijn
gedrag" en "op basis van voorspelling niet op tijdstippen".
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import airco_ritme as ar

TZ = timezone(timedelta(hours=2))
MA = datetime(2026, 10, 5, tzinfo=TZ)  # maandag


def _op(dag, uur, minuut=0):
    return MA + timedelta(days=dag, hours=uur, minutes=minuut)


def _geleerd_ritme(ochtenden=3, bed=3):
    r = ar.leeg()
    for d in range(ochtenden):
        ar.noteer_ochtend_thuis(r, _op(d, 6, 0))
        ar.noteer_bediening(r, _op(d, 6, 45), "heat", 19)
    for d in range(bed):
        ar.noteer_bediening(r, _op(d, 22, 0), "off", None)
    return r


def _besluit(r, nu, **extra):
    basis = dict(
        nu=nu, woonkamer_c=17.5, verwacht_bij_warm_om=lambda m: 17.0,
        tempo_c_per_uur=2.0, aanwezigheid="slaapt", advies="airco", airco_stand="off",
    )
    basis.update(extra)
    return ar.besluit(r, **basis)


def test_leert_warm_om_doel_en_bedtijd():
    leer = ar.geleerd(_geleerd_ritme(), "werkdag")
    assert leer["warm_om"] == 405 and leer["ochtend_doel_c"] == 19.0
    assert leer["bedtijd"] == 1320 and leer["kans"] == 1.0


def test_pas_vanaf_drie_keer():
    leer = ar.geleerd(_geleerd_ritme(ochtenden=2, bed=2), "werkdag")
    assert leer["warm_om"] is None and leer["bedtijd"] is None


def test_weekend_apart():
    assert ar.geleerd(_geleerd_ritme(), "weekend")["warm_om"] is None


def test_na_middernacht_hoort_bij_de_avond_ervoor():
    r = ar.leeg()
    ar.noteer_bediening(r, _op(1, 0, 30), "off", None)
    assert r["uit"]["werkdag"] == {"2026-10-05": 1470}


def test_aanzetmoment_volgt_uit_voorspelling_en_opwarmtempo():
    r = _geleerd_ritme()
    # 2 graden tekort, 2 °C/uur: een uur vooraf -> 05:45.
    assert _besluit(r, _op(3, 5, 40)) is None
    uit = _besluit(r, _op(3, 5, 45))
    assert uit["actie"] == "verwarmen" and uit["doel_c"] == 19.0
    # Warmer verwacht: later aan.
    assert _besluit(r, _op(3, 5, 45), verwacht_bij_warm_om=lambda m: 18.5) is None
    assert _besluit(r, _op(3, 6, 30), verwacht_bij_warm_om=lambda m: 18.5)["actie"] == "verwarmen"


def test_geen_ochtendverwarming_als_warm_genoeg_niemand_thuis_of_gas_goedkoper():
    r = _geleerd_ritme()
    assert _besluit(r, _op(3, 6, 0), woonkamer_c=19.5, verwacht_bij_warm_om=lambda m: 19.2) is None
    assert _besluit(r, _op(3, 6, 0), aanwezigheid="weg") is None
    assert _besluit(r, _op(3, 6, 0), advies="gas") is None


def test_ochtendverwarming_loopt_door_als_iedereen_nog_slaapt():
    r = _geleerd_ritme()
    ar.noteer_ems_aan(r, _op(3, 6, 0))
    uit = _besluit(r, _op(3, 6, 30), airco_stand="heat")
    assert uit["houd_aan"]
    assert _besluit(r, _op(3, 8, 0), airco_stand="heat") is None


def test_ems_ochtend_weer_uitgezet_telt_als_niet_gewenst():
    r = _geleerd_ritme()
    ar.noteer_ochtend_thuis(r, _op(3, 6, 0))
    ar.noteer_ems_aan(r, _op(3, 6, 0))
    ar.noteer_bediening(r, _op(3, 6, 10), "off", None)
    assert "2026-10-08" not in r["aan"]["werkdag"]
    assert ar.geleerd(r, "werkdag")["kans"] == 0.75


def test_bedtijd_uit_een_keer_per_avond():
    r = _geleerd_ritme()
    assert _besluit(r, _op(3, 21, 50), airco_stand="heat") is None
    uit = _besluit(r, _op(3, 22, 5), airco_stand="heat")
    assert uit["actie"] == "uit"
    ar.noteer_ems_uit(r, _op(3, 22, 5))
    assert _besluit(r, _op(3, 22, 30), airco_stand="heat") is None


def test_kapotte_opslag_geeft_lege_structuur():
    assert ar.geldig("onzin") == ar.leeg()
    assert ar.geldig({"aan": {"werkdag": []}}) == ar.leeg()


# --- coördinator --------------------------------------------------------------

def test_ritme_wint_van_slaapt_en_stuurt_ochtenddoel(make_coordinator):
    c = make_coordinator({})
    c.airco_ritme = _geleerd_ritme()
    c.presence_state = "slaapt"
    c.living_room_current_temp_c = 17.5
    c.airco_automaat_aan = True
    c._airco_handmatig_bij = None
    c.get_verwarmingsadvies = lambda: {"advies": "airco"}
    c._woonkamer_verwacht_om = lambda m: 17.0
    basis = {"actie": "niets", "tekst": "x", "redenen": [], "redenen_tekst": "", "doel_c": 21.0}
    # Opwarmtempo nog onbekend: een half uur vooraf.
    assert c._airco_ritme_ronde(_op(3, 6, 10), basis, "off")["actie"] == "niets"
    uit = c._airco_ritme_ronde(_op(3, 6, 20), basis, "off")
    assert uit["actie"] == "verwarmen" and uit["doel_c"] == 19.0
    assert c.airco_ritme["ems"]["aan"] == "2026-10-08"


def test_ritme_niet_als_iemand_zelf_bedient(make_coordinator):
    c = make_coordinator({})
    c.airco_ritme = _geleerd_ritme()
    c.presence_state = "thuis"
    c.living_room_current_temp_c = 17.5
    c._airco_handmatig_bij = "thuis"
    c.get_verwarmingsadvies = lambda: {"advies": "airco"}
    c._woonkamer_verwacht_om = lambda m: 17.0
    basis = {"actie": "niets", "tekst": "x", "redenen": [], "redenen_tekst": "", "doel_c": 21.0}
    assert c._airco_ritme_ronde(_op(3, 6, 0), basis, "off")["actie"] == "niets"


def test_bedtijd_gaat_ook_voor_handmatig(make_coordinator):
    c = make_coordinator({})
    c.airco_ritme = _geleerd_ritme()
    c.presence_state = "thuis"
    c._airco_handmatig_bij = "thuis"
    c.airco_automaat_aan = True
    basis = {"actie": "niets", "tekst": "x", "redenen": [], "redenen_tekst": "", "doel_c": 21.0}
    assert c._airco_ritme_ronde(_op(3, 22, 10), basis, "heat")["actie"] == "uit"


def test_opwarmtempo_uit_de_klimaatcellen(make_coordinator):
    c = make_coordinator({})
    c.climate_rate_history = {"d-5|beide_open|verwarmen": [1.5, 2.0, 2.5, 1.0, 3.0], "x|y|uit": [-0.2] * 9}
    assert c._airco_opwarmtempo() == 2.0


def test_ritme_wordt_bewaard():
    from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS

    assert "airco_ritme" in PERSISTED_PLAIN_FIELDS
