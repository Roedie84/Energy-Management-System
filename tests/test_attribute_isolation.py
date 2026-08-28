"""Eén fout mag niet alles blanco maken (v1.19.1).

Gemeld met screenshot: alle acht tegels onder "Status per onderwerp"
toonden tegelijk "Nog geen gegevens" - wat niet kan, want ze lezen
verschillende onderwerpen.

Twee oorzaken, allebei dezelfde vorm:

1. Het attributenblok van de GACS-sensor was één dict-expressie. Gooit
   één aanroep een fout, dan mislukt het HELE blok en heeft Home
   Assistant geen enkel attribuut meer.

2. `get_topic_summaries` roept intern `get_pv_forecast_quality` aan (sinds
   v1.17.5, voor de zon-samenvatting). Faalt die, dan valt de hele lijst
   van acht weg.

Vandaag zijn er vijf aanroepen aan dat blok toegevoegd; elke toevoeging
vergrootte de kans dat álles wegvalt op een fout in één onderdeel.
"""


def _sensor_klasse():
    import custom_components.energy_management_system.sensor as m

    return next(
        getattr(m, naam)
        for naam in dir(m)
        if "acs" in naam.lower() and naam.endswith("Sensor")
    )


def _met_kapotte(make_coordinator, naam):
    c = make_coordinator({})

    def stuk():
        raise KeyError("gesimuleerde fout")

    setattr(c, naam, stuk)
    return c


# --- het attributenblok ----------------------------------------------


def test_one_broken_call_does_not_blank_the_rest(make_coordinator, hass):
    c = _met_kapotte(make_coordinator, "get_pv_forecast_quality")

    attributen = _sensor_klasse()(c, "x").extra_state_attributes

    assert "samenvattingen" in attributen
    assert "aanwezigheid" in attributen
    assert "uitbreidingsadvies" in attributen


def test_the_failure_is_visible(make_coordinator, hass):
    """Stil terugvallen is erger dan een foutmelding: dan zoek je in de
    verkeerde hoek."""
    c = _met_kapotte(make_coordinator, "get_pv_forecast_quality")

    attributen = _sensor_klasse()(c, "x").extra_state_attributes

    assert "KeyError" in str(attributen["pv_voorspelkwaliteit"])


def test_a_broken_gacs_assessment_is_survivable(make_coordinator, hass):
    c = _met_kapotte(make_coordinator, "get_gacs_assessment")

    attributen = _sensor_klasse()(c, "x").extra_state_attributes

    assert "samenvattingen" in attributen
    assert "gacs_fout" in attributen


# --- de samenvattingen zelf ------------------------------------------


def test_all_eight_topics_survive_a_pv_failure(make_coordinator, hass):
    """De kern van de melding: de zon-samenvatting hangt aan
    `get_pv_forecast_quality`, en die sleepte de andere zeven mee."""
    c = _met_kapotte(make_coordinator, "get_pv_forecast_quality")

    samenvattingen = _sensor_klasse()(c, "x").extra_state_attributes[
        "samenvattingen"
    ]

    assert len(samenvattingen) == 8
    for onderwerp in (
        "zon",
        "accumodules",
        "apparaten",
        "zelflerend",
        "financieel",
        "klimaat",
        "water",
        "kwaliteit",
    ):
        assert onderwerp in samenvattingen, onderwerp


def test_the_sun_topic_still_says_something(make_coordinator, hass):
    """Ook het gefaalde onderwerp hoort een leesbare zin te geven."""
    c = _met_kapotte(make_coordinator, "get_pv_forecast_quality")

    zon = _sensor_klasse()(c, "x").extra_state_attributes["samenvattingen"]["zon"]

    assert zon["zin"]
    assert "kWh opgewekt" in zon["zin"]


def test_every_topic_has_a_sentence(make_coordinator, hass):
    """Geen enkel onderwerp mag leeg blijven, ook niet bij een fout."""
    c = _met_kapotte(make_coordinator, "get_pv_forecast_quality")

    samenvattingen = _sensor_klasse()(c, "x").extra_state_attributes[
        "samenvattingen"
    ]

    for onderwerp, gegevens in samenvattingen.items():
        assert gegevens.get("zin"), onderwerp
        assert gegevens.get("niveau"), onderwerp


# --- borging ---------------------------------------------------------


def test_the_block_is_built_incrementally():
    """Terugvallen op één dict-expressie zou de fout terugbrengen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()
    start = bron.index("def extra_state_attributes(self) -> dict:\n        \"\"\"Alle samenvattingen")
    # v3.61.0: tot het EINDE van de functie in plaats van een vast
    # aantal tekens.
    #
    # Dat aantal is drie keer opgehoogd - 2500, 3500, 4500 - en elke
    # keer om dezelfde reden: de lijst met samenvattingen groeit en het
    # commentaar erbij ook. Valkuil 5 uit de overdracht, en die staat er
    # letterlijk boven.
    #
    # De functie loopt tot de volgende definitie op hetzelfde
    # inspringniveau. Dan hoeft er nooit meer aan een getal gesleuteld
    # te worden.
    einde = bron.find("\n    def ", start + 1)
    blok = bron[start : einde if einde > 0 else len(bron)]

    assert "for sleutel, functie in" in blok
    assert "except Exception" in blok


# --- v1.25.0: te groot om te bewaren ---------------------------------


def test_the_big_attributes_stay_out_of_the_recorder():
    """Deze sensor draagt de tekst voor een stuk of tien pagina's en zat
    met 36 planregels al op ruim 21 kB. Home Assistant slaat de
    attributen van een toestand boven 16 kB niet meer op; nu de planning
    zoveel regels telt als er prijzen zijn, wordt dat alleen erger.

    De kaarten lezen de huidige toestand, niet de geschiedenis - er
    verdwijnt dus niets waar iemand op terugkijkt.
    """
    niet_bewaard = _sensor_klasse()._unrecorded_attributes

    for sleutel in (
        "kwartierplanning",
        "kwartier_samenvatting",
        "samenvattingen",
        "aanwezigheid",
        "uitbreidingsadvies",
    ):
        assert sleutel in niet_bewaard


def test_the_dashboard_attribute_is_the_compact_plan(make_coordinator, hass):
    """Het attribuut hoort de compacte variant te zijn - anders groeit
    het met vijftien velden per regel mee met de horizon.
    """
    c = make_coordinator({})
    gezien = []
    c.get_quarter_plan_compact = lambda *a, **k: gezien.append(True) or []

    _sensor_klasse()(c, "x").extra_state_attributes

    assert gezien


# --- v1.72.0: hetzelfde voor de andere entiteitsbestanden ------------


def test_no_entity_file_calls_a_missing_coordinator_method():
    """De knop "Nu laden" riep `async_request_refresh` aan, een methode
    van `DataUpdateCoordinator` die deze coordinator niet heeft. Alle
    tests bleven groen omdat niemand de knop indrukte.

    Deze toets loopt alle entiteitsbestanden na.
    """
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator,
    )

    map_ = Path(pkg.__file__).parent
    ontbreekt = []
    for bestand in ("switch.py", "sensor.py", "button.py", "number.py", "select.py"):
        pad = map_ / bestand
        if not pad.exists():
            continue
        for naam in sorted(
            set(re.findall(r"_coordinator\.([a-z_][a-z_0-9]*)\(", pad.read_text()))
        ):
            if not hasattr(EnergyManagementSystemCoordinator, naam):
                ontbreekt.append(f"{bestand}: {naam}")

    assert not ontbreekt, ontbreekt
