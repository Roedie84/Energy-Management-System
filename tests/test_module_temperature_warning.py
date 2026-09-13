"""Temperatuurverschil tussen accumodules duiden (v1.15.8).

Uit een export: "Accumodules verschillen 5.0 °C in celtemperatuur - bij
gelijke belasting wijst dat op een module met hogere inwendige
weerstand."

De melding trok één conclusie terwijl er twee even goede verklaringen
zijn. Een module die bovenaan de stapel of tegen een muur staat wordt óók
warmer - en dát kan de integratie niet zien.

Het VERMOGEN erbij zetten maakt het onderscheid wél mogelijk: levert de
warmste module ook minder, dan wijst het op de accu; levert hij evenveel,
dan eerder op de plaatsing.
"""
from custom_components.energy_management_system.const import (
    BATTERY_MODULE_TEMPERATURE_SPREAD_ATTENTION_C,
)


def _met_modules(make_coordinator, modules, spreiding):
    c = make_coordinator({})
    c.battery_module_live = modules
    c.battery_module_spread = {"temperatuur_c": spreiding}
    return c


def _melding(c):
    return next(
        p
        for p in c.get_diagnostic_summary()["aandachtspunten"]
        if "celtemperatuur" in p
    )


# --- het gerapporteerde geval ----------------------------------------


def test_warmest_and_weakest_points_at_the_module(make_coordinator, hass):
    """De werkelijke cijfers: 32 °C bij 542 W tegen 27 °C bij 602 W."""
    c = _met_modules(
        make_coordinator,
        [
            {"module": 1, "temperatuur_c": 32.0, "vermogen_w": 542.0},
            {"module": 2, "temperatuur_c": 29.0, "vermogen_w": 562.0},
            {"module": 3, "temperatuur_c": 27.0, "vermogen_w": 602.0},
        ],
        5.0,
    )

    melding = _melding(c)

    assert "Module 1 is de warmste én levert het minste" in melding
    assert "inwendige weerstand" in melding


def test_warmest_but_not_weakest_points_at_placement(make_coordinator, hass):
    """Levert de warmste module gewoon mee, dan is de accu niet de
    verdachte - en dat mag de melding niet suggereren."""
    c = _met_modules(
        make_coordinator,
        [
            {"module": 1, "temperatuur_c": 32.0, "vermogen_w": 620.0},
            {"module": 2, "temperatuur_c": 29.0, "vermogen_w": 562.0},
            {"module": 3, "temperatuur_c": 27.0, "vermogen_w": 542.0},
        ],
        5.0,
    )

    melding = _melding(c)

    assert "plaatsing" in melding
    assert "inwendige weerstand" not in melding


# --- grenzen ---------------------------------------------------------


def test_a_small_spread_gives_no_warning(make_coordinator, hass):
    c = _met_modules(
        make_coordinator,
        [
            {"module": 1, "temperatuur_c": 27.0, "vermogen_w": 560.0},
            {"module": 2, "temperatuur_c": 28.0, "vermogen_w": 560.0},
        ],
        BATTERY_MODULE_TEMPERATURE_SPREAD_ATTENTION_C - 1,
    )

    assert not any(
        "celtemperatuur" in p
        for p in c.get_diagnostic_summary()["aandachtspunten"]
    )


def test_missing_power_still_reports_the_spread(make_coordinator, hass):
    """Zonder vermogenssensoren valt de duiding weg, maar het
    temperatuurverschil blijft het melden waard."""
    c = _met_modules(
        make_coordinator,
        [
            {"module": 1, "temperatuur_c": 32.0},
            {"module": 2, "temperatuur_c": 27.0},
        ],
        5.0,
    )

    melding = _melding(c)

    assert "5.0 °C" in melding
    assert "inwendige weerstand" not in melding


# --- v1.16.4: externe warmte of eigen verlies -----------------------


def _met_rust(c, temperaturen):
    c.battery_module_health = {
        str(m): {"geschiedenis": {"temperatuur_c": [t]}}
        for m, t in temperaturen.items()
    }
    return c


def test_a_large_rest_spread_points_outward(make_coordinator, hass):
    """Gemeld: "Ik vermoed dat de accu 1 direct onder de omvormer zit."

    Dat is een derde verklaring die v1.15.8 niet meenam, en ze keert het
    beeld om: een warmere cel heeft juist LAGERE inwendige weerstand, dus
    minder vermogen bij hogere temperatuur past eerder bij een BMS dat
    terugregelt om de cel te beschermen. Dan is de warmte de OORZAAK van
    het lagere vermogen, niet het gevolg van een zwakke module.
    """
    c = _met_modules(
        make_coordinator,
        [
            {"module": 1, "temperatuur_c": 32.0, "vermogen_w": 442.0},
            {"module": 2, "temperatuur_c": 29.0, "vermogen_w": 562.0},
            {"module": 3, "temperatuur_c": 27.0, "vermogen_w": 602.0},
        ],
        5.0,
    )
    _met_rust(c, {1: 30.0, 2: 26.0, 3: 25.0})

    melding = _melding(c)

    assert "In rust verschillen ze al" in melding
    assert "omvormer" in melding
    assert "inwendige weerstand" not in melding


def test_a_small_rest_spread_points_at_the_module(make_coordinator, hass):
    """Externe warmte werkt dag en nacht; eigen verlies alleen onder
    belasting. Groeit het verschil met de belasting, dan ligt het aan de
    module."""
    c = _met_modules(
        make_coordinator,
        [
            {"module": 1, "temperatuur_c": 32.0, "vermogen_w": 442.0},
            {"module": 2, "temperatuur_c": 29.0, "vermogen_w": 562.0},
            {"module": 3, "temperatuur_c": 27.0, "vermogen_w": 602.0},
        ],
        5.0,
    )
    _met_rust(c, {1: 26.0, 2: 25.0, 3: 24.0})

    melding = _melding(c)

    assert "in rust maar 2.0 °C" in melding
    assert "inwendige weerstand" in melding


def test_without_rest_data_the_wording_stays_careful(make_coordinator, hass):
    """Zonder rustmeting valt het onderscheid niet te maken; dan mag de
    melding er ook geen uitspraak over doen."""
    c = _met_modules(
        make_coordinator,
        [
            {"module": 1, "temperatuur_c": 32.0, "vermogen_w": 442.0},
            {"module": 2, "temperatuur_c": 27.0, "vermogen_w": 602.0},
        ],
        5.0,
    )
    c.battery_module_health = {}

    melding = _melding(c)

    assert "In rust" not in melding
    assert "inwendige weerstand" in melding
