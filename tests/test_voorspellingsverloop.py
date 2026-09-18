"""Het verloop van de zonvoorspelling bewaren (v5.3).

Aanleiding, 18 september rond 11:15:

    PV / zon:   2,9 kWh opgewekt vandaag (voorspeld 14,0)
    Uitstellen: "Nee. Te weinig zon verwacht om 5,2 kWh vóór 16:00 nog
                 veilig op te vangen."

De beslissing klopte, maar de voorspelling zat 79% ernaast terwijl het
al over elven was. Precies de dag waarop intraday-herschaling had moeten
helpen.

En precies de dag die de terugtoetsbank NIET kan beoordelen. Die
gebruikt de gerealiseerde zon als proxy voor de voorspelling, omdat het
verloop van de voorspelling niet wordt opgeslagen - dat staat als
`beperking` bij de uitkomst. Op een dag als deze is het verschil tussen
"voorspeld 14" en "werkelijk 2,9" juist de hele vraag.

Daarom mijn conclusie van gisteren - herschaling levert -0,001 euro per
dag op, dus dood spoor - te snel was. De bank meet niet wat we willen
weten, en dat wist ik toen ik hem bouwde.

Wat er ontbreekt is het VERLOOP: wat voorspelde het EMS voor de rest van
de dag, op een paar vaste momenten. Drie momentopnames per dag, veertien
dagen bewaard. Stuurt niets; het is de enige nieuwe data die het hele
uitsteltraject nodig heeft.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 9, 18, 11, 0, tzinfo=timezone.utc)


def _zon(c, rest_kwh, tot_nu_kwh=2.9, dag_kwh=14.0):
    c.pv_production_today_kwh = tot_nu_kwh
    c._estimate_pv_kwh_for_period = lambda a, b, **kw: rest_kwh
    c.voorspelde_zon_vandaag_kwh = lambda now=None: (dag_kwh, "vastgelegd")


def test_op_een_vast_moment_wordt_de_voorspelling_vastgelegd(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        VOORSPELLING_MOMENTEN,
    )

    c = make_coordinator({})
    c.voorspellingsverloop = {}
    _zon(c, rest_kwh=4.1)

    c.noteer_voorspellingsverloop(NU)

    dag = c.voorspellingsverloop["2026-09-18"]
    assert "11" in dag
    assert dag["11"]["rest_van_de_dag_kwh"] == 4.1
    assert dag["11"]["gerealiseerd_tot_nu_kwh"] == 2.9
    assert dag["11"]["dagvoorspelling_kwh"] == 14.0
    assert 11 in VOORSPELLING_MOMENTEN


def test_buiten_de_vaste_momenten_gebeurt_er_niets(make_coordinator, hass):
    c = make_coordinator({})
    c.voorspellingsverloop = {}
    _zon(c, rest_kwh=4.1)

    c.noteer_voorspellingsverloop(NU.replace(hour=12, minute=30))

    assert c.voorspellingsverloop == {}


def test_hetzelfde_uur_wordt_niet_twee_keer_overschreven(make_coordinator, hass):
    """De eerste meting van dat uur telt - anders schuift hij mee met de
    ronde en meet je 11:59 in plaats van 11:00."""
    c = make_coordinator({})
    c.voorspellingsverloop = {}
    _zon(c, rest_kwh=4.1)
    c.noteer_voorspellingsverloop(NU)
    _zon(c, rest_kwh=1.2, tot_nu_kwh=3.4)

    c.noteer_voorspellingsverloop(NU.replace(minute=55))

    assert c.voorspellingsverloop["2026-09-18"]["11"]["rest_van_de_dag_kwh"] == 4.1


def test_de_geschiedenis_blijft_begrensd(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        VOORSPELLINGSVERLOOP_DAGEN,
    )

    c = make_coordinator({})
    c.voorspellingsverloop = {}
    _zon(c, rest_kwh=4.1)
    for d in range(1, VOORSPELLINGSVERLOOP_DAGEN + 6):
        c.noteer_voorspellingsverloop(
            NU.replace(month=8 if d <= 31 else 9, day=d if d <= 31 else d - 31)
        )

    assert len(c.voorspellingsverloop) == VOORSPELLINGSVERLOOP_DAGEN
    assert VOORSPELLINGSVERLOOP_DAGEN >= 14


def test_het_overzicht_toont_hoe_de_voorspelling_schoof(make_coordinator, hass):
    """Waar het om gaat: zakte de verwachting gedurende de dag mee met de
    werkelijkheid, of bleef hij hangen?"""
    c = make_coordinator({})
    c.voorspellingsverloop = {
        "2026-09-18": {
            "8": {"rest_van_de_dag_kwh": 13.8, "gerealiseerd_tot_nu_kwh": 0.2,
                  "dagvoorspelling_kwh": 14.0},
            "11": {"rest_van_de_dag_kwh": 11.1, "gerealiseerd_tot_nu_kwh": 2.9,
                   "dagvoorspelling_kwh": 14.0},
            # om 14:00 staat de som nog steeds op 14,0 - de bron stelde
            # dus NIET bij, ook al kwam er veel minder binnen
            "14": {"rest_van_de_dag_kwh": 10.0, "gerealiseerd_tot_nu_kwh": 4.0,
                   "dagvoorspelling_kwh": 14.0},
        }
    }

    uit = c.get_voorspellingsverloop()
    dag = uit["dagen"]["2026-09-18"]

    assert dag["dagvoorspelling_kwh"] == 14.0
    # om 11:00 was er 2,9 binnen en nog 11,1 verwacht: samen 14,0 - de
    # voorspelling schoof dus NIET mee met de werkelijkheid
    assert dag["schoof_mee"] is False


def test_een_voorspelling_die_wel_meeschuift(make_coordinator, hass):
    c = make_coordinator({})
    c.voorspellingsverloop = {
        "2026-09-18": {
            "8": {"rest_van_de_dag_kwh": 13.8, "gerealiseerd_tot_nu_kwh": 0.2,
                  "dagvoorspelling_kwh": 14.0},
            "14": {"rest_van_de_dag_kwh": 2.0, "gerealiseerd_tot_nu_kwh": 4.0,
                   "dagvoorspelling_kwh": 14.0},
        }
    }

    dag = c.get_voorspellingsverloop()["dagen"]["2026-09-18"]

    assert dag["schoof_mee"] is True


def test_zonder_dagen_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    c.voorspellingsverloop = {}

    uit = c.get_voorspellingsverloop()

    assert uit["dagen"] == {}
    assert "nog geen" in uit["oordeel"].lower()
