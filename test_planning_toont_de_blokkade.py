"""De planning vertelt dat de verkoop niet doorgaat (v3.44.0).

Gemeten op 20 augustus 21:16, één minuut na het installeren van de rem
uit v3.43.0:

    sell_check          mag_verkopen: false
                        "planning voorziet een tekort"
    quarter_plan        30 verkoopkwartieren

De aansturing weigert te verkopen; de tabel toont dertig
verkoopkwartieren. Geen van beide is fout, maar samen misleiden ze.

De simulatie verkoopt bewust WÉL. Dat is de tegenfeitelijke wereld die
de rem rechtvaardigt: "als ik nu verkoop, kom ik morgenvroeg tekort."
Zou de simulatie de rem meenemen, dan verdwijnt het tekort, gaat de rem
uit, komt het tekort terug - en pendelt het tussen die twee. Precies wat
de koeling vier versies lang deed.

Dus niet de simulatie aanpassen, maar zeggen wat er staat.
"""
from datetime import datetime

from custom_components.energy_management_system.const import (
    PLAN_SHORTFALL_ALERT_MIN_QUARTERS,
)

NU = datetime(2026, 8, 20, 21, 16)


def _met_planning(make_coordinator):
    """Een minimale planning, zodat de samenvatting iets te vatten heeft."""
    c = make_coordinator({})
    c.get_quarter_plan = lambda now=None: [
        {
            "van": "21:15",
            "modus": "manual (verkopen)",
            "prijs_ct": 37.0,
            "soc_procent": 60.0,
            "zon_kwh": 0.0,
            "verbruik_kwh": 0.06,
            "net_kwh": -0.34,
            "tekort": False,
            "voor_bijladen": False,
            "in_goedkoop_blok": False,
            "verkoop_kwh": 0.34,
        }
    ]
    return c


def test_the_summary_says_selling_is_blocked(make_coordinator, hass):
    c = _met_planning(make_coordinator)
    c.last_plan_shortfall = {"kwartieren": 5, "perioden": ["morgen 06:15"]}


    assert c.verkoop_geblokkeerd_door_tekort() is True
    assert "verkoopt op dit moment niet" in c.verkoop_blokkade_reden()


def test_without_a_shortfall_the_table_speaks_for_itself(
    make_coordinator, hass
):
    c = _met_planning(make_coordinator)
    c.last_plan_shortfall = {"kwartieren": 0, "perioden": []}


    assert c.verkoop_geblokkeerd_door_tekort() is False
    assert c.verkoop_blokkade_reden() is None


def test_the_same_threshold_as_the_brake(make_coordinator, hass):
    """Twee drempels voor dezelfde beslissing betekent dat de tabel iets

    anders zegt dan de aansturing doet.
    """
    c = _met_planning(make_coordinator)
    c.last_plan_shortfall = {
        "kwartieren": PLAN_SHORTFALL_ALERT_MIN_QUARTERS - 1,
        "perioden": [],
    }

    assert c.verkoop_geblokkeerd_door_tekort() is False

    c.last_plan_shortfall["kwartieren"] = PLAN_SHORTFALL_ALERT_MIN_QUARTERS

    assert c.verkoop_geblokkeerd_door_tekort() is True


def test_a_fresh_start_blocks_nothing(make_coordinator, hass):
    """Na een herstart is er nog geen planning doorgerekend."""
    c = _met_planning(make_coordinator)

    assert c.verkoop_geblokkeerd_door_tekort() is False


def test_the_simulation_itself_keeps_selling(make_coordinator, hass):
    """De kern van de keuze: de simulatie mag de rem NIET meenemen.

    Doet hij dat wel, dan verdwijnt het tekort dat de rem rechtvaardigt
    en gaat het pendelen.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C.get_quarter_plan)

    assert "last_plan_shortfall" not in bron


def test_the_field_reaches_the_export():
    """Zonder dit veld is niet na te gaan of de rem zweeg omdat er geen

    tekort was, of omdat de stand nog leeg was - precies de vraag die
    op 20 augustus 21:15 open bleef.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert '"last_plan_shortfall"' in bron
