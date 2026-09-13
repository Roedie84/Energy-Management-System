"""Alles van vandaag is herleidbaar in de diagnostiek (v1.18.2).

Gevraagd: "Alles wat je gebouwd hebt vandaag moet in de diagnostiek
herleidbaar zijn zodat we na delen van de diagnostiek eventueel kunnen
corrigeren."

Zeven onderdelen stonden er nog niet in. Zonder die velden is een gemeld
probleem alleen op een screenshot te zien - en dat is precies wat er
vandaag telkens misging: tien van de veertien problemen zaten in een laag
die de export niet toonde.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent


def _export_bron() -> str:
    return (PAKKET / "diagnostics.py").read_text()


def test_everything_built_today_is_exported():
    """Eén lijst met alles van deze dag, zodat een gemist onderdeel
    meteen opvalt."""
    bron = _export_bron()

    for veld in (
        # v1.11-v1.12: meldingen en kwaliteit
        "sensor_health_breakdown",
        "stalled_series",
        "plausibility_warnings",
        # v1.14-v1.16: zelfevaluatie en dashboardcontrole
        "self_evaluation",
        "dashboard_health",
        "pv_production_source",
        # v1.17: PV-analyse
        "pv_forecast_quality",
        "pv_correction_status",
        # v1.17-v1.18: overzicht, water, klimaat, accu
        "topic_summaries",
        "water_source_profiles",
        "water_source_overview",
        "living_room_temp_bucket_direction",
        "battery_discharge_today_kwh",
        "battery_module_rest_spread_c",
        # v1.18.2: aanwezigheid
        "presence_overview",
        "presence_week_profile",
    ):
        assert veld in bron, veld


def test_every_exported_call_exists(make_coordinator, hass):
    """Een aanroep naar een verwijderde methode laat de hele export
    falen - precies wanneer je hem nodig hebt."""
    import inspect
    import json
    import re

    from custom_components.energy_management_system import diagnostics

    c = make_coordinator({})
    bron = inspect.getsource(diagnostics)

    for naam in sorted(set(re.findall(r"coordinator\.(get_\w+)\(\)", bron))):
        json.dumps(getattr(c, naam)(), default=str)


def test_every_exported_attribute_exists(make_coordinator, hass):
    import inspect
    import re

    from custom_components.energy_management_system import diagnostics

    c = make_coordinator({})
    bron = inspect.getsource(diagnostics)

    velden = sorted(set(re.findall(r"coordinator\.([a-z_]+)[,\s\)\]]", bron)))
    ontbreekt = [v for v in velden if not hasattr(c, v)]

    assert not ontbreekt, ontbreekt


def test_the_export_is_serialisable(make_coordinator, hass):
    """Een niet-serialiseerbaar veld laat de HELE bewaarslag mislukken,
    niet alleen dat veld - dezelfde les als bij de dagsleutel in
    v1.16.5."""
    import json

    c = make_coordinator({})

    for naam in (
        "get_topic_summaries",
        "get_presence_overview",
        "get_water_source_overview",
        "get_pv_forecast_quality",
        "get_pv_correction_status",
        "get_dashboard_health",
    ):
        json.dumps(getattr(c, naam)(), default=str)


# --- v1.19.3: één fout mag de export niet slopen --------------------


def test_every_call_is_shielded():
    """Gemeld: "De diagnostiek blijft nu een text file, wordt geen json,
    dit suggereert dat daar nu ook iets fout gaat?"

    Terechte conclusie. De export was één grote dict-expressie: gooit
    één aanroep een fout, dan mislukt het HELE bestand en krijg je een
    foutpagina in plaats van JSON.

    Dat is precies het verkeerde moment om te falen - de export is het
    gereedschap dat je nodig hebt WANNEER er iets stuk is. Dezelfde vorm
    als het attributenblok in v1.19.1, en dezelfde oplossing.
    """
    import re

    bron = _export_bron()

    # Geen kale aanroepen meer buiten de afscherming.
    kaal = re.findall(r"(?<!_veilig\(\")coordinator\.get_\w+\(\)", bron)

    assert not kaal, kaal
    assert "_veilig" in bron


def test_a_broken_part_does_not_break_the_rest(make_coordinator, hass):
    c = make_coordinator({})

    def stuk():
        raise KeyError("gesimuleerd")

    c.get_topic_summaries = stuk

    def veilig(functie):
        try:
            return functie()
        except Exception as fout:  # noqa: BLE001
            return {"fout": f"{type(fout).__name__}: {fout}"}

    assert veilig(c.get_topic_summaries) == {"fout": "KeyError: 'gesimuleerd'"}
    assert veilig(c.get_dashboard_health)["beschikbaar"] is True


def test_the_failure_is_recorded_not_swallowed():
    """Een stil weggevallen onderdeel is erger dan een zichtbare fout:
    dan denk je dat er niets te melden was."""
    bron = _export_bron()

    assert "_LOGGER.exception" in bron
    assert '"fout"' in bron


# --- v1.22.1: de losse kwartierprijzen --------------------------------


def test_the_quarter_prices_are_exported():
    """Gevraagd: "De nieuwe kwartierprijzen van Zonneplan zijn toch al
    bekend?"

    Ja - de integratie kent ze tot morgen middernacht. Maar de export
    toonde alleen `upcoming_transitions`: samengevoegde blokken per
    modus met alleen een min- en maxprijs. Voor een hele dag waren dat
    drie regels met "0,1267 - 0,3505".

    Daarmee valt niet na te gaan WANNEER de prijs hoog is, en dat is nu
    juist waar het uitstelplan uit v1.22.0 op stuurt.
    """
    bron = _export_bron()

    assert "price_forecast_quarters" in bron
    assert "_get_forecast_entries" in bron


def test_the_price_export_is_shielded():
    """Zonder prijssensor gooit `_get_forecast_entries` een KeyError -
    dat mag de hele export niet meeslepen."""
    bron = _export_bron()
    start = bron.index("price_forecast_quarters")
    blok = bron[start - 200 : start + 600]

    assert "_veilig(" in blok


def test_it_survives_without_a_price_sensor(make_coordinator, hass):
    c = make_coordinator({})

    def veilig(functie):
        try:
            return functie()
        except Exception as fout:  # noqa: BLE001
            return {"fout": f"{type(fout).__name__}: {fout}"}

    resultaat = veilig(c._get_forecast_entries)

    assert resultaat is not None
