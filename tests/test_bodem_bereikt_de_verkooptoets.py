"""De bodem bereikt de verkooptoets niet (v3.92.3).

Gemeten in de export van 31 augustus 10:11, met v3.92.2 al geïnstalleerd:

    reserve (bodem bindend)   1,296 kWh
    beschikbaar               0,69 kWh
    sell_check                mag_verkopen: true
                              vrij_te_verkopen_kwh: 0,69
                              nodig_voor_woning_kwh: 0,00

Er zit minder in de accu dan de reserve voorschrijft, en de verkooptoets
geeft alles vrij.

`may_sell_now` rekent `veilig = diepste * marge` zélf uit. Dat is de
VIERDE onafhankelijke reserveberekening, na de sturing, de
kwartierplanning en de uitsplitsing — en de enige die de bodem nog niet
kende. Het commentaar bij de bodem beweert al sinds v3.74.0 dat hij "op
ÉÉN plek staat zodat hij doorwerkt in het ontladen, de verkooptoets en
de kwartierplanning tegelijk". Dat was de bedoeling, niet de code.

Dat de overdracht dacht dat de bodem het verkopen wél stopte, komt
doordat op 31 augustus 06:51 een andere poort dichtstond: "planning
voorziet een tekort". Vandaag staat die open, en dan ligt er niets onder.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    RESERVE_BODEM_FRACTIE,
)

NU = datetime(2026, 8, 31, 10, 11, tzinfo=timezone.utc)
BLOK = NU + timedelta(hours=16)
CAPACITEIT = 8.64
BODEM = CAPACITEIT * RESERVE_BODEM_FRACTIE


def _toets(c, beschikbaar, diepste=0.0):
    c.bruikbare_capaciteit_kwh = lambda: CAPACITEIT
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: diepste
    c.last_cheap_block_start = BLOK
    return c.may_sell_now(NU)


# --- 1. de bodem in de verkooptoets -----------------------------------


def test_er_wordt_niet_verkocht_onder_de_bodem(make_coordinator, hass):
    """Het geval van 31 augustus 10:11 precies."""
    uitkomst = _toets(make_coordinator({}), beschikbaar=0.69)

    assert uitkomst["mag_verkopen"] is False


def test_de_bodem_staat_in_de_uitkomst(make_coordinator, hass):
    """Anders is niet te zien waarom er niet verkocht mag worden — en

    juist dat maakte dit zo lang onzichtbaar.
    """
    uitkomst = _toets(make_coordinator({}), beschikbaar=0.69)

    assert uitkomst["nodig_voor_woning_kwh"] == pytest.approx(BODEM, abs=0.01)


def test_alleen_wat_boven_de_bodem_zit_is_vrij(make_coordinator, hass):
    """Met 5,0 kWh in de accu en een bodem van 1,296 blijft er 3,7 over,

    niet de volle 5,0.
    """
    uitkomst = _toets(make_coordinator({}), beschikbaar=5.0)

    assert uitkomst["mag_verkopen"] is True
    assert uitkomst["vrij_te_verkopen_kwh"] == pytest.approx(
        5.0 - BODEM, abs=0.02
    )


def test_een_echt_tekort_wint_nog_steeds_van_de_bodem(make_coordinator, hass):
    """De bodem vervangt de berekening niet, hij staat eronder."""
    uitkomst = _toets(make_coordinator({}), beschikbaar=8.0, diepste=4.0)

    assert uitkomst["nodig_voor_woning_kwh"] > BODEM


def test_ook_de_terugval_zonder_uurprofiel_houdt_de_bodem(
    make_coordinator, hass
):
    """Zonder volledig uurprofiel valt de wandeling weg en rekent de

    toets met de oude nettosom. Die kende de bodem net zo min.
    """
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: CAPACITEIT
    c.beschikbare_energie_kwh = lambda: 0.69
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: None
    c._estimate_consumption_kwh_for_period = lambda a, b: 0.0
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c.last_cheap_block_start = BLOK

    assert c.may_sell_now(NU)["mag_verkopen"] is False


# --- 2. één definitie van de bodem ------------------------------------


def test_de_drie_gebruikers_rekenen_met_hetzelfde_getal(
    make_coordinator, hass
):
    """Sturing, planning en verkooptoets horen dezelfde bodem te zien.

    Vier losse berekeningen waren er al drie te veel.
    """
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: CAPACITEIT
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 0.0
    c.last_cheap_block_start = None

    uit_sturing = c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    uit_planning = c._planning_reserve_kwh(NU, {})

    assert uit_sturing == pytest.approx(BODEM, abs=0.01)
    assert uit_planning == pytest.approx(BODEM, abs=0.01)
    assert c._reserve_bodem_kwh() == pytest.approx(BODEM, abs=0.01)


def test_zonder_capaciteit_geen_verzonnen_bodem(make_coordinator, hass):
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: None

    assert c._reserve_bodem_kwh() == 0.0


# --- 3. het label op de meetkwaliteitskaart ---------------------------


def test_de_kaart_vraagt_niet_naar_een_correctie_die_er_niet_is(
    make_coordinator, hass
):
    """Gemeld met schermafdruk: "1 van de 27 gemeten grootheden is

    onbetrouwbaar: Zonvoorspelling (klopt de correctie nog?)".

    De melding klopt, het label niet: de vlakke bias is ingehouden en de
    vakcorrectie sinds v3.92.2 ook. Er ís geen correctie om naar te
    vragen.
    """
    c = make_coordinator({})

    namen = [r["naam"] for r in c.get_reliability_overview()]

    assert "Zonvoorspelling (klopt de correctie nog?)" not in namen
    assert any(naam.startswith("Zonvoorspelling") for naam in namen)


# --- 4. het trackerblok in de export ---------------------------------


def test_de_export_leest_de_verwijzing_die_altijd_bestaat():
    """v3.92.4, rechtzetting.

    In v3.92.3 stond hier dat `solar_forecast_tracker` uit de export van
    31 augustus 10:11 ontbrak. Dat was fout: het blok stond er wel,
    alleen op het hoogste niveau van `data` en niet onder `coordinator`.
    Er is nooit iets weggevallen.

    De terugval op `coordinator.solar_tracker` blijft staan omdat hij
    onschadelijk is en de export niet van één verwijzing laat afhangen.
    Deze toets legt alleen dat vast - hij vangt geen gemelde fout, en
    hoort dus niet gelezen te worden als bewijs dat er een was.
    """
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()
    boom = ast.parse(bron)

    toekenning = None
    for knoop in ast.walk(boom):
        if (
            isinstance(knoop, ast.Assign)
            and len(knoop.targets) == 1
            and isinstance(knoop.targets[0], ast.Name)
            and knoop.targets[0].id == "solar_tracker"
        ):
            toekenning = knoop
            break

    assert toekenning is not None, "geen toekenning van solar_tracker gevonden"
    assert isinstance(toekenning.value, ast.BoolOp)
    assert isinstance(toekenning.value.op, ast.Or)
