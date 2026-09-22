"""Twee waarschuwingen uit het log van 22 september (v5.14.3).

    00:35:40  Updating state for sensor...gacs_zelfbeoordeling took 2.622
              seconds.
    00:40:40  Onverwachte netimport van 211 W ... Telt als tekortdag; de
              marge op de reserve gaat omhoog als dit vaker gebeurt.

EEN - DE KWARTIERREEKS DIE PER RONDE MAT

`niet_ontladen_history` stond op 11.520 regels, honderd keer groter dan
al het andere in de opslag. De grens:

    self.niet_ontladen_history[-PROEFSTAND_LEDGER_DAYS * 96:]

96 per dag: één per kwartier. Maar de meting liep elke RONDE, en bij
60 seconden zijn dat er 1440 per dag. Bedoeld was 120 dagen aan
kwartieren; het werden 8 dagen, met vijftien keer zoveel regels. Dezelfde
klasse als de tijdvensters van v5.14.2 - een aantal dat een tijd bedoelde.

Nu één meting per kwartier, en de bestaande voorraad wordt bij het laden
teruggebracht naar één per kwartier.

TWEE - DE GACS-SENSOR, 2,6 SECONDEN

Niet na te spelen: hier duurt het 5 milliseconden, ook met de reeks van
11.520 regels erin. Eén sterk verband: in v3.99.20 kostte het trainen van
het regressiewoud 2,72 seconden, en de waarschuwing toen was "took 2.624
seconds". Het woud traint sindsdien in een executor, maar Python laat één
thread tegelijk rekenen - loopt de training precies terwijl de sensor
bijwerkt, dan kan die wachten.

Een vermoeden, geen bewijs. Daarom eerst METEN: de integratie houdt bij
hoe lang de sensor erover doet en of het woud op dat moment traint, en
zet dat in de diagnoseregel. Pas daarna repareren.

DRIE - DE LOGTEKST

"Telt als tekortdag" klopt sinds v5.7 niet meer: één moment telt niet,
pas meer dan 0,5 kWh bijgekocht over de nacht. En een WAARSCHUWING is te
zwaar voor een moment dat op zichzelf geen gevolg heeft.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _regel(moment):
    return {
        "moment": moment.isoformat(), "prijs_nu_ct": 20.0, "duurste_later_ct": 35.0,
        "waarde_later_ct": 30.0, "voordeel_ct_per_kwh": 4.0, "vermogen_w": 300, "tekort_w": 0,
    }


# --- de kwartierreeks ---------------------------------------------------


def test_een_meting_per_kwartier(make_coordinator, hass):
    c = make_coordinator({})
    c.niet_ontladen_history = []

    for minuut in range(0, 30):
        c._noteer_niet_ontladen(NU + timedelta(minutes=minuut), _regel(NU + timedelta(minutes=minuut)))

    assert len(c.niet_ontladen_history) == 2      # 12:00 en 12:15


def test_de_voorraad_gaat_terug_naar_een_per_kwartier(make_coordinator, hass):
    """Instroom en voorraad: de 11.520 bestaande regels ook."""
    c = make_coordinator({})
    per_minuut = [_regel(NU + timedelta(minutes=m)) for m in range(60)]

    c._apply_persisted_state({"niet_ontladen_history": per_minuut})

    assert len(c.niet_ontladen_history) == 4      # vier kwartieren in een uur


def test_de_grens_beslaat_de_bedoelde_dagen(make_coordinator, hass):
    from custom_components.energy_management_system.const import PROEFSTAND_LEDGER_DAYS

    c = make_coordinator({})
    c.niet_ontladen_history = []
    for kwartier in range(PROEFSTAND_LEDGER_DAYS * 96 + 50):
        moment = NU + timedelta(minutes=15 * kwartier)
        c._noteer_niet_ontladen(moment, _regel(moment))

    assert len(c.niet_ontladen_history) == PROEFSTAND_LEDGER_DAYS * 96


# --- de GACS-sensor meten -----------------------------------------------


def test_de_duur_van_de_gacs_sensor_wordt_gemeten(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import GacsAssessmentSensor

    c = make_coordinator({})
    GacsAssessmentSensor(c, "x").extra_state_attributes

    assert c.gacs_duur_ms is not None
    assert c.gacs_duur_ms >= 0


def test_een_trage_keer_wordt_bewaard_met_of_het_woud_trainde(make_coordinator, hass):
    c = make_coordinator({})
    c._pv_model_bezig = True

    c._noteer_gacs_duur(2622.0)

    assert c.gacs_traag[-1]["ms"] == 2622.0
    assert c.gacs_traag[-1]["woud_trainde"] is True


def test_een_snelle_keer_wordt_niet_bewaard(make_coordinator, hass):
    c = make_coordinator({})
    c.gacs_traag = []

    c._noteer_gacs_duur(5.0)

    assert c.gacs_traag == []


def test_de_diagnoseregel_toont_de_traagste_keer(make_coordinator, hass):
    from test_alles_uitgevraagd import _maximaal

    c = make_coordinator(_maximaal())
    c._pv_model_bezig = True
    c._noteer_gacs_duur(2622.0)

    regel = c.diagnose_regel("gezondheid")

    assert "gacs" in regel and "2622" in regel and "woud" in regel


@pytest.mark.asyncio
async def test_de_trainingsvlag_staat_alleen_aan_tijdens_het_trainen(make_coordinator, hass):
    c = make_coordinator({})
    c._pv_model_berekend_op = None
    tijdens = []

    def trainen():
        tijdens.append(c._pv_model_bezig)
        return {}

    c._bereken_pv_model_evaluatie = trainen

    async def executor(functie, *args):
        return functie(*args)

    hass.async_add_executor_job = executor
    await c.async_ververs_pv_model(NU)

    assert tijdens == [True]
    assert c._pv_model_bezig is False


# --- de logtekst --------------------------------------------------------


def test_de_logtekst_zegt_niet_meer_dat_een_moment_een_tekortdag_is():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("Onverwachte netimport van %.0f W")
    blok = bron[i - 400 : i + 500]

    assert "Telt als tekortdag; de marge" not in blok
    assert "_LOGGER.info" in blok
