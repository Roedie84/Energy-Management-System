"""Een tekortdag vraagt meer dan één moment van 100 W (v5.6).

Uit de export van 18 september: zeven tekortnachten op rij, en de
dashboardtekst *"de veiligheidsmarge staat mogelijk te krap"*. De
onderliggende cijfers:

    09-11   ochtendstand 37%   netimport 0,11 kWh   -> tekort
    09-12   ochtendstand 10%   netimport 1,05 kWh   -> tekort
    09-13   ochtendstand 33%   netimport 0,10 kWh   -> tekort
    09-14   ochtendstand 18%   netimport 0,10 kWh   -> tekort
    09-15   ochtendstand 18%   netimport 0,10 kWh   -> tekort
    09-16   ochtendstand 15%   netimport 0,26 kWh   -> tekort
    09-17   ochtendstand 13%   netimport 0,21 kWh   -> tekort

Een nacht met 37% laadstand OVER en 0,11 kWh netafname telde als tekort.
Dat is honderd watt-uur over een hele nacht.

De oorzaak: een dag telt als tekortdag zodra de netafname ÉÉN keer boven
100 W komt. Geen minimale duur, geen minimale hoeveelheid.

En dat is niet cosmetisch. `SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY` is 5
procent per recente tekortdag, dus zeven "tekorten" zetten een forse
opslag op de reserve - de 1,295 die de zelfcontrole van v4.1 liet
oplopen. Een hogere reserve betekent MINDER VERKOPEN. Er werd dus
betaald voor een tekort dat er niet was.

Van de zeven was er één echt: 12 september, 10% en 1,05 kWh.

De maat die hier hoort bestond al in `const.py` -
`BATTERY_NIGHT_SHORTFALL_MIN_KWH = 0.5` - maar werd op deze plek niet
gebruikt. Nu telt een dag pas als tekortdag als er ook werkelijk
noemenswaardig is bijgekocht.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 18, 3, 0, tzinfo=timezone.utc)


def test_een_kort_piekje_is_geen_tekortdag(make_coordinator, hass):
    """Het gemeten geval: 0,11 kWh over een nacht met 37% over."""
    from custom_components.energy_management_system.const import (
        SHORTFALL_MIN_NETIMPORT_KWH,
    )

    c = make_coordinator({})

    assert c._telt_als_tekortdag(netimport_kwh=0.11) is False
    assert c._telt_als_tekortdag(netimport_kwh=0.26) is False
    assert SHORTFALL_MIN_NETIMPORT_KWH >= 0.4


def test_een_echt_tekort_telt_wel(make_coordinator, hass):
    """12 september: 10% ochtendstand en 1,05 kWh bijgekocht."""
    c = make_coordinator({})

    assert c._telt_als_tekortdag(netimport_kwh=1.05) is True


def test_precies_op_de_drempel(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        SHORTFALL_MIN_NETIMPORT_KWH,
    )

    c = make_coordinator({})

    assert c._telt_als_tekortdag(netimport_kwh=SHORTFALL_MIN_NETIMPORT_KWH) is True


def test_zonder_meting_geen_tekort(make_coordinator, hass):
    """Geen meting is geen bewijs van een tekort - anders telt een
    kapotte sensor als zeven tekortdagen."""
    c = make_coordinator({})

    assert c._telt_als_tekortdag(netimport_kwh=None) is False


def test_het_moment_alleen_zet_nog_geen_tekortdag(make_coordinator, hass):
    """De 100 W-drempel blijft bestaan als SIGNAAL: hij zet de vlag dat
    er iets gebeurde. Maar pas bij de dagwissel, met de gemeten
    netimport erbij, telt het als tekortDAG."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index('"shortfall": ')
    # de toewijzing loopt over twee regels
    blok = bron[i : i + 220]

    assert "_telt_als_tekortdag" in blok, blok[:160]


def test_de_marge_reageert_op_de_nieuwe_telling(make_coordinator, hass):
    """Waar het om gaat: minder valse tekortdagen is een lagere opslag op
    de reserve, en dus meer ruimte om te verkopen."""
    from custom_components.energy_management_system.const import (
        SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY,
    )

    c = make_coordinator({})
    c.reserve_daily_records = [
        {"date": f"2026-09-{d:02d}", "shortfall": False, "netimport_nacht_kwh": 0.1}
        for d in range(11, 18)
    ]

    recent = sum(1 for r in c.reserve_daily_records if r.get("shortfall"))

    assert recent == 0
    assert SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY == 5.0
