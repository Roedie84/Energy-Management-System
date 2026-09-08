"""De statussensor overschreed de 16 kB van de recorder (v3.99.16).

Uit het logboek, 776 keer sinds 7 september 18:00:

    State attributes for sensor.woonkamer_energy_management_system_system_status
    exceed maximum size of 16384 bytes. Attributes will not be stored.

`meldingen_historie` bevatte de laatste dertig meldingen VOLLEDIG, en een
moduswisselmelding is tot 924 tekens - de hele uitleg van de energiebrug
zit erin. Dertig van die berichten zijn 15,6 kB; met de aandachtspunten
erbij gaat het over de grens. Dat betekent dat de recorder de attributen
van deze sensor NIET meer opslaat, en dat is precies het mechanisme waar
de reeksen van twintig sensoren aan hangen (v3.99.1, v3.99.11).

De kaart die de historie toont, gebruikt drie velden: moment, titel en
verstuurd. Het bericht staat er niet eens op. De sensor geeft nu alleen
wat de kaart nodig heeft, plus een ingekort bericht voor wie erop tikt.
"""
import json


def test_de_historie_op_de_sensor_is_klein(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        _meldingen_voor_de_kaart,
    )

    lang = "x" * 924
    historie = [
        {"moment": "2026-09-07T18:00:00+02:00", "titel": "🔄 Accu: huis dekken",
         "soort": "mode_change", "verstuurd": True, "bericht": lang}
        for _ in range(30)
    ]

    klein = _meldingen_voor_de_kaart(historie)

    assert len(klein) <= 20
    # v3.99.17: zonder bericht - de kaart gebruikt het niet.
    assert len(json.dumps(klein, ensure_ascii=False)) < 3000
    assert set(klein[0]) == {"moment", "titel", "soort", "verstuurd", "reden_niet_verstuurd"}


def test_de_kaartvelden_blijven_intact(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        _meldingen_voor_de_kaart,
    )

    m = _meldingen_voor_de_kaart([{"moment": "m", "titel": "t", "soort": "s", "verstuurd": False,
                                  "reden_niet_verstuurd": "gedempt", "bericht": "lang"}])[0]

    assert m == {"moment": "m", "titel": "t", "soort": "s", "verstuurd": False, "reden_niet_verstuurd": "gedempt"}


def test_geen_leesactie_in_de_event_loop():
    """Gemeld uit het logboek: "Detected blocking call to read_text inside

    the event loop" - de vertaallabels werden bij de eerste melding
    synchroon gelezen. Nu bij het opstarten in een executor.
    """
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("def _instelling_leesbaar")
    j = bron.index("\n    def ", i + 10)
    assert "read_text" not in bron[i:j]
    assert "async_add_executor_job(self._lees_instellingslabels)" in bron
