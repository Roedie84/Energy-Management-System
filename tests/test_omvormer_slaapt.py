"""Een omvormer die 's nachts slaapt, is niet kapot (v5.14.6).

Uit de export van 23 september 06:56:

    fout 1 · config 61/1/1          System status: Aandacht gewenst
    geen_waarde  pv_energy_sensor_entity  sensor.solaredge_production_energy
                 waarde: unknown

De SolarEdge-omvormer schakelt zichzelf uit als er geen zon is, en meldt
dan niets. Om 06:56 stond de zon nog onder de horizon. De integratie
noemde dat "geen_waarde", telde het als kapot, en zette de systeemstatus
op "Aandacht gewenst".

Sinds v3.95.0 geldt al: een apparaat dat uit staat, is niet stuk - de
vaatwasser en de wasmachine krijgen dan "slaapt". Een omvormer zonder zon
hoort in dezelfde categorie. Overdag blijft het wél een storing: dan hoort
hij te leveren.

Dezelfde soort als de opstartweergave van v5.14.5: onderscheid tussen "nu
even niet" en "kapot".
"""
import pytest


def _met_pv(make_coordinator, hass, waarde, zonhoogte):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["pv_energy_sensor_entity"] = "sensor.solaredge_production_energy"
    hass.states.set("sensor.solaredge_production_energy", waarde, {"unit_of_measurement": "kWh"})
    c.get_sun_elevation_degrees = lambda: zonhoogte
    return c


def _regel(c):
    return next(
        r
        for r in c.get_configuratiecontrole()["entiteiten"]
        if r["instelling"] == "pv_energy_sensor_entity"
    )


def test_zonder_zon_slaapt_de_omvormer(make_coordinator, hass):
    """Het gemeten geval van 06:56."""
    c = _met_pv(make_coordinator, hass, "unknown", zonhoogte=-5.0)

    regel = _regel(c)

    assert regel["oordeel"] == "slaapt"
    assert "zon" in regel["uitleg"].lower()


def test_overdag_is_het_wel_een_storing(make_coordinator, hass):
    """Dan hoort de omvormer te leveren."""
    c = _met_pv(make_coordinator, hass, "unknown", zonhoogte=25.0)

    assert _regel(c)["oordeel"] == "geen_waarde"


def test_met_een_waarde_is_er_niets_aan_de_hand(make_coordinator, hass):
    c = _met_pv(make_coordinator, hass, "23253.38", zonhoogte=-5.0)

    assert _regel(c)["oordeel"] == "in_orde"


def test_een_slapende_omvormer_telt_niet_als_kapot(make_coordinator, hass):
    """Anders staat de systeemstatus elke nacht op "Aandacht gewenst"."""
    c = _met_pv(make_coordinator, hass, "unknown", zonhoogte=-5.0)

    controle = c.get_configuratiecontrole()

    assert controle["aantal_stuk"] == 0
    assert controle["aantal_slaapt"] >= 1
