"""Een wasmachine die uit staat, is niet stuk (v3.95.0).

Gemeld: "Welke entiteiten zijn stuk?" bij `entiteiten_stuk: 2` naast
`"Geen bijzonderheden"` in dezelfde regel.

Uit de export van 31 augustus 21:38:

    washing_machine_end_at_entity        sensor.wasmachine_programma_eindtijd
    washing_machine_ready_sensor_entity  binary_sensor.wasmachine_start_op_afstand

Beide `unavailable`, allebei van de wasmachine. Veel
apparaatintegraties zetten hun entiteiten op unavailable zodra het
apparaat uit staat - een programma-eindtijd bestaat niet als er geen
programma loopt.

Dat verklaart ook het oplopen: 0, 1, 2 over drie exports op één avond.
Geen kapotgaande entiteiten, maar een wasmachine die aan stond, ging
draaien en klaar was.

De analyse noemde het terecht geen probleem, maar het getal ernaast
suggereerde het wel. Voor een apparaat dat uit staat hoort er een derde
oordeel te zijn, naast `bestaat_niet` en `geen_waarde`.

Wat het NIET mag worden: een oordeel dat alles wegpoetst. Een prijssensor
of een accusensor die niets geeft, is wél stuk - daar hangt de sturing
aan.
"""
import pytest

APPARAAT = "sensor.wasmachine_programma_eindtijd"
KERN = "sensor.price"


def _controle(c, hass, config, waarden):
    for entiteit, staat in waarden.items():
        hass.states.set(entiteit, staat)
    c.config = dict(config)
    return c.get_configuratiecontrole()


def _regel(uitkomst, entiteit):
    return next(r for r in uitkomst["entiteiten"] if r["entiteit"] == entiteit)


def test_een_apparaat_dat_uit_staat_heet_slaapt(make_coordinator, hass):
    """Het geval van 31 augustus."""
    c = make_coordinator({})

    uitkomst = _controle(
        c,
        hass,
        {"washing_machine_end_at_entity": APPARAAT},
        {APPARAAT: "unavailable"},
    )

    assert _regel(uitkomst, APPARAAT)["oordeel"] == "slaapt"


def test_een_slapend_apparaat_telt_niet_als_stuk(make_coordinator, hass):
    """`entiteiten_stuk: 2` naast "Geen bijzonderheden" was de klacht."""
    c = make_coordinator({})

    uitkomst = _controle(
        c,
        hass,
        {"washing_machine_end_at_entity": APPARAAT},
        {APPARAAT: "unavailable"},
    )

    assert uitkomst["aantal_stuk"] == 0
    assert uitkomst["aantal_slaapt"] == 1


def test_een_kernsensor_zonder_waarde_is_wel_stuk(make_coordinator, hass):
    """Aan de prijssensor hangt de hele sturing. Die mag dit oordeel

    niet krijgen, hoe stil hij ook is.
    """
    c = make_coordinator({})

    uitkomst = _controle(
        c, hass, {"price_sensor_entity": KERN}, {KERN: "unavailable"}
    )

    assert _regel(uitkomst, KERN)["oordeel"] == "geen_waarde"
    assert uitkomst["aantal_stuk"] == 1


def test_een_apparaatentiteit_die_niet_bestaat_blijft_een_fout(
    make_coordinator, hass
):
    """Een hernoemde entiteit is geen slapend apparaat, en dat verschil

    is juist waarom dit oordeel bestaat.
    """
    c = make_coordinator({})

    uitkomst = _controle(
        c, hass, {"washing_machine_end_at_entity": APPARAAT}, {}
    )

    assert _regel(uitkomst, APPARAAT)["oordeel"] == "bestaat_niet"
    assert uitkomst["aantal_stuk"] == 1


def test_een_draaiend_apparaat_is_gewoon_in_orde(make_coordinator, hass):
    c = make_coordinator({})

    uitkomst = _controle(
        c,
        hass,
        {"washing_machine_end_at_entity": APPARAAT},
        {APPARAAT: "2026-09-01T07:30:00+00:00"},
    )

    assert _regel(uitkomst, APPARAAT)["oordeel"] == "in_orde"
    assert uitkomst["aantal_slaapt"] == 0


def test_de_uitleg_zegt_waarom_het_geen_fout_is(make_coordinator, hass):
    """Zonder uitleg is "slaapt" net zo raadselachtig als het getal 2."""
    c = make_coordinator({})

    uitkomst = _controle(
        c,
        hass,
        {"washing_machine_end_at_entity": APPARAAT},
        {APPARAAT: "unavailable"},
    )

    uitleg = _regel(uitkomst, APPARAAT)["uitleg"]

    assert "uit" in uitleg.lower()
    assert "wasmachine" in uitleg.lower() or "apparaat" in uitleg.lower()


def test_elke_apparaatinstelling_wordt_herkend(make_coordinator, hass):
    """De lijst hoort compleet te zijn: staat er een apparaat niet in,

    dan telt dat straks weer als storing zodra het uit gaat.
    """
    from custom_components.energy_management_system.const import (
        APPARAAT_INSTELLINGEN,
    )

    verwacht = {
        "dishwasher_power_sensor_entity",
        "dishwasher_ready_sensor_entity",
        "dishwasher_energy_sensor_entity",
        "dishwasher_start_in_entity",
        "washing_machine_power_sensor_entity",
        "washing_machine_ready_sensor_entity",
        "washing_machine_energy_sensor_entity",
        "washing_machine_end_at_entity",
        "steelstofzuiger_switch_entity",
        "steelstofzuiger_power_sensor_entity",
        "fietsladers_switch_entity",
        "fietsladers_power_sensor_entity",
        "oven_state_sensor_entity",
        "quooker_power_sensor_entity",
    }

    assert verwacht <= set(APPARAAT_INSTELLINGEN)
