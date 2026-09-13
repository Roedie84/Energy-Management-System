"""Werkstand van de accu en zelfconsumptie via de accu (v1.16.9).

Twee samenhangende meldingen:

1. "Als de accu alleen door PV of gedeeltelijk door PV is geladen, blijft
   het toch zelfconsumptie, alleen niet direct uit PV maar dan vanuit de
   accu?"

   Terecht. De begrenzing uit v1.9.2 kapte de export op de dagopwek, maar
   ging er nog steeds van uit dat export ZON is zolang er die dag genoeg
   scheen. Op de ochtend van 9 augustus was de opwek 0,215 kWh en de
   export 0,56 kWh - dat gaf 0% zelfconsumptie, terwijl die export uit de
   accu kwam en de zon juist volledig naar het huis ging.

2. "De accu laadt nu op, sensor.zendure_manager_power = -500W ik weet
   niet welke entiteit jij gebruikt? Gaat vooral om dat dit goed gaat en
   er geen foutje in sluipt." En daarna: "Er is nog een betere weg,
   sensor.zendure_manager_operation_state".

   Terechte zorg: bij deze installatie staat `invert_battery_power_sign`
   op True, en of dat klopt was uit een export niet vast te stellen. Een
   tekenfout zou laden als ontladen tellen, wat rechtstreeks doorwerkt in
   de zelfconsumptie. De werkstandsensor zegt het zonder interpretatie.
"""
from custom_components.energy_management_system.const import (
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_STATE_SENSOR,
    CONF_INVERT_BATTERY_POWER_SIGN,
)


# --- 1. de werkstand ------------------------------------------------


def test_the_state_sensor_decides(make_coordinator, hass):
    """Zendure levert Nederlandse labels: Laden / Ontladen / Inactief."""
    c = make_coordinator({CONF_BATTERY_STATE_SENSOR: "sensor.werkstand"})

    hass.states.set("sensor.werkstand", "Ontladen")
    assert c.is_battery_discharging() is True

    hass.states.set("sensor.werkstand", "Laden")
    assert c.is_battery_discharging() is False

    # v1.21.4: "Inactief" blijft een BEKENDE werkstand die "doet niets"
    # betekent. Zou hij terugvallen op het vermogen, dan telde een
    # ruststroom van een paar honderd watt als ontlading.
    #
    # Alleen ONBEKENDE waarden vallen nu terug op het vermogen. Dat kwam
    # uit een gemeld geval: `battery_discharge_today_kwh` bleef op 0,0
    # staan terwijl er 's nachts wel ontladen werd, waardoor de
    # zelfconsumptie op 12,7% bleef hangen.
    hass.states.set("sensor.werkstand", "Inactief")
    assert c.is_battery_discharging() is False


def test_english_labels_work_too(make_coordinator, hass):
    """Een andere taalinstelling of merk mag de meting niet stilzetten."""
    c = make_coordinator({CONF_BATTERY_STATE_SENSOR: "sensor.werkstand"})

    hass.states.set("sensor.werkstand", "discharging")

    assert c.is_battery_discharging() is True


def test_the_state_beats_a_wrong_sign(make_coordinator, hass):
    """De kern van de zorg: ook met een verkeerd ingestelde omkering
    blijft het oordeel juist."""
    c = make_coordinator(
        {
            CONF_BATTERY_STATE_SENSOR: "sensor.werkstand",
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
            CONF_INVERT_BATTERY_POWER_SIGN: True,
        }
    )
    hass.states.set("sensor.accu_w", "-500")   # zou na inversie +500 zijn
    hass.states.set("sensor.werkstand", "Laden")

    assert c.is_battery_discharging() is False


def test_it_falls_back_to_the_power_sign(make_coordinator, hass):
    """Zonder werkstandsensor moet de meting blijven werken; het
    alternatief zou zijn dat ze helemaal stopt."""
    c = make_coordinator(
        {CONF_BATTERY_POWER_SENSOR: "sensor.accu_w"}
    )
    hass.states.set("sensor.accu_w", "500")

    assert c.is_battery_discharging() is True


def test_without_any_sensor_it_says_nothing(make_coordinator, hass):
    c = make_coordinator({})

    assert c.is_battery_discharging() is None


# --- 2. zelfconsumptie via de accu ----------------------------------


def _verhouding(make_coordinator, opwek, export, ontladen):
    c = make_coordinator({})
    c.pv_production_today_kwh = opwek
    c.pv_export_today_kwh = export
    c.battery_discharge_today_kwh = ontladen
    return c.self_consumption_ratio_percent


def test_battery_export_is_not_solar_export(make_coordinator, hass):
    """Verkoopt de accu 4 kWh van de 6 kWh export, dan is maar 2 kWh
    daadwerkelijk zon die het net op ging."""
    verhouding = _verhouding(make_coordinator, 15.5, 6.0, 4.0)

    assert verhouding == 87.1


def test_solar_through_the_battery_counts_as_self_consumption(
    make_coordinator, hass
):
    """Het punt uit de melding: opgeslagen zon die later in huis wordt
    gebruikt, is nog steeds zelf verbruikt."""
    zonder_accu = _verhouding(make_coordinator, 15.5, 4.0, 0.0)
    met_accu = _verhouding(make_coordinator, 15.5, 4.0, 4.0)

    assert met_accu == 100.0
    assert met_accu > zonder_accu


def test_direct_export_still_lowers_the_ratio(make_coordinator, hass):
    """De correctie mag geen truc worden die alles op 100% zet."""
    verhouding = _verhouding(make_coordinator, 15.5, 4.0, 0.0)

    assert verhouding is not None
    assert verhouding < 100


def test_no_export_means_everything_was_used(make_coordinator, hass):
    assert _verhouding(make_coordinator, 10.0, 0.0, 0.0) == 100.0


def test_it_never_leaves_the_zero_to_hundred_range(make_coordinator, hass):
    """De oorspronkelijke melding was -244,6%; dat mag niet terugkomen."""
    for opwek, export, ontladen in (
        (1.0, 50.0, 50.0),
        (1.0, 50.0, 0.0),
        (20.0, 0.0, 15.0),
        (5.0, 5.0, 2.0),
    ):
        verhouding = _verhouding(make_coordinator, opwek, export, ontladen)
        assert verhouding is None or 0 <= verhouding <= 100


# --- de dagteller ----------------------------------------------------


def test_the_discharge_counter_resets_daily():
    """Zonder dagreset telt de ontlading van gisteren door en wordt de
    zelfconsumptie kunstmatig hoog."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("self._self_sufficiency_day_key = today_key")

    assert "battery_discharge_today_kwh = 0.0" in bron[start : start + 400]


def test_the_config_field_exists():
    """Zonder configuratieveld is de werkstandsensor niet in te
    stellen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "config_flow.py").read_text()

    # De constante wordt via de naam gebruikt, niet als letterlijke
    # tekenreeks - daarop zoeken gaf een vals negatief.
    assert "CONF_BATTERY_STATE_SENSOR" in bron


# --- v1.21.4: exacte werkstand en een eigen sensor ------------------


def test_exact_matching_not_substrings(make_coordinator, hass):
    """"ontladen" bevat "laden" als deelwoord.

    Met een deelwoordvergelijking hing de uitkomst af van de volgorde
    waarin er wordt getoetst - en die keert stilzwijgend om zodra iemand
    die volgorde wijzigt. Nu exact.
    """
    c = _met_tv(make_coordinator, hass) if False else make_coordinator(
        {CONF_BATTERY_STATE_SENSOR: "sensor.werkstand"}
    )

    hass.states.set("sensor.werkstand", "ontladen")
    assert c.is_battery_discharging() is True

    hass.states.set("sensor.werkstand", "laden")
    assert c.is_battery_discharging() is False


def test_idle_is_a_known_state(make_coordinator, hass):
    """Zou "Inactief" terugvallen op het vermogen, dan telde een
    ruststroom van een paar honderd watt als ontlading."""
    c = make_coordinator(
        {
            CONF_BATTERY_STATE_SENSOR: "sensor.werkstand",
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
        }
    )
    hass.states.set("sensor.accu_w", "500")

    for waarde in ("Inactief", "standby", "idle"):
        hass.states.set("sensor.werkstand", waarde)
        assert c.is_battery_discharging() is False, waarde


def test_an_unknown_state_falls_back_to_power(make_coordinator, hass):
    """Gemeld geval: `battery_discharge_today_kwh` bleef op 0,0 staan
    terwijl er 's nachts wel ontladen werd, waardoor de zelfconsumptie
    op 12,7% bleef hangen. Een onbekende werkstand mag de meting niet
    stilzetten."""
    c = make_coordinator(
        {
            CONF_BATTERY_STATE_SENSOR: "sensor.werkstand",
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
        }
    )
    hass.states.set("sensor.accu_w", "500")
    hass.states.set("sensor.werkstand", "iets_onverwachts")

    assert c.is_battery_discharging() is True


def test_self_consumption_has_its_own_sensor():
    """Gemeld: de grafiek achter de zelfconsumptie-tegel toonde de
    zelfvoorziening (97,4%) in plaats van de zelfconsumptie (9,1%).

    Zelfconsumptie stond als attribuut op de zelfvoorzieningssensor, dus
    de tegel verwees naar diezelfde entiteit - en Home Assistant toont
    dan de geschiedenis van de hoofdwaarde.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()

    assert "class SelfConsumptionSensor" in bron
    assert 'SelfConsumptionSensor(coordinator, entry.entry_id)' in bron


def test_the_card_points_at_the_new_sensor():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )

    def zoek(kaarten):
        for k in kaarten or []:
            if not isinstance(k, dict):
                continue
            if "zelfconsumptieratio" in str(k.get("entity", "")):
                return True
            if zoek(k.get("cards")):
                return True
        return False

    gevonden = False
    for view in data["views"]:
        gevonden = gevonden or zoek(view.get("cards"))
        for sectie in view.get("sections") or []:
            gevonden = gevonden or zoek(sectie.get("cards"))

    assert gevonden
