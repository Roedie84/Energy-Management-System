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


# --- v5.66: voorverwarmen op goedkope stroom ---------------------------------

from custom_components.energy_management_system import airco_sturing  # noqa: E402


def test_buffer_hoger_voor_een_duur_blok():
    b = airco_sturing.buffer(19.0, 0.20, [0.22, 0.35, 0.40])
    assert b["doel_c"] == 19.5 and "voorverwarmen" in b["reden"]


def test_buffer_lager_in_een_duur_kwartier():
    b = airco_sturing.buffer(19.0, 0.40, [0.38, 0.25, 0.22])
    assert b["doel_c"] == 18.5


def test_buffer_vlak_bij_gelijke_prijzen():
    assert airco_sturing.buffer(19.0, 0.25, [0.26, 0.27, 0.24])["doel_c"] == 19.0
    assert airco_sturing.buffer(None, 0.25, [0.40])["doel_c"] is None


def _met_prijzen(c, nu, nu_prijs, later):
    c._get_forecast_entries = lambda *a, **k: [
        (nu + timedelta(minutes=15 * (i + 1)), nu + timedelta(minutes=15 * (i + 2)), p)
        for i, p in enumerate(later)
    ]
    c.huidige_prijs_eur_per_kwh = lambda now=None: nu_prijs


def test_buffer_op_een_nieuw_verwarmen(make_coordinator):
    c = make_coordinator({})
    nu = _op(3, 17, 0)
    _met_prijzen(c, nu, 0.20, [0.30, 0.40])
    uit = c._airco_buffer_ronde(nu, {"actie": "verwarmen", "doel_c": 21.0, "tekst": "t", "redenen": []}, "off")
    assert uit["doel_c"] == 21.5 and uit["basis_doel_c"] == 21.0


def test_buffer_stelt_lopende_ems_airco_bij_maar_niet_handmatig(make_coordinator):
    c = make_coordinator({})
    nu = _op(3, 17, 0)
    _met_prijzen(c, nu, 0.20, [0.30, 0.40])
    c.airco_door_ems = True
    c._airco_handmatig_bij = None
    c._airco_laatste_ems = {"stand": "heat", "doel": 19.0, "basis": 19.0}
    basis = {"actie": "niets", "doel_c": 21.0, "tekst": "De airco verwarmt al.", "redenen": []}
    uit = c._airco_buffer_ronde(nu, basis, "heat")
    assert uit["actie"] == "verwarmen" and uit["doel_c"] == 19.5
    c._airco_laatste_ems = {"stand": "heat", "doel": 19.5, "basis": 19.0}
    assert c._airco_buffer_ronde(nu, basis, "heat")["actie"] == "niets"
    c._airco_handmatig_bij = "thuis"
    c._airco_laatste_ems = {"stand": "heat", "doel": 19.0, "basis": 19.0}
    assert c._airco_buffer_ronde(nu, basis, "heat")["actie"] == "niets"


# --- v5.66: warm bij thuiskomst ----------------------------------------------

def _thuis(r, **extra):
    basis = dict(
        koers="towards", km=10.0, aanwezigheid="weg", woonkamer_c=18.0, doel_c=21.0,
        tempo_c_per_uur=3.0, advies="airco", airco_stand="off", door_ems=False,
    )
    basis.update(extra)
    return ar.thuiskomst(r, **basis)


def test_thuiskomst_aan_als_reistijd_korter_dan_opwarmen():
    r = ar.leeg()
    # 3 graden tekort / 3 °C per uur = 60 min; 10 km / 50 km/h = 12 min.
    assert _thuis(r)["actie"] == "verwarmen"
    # 60 km weg: buiten bereik.
    assert _thuis(r, km=60.0) is None
    # 1 graad tekort / 3 = 20 min opwarmen, 25 km = 30 min reizen: nog niet.
    assert _thuis(r, km=25.0, woonkamer_c=20.0) is None


def test_thuiskomst_niet_als_iemand_thuis_is_of_weggaat():
    r = ar.leeg()
    assert _thuis(r, aanwezigheid="thuis") is None
    assert _thuis(r, koers="away_from") is None
    assert _thuis(r, advies="cv") is None


def test_thuiskomst_houdt_ems_airco_aan_tijdens_naderen():
    r = ar.leeg()
    assert _thuis(r, airco_stand="heat", door_ems=True)["houd_aan"]


def test_reissnelheid_wordt_geleerd():
    r = ar.leeg()
    t = _op(3, 17, 0)
    vorige = None
    for i, km in enumerate([20.0, 15.0, 10.0, 5.0]):
        moment = t + timedelta(minutes=5 * i)
        ar.noteer_nadering(r, vorige, moment, km)
        vorige = (moment, km)
    assert ar.reissnelheid(r) == 60.0


def test_thuiskomst_in_de_coordinator(make_coordinator, hass):
    c = make_coordinator({})
    hass.states.set("sensor.thuis_nearest_direction_of_travel", "towards", {})
    hass.states.set("sensor.thuis_nearest_distance", "8000", {"unit_of_measurement": "m"})
    assert c._nadering() == ("towards", 8.0)
    c.presence_state = "weg"
    c.living_room_current_temp_c = 18.0
    c._airco_handmatig_bij = None
    c.get_verwarmingsadvies = lambda: {"advies": "airco"}
    basis = {"actie": "niets", "tekst": "x", "redenen": [], "redenen_tekst": "", "doel_c": 21.0}
    assert c._airco_thuiskomst_ronde(_op(3, 17, 0), basis, "off")["actie"] == "verwarmen"
