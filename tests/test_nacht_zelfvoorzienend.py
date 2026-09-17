"""De nachtcontrole keek naar de stand in plaats van naar het net (v4.18).

Uit de export van 17 september:

    nacht_gecontroleerd: in_orde false
    "Nul van 521 nachtrondes waren zelfvoorzienend. Dan draait de
     tekortdetectie niet 's nachts - precies de fout van v3.99.16."

Maar de nacht was perfect. Elk kwartier van 00:00 tot 07:00 dekte de
accu het huis volledig en er ging zelfs 50 W naar het net:

    01:00   huis 236 W   accu +285   net -49   soc 39%
    04:00   huis 191 W   accu +247   net -56   soc 30%
    06:45   huis 159 W   accu +207   net -48   soc 19%

Nul netafname, laadstand van 42% naar 19%. De teller keek of de STAND
`smart_discharging` was; de reden was de hele nacht `default_smart`, en
die vertaalt naar stand `smart`. Dus telde geen enkele ronde.

Dat is dezelfde fout die deze controle moest opsporen, met een andere
naam: in v3.99.16 miste `smart_discharging` in de lijst, hier mist
`default_smart`. Ik heb een controle gebouwd die naar de stand kijkt
terwijl de vraag is of er stroom van het net kwam - en dat staat in
dezelfde regel.

De teller kijkt nu naar het NET. Dan is geen enkele redennaam meer
nodig en kan deze fout niet een derde keer terugkomen.
"""
from datetime import datetime, timezone

import pytest

NACHT = datetime(2026, 9, 17, 3, 0, tzinfo=timezone.utc)
DAG = datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc)


def test_een_nacht_uit_de_accu_telt(make_coordinator, hass):
    """Het gemeten geval: accu dekt het huis, niets van het net."""
    c = make_coordinator({})
    c._nachtrondes = None

    c._tel_nachtronde(NACHT, "default_smart", net_w=-49.0)

    assert c._nachtrondes == {"totaal": 1, "zelfvoorzienend": 1}


def test_netafname_telt_niet_als_zelfvoorzienend(make_coordinator, hass):
    c = make_coordinator({})
    c._nachtrondes = None

    c._tel_nachtronde(NACHT, "default_smart", net_w=850.0)

    assert c._nachtrondes == {"totaal": 1, "zelfvoorzienend": 0}


def test_een_beetje_netafname_mag(make_coordinator, hass):
    """Vijftig watt ruis is geen aan-het-net-hangen."""
    c = make_coordinator({})
    c._nachtrondes = None

    c._tel_nachtronde(NACHT, "default_smart", net_w=40.0)

    assert c._nachtrondes["zelfvoorzienend"] == 1


def test_de_redennaam_doet_niet_meer_mee(make_coordinator, hass):
    """Waar het om gaat: welke reden er ook staat, het net beslist."""
    c = make_coordinator({})
    c._nachtrondes = None

    for reden in ("default_smart", "discharging_window", "iets_nieuws", None):
        c._tel_nachtronde(NACHT, reden, net_w=-20.0)

    assert c._nachtrondes == {"totaal": 4, "zelfvoorzienend": 4}


def test_buiten_de_nacht_telt_niets(make_coordinator, hass):
    c = make_coordinator({})
    c._nachtrondes = None

    c._tel_nachtronde(DAG, "default_smart", net_w=-49.0)

    assert c._nachtrondes is None


def test_zonder_netmeting_telt_de_ronde_wel_mee(make_coordinator, hass):
    """Wel in het totaal, niet als zelfvoorzienend - anders lijkt een
    kapotte netsensor een geslaagde nacht."""
    c = make_coordinator({})
    c._nachtrondes = None

    c._tel_nachtronde(NACHT, "default_smart", net_w=None)

    assert c._nachtrondes == {"totaal": 1, "zelfvoorzienend": 0}


def test_de_controle_wordt_groen_bij_een_goede_nacht(make_coordinator, hass):
    c = make_coordinator({})
    c._nachtrondes = {"totaal": 500, "zelfvoorzienend": 480}

    uit = c.zelfcontrole_nacht_gecontroleerd()

    assert uit["in_orde"] is True
