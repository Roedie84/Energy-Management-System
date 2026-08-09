"""Dashboard verwijst alleen naar entiteiten die bestaan (v1.6.4).

Gerapporteerd: het Financieel-tabblad toonde "Geen
Zonneplan-kostensensoren gevonden", terwijl die sensoren er wél waren en
gewoon waarden gaven.

Oorzaak: het dashboard las
`sensor.woonkamer_energy_management_system_tegenfeitelijke_besparing`,
maar die sensor heet "Besparing t.o.v. zonder accu-sturing" en heeft dus
een heel andere entity_id. `state_attr` op een niet-bestaande entiteit
geeft None, en het sjabloon toonde daarop de "niet gevonden"-tekst - een
melding over Zonneplan, terwijl het probleem bij de eigen entiteitnaam
lag.

Dat is het vervelendste soort fout: het dashboard wijst de verkeerde
kant op.
"""
import re
import unicodedata
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent
VOORVOEGSEL = "sensor.woonkamer_energy_management_system_"


def _slug(naam: str) -> str:
    tekst = unicodedata.normalize("NFKD", naam).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", tekst.lower()).strip("_")


def _sensornamen() -> set[str]:
    """Alle `_attr_name`-waarden uit sensor.py, geslugificeerd zoals Home
    Assistant dat doet bij het aanmaken van een entity_id."""
    bron = (PAKKET / "sensor.py").read_text()
    namen = re.findall(r'_attr_name\s*=\s*"([^"]+)"', bron)
    return {_slug(naam) for naam in namen}


def test_every_referenced_sensor_name_exists():
    """De borging waar het om gaat.

    Elke `sensor.woonkamer_energy_management_system_X` in het dashboard
    moet corresponderen met een sensor die zo heet. Anders geeft
    `state_attr` stilzwijgend None en toont het sjabloon zijn
    terugvaltekst - die dan iets heel anders beweert dan er aan de hand
    is.
    """
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()
    verwezen = set(re.findall(rf"{re.escape(VOORVOEGSEL)}([a-z0-9_]+)", yaml_tekst))
    bekend = _sensornamen()

    # Home Assistant kent de entity_id toe bij de EERSTE aanmaak en laat
    # die daarna ongemoeid, ook als de weergavenaam verandert. Deze twee
    # zijn dus correct voor bestaande installaties, ook al slugificeert
    # de huidige naam anders:
    #   - "Advies-gereedheid (10 modules)" heette ooit "(8 modules)"
    #   - "Piekvermogen (netimport)" heette ooit alleen "Piekvermogen"
    # Bewust een expliciete lijst met reden: wie hier iets aan toevoegt
    # moet kunnen aantonen dat het om zo'n historische naam gaat en niet
    # om een typefout.
    HISTORISCHE_ENTITY_IDS = {
        "advies_gereedheid_8_modules",
        "piekvermogen",
    }

    # Sensoren met een dynamische naam (per apparaat, per module) staan
    # niet als letterlijke `_attr_name` in de bron; die worden hier
    # overgeslagen omdat ze niet statisch te controleren zijn.
    dynamisch = {
        naam
        for naam in verwezen
        if any(
            deel in naam
            for deel in ("vaatwasser", "wasmachine", "dishwasher", "washing")
        )
    }

    ontbreekt = sorted(verwezen - bekend - dynamisch - HISTORISCHE_ENTITY_IDS)

    assert not ontbreekt, (
        "dashboard verwijst naar sensoren die niet bestaan - `state_attr` "
        f"geeft daar None en het sjabloon toont zijn terugvaltekst: {ontbreekt}"
    )


def test_the_counterfactual_sensor_is_referenced_correctly():
    """Het concrete geval: de sensor heet "Besparing t.o.v. zonder
    accu-sturing", niet "Tegenfeitelijke besparing"."""
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    assert "besparing_t_o_v_zonder_accu_sturing" in yaml_tekst
    assert "tegenfeitelijke_besparing" not in yaml_tekst


def test_the_zonneplan_block_reads_the_right_sensor():
    """De Zonneplan-vergelijking hangt aan de besparingssensor; leest het
    blok een andere entiteit, dan meldt het ten onrechte dat er geen
    Zonneplan-sensoren zijn."""
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()
    # v1.12.4: de tabel is een tegel geworden; het attribuut
    # `zonneplan_vergelijking` hangt nog steeds aan dezelfde sensor.
    start = yaml_tekst.index("zonneplan_vergelijking")
    blok = yaml_tekst[max(0, start - 400) : start + 200]

    assert "besparing_t_o_v_zonder_accu_sturing" in blok


# --- v1.15.3: kaarten die netjes falen ------------------------------


def test_no_entity_card_uses_a_renamed_sensor():
    """Gemeld met screenshot: twee kaarten toonden "Entiteit niet
    gevonden".

    Ik had de entity_id's afgeleid uit de huidige weergavenaam, terwijl
    Home Assistant die vastlegt bij de EERSTE aanmaak. `Piekvermogen
    (netimport)` heet nog steeds `..._piekvermogen` - dat stond sinds
    v1.6.4 al als historische naam in dit bestand, maar bij het
    terugzetten van de 24 sensoren heb ik die lijst niet geraadpleegd.
    """
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    for fout in ("piekvermogen_netimport", "advies_gereedheid_10_modules"):
        assert fout not in yaml_tekst, (
            f"{fout} volgt de weergavenaam in plaats van de entity_id"
        )


def test_the_historical_ids_are_used_instead():
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    assert "_piekvermogen\n" in yaml_tekst or "_piekvermogen'" in yaml_tekst
    assert "advies_gereedheid_8_modules" in yaml_tekst


# --- v1.15.5: eenheden en onbekende waarden -------------------------


def test_learned_values_explain_an_empty_state():
    """Gemeld: "unknown kW" op de nachtverbruik-kaart.

    Bij een GELEERDE waarde betekent een lege toestand meestal "nog niet
    genoeg verzameld", niet "kapot". Die twee zien er identiek uit als je
    de kale toestand toont, en dan ga je zoeken naar een storing die er
    niet is.

    Bij LIVE meetwaarden (accustand, netstroom) is een lege toestand wél
    een signaal - die houden hun kale weergave, want daar wil je juist
    zien dat er iets mis is.
    """
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    # v1.17.1: het dashboard is herschreven via `yaml.dump`, waardoor
    # aanhalingstekens in Jinja verdubbeld op schijf staan ('' in plaats
    # van '). Na parsing is de Jinja identiek - Home Assistant leest het
    # correct - maar op de RUWE tekst zoeken werkt niet meer. Daarom via
    # de geparste kaarten.
    import yaml as _yaml

    data = _yaml.safe_load(yaml_tekst)
    kaarten = []
    for view in data["views"]:
        kaarten += list(view.get("cards") or [])
        for sectie in view.get("sections") or []:
            kaarten += sectie.get("cards") or []
        for kaart in list(kaarten):
            kaarten += kaart.get("cards") or []

    for eid, terugval in (
        ("learned_night_consumption", "nog niet geleerd"),
        ("piekvermogen", "nog niet gemeten"),
    ):
        passend = [k for k in kaarten if eid in str(k.get("entity", ""))]
        assert passend, eid
        assert any(terugval in str(k) for k in passend), eid



def test_the_night_consumption_uses_watt():
    """De sensor rekent kW al om naar W; nog een keer omrekenen of een
    verkeerde eenheid tonen maakt het getal onbruikbaar."""
    bron = (PAKKET / "sensor.py").read_text()
    start = bron.index("class LearnedNightConsumptionSensor")
    blok = bron[start : start + 600]

    assert '_attr_native_unit_of_measurement = "W"' in blok

    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()
    kaart_start = yaml_tekst.index("secondary: Nachtverbruik")
    kaart = yaml_tekst[max(0, kaart_start - 400) : kaart_start]

    assert "' W'" in kaart
    assert "kW" not in kaart


# --- v1.15.6: sensoren van vóór de apparaatnaam ---------------------

# Deze entiteiten zijn aangemaakt voordat het apparaat "Woonkamer" heette.
# Home Assistant legt de entity_id vast bij de EERSTE aanmaak, dus ze
# missen dat voorvoegsel - te zien in een dashboard van v0.63.114.
#
# Bewust een expliciete lijst: wie hier iets aan toevoegt moet kunnen
# aantonen dat de entiteit echt zonder voorvoegsel bestaat, in plaats van
# dat het een typefout verbergt.
ZONDER_VOORVOEGSEL = {
    "battery_protection",
    "cheapest_block_start",
    "discharge_window_start",
    "effective_expensive_quarters",
    "energy_bridge_check",
    "expected_operation_mode",
    "last_decision_reason",
    "learned_night_consumption",
    "pv_forecast_accuracy",
    "simulated_action",
    "upcoming_schedule",
}


def test_the_old_sensors_have_no_device_prefix():
    """Gemeld met screenshot: zeven kaarten onder "Beslissing en
    planning" toonden "Entiteit niet gevonden".

    Ik had de entity_id's afgeleid uit de weergavenaam met het
    `woonkamer_`-voorvoegsel ervoor. Maar deze sensoren bestaan al langer
    dan die apparaatnaam, en hun entity_id is bij de eerste aanmaak
    vastgelegd zonder dat voorvoegsel.
    """
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    fout = sorted(
        eid
        for eid in ZONDER_VOORVOEGSEL
        if f"sensor.woonkamer_energy_management_system_{eid}" in yaml_tekst
    )

    assert not fout, (
        f"deze sensoren bestaan zonder `woonkamer_`-voorvoegsel: {fout}"
    )


def test_they_are_actually_referenced():
    """De correctie moet de kaarten ook echt bereiken; anders staan er
    straks geen fouten maar ook geen gegevens."""
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    for eid in ("last_decision_reason", "upcoming_schedule", "battery_protection"):
        assert f"sensor.energy_management_system_{eid}" in yaml_tekst, eid
