"""De accustand komt van de sensor, niet uit een oud veld (v3.48.0).

Gemeld: "Accu lijkt 's morgens structureel te weinig te hebben." Gemeten
in de export van 27 augustus 08:09:

    last_soc_percent          38 %
    kwartierplan begint       10 %
    modules                   2, 8, 7 %
    grafiek van de sensor      6 %
    kalman gefilterd           0,0 kWh

Elk getal in dezelfde export zei "leeg", behalve dat ene veld. De
sensor liep gewoon door - die 38% kwam ergens uit de nacht, toen een tak
die het veld zet voor het laatst werd bereikt.

`last_soc_percent` wordt namelijk maar op drie plaatsen geschreven, en
alle drie zitten in de berekening van het ontlaadvermogen. Wordt die tak
niet bereikt, dan blijft de oude waarde staan.

Dit is dezelfde fout als op 11 augustus, toen het veld op None stond
terwijl de accu 22% aangaf. Daarvoor is toen `accustand_procent()`
gemaakt, met in de toelichting: "Zo'n veld is een bijproduct van een
berekening, geen accustand." Maar het veld bleef als TERUGVAL in die
helper staan, en zes andere plekken lazen het nog rechtstreeks.

Een oude waarde is gevaarlijker dan geen waarde: er wordt zonder
aarzeling mee gerekend.
"""
import inspect

import pytest

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


def test_the_live_sensor_wins(make_coordinator, hass):
    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    hass.states.set("sensor.soc", "6.0")
    c.last_soc_percent = 38.0

    assert c.accustand_procent() == 6.0


def test_a_stale_field_is_not_a_fallback(make_coordinator, hass):
    """v3.50.0: de terugval mag, maar alleen zolang hij VERS is.

    Eerst had ik hem helemaal geschrapt. Achtenveertig toetsen vielen
    om, en dat was terecht: bij een sensor die één ronde niets zegt is
    een waarde van een minuut geleden prima. De aansturing stilzetten
    bij elke hapering is erger dan het kwaad.

    Het probleem is niet de terugval maar de LEEFTIJD ervan.
    """
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    c.last_soc_percent = 38.0
    c.meting_tijdstippen["last_soc_percent"] = dt_util.now() - timedelta(
        hours=5
    )

    assert c.accustand_procent() is None


def test_a_fresh_field_is_still_used(make_coordinator, hass):
    """Een sensor die één ronde hapert mag de aansturing niet stilzetten."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    c.last_soc_percent = 38.0
    c.meting_tijdstippen["last_soc_percent"] = dt_util.now() - timedelta(
        seconds=30
    )

    assert c.accustand_procent() == 38.0


def test_a_fresh_derivation_is_still_allowed(make_coordinator, hass):
    """Afleiden uit de beschikbare energie mag wél - dat is een VERSE

    meting, geen oude.
    """
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    c.last_soc_percent = 38.0
    c.meting_tijdstippen["last_soc_percent"] = dt_util.now() - timedelta(
        hours=5
    )
    c.beschikbare_energie_kwh = lambda: 3.9
    c.bruikbare_capaciteit_kwh = lambda: 7.8

    uitkomst = c.accustand_procent()

    # De afleiding rekent de ondergrens mee: 3,9 van 7,8 bruikbaar is
    # 50% van de SCHAAL, wat neerkomt op 65% laadstand bij 10% bodem.
    assert uitkomst is not None
    assert 60.0 <= uitkomst <= 70.0


@pytest.mark.parametrize(
    "naam",
    [
        "_build_explanation",
        "get_diagnostic_summary",
    ],
)
def test_no_function_reads_the_stale_field_directly(naam):
    """Zes plekken lazen het veld rechtstreeks. Die horen allemaal via

    de helper te gaan, anders is de reparatie half.
    """
    bron = inspect.getsource(getattr(C, naam))

    assert "self.last_soc_percent" not in bron


def test_only_the_helper_still_mentions_the_field():
    """Structuurtoets: buiten de schrijvers en de helper mag het veld

    nergens meer gelezen worden.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    # v3.49.0: de spiegelcontrole leest het veld met opzet - dat is
    # precies zijn taak. Hij vergelijkt het interne getal met de sensor
    # om te MELDEN dat ze uiteenlopen, en dan moet hij er wel bij
    # kunnen.
    for uitzondering in (
        # De spiegelcontrole leest het veld met opzet - dat is zijn taak.
        "self.last_soc_percent,\n                self._read_sensor_float(soc_entity)",
        # En de leeftijdstoets van v3.50.0 mag het teruggeven zolang het
        # vers is.
        'if self._meting_is_vers("last_soc_percent"):\n            return self.last_soc_percent',
    ):
        bron = bron.replace(uitzondering, "<toegestaan>")
    lezers = [
        r.strip()
        for r in bron.split("\n")
        if "self.last_soc_percent" in r
        and not r.split("self.last_soc_percent")[1].lstrip().startswith(("=", ":"))
        and not r.strip().startswith("#")
    ]

    assert not lezers, f"nog directe lezers: {lezers}"
