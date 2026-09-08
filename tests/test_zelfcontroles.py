"""Invarianten die tijdens bedrijf worden gecontroleerd (v4.1).

Gevraagd: "Wordt nu ook echt elke minuscuul foutje gevonden middels de
diagnostiek?" Nee. De grootste fouten van de afgelopen week hadden geen
foutmelding; het waren getallen die er plausibel uitzagen. De nacht die
nooit als tekort werd gezien, een tak die drie maanden niet bereikt
werd, drie reserves die uiteenliepen. Dit zijn de controles die die
drie WEL hadden gezien.

1. Eén reserve: de brug, de verkooptoets en de planning zien hetzelfde
   getal. Zo niet, dan is er weer een tweede definitie ingeslopen.
2. De nacht is gecontroleerd: tussen 22:00 en 06:00 hoort de
   tekortdetectie te draaien. Nul zelfvoorzienende rondes in een nacht
   is de fout van v3.99.16.
3. Padbereik: per beslissingsreden en per proefstandkandidaat hoeveel
   keer hij gevuurd heeft. Een reden die in dertig dagen nooit vuurt,
   is een tak waar een NameError drie maanden kan wachten.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 9, 7, 0, tzinfo=timezone.utc)


# --- 1. één reserve ----------------------------------------------------


def test_de_drie_lezers_worden_vergeleken(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reserve_margin_breakdown = {"reserve_kwh_after_margin": 6.13}
    c.last_needed_kwh_to_bridge = 6.13
    c.last_sell_check = {"nodig_voor_woning_kwh": 6.13}

    uit = c.zelfcontrole_een_reserve()

    assert uit["in_orde"] is True


def test_een_afwijkende_lezer_wordt_gemeld(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reserve_margin_breakdown = {"reserve_kwh_after_margin": 6.13}
    c.last_needed_kwh_to_bridge = 4.42
    c.last_sell_check = {"nodig_voor_woning_kwh": 6.13}

    uit = c.zelfcontrole_een_reserve()

    assert uit["in_orde"] is False
    assert "brug" in uit["afwijkend"]


def test_de_dode_zone_van_de_verkooptoets_telt_niet_als_afwijking(make_coordinator, hass):
    """De verkooptoets kapt op de accu en houdt de bodem aan; dat is
    dezelfde reserve met een rem, geen andere reserve. Een verschil
    onder de tolerantie is in orde."""
    c = make_coordinator({})
    c.last_reserve_margin_breakdown = {"reserve_kwh_after_margin": 6.13}
    c.last_needed_kwh_to_bridge = 6.13
    c.last_sell_check = {"nodig_voor_woning_kwh": 6.10}

    assert c.zelfcontrole_een_reserve()["in_orde"] is True


# --- 2. de nacht is gecontroleerd --------------------------------------


def test_zelfvoorzienende_rondes_worden_geteld(make_coordinator, hass):
    c = make_coordinator({})
    c._nachtrondes = {"totaal": 0, "zelfvoorzienend": 0}

    c._tel_nachtronde(NU.replace(hour=2), "discharging_window")
    c._tel_nachtronde(NU.replace(hour=3), "arbitrage_solar_capture")

    assert c._nachtrondes == {"totaal": 2, "zelfvoorzienend": 1}


def test_overdag_telt_niet(make_coordinator, hass):
    c = make_coordinator({})
    c._nachtrondes = {"totaal": 0, "zelfvoorzienend": 0}

    c._tel_nachtronde(NU.replace(hour=14), "discharging_window")

    assert c._nachtrondes == {"totaal": 0, "zelfvoorzienend": 0}


def test_een_nacht_zonder_controle_is_een_bevinding(make_coordinator, hass):
    c = make_coordinator({})
    c._nachtrondes = {"totaal": 240, "zelfvoorzienend": 0}

    uit = c.zelfcontrole_nacht_gecontroleerd()

    assert uit["in_orde"] is False
    assert "v3.99.16" in uit["uitleg"]


def test_een_gecontroleerde_nacht_is_in_orde(make_coordinator, hass):
    c = make_coordinator({})
    c._nachtrondes = {"totaal": 240, "zelfvoorzienend": 180}

    assert c.zelfcontrole_nacht_gecontroleerd()["in_orde"] is True


# --- 3. padbereik --------------------------------------------------------


def test_elke_reden_wordt_geteld(make_coordinator, hass):
    c = make_coordinator({})
    c.padbereik = {}

    c._tel_pad("reden", "discharging_window", NU)
    c._tel_pad("reden", "discharging_window", NU)
    c._tel_pad("reden", "emergency_low_battery", NU)

    assert c.padbereik["reden:discharging_window"]["aantal"] == 2
    assert c.padbereik["reden:emergency_low_battery"]["laatst"] == NU.isoformat()


def test_redenen_die_nooit_vuurden_worden_genoemd(make_coordinator, hass):
    c = make_coordinator({})
    c.padbereik = {"reden:discharging_window": {"aantal": 5, "laatst": NU.isoformat()}}

    uit = c.get_padbereik()

    assert "emergency_low_battery" in uit["nooit_gevuurd"]
    assert "discharging_window" not in uit["nooit_gevuurd"]
    assert uit["toelichting"]
