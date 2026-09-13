"""Accu-modulegezondheid (v0.63.123).

Gevraagd naar aanleiding van een screenshot met per module: hoogste/
laagste celspanning, hoogste celtemperatuur, SoC, stroom, vermogen en
pakspanning - "zit hier nog relevante info tussen om de gezondheid van
de accus te monitoren?"

Kern van het ontwerp: elke module wordt vergeleken met het gemiddelde
van de ANDERE modules op hetzelfde moment. Omdat alle modules onder
identieke omstandigheden draaien (zelfde SoC, zelfde omgeving, zelfde
belasting) valt alles wat ze delen weg en blijft over wat eigen is aan
die module. Dat lost meteen het lastigste probleem op: bij LFP is het
celspanningsverschil sterk SoC-afhankelijk (vlak in het midden, steil
aan de uiteinden), waardoor een absolute waarde niet over de tijd met
zichzelf te vergelijken is.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    BATTERY_MODULE_CELL_DELTA_ATTENTION_V,
    BATTERY_MODULE_CUSUM_THRESHOLD_C,
    BATTERY_MODULE_MIN_SAMPLES_PER_DAY,
    CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS,
    CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS,
    CONF_BATTERY_MODULE_POWER_SENSORS,
    CONF_BATTERY_MODULE_SOC_SENSORS,
    CONF_BATTERY_MODULE_TEMPERATURE_SENSORS,
    CUSUM_MIN_HISTORY_FOR_REFERENCE,
)

DAY0 = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _config(aantal=3):
    return {
        CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS: [
            f"sensor.accu{i}_cel_max" for i in range(1, aantal + 1)
        ],
        CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS: [
            f"sensor.accu{i}_cel_min" for i in range(1, aantal + 1)
        ],
        CONF_BATTERY_MODULE_TEMPERATURE_SENSORS: [
            f"sensor.accu{i}_temp" for i in range(1, aantal + 1)
        ],
        CONF_BATTERY_MODULE_SOC_SENSORS: [
            f"sensor.accu{i}_soc" for i in range(1, aantal + 1)
        ],
        CONF_BATTERY_MODULE_POWER_SENSORS: [
            f"sensor.accu{i}_power" for i in range(1, aantal + 1)
        ],
    }


def _zet(hass, module, cel_max, cel_min, temp, soc, power=600):
    hass.states.set(f"sensor.accu{module}_cel_max", str(cel_max))
    hass.states.set(f"sensor.accu{module}_cel_min", str(cel_min))
    hass.states.set(f"sensor.accu{module}_temp", str(temp))
    hass.states.set(f"sensor.accu{module}_soc", str(soc))
    hass.states.set(f"sensor.accu{module}_power", str(power))


def _gezonde_situatie(hass):
    """De situatie uit de screenshot: keurig in balans."""
    _zet(hass, 1, 3.35, 3.34, 28.0, 49, 597)
    _zet(hass, 2, 3.34, 3.33, 27.0, 48, 700)
    _zet(hass, 3, 3.34, 3.34, 26.0, 47, 566)


# --- basis: uitlezen en afleiden -----------------------------------


def test_reads_all_three_modules(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _gezonde_situatie(hass)

    coordinator._update_battery_module_health(DAY0)

    assert len(coordinator.battery_module_live) == 3
    assert [m["module"] for m in coordinator.battery_module_live] == [1, 2, 3]


def test_cell_delta_is_derived(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _gezonde_situatie(hass)

    coordinator._update_battery_module_health(DAY0)

    deltas = [m["cel_delta_v"] for m in coordinator.battery_module_live]
    assert deltas == [0.01, 0.01, 0.0]


def test_no_modules_configured_is_a_clean_no_op(make_coordinator, hass):
    coordinator = make_coordinator({})

    coordinator._update_battery_module_health(DAY0)

    assert coordinator.battery_module_live == []
    assert coordinator.get_battery_module_table() == []


def test_a_module_survives_one_missing_reading(make_coordinator, hass):
    """Een tijdelijk onbereikbare sensor mag niet de hele module uit de
    weergave laten verdwijnen."""
    coordinator = make_coordinator(_config())
    _gezonde_situatie(hass)
    hass.states.set("sensor.accu2_temp", "unavailable")

    coordinator._update_battery_module_health(DAY0)

    assert len(coordinator.battery_module_live) == 3
    module2 = coordinator.battery_module_live[1]
    assert module2["temperatuur_c"] is None
    assert module2["cel_delta_v"] == 0.01


def test_lists_of_unequal_length_are_allowed(make_coordinator, hass):
    """Wel celspanningen, geen vermogen per module - moet gewoon
    werken."""
    config = _config()
    del config[CONF_BATTERY_MODULE_POWER_SENSORS]
    coordinator = make_coordinator(config)
    _gezonde_situatie(hass)

    coordinator._update_battery_module_health(DAY0)

    assert len(coordinator.battery_module_live) == 3
    assert coordinator.battery_module_live[0]["vermogen_w"] is None


# --- de differentiële vergelijking ---------------------------------


def test_deviation_excludes_the_module_itself(make_coordinator, hass):
    """Het gemiddelde waartegen wordt vergeleken mag de module zelf niet
    bevatten - anders trekt een uitschieter het gemiddelde met zich mee
    en wordt zijn eigen afwijking onderschat."""
    coordinator = make_coordinator(_config())
    _zet(hass, 1, 3.40, 3.30, 40.0, 50)  # de uitschieter
    _zet(hass, 2, 3.35, 3.34, 26.0, 50)
    _zet(hass, 3, 3.35, 3.34, 26.0, 50)

    coordinator._update_battery_module_health(DAY0)

    # 40 t.o.v. het gemiddelde van 26 en 26 = +14, niet +9.33.
    assert coordinator.battery_module_live[0]["temperatuur_afwijking_c"] == 14.0


def test_balanced_modules_have_near_zero_deviation(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _zet(hass, 1, 3.35, 3.34, 27.0, 48)
    _zet(hass, 2, 3.35, 3.34, 27.0, 48)
    _zet(hass, 3, 3.35, 3.34, 27.0, 48)

    coordinator._update_battery_module_health(DAY0)

    for module in coordinator.battery_module_live:
        assert module["temperatuur_afwijking_c"] == 0.0
        assert module["soc_afwijking_percent"] == 0.0


def test_deviation_is_none_with_a_single_module(make_coordinator, hass):
    """Met één module valt er niets te vergelijken."""
    coordinator = make_coordinator(_config(aantal=1))
    _zet(hass, 1, 3.35, 3.34, 27.0, 48)

    coordinator._update_battery_module_health(DAY0)

    assert coordinator.battery_module_live[0]["temperatuur_afwijking_c"] is None


def test_soc_dependence_cancels_out_in_the_deviation(make_coordinator, hass):
    """De kern van het ontwerp: bij LFP loopt de celdelta aan de
    uiteinden voor ALLE modules op. De absolute waarde verandert dus
    sterk, maar de onderlinge afwijking niet - en juist die wordt
    bewaakt."""
    coordinator = make_coordinator(_config())

    # Midden in het vlakke gebied.
    _zet(hass, 1, 3.350, 3.340, 27.0, 50)
    _zet(hass, 2, 3.340, 3.335, 27.0, 50)
    _zet(hass, 3, 3.340, 3.335, 27.0, 50)
    coordinator._update_battery_module_health(DAY0)
    midden = coordinator.battery_module_live[0]["cel_delta_afwijking_v"]

    # Aan het einde: alle deltas vier keer zo groot.
    _zet(hass, 1, 3.500, 3.460, 27.0, 98)
    _zet(hass, 2, 3.500, 3.480, 27.0, 98)
    _zet(hass, 3, 3.500, 3.480, 27.0, 98)
    coordinator._update_battery_module_health(DAY0)
    uiteinde = coordinator.battery_module_live[0]["cel_delta_afwijking_v"]

    # De absolute delta ging van 0,010 naar 0,040 V, maar de verhouding
    # tussen de modules bleef gelijk - de afwijking schaalt netjes mee
    # zonder dat één module ineens "verdacht" wordt.
    assert midden > 0
    assert uiteinde > midden
    assert coordinator.battery_module_live[1]["cel_delta_afwijking_v"] < 0


# --- absolute waarschuwingen ---------------------------------------


def test_high_cell_delta_is_flagged(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _zet(hass, 1, 3.45, 3.30, 27.0, 48)  # delta 0,15 V
    _zet(hass, 2, 3.35, 3.34, 27.0, 48)
    _zet(hass, 3, 3.35, 3.34, 27.0, 48)

    coordinator._update_battery_module_health(DAY0)

    tabel = coordinator.get_battery_module_table()
    assert any("celspanningsverschil" in w for w in tabel[0]["waarschuwingen"])
    assert tabel[1]["waarschuwingen"] == []


def test_serious_cell_delta_is_worded_more_strongly(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _zet(hass, 1, 3.55, 3.30, 27.0, 48)  # delta 0,25 V
    _zet(hass, 2, 3.35, 3.34, 27.0, 48)
    _zet(hass, 3, 3.35, 3.34, 27.0, 48)

    coordinator._update_battery_module_health(DAY0)

    assert any(
        "fors uit balans" in w
        for w in coordinator.get_battery_module_table()[0]["waarschuwingen"]
    )


def test_healthy_snapshot_produces_no_warnings(make_coordinator, hass):
    """De situatie uit de screenshot hoort schoon door te komen."""
    coordinator = make_coordinator(_config())
    _gezonde_situatie(hass)

    coordinator._update_battery_module_health(DAY0)

    for module in coordinator.get_battery_module_table():
        assert module["waarschuwingen"] == []


def test_spread_between_modules_is_tracked(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _gezonde_situatie(hass)

    coordinator._update_battery_module_health(DAY0)

    spreiding = coordinator.battery_module_spread
    assert spreiding["temperatuur_c"] == 2.0
    assert spreiding["soc_percent"] == 2.0


def test_large_temperature_spread_becomes_an_attention_point(
    make_coordinator, hass
):
    coordinator = make_coordinator(_config())
    _zet(hass, 1, 3.35, 3.34, 34.0, 48)
    _zet(hass, 2, 3.35, 3.34, 27.0, 48)
    _zet(hass, 3, 3.35, 3.34, 26.0, 48)

    coordinator._update_battery_module_health(DAY0)

    punten = coordinator.get_diagnostic_summary()["aandachtspunten"]
    # v1.15.8: de duiding ("inwendige weerstand" of "plaatsing") vraagt
    # om vermogens per module, en die zet deze opstelling niet. Het
    # temperatuurverschil zelf blijft wel gemeld - dat is de kern van
    # deze test.
    assert any("celtemperatuur" in p for p in punten)


def test_large_soc_spread_becomes_an_attention_point(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _zet(hass, 1, 3.35, 3.34, 27.0, 60)
    _zet(hass, 2, 3.35, 3.34, 27.0, 48)
    _zet(hass, 3, 3.35, 3.34, 27.0, 47)

    coordinator._update_battery_module_health(DAY0)

    punten = coordinator.get_diagnostic_summary()["aandachtspunten"]
    assert any("komt niet meer mee" in p for p in punten)


# --- dagafronding en drift -----------------------------------------


def _dag_vullen(coordinator, hass, dag, temp1):
    """Draait een dag vol metingen met module 1 op een gegeven
    temperatuur, en rondt die dag af."""
    for _ in range(BATTERY_MODULE_MIN_SAMPLES_PER_DAY):
        _zet(hass, 1, 3.35, 3.34, temp1, 48)
        _zet(hass, 2, 3.35, 3.34, 27.0, 48)
        _zet(hass, 3, 3.35, 3.34, 27.0, 48)
        coordinator._update_battery_module_health(dag)


def test_day_rollover_stores_a_median(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _dag_vullen(coordinator, hass, DAY0, temp1=27.0)
    # Volgende dag: de vorige wordt afgerond.
    _dag_vullen(coordinator, hass, DAY0 + timedelta(days=1), temp1=27.0)

    staat = coordinator.battery_module_health["1"]
    assert len(staat["geschiedenis"]["temperatuur_afwijking_c"]) == 1


def test_a_day_with_too_few_samples_is_discarded(make_coordinator, hass):
    """Een herstart vlak voor middernacht mag geen dagwaarde op basis
    van twee metingen in de leergeschiedenis zetten."""
    coordinator = make_coordinator(_config())
    for _ in range(3):
        _gezonde_situatie(hass)
        coordinator._update_battery_module_health(DAY0)
    _gezonde_situatie(hass)
    coordinator._update_battery_module_health(DAY0 + timedelta(days=1))

    staat = coordinator.battery_module_health["1"]
    assert staat["geschiedenis"] == {}


def test_sustained_drift_is_detected(make_coordinator, hass):
    """Module 1 loopt langzaam warmer dan de andere twee - precies het
    signaal dat maanden eerder komt dan merkbaar capaciteitsverlies."""
    coordinator = make_coordinator(_config())

    dag = DAY0
    # Eerst een lange, rustige referentieperiode.
    for _ in range(CUSUM_MIN_HISTORY_FOR_REFERENCE + 5):
        _dag_vullen(coordinator, hass, dag, temp1=27.0)
        dag += timedelta(days=1)
    # Dan structureel warmer.
    for _ in range(10):
        _dag_vullen(coordinator, hass, dag, temp1=33.0)
        dag += timedelta(days=1)

    cusum = coordinator.battery_module_health["1"]["cusum"]
    assert cusum["temperatuur_afwijking_c"]["drift"] is True
    assert cusum["temperatuur_afwijking_c"]["accumulator"] > (
        BATTERY_MODULE_CUSUM_THRESHOLD_C
    )


def test_stable_modules_never_drift(make_coordinator, hass):
    coordinator = make_coordinator(_config())

    dag = DAY0
    for _ in range(CUSUM_MIN_HISTORY_FOR_REFERENCE + 15):
        _dag_vullen(coordinator, hass, dag, temp1=27.0)
        dag += timedelta(days=1)

    cusum = coordinator.battery_module_health["1"]["cusum"]
    assert cusum.get("temperatuur_afwijking_c", {}).get("drift") is not True


def test_drift_becomes_an_attention_point(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    coordinator.battery_module_health["2"] = {
        "dag_metingen": {},
        "geschiedenis": {},
        "cusum": {"temperatuur_afwijking_c": {"drift": True}},
        "soc_buckets": {},
        "waarschuwingen": [],
    }
    _gezonde_situatie(hass)
    coordinator._update_battery_module_health(DAY0)

    punten = coordinator.get_diagnostic_summary()["aandachtspunten"]
    assert any("loopt aanhoudend uit de pas" in p for p in punten)


def test_drift_resets_after_a_sustained_return_to_normal(make_coordinator, hass):
    """Zelfde zelfherstel als bij de NILM-detectie: een afgelopen
    probleem mag niet maandenlang blijven hangen."""
    coordinator = make_coordinator(_config())

    dag = DAY0
    for _ in range(CUSUM_MIN_HISTORY_FOR_REFERENCE + 5):
        _dag_vullen(coordinator, hass, dag, temp1=27.0)
        dag += timedelta(days=1)
    for _ in range(10):
        _dag_vullen(coordinator, hass, dag, temp1=33.0)
        dag += timedelta(days=1)
    assert coordinator.battery_module_health["1"]["cusum"][
        "temperatuur_afwijking_c"
    ]["drift"] is True

    for _ in range(10):
        _dag_vullen(coordinator, hass, dag, temp1=26.0)
        dag += timedelta(days=1)

    assert coordinator.battery_module_health["1"]["cusum"][
        "temperatuur_afwijking_c"
    ]["drift"] is False


def test_absolute_delta_is_bucketed_by_soc(make_coordinator, hass):
    """De absolute celdelta wordt per SoC-bucket bewaard, want bij LFP
    hoort die aan de uiteinden hoger te liggen."""
    coordinator = make_coordinator(_config())
    _zet(hass, 1, 3.35, 3.34, 27.0, 45)
    _zet(hass, 2, 3.35, 3.34, 27.0, 45)
    _zet(hass, 3, 3.35, 3.34, 27.0, 45)
    coordinator._update_battery_module_health(DAY0)

    _zet(hass, 1, 3.50, 3.46, 27.0, 95)
    _zet(hass, 2, 3.50, 3.46, 27.0, 95)
    _zet(hass, 3, 3.50, 3.46, 27.0, 95)
    coordinator._update_battery_module_health(DAY0)

    buckets = coordinator.battery_module_health["1"]["soc_buckets"]
    assert "40" in buckets
    assert "90" in buckets
    assert buckets["90"][0] > buckets["40"][0]


# --- sensorweergave -------------------------------------------------


def test_sensor_counts_modules_needing_attention(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        BatteryModuleHealthSensor,
    )

    coordinator = make_coordinator(_config())
    _zet(hass, 1, 3.50, 3.30, 27.0, 48)  # delta 0,20 V
    _zet(hass, 2, 3.35, 3.34, 27.0, 48)
    _zet(hass, 3, 3.35, 3.34, 27.0, 48)
    coordinator._update_battery_module_health(DAY0)

    sensor = BatteryModuleHealthSensor(coordinator, "entry1")

    assert sensor.native_value == 1
    assert sensor.extra_state_attributes["aantal_modules"] == 3


def test_sensor_reports_zero_when_all_is_well(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        BatteryModuleHealthSensor,
    )

    coordinator = make_coordinator(_config())
    _gezonde_situatie(hass)
    coordinator._update_battery_module_health(DAY0)

    assert BatteryModuleHealthSensor(coordinator, "entry1").native_value == 0


def test_attention_threshold_matches_the_constant(make_coordinator, hass):
    """Net onder de drempel geen melding, net erboven wel."""
    coordinator = make_coordinator(_config())

    _zet(hass, 1, 3.34 + BATTERY_MODULE_CELL_DELTA_ATTENTION_V - 0.001, 3.34, 27.0, 48)
    _zet(hass, 2, 3.35, 3.34, 27.0, 48)
    _zet(hass, 3, 3.35, 3.34, 27.0, 48)
    coordinator._update_battery_module_health(DAY0)
    assert coordinator.get_battery_module_table()[0]["waarschuwingen"] == []

    _zet(hass, 1, 3.34 + BATTERY_MODULE_CELL_DELTA_ATTENTION_V + 0.001, 3.34, 27.0, 48)
    coordinator._update_battery_module_health(DAY0)
    assert coordinator.get_battery_module_table()[0]["waarschuwingen"] != []


def test_dashboard_shows_the_battery_modules():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    titels = [v["title"] for v in data["views"]]

    # v1.12.2: samengevoegd tot het tabblad "Systeem", met een kop
    # "Accumodules" erboven.
    plat = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    assert "Accu" in titels
    assert "title: Accumodules" in plat


def test_every_tab_shows_its_name_not_just_an_icon():
    """Gevraagd: "Zou je bij de tabbladen ook de namen willen laten zien
    zodat het helder blijft en niet alleen icoontjes zichtbaar zijn?"

    Home Assistant toont uitsluitend het icoon zodra een view er een
    heeft - de titel verdwijnt dan volledig. Geen enkele view mag er dus
    nog een hebben.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )

    for view in data["views"]:
        assert view.get("title"), f"view zonder titel: {view.get('path')}"
        assert "icon" not in view, (
            f"view '{view['title']}' heeft een icoon - dan verbergt Home "
            "Assistant de naam in de tabbalk"
        )


# --- v1.64.0: het celverschil hangt van de accustand af --------------


def _staat(vak="90", reeks=None):
    return {
        "soc_buckets": {vak: reeks if reeks is not None else [0.02] * 30},
        "waarschuwingen": [],
    }


def test_a_full_battery_no_longer_cries_wolf(make_coordinator, hass):
    """Gemeld: "Accumodule 1: celspanningsverschil 0.190 V - hoger dan
    gebruikelijk. Dit lijkt een standaard iets te zijn, gebeurt altijd
    nabij laden rond 100% SOC."

    LFP heeft een vlakke curve in het midden en steile uiteinden. Dezelfde
    module staat in het vak van 70% op 0,00 tot 0,03 V.
    """
    c = make_coordinator({})
    staat = _staat(vak="90", reeks=[0.17, 0.18, 0.19, 0.185] * 8)

    melding = c._beoordeel_celspreiding(staat, 0.190, soc=99.0)

    assert melding is None


def test_the_flat_middle_still_uses_the_absolute_limits(
    make_coordinator, hass
):
    """In het vlakke midden zegt een hoge delta wél iets - daar is de
    curve immers vlak."""
    c = make_coordinator({})

    melding = c._beoordeel_celspreiding(_staat(vak="50"), 0.12, soc=50.0)

    assert melding is not None
    assert "hoger dan gebruikelijk" in melding


def test_an_outlier_at_a_full_battery_is_still_reported(
    make_coordinator, hass
):
    """De melding hoort niet te verdwijnen, alleen eerlijker te worden:
    boven wat voor DEZE module bij DEZE stand gebruikelijk is, telt het
    alsnog."""
    c = make_coordinator({})
    staat = _staat(vak="90", reeks=[0.05] * 30)

    melding = c._beoordeel_celspreiding(staat, 0.190, soc=98.0)

    assert melding is not None
    assert "gebruikelijk is rond deze stand" in melding


def test_too_little_history_says_nothing(make_coordinator, hass):
    """Liever een gemiste melding dan een drempel op drie waarnemingen -
    anders leert het overzicht je hem te negeren."""
    c = make_coordinator({})
    staat = _staat(vak="90", reeks=[0.02, 0.03, 0.02])

    assert c._beoordeel_celspreiding(staat, 0.190, soc=98.0) is None


def test_a_nearly_empty_battery_is_treated_the_same(make_coordinator, hass):
    """De curve is aan béide uiteinden steil."""
    c = make_coordinator({})
    staat = _staat(vak="10", reeks=[0.15] * 30)

    assert c._beoordeel_celspreiding(staat, 0.18, soc=12.0) is None


def test_without_a_state_of_charge_it_falls_back(make_coordinator, hass):
    """Zonder stand valt er niets over het uiteinde te zeggen; dan de
    oude, veilige beoordeling."""
    c = make_coordinator({})

    melding = c._beoordeel_celspreiding(_staat(), 0.25, soc=None)

    assert melding is not None
    assert "fors uit balans" in melding
