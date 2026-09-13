"""De plaat als AFBEELDING in plaats van als ruwe SVG (v3.26.0).

Gemeld, vier keer achter elkaar: "de visuele pagina toont platte tekst in
plaats van een plaatje." Drie verklaringen geprobeerd en alle drie fout:
`<a href>` weggehaald (v3.23.0), twee SVG's over twee kaarten gesplitst
(v3.25.3), `<animate>` vervangen (v3.25.4). Geen ervan hielp, omdat geen
ervan de oorzaak was.

De oorzaak staat in de bron van de Home Assistant frontend en is met
zekerheid na te lezen:

`src/panels/lovelace/cards/hui-markdown-card.ts` rendert

    <ha-markdown cache breaks .content=${...}></ha-markdown>

ZONDER het attribuut `allow-svg`. In `ha-markdown.ts` is de standaard van
die eigenschap `false`. Daardoor draait `markdown-worker.ts` met de
gewone witte lijst, en die kent GEEN enkel SVG-element - ook `<svg>`
zelf niet. De xss-opschoner ontsnapt alles wat niet op die lijst staat
naar tekst. Dat is exact de klacht: de hele plaat verschijnt als tekst.

Zelfs mét `allow-svg` zou het niet werken. De SVG-lijst is:

    svg:  xmlns, height, width
    path: transform, stroke, d
    img:  src

Geen `viewBox`, geen `rect`, `text`, `circle`, `line`, `g`, `tspan`,
`polygon`, `ellipse` - en de plaat bestaat vrijwel volledig uit die
elementen.

Ruwe SVG in een markdown-kaart kan dus NOOIT werken. Wat wél door de
opschoner komt is `<img>`: die staat in de gewone witte lijst, en
`safeAttrValue` in de xss-bibliotheek laat `data:image/` uitdrukkelijk
toe. De plaat gaat daarom als data-URI door een `<img>` heen.

Dit is geen dashboardwijziging: de kaart leest dezelfde sensorattributen
als eerst. Opnieuw importeren is niet nodig.
"""
import base64
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent
sys.path.insert(0, str(PAKKET))

from overview_svg import (  # noqa: E402
    als_afbeelding,
    bouw_overzicht,
    bouw_scada,
    bouw_secties,
    bouw_status,
)


def _plaat() -> str:
    return bouw_scada(
        {
            "status": "goed",
            "soc": 87.0,
            "omvormer_c": 31.0,
            "beschikbaar_kwh": 6.6,
            "accu_w": -430.0,
            "pv_w": 210.0,
            "net_w": 180.0,
            "huis_w": 820.0,
            "koeling": {"ventilator_aan": True, "buiten_c": 17.9},
        }
    )


# --- 1. wat er de kaart in gaat --------------------------------------


def test_the_plate_leaves_as_an_image_tag():
    """Alleen `<img>` overleeft de opschoner van de markdown-kaart."""
    uit = als_afbeelding(_plaat(), "Overzicht accu-installatie")

    assert uit.startswith("<img ")
    assert 'src="data:image/svg+xml;base64,' in uit


def test_no_raw_svg_element_is_handed_to_the_card():
    """Een `<svg` in de kaartinhoud is precies wat als tekst verschijnt."""
    uit = als_afbeelding(_plaat())

    assert "<svg" not in uit
    assert "<rect" not in uit
    assert "<text" not in uit


def test_the_data_uri_survives_the_xss_filter_rules():
    """`safeAttrValue` laat voor `src` alleen een handvol voorvoegsels

    toe, waaronder `data:image/`. Base64 is gekozen omdat de plaat vol
    `#`-kleurcodes staat; die breken een niet-gecodeerde data-URI.
    """
    uit = als_afbeelding(_plaat())
    bron = re.search(r'src="([^"]+)"', uit).group(1)

    assert bron.startswith("data:image/")
    assert re.fullmatch(r"[A-Za-z0-9+/=]+", bron.split(",", 1)[1])


# --- 2. wat er in de afbeelding zit ----------------------------------


def _ingepakte_svg(uit: str) -> str:
    blok = re.search(r"base64,([^\"]+)", uit).group(1)
    return base64.b64decode(blok).decode("utf-8")


def test_the_encoded_plate_is_still_valid_svg():
    svg = _ingepakte_svg(als_afbeelding(_plaat()))

    ET.fromstring(svg)


def test_the_plate_gets_a_real_size_instead_of_a_percentage():
    """`width="100%"` op de wortel is binnen een `<img>` betekenisloos:

    de browser kent dan geen eigen afmeting en valt terug op 300 bij 150
    pixels. Met een maat uit de `viewBox` klopt de verhouding, en de
    regel `img { max-width: 100% }` van `ha-markdown` laat hem alsnog
    meeschalen op een telefoon.
    """
    svg = _ingepakte_svg(als_afbeelding(_plaat()))
    wortel = ET.fromstring(svg)

    assert 'width="100%"' not in svg
    assert wortel.get("width") == "760"
    assert wortel.get("height") == wortel.get("viewBox").split()[3]


def test_every_plate_keeps_its_own_ratio():
    """De statusplaat groeit met het aantal onderwerpen; een vaste hoogte

    zou hem uitrekken.
    """
    for plaat in (
        bouw_overzicht({}),
        bouw_scada({}),
        bouw_secties({"secties": [("test", [("a", "b", None)])]}),
        bouw_status(
            {"onderwerpen": {"water": {"niveau": "betrouwbaar", "zin": "x"}}}
        ),
    ):
        if not plaat:
            continue
        wortel = ET.fromstring(_ingepakte_svg(als_afbeelding(plaat)))
        _, _, b, h = wortel.get("viewBox").split()

        assert (wortel.get("width"), wortel.get("height")) == (b, h)


def test_an_empty_plate_stays_empty():
    """De statusplaat geeft niets terug als er geen onderwerpen zijn; een

    lege afbeelding zou een gebroken plaatje-icoon opleveren.
    """
    assert als_afbeelding("") == ""
    assert als_afbeelding(None) == ""


def test_the_alt_text_shows_what_is_missing():
    """Laadt de afbeelding niet, dan is de alt-tekst het enige spoor."""
    uit = als_afbeelding(_plaat(), "Overzicht accu-installatie")

    assert 'alt="Overzicht accu-installatie"' in uit


# --- 3. dat de sensor het ook echt zo levert -------------------------


def test_the_coordinator_never_returns_a_bare_plate():
    """De drie getters vullen sensorattributen die rechtstreeks in een

    markdown-kaart terechtkomen. Geeft één ervan de kale bouwfunctie
    terug, dan is de klacht meteen weer terug.
    """
    bron = (PAKKET / "coordinator.py").read_text()

    for naam in (
        "get_overview_svg",
        "get_overview_sections_svg",
        "get_overview_status_svg",
    ):
        begin = bron.index(f"def {naam}(")
        romp = bron[begin:]
        romp = romp[: romp.index("\n    def ", 1)]

        assert "als_afbeelding(" in romp, f"{naam} levert ruwe SVG"


def test_the_dashboard_reads_those_attributes_unchanged():
    """Het dashboard verandert niet, dus hoeft de gebruiker het niet

    opnieuw te importeren. Wijzigt dit ooit wel, dan hoort daar een
    uitdrukkelijke instructie bij.
    """
    import yaml

    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    visueel = next(v for v in data["views"] if v.get("title") == "Visueel")
    inhoud = yaml.dump(visueel)

    assert "overzichtsplaat" in inhoud
    assert "overzichtsecties" in inhoud
