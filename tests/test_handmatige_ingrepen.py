"""Vastleggen wanneer de accu anders staat dan EMS wilde (v3.75.0).

Gevraagd: "Maar als ik iets manueel doe kan dat toch juist een leer voor
de integratie zijn?"

Terecht, en dat zat er niet in. Alle bestaande metingen vergelijken
alternatieven die de integratie ZELF had kunnen kiezen; een ingreep van
buitenaf is een derde optie die nergens werd opgemerkt.

De aanleiding: op 30 augustus is de accu handmatig op laden gezet omdat
het pas na tweeën zou opklaren en de planning de avond niet zou halen.
Dat is een oordeel dat de integratie niet had.

Dit legt alleen VAST. Geen patroon, geen conclusie, geen sturing.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    CONF_OPERATION_SELECT,
    HANDMATIGE_INGREPEN_MIN_VOOR_PATROON,
)

NU = datetime(2026, 8, 30, 11, 0)


def _coordinator(make_coordinator, hass, werkelijk, gewenst):
    c = make_coordinator({CONF_OPERATION_SELECT: "select.modus"})
    hass.states.set("select.modus", werkelijk)
    c.last_applied_operation = gewenst
    return c


# --- de ingreep van 30 augustus --------------------------------------


def test_a_manual_change_is_recorded(make_coordinator, hass):
    """EMS wilde `smart`, de accu staat op `manual` omdat er handmatig

    is bijgeladen.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")

    c._volg_handmatige_ingrepen(NU)

    assert len(c.handmatige_ingrepen) == 1
    regel = c.handmatige_ingrepen[0]
    assert regel["ems_wilde"] == "smart"
    assert regel["werkelijk"] == "manual"


def test_the_circumstances_are_recorded_too(make_coordinator, hass):
    """Daar zit de mogelijke regel in: bij welke prijs, welke accustand

    en hoeveel verwachte zon greep de gebruiker in?
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")
    c.voorspelde_zon_vandaag_kwh = lambda now=None: (10.2, "toets")

    c._volg_handmatige_ingrepen(NU)

    regel = c.handmatige_ingrepen[0]
    for sleutel in (
        "accustand_procent",
        "beschikbaar_kwh",
        "prijs_nu_ct",
        "duurste_vandaag_ct",
        "verwachte_zon_kwh",
        "reden_ems",
    ):
        assert sleutel in regel
    assert regel["verwachte_zon_kwh"] == 10.2


def test_matching_modes_record_nothing(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, "smart", "smart")

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen == []


# --- één regel per periode -------------------------------------------


def test_one_line_per_period_not_per_round(make_coordinator, hass):
    """Anders staat er na een middag handmatig laden honderd keer

    hetzelfde.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")

    for minuut in range(0, 120, 5):
        c._volg_handmatige_ingrepen(NU + timedelta(minutes=minuut))

    assert len(c.handmatige_ingrepen) == 1


def test_a_new_period_is_recorded_again(make_coordinator, hass):
    """Terug naar normaal en dan opnieuw ingrijpen is een tweede

    waarneming.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")
    c._volg_handmatige_ingrepen(NU)

    hass.states.set("select.modus", "smart")
    c._volg_handmatige_ingrepen(NU + timedelta(hours=3))

    hass.states.set("select.modus", "manual")
    c._volg_handmatige_ingrepen(NU + timedelta(hours=4))

    assert len(c.handmatige_ingrepen) == 2


# --- wanneer er niets te vergelijken valt ----------------------------


def test_without_a_desired_mode_nothing_is_recorded(
    make_coordinator, hass
):
    """Vlak na het opstarten, of in leermodus waarin EMS niets schrijft."""
    c = _coordinator(make_coordinator, hass, "manual", None)

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen == []


def test_an_unavailable_entity_records_nothing(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, "unavailable", "smart")

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen == []


# --- geen conclusies -------------------------------------------------


def test_it_draws_no_conclusion_from_one_case(make_coordinator, hass):
    """Eén waarneming is geen patroon, en deze week is het vijf keer

    misgegaan dat er iets werd gebouwd op grond van één geval.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")
    c._volg_handmatige_ingrepen(NU)

    overzicht = c.get_handmatige_ingrepen()

    assert overzicht["aantal"] == 1
    assert overzicht["genoeg_voor_een_patroon"] is False


def test_enough_cases_says_so(make_coordinator, hass):
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        {"moment": "x"} for _ in range(HANDMATIGE_INGREPEN_MIN_VOOR_PATROON)
    ]

    assert c.get_handmatige_ingrepen()["genoeg_voor_een_patroon"] is True


def test_it_steers_nothing(make_coordinator, hass):
    import ast
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    for fn in (C._volg_handmatige_ingrepen, C.get_handmatige_ingrepen):
        boom = ast.parse(inspect.getsource(fn).lstrip())
        aanroepen = {
            n.func.attr
            for n in ast.walk(boom)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert "_async_apply_operation" not in aanroepen
        assert "_async_apply_manual" not in aanroepen


def test_it_reaches_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert '"handmatige_ingrepen"' in bron


# --- het gat van 30 augustus (v3.76.0) -------------------------------


def test_an_intervention_before_the_first_write_is_recorded(
    make_coordinator, hass
):
    """Gemeten in de export van 30 augustus 10:16:

        select.zendure_manager_operation = off
        last_applied_operation           = None
        handmatige ingrepen              = 0

    De accu stond handmatig op laden, en juist die ingreep werd niet
    vastgelegd. `last_applied_operation` wordt pas gevuld zodra EMS zelf
    schrijft, en dat was sinds de herstart niet gebeurd - want de manager
    stond op `off`.

    Precies verkeerd om: een ingreep die vóór of tijdens een herstart
    begint, is er een die je juist wilt zien.
    """
    c = make_coordinator({CONF_OPERATION_SELECT: "select.modus"})
    hass.states.set("select.modus", "off")
    c.last_applied_operation = None
    c.last_reason = "default_smart"

    c._volg_handmatige_ingrepen(NU)

    assert len(c.handmatige_ingrepen) == 1
    regel = c.handmatige_ingrepen[0]
    assert regel["werkelijk"] == "off"
    assert regel["uit_beslissing"] is True


def test_a_written_mode_still_wins(make_coordinator, hass):
    """Wat EMS werkelijk heeft geschreven is nauwkeuriger dan wat uit de

    beslissing valt af te leiden.
    """
    c = make_coordinator({CONF_OPERATION_SELECT: "select.modus"})
    hass.states.set("select.modus", "manual")
    c.last_applied_operation = "smart_discharging"
    c.last_reason = "default_smart"

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen[0]["ems_wilde"] == "smart_discharging"
    assert c.handmatige_ingrepen[0]["uit_beslissing"] is False


def test_without_a_decision_either_nothing_is_recorded(
    make_coordinator, hass
):
    """Vlak na het opstarten, vóór de eerste ronde: dan is er niets om

    tegen te vergelijken en is zwijgen het juiste.
    """
    c = make_coordinator({CONF_OPERATION_SELECT: "select.modus"})
    hass.states.set("select.modus", "off")
    c.last_applied_operation = None
    c.last_reason = None

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen == []


@pytest.mark.parametrize(
    "reden,verwacht",
    [
        ("default_smart", "smart"),
        ("expensive_quarter", "manual"),
        ("discharging_window", "smart_discharging"),
        ("arbitrage_solar_capture", "smart"),
    ],
)
def test_the_decision_maps_to_a_mode(
    make_coordinator, hass, reden, verwacht
):
    """De vertaling is bewust grof: het gaat erom of de accu ergens

    ANDERS staat dan bedoeld, niet om het precieze verschil.
    """
    c = make_coordinator({})

    assert c._modus_bij_beslissing(reden) == verwacht


# --- niet meten wat de integratie zelf doet (v3.82.0) ----------------


def test_learning_mode_is_not_an_intervention(make_coordinator, hass):
    """Gemeten in de export van 30 augustus 14:33: zeven ingrepen in

    veertig minuten, terwijl er hooguit twee waren gedaan. Vier daarvan
    waren van de vorm:

        EMS wilde smart_discharging, werkelijk smart

    Dat is geen ingreep van de gebruiker maar de LEERMODUS: EMS schrijft
    dan niets, dus staat de accu vanzelf ergens anders dan de beslissing
    zegt. Daar valt niets van te leren.
    """
    c = _coordinator(make_coordinator, hass, "smart", None)
    c.last_reason = "discharging_window"
    c.learning_only = True

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen == []


def test_force_manual_is_not_an_intervention(make_coordinator, hass):
    """Dezelfde reden: dan stuurt de gebruiker via een andere schakelaar

    en is de afwijking geen verrassing.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")
    c.force_manual = True

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen == []


def test_the_same_pair_is_recorded_once(make_coordinator, hass):
    """In dezelfde export stonden 14:19:48 en 14:20:57 allebei, met

    precies dezelfde inhoud. De periode-markering hing aan een tijdstip
    dat elders weer op None werd gezet; hij hangt nu aan het PAAR
    (gewenst, werkelijk), en dat verandert niet zolang de ingreep duurt.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")

    for minuut in (0, 1, 2, 15, 60):
        c._volg_handmatige_ingrepen(NU + timedelta(minutes=minuut))

    assert len(c.handmatige_ingrepen) == 1


def test_a_different_pair_is_a_new_period(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, "manual", "smart")
    c._volg_handmatige_ingrepen(NU)

    hass.states.set("select.modus", "smart_charging")
    c._volg_handmatige_ingrepen(NU + timedelta(minutes=5))

    assert len(c.handmatige_ingrepen) == 2


# --- en ervan leren --------------------------------------------------


def _ingreep(prijs=13.0, duurste=38.8, soc=70.0, zon=10.8, dag=30,
             richting="laden"):
    """v3.85.0: elke ingreep krijgt een eigen DAG.

    De vorige versie zette ze allemaal op 30 augustus - precies de fout
    die in de export van die dag naar boven kwam: twaalf ingrepen op één
    dag hebben per definitie dezelfde duurste prijs en zonverwachting.
    """
    return {
        "moment": f"2026-08-{dag:02d}T14:00:00+02:00",
        "richting": richting,
        "prijs_nu_ct": prijs,
        "duurste_vandaag_ct": duurste,
        "accustand_procent": soc,
        "verwachte_zon_kwh": zon,
    }


def test_a_pattern_needs_enough_cases(make_coordinator, hass):
    c = make_coordinator({})
    c.handmatige_ingrepen = [_ingreep(dag=10 + i) for i in range(3)]

    assert c._patroon_in_de_ingrepen()["beschikbaar"] is False


def test_consistent_circumstances_form_a_line(make_coordinator, hass):
    """Elke keer bij ongeveer dezelfde prijs en dezelfde verwachte zon:

    dan lijkt elke ingreep op de vorige.
    """
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        _ingreep(prijs=13.0 + i * 0.2, zon=10.8 + i * 0.1, dag=10 + i)
        for i in range(HANDMATIGE_INGREPEN_MIN_VOOR_PATROON)
    ]

    patroon = c._patroon_in_de_ingrepen()

    assert patroon["heeft_lijn"] is True
    assert "prijs_nu_ct" in patroon["consistente_kenmerken"]


def test_scattered_circumstances_are_no_line(make_coordinator, hass):
    """Gaat een kenmerk alle kanten op, dan is er geen regel - en dan

    hoort de integratie dat te zeggen in plaats van iets te verzinnen.
    """
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        _ingreep(prijs=5.0 + i * 8, soc=10.0 + i * 9, zon=1.0 + i * 3,
                 dag=10 + i)
        for i in range(HANDMATIGE_INGREPEN_MIN_VOOR_PATROON)
    ]

    patroon = c._patroon_in_de_ingrepen()

    assert patroon["heeft_lijn"] is False


def test_the_pattern_is_in_the_overview(make_coordinator, hass):
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        _ingreep(dag=10 + i)
        for i in range(HANDMATIGE_INGREPEN_MIN_VOOR_PATROON)
    ]

    assert c.get_handmatige_ingrepen()["patroon"]["beschikbaar"] is True


def test_the_pattern_steers_nothing(make_coordinator, hass):
    import ast
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    boom = ast.parse(inspect.getsource(C._patroon_in_de_ingrepen).lstrip())
    aanroepen = {
        n.func.attr
        for n in ast.walk(boom)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }

    assert "_async_apply_operation" not in aanroepen
    assert "_async_apply_manual" not in aanroepen


# --- de fout van 30 augustus (v3.85.0) -------------------------------


def test_one_day_is_never_a_pattern(make_coordinator, hass):
    """Gemeten in de export van 30 augustus 20:24. Twaalf ingrepen,

    allemaal op diezelfde dag, en de analyse meldde een lijn met drie
    consistente kenmerken:

        duurste_vandaag_ct   38,8  altijd
        verwachte_zon_kwh    10,8  altijd

    Twee daarvan zijn DAGwaarden. Twaalf ingrepen op één dag hebben per
    definitie dezelfde duurste prijs en dezelfde zonverwachting; dat is
    geen patroon maar een telfout.
    """
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        _ingreep(dag=30) for _ in range(12)
    ]

    patroon = c._patroon_in_de_ingrepen()

    assert patroon["beschikbaar"] is False
    assert "dag(en)" in patroon["reden"]


def test_enough_days_does_produce_a_pattern(make_coordinator, hass):
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        _ingreep(dag=10 + i)
        for i in range(HANDMATIGE_INGREPEN_MIN_VOOR_PATROON)
    ]

    patroon = c._patroon_in_de_ingrepen()

    assert patroon["beschikbaar"] is True
    assert patroon["dagen"] >= 3


# --- laden en ontladen apart -----------------------------------------


def test_charging_and_discharging_are_counted_apart(
    make_coordinator, hass
):
    """Gemeten op 30 augustus: om 14:22 ging de stand van 67 naar 78% bij

    13 ct, en om 18:45 van 96 naar 90% bij 37 ct. Dat zijn twee
    TEGENGESTELDE beslissingen, en op één hoop geteld is de mediaanprijs
    van 13 en 37 ct betekenisloos.
    """
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        _ingreep(prijs=13.0, soc=70.0, dag=10 + i, richting="laden")
        for i in range(5)
    ] + [
        _ingreep(prijs=37.0, soc=95.0, dag=20 + i, richting="ontladen")
        for i in range(5)
    ]

    per = c._patroon_in_de_ingrepen()["per_richting"]

    assert per["laden"]["prijs_ct"]["mediaan"] == 13.0
    assert per["ontladen"]["prijs_ct"]["mediaan"] == 37.0
    assert per["laden"]["accustand_procent"]["mediaan"] == 70.0


def test_too_few_of_one_kind_says_so(make_coordinator, hass):
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        _ingreep(dag=10 + i, richting="laden") for i in range(10)
    ]

    per = c._patroon_in_de_ingrepen()["per_richting"]

    assert per["laden"]["genoeg"] is True
    assert per["ontladen"]["genoeg"] is False


def test_the_direction_comes_from_the_power(make_coordinator, hass):
    """Uit het accuvermogen, want dat is wat er WERKELIJK gebeurt - de

    modus zegt alleen wat er bedoeld was.
    """
    from custom_components.energy_management_system.const import (
        CONF_BATTERY_POWER_SENSOR,
    )

    c = make_coordinator({CONF_BATTERY_POWER_SENSOR: "sensor.accu"})

    hass.states.set("sensor.accu", "-1800")
    assert c._richting_van_de_accu() == "laden"

    hass.states.set("sensor.accu", "1200")
    assert c._richting_van_de_accu() == "ontladen"

    hass.states.set("sensor.accu", "12")
    assert c._richting_van_de_accu() == "stil"


def test_the_sun_shortfall_is_recorded(make_coordinator, hass):
    """Gemeten op 30 augustus: verwacht 10,8 kWh, gemeten 6,04 - 44%

    eronder. De ingreep om 14:22 was dus terecht: de accu zou het op zon
    alleen niet gehaald hebben.

    Dat is de correlatie die ertoe doet - niet de voorspelling alleen,
    maar het VERSCHIL tussen wat het model beloofde en wat er kwam.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")
    c.voorspelde_zon_vandaag_kwh = lambda now=None: (10.8, "toets")
    c.pv_production_today_kwh = 6.04

    c._volg_handmatige_ingrepen(NU)

    regel = c.handmatige_ingrepen[0]
    assert regel["zon_tot_nu_kwh"] == 6.04
    assert 0 < regel["deel_van_de_dag"] < 1


def test_a_lagging_sun_shows_in_the_pattern(make_coordinator, hass):
    """Onder de 1 betekent dat de zon achterliep op de voorspelling."""
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        dict(
            _ingreep(dag=10 + i, richting="laden"),
            zon_tot_nu_kwh=3.0,
            deel_van_de_dag=14 / 24,
            verwachte_zon_kwh=10.8,
        )
        for i in range(HANDMATIGE_INGREPEN_MIN_VOOR_PATROON)
    ]

    per = c._patroon_in_de_ingrepen()["per_richting"]["laden"]

    assert per["zon_tegenover_voorspelling"] is not None
    # 3,0 kWh gemeten waar er op dat punt van de dag 5,8 verwacht mocht
    # worden: de zon liep ver achter, en dat rechtvaardigt bijladen.
    assert per["zon_tegenover_voorspelling"] < 1.0
