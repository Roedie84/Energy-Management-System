"""Bevindingen uit de integratie-brede review (v1.1.5).

Gevraagd: "Kun je nu eens de hele integratie nakijken of je nog zaken
ziet welke bij nader inzien niet goed/anders/beter kunnen?"

Twee echte vondsten, allebei stille problemen: ze veroorzaken geen fout
en geen melding, maar doen wel iets anders dan bedoeld.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_BATTERY_COOLING_FAN_SWITCH,
    CONF_BATTERY_COOLING_OUTDOOR_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_TEMPERATURE_SENSOR,
    CONF_FEEDIN_COST_EUR_PER_KWH,
    CONF_SALDEREN_END_DATE,
)

FAN = "switch.ventilatoren"


# --- 1. wedloop op de koelventilator --------------------------------


def _cooling_coordinator(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_BATTERY_TEMPERATURE_SENSOR: "sensor.accu_temp",
            CONF_BATTERY_COOLING_OUTDOOR_SENSOR: "sensor.buiten",
            CONF_BATTERY_COOLING_FAN_SWITCH: FAN,
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
        }
    )
    hass.states.set("sensor.accu_temp", "36.0")
    hass.states.set("sensor.buiten", "22.0")
    hass.states.set("sensor.accu_w", "0")
    hass.states.set(FAN, "off")
    return c


def test_cooling_does_not_switch_twice_when_called_concurrently(
    make_coordinator, hass
):
    """De koeling draait op TWEE plekken: binnen de gewone tick (dus
    binnen het bestaande slot) en vanuit een eigen live listener
    daarbuiten. Zonder eigen slot kunnen die elkaar overlappen op de
    `await` van de service-aanroep: beide lezen "ventilator staat uit",
    beide schakelen hem aan. Dat levert een dubbele melding en een
    dubbele regel in de schakelgeschiedenis op - precies wat de
    "niet opnieuw schakelen als hij al goed staat"-controle moest
    voorkomen.
    """
    c = _cooling_coordinator(make_coordinator, hass)

    # De nep-service moet zich als de echte gedragen: de schakelaar
    # daadwerkelijk omzetten, en onderweg de gebeurtenislus vrijgeven.
    # Dat `await` is precies het punt waarop de twee aanroepen elkaar
    # zonder slot zouden kruisen - zonder die twee dingen toetst deze
    # test de nepversie in plaats van de code.
    async def fake_call(domein, dienst, data, blocking=False):
        await asyncio.sleep(0)
        hass.states.set(FAN, "on" if dienst == "turn_on" else "off")

    c.hass.services.async_call = fake_call

    async def run():
        await asyncio.gather(
            c._async_apply_battery_cooling(),
            c._async_apply_battery_cooling(),
        )

    asyncio.run(run())

    assert len(c.battery_cooling_history) == 1


def test_cooling_still_works_when_called_once(make_coordinator, hass):
    """Het slot mag de normale werking niet in de weg zitten."""
    c = _cooling_coordinator(make_coordinator, hass)

    async def fake_call(domein, dienst, data, blocking=False):
        await asyncio.sleep(0)
        hass.states.set(FAN, "on" if dienst == "turn_on" else "off")

    c.hass.services.async_call = fake_call
    asyncio.run(c._async_apply_battery_cooling())

    assert len(c.battery_cooling_history) == 1
    assert c.battery_cooling_history[0]["actie"] == "aan"


# --- 2. configuratie zonder validatie -------------------------------


def test_a_malformed_date_is_rejected():
    """De salderingsdatum is vrije tekst en stuurt sinds v1.1.0 óók de
    beslislogica. Een typefout viel stilzwijgend terug op "salderen
    actief" - verdedigbaar als noodgreep, maar de gebruiker kreeg geen
    enkel signaal dat zijn invoer niet was aangekomen, en het gedrag na
    saldering zou dan gewoon nooit aangaan.
    """
    from custom_components.energy_management_system.config_flow import (
        _validate_input,
    )

    for verkeerd in ("31-12-2026", "2026-13-01", "morgen", "2026/12/31"):
        assert CONF_SALDEREN_END_DATE in _validate_input(
            {CONF_SALDEREN_END_DATE: verkeerd}
        ), verkeerd


def test_a_valid_date_passes():
    from custom_components.energy_management_system.config_flow import (
        _validate_input,
    )

    assert _validate_input({CONF_SALDEREN_END_DATE: "2026-12-31"}) == {}


def test_an_empty_date_is_allowed():
    """Leeg laten mag - dan geldt de standaardwaarde."""
    from custom_components.energy_management_system.config_flow import (
        _validate_input,
    )

    assert _validate_input({}) == {}
    assert _validate_input({CONF_SALDEREN_END_DATE: ""}) == {}


def test_feedin_cost_must_be_a_number(make_coordinator, hass):
    from custom_components.energy_management_system.config_flow import (
        _validate_input,
    )

    assert CONF_FEEDIN_COST_EUR_PER_KWH in _validate_input(
        {CONF_FEEDIN_COST_EUR_PER_KWH: "twee cent"}
    )


def test_feedin_cost_cannot_be_negative():
    """Negatieve terugleverkosten zouden de besparing kunstmatig
    verhogen."""
    from custom_components.energy_management_system.config_flow import (
        _validate_input,
    )

    assert CONF_FEEDIN_COST_EUR_PER_KWH in _validate_input(
        {CONF_FEEDIN_COST_EUR_PER_KWH: -0.05}
    )
    assert _validate_input({CONF_FEEDIN_COST_EUR_PER_KWH: 0.02}) == {}


def test_every_error_key_has_a_translation():
    """Een foutcode zonder vertaling toont in Home Assistant een kale
    sleutel als 'invalid_date' - onbruikbaar voor wie het formulier
    invult."""
    import json
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    map_ = Path(pkg.__file__).parent
    codes = {"invalid_date", "invalid_number", "negative_cost"}
    for bestand in ("translations/nl.json", "translations/en.json", "strings.json"):
        data = json.loads((map_ / bestand).read_text())
        for blok in ("config", "options"):
            if blok in data:
                aanwezig = set(data[blok].get("error", {}))
                assert codes <= aanwezig, f"{bestand}/{blok}: {codes - aanwezig}"


def test_the_form_is_redisplayed_with_the_entered_values():
    """Bij een fout moet alleen het foute veld hoeven te worden
    aangepast, niet het hele formulier opnieuw."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "config_flow.py").read_text()

    assert bron.count("data_schema=_schema(user_input)") == 2


# --- v1.4.2: optionele getalvelden blokkeerden het formulier ---------


def test_empty_optional_number_fields_are_accepted():
    """Gerapporteerd met screenshot: twee velden toonden "expected
    float" en het formulier was niet meer te verzenden.

    Een `NumberSelector` met `default=None` - wat een optioneel veld
    oplevert zodra het leeg blijft - wijst die None af. Alle bestaande
    getalvelden in deze flow hebben een concrete standaard en liepen daar
    dus niet tegenaan; deze twee mogen juist leeg blijven.
    """
    from custom_components.energy_management_system.config_flow import (
        _validate_input,
    )
    from custom_components.energy_management_system.const import (
        CONF_PV_ACTUAL_AZIMUTH_DEGREES,
        CONF_PV_ACTUAL_TILT_DEGREES,
    )

    invoer = {
        CONF_PV_ACTUAL_AZIMUTH_DEGREES: "",
        CONF_PV_ACTUAL_TILT_DEGREES: "",
    }

    assert _validate_input(invoer) == {}
    # Leeg betekent "geen ijkpunt" - het veld hoort dan niet als lege
    # tekst in de configuratie te blijven staan.
    assert CONF_PV_ACTUAL_AZIMUTH_DEGREES not in invoer


def test_a_valid_orientation_becomes_a_number():
    """Anders krijgt de coordinator later alsnog een tekst binnen."""
    from custom_components.energy_management_system.config_flow import (
        _validate_input,
    )
    from custom_components.energy_management_system.const import (
        CONF_PV_ACTUAL_AZIMUTH_DEGREES,
    )

    invoer = {CONF_PV_ACTUAL_AZIMUTH_DEGREES: "200"}

    assert _validate_input(invoer) == {}
    assert invoer[CONF_PV_ACTUAL_AZIMUTH_DEGREES] == 200.0


def test_a_comma_decimal_is_accepted():
    """Op een Nederlands toetsenbord ligt een komma meer voor de hand."""
    from custom_components.energy_management_system.config_flow import (
        _validate_input,
    )
    from custom_components.energy_management_system.const import (
        CONF_PV_ACTUAL_TILT_DEGREES,
    )

    invoer = {CONF_PV_ACTUAL_TILT_DEGREES: "12,5"}

    assert _validate_input(invoer) == {}
    assert invoer[CONF_PV_ACTUAL_TILT_DEGREES] == 12.5


def test_nonsense_and_out_of_range_are_rejected():
    from custom_components.energy_management_system.config_flow import (
        _validate_input,
    )
    from custom_components.energy_management_system.const import (
        CONF_PV_ACTUAL_AZIMUTH_DEGREES,
        CONF_PV_ACTUAL_TILT_DEGREES,
    )

    assert CONF_PV_ACTUAL_AZIMUTH_DEGREES in _validate_input(
        {CONF_PV_ACTUAL_AZIMUTH_DEGREES: "zuidwest"}
    )
    assert CONF_PV_ACTUAL_AZIMUTH_DEGREES in _validate_input(
        {CONF_PV_ACTUAL_AZIMUTH_DEGREES: "400"}
    )
    assert CONF_PV_ACTUAL_TILT_DEGREES in _validate_input(
        {CONF_PV_ACTUAL_TILT_DEGREES: "120"}
    )


def test_no_optional_number_selector_without_a_default():
    """Borging tegen herhaling: een NumberSelector op een veld dat leeg
    mag blijven, blokkeert het hele formulier."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "config_flow.py").read_text()
    for blok in re.finditer(
        r"vol\.Optional\(\s*(\w+),\s*default=([^)]*?)\),\s*\):\s*selector\.NumberSelector",
        bron,
        re.S,
    ):
        veld, standaard = blok.group(1), blok.group(2)
        assert "," in standaard, (
            f"{veld}: optioneel NumberSelector zonder terugvalwaarde - "
            "levert 'expected float' zodra het veld leeg blijft"
        )


def test_no_optional_entity_selector_defaults_to_none():
    """Gemeld met een screenshot van het configuratiescherm:

        Entity None is neither a valid entity ID nor a valid UUID

    `vol.Optional(sleutel, default=None)` geeft de EntitySelector een
    lege waarde mee, en die weigert dat - het veld is dan niet in te
    vullen.

    Er stond al zo'n toets voor NumberSelector (v1.78.0); die dekte
    EntitySelector niet. Dit raakte 52 velden, waarvan er twee opvielen
    omdat ze nog nooit waren ingevuld.
    """
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "config_flow.py").read_text()

    fout = [
        m.group(1)
        for m in re.finditer(
            r"vol\.Optional\(\s*(CONF_\w+),\s*default=defaults\.get\(\1\),"
            r"\s*\):\s*selector\.EntitySelector",
            bron,
            re.S,
        )
    ]

    assert not fout, (
        "optioneel entiteitsveld met een lege standaard - gebruik "
        f"_optioneel(): {fout}"
    )


def test_the_helper_omits_the_default_when_empty():
    """De kern: zonder waarde hoort er geen `default` mee te gaan."""
    from custom_components.energy_management_system import config_flow

    leeg = config_flow._optioneel("iets", {})
    gevuld = config_flow._optioneel("iets", {"iets": "sensor.x"})

    assert leeg.default is not None  # voluptuous' UNDEFINED-markering
    assert gevuld.default() == "sensor.x"
