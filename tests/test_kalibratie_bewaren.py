"""De kalibratiestand na een herstart (v3.98.0).

Gemeld met een schermafdruk van de knoppenkaart: "kalibratie wordt
gereset na herstart", bij een schakelaar die "9 minuten geleden" als
onderregel toont terwijl de integratie negen minuten eerder startte.

Twee dingen, en ze staan los van elkaar.

1. De kaart toont `last-changed`. Bij een herstart wordt de entiteit
   opnieuw aangemaakt en is dat het startmoment - dat getal zegt dus
   niets over de kalibratie. Er staat nu `kalibratie_sinds` naast, dat
   wél bijhoudt wanneer de stand is aangezet.

2. Een handmatige schakeling plande een opslag over dertig seconden.
   Die vertraging is terecht voor de tientallen velden die elke ronde
   veranderen, maar een bewuste knopdruk hoort daar niet in mee te
   liften: gaat HA binnen die dertig seconden onderuit, dan is de stand
   weg. `KalibratieSwitch` is bovendien de enige schakelaar die zijn
   stand NIET uit de entiteit terugzet - sinds v3.42.1 is de opslag
   daar leidend, juist om twee bronnen te vermijden. Dan moet die
   opslag ook meteen kloppen.
"""
import asyncio
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc)


class _Opslag:
    """Telt wat er vertraagd en wat er direct wordt weggeschreven."""

    def __init__(self):
        self.vertraagd = 0
        self.direct = 0


@pytest.fixture
def opslag(make_coordinator):
    return _Opslag()


def _volg(c, opslag):
    c.schedule_persisted_state_save = lambda: setattr(
        opslag, "vertraagd", opslag.vertraagd + 1
    )

    async def _nu():
        opslag.direct += 1

    c.async_save_persisted_state_now = _nu
    c.async_update = lambda: asyncio.sleep(0)


# --- 1. direct wegschrijven -------------------------------------------


def test_de_kalibratie_wordt_meteen_bewaard(make_coordinator, hass, opslag):
    """Het geval uit de melding: aanzetten en meteen herstarten."""
    c = make_coordinator({})
    _volg(c, opslag)

    asyncio.run(c.async_set_kalibratie(True))

    assert opslag.direct == 1


def test_uitzetten_ook(make_coordinator, hass, opslag):
    """v3.42.1 beschreef precies het omgekeerde geval: uitzetten en

    binnen dertig seconden herstarten liet de kalibratie terugkomen.
    """
    c = make_coordinator({})
    c.kalibratie = True
    _volg(c, opslag)

    asyncio.run(c.async_set_kalibratie(False))

    assert opslag.direct == 1


def test_de_andere_handmatige_schakelaars_ook(make_coordinator, hass, opslag):
    c = make_coordinator({})
    _volg(c, opslag)

    asyncio.run(c.async_set_force_manual(True))
    asyncio.run(c.async_set_learning_only(True))

    assert opslag.direct == 2


def test_de_gewone_ronde_blijft_vertraagd(make_coordinator, hass, opslag):
    """De vertraging bestaat niet voor niets: één ronde raakt tientallen

    velden, en de live luisteraars vuren meermaals per minuut. Zonder
    die rem is het onnodig schrijven naar de schijf.
    """
    c = make_coordinator({})
    _volg(c, opslag)

    c.schedule_persisted_state_save()

    assert opslag.direct == 0
    assert opslag.vertraagd == 1


# --- 2. sinds wanneer loopt hij ---------------------------------------


def test_aanzetten_legt_het_moment_vast(make_coordinator, hass, opslag):
    c = make_coordinator({})
    _volg(c, opslag)

    asyncio.run(c.async_set_kalibratie(True, now=NU))

    assert c.kalibratie_sinds == NU.isoformat()


def test_uitzetten_wist_het_moment(make_coordinator, hass, opslag):
    c = make_coordinator({})
    c.kalibratie = True
    c.kalibratie_sinds = NU.isoformat()
    _volg(c, opslag)

    asyncio.run(c.async_set_kalibratie(False, now=NU))

    assert c.kalibratie_sinds is None


def test_nog_eens_aanzetten_verschuift_het_moment_niet(
    make_coordinator, hass, opslag
):
    """Een tweede aanroep met dezelfde stand is geen nieuwe kalibratie.

    Zonder deze regel zou elke ronde die de schakelaar bevestigt de
    teller op nul zetten.
    """
    c = make_coordinator({})
    c.kalibratie = True
    c.kalibratie_sinds = "2026-09-01T07:00:00+00:00"
    _volg(c, opslag)

    asyncio.run(c.async_set_kalibratie(True, now=NU))

    assert c.kalibratie_sinds == "2026-09-01T07:00:00+00:00"


def test_het_moment_wordt_bewaard():
    """Anders staat het er na een herstart alsnog niet."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "kalibratie_sinds" in PERSISTED_PLAIN_FIELDS
