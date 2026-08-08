"""Advisory readiness assessment (v0.63.40): "kunnen we een advies
afgeven wanneer betrouwbaar genoeg om er werkelijk iets mee te doen?"

Deliberate honesty distinction: modules with a genuine data-maturity
signal (Kirchhoff, sluipverbruik, Monte Carlo, Kalman, NILM) get a real
readiness status ("klaar"/"bijna_klaar"/"onvoldoende_data"). Modules
with no mechanism comparing past predictions to what actually happened
(Weather Ensemble, MPC, Digital Twin) get "structureel_beschikbaar"
instead - never a false claim of proven accuracy.
"""
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def test_kirchhoff_not_configured(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kirchhoff"]["status"] == "niet_geconfigureerd"


def test_kirchhoff_insufficient_data(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "battery_power_sensor_entity": "sensor.battery_power",
        }
    )
    coordinator.energy_balance_error_history = [1.0, 2.0]
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kirchhoff"]["status"] == "onvoldoende_data"


def test_kirchhoff_ready_with_good_score(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "battery_power_sensor_entity": "sensor.battery_power",
        }
    )
    coordinator.energy_balance_error_history = [0.0] * 20
    coordinator.sensor_health_score = 95.0
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kirchhoff"]["status"] == "klaar"


def test_kirchhoff_quality_too_low(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "battery_power_sensor_entity": "sensor.battery_power",
        }
    )
    coordinator.energy_balance_error_history = [500.0] * 20
    coordinator.sensor_health_score = 30.0
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kirchhoff"]["status"] == "kwaliteit_te_laag"


def test_sluipverbruik_maturity_levels(make_coordinator, hass):
    coordinator = make_coordinator({})

    coordinator.baseline_load_history = [0.2] * 5
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["sluipverbruik"]["status"] == "onvoldoende_data"

    coordinator.baseline_load_history = [0.2] * 15
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["sluipverbruik"]["status"] == "bijna_klaar"

    coordinator.baseline_load_history = [0.2] * 30
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["sluipverbruik"]["status"] == "klaar"


def test_weather_ensemble_starts_without_enough_observations(
    make_coordinator, hass
):
    """v1.0.2: de ensemble heeft nu WEL een meting - hoe vaak hij het
    eens is met wat de panelen werkelijk doen. Hij begint dus bij
    "onvoldoende_data" in plaats van bij het vage
    "structureel_beschikbaar"."""
    coordinator = make_coordinator({})
    coordinator.weather_ensemble_sources_used = ["weather.knmi"]
    coordinator._update_advisory_readiness(DAY0)

    entry = coordinator.advisory_readiness["weather_ensemble"]
    assert entry["status"] == "onvoldoende_data"
    assert "waarnemingen" in entry["reden"]
    # Het aantal actieve bronnen blijft zichtbaar naast het oordeel.
    assert "1 bron(nen)" in entry["reden"]


def test_weather_ensemble_not_configured(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert (
        coordinator.advisory_readiness["weather_ensemble"]["status"]
        == "niet_geconfigureerd"
    )


def test_mpc_labelled_structural_not_ready(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.mpc_horizon_quarters_used = 96
    coordinator._update_advisory_readiness(DAY0)

    status = coordinator.advisory_readiness["mpc"]["status"]
    assert status == "structureel_beschikbaar"
    assert status != "klaar"


def test_monte_carlo_maturity_levels(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["monte_carlo"]["status"] == "onvoldoende_data"

    for h in range(24):
        coordinator.hourly_consumption_profile[h] = [0.3] * 7
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["monte_carlo"]["status"] == "klaar"


def test_kalman_not_configured(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kalman"]["status"] == "niet_geconfigureerd"


def test_kalman_converges_after_many_consistent_updates(make_coordinator, hass):
    coordinator = make_coordinator(
        {"available_energy_sensor_entity": "sensor.available_energy"}
    )
    for _ in range(50):
        coordinator._kalman_soc.update(3.0)
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kalman"]["status"] in (
        "klaar",
        "bijna_klaar",
    )


def test_digital_twin_starts_without_enough_comparisons(make_coordinator, hass):
    """v1.0.1: de twin heeft nu WEL een nauwkeurigheidsmeting, dus hij
    begint bij "onvoldoende_data" in plaats van bij het vage
    "structureel_beschikbaar" - en klimt op zodra er genoeg afgeronde
    vergelijkingen zijn."""
    coordinator = make_coordinator({})
    coordinator.digital_twin_trajectory = [{"start": "x", "mode": "smart", "soc_kwh": 1.0}]
    coordinator.digital_twin_hours_simulated = 24
    coordinator._update_advisory_readiness(DAY0)

    entry = coordinator.advisory_readiness["digital_twin"]
    assert entry["status"] == "onvoldoende_data"
    assert "vergelijkingen" in entry["reden"]
    # De simulatieduur blijft zichtbaar naast het nieuwe oordeel.
    assert "24 uur" in entry["reden"]


def test_nilm_not_configured(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["nilm"]["status"] == "niet_geconfigureerd"


def test_nilm_maturity_across_devices(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices = {
        "sensor.a": {"friendly_name": "A", "daily_avg_history": [1.0] * 30},
        "sensor.b": {"friendly_name": "B", "daily_avg_history": [1.0] * 5},
    }
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["nilm"]["status"] == "bijna_klaar"

    coordinator.nilm_confirmed_devices["sensor.b"]["daily_avg_history"] = [1.0] * 30
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["nilm"]["status"] == "klaar"


def test_all_ten_modules_always_present(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    expected = {
        "kirchhoff",
        "sluipverbruik",
        "weather_ensemble",
        "mpc",
        "monte_carlo",
        "kalman",
        "digital_twin",
        "nilm",
        "extra_dip_marge",
        "temperatuur_regressie",
    }
    assert set(coordinator.advisory_readiness.keys()) == expected


def test_never_calls_any_hass_service(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert hass.services.calls == []


def test_extra_dip_marge_klaar_with_enough_samples(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.extra_dip_margin_history = [0.05, 0.06, 0.07]

    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["extra_dip_marge"]["status"] == "klaar"


def test_extra_dip_marge_onvoldoende_data_without_samples(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.extra_dip_margin_history = []

    coordinator._update_advisory_readiness(DAY0)

    assert (
        coordinator.advisory_readiness["extra_dip_marge"]["status"]
        == "onvoldoende_data"
    )


def test_temperatuur_regressie_klaar_with_enough_samples(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        TEMP_CONSUMPTION_MIN_SAMPLES,
    )

    coordinator = make_coordinator({})
    coordinator.temp_consumption_history = [
        {"temp_c": float(i), "kwh": 3.0} for i in range(TEMP_CONSUMPTION_MIN_SAMPLES)
    ]

    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["temperatuur_regressie"]["status"] == "klaar"


def test_temperatuur_regressie_onvoldoende_data_without_samples(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.temp_consumption_history = []

    coordinator._update_advisory_readiness(DAY0)

    assert (
        coordinator.advisory_readiness["temperatuur_regressie"]["status"]
        == "onvoldoende_data"
    )


# --- v1.0.3: de legenda mag niet achterlopen op de code ------------


def _legenda_tekst():
    """De legenda als één doorlopende regel.

    De YAML-bronopmaak breekt zinnen over meerdere regels af, dus een
    letterlijke zoekopdracht op een zinsdeel zou stuklopen op een
    regelafbreking die niets met de inhoud te maken heeft.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    # v1.3.0: het Betrouwbaarheid-tabblad heeft óók een kaart met de
    # titel "Legenda". Alleen op titel zoeken pakt dan de verkeerde, dus
    # eerst het juiste tabblad opzoeken.
    # v1.10.1: het Advies-tabblad is samengevoegd in "Kwaliteit". Daar
    # staan nu twee kaarten met de titel "Legenda" - die van de
    # betrouwbaarheidsschaal en die van de adviesmodules - dus zoeken op
    # titel alleen is niet genoeg; de inhoud onderscheidt ze.
    for view in data["views"]:
        if view.get("title") != "Kwaliteit":
            continue
        for card in view.get("cards") or []:
            if card.get("title") == "Legenda" and "MPC" in card.get(
                "content", ""
            ):
                return " ".join(card["content"].split())
    raise AssertionError("geen legenda-kaart gevonden op het Advies-tabblad")


def test_legend_does_not_claim_weather_ensemble_is_unmeasured(
    make_coordinator, hass
):
    """De legenda noemde tot v1.0.2 nog "de drie modules zonder
    mechanisme dat een voorspelling ooit tegen de werkelijkheid legt
    (Weather Ensemble, MPC, Digital Twin)". Twee daarvan meten zichzelf
    inmiddels wél - de tekst was achtergebleven bij de code.
    """
    tekst = _legenda_tekst()

    assert "drie modules" not in tekst
    assert "(Weather Ensemble, MPC, Digital Twin)" not in tekst


def test_legend_still_explains_why_mpc_cannot_be_measured():
    """MPC hoort er wél te blijven staan, mét de reden - anders wordt
    "consistentie" later een argument om er alsnog een meting bij te
    verzinnen die niets meet."""
    tekst = _legenda_tekst()

    assert "MPC" in tekst
    assert "niet wordt uitgevoerd" in tekst


def test_legend_mentions_the_digital_twin_fallback():
    """De twin kan nog steeds in deze categorie belanden: met een
    gemeten afwijking maar zonder bekende accucapaciteit valt niet te
    zeggen of die afwijking veel of weinig is. Dat hoort er eerlijk in
    te staan in plaats van "geldt nog voor één module"."""
    tekst = _legenda_tekst()

    assert "Digital Twin" in tekst
    assert "accucapaciteit onbekend" in tekst


def test_weather_ensemble_can_reach_ready_now(make_coordinator, hass):
    """Gedragsbewijs achter die legenda-tekst: de ensemble kan
    daadwerkelijk "klaar" bereiken, iets wat vóór v1.0.2 onmogelijk
    was."""
    coordinator = make_coordinator({})
    coordinator.weather_ensemble_sources_used = ["weather.knmi"]
    coordinator.weather_ensemble_agreement_history = [True] * 25

    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["weather_ensemble"]["status"] == "klaar"


# --- v1.0.5: geen module mag onzichtbaar blijven -------------------


def _dashboard_modulelabels():
    """De labels die het Advies-tabblad hardcodeert, uit de
    `namen`-dict in de markdown-kaart."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    blok = yaml_tekst[yaml_tekst.index("{% set namen = {") :]
    blok = blok[: blok.index("} %}")]
    return set(re.findall(r"'([a-z_]+)':", blok))


def test_every_readiness_module_is_shown_on_the_dashboard(
    make_coordinator, hass
):
    """Gerapporteerd via een screenshot: de kaart zei "8 adviesmodules"
    terwijl er er tien zijn. `extra_dip_marge` en
    `temperatuur_regressie` werden nergens getoond - ze bestonden, werden
    berekend, maar vielen buiten de hardcoded namenlijst.

    Deze test laat de suite falen zodra er een module bijkomt zonder
    label, in plaats van dat die stilzwijgend onzichtbaar blijft.
    """
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    ontbreekt = set(coordinator.advisory_readiness) - _dashboard_modulelabels()

    assert not ontbreekt, (
        "deze adviesmodules worden nergens getoond - voeg een label toe "
        f"aan de namen-dict op het Advies-tabblad: {sorted(ontbreekt)}"
    )


def test_no_label_without_a_matching_module(make_coordinator, hass):
    """Andersom net zo: een label voor een module die niet meer bestaat
    zou een lege regel met "onbekend" opleveren."""
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    overbodig = _dashboard_modulelabels() - set(coordinator.advisory_readiness)

    assert not overbodig, sorted(overbodig)


def test_dashboard_counts_match_the_actual_number(make_coordinator, hass):
    """De teksten noemden "acht" op drie plekken terwijl het er tien
    zijn. Het getal hoort te kloppen met de code, niet met wat er ooit
    waar was."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)
    aantal = len(coordinator.advisory_readiness)
    assert aantal == 10

    yaml_tekst = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    assert "Alle tien modules" in yaml_tekst
    # v1.0.5: de tekst zegt niet langer dat álle tien adviserend zijn -
    # zie test_dashboard_states_which_module_acts.
    assert "van de tien" in " ".join(yaml_tekst.split())
    assert "acht modules" not in yaml_tekst.lower()


def test_readiness_count_row_explains_its_number(make_coordinator, hass):
    """De waarde is een kaal getal ("1"). Zonder uitleg is niet te zien
    dat het om "aantal klaar van tien" gaat."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()

    assert "aantal 'klaar' van 10" in yaml_tekst


# --- v1.0.5: welke modules sturen daadwerkelijk aan? ----------------

# De enige module in de gereedheidslijst die géén advies geeft maar
# werkelijk een laadcommando stuurt. Bewust een expliciete verzameling:
# komt er ooit een tweede bij, dan hoort iemand deze regel te wijzigen
# en daarmee bewust te bevestigen dat het dashboard dat ook vermeldt.
AANSTURENDE_MODULES = {"extra_dip_marge"}


def test_the_acting_module_actually_sends_a_command():
    """Onderbouwing van de claim, uit de code zelf: het extra-dip-pad
    roept `_async_apply_manual` aan en zet een eigen beslissingsreden.
    Zie ook `test_low_solar_extra_dip_charging.py`, dat het gedrag
    end-to-end vastlegt."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH:")
    blok = bron[start : start + 900]

    assert "_async_apply_manual" in blok
    assert "grid_charging_low_solar_extra_dip" in blok


def test_advisory_modules_never_reach_the_decision_tree():
    """De andere negen mogen hun uitkomst nergens in de beslislogica
    laten meewegen. Gecontroleerd op de uitkomstvelden zelf: die worden
    berekend en getoond, maar nooit gelezen om een besluit op te
    baseren."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    # Per module het veld waarin de uitkomst landt.
    uitkomsten = {
        "mpc": "mpc_projected_total_profit_eur",
        "monte_carlo": "monte_carlo_shortfall_probability_percent",
        "digital_twin": "digital_twin_projected_profit_eur",
        "kalman": "kalman_soc_filtered_kwh",
        "weather_ensemble": "weather_ensemble_cloud_cover_percent",
        "temperatuur_regressie": "temp_consumption_prediction_error_history",
    }
    for module, veld in uitkomsten.items():
        # Elke regel die dit veld LEEST (geen toewijzing) mag niet in een
        # voorwaarde staan die tot een commando leidt.
        lezend = [
            regel.strip()
            for regel in bron.split("\n")
            if f"self.{veld}" in regel and f"self.{veld} =" not in regel
        ]
        for regel in lezend:
            assert "_async_apply" not in regel, f"{module}: {regel}"


def test_dashboard_states_which_module_acts():
    """Het tabblad claimde dat alle tien uitsluitend adviserend zijn.
    Dat klopte niet voor de extra-dip-laadmarge - en juist bij een
    integratie die de accu aanstuurt is dat het soort onwaarheid dat je
    niet wilt hebben staan."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    plat = " ".join(yaml_tekst.split())

    assert "Negen van de tien zijn uitsluitend adviserend" in plat
    assert "Extra-dip-laadmarge (⚡) stuurt wél aan" in plat
    assert "Tien modules zijn uitsluitend adviserend" not in plat


def test_the_acting_module_is_marked_in_the_table():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()

    assert "⚡ Extra-dip-laadmarge (stuurt aan)" in yaml_tekst
