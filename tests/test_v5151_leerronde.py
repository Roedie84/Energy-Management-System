"""v5.151.0 - leerronde 31-10 (dagafsluiting).

L-EMS-049: de zonstandtoets vergelijkt met de zonstand op het moment dat
de sensor zijn waarde kreeg. 's Nachts ververst de zonnesensor maar elke
20 minuten terwijl de azimut 6-8 graden per 20 minuten draait; met 'nu'
gaf dat elke nacht ~85 minuten een valse "Stand van de zon klopt niet".
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_SUN_AZIMUTH_SENSOR,
    RELIABILITY_RELIABLE,
    RELIABILITY_UNRELIABLE,
)

# 30-10-2026 23:30 lokaal (CET) - het moment van de valse 'doen'-regel.
NU = datetime(2026, 10, 30, 22, 30, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass):
    from types import SimpleNamespace

    c = make_coordinator({CONF_SUN_AZIMUTH_SENSOR: "sensor.azimut"})
    hass.config = SimpleNamespace(latitude=52.10, longitude=6.65)
    return c


def _zet(hass, waarde, moment):
    hass.states.set("sensor.azimut", str(waarde))
    hass.states.get("sensor.azimut").last_updated = moment


def test_twintig_minuten_oude_nachtwaarde_klopt(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    meetmoment = NU - timedelta(minutes=20)
    az_toen = c._bereken_zonstand(meetmoment)[0]
    az_nu = c._bereken_zonstand(NU)[0]
    # Voorwaarde van het scenario: de zon draaide in 20 min meer dan de tolerantie
    assert abs((az_nu - az_toen + 180) % 360 - 180) > 5.0
    _zet(hass, round(az_toen + 0.3, 1), meetmoment)

    toets = c.get_sun_position_check(NU)

    assert toets["status"] == RELIABILITY_RELIABLE
    assert toets["leeftijd_meting_min"] == 20.0
    assert toets["verschil_graden"] < 1.0
    # berekend_azimut blijft de stand van nu (pv-modelsamples)
    assert toets["berekend_azimut"] == round(az_nu, 1)


def test_vaste_afwijking_van_tien_graden_blijft_gevangen(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    meetmoment = NU - timedelta(minutes=20)
    az_toen = c._bereken_zonstand(meetmoment)[0]
    _zet(hass, round((az_toen + 10.0) % 360, 1), meetmoment)

    toets = c.get_sun_position_check(NU)

    assert toets["status"] == RELIABILITY_UNRELIABLE


def test_vastgelopen_sensor_telt_als_nu(make_coordinator, hass):
    """Ouder dan een uur: vergelijken met nu, zodat een bevroren waarde opvalt."""
    c = _coordinator(make_coordinator, hass)
    meetmoment = NU - timedelta(hours=3)
    az_toen = c._bereken_zonstand(meetmoment)[0]
    _zet(hass, round(az_toen, 1), meetmoment)

    toets = c.get_sun_position_check(NU)

    assert "leeftijd_meting_min" not in toets
    assert toets["status"] == RELIABILITY_UNRELIABLE


def test_zonder_tijdstempel_rekent_hij_met_nu(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.azimut", str(round(c._bereken_zonstand(NU)[0], 1)))

    toets = c.get_sun_position_check(NU)

    assert toets["status"] == RELIABILITY_RELIABLE
    assert "gemeten_om" not in toets


# --- L-EMS-048: proefstandregels zeggen hoe ver ze zijn -------------------

from custom_components.energy_management_system.coordinator import (  # noqa: E402
    EnergyManagementSystemCoordinator as _C,
)


def test_wachtende_kandidaat_toont_de_reden():
    k = {
        "naam": "Plan gewogen over drie scenario's",
        "status": "onvoldoende",
        "waarde": None,
        "zou_hebben_opgeleverd": {"te_becijferen": False, "reden": "7 van 14 dagen gemeten sinds v5.122.0."},
        "betrouwbaarheid": "Verwachte kosten over drie zonscenario's. Stuurt niets.",
    }
    assert _C._proefstand_wat_ontbreekt(k) == "7 van 14 dagen gemeten sinds v5.122.0."


def test_uitgerekende_kandidaat_is_herkenbaar():
    k = {
        "naam": "Regressiewoud voor de zonvoorspelling",
        "status": "indicatief",
        "waarde": "-13.2% tegen de huidige methode",
        "zou_hebben_opgeleverd": {"te_becijferen": True, "reden": "Gemiddelde fout 0.21 kWh per uur tegen 0.19 nu, over 15 ongeziene dagen."},
        "betrouwbaarheid": "Getoetst op dagen die het model niet heeft gezien.",
    }
    tekst = _C._proefstand_wat_ontbreekt(k)
    assert tekst.startswith("Uitgerekend: -13.2%")
    assert "15 ongeziene dagen" in tekst


def test_zonder_reden_blijft_de_omschrijving():
    k = {"naam": "x", "status": "onvoldoende", "betrouwbaarheid": "Omschrijving.", "zou_hebben_opgeleverd": {}}
    assert _C._proefstand_wat_ontbreekt(k) == "Omschrijving."


# --- L-EMS-047: dagarchief vult ontbrekende kwartieren aan ---------------

from custom_components.energy_management_system import dagarchief as D  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

TZ = ZoneInfo("Europe/Amsterdam")


def _dag(datum="2026-10-29", missen=()):
    """96 kwartieren: 's nachts 0,1 kWh huis uit het net, 11-15 u 0,25 kWh zon per kwartier."""
    begin = datetime.fromisoformat(datum + "T00:00").replace(tzinfo=TZ)
    kwartieren = []
    uren: dict = {t: {} for t in ("grid_import", "grid_export", "pv", "battery_out", "battery_in")}
    for n in range(96):
        moment = (begin + timedelta(minutes=15 * n)).astimezone(timezone.utc)
        lokaal = moment.astimezone(TZ)
        zon = 0.25 if 11 <= lokaal.hour < 15 else 0.0
        imp = 0.1 if zon == 0 else 0.0
        exp = max(0.0, zon - 0.1)
        huis = imp - exp + zon
        sleutel = moment.replace(minute=0)
        for t, w in (("grid_import", imp), ("grid_export", exp), ("pv", zon), ("battery_out", 0.0), ("battery_in", 0.0)):
            uren[t][sleutel] = uren[t].get(sleutel, 0.0) + w
        if n in missen:
            continue
        kwartieren.append({"kwartier": moment.isoformat(), "grid_import_kwh": imp, "grid_export_kwh": exp,
                           "pv_kwh": zon, "battery_out_kwh": 0.0, "battery_in_kwh": 0.0, "house_kwh": huis,
                           "prijs_eur": 0.4})
    prijzen = {m: 0.4 for m in uren["pv"]}
    return kwartieren, uren, prijzen


def test_drie_ontbrekende_middagkwartieren_worden_aangevuld():
    # 12:00, 12:15 en 14:45 lokaal ontbreken (herstarts)
    kwartieren, uren, prijzen = _dag(missen=(48, 49, 59))
    oud = D.dag_uit_kwartieren(kwartieren)
    assert oud["p"] == 3.25            # 16 kwartieren x 0,25 = 4,0 - 0,75
    nieuw = D.dag_uit_kwartieren_en_statistiek(kwartieren, uren, prijzen, "2026-10-29")
    assert nieuw["p"] == 4.0           # gelijk aan de teller
    assert nieuw["q"] == 93 and nieuw["aq"] == 3 and nieuw["su"] == 2
    assert nieuw["b_"] == "m"
    assert nieuw["v"] == D.dag_uit_kwartieren(_dag()[0])["v"]


def test_volledige_dag_blijft_gelijk():
    kwartieren, uren, prijzen = _dag()
    assert D.dag_uit_kwartieren_en_statistiek(kwartieren, uren, prijzen, "2026-10-29") == {
        **D.dag_uit_kwartieren(kwartieren)}


def test_zonder_statistiek_blijven_de_meetlogkwartieren():
    kwartieren, _, _ = _dag(missen=(48,))
    regel = D.dag_uit_kwartieren_en_statistiek(kwartieren, {}, {}, "2026-10-29")
    assert regel["p"] == 3.75 and "aq" not in regel


def test_verwachte_kwartieren_rond_de_klokwissel():
    assert D.verwachte_kwartieren("2026-10-29") == 96
    assert D.verwachte_kwartieren("2026-10-25") == 100
    assert D.verwachte_kwartieren("2026-03-29") == 92


def test_aanvulling_uitgeschreven():
    regel = D.uitgeschreven({"aq": 3, "su": 2, "b_": "m"})
    assert regel["aangevulde_kwartieren"] == 3 and regel["uren_uit_statistiek"] == 2
