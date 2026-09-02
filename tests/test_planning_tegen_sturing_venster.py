"""86 kwartieren "onder de reserve" die er niet onder zitten (v3.99.5).

Uit de export van 2 september 20:19:

    planning_tegen_sturing   reserve_kwh 5,02
                             kwartieren_onder_de_reserve 86
                             laagste 08:45, 28%, 1,73 kWh

De kaart vergelijkt ELK kwartier van de planning met de reserve VAN NU:
5,02 kWh, wat de woning nodig heeft tot het goedkope blok van morgen
12:15. Maar die reserve krimpt met de klok. Om 08:45 is er nog drieënhalf
uur te overbruggen, geen zestien, en dan is 1,73 kWh geen tekort.

De planning rekent zelf al met een reserve per moment
(`_planning_reserve_kwh`, v3.92.1). De kaart hoort daar tegen te
vergelijken, anders telt hij elke nachtelijke kwartier als "gaat in
bedrijf niet gebeuren" terwijl de sturing het gewoon zal laten gebeuren.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 2, 20, 30, tzinfo=timezone.utc)


def _opzet(c):
    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: NU
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.effective_min_soc_percent = lambda: 10.0
    c.last_projection_reserve_kwh = 5.02
    # De planning: 's avonds 60%, 's nachts 40%, 's ochtends 28%.
    c.get_quarter_plan = lambda now=None: [
        {"van": "21:00", "soc_procent": 60, "modus": "manual (verkopen)", "start": NU + timedelta(minutes=30)},
        {"van": "02:00", "soc_procent": 40, "modus": "smart", "start": NU + timedelta(hours=5, minutes=30)},
        {"van": "08:45", "soc_procent": 28, "modus": "smart", "start": NU + timedelta(hours=12, minutes=15)},
    ]
    # De reserve per moment: krimpt naarmate het blok nadert.
    c._planning_reserve_kwh = lambda moment, cache: {
        30: 5.0, 330: 2.5, 735: 1.3
    }[int((moment - NU).total_seconds() // 60)]


def test_de_kaart_vergelijkt_per_moment(make_coordinator, hass):
    """21:00 op 60% is 4,8 kWh tegen 5,0 nodig: onder. 08:45 op 28% is

    1,73 tegen 1,3: erboven.
    """
    c = make_coordinator({})
    _opzet(c)

    uit = c.get_planning_tegen_sturing()

    assert uit["kwartieren_onder_de_reserve"] == 1
    assert uit["eerste"]["van"] == "21:00"


def test_de_reserve_per_moment_staat_erbij(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c)

    uit = c.get_planning_tegen_sturing()

    assert uit["eerste"]["reserve_op_dat_moment_kwh"] == pytest.approx(5.0, abs=0.01)
    assert "krimpt" in uit["toelichting"]
