"""PV-installatieprofiel afgeleid uit de zonnestand (v1.4.0).

Gevraagd: "kun je nu ook zelf een berekening maken voor de verwachtte
azimuth en andere relevante informatie hoe mijn PV installatie
geinstalleerd ligt".

Het vermogen piekt wanneer de zon recht voor de panelen staat, dus de
zon-azimut op dat moment schat de paneelrichting. De verhouding tussen
werkelijke en verwachte opbrengst per windrichting laat beschaduwing
zien.

Hellingshoek wordt bewust NIET afgeleid - dat vraagt maanden aan
seizoensvariatie of oncontroleerbare aannames, en een getal dat er
vijftien graden naast zit is erger dan geen getal.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_PV_POWER_SENSOR,
    CONF_SUN_PHASE_SENSOR,
    PV_GEOMETRY_BUCKET_MIN_SAMPLES,
    PV_GEOMETRY_MIN_DAYS,
    RELIABILITY_INDICATIVE,
    RELIABILITY_INSUFFICIENT,
)

FASE = "sensor.zon_fase"


def _met_zonvoorspelling(c):
    """v1.8.1: het profiel meldt "niet geconfigureerd" zonder
    zonvoorspelling, want dan valt niet te bepalen of een dag helder
    genoeg was. Deze tests gaan over het gedrag DAARNA."""
    c._get_pv_forecast_entries = lambda: [("x", "y", 1.0)]
    return c


def _coordinator(make_coordinator, hass):
    c = make_coordinator(
        {CONF_PV_POWER_SENSOR: "sensor.pv", CONF_SUN_PHASE_SENSOR: FASE}
    )
    hass.states.set(FASE, "day")
    return _met_zonvoorspelling(c)


def _meting(c, hass, azimut, pv_w, verwacht_w, moment):
    """Eén tick met een gegeven zonstand, opbrengst en verwachting."""
    hass.states.set("sun.sun", "above_horizon", {"azimuth": azimut})
    hass.states.set("sensor.pv", str(pv_w))
    c._get_expected_pv_power_w = lambda now, _w=verwacht_w: _w
    c._update_pv_geometry_learning(moment)


def _dag(c, hass, dag_offset, piek_azimut, factor=1.0):
    """Een hele dag: de zon loopt van oost naar west, met de piek op de
    opgegeven azimut."""
    basis = datetime(2026, 8, 1, 6, 0, tzinfo=timezone.utc) + timedelta(
        days=dag_offset
    )
    for stap in range(24):
        azimut = 70 + stap * 10
        # Driehoekig profiel rond de piekrichting.
        afstand = abs(azimut - piek_azimut)
        verwacht = max(0, 3000 - afstand * 25)
        if verwacht <= 0:
            continue
        _meting(c, hass, azimut, verwacht * factor, verwacht,
                basis + timedelta(minutes=stap * 30))


# --- oriëntatie ------------------------------------------------------


def test_no_verdict_without_enough_clear_days(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _dag(c, hass, 0, 180)

    profiel = c.get_pv_installation_profile()

    assert profiel["betrouwbaarheid"] == RELIABILITY_INSUFFICIENT
    assert profiel["geschatte_azimut"] is None


def test_the_orientation_is_derived(make_coordinator, hass):
    """De kern: de zon-azimut bij de dagpiek verraadt de
    paneelrichting."""
    c = _coordinator(make_coordinator, hass)
    for dag in range(PV_GEOMETRY_MIN_DAYS + 2):
        _dag(c, hass, dag, 180)
    # Nog een dag zodat de laatste wordt afgesloten.
    _dag(c, hass, PV_GEOMETRY_MIN_DAYS + 2, 180)

    profiel = c.get_pv_installation_profile()

    assert profiel["geschatte_azimut"] == 180.0
    assert profiel["windrichting"] == "zuid"
    assert profiel["betrouwbaarheid"] == RELIABILITY_INDICATIVE


def test_a_south_west_roof_is_recognised(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    for dag in range(PV_GEOMETRY_MIN_DAYS + 3):
        _dag(c, hass, dag, 220)

    assert c.get_pv_installation_profile()["windrichting"] == "zuidwest"


def test_a_cloudy_day_is_not_counted(make_coordinator, hass):
    """Op een dag met wisselende bewolking ligt de piek waar het
    toevallig opklaarde - dat zegt niets over de daklijn."""
    c = _coordinator(make_coordinator, hass)
    _dag(c, hass, 0, 180, factor=0.3)
    _dag(c, hass, 1, 180, factor=0.3)

    assert c.pv_peak_azimuth_history == []


def test_multiple_roof_planes_are_flagged(make_coordinator, hass):
    """Bij één dakvlak liggen de dagelijkse pieken dicht bij elkaar; een
    brede spreiding wijst op meer dan één richting."""
    c = _coordinator(make_coordinator, hass)
    for dag in range(4):
        _dag(c, hass, dag * 2, 120)
        _dag(c, hass, dag * 2 + 1, 240)

    profiel = c.get_pv_installation_profile()

    assert profiel["waarschijnlijk_meerdere_dakvlakken"] is True
    assert profiel["spreiding_graden"] > 40


def test_one_roof_plane_is_not_flagged(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    for dag in range(PV_GEOMETRY_MIN_DAYS + 3):
        _dag(c, hass, dag, 180)

    assert (
        c.get_pv_installation_profile()["waarschijnlijk_meerdere_dakvlakken"]
        is False
    )


# --- beschaduwing ----------------------------------------------------


def test_shading_is_detected_per_direction(make_coordinator, hass):
    """Een windrichting die structureel achterblijft verraadt een boom,
    schoorsteen of dakkapel."""
    c = _coordinator(make_coordinator, hass)
    moment = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)

    for i in range(PV_GEOMETRY_BUCKET_MIN_SAMPLES + 5):
        # Oost presteert normaal, zuidoost blijft ver achter.
        _meting(c, hass, 95.0, 2000, 2000, moment + timedelta(minutes=i))
        _meting(c, hass, 135.0, 600, 2000, moment + timedelta(minutes=i))

    beschaduwd = {
        s["azimut"] for s in c.get_pv_installation_profile()["beschaduwing"]
    }

    assert 130.0 in beschaduwd
    assert 90.0 not in beschaduwd


def test_a_thin_bucket_is_not_judged(make_coordinator, hass):
    """Te weinig metingen in een vakje mag geen conclusie opleveren."""
    c = _coordinator(make_coordinator, hass)
    moment = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)

    for i in range(3):
        _meting(c, hass, 135.0, 100, 2000, moment + timedelta(minutes=i))

    assert c.get_pv_installation_profile()["beschaduwing"] == []


def test_low_expectations_are_ignored(make_coordinator, hass):
    """Bij een verwachting van bijna nul is de verhouding betekenisloos -
    vroeg in de ochtend zou anders alles als beschaduwd gelden."""
    c = _coordinator(make_coordinator, hass)
    moment = datetime(2026, 8, 1, 6, 0, tzinfo=timezone.utc)

    for i in range(50):
        _meting(c, hass, 75.0, 0, 50, moment + timedelta(minutes=i))

    assert c.pv_azimuth_performance == {}


# --- overige ---------------------------------------------------------


def test_nothing_is_learned_at_night(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set(FASE, "night")

    _meting(c, hass, 180.0, 0, 0,
            datetime(2026, 8, 1, 23, 0, tzinfo=timezone.utc))

    assert c.pv_peak_azimuth_history == []
    assert c.pv_azimuth_performance == {}


def test_no_tilt_is_estimated(make_coordinator, hass):
    """Bewust weggelaten: dat vraagt maanden aan seizoensvariatie of
    oncontroleerbare aannames. Een getal dat er vijftien graden naast
    zit is erger dan geen getal.

    v1.4.1: er is wél een `opgegeven_hellingshoek` - dat is een
    ingevulde waarde en geen schatting, en die wordt alleen gebruikt om
    de tolerantie te bepalen.
    """
    c = _coordinator(make_coordinator, hass)

    profiel = c.get_pv_installation_profile()

    geschat = [
        sleutel
        for sleutel in profiel
        if ("hellingshoek" in sleutel or "tilt" in sleutel)
        and not sleutel.startswith("opgegeven")
    ]
    assert geschat == []


def test_compass_conversion(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    assert c._azimuth_to_compass(0) == "noord"
    assert c._azimuth_to_compass(90) == "oost"
    assert c._azimuth_to_compass(180) == "zuid"
    assert c._azimuth_to_compass(270) == "west"
    assert c._azimuth_to_compass(359) == "noord"


def test_the_profile_survives_a_restart(make_coordinator, hass):
    """Het profiel bouwt over weken op; zonder bewaren zou het na elke
    herstart opnieuw beginnen en nooit iets opleveren."""
    import asyncio

    bron = _coordinator(make_coordinator, hass)
    bron.pv_peak_azimuth_history = [180.0, 182.0, 179.0]
    bron.pv_azimuth_performance = {"130": [0.4] * 25}
    asyncio.run(bron.async_save_persisted_state_now())

    verse = _coordinator(make_coordinator, hass)
    asyncio.run(verse.async_load_persisted_state())

    assert verse.pv_peak_azimuth_history == [180.0, 182.0, 179.0]
    assert verse.pv_azimuth_performance == {"130": [0.4] * 25}


def test_it_appears_in_the_reliability_overview(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    namen = {r["naam"] for r in c.get_reliability_overview()}

    assert "PV-installatieprofiel (oriëntatie)" in namen


# --- v1.4.1: vergelijken met de opgegeven waarde ---------------------

from custom_components.energy_management_system.const import (  # noqa: E402
    CONF_PV_ACTUAL_AZIMUTH_DEGREES,
    CONF_PV_ACTUAL_TILT_DEGREES,
    PV_ORIENTATION_MISMATCH_DEGREES,
    PV_SHALLOW_TILT_EXTRA_TOLERANCE_DEGREES,
)


def _met_opgave(make_coordinator, hass, azimut, helling=None):
    config = {
        CONF_PV_POWER_SENSOR: "sensor.pv",
        CONF_SUN_PHASE_SENSOR: FASE,
        CONF_PV_ACTUAL_AZIMUTH_DEGREES: azimut,
    }
    if helling is not None:
        config[CONF_PV_ACTUAL_TILT_DEGREES] = helling
    c = make_coordinator(config)
    hass.states.set(FASE, "day")
    return _met_zonvoorspelling(c)


def test_a_matching_orientation_is_confirmed(make_coordinator, hass):
    c = _met_opgave(make_coordinator, hass, 200)
    c.pv_peak_azimuth_history = [205.0] * 8

    profiel = c.get_pv_installation_profile()

    assert profiel["afwijking_graden"] == 5.0
    assert profiel["wijkt_af"] is False


def test_a_large_deviation_is_flagged(make_coordinator, hass):
    """Verschuift de piekrichting terwijl de panelen niet zijn
    verplaatst, dan wijst dat op iets fysieks."""
    c = _met_opgave(make_coordinator, hass, 200)
    c.pv_peak_azimuth_history = [255.0] * 8

    profiel = c.get_pv_installation_profile()

    assert profiel["afwijking_graden"] == 55.0
    assert profiel["wijkt_af"] is True


def test_a_shallow_tilt_widens_the_tolerance(make_coordinator, hass):
    """Bij een flauwe helling is de opbrengstcurve breder en ligt het
    piekmoment minder scherp vast. Zonder deze verruiming zou een vlakke
    opstelling voortdurend "afwijkend" melden terwijl er niets aan de
    hand is."""
    steil = _met_opgave(make_coordinator, hass, 200, helling=40)
    vlak = _met_opgave(make_coordinator, hass, 200, helling=12)
    afwijking = PV_ORIENTATION_MISMATCH_DEGREES + 5
    for c in (steil, vlak):
        c.pv_peak_azimuth_history = [200.0 + afwijking] * 8

    assert steil.get_pv_installation_profile()["wijkt_af"] is True
    assert vlak.get_pv_installation_profile()["wijkt_af"] is False
    assert (
        vlak.get_pv_installation_profile()["tolerantie_graden"]
        == PV_ORIENTATION_MISMATCH_DEGREES
        + PV_SHALLOW_TILT_EXTRA_TOLERANCE_DEGREES
    )


def test_no_verdict_while_the_estimate_is_still_weak(make_coordinator, hass):
    """Bij onvoldoende data zegt een afwijking niets - dan hoort er geen
    oordeel te staan."""
    c = _met_opgave(make_coordinator, hass, 200)
    c.pv_peak_azimuth_history = [300.0]

    profiel = c.get_pv_installation_profile()

    assert profiel["wijkt_af"] is None


def test_without_a_configured_value_nothing_is_compared(
    make_coordinator, hass
):
    c = _coordinator(make_coordinator, hass)
    c.pv_peak_azimuth_history = [200.0] * 8

    profiel = c.get_pv_installation_profile()

    assert profiel["afwijking_graden"] is None
    assert profiel["wijkt_af"] is None


def test_the_deviation_wraps_around_north(make_coordinator, hass):
    """350° en 10° liggen twintig graden uit elkaar, niet 340 - anders
    zou een opstelling rond het noorden altijd als afwijkend gelden."""
    c = _met_opgave(make_coordinator, hass, 350)
    c.pv_peak_azimuth_history = [10.0] * 8

    assert c.get_pv_installation_profile()["afwijking_graden"] == 20.0


def test_without_a_solar_forecast_it_says_so(make_coordinator, hass):
    """v1.8.1: zonder zonvoorspelling wordt er nooit een dag afgesloten,
    want dan valt niet te bepalen of hij helder genoeg was. De teller
    bleef dan op "0/5 heldere dagen" staan zonder uit te leggen waarom -
    en wie geen Solcast heeft zou eeuwig wachten op een profiel dat nooit
    komt."""
    from custom_components.energy_management_system.const import (
        RELIABILITY_NOT_CONFIGURED,
    )

    c = make_coordinator({CONF_PV_POWER_SENSOR: "sensor.pv"})

    profiel = c.get_pv_installation_profile()

    assert profiel["betrouwbaarheid"] == RELIABILITY_NOT_CONFIGURED
    assert "zonvoorspelling" in profiel["reden"]


# --- v1.46.0: de azimut kwam nooit binnen ----------------------------


def test_an_own_azimuth_sensor_is_used(make_coordinator, hass):
    """Gemeld: "Vandaag was een mega zonnige dag: PV-installatieprofiel
    (oriëntatie) 0/5 heldere dagen verzameld."

    Het lag niet aan de bewolking. De azimut werd uitsluitend uit
    `sun.sun` gelezen, terwijl de zonshoogte wel een eigen instelbare
    sensor had. Komt de zonstand van een eigen integratie, dan viel de
    hele leerroutine elke tick meteen stil.
    """
    from custom_components.energy_management_system.const import (
        CONF_SUN_AZIMUTH_SENSOR,
    )

    c = _coordinator(make_coordinator, hass)
    c.config[CONF_SUN_AZIMUTH_SENSOR] = "sensor.eigen_azimut"
    hass.states.set("sensor.eigen_azimut", "182.5")

    assert c.get_sun_azimuth_degrees() == 182.5


def test_sun_sun_remains_the_fallback(make_coordinator, hass):
    """Wie niets instelt mag er niets van merken."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sun.sun", "above_horizon", {"azimuth": 200.0})

    assert c.get_sun_azimuth_degrees() == 200.0


def test_without_any_azimuth_the_profile_says_why(make_coordinator, hass):
    """"0/5 heldere dagen" is een misleidend antwoord als de oorzaak is
    dat de zonstand niet uit te lezen valt - dan helpt wachten niet."""
    from custom_components.energy_management_system.const import (
        RELIABILITY_NOT_CONFIGURED,
    )

    c = _coordinator(make_coordinator, hass)

    profiel = c.get_pv_installation_profile()

    assert profiel["betrouwbaarheid"] == RELIABILITY_NOT_CONFIGURED
    assert "azimut" in profiel["reden"]


def test_with_days_collected_the_warning_disappears(make_coordinator, hass):
    """Zodra er dagen zijn, gaat het weer over die dagen - niet over de
    sensor."""
    from custom_components.energy_management_system.const import (
        RELIABILITY_NOT_CONFIGURED,
    )

    c = _coordinator(make_coordinator, hass)
    c.pv_peak_azimuth_history = [180.0, 181.0]

    profiel = c.get_pv_installation_profile()

    assert profiel["betrouwbaarheid"] != RELIABILITY_NOT_CONFIGURED


# --- v1.49.0: een herstart wist de dag ------------------------------


def test_the_days_peak_survives_a_restart():
    """`_finalize_pv_geometry_day` sluit de dag af zodra de datum
    wisselt - maar na een herstart staat de piek op 0 en wordt de dag
    stilzwijgend weggegooid. Met een herstart ná de middagpiek is de
    rest van de dag bovendien te donker om als "helder" door te komen.

    Daarmee was "0/5 heldere dagen" op een strakblauwe dag een
    zelfvervullende voorspelling: elke versie die je installeert wist de
    dag waarop gemeten werd.
    """
    from custom_components.energy_management_system.const import (
        PERSISTED_DATE_FIELDS,
        PERSISTED_PLAIN_FIELDS,
    )

    assert "_pv_geometry_day_key" in PERSISTED_DATE_FIELDS
    for veld in (
        "_pv_geometry_day_peak_w",
        "_pv_geometry_day_peak_azimuth",
        "_pv_geometry_day_expected_peak_w",
    ):
        assert veld in PERSISTED_PLAIN_FIELDS, veld


def test_a_restart_mid_afternoon_keeps_the_morning_peak(
    make_coordinator, hass
):
    """De piek van vóór de herstart telt gewoon mee."""
    c = _coordinator(make_coordinator, hass)
    _dag(c, hass, 0, 180)
    piek_voor = c._pv_geometry_day_peak_w

    # Herstart: de dagstand komt terug uit de opslag.
    verse = _coordinator(make_coordinator, hass)
    verse._pv_geometry_day_key = c._pv_geometry_day_key
    verse._pv_geometry_day_peak_w = c._pv_geometry_day_peak_w
    verse._pv_geometry_day_peak_azimuth = c._pv_geometry_day_peak_azimuth
    verse._pv_geometry_day_expected_peak_w = c._pv_geometry_day_expected_peak_w

    verse._finalize_pv_geometry_day()

    assert piek_voor > 0
    assert verse.pv_peak_azimuth_history == [180.0]
