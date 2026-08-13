"""Aanwezigheid uit bewegingssensoren (v1.18.2).

Gevraagd: "Ook zijn er meerdere bewegingssensoren in huis aanwezig, ik
wil dat je daarmee analyseert of er iemand thuis is of niet. Ook daar kun
je van leren lijkt me."

Bewust een INSTELBARE lijst en geen automatische herkenning: van de
twintig bewegingsachtige entiteiten in deze installatie hangen er
meerdere buiten (deurbel, tuin, schuur). Die slaan aan als de kat
langsloopt en zeggen niets over of er iemand thuis is.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_PRESENCE_MOTION_SENSORS,
    PRESENCE_ABSENCE_AFTER_MINUTES,
    PRESENCE_MIN_OBSERVATIONS,
)

NU = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
SENSOREN = ["binary_sensor.gang", "binary_sensor.woonkamer"]


def _coordinator(make_coordinator, hass, sensoren=SENSOREN):
    c = make_coordinator({CONF_PRESENCE_MOTION_SENSORS: sensoren})
    for naam in SENSOREN:
        hass.states.set(naam, "off")
    return c


# --- de detectie -----------------------------------------------------


def test_motion_means_someone_is_home(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")

    c._update_presence(NU)

    assert c.presence_state == "thuis"


def test_a_short_quiet_period_is_still_home(make_coordinator, hass):
    """Stilzitten op de bank is geen afwezigheid."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(NU + timedelta(minutes=20))

    assert c.presence_state == "thuis"


def test_a_long_quiet_period_means_away(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(
        NU + timedelta(minutes=PRESENCE_ABSENCE_AFTER_MINUTES + 5)
    )

    assert c.presence_state == "weg"


def test_any_sensor_counts(make_coordinator, hass):
    """Beweging in de woonkamer telt net zo goed als in de gang."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.woonkamer", "on")

    c._update_presence(NU)

    assert c.presence_state == "thuis"


def test_the_threshold_is_generous():
    """Een korte drempel zou 's nachts elk uur "niemand thuis"
    melden."""
    assert PRESENCE_ABSENCE_AFTER_MINUTES >= 30


# --- het leren -------------------------------------------------------


def test_it_learns_per_half_hour_of_the_week(make_coordinator, hass):
    """Een week is de natuurlijke cyclus: werkdagen verschillen van het
    weekend, ochtend van avond."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")

    c._update_presence(NU)

    sleutel = f"{NU.weekday()}-0800"
    assert c.presence_week_profile[sleutel] == [1, 1]


def test_absence_is_learned_too(make_coordinator, hass):
    """Weten wanneer je NIET thuis bent is even bruikbaar."""
    c = _coordinator(make_coordinator, hass)
    c.last_motion_at = NU - timedelta(hours=3)

    c._update_presence(NU)

    sleutel = f"{NU.weekday()}-0800"
    assert c.presence_week_profile[sleutel] == [0, 1]


def test_the_overview_needs_enough_observations(make_coordinator, hass):
    """Twee weken zegt nog niets over een vast patroon."""
    c = _coordinator(make_coordinator, hass)
    c.presence_week_profile = {
        "0-0800": [2, PRESENCE_MIN_OBSERVATIONS - 1],
        "0-1800": [5, PRESENCE_MIN_OBSERVATIONS + 2],
    }

    profiel = c.get_presence_overview()["profiel"]

    assert "0-0800" not in profiel
    assert "0-1800" in profiel


def test_the_profile_stays_bounded(make_coordinator, hass):
    """Zonder begrenzing blijven oude gewoontes eeuwig meewegen."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")

    for minuut in range(0, 60 * 24 * 60, 30):
        c._update_presence(NU + timedelta(minutes=minuut))

    for aan, totaal in c.presence_week_profile.values():
        assert totaal <= 12, totaal


# --- zonder configuratie ---------------------------------------------


def test_without_sensors_it_says_what_to_do(make_coordinator, hass):
    """Buitensensoren zouden hier juist schade doen, dus het is een
    keuze - met uitleg waarom."""
    c = _coordinator(make_coordinator, hass, sensoren=[])

    overzicht = c.get_presence_overview()

    assert overzicht["beschikbaar"] is False
    assert "BINNEN" in overzicht["reden"]
    assert "voorbijgangers" in overzicht["reden"]


def test_without_sensors_no_state(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, sensoren=[])

    c._update_presence(NU)

    assert c.presence_state is None


# --- inbedding -------------------------------------------------------


def test_it_runs_every_tick():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "self._update_presence(now)" in bron


def test_it_is_in_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "presence_overview" in bron
    assert "presence_week_profile" in bron


def test_the_profile_survives_a_restart():
    import custom_components.energy_management_system.const as C

    bewaard = set()
    for naam in dir(C):
        if naam.startswith("PERSISTED_") and isinstance(getattr(C, naam), tuple):
            bewaard |= set(getattr(C, naam))

    assert "presence_week_profile" in bewaard


def test_the_config_field_allows_multiple():
    """Meerdere sensoren, want één ruimte dekt het huis niet."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "config_flow.py").read_text()
    start = bron.index("CONF_PRESENCE_MOTION_SENSORS,\n                default")

    assert "multiple=True" in bron[start : start + 400]


# --- v1.20.0: slapen is geen afwezigheid ----------------------------

from custom_components.energy_management_system.const import (  # noqa: E402
    CONF_PRESENCE_BEDTIME_SENSOR,
)

AVOND = datetime(2026, 8, 10, 22, 30, tzinfo=timezone.utc)


def _met_slaapsensor(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_PRESENCE_MOTION_SENSORS: [
                "binary_sensor.woonkamer",
                "binary_sensor.overloop",
            ],
            CONF_PRESENCE_BEDTIME_SENSOR: "binary_sensor.overloop",
        }
    )
    for naam in ("binary_sensor.woonkamer", "binary_sensor.overloop"):
        hass.states.set(naam, "off")
    return c


def _alleen(hass, actief=None):
    """Zet één sensor aan en de rest uit.

    v1.20.1: ook `binary_sensor.gang` meenemen. Die stond er niet in,
    waardoor tests die hem aanzetten stilzwijgend niets deden - de
    opstelling zette hem meteen weer uit.
    """
    for naam in (
        "binary_sensor.gang",
        "binary_sensor.woonkamer",
        "binary_sensor.overloop",
    ):
        hass.states.set(naam, "on" if naam == actief else "off")


def test_sleeping_is_not_absence(make_coordinator, hass):
    """Gemeld: "Als de overloop sensor als laatste beweging heeft
    gedetecteerd 's avonds/'s nachts zijn we wel thuis maar slapen we."

    Zonder dat kenmerk ziet stilte er hetzelfde uit, terwijl "niemand
    thuis" en "iedereen slaapt" tegengestelde situaties zijn: bij
    afwezigheid mag alles uit, bij slapen moet de nachtreserve juist
    kloppen.
    """
    c = _met_slaapsensor(make_coordinator, hass)
    _alleen(hass, "binary_sensor.overloop")
    c._update_presence(AVOND)
    _alleen(hass)

    c._update_presence(AVOND + timedelta(hours=6))

    assert c.presence_state == "slaapt"


def test_motion_downstairs_after_bedtime_means_awake(make_coordinator, hass):
    """De volgorde is het bewijs: bewoog er daarna nog iets beneden, dan
    zegt de SLAAPSENSOR niets meer.

    v1.30.0: de staat wordt dan alsnog "slaapt", maar via een andere
    regel - het nachtvenster. Gemeld: "Ik ging om 23:15 slapen, was
    snachts wel een tijdje wakker", waarna de tijdlijn de hele nacht
    "weg" gaf. Een huis loopt 's nachts niet vanzelf leeg.
    """
    c = _met_slaapsensor(make_coordinator, hass)
    _alleen(hass, "binary_sensor.overloop")
    c._update_presence(AVOND)
    _alleen(hass, "binary_sensor.woonkamer")
    c._update_presence(AVOND + timedelta(minutes=10))
    _alleen(hass)

    c._update_presence(AVOND + timedelta(hours=6))

    assert c._slaapt_waarschijnlijk(AVOND + timedelta(hours=6)) is False
    assert c.presence_state == "slaapt"


def test_the_landing_during_the_day_is_not_bedtime(make_coordinator, hass):
    """Overdag loop je er ook langs."""
    c = _met_slaapsensor(make_coordinator, hass)
    middag = AVOND.replace(hour=14)
    _alleen(hass, "binary_sensor.overloop")

    c._update_presence(middag)
    _alleen(hass)
    c._update_presence(middag + timedelta(hours=2))

    assert c.presence_state == "weg"


def test_sleeping_ends_after_a_long_time(make_coordinator, hass):
    """Na een etmaal stilte is het geen nacht meer maar afwezigheid."""
    c = _met_slaapsensor(make_coordinator, hass)
    _alleen(hass, "binary_sensor.overloop")
    c._update_presence(AVOND)
    _alleen(hass)

    c._update_presence(AVOND + timedelta(hours=20))

    assert c.presence_state == "weg"


def test_bedtimes_are_learned(make_coordinator, hass):
    """Wanneer je doorgaans naar bed gaat, is bruikbaar om op te
    plannen."""
    c = _met_slaapsensor(make_coordinator, hass)
    _alleen(hass, "binary_sensor.overloop")

    c._update_presence(AVOND)

    assert c.bedtime_history == ["22:30"]
    assert c.get_presence_overview()["typische_bedtijd"] == "22:30"


def test_without_a_bedtime_sensor_it_says_so(make_coordinator, hass):
    """Zonder die sensor telt een nacht als afwezigheid; dat hoort
    zichtbaar te zijn."""
    c = _coordinator(make_coordinator, hass)

    assert c.get_presence_overview()["slaapsensor_ingesteld"] is False


def test_the_bedtime_history_survives_a_restart():
    import custom_components.energy_management_system.const as C

    bewaard = set()
    for naam in dir(C):
        if naam.startswith("PERSISTED_") and isinstance(getattr(C, naam), tuple):
            bewaard |= set(getattr(C, naam))

    assert "bedtime_history" in bewaard


# --- v1.20.1: sneller, met bron, tv en vakantiemelding --------------

from custom_components.energy_management_system.const import (  # noqa: E402
    CONF_PRESENCE_TV_ENTITY,
    PRESENCE_ABSENCE_AFTER_MINUTES_FAST,
    PRESENCE_INTRUSION_COOLDOWN_MINUTES,
)

TV = "remote.samsung_qn85ba_55"


def _met_tv(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_PRESENCE_MOTION_SENSORS: SENSOREN,
            CONF_PRESENCE_TV_ENTITY: TV,
        }
    )
    for naam in SENSOREN:
        hass.states.set(naam, "off")
    hass.states.set(TV, "off")
    return c


# --- sneller ---------------------------------------------------------


def test_absence_is_seen_much_faster_with_a_tv(make_coordinator, hass):
    """Gemeld: "We zijn net 25 minuten namelijk niet thuis geweest" -
    terwijl het systeem "thuis" bleef melden.

    Dat klopte met de oude drempel: 25 minuten is korter dan 45. Die 45
    stond er om stilzitten op de bank niet als afwezigheid te tellen, en
    juist dat vangt de tv nu op.
    """
    c = _met_tv(make_coordinator, hass)

    assert c._afwezigheidsdrempel_minuten() == PRESENCE_ABSENCE_AFTER_MINUTES_FAST
    # v1.78.0: van 10 naar 20 minuten. Gemeld: "De aanwezigheid sensor
    # wijzigt te snel naar weg." Van de 24 weg-blokken in de eigen
    # tijdlijn duurden er acht precies vijf tot zeven minuten - geflikker,
    # geen vertrek.
    assert PRESENCE_ABSENCE_AFTER_MINUTES_FAST <= 30


def test_a_short_silence_is_no_longer_absence(make_coordinator, hass):
    c = _met_tv(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(NU + timedelta(minutes=12))

    # v1.78.0: twaalf minuten stilte is geen vertrek meer. In de eigen
    # tijdlijn leverde de drempel van tien minuten acht valse
    # weg-blokken van vijf tot zeven minuten op.
    assert c.presence_state == "thuis"

    c._update_presence(NU + timedelta(minutes=25))

    assert c.presence_state == "weg"


def test_without_a_tv_the_threshold_stays_generous(make_coordinator, hass):
    """Zonder tv zou tien minuten 's avonds telkens "niemand thuis"
    melden."""
    c = _coordinator(make_coordinator, hass)

    assert c._afwezigheidsdrempel_minuten() == PRESENCE_ABSENCE_AFTER_MINUTES


# --- de televisie ----------------------------------------------------


def test_the_tv_counts_as_present(make_coordinator, hass):
    c = _met_tv(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")
    hass.states.set(TV, "on")

    c._update_presence(NU + timedelta(minutes=40))

    assert c.presence_state == "thuis"


def test_a_playing_media_player_also_counts(make_coordinator, hass):
    """Een media_player meldt "playing", geen "on"."""
    c = _met_tv(make_coordinator, hass)
    hass.states.set(TV, "playing")

    assert c._tv_staat_aan() is True


# --- welke sensor zag als laatste beweging ---------------------------


def test_every_moving_sensor_is_recorded(make_coordinator, hass):
    """Gevraagd: "Ook wil ik een tabel met welke sensor als laatst
    gedetecteerd heeft."

    Niet stoppen bij de eerste treffer, anders mist de tabel de rest.
    """
    c = _met_tv(make_coordinator, hass)
    for naam in SENSOREN:
        hass.states.set(naam, "on")

    c._update_presence(NU)

    assert set(c.presence_last_seen) == set(SENSOREN)


def test_the_table_is_sorted_most_recent_first(make_coordinator, hass):
    c = _met_tv(make_coordinator, hass)
    _alleen(hass, "binary_sensor.woonkamer")
    c._update_presence(NU)
    hass.states.set("binary_sensor.woonkamer", "off")
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU + timedelta(minutes=5))

    tabel = c.get_presence_overview()["laatst_gezien"]

    assert tabel[0]["naam"].endswith("gang") or "gang" in tabel[0]["naam"]


def test_a_missing_name_falls_back_to_the_entity_id(make_coordinator, hass):
    """Niet elke toestand heeft een naam; de entity_id is dan nog altijd
    bruikbaarder dan een foutmelding."""
    c = _met_tv(make_coordinator, hass)

    assert c._entiteitsnaam("binary_sensor.bestaat_niet") == (
        "binary_sensor.bestaat_niet"
    )


# --- vakantiestand ---------------------------------------------------


def test_motion_during_vacation_sends_an_alert(make_coordinator, hass):
    c = _met_tv(make_coordinator, hass)
    c.vacation_mode = True
    _alleen(hass, "binary_sensor.gang")

    c._update_presence(NU)

    assert c._last_intrusion_alert_at == NU


def test_no_alert_without_vacation_mode(make_coordinator, hass):
    c = _met_tv(make_coordinator, hass)
    c.vacation_mode = False
    _alleen(hass, "binary_sensor.gang")

    c._update_presence(NU)

    assert c._last_intrusion_alert_at is None


def test_the_alert_is_rate_limited(make_coordinator, hass):
    """Zonder rem levert één passage door een gang tientallen berichten
    op, en dan zet je de melding uit - precies wanneer je hem wilt
    hebben."""
    c = _met_tv(make_coordinator, hass)
    c.vacation_mode = True
    _alleen(hass, "binary_sensor.gang")
    c._update_presence(NU)

    c._update_presence(NU + timedelta(minutes=2))

    assert c._last_intrusion_alert_at == NU


def test_a_later_alert_is_sent_again(make_coordinator, hass):
    c = _met_tv(make_coordinator, hass)
    c.vacation_mode = True
    _alleen(hass, "binary_sensor.gang")
    c._update_presence(NU)
    later = NU + timedelta(minutes=PRESENCE_INTRUSION_COOLDOWN_MINUTES + 1)

    c._update_presence(later)

    assert c._last_intrusion_alert_at == later


def test_the_alert_has_a_switch():
    """Elke melding hoort uitschakelbaar te zijn."""
    from custom_components.energy_management_system.const import (
        NOTIFICATION_TYPES,
    )

    soorten = {k: (aan, demping) for k, _, _, aan, demping in NOTIFICATION_TYPES}

    assert "vakantie_beweging" in soorten
    assert soorten["vakantie_beweging"][1] == PRESENCE_INTRUSION_COOLDOWN_MINUTES


# --- v1.26.0: de tijdlijn --------------------------------------------


def _op(c, hass, moment, beweging=True):
    """Eén tick, met of zonder beweging."""
    hass.states.set("binary_sensor.gang", "on" if beweging else "off")
    c._update_presence(moment)


def _tijd(nu):
    """Zet dt_util.now vast, anders loopt de duur van het laatste blok
    door tot de echte klok."""
    import custom_components.energy_management_system.coordinator as m

    m.dt_util.now = lambda: nu


def test_a_transition_lands_in_the_timeline(make_coordinator, hass):
    """Gevraagd: "Tevens in dit overzicht een 'time table' Thuis, weg
    slapen of iets dergelijks zodat ik achteraf kan controleren of het
    klopt."
    """
    c = _coordinator(make_coordinator, hass)

    _op(c, hass, NU)
    _op(c, hass, NU + timedelta(minutes=PRESENCE_ABSENCE_AFTER_MINUTES + 10), False)

    staten = [b["staat"] for b in c.presence_timeline]
    assert staten == ["thuis", "weg"]


def test_the_timeline_only_records_changes(make_coordinator, hass):
    """Elke tick wegschrijven levert 288 regels per dag op die allemaal
    hetzelfde zeggen."""
    c = _coordinator(make_coordinator, hass)

    for minuut in range(0, 40, 5):
        _op(c, hass, NU + timedelta(minutes=minuut))

    assert len(c.presence_timeline) == 1


def test_the_timeline_says_why(make_coordinator, hass):
    """Zonder de reden valt er niets te controleren: "weg om 14:20" zegt
    niets, "weg, 45 min na de laatste beweging (gang)" wel."""
    c = _coordinator(make_coordinator, hass)

    _op(c, hass, NU)
    _op(c, hass, NU + timedelta(minutes=PRESENCE_ABSENCE_AFTER_MINUTES + 10), False)

    assert "beweging" in c.presence_timeline[0]["aanleiding"]
    assert "zonder beweging" in c.presence_timeline[1]["aanleiding"]


def test_a_flicker_is_merged_away(make_coordinator, hass):
    """Eén beweging midden in de nacht zou anders "slaapt - thuis -
    slaapt" opleveren, en dan is de tabel onleesbaar terwijl er niets
    gebeurd is."""
    c = _coordinator(make_coordinator, hass)
    c.presence_timeline = [
        {"van": (NU - timedelta(hours=3)).isoformat(), "staat": "weg", "aanleiding": ""},
        {"van": (NU - timedelta(minutes=2)).isoformat(), "staat": "thuis", "aanleiding": ""},
    ]
    c.presence_state = "thuis"

    # Terug naar "weg" binnen twee minuten: dat blokje hoort te
    # verdwijnen, niet als derde regel te blijven staan.
    c.presence_state = "weg"
    c._registreer_aanwezigheidsovergang(NU, "thuis")

    assert [b["staat"] for b in c.presence_timeline] == ["weg"]


def test_a_real_block_is_kept(make_coordinator, hass):
    """De samenvoegregel mag geen echte blokken opeten."""
    c = _coordinator(make_coordinator, hass)
    c.presence_timeline = [
        {"van": (NU - timedelta(hours=3)).isoformat(), "staat": "weg", "aanleiding": ""},
        {"van": (NU - timedelta(hours=1)).isoformat(), "staat": "thuis", "aanleiding": ""},
    ]
    c.presence_state = "weg"

    c._registreer_aanwezigheidsovergang(NU, "thuis")

    assert [b["staat"] for b in c.presence_timeline] == ["weg", "thuis", "weg"]


def test_the_table_reads_newest_first_and_computes_duration(
    make_coordinator, hass
):
    c = _coordinator(make_coordinator, hass)
    c.presence_timeline = [
        {"van": (NU - timedelta(hours=2)).isoformat(), "staat": "weg", "aanleiding": "x"},
        {"van": (NU - timedelta(minutes=30)).isoformat(), "staat": "thuis", "aanleiding": "y"},
    ]
    _tijd(NU)

    regels = c.get_presence_timeline()

    assert [r["staat"] for r in regels] == ["thuis", "weg"]
    # Het bovenste blok loopt nog door; de duur ervan is niet bewaard
    # maar berekend.
    assert regels[0]["tot"] == "nu"
    assert regels[0]["duur_minuten"] == 30
    assert regels[1]["duur_minuten"] == 90


def test_the_day_totals_split_at_midnight(make_coordinator, hass):
    """Anders schrijft een nacht slapen zeven uur op de verkeerde dag."""
    c = _coordinator(make_coordinator, hass)
    avond = NU.replace(hour=21, minute=0)
    c.presence_timeline = [
        {"van": avond.isoformat(), "staat": "slaapt", "aanleiding": ""},
        {"van": (avond + timedelta(hours=9)).isoformat(), "staat": "thuis", "aanleiding": ""},
    ]
    _tijd(avond + timedelta(hours=10))

    totalen = {r["dag"]: r for r in c.get_presence_day_totals()}

    assert len(totalen) == 2
    vandaag = totalen[avond.strftime("%Y-%m-%d")]
    morgen = totalen[(avond + timedelta(days=1)).strftime("%Y-%m-%d")]
    assert vandaag["slaapt_uur"] == 3.0
    assert morgen["slaapt_uur"] == 6.0
    assert morgen["thuis_uur"] == 1.0


def test_the_timeline_is_bounded(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        PRESENCE_TIMELINE_LENGTH,
    )

    c = _coordinator(make_coordinator, hass)
    for i in range(PRESENCE_TIMELINE_LENGTH + 20):
        c.presence_state = "thuis" if i % 2 else "weg"
        c._registreer_aanwezigheidsovergang(
            NU + timedelta(hours=i), "weg" if i % 2 else "thuis"
        )

    assert len(c.presence_timeline) == PRESENCE_TIMELINE_LENGTH


def test_the_timeline_survives_a_restart():
    """Een tabel die na elke herstart leeg is, valt niet achteraf te
    controleren - en dat is precies waarvoor hij gevraagd werd."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "presence_timeline" in PERSISTED_PLAIN_FIELDS


def test_the_overview_carries_the_timeline(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _op(c, hass, NU)
    _tijd(NU + timedelta(minutes=5))

    overzicht = c.get_presence_overview()

    assert overzicht["tijdlijn"]
    assert overzicht["tijdlijn_totaal"] == 1


# --- v1.30.0: de nacht, en niets kwijtraken bij een herstart ---------


def test_going_to_bed_via_the_hall_is_still_sleeping(make_coordinator, hass):
    """Gemeld: "Ik ging om 23:15 slapen, was snachts wel een tijdje
    wakker" - en de tijdlijn zei van 23:15 tot de ochtend "weg", met
    "laatst: Gang Beweging" als reden.

    Loop je via de gang naar bed, dan is de gang de laatste beweging en
    zwijgt de slaapsensor de rest van de nacht.
    """
    c = _coordinator(make_coordinator, hass)
    nacht = NU.replace(hour=23, minute=15)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(nacht)
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(nacht + timedelta(hours=2))

    assert c.presence_state == "slaapt"


def test_an_empty_house_at_night_stays_away(make_coordinator, hass):
    """De regel geldt alleen als er net nog iemand thuis was. Wie om
    18:00 vertrokken is, ligt om 01:00 niet ineens in bed."""
    c = _coordinator(make_coordinator, hass)
    avond = NU.replace(hour=18, minute=0)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(avond)
    hass.states.set("binary_sensor.gang", "off")
    c._update_presence(avond + timedelta(hours=2))
    assert c.presence_state == "weg"

    c._update_presence(avond + timedelta(hours=7))

    assert c.presence_state == "weg"


def test_the_evening_before_the_window_is_unchanged(make_coordinator, hass):
    """Om 20:00 stil worden betekent nog gewoon weg."""
    c = _coordinator(make_coordinator, hass)
    avond = NU.replace(hour=19, minute=0)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(avond)
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(avond + timedelta(hours=1))

    assert c.presence_state == "weg"


def test_the_timeline_never_repeats_a_state(make_coordinator, hass):
    """Gemeld met screenshot: vijf "weg"-regels achter elkaar. Een
    tijdlijn van blokken hoort nooit twee gelijke staten naast elkaar te
    hebben."""
    c = _coordinator(make_coordinator, hass)
    c.presence_timeline = [
        {"van": (NU - timedelta(hours=2)).isoformat(), "staat": "weg", "aanleiding": ""}
    ]
    c.presence_state = "weg"

    c._registreer_aanwezigheidsovergang(NU, "onbekend")

    assert len(c.presence_timeline) == 1


def test_a_missing_reading_does_not_break_the_block(make_coordinator, hass):
    """Viel er een sensor weg, dan hoort het lopende blok door te lopen
    in plaats van te eindigen."""
    c = _coordinator(make_coordinator, hass)
    c.presence_timeline = [
        {"van": (NU - timedelta(hours=2)).isoformat(), "staat": "slaapt", "aanleiding": ""}
    ]
    c.presence_state = "onbekend"

    c._registreer_aanwezigheidsovergang(NU, "slaapt")

    assert [b["staat"] for b in c.presence_timeline] == ["slaapt"]


def test_everything_the_presence_logic_learns_survives_a_restart():
    """Gevraagd: "Let op alle gecreeerde data dient na een herstart niet
    verloren te gaan."

    `last_bedtime_motion_at` ontbrak, en dat is precies waarom de
    slaapherkenning na een herstart niets meer kon zeggen: wie al in bed
    ligt, loopt niet opnieuw langs die sensor.
    """
    from custom_components.energy_management_system.const import (
        PERSISTED_DATETIME_FIELDS,
        PERSISTED_PLAIN_FIELDS,
    )

    for veld in (
        "presence_timeline",
        "presence_state",
        "presence_week_profile",
        "presence_last_seen",
        "bedtime_history",
        "quarter_plan_first_seen",
    ):
        assert veld in PERSISTED_PLAIN_FIELDS, veld
    for veld in ("last_motion_at", "last_bedtime_motion_at"):
        assert veld in PERSISTED_DATETIME_FIELDS, veld


# --- v1.31.1: de tabel loopt niet uit de pas -------------------------


def test_the_timeline_catches_up_with_the_state(make_coordinator, hass):
    """Gevonden in de export van 11 augustus 08:38: de tijdlijn stond op
    "weg sinds 08:21" terwijl de staat "thuis" was en er 2,6 minuten
    eerder nog beweging was geweest.

    Zolang alleen een WISSEL werd vastgelegd, was elke gemiste wissel
    blijvend - er kwam nooit meer een gelegenheid om hem goed te zetten.
    """
    c = _coordinator(make_coordinator, hass)
    c.presence_timeline = [
        {"van": (NU - timedelta(hours=1)).isoformat(), "staat": "weg", "aanleiding": ""}
    ]
    # De staat staat al op thuis, maar dat is nooit in de tabel beland.
    c.presence_state = "thuis"
    hass.states.set("binary_sensor.gang", "on")

    c._update_presence(NU)

    assert [b["staat"] for b in c.presence_timeline] == ["weg", "thuis"]


def test_repeating_the_same_state_adds_nothing(make_coordinator, hass):
    """Elke tick aanbieden mag geen regels opleveren."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")

    for minuut in range(0, 30, 5):
        c._update_presence(NU + timedelta(minutes=minuut))

    assert len(c.presence_timeline) == 1


# --- v1.36.0: lampen als signaal -------------------------------------


def _met_lampen(make_coordinator, hass, lampen=("light.woonkamer",)):
    from custom_components.energy_management_system.const import (
        CONF_PRESENCE_LIGHT_ENTITIES,
    )

    c = _coordinator(make_coordinator, hass)
    c.config[CONF_PRESENCE_LIGHT_ENTITIES] = list(lampen)
    for lamp in lampen:
        hass.states.set(lamp, "off")
    return c


def test_a_burning_light_counts_as_home(make_coordinator, hass):
    """Gevraagd: "Voor aanwezigheids detectie, kan ook nog gekeken naar
    lampen of heb ik dat niet goed?"

    Klopt - dat gebeurde nog niet, terwijl de systeemscan de lampen al
    wel verzamelde. Een brandende lamp zegt niets over beweging, maar
    wel dat er iemand is.
    """
    c = _met_lampen(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")
    hass.states.set("light.woonkamer", "on")

    c._update_presence(NU + timedelta(hours=3))

    assert c.presence_state == "thuis"


def test_without_a_light_it_would_have_been_away(make_coordinator, hass):
    """Zonder dat signaal was dezelfde stilte afwezigheid geweest - de
    test hierboven toetst anders niets."""
    c = _met_lampen(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")

    c._update_presence(NU + timedelta(hours=3))

    assert c.presence_state == "weg"


def test_lights_do_not_count_during_the_holiday_mode(make_coordinator, hass):
    """De eigen automatisering zet tijdens de vakantiestand juist lampen
    aan om aanwezigheid na te bootsen. Die als bewijs van aanwezigheid
    nemen is een cirkelredenering - en het zou de inbraakmelding smoren,
    precies wanneer die nodig is.
    """
    c = _met_lampen(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")
    hass.states.set("light.woonkamer", "on")
    c.vacation_mode = True

    c._update_presence(NU + timedelta(hours=3))

    assert c.presence_state == "weg"


def test_the_timeline_says_which_light(make_coordinator, hass):
    """Zonder te noemen welke lamp valt niet na te gaan of het klopt -
    een vergeten zolderlamp verklaart een verkeerde staat."""
    c = _met_lampen(make_coordinator, hass)
    hass.states.set("binary_sensor.gang", "on")
    c._update_presence(NU)
    hass.states.set("binary_sensor.gang", "off")
    c._update_presence(NU + timedelta(hours=3))
    hass.states.set("light.woonkamer", "on")

    c._update_presence(NU + timedelta(hours=4))

    assert "licht aan" in c.presence_timeline[-1]["aanleiding"]


def test_no_lights_configured_changes_nothing(make_coordinator, hass):
    """Wie geen lampen kiest, mag er niets van merken."""
    c = _coordinator(make_coordinator, hass)

    assert c._brandend_licht() is None


# --- v1.78.0: de drempel is instelbaar -------------------------------


def test_the_threshold_can_be_set_per_house(make_coordinator, hass):
    """Gemeld: "De aanwezigheid sensor wijzigt te snel naar weg,
    misschien de tijd voor analyse verlengen?"

    Hoe lang stilte normaal is hangt af van hoeveel sensoren er hangen en
    hoe het huis loopt - dat valt niet met één getal voor iedereen te
    vangen.
    """
    from custom_components.energy_management_system.const import (
        CONF_PRESENCE_ABSENCE_MINUTES,
    )

    c = _met_tv(make_coordinator, hass)
    c.config[CONF_PRESENCE_ABSENCE_MINUTES] = 45

    assert c._afwezigheidsdrempel_minuten() == 45


def test_without_a_setting_the_default_applies(make_coordinator, hass):
    c = _met_tv(make_coordinator, hass)

    assert c._afwezigheidsdrempel_minuten() == PRESENCE_ABSENCE_AFTER_MINUTES_FAST


def test_the_flicker_from_the_real_timeline_is_gone(make_coordinator, hass):
    """De acht valse blokken uit de eigen tijdlijn duurden vijf tot zeven
    minuten. Die horen geen van alle nog een toestandswissel op te
    leveren."""
    c = _met_tv(make_coordinator, hass)

    for minuten in (5, 6, 7):
        c.presence_state = "thuis"
        # `last_motion_at` is een datetime in het geheugen; de ISO-tekst
        # is alleen het opslagformaat.
        c.last_motion_at = NU
        c._update_presence(NU + timedelta(minutes=minuten))

        assert c.presence_state == "thuis", f"{minuten} min gaf een wissel"
