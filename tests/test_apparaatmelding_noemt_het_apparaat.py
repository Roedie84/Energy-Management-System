"""De melding zegt niet welk apparaat klaar is (v3.93.1).

Gemeld met vier voorbeelden van 31 augustus:

    12:39  'n Apparaat is klaor   "Klaor na ongeveer 8 minuten."
    12:30  'n Apparaat is klaor   "Klaor na ongeveer 16 minuten."
    12:01  'n Apparaat is klaor   "De fietsladers bunt uitgeschakeld ..."
    11:53  'n Apparaat is klaor   "De steelstofzuiger is klaor ..."

"Maar kan dan niet zien welk apparaat."

De Nederlandse titels noemen het apparaat wel degelijk: "🍽️ Vaatwasser
klaar", "🧺 Wasmachine klaar", "🧹 Steelstofzuiger opgeladen", "🚲
Fietsen opgeladen". `_naar_achterhoeks` vervangt die door één vaste
titel per SOORT, en daarmee is de naam weg.

Dat de laatste twee toch te herkennen zijn, komt doordat hun BERICHT het
apparaat noemt. De twee cyclusmeldingen hebben alleen "Klaar na ongeveer
X minuten", en die zijn dus niet uit elkaar te houden.

Dit is precies de fout die in v3.1.0 al is gerepareerd voor de
accukoeling - "Accukoeling an of uut, terwijl het of aan of uit is" -
maar alleen daar. Hetzelfde geldt voor `handmatige_stand`, waar "✋ De
accu staat nog handmatig" en "🔋 De accu is vol" allebei op één titel
uitkwamen.
"""
import pytest

from custom_components.energy_management_system.const import (
    ACHTERHOEKS_TITELS,
)

CYCLUS_TITELS = [
    "🍽️ Vaatwasser klaar",
    "🧺 Wasmachine klaar",
    "🧹 Steelstofzuiger opgeladen",
    "🚲 Fietsen opgeladen",
]

HANDMATIG_TITELS = [
    "✋ De accu staat nog handmatig",
    "🔋 De accu is vol",
]


def _vertaald(c, titels, soort):
    return [c._naar_achterhoeks(t, soort) for t in titels]


def test_elke_apparaatmelding_houdt_zijn_eigen_titel(make_coordinator, hass):
    """Vier apparaten, vier titels. Waren er één."""
    c = make_coordinator({})

    vertaald = _vertaald(c, CYCLUS_TITELS, "appliance_ready")

    assert len(set(vertaald)) == len(CYCLUS_TITELS)


def test_de_vaatwasser_staat_er_met_naam_in(make_coordinator, hass):
    c = make_coordinator({})

    assert "Vaatwasser" in c._naar_achterhoeks(
        "🍽️ Vaatwasser klaar", "appliance_ready"
    )


def test_de_titel_is_nog_wel_achterhoeks(make_coordinator, hass):
    """De naam behouden mag niet betekenen dat de vertaling wegvalt."""
    c = make_coordinator({})

    assert c._naar_achterhoeks("🍽️ Vaatwasser klaar", "appliance_ready") == (
        "🍽️ Vaatwasser klaor"
    )


def test_handmatig_en_vol_blijven_twee_meldingen(make_coordinator, hass):
    """"De accu staat nog handmatig" en "De accu is vol" zijn niet

    hetzelfde bericht.
    """
    c = make_coordinator({})

    vertaald = _vertaald(c, HANDMATIG_TITELS, "handmatige_stand")

    assert len(set(vertaald)) == 2


def test_soorten_met_een_vaste_titel_blijven_werken(make_coordinator, hass):
    """De vaste titels bestaan niet voor niets: waar er maar één

    boodschap is, leest een geschreven Achterhoekse zin beter dan een
    woord-voor-woord vertaling.
    """
    c = make_coordinator({})

    assert c._naar_achterhoeks("Accu haalt de nacht niet", "battery_wont_last_night") == (
        ACHTERHOEKS_TITELS["battery_wont_last_night"]
    )


def test_de_twee_soorten_hebben_geen_vaste_titel_meer():
    """Een vaste titel per soort kan alleen als er ook maar één

    boodschap per soort is.
    """
    assert "appliance_ready" not in ACHTERHOEKS_TITELS
    assert "handmatige_stand" not in ACHTERHOEKS_TITELS


def test_het_bericht_noemt_het_apparaat_ook(make_coordinator, hass):
    """De titel wordt op een telefoon soms afgekapt. "Klaar na ongeveer

    8 minuten" zegt dan nog steeds niets.
    """
    c = make_coordinator({})

    bericht = c._cyclus_klaar_bericht("Vaatwasser", 8.0)

    assert "Vaatwasser" in bericht
    assert "8" in bericht


def test_zonder_bekende_duur_blijft_het_bericht_kloppen(
    make_coordinator, hass
):
    c = make_coordinator({})

    bericht = c._cyclus_klaar_bericht("Wasmachine", None)

    assert "Wasmachine" in bericht
    assert "onbekende tijd" in bericht
