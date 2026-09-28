"""De zoncorrectie per UTC-uur (v5.24).

Gevraagd: "wordt in de PV-verwachting ook de hoogte van de zon
meegenomen? Seizoenen zeg maar." Solcast rekent zelf met de stand van de
zon. De geleerde correctie erbovenop hing aan het KLOKUUR - en na de
omschakeling naar wintertijd (zondag 25 oktober 2026) staat de zon om
14:00 waar hij eerst om 15:00 stond. Een schaduw die aan 15:00 gekoppeld
was, viel dan een uur vroeger dan de correctie dacht.
"""
from datetime import datetime, timedelta, timezone

import pytest

import custom_components.energy_management_system.coordinator as coord

ZOMERTIJD = timezone(timedelta(hours=2))
WINTERTIJD = timezone(timedelta(hours=1))


@pytest.fixture
def klok(monkeypatch):
    """Zet 'nu' in een bepaalde tijdzone."""
    def zet(tz):
        moment = datetime(2026, 9, 28, 12, 0, tzinfo=tz)
        monkeypatch.setattr(coord.dt_util, "now", lambda: moment)
    return zet


def test_dezelfde_zon_dezelfde_sleutel_voor_en_na_de_omschakeling(make_coordinator, hass):
    """15:00 zomertijd en 14:00 wintertijd zijn allebei 13:00 UTC - dezelfde
    stand van de zon, dus dezelfde correctie."""
    c = make_coordinator({})

    zomer = c._utc_uur(datetime(2026, 10, 24, 15, 0, tzinfo=ZOMERTIJD))
    winter = c._utc_uur(datetime(2026, 10, 26, 14, 0, tzinfo=WINTERTIJD))

    assert zomer == winter == 13


def test_de_verwachting_gebruikt_de_utc_sleutel(make_coordinator, hass):
    """Een correctie geleerd onder 13:00 UTC hoort bij 14:00 in de winter."""
    c = make_coordinator({})
    c.pv_hourly_bias_history = {13: [0.5] * 10}

    geleerd = c.learned_pv_hourly_ratio(
        c._utc_uur(datetime(2026, 10, 26, 14, 0, tzinfo=WINTERTIJD))
    )

    assert geleerd == 0.5


def test_oude_opslag_wordt_eenmalig_omgezet(make_coordinator, hass, klok):
    """Opslag zonder kenmerk heeft klokuren (zomertijd, +2)."""
    klok(ZOMERTIJD)
    c = make_coordinator({})
    c.pv_hourly_bias_history = {15: [0.5], 9: [1.1]}

    c._migreer_pv_uurbias_naar_utc({})

    assert c.pv_hourly_bias_history == {13: [0.5], 7: [1.1]}
    assert c.pv_uurbias_in_utc is True


def test_al_omgezette_opslag_blijft_staan(make_coordinator, hass, klok):
    klok(ZOMERTIJD)
    c = make_coordinator({})
    c.pv_hourly_bias_history = {13: [0.5]}

    c._migreer_pv_uurbias_naar_utc({"pv_uurbias_in_utc": True})

    assert c.pv_hourly_bias_history == {13: [0.5]}


def test_een_verse_installatie_begint_in_utc(make_coordinator, hass):
    c = make_coordinator({})
    c.pv_hourly_bias_history = {}

    c._migreer_pv_uurbias_naar_utc({})

    assert c.pv_uurbias_in_utc is True


def test_twee_keer_omzetten_verschuift_niet_twee_keer(make_coordinator, hass, klok):
    """Het kenmerk voorkomt dat een tweede herstart nog eens verschuift."""
    klok(ZOMERTIJD)
    c = make_coordinator({})
    c.pv_hourly_bias_history = {15: [0.5]}

    c._migreer_pv_uurbias_naar_utc({})
    c._migreer_pv_uurbias_naar_utc({"pv_uurbias_in_utc": c.pv_uurbias_in_utc})

    assert c.pv_hourly_bias_history == {13: [0.5]}


def test_de_export_toont_klokuren(make_coordinator, hass, klok):
    """Opgeslagen per UTC-uur, getoond per klokuur - daar lees jij ze."""
    klok(ZOMERTIJD)
    c = make_coordinator({})
    c.pv_hourly_bias_history = {13: [0.5] * 10}

    assert c.learned_pv_hourly_ratio(c._utc_uur_van_lokaal(15)) == 0.5
