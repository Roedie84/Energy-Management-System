"""Airco-verwachting toont nu de kans (v1.17.6).

Gemeld: "Wat zegt dit nu? Ik dacht dat hier de verwachting in % of de
airco aan zou gaan of niet. Ik zet de airco altijd zelf aan en ook daar
kan van geleerd worden toch, in combinatie met de verwachte temperatuur
etc."

Dat leermechanisme bestond al sinds v0.63.55 en doet precies dat: elke
temperatuurmeting gaat in een bin van 1 °C en krijgt een uur de tijd;
gaat de airco in dat uur aan, dan telt die waarneming als "ja".

Maar de sensor gaf de HUIDIGE woonkamertemperatuur terug - hetzelfde
getal dat de temperatuursensor al toont. De kans zat in een attribuut dat
nergens in beeld kwam.
"""


def _met_bins(make_coordinator, temp, bins):
    c = make_coordinator({})
    c.living_room_current_temp_c = temp
    c.living_room_temp_bucket_history = dict(bins)
    return c


# --- de kern ---------------------------------------------------------


def test_the_probability_grows_with_temperature(make_coordinator, hass):
    """Het punt van de melding: bij welke temperatuur grijp je in?"""
    c = _met_bins(
        make_coordinator,
        26.4,
        {
            "22.0": [False] * 20,
            "25.0": [False] * 18 + [True] * 2,
            "26.0": [True] * 7 + [False] * 3,
            "27.0": [True] * 9 + [False],
        },
    )

    assert c.get_airco_activation_probability("22.0")["probability_percent"] == 0.0
    assert c.get_airco_activation_probability("25.0")["probability_percent"] == 10.0
    assert c.get_airco_activation_probability("26.0")["probability_percent"] == 70.0
    assert c.get_airco_activation_probability("27.0")["probability_percent"] == 90.0


def test_the_sensor_returns_a_percentage_not_a_temperature():
    """De sensor heette "Airco-verwachting" maar gaf een temperatuur -
    hetzelfde getal dat elders al stond."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()
    start = bron.index('_attr_name = "Airco-verwachting')
    blok = bron[start : start + 1800]

    assert '_attr_native_unit_of_measurement = "%"' in blok
    assert "living_room_current_temp_c" not in blok.split("def native_value")[1][:200]


def test_the_name_says_what_it_is():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()

    assert 'Airco-verwachting (kans binnen 1 uur)' in bron


# --- de bins zijn zichtbaar ------------------------------------------


def test_all_learned_bins_are_exposed():
    """Alleen de huidige bin tonen laat de vraag open bij welke
    temperatuur je normaal ingrijpt."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()

    assert '"geleerde_buckets"' in bron


def test_the_card_shows_the_bins():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    klimaat = next(v for v in data["views"] if v["path"] == "detail-klimaat")
    kaarten = [k for s in klimaat["sections"] for k in s.get("cards") or []]

    kaart = next(k for k in kaarten if "airco" in str(k.get("title", "")).lower())

    assert "geleerde_buckets" in kaart["content"]
    assert "20 waarnemingen" in kaart["content"]


def test_the_card_explains_the_mechanism():
    """Zonder uitleg is niet te beoordelen waarom een bin op 0% staat."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    klimaat = next(v for v in data["views"] if v["path"] == "detail-klimaat")
    kaarten = [k for s in klimaat["sections"] for k in s.get("cards") or []]

    kaart = next(k for k in kaarten if "airco" in str(k.get("title", "")).lower())

    assert "bin van 1 °C" in kaart["content"]
    assert "een uur de tijd" in kaart["content"]


def test_zero_percent_is_a_real_answer(make_coordinator, hass):
    """0% betekent "je zet hem hier nooit aan" - dat is informatie, geen
    ontbrekende meting."""
    c = _met_bins(make_coordinator, 22.0, {"22.0": [False] * 20})

    resultaat = c.get_airco_activation_probability("22.0")

    assert resultaat["probability_percent"] == 0.0
    assert resultaat["sample_count"] == 20


# --- v1.18.1: werkt het ook in de winter? ---------------------------


def test_it_works_in_winter_too():
    """Gevraagd: "Werkt het airco-voorspellingsmechanisme ook in de
    winter (dus bij te koude temperaturen)?"

    Ja: de bins zijn richtingsneutraal, en `AIRCO_ACTIVE_HVAC_ACTIONS`
    bevat zowel "heating" als "cooling". Bij 18 °C leert hij dus wanneer
    je gaat stoken, bij 26 °C wanneer je gaat koelen.
    """
    from custom_components.energy_management_system.const import (
        AIRCO_ACTIVE_HVAC_ACTIONS,
    )

    assert "heating" in AIRCO_ACTIVE_HVAC_ACTIONS
    assert "cooling" in AIRCO_ACTIVE_HVAC_ACTIONS


def test_a_cold_bin_learns_just_like_a_warm_one(make_coordinator, hass):
    c = _met_bins(
        make_coordinator,
        18.4,
        {"18.0": [True] * 8 + [False] * 2, "26.0": [True] * 7 + [False] * 3},
    )

    assert c.get_airco_activation_probability("18.0")["probability_percent"] == 80.0
    assert c.get_airco_activation_probability("26.0")["probability_percent"] == 70.0


def test_the_direction_is_recorded(make_coordinator, hass):
    """"60% kans dat de airco aangaat" betekent iets heel anders bij 18
    dan bij 26 graden - dat zijn tegengestelde acties met een
    tegengesteld gevolg voor het verbruik."""
    c = _met_bins(
        make_coordinator,
        18.4,
        {"18.0": [True] * 8, "26.0": [True] * 7},
    )
    c.living_room_temp_bucket_direction = {
        "18.0": ["verwarmen"] * 8,
        "26.0": ["koelen"] * 7,
    }

    assert c.get_airco_activation_probability("18.0")["richting"] == "verwarmen"
    assert c.get_airco_activation_probability("26.0")["richting"] == "koelen"


def test_without_direction_data_it_stays_empty(make_coordinator, hass):
    """Bins van vóór deze versie hebben geen richting; die mogen er niet
    op stuklopen."""
    c = _met_bins(make_coordinator, 22.0, {"22.0": [False] * 20})

    assert c.get_airco_activation_probability("22.0")["richting"] is None


def test_the_card_shows_the_direction():
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    klimaat = next(v for v in data["views"] if v["path"] == "detail-klimaat")
    kaarten = [k for s in klimaat["sections"] for k in s.get("cards") or []]

    kaart = next(
        k
        for k in kaarten
        if "airco" in str(k.get("title", "")).lower() and k.get("type") == "markdown"
    )

    assert "Richting" in kaart["content"]
    assert "het hele jaar" in kaart["content"]
