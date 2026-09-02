"""Veel schakelingen kort achter elkaar (v3.99.4).

Gemeld met een schermafdruk van de Zendure Manager: "Slim ontladen" en
"Handmatig Vermogen" om en om, 19:58, 20:04, 20:05, 20:12, 20:13. En
overdag een fijn gestreepte balk van 08:00 tot 16:00.

Uit de export van 20:19: 68 wissels op één dag, 14 in het laatste uur,
`te_vaak: true`. Twee paren doen het:

    overdag   arbitrage_solar_capture  <->  discharging_window   23x
    's avonds expensive_quarter        <->  discharging_window    8x

Allebei dezelfde vorm: een ja/nee-besluit op een getal dat continu
beweegt, zonder dode zone.

De verkooptoets: `beschikbaar <= veilig`. Om 20:19 stond dat op 5,01
tegen 5,02. Verkopen kost 0,03 kWh per minuut, dus na één minuut is het
5,98 tegen 5,02 -> stop -> slim ontladen -> de reserve zakt met de tijd
-> weer ruimte -> verkopen. Elke paar minuten om.

De zonvangst: `overschot > 0`, met het overschot als verwachte zon min
het LIVE huisverbruik. Die verwachting is glad, het verbruik niet: een
koelkastcompressor is genoeg om het teken om te laten slaan.

De energiebrug heeft sinds v0.63.x wél een dode zone (10%, minimaal
0,15 kWh). Deze twee poorten krijgen er nu ook een.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)
BLOK = datetime(2026, 9, 3, 12, 15, tzinfo=timezone.utc)


def _verkoop(c, beschikbaar, veilig):
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: veilig / 1.616
    c._reserve_margin_factor = lambda: 1.616
    c.last_cheap_block_start = BLOK
    return c.may_sell_now(NU)["mag_verkopen"]


# --- de verkooptoets ----------------------------------------------------


def test_eenmaal_geblokkeerd_blijft_hij_dicht_tot_er_ruimte_is(
    make_coordinator, hass
):
    """5,01 tegen 5,02 -> dicht. 5,05 tegen 5,02 -> nog steeds dicht:

    dat is drie minuten verkopen, dan weer dicht.
    """
    c = make_coordinator({})

    assert _verkoop(c, beschikbaar=5.01, veilig=5.02) is False
    assert _verkoop(c, beschikbaar=5.05, veilig=5.02) is False


def test_met_genoeg_ruimte_gaat_hij_weer_open(make_coordinator, hass):
    """... en na het kwartier (v3.99.7)."""
    c = make_coordinator({})
    _verkoop(c, beschikbaar=5.01, veilig=5.02)

    assert _verkoop_op(c, NU + timedelta(minutes=20), beschikbaar=5.40, veilig=5.02) is True


def test_eenmaal_open_blijft_hij_open_tot_de_grens(make_coordinator, hass):
    """Omgekeerd geldt het ook: wie verkoopt, verkoopt door tot de

    reserve zelf - niet tot de reserve plus marge.
    """
    c = make_coordinator({})
    assert _verkoop(c, beschikbaar=5.40, veilig=5.02) is True
    assert _verkoop(c, beschikbaar=5.10, veilig=5.02) is True
    assert _verkoop(c, beschikbaar=5.01, veilig=5.02) is False


def test_de_reden_noemt_de_dode_zone(make_coordinator, hass):
    c = make_coordinator({})
    _verkoop(c, beschikbaar=5.01, veilig=5.02)
    c.beschikbare_energie_kwh = lambda: 5.05

    uitkomst = c.may_sell_now(NU)

    assert "dode zone" in uitkomst["reden"].lower() or "ruimte" in uitkomst["reden"].lower()


# --- de zonvangst -------------------------------------------------------


def _zon(c, verwacht_w, huis_w):
    c._get_expected_pv_power_w = lambda now: verwacht_w
    c._read_corrected_consumption_power = lambda: huis_w
    return c._should_capture_solar_instead_of_postponing(NU, True)


def test_een_klein_overschot_zet_de_zonvangst_niet_aan(make_coordinator, hass):
    """40 W overschot is een koelkast die net uit ging."""
    c = make_coordinator({})

    assert _zon(c, verwacht_w=500, huis_w=460) is False


def test_een_duidelijk_overschot_wel(make_coordinator, hass):
    c = make_coordinator({})

    assert _zon(c, verwacht_w=800, huis_w=460) is True


def test_eenmaal_aan_blijft_hij_aan_bij_een_klein_tekort(make_coordinator, hass):
    """Aan bij +340 W, en dan 30 W tekort door de waterkoker: aan laten."""
    c = make_coordinator({})
    _zon(c, verwacht_w=800, huis_w=460)

    assert _zon(c, verwacht_w=500, huis_w=530) is True


def test_een_duidelijk_tekort_zet_hem_uit(make_coordinator, hass):
    c = make_coordinator({})
    _zon(c, verwacht_w=800, huis_w=460)

    assert _zon(c, verwacht_w=300, huis_w=600) is False


def test_zonder_uitstel_geen_zonvangst(make_coordinator, hass):
    """De poort staat alleen open als de reserve toereikend is; dat is

    niet veranderd.
    """
    c = make_coordinator({})
    c._get_expected_pv_power_w = lambda now: 800
    c._read_corrected_consumption_power = lambda: 460

    assert c._should_capture_solar_instead_of_postponing(NU, False) is False


# --- het derde paar: default_smart <-> discharging_window ---------------
#
# Uit hetzelfde logboek, vier keer heen en terug binnen tien minuten,
# geclusterd rond 13:33-13:53 en 17:29-17:37: etenstijd. Hier zit geen
# poort zonder dode zone - de energiebrug heeft er een - maar de INVOER
# springt: een kookplaat wordt bevestigd (+0,6 kWh vaste post, v3.99.3),
# de volgende ronde niet meer (-0,6), de ronde erna wel. Een dode zone
# van 10% vangt geen stap van 0,6 kWh.
#
# De vaste post hoort te blijven staan voor het uur waarvoor hij bedoeld
# is, ook als de bevestiging tussendoor even wegvalt.


def _post(c, bron, wanneer):
    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: wanneer
    c.last_heavy_load_source = bron
    c._dishwasher_state = "rustend"
    c._washing_machine_state = "rustend"
    return c.lopend_witgoed_kwh_in_periode(wanneer, wanneer + timedelta(hours=2))


def test_de_vaste_post_blijft_het_uur_uit_staan(make_coordinator, hass):
    """Kookplaat gezien om 17:29, om 17:30 even niet bevestigd: post

    blijft.
    """
    c = make_coordinator({})
    t0 = datetime(2026, 9, 2, 17, 29, tzinfo=timezone.utc)

    assert _post(c, "kookplaat", t0) > 0
    assert _post(c, None, t0 + timedelta(minutes=1)) > 0
    assert _post(c, None, t0 + timedelta(minutes=45)) > 0


def test_na_het_uur_is_de_post_weg(make_coordinator, hass):
    c = make_coordinator({})
    t0 = datetime(2026, 9, 2, 17, 29, tzinfo=timezone.utc)
    _post(c, "kookplaat", t0)

    assert _post(c, None, t0 + timedelta(minutes=61)) == 0.0


def test_een_nieuwe_bevestiging_verlengt(make_coordinator, hass):
    """Wie om 18:15 nog kookt, kookt tot 19:15."""
    c = make_coordinator({})
    t0 = datetime(2026, 9, 2, 17, 29, tzinfo=timezone.utc)
    _post(c, "kookplaat", t0)
    _post(c, "kookplaat", t0 + timedelta(minutes=46))

    assert _post(c, None, t0 + timedelta(minutes=100)) > 0


# --- en de noodstop, die vandaag niet vuurde ---------------------------
#
# Gevraagd: "wil weten of dergelijke schakelingen elders ook zo vaak
# voorkomen." In het logboek van vandaag niet; in de code wel. De
# noodlading (winter, weinig zon verwacht) gaat aan bij `soc <= min` en
# stopt zodra de laadstand er een procent boven staat - waarna het huis
# hem er weer onder trekt. Dezelfde vorm als de verkooptoets, alleen op
# een moment dat het er meer toe doet.


def _nood(c, soc):
    c._is_low_solar_expected = lambda: True
    c.config = dict(c.config or {})
    c.config["battery_soc_sensor_entity"] = "sensor.soc"
    c.hass.states.set("sensor.soc", str(soc))
    c.effective_min_soc_percent = lambda: 10.0
    return c._is_emergency_low_battery()


def test_de_noodlading_gaat_aan_op_de_ondergrens(make_coordinator, hass):
    c = make_coordinator({})

    assert _nood(c, 10.0) is True


def test_en_stopt_niet_een_procent_erboven(make_coordinator, hass):
    c = make_coordinator({})
    _nood(c, 10.0)

    assert _nood(c, 11.0) is True
    assert _nood(c, 14.0) is True


def test_maar_wel_met_ruimte(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        EMERGENCY_LOW_BATTERY_EXIT_MARGIN_PERCENT,
    )

    c = make_coordinator({})
    _nood(c, 10.0)

    assert _nood(c, 10.0 + EMERGENCY_LOW_BATTERY_EXIT_MARGIN_PERCENT + 0.5) is False


def test_zonder_lopende_noodlading_geldt_de_ondergrens(make_coordinator, hass):
    """Wie NIET aan het noodladen is, hoeft bij 14% niets."""
    c = make_coordinator({})

    assert _nood(c, 14.0) is False


# --- v3.99.7: de reserve zelf springt, dus ook een tijd-dode-zone -------
#
# Met v3.99.6 draaiend, uit het logboek van 21:18:
#
#     21:03  verkopen   21:08  slim   21:15  verkopen   21:17  slim
#
# De dode zone op de VOORRAAD (0,25 kWh) hield niet. De reserve springt
# namelijk zelf tussen twee rondes: op een kwartiergrens verschuift de
# wandeling een kwartier, en de correctieverhouding ververst. Zakt de
# reserve 0,3 kWh, dan is de dode zone weg. Een dode zone op de voorraad
# helpt niet tegen een drempel die beweegt.
#
# Daarom ook een dode zone in de TIJD: eenmaal dicht, blijft hij minstens
# een kwartier dicht, wat de reserve ook doet. Stoppen blijft direct.


def test_binnen_een_kwartier_gaat_hij_niet_weer_open(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        SELL_REOPEN_MIN_MINUTES,
    )

    c = make_coordinator({})
    assert _verkoop(c, beschikbaar=5.01, veilig=5.02) is False
    # Volgende ronde zakt de reserve fors: ruimte zat, maar te snel.
    c._verkoop_dicht_sinds = NU
    assert _verkoop_op(c, NU + timedelta(minutes=5), beschikbaar=5.01, veilig=4.40) is False
    assert _verkoop_op(c, NU + timedelta(minutes=SELL_REOPEN_MIN_MINUTES + 1), beschikbaar=5.01, veilig=4.40) is True


def _verkoop_op(c, wanneer, beschikbaar, veilig):
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: veilig / 1.616
    c._reserve_margin_factor = lambda: 1.616
    c.last_cheap_block_start = BLOK
    return c.may_sell_now(wanneer)["mag_verkopen"]
