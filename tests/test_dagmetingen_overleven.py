"""Dagmetingen overleven een herstart (v4.7).

Uit de export van 10 september 06:58, in beide dagrecords:

    laagste_soc_ochtend: null

De meting loopt tussen 03:00 en 09:00; het record wordt om middernacht
geschreven. Daartussen zaten gisteren twee herstarts, en geen van de
dagvelden wordt bewaard. Elke herstart wist ze stilzwijgend.

Dat geldt voor alle metingen die een DAG beslaan en pas bij de dagwissel
worden vastgelegd: de laagste ochtendstand, de netimport 's nachts, de
kookpiek-vlag, het hoogste ontlaadvermogen, wat de lange horizon extra
vasthield, en de tekort- en overschotvlag zelf. Zonder die metingen kan
`lange_horizon_effect` niet zeggen of de horizon de ochtenden heeft
geholpen - en dat is precies waarvoor hij is gebouwd.

Dit is dezelfde klasse als de kijkvelden van v3.92: een veld dat maar op
één plek wordt gezet en nergens bewaard. Ik heb die klasse deze week
opgeruimd en hem in v3.99.18 zelf opnieuw ingebouwd.
"""
import pytest

from custom_components.energy_management_system.const import (
    PERSISTED_DATE_FIELDS,
    PERSISTED_PLAIN_FIELDS,
)

DAGVELDEN = (
    "_laagste_soc_ochtend",
    "_netimport_nacht_kwh",
    "_lange_horizon_extra_vandaag",
    "_max_ontlaad_w_vandaag",
    "_vermogensgrens_gezien_today",
    "_shortfall_detected_today",
    "_excess_detected_today",
)


def test_elke_dagmeting_wordt_bewaard():
    ontbreekt = sorted(set(DAGVELDEN) - set(PERSISTED_PLAIN_FIELDS))

    assert not ontbreekt, ontbreekt


def test_de_dag_waarop_geteld_wordt_ook():
    """Zonder de datum begint de teller na een herstart aan een 'nieuwe'
    dag en worden de waarden meteen gewist."""
    assert "_shortfall_check_date" in PERSISTED_DATE_FIELDS


def test_de_metingen_komen_terug_na_een_herstart(make_coordinator, hass):
    from datetime import date

    bron = make_coordinator({})
    bron._laagste_soc_ochtend = 24.0
    bron._netimport_nacht_kwh = 0.35
    bron._max_ontlaad_w_vandaag = {"handmatig_ontladen": 1639.0}
    bron._vermogensgrens_gezien_today = True
    bron._shortfall_detected_today = True
    bron._shortfall_check_date = date(2026, 9, 10)

    verse = make_coordinator({})
    verse._apply_persisted_state(bron._collect_persisted_state())

    assert verse._laagste_soc_ochtend == 24.0
    assert verse._netimport_nacht_kwh == pytest.approx(0.35)
    assert verse._max_ontlaad_w_vandaag == {"handmatig_ontladen": 1639.0}
    assert verse._vermogensgrens_gezien_today is True
    assert verse._shortfall_detected_today is True
    assert verse._shortfall_check_date == date(2026, 9, 10)


def test_een_nieuwe_dag_wist_ze_alsnog(make_coordinator, hass):
    """De bewaring mag de dagwissel niet in de weg zitten."""
    from datetime import date, datetime, timezone

    c = make_coordinator({})
    c._shortfall_check_date = date(2026, 9, 9)
    c._laagste_soc_ochtend = 24.0
    c._shortfall_detected_today = True
    c.reserve_daily_records = []

    c._update_shortfall_detection(
        datetime(2026, 9, 10, 0, 1, tzinfo=timezone.utc), "discharging_window", 2.0, 1.0
    )

    assert c._shortfall_check_date == date(2026, 9, 10)
    assert c._laagste_soc_ochtend is None
    assert c._shortfall_detected_today is False
    assert c.reserve_daily_records[-1]["laagste_soc_ochtend"] == 24.0
