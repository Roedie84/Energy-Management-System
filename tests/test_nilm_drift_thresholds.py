"""Ondergrens voor drift-detectie (v1.12.3).

Uit een export: vijf van de 38 apparaten stonden als "mogelijk defect",
waaronder een televisie met referentie 0,79 W (drift -24%) en een
diepvries met 0,85 W (-15%). Dat komt neer op 0,19 respectievelijk 0,13
watt verschil.

Een procentuele drempel is bij zulke kleine vermogens betekenisloos:
meetruis van een tiende watt is al vijftien procent. Vijf meldingen
waarvan er drie over tienden van watts gaan, leert je ze te negeren - en
dan mis je de koelkast die echt stukgaat.
"""
from custom_components.energy_management_system.const import (
    NILM_DRIFT_MIN_ABSOLUTE_W,
    NILM_DRIFT_MIN_REFERENCE_W,
)


def _apparaat(referentie, dagen):
    return {
        "daily_avg_history": list(dagen),
        "reference_avg_w": referentie,
        "cusum_accumulator": 0.0,
        "anomaly_detected": False,
        "friendly_name": "Testapparaat",
        "_normal_streak_days": 0,
    }


def _laat_driften(coordinator, apparaat, waarde, dagen=8):
    coordinator.nilm_confirmed_devices["sensor.test"] = apparaat
    for _ in range(dagen):
        coordinator._finalize_nilm_device_day("sensor.test", apparaat, waarde)
    return apparaat


# --- de gerapporteerde valse alarmen ---------------------------------


def test_a_tiny_device_does_not_trigger(make_coordinator, hass):
    """Televisie: 0,79 W referentie, 0,60 W nu. Dat is 0,19 watt."""
    c = make_coordinator({})
    apparaat = _apparaat(0.79, [0.79] * 10)

    _laat_driften(c, apparaat, 0.60)

    assert apparaat["anomaly_detected"] is False


def test_a_small_percentage_on_a_small_device_does_not_trigger(
    make_coordinator, hass
):
    """IPTV: +14,9% klinkt fors, maar is 0,37 watt."""
    c = make_coordinator({})
    apparaat = _apparaat(2.49, [2.49] * 10)

    _laat_driften(c, apparaat, 2.86)

    assert apparaat["anomaly_detected"] is False


# --- echte defecten blijven melden -----------------------------------


def test_a_real_appliance_still_triggers(make_coordinator, hass):
    """De koelkast die echt meer gaat verbruiken - daar is dit voor."""
    c = make_coordinator({})
    apparaat = _apparaat(80.0, [80.0] * 10)

    _laat_driften(c, apparaat, 110.0)

    assert apparaat["anomaly_detected"] is True


def test_a_large_jump_on_a_modest_device_triggers(make_coordinator, hass):
    """Koelkast schuur: 8,3 W naar 67,7 W. Klein apparaat, maar het
    verschil van 59 watt is onmiskenbaar."""
    c = make_coordinator({})
    apparaat = _apparaat(8.30, [8.30] * 10)

    _laat_driften(c, apparaat, 67.7)

    assert apparaat["anomaly_detected"] is True


# --- beide voorwaarden zijn nodig ------------------------------------


def test_a_big_device_with_a_small_change_stays_quiet(
    make_coordinator, hass
):
    """Een apparaat van 200 W dat 2 watt meer trekt, is geen beginnend
    defect."""
    c = make_coordinator({})
    apparaat = _apparaat(200.0, [200.0] * 10)

    _laat_driften(c, apparaat, 202.0)

    assert apparaat["anomaly_detected"] is False


def test_both_thresholds_are_documented():
    """Wie deze grenzen aanpast moet weten waar ze vandaan komen: het
    verschil moet zichtbaar zijn op een energienota, niet in de
    meetruis."""
    assert NILM_DRIFT_MIN_REFERENCE_W >= 5.0
    assert NILM_DRIFT_MIN_ABSOLUTE_W >= 5.0


def test_the_thresholds_reduce_the_reported_devices(make_coordinator, hass):
    """De kern: van vijf meldingen naar één die ertoe doet."""
    c = make_coordinator({})
    echt = [
        (0.79, 0.60),   # televisie
        (0.85, 0.72),   # diepvries
        (2.49, 2.86),   # IPTV
        (2.84, 4.17),   # oplader tablet
        (8.30, 67.7),   # koelkast schuur
    ]
    gemeld = 0
    for i, (ref, nu) in enumerate(echt):
        apparaat = _apparaat(ref, [ref] * 10)
        c.nilm_confirmed_devices = {}
        _laat_driften(c, apparaat, nu)
        if apparaat["anomaly_detected"]:
            gemeld += 1

    assert gemeld == 1
