"""Een wc-bezoek knipt de nacht in stukken (v3.96.0).

Gemeld met de aanwezigheidstijdlijn: "Normaal slapen we op weekdagen van
ongeveer 23:00 tot 06:00 echter gaat er wel eens iemand snachts naar de
wc, hoe kunnen we dit borgen?"

Uit de tijdlijn, drie nachten:

    27-08  02:49-06:16  slaapt   06:16-06:48  thuis (32 min)
    28-08  01:33-02:27  slaapt   02:27-02:59  thuis (32 min)
    30-08  00:41-03:04  slaapt   03:04-03:44  thuis (40 min)

Die blokken van 30 tot 40 minuten "thuis" zijn geen wakker liggen. Het
zijn twee minuten lopen naar de wc, plus de dertig minuten stilte die
daarna nodig zijn voordat de staat terugvalt. De volgorde in
`_update_presence` is: eerst "was er recent beweging?" -> thuis, en pas
daarna de slaapregels. Elke beweging beeindigt de nacht dus meteen.

En hetzelfde blijkt aan de andere kant:

    27-08  07:00-08:01  weg (62 min)
    29-08  07:00-07:53  weg (53 min)
    30-08  07:00-07:37  weg (38 min)

Drie keer exact 07:00. Dat is geen sensor maar
PRESENCE_NIGHT_END_HOUR: op dat tijdstip vervalt de nachtregel, en dan
valt een stilte van dertig minuten door naar "weg" - terwijl er iemand
onder de douche staat. De klok trekt daar een conclusie waar het bewijs
ontbreekt.
"""
from datetime import datetime, timedelta, timezone

import pytest

NACHT = datetime(2026, 8, 31, 3, 0, tzinfo=timezone.utc)
OCHTEND = datetime(2026, 8, 31, 7, 5, tzinfo=timezone.utc)


def _slapend(c, now, beweging_geleden_min, slaapsensor_geleden_min=None):
    c.presence_state = "slaapt"
    c.last_motion_at = now - timedelta(minutes=beweging_geleden_min)
    c.last_bedtime_motion_at = now - timedelta(
        minutes=slaapsensor_geleden_min
        if slaapsensor_geleden_min is not None
        else beweging_geleden_min
    )
    c._tv_staat_aan = lambda: False
    c._stromend_water = lambda: False
    c._brandend_licht = lambda: None
    c.config = dict(c.config or {})
    c.config["presence_motion_sensor_entities"] = ["binary_sensor.gang"]


def _bepaal(c, now):
    c._update_presence(now)
    return c.presence_state


# --- 1. de nacht overleeft een wc-bezoek ------------------------------


def test_kort_lopen_beeindigt_de_nacht_niet(make_coordinator, hass):
    """Het geval van 30 augustus 03:04: gang, twee minuten, weer stil."""
    c = make_coordinator({})
    _slapend(c, NACHT, beweging_geleden_min=2, slaapsensor_geleden_min=140)

    assert _bepaal(c, NACHT) == "slaapt"


def test_aanhoudende_beweging_beeindigt_de_nacht_wel(make_coordinator, hass):
    """Wie opstaat, loopt langer dan een wc-bezoek. Anders zou de

    tijdlijn een ochtend als nacht boeken.
    """
    c = make_coordinator({})
    _slapend(c, NACHT, beweging_geleden_min=0, slaapsensor_geleden_min=200)
    # Onderbreking duurt al langer dan de drempel.
    c._nachtrust_onderbroken_sinds = NACHT - timedelta(minutes=25)

    assert _bepaal(c, NACHT) == "thuis"


def test_de_onderbreking_wordt_vastgelegd(make_coordinator, hass):
    """Zonder tijdstempel is niet te zien hoe lang de onderbreking al

    duurt, en dan is elke ronde weer de eerste.
    """
    c = make_coordinator({})
    c._nachtrust_onderbroken_sinds = None
    _slapend(c, NACHT, beweging_geleden_min=1, slaapsensor_geleden_min=140)

    _bepaal(c, NACHT)

    assert c._nachtrust_onderbroken_sinds is not None


def test_na_de_onderbreking_begint_de_teller_opnieuw(make_coordinator, hass):
    """Twee wc-bezoeken in een nacht mogen niet bij elkaar optellen tot

    een wakker geworden huishouden.
    """
    c = make_coordinator({})
    _slapend(c, NACHT, beweging_geleden_min=1, slaapsensor_geleden_min=140)
    c._nachtrust_onderbroken_sinds = NACHT - timedelta(minutes=3)
    _bepaal(c, NACHT)

    later = NACHT + timedelta(minutes=20)
    _slapend(c, later, beweging_geleden_min=60, slaapsensor_geleden_min=60)
    assert _bepaal(c, later) == "slaapt"
    assert c._nachtrust_onderbroken_sinds is None


def test_overdag_geldt_de_regel_niet(make_coordinator, hass):
    """Buiten de nacht is beweging gewoon beweging."""
    c = make_coordinator({})
    middag = datetime(2026, 8, 31, 14, 0, tzinfo=timezone.utc)
    _slapend(c, middag, beweging_geleden_min=1, slaapsensor_geleden_min=600)

    assert _bepaal(c, middag) == "thuis"


# --- 2. de ochtendgrens trekt geen conclusie ---------------------------


def test_zeven_uur_maakt_van_slapen_geen_weg(make_coordinator, hass):
    """Drie keer exact 07:00 in de tijdlijn. Dat is de nachtgrens, geen

    sensor. Een uur stilte om zeven uur is een douche en een ontbijt,
    geen leeg huis.
    """
    c = make_coordinator({})
    _slapend(c, OCHTEND, beweging_geleden_min=60, slaapsensor_geleden_min=90)

    assert _bepaal(c, OCHTEND) == "slaapt"


def test_een_lange_stilte_na_de_nacht_is_wel_weg(make_coordinator, hass):
    """De regel mag geen slot op de deur worden: wie na het opstaan

    vertrekt, hoort ook als weg te tellen.
    """
    c = make_coordinator({})
    _slapend(c, OCHTEND, beweging_geleden_min=180, slaapsensor_geleden_min=240)

    assert _bepaal(c, OCHTEND) == "weg"


def test_vanuit_weg_verandert_er_niets(make_coordinator, hass):
    """De ruimere ochtenddrempel geldt alleen na een nacht. Wie al weg

    was, blijft weg.
    """
    c = make_coordinator({})
    _slapend(c, OCHTEND, beweging_geleden_min=60, slaapsensor_geleden_min=90)
    c.presence_state = "weg"

    assert _bepaal(c, OCHTEND) == "weg"
