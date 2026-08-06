"""Beslislogica na het einde van saldering (v1.1.0).

Gevraagd: de aansturing laten meebewegen met het verschil dat ontstaat
zodra saldering vervalt - maar uitdrukkelijk: "In acht houden dat dit pas
vanaf 01-01-2027 geldt".

Alles hieronder hangt daarom achter `_is_salderen_active(now)`. Tot en
met de salderingsdatum is het gedrag ONGEWIJZIGD; de eerste
testgroep legt dat vast en is daarmee de belangrijkste van dit bestand.

Twee wijzigingen, beide met dezelfde onderliggende reden: onder saldering
levert een teruggeleverde kWh evenveel op als een ingekochte kost, dus is
exporteren en zelf verbruiken om het even. Daarna niet meer - exporteren
levert het lage teruglevertarief, terwijl diezelfde kWh thuis de volle
belaste inkoopprijs bespaart.

1. Zonoverschot opvangen krijgt voorrang op verkopen.
2. Geforceerd ontladen wordt begrensd tot ongeveer het eigen verbruik.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_PV_POWER_SENSOR,
    CONF_SALDEREN_END_DATE,
    POST_SALDEREN_DISCHARGE_OVERSHOOT_W,
    POST_SALDEREN_MIN_SURPLUS_TO_CAPTURE_W,
    POST_SALDEREN_MIN_USEFUL_DISCHARGE_W,
)

TIJDENS = datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc)
DAARNA = datetime(2027, 8, 6, 18, 0, tzinfo=timezone.utc)


def _config(**extra):
    basis = {
        CONF_PV_POWER_SENSOR: "sensor.pv",
        CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1",
        CONF_SALDEREN_END_DATE: "2026-12-31",
    }
    basis.update(extra)
    return basis


def _situatie(hass, pv_w, huisverbruik_w):
    """Zet PV en verbruik. `_read_corrected_consumption_power` leidt het
    huisverbruik af uit P1 + accu + PV, dus P1 wordt zo gezet dat het
    gewenste huisverbruik eruit komt."""
    hass.states.set("sensor.pv", str(pv_w))
    hass.states.set("sensor.p1", str(huisverbruik_w - pv_w))


# --- 1. VÓÓR 2027 VERANDERT ER NIETS --------------------------------


def test_capture_never_triggers_while_salderen_is_active(
    make_coordinator, hass
):
    """De belangrijkste test van dit bestand."""
    c = make_coordinator(_config())
    _situatie(hass, pv_w=4000, huisverbruik_w=300)

    assert c.should_capture_surplus_over_selling(TIJDENS) is False


def test_discharge_is_never_capped_while_salderen_is_active(
    make_coordinator, hass
):
    c = make_coordinator(_config())
    _situatie(hass, pv_w=0, huisverbruik_w=200)

    assert c.cap_discharge_to_own_consumption(TIJDENS, 2400.0) == 2400.0


def test_capping_is_a_no_op_on_the_last_salderen_day(make_coordinator, hass):
    """Op 31 december geldt saldering nog - de omslag hoort pas de dag
    erna te komen."""
    c = make_coordinator(_config())
    _situatie(hass, pv_w=0, huisverbruik_w=200)
    laatste_dag = datetime(2026, 12, 31, 18, 0, tzinfo=timezone.utc)

    assert c.cap_discharge_to_own_consumption(laatste_dag, 2400.0) == 2400.0
    assert c.should_capture_surplus_over_selling(laatste_dag) is False


def test_the_switch_happens_the_next_day(make_coordinator, hass):
    c = make_coordinator(_config())
    _situatie(hass, pv_w=0, huisverbruik_w=200)
    eerste_dag = datetime(2027, 1, 1, 18, 0, tzinfo=timezone.utc)

    assert c.cap_discharge_to_own_consumption(eerste_dag, 2400.0) != 2400.0


def test_a_postponed_end_date_postpones_the_behaviour(make_coordinator, hass):
    """De datum is configureerbaar wegens mogelijk politiek uitstel; het
    gedrag hoort daar zonder meer in mee te bewegen."""
    c = make_coordinator(_config(**{CONF_SALDEREN_END_DATE: "2028-12-31"}))
    _situatie(hass, pv_w=0, huisverbruik_w=200)

    assert c.cap_discharge_to_own_consumption(DAARNA, 2400.0) == 2400.0


# --- 2. ZONOVERSCHOT OPVANGEN (na saldering) ------------------------


def test_surplus_gets_priority_over_selling(make_coordinator, hass):
    c = make_coordinator(_config())
    _situatie(hass, pv_w=4000, huisverbruik_w=300)

    assert c.should_capture_surplus_over_selling(DAARNA) is True


def test_no_surplus_means_no_change(make_coordinator, hass):
    """Zonder overschot blijft de bestaande verkooplogica gewoon
    gelden."""
    c = make_coordinator(_config())
    _situatie(hass, pv_w=0, huisverbruik_w=800)

    assert c.should_capture_surplus_over_selling(DAARNA) is False


def test_a_trickle_of_surplus_is_not_enough(make_coordinator, hass):
    """Bij een paar watt zou de beslissing heen en weer slaan tussen
    opvangen en ontladen."""
    c = make_coordinator(_config())
    _situatie(
        hass, pv_w=500 + POST_SALDEREN_MIN_SURPLUS_TO_CAPTURE_W - 10,
        huisverbruik_w=500,
    )

    assert c.should_capture_surplus_over_selling(DAARNA) is False


def test_unreadable_sensors_leave_the_existing_logic_alone(
    make_coordinator, hass
):
    c = make_coordinator(_config())
    hass.states.set("sensor.pv", "unavailable")
    hass.states.set("sensor.p1", "300")

    assert c.should_capture_surplus_over_selling(DAARNA) is False


# --- 3. ONTLADEN BEGRENZEN TOT EIGEN VERBRUIK -----------------------


def test_discharge_is_capped_to_household_load(make_coordinator, hass):
    """2400 W ontladen bij 400 W verbruik zou 2000 W exporteren tegen het
    lage teruglevertarief."""
    c = make_coordinator(_config())
    _situatie(hass, pv_w=0, huisverbruik_w=400)

    resultaat = c.cap_discharge_to_own_consumption(DAARNA, 2400.0)

    assert resultaat == 400.0 + POST_SALDEREN_DISCHARGE_OVERSHOOT_W


def test_a_modest_discharge_is_left_alone(make_coordinator, hass):
    """Blijft het vermogen al onder het verbruik, dan is er niets te
    begrenzen."""
    c = make_coordinator(_config())
    _situatie(hass, pv_w=0, huisverbruik_w=2000)

    assert c.cap_discharge_to_own_consumption(DAARNA, 800.0) == 800.0


def test_too_little_own_load_means_no_forced_discharge(make_coordinator, hass):
    """Bij vrijwel geen eigen verbruik wegen de omvormer-verliezen
    zwaarder dan de vermeden inkoop."""
    c = make_coordinator(_config())
    _situatie(hass, pv_w=0, huisverbruik_w=0)

    assert c.cap_discharge_to_own_consumption(DAARNA, 2400.0) is None


def test_the_threshold_applies_to_own_consumption(make_coordinator, hass):
    """De drempel geldt voor het EIGEN VERBRUIK, niet voor het begrensde
    totaal. Anders haalt de overschrijdingsmarge in zijn eentje de
    drempel al en zou er bij nul verbruik alsnog puur geexporteerd
    worden."""
    c = make_coordinator(_config())

    _situatie(hass, pv_w=0, huisverbruik_w=POST_SALDEREN_MIN_USEFUL_DISCHARGE_W - 1)
    assert c.cap_discharge_to_own_consumption(DAARNA, 2400.0) is None

    _situatie(hass, pv_w=0, huisverbruik_w=POST_SALDEREN_MIN_USEFUL_DISCHARGE_W + 1)
    assert c.cap_discharge_to_own_consumption(DAARNA, 2400.0) is not None


def test_no_consumption_sensor_leaves_the_power_untouched(
    make_coordinator, hass
):
    """Zonder verbruiksmeting valt er niets te begrenzen - dan liever het
    bestaande gedrag dan gokken."""
    c = make_coordinator({CONF_SALDEREN_END_DATE: "2026-12-31"})

    assert c.cap_discharge_to_own_consumption(DAARNA, 2400.0) == 2400.0


def test_none_stays_none(make_coordinator, hass):
    """Was het vermogen al weggevallen door een lage SoC, dan blijft dat
    zo."""
    c = make_coordinator(_config())
    _situatie(hass, pv_w=0, huisverbruik_w=1000)

    assert c.cap_discharge_to_own_consumption(DAARNA, None) is None


# --- 4. uitleg ------------------------------------------------------


def test_both_new_reasons_have_an_explanation(make_coordinator, hass):
    """Een beslissing zonder uitleg is in dit project geen beslissing."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    for reden in ("post_salderen_solar_capture", "expensive_quarter_no_own_load"):
        assert f'reason == "{reden}"' in bron


def test_the_gate_is_the_salderen_date_itself(make_coordinator, hass):
    """Borging dat beide wijzigingen echt achter dezelfde poort hangen en
    niet achter een eigen, los criterium dat kan gaan afwijken."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    for functie in (
        "def should_capture_surplus_over_selling",
        "def cap_discharge_to_own_consumption",
    ):
        blok = bron[bron.index(functie) :][:2200]
        assert "_is_salderen_active" in blok
