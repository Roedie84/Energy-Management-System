"""Dashboardcontrole in de diagnostiek-export (v1.16.3).

Gevraagd: "Had je alles afgevangen met een betere diagnose file?"

Eerlijk antwoord was nee. Van de veertien problemen op één dag zaten er
tien in het DASHBOARD, en de export bevatte alleen sensorwaarden - niet
hoe die worden getoond. Elke fout zat in de laag ertussen, en die was
alleen op een screenshot te zien.

Deze controle sluit dat gat voor negen van die tien: bestaat elke
entiteit waar het dashboard naar verwijst, en staat ze niet leeg?
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent


# --- de controle zelf ------------------------------------------------


def test_it_checks_every_referenced_entity(make_coordinator, hass):
    c = make_coordinator({})

    rapport = c.get_dashboard_health()

    assert rapport["beschikbaar"] is True
    assert rapport["gecontroleerd"] > 50


def test_a_missing_entity_is_reported(make_coordinator, hass):
    """Het patroon van vandaag: een verkeerd afgeleide entity_id die
    "Entiteit niet gevonden" toont."""
    c = make_coordinator({})

    rapport = c.get_dashboard_health()

    # In de testomgeving bestaat vrijwel niets, dus de lijst hoort
    # gevuld te zijn - dat bewijst dat de controle werkt.
    assert rapport["niet_bestaande_entiteiten"]


def test_an_empty_entity_is_reported_separately(make_coordinator, hass):
    """"Onbekend" en "Entiteit niet gevonden" zien er op een screenshot
    hetzelfde uit, maar vragen om een ander onderzoek: de eerste kan
    normaal zijn, de tweede nooit."""
    c = make_coordinator({})
    hass.states.set(
        "sensor.energy_management_system_last_decision_reason", "unknown"
    )

    rapport = c.get_dashboard_health()

    assert (
        "sensor.energy_management_system_last_decision_reason"
        in rapport["lege_entiteiten"]
    )
    assert (
        "sensor.energy_management_system_last_decision_reason"
        not in rapport["niet_bestaande_entiteiten"]
    )


def test_a_working_entity_is_not_reported(make_coordinator, hass):
    c = make_coordinator({})
    hass.states.set(
        "sensor.energy_management_system_last_decision_reason",
        "expensive_quarter",
    )

    rapport = c.get_dashboard_health()

    for lijst in ("niet_bestaande_entiteiten", "lege_entiteiten"):
        assert (
            "sensor.energy_management_system_last_decision_reason"
            not in rapport[lijst]
        )


# --- inbedding -------------------------------------------------------


def test_it_is_in_the_export():
    bron = (PAKKET / "diagnostics.py").read_text()

    assert "dashboard_health" in bron


def test_it_explains_what_the_findings_mean(make_coordinator, hass):
    """Een lijst entity_id's zonder duiding laat je gissen wat je ermee
    moet - zeker omdat "Onbekend" vaak normaal is en "niet gevonden"
    nooit."""
    c = make_coordinator({})

    toelichting = c.get_dashboard_health()["toelichting"]

    assert "Entiteit niet gevonden" in toelichting
    assert "Onbekend" in toelichting


def test_a_missing_template_does_not_crash(make_coordinator, hass):
    """Zonder sjabloon hoort de export gewoon door te gaan; een
    diagnostiek die zelf faalt is waardeloos."""
    c = make_coordinator({})
    c._read_dashboard_template = lambda: ""

    assert c.get_dashboard_health() == {"beschikbaar": False}


# --- v1.19.2: ontbrekende ATTRIBUTEN -------------------------------


def _gacs(hass, attributen):
    hass.states.set(
        "sensor.woonkamer_energy_management_system_gacs_zelfbeoordeling",
        "0",
        attributen,
    )


def test_a_missing_attribute_is_reported(make_coordinator, hass):
    """Gemeld: kaarten die "Nog geen gegevens" tonen terwijl de entiteit
    gewoon bestaat.

    De controle keek alleen of de ENTITEIT er was, niet of het ATTRIBUUT
    dat de kaart opvraagt bestaat - en juist daar zat het probleem. Een
    sjabloon dat een ontbrekend attribuut opvraagt krijgt None en toont
    zijn vangnettekst; op het scherm is dat niet te onderscheiden van
    "nog niets geleerd".
    """
    c = make_coordinator({})
    _gacs(hass, {})

    ontbrekend = c.get_dashboard_health()["ontbrekende_attributen"]

    assert any("samenvattingen" in x for x in ontbrekend)
    assert any("pv_voorspelkwaliteit" in x for x in ontbrekend)


def test_present_attributes_are_not_reported(make_coordinator, hass):
    c = make_coordinator({})
    _gacs(
        hass,
        {
            "samenvattingen": {},
            "pv_voorspelkwaliteit": {},
            "pv_correctie": {},
            "aanwezigheid": {},
            "uitbreidingsadvies": {},
            "weerbronnen": {},
            # v3.94.0: de heldere-hemel-ijklijn op de weerpagina.
            "helderheid_ijking": {},
            # v3.95.2: de zin van de tegel "Haalt de accu het?".
            "haalt_de_accu_het": "",
            "statuskop": "",
            "zon_uitstelplan": {},
            "kwartierplanning": [],
            # v3.67.0: de proefplanning op de kwartierpagina.
            "smart_charging_proef": {},
            "verkooptoets": {},
            "reservemarge": {},
            "zelfconsumptie": {},
            "perioden": {},
            "geschiedenisbronnen": {},
            "kwartier_samenvatting": {},
            "plantoetsing": {},
            "rendement": {},
            "prijstoets": {},
            "terugvallen": [],
            "zonstand": {},
            "buitensensor": {},
            "zelfcontrole": {},
            "rondeduur": {},
            "capaciteit": {},
            "overzichtsplaat": "",
            "overzichtsecties": "",
            "overzichtstatus": "",
            "logboek": {},
            "gezondheid": {},
            "veroudering": {},
            "waarom_nu": {},
            "gepland_witgoed": {},
            "zon_vandaag": {},
            "zonspreiding": {},
            "zonband_ijking": {},
            "weerbron_vergelijking": {},
            "besparingscorrectie": {},
            "proefstand": {},
            "nog_niet_bepaald": {},
            "verbetermogelijkheden": [],
        },
    )

    ontbrekend = c.get_dashboard_health()["ontbrekende_attributen"]

    assert not [x for x in ontbrekend if "gacs" in x]


def test_a_missing_entity_is_not_double_reported(make_coordinator, hass):
    """Bestaat de entiteit niet, dan is dat de melding - niet twintig
    ontbrekende attributen erbovenop."""
    c = make_coordinator({})

    rapport = c.get_dashboard_health()

    for regel in rapport["ontbrekende_attributen"]:
        entity_id = regel.split(" ->")[0]
        assert entity_id not in rapport["niet_bestaande_entiteiten"]


def test_the_doubled_quotes_are_handled(make_coordinator, hass):
    """Het sjabloon is met `yaml.dump` weggeschreven (v1.17.1), waardoor
    aanhalingstekens op schijf verdubbeld staan. Zonder normaliseren
    vindt de zoekactie niets - precies waar deze controle bij de eerste
    poging op stukliep."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("def get_dashboard_health")
    # v3.2.0: tot de volgende definitie. Een vast aantal tekens breekt
    # zodra de functie groeit - de valkuil die al in de overdracht staat.
    blok = bron[start : bron.index("\n    def ", start + 10)]

    assert 'replace("\'\'", "\'")' in blok


def test_the_explanation_names_the_hardest_case(make_coordinator, hass):
    """Een ontbrekend attribuut is lastiger te herkennen dan een
    ontbrekende entiteit; dat hoort in de duiding te staan."""
    c = make_coordinator({})

    toelichting = c.get_dashboard_health()["toelichting"]

    assert "ATTRIBUUT" in toelichting
    assert "vangnettekst" in toelichting


def test_the_export_shows_what_the_check_needed():
    """v1.76.0: bij de volledige controle van 13 augustus bleken drie
    dingen niet na te kijken omdat ze niet in de export stonden -
    `notification_last_sent` was er niet, en de export-splitsing bestond
    nog niet.

    Een diagnostiek waarin een veld ontbreekt, ziet er hetzelfde uit als
    een veld dat op nul staat. Dat verschil kostte bij de azimut al een
    verkeerde conclusie.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    for veld in (
        "solar_export_today_kwh",
        "battery_export_today_kwh",
        "notification_last_sent",
        "notification_history_last",
    ):
        assert veld in bron, veld


# --- v3.2.0: geen zelfgemaakte helpers op het dashboard --------------


def test_the_dashboard_only_uses_its_own_entities():
    """Gemeld met een screenshot van de kostenpagina: vijf van de zes
    eurotegels stonden op nul, terwijl er onderaan wél "-20,44 € stroom
    deze week" stond.

    Ze lazen negen zelfgemaakte helper-sensoren
    (`sensor.ems_ontlaadwaarde_*`, `..._netlaadkosten_*`,
    `..._accubesparing_*`) die de integratie nergens aanmaakt. Een
    dashboard dat de integratie meelevert mag alleen leunen op wat die
    integratie zelf levert - anders werkt het bij de een en niet bij de
    ander.
    """
    import yaml
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )

    verwezen = set()

    def _loop(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "entity" and isinstance(v, str):
                    verwezen.add(v)
                _loop(v)
        elif isinstance(o, list):
            for x in o:
                _loop(x)

    _loop(data)

    eigenbouw = sorted(e for e in verwezen if e.startswith("sensor.ems_"))

    assert not eigenbouw, (
        "deze entiteiten worden door de integratie niet aangemaakt en "
        f"blijven dus leeg: {eigenbouw}"
    )


def test_the_check_covers_every_domain():
    """De controle keek alleen naar `sensor.`. Een tegel die naar een
    verdwenen switch of button wijst toont "Entiteit niet gevonden"
    zonder dat er iets van te zien was."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("def get_dashboard_health")
    blok = bron[start : bron.index("\n    def ", start + 10)]

    for domein in ("switch", "button", "number", "select"):
        assert domein in blok, domein


# --- structuurscan 19: geen sjabloon waar het niet werkt -------------


def test_no_template_in_a_field_that_does_not_render_one():
    """De fout van 30 augustus (v3.79.0).

    Op de Besturing-kaart stond letterlijk op het dashboard:

        {% set e = 'switch.woonkamer_energy_management_system_han...

    Een `mushroom-entity-card` accepteert geen sjabloon in `name` - dat
    werkt alleen bij een `mushroom-template-card`. De sjabloontekst werd
    dus gewoon als naam getoond.

    Geen foutmelding, geen kapotte kaart: hij ziet er alleen dom uit. En
    dat is precies het soort fout dat blijft staan.
    """
    from pathlib import Path

    import yaml

    import custom_components.energy_management_system as pkg

    sjabloon = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )

    # Kaarttypes die GEEN sjabloon verwerken, met de velden waar het
    # misgaat.
    zonder_sjabloon = {
        "custom:mushroom-entity-card": ("name",),
        "entities": ("title",),
        "custom:mushroom-chips-card": (),
    }

    fouten = []

    def _loop(kaarten, pagina):
        for kaart in kaarten or []:
            if not isinstance(kaart, dict):
                continue
            soort = kaart.get("type")
            for veld in zonder_sjabloon.get(soort, ()):
                waarde = kaart.get(veld)
                if isinstance(waarde, str) and "{%" in waarde:
                    fouten.append(f"{pagina}: {soort}.{veld}")
            for sleutel in ("cards", "sections"):
                _loop(kaart.get(sleutel), pagina)

    for pagina in sjabloon.get("views", []):
        _loop(pagina.get("cards"), pagina.get("title"))
        for sectie in pagina.get("sections", []) or []:
            _loop(sectie.get("cards"), pagina.get("title"))

    assert not fouten, (
        "sjabloon in een veld dat er geen verwerkt - dat komt letterlijk "
        f"op het dashboard te staan: {fouten}"
    )
