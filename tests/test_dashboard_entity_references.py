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
    # v5.62: de pagina-sensoren krijgen hun naam uit één tabel.
    from custom_components.energy_management_system.sensor import (
        DASHBOARD_PAGINA_SENSOREN,
    )

    namen += [rij[1] for rij in DASHBOARD_PAGINA_SENSOREN]
    return {_slug(naam) for naam in namen}


# --- v1.15.3: kaarten die netjes falen ------------------------------


# --- v1.15.5: eenheden en onbekende waarden -------------------------


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


# --- v1.21.5: het venster heet nu wat het is ------------------------


def test_the_discharge_window_sensor_says_what_it_measures():
    """Gemeld: "Tevens een nachtverbruik van 400W? Mijns inziens moet
    dit meer zijn, lijkt wel een uurwaarde?"

    De twijfel was terecht, maar anders dan verwacht. Het getal klopt -
    het is een VERMOGEN, geen dagtotaal - maar de naam niet: er wordt
    gemeten over het ONTLAADVENSTER, vanaf het moment dat de accu gaat
    leveren tot het goedkope laadblok. Dus avond én nacht samen.

    Het geleerde uurprofiel laat 's nachts 200-290 W zien en 's avonds
    300-380 W; de 403 W past bij een venster dat zwaarder op de avond
    leunt.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()
    start = bron.index("class LearnedNightConsumptionSensor")
    blok = bron[start : bron.index("\nclass ", start + 10)]

    assert '_attr_name = "Gemiddeld vermogen in het ontlaadvenster"' in blok
    assert "ontlaadvenster" in blok


def test_the_explanation_names_the_evening():
    """Zonder die uitleg blijft "403 W" te hoog lijken voor een nacht."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()
    start = bron.index("class LearnedNightConsumptionSensor")
    blok = bron[start : bron.index("\nclass ", start + 10)]

    assert "avond én nacht samen" in blok


