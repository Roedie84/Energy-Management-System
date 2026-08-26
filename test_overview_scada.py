"""De visuele pagina in SCADA-stijl (v3.17.0).

Gevraagd naar aanleiding van een schermafbeelding van een Grid Support
Unit: "Deze style vind ik wel mooi" - en daarna: "Ik wil alleen de
'visueel' pagina geüpdate hebben, de rest is goed."

Overgenomen wat daar werkt: halve-cirkelmeters met één groot getal,
staafjes per accupakket, één kleur met rood alleen voor alarmen.
"""
import sys
from pathlib import Path

import custom_components.energy_management_system as pkg

sys.path.insert(0, str(Path(pkg.__file__).parent))

from overview_svg import bouw_scada  # noqa: E402


def _plaat(**overrides):
    gegevens = {
        "status": "goed",
        "soc": 87.0,
        "omvormer_c": 31.0,
        "beschikbaar_kwh": 6.6,
        "accu_w": -430.0,
        "pv_w": 210.0,
        "net_w": 180.0,
        "huis_w": 820.0,
        "modules": [
            {"module": 1, "temperatuur_c": 31.0, "cel_delta_v": 0.26},
            {"module": 2, "temperatuur_c": 28.0, "cel_delta_v": 0.0},
            {"module": 3, "temperatuur_c": 27.0, "cel_delta_v": 0.0},
        ],
        "koeling": {"ventilator_aan": True, "buiten_c": 17.9},
        "tekort_kwartieren": 0,
        "verkoopkwartieren": 14,
    }
    gegevens.update(overrides)
    return bouw_scada(gegevens)


def test_it_produces_valid_svg():
    import xml.etree.ElementTree as ET

    ET.fromstring(_plaat())





def test_no_meter_for_a_fixed_number():
    """Op het voorbeeld staat "Power capacity 413 kW" in een halve
    cirkel. Dat is versiering: een waarde die nooit beweegt hoort geen
    meter te krijgen."""
    plaat = _plaat()

    for vast in ("capaciteit", "nominaal", "8.6 kWh"):
        assert vast.lower() not in plaat.lower()


def test_charging_and_discharging_are_named():
    assert "LADEN" in _plaat(accu_w=800.0)
    assert "ONTLADEN" in _plaat(accu_w=-800.0)
    assert "RUST" in _plaat(accu_w=0.0)


def test_the_cooling_state_is_visible():
    assert "ventilator draait" in _plaat()
    assert "ventilator uit" in _plaat(koeling={"ventilator_aan": False})


def test_a_shortfall_is_marked_red():
    from overview_svg import KLEUR_ALARM, KLEUR_GOED

    assert KLEUR_GOED in _plaat(tekort_kwartieren=0)
    assert KLEUR_ALARM in _plaat(tekort_kwartieren=6)


def test_empty_data_does_not_crash():
    """Vlak na een herstart is er nog niets gemeten."""
    import xml.etree.ElementTree as ET

    ET.fromstring(bouw_scada({}))



def test_the_canvas_fits_its_content():
    """Alles moet binnen de viewBox vallen, anders wordt de onderbalk
    afgesneden."""
    import re

    plaat = _plaat()
    hoogte = float(re.search(r'viewBox="0 0 \d+ (\d+)"', plaat).group(1))
    ys = [float(y) for y in re.findall(r'y="(\d+(?:\.\d+)?)"', plaat)]

    assert max(ys) < hoogte


# --- v3.18.0: uitlijning en loze ruimte ------------------------------




def test_the_power_block_carries_context():
    """Gemeld: "hier bijvoorbeeld veel loze ruimte". Een kader van 128
    hoog voor één getal is verspilling."""
    plaat = _plaat(prijs_ct=28.9, accu_ct=43.2, reden="Zon opvangen")

    assert "stroomprijs nu" in plaat
    assert "kWh uit de accu" in plaat
    assert "Zon opvangen" in plaat


def test_missing_context_shows_a_dash():
    plaat = _plaat()

    assert "--" in plaat


def test_the_sections_have_three_columns():
    """Gevraagd: "misschien 3 secties naast elkaar welke wat meer info
    geven"."""
    from overview_svg import bouw_secties

    svg = bouw_secties(
        {
            "secties": [
                ("vandaag", [("opgewekt", "2.7 kWh", None)]),
                ("vooruit", [("laagste stand", "50 %", None)]),
                ("kosten", [("rendement", "84.5 %", None)]),
            ]
        }
    )

    for titel in ("VANDAAG", "VOORUIT", "KOSTEN"):
        assert titel in svg


def test_the_sections_are_valid_svg():
    import xml.etree.ElementTree as ET

    from overview_svg import bouw_secties

    ET.fromstring(bouw_secties({"secties": []}))


# --- v3.19.0: accumodules eruit --------------------------------------


def test_the_modules_are_gone():
    """Gevraagd: "de accumodules gedeelte mag er wel uit, die info vind
    ik overbodig op deze pagina."

    Terecht. De staafjes stonden er om een uitschieter te laten zien,
    maar de modules lopen gelijk - drie identieke blokjes zeggen niets.
    De accupagina heeft de cijfers per module, en de zelfcontrole meldt
    het zodra er wél iets uit de pas loopt.
    """
    plaat = _plaat()

    assert "ACCUMODULES" not in plaat
    assert "celspreiding" not in plaat


def test_the_day_figures_took_their_place():
    """Loze ruimte is geen verbetering: er staat nu iets dat op een
    overzichtspagina hoort."""
    plaat = _plaat(
        opgewekt_kwh=2.7,
        voorspeld_kwh=9.1,
        verbruik_kwh=2.9,
        import_kwh=5.9,
    )

    assert "opgewekt" in plaat
    assert "van het net" in plaat


def test_the_module_bars_helper_still_works():
    """De bouwsteen blijft, want de accupagina gebruikt hem. Alleen op
    deze plaat staat hij niet meer."""
    from overview_svg import _staafjes

    svg = _staafjes(10, 60, [30.0, 28.0], ["M1", "M2"])

    assert "M1" in svg and "M2" in svg


# --- v3.19.0: status per onderwerp, klikbaar -------------------------



def test_the_reliability_level_is_coloured():
    """Dezelfde schaal als de proefstand en de meetkwaliteit gebruiken,
    dus geen nieuw begrip."""
    from overview_svg import KLEUR_ALARM, KLEUR_GOED, bouw_status

    goed = bouw_status(
        {"onderwerpen": {"water": {"niveau": "betrouwbaar", "zin": "ok"}}}
    )
    slecht = bouw_status(
        {"onderwerpen": {"water": {"niveau": "onbetrouwbaar", "zin": "ok"}}}
    )

    assert KLEUR_GOED in goed
    assert KLEUR_ALARM in slecht


def test_an_unknown_topic_is_skipped():
    """Zonder pad valt er niets te openen, en een blok dat niet klikt
    terwijl de andere dat wel doen is verwarrend."""
    from overview_svg import bouw_status

    svg = bouw_status(
        {"onderwerpen": {"iets_nieuws": {"niveau": "goed", "zin": "test"}}}
    )

    assert svg == ""


def test_long_sentences_are_cut_on_a_word():
    """Midden in een woord afkappen leest slecht."""
    from overview_svg import _kort

    assert _kort("een tekst die te lang is om te tonen", 20).endswith("…")
    assert " …" not in _kort("een tekst die te lang is", 12)


def test_empty_topics_render_nothing():
    from overview_svg import bouw_status

    assert bouw_status({}) == ""


# --- v3.20.0: één plaat, en nette schaalgrenzen -----------------------





def test_everything_still_fits_the_canvas():
    import re

    plaat = _plaat(
        onderwerpen={
            "water": {"niveau": "betrouwbaar", "zin": "test"},
            "zon": {"niveau": "betrouwbaar", "zin": "test"},
        }
    )
    hoogte = int(re.search(r'viewBox="0 0 760 (\d+)"', plaat).group(1))
    ys = [float(y) for y in re.findall(r'y="(\d+(?:\.\d+)?)"', plaat)]

    assert max(ys) < hoogte


# --- v3.21.0: drie kolommen -------------------------------------------





def test_the_bottom_bar_spans_the_full_width():
    plaat = _plaat()

    assert 'width="728"' in plaat


# --- v3.22.0: balkjes in plaats van meters ---------------------------


def test_the_gauges_are_gone():
    """Gemeld: "springt er teveel uit, misschien compacter, en geen
    gauges?"

    Terecht. Drie halve cirkels met bogen, achtergrondbogen en
    schaalgrenzen zijn veel lijnen voor drie getallen.
    """
    plaat = _plaat(soc=87.0, omvormer_c=26.0, beschikbaar_kwh=7.0)

    assert " A 22.0 22.0 " not in plaat
    assert " A 30.0 30.0 " not in plaat


def test_the_number_is_what_stands_out():
    """Het getal blijft het belangrijkste, en dat is nu ook wat
    opvalt."""
    plaat = _plaat(soc=87.0)

    assert 'font-size="17" font-weight="600"' in plaat


def test_a_bar_shows_the_position_on_the_scale():
    """Een balkje van drie pixels zegt hetzelfde als een halve cirkel:
    waar sta je tussen minimum en maximum."""
    from overview_svg import _balkje

    leeg = _balkje(0, 20, 0.0, 0, 100, "test")
    vol = _balkje(0, 20, 100.0, 0, 100, "test")

    assert 'width="0.0" height="3"' in leeg
    assert 'width="68.0" height="3"' in vol


def test_a_missing_value_shows_a_dash():
    """Een balkje op nul lijkt een meting."""
    from overview_svg import _balkje

    assert "--" in _balkje(0, 20, None, 0, 100, "test")


def test_a_high_value_is_marked_red():
    from overview_svg import KLEUR_ALARM, _balkje

    assert KLEUR_ALARM in _balkje(0, 20, 48.0, 10, 55, "t", alarm_boven=45)
    assert KLEUR_ALARM not in _balkje(0, 20, 26.0, 10, 55, "t", alarm_boven=45)


def test_the_plate_got_shorter():
    """Compacter was de vraag, niet alleen anders."""
    import re

    plaat = _plaat(
        onderwerpen={
            sleutel: {"niveau": "betrouwbaar", "zin": "test"}
            for sleutel in (
                "water", "zon", "apparaten", "klimaat", "financieel",
                "zelflerend", "accumodules",
            )
        }
    )
    hoogte = int(re.search(r'viewBox="0 0 760 (\d+)"', plaat).group(1))

    assert hoogte < 400, f"{hoogte} hoog - dat was 464 met de meters"


def test_nothing_falls_outside_the_canvas():
    """Elke keer dat de indeling verandert kan er iets uitlopen; dit
    rekent het na in plaats van het met het oog te beoordelen."""
    import re

    plaat = _plaat(
        onderwerpen={
            sleutel: {"niveau": "betrouwbaar", "zin": "test"}
            for sleutel in ("water", "zon", "apparaten")
        }
    )
    hoogte = int(re.search(r'viewBox="0 0 760 (\d+)"', plaat).group(1))
    ys = [float(y) for y in re.findall(r'y="(\d+(?:\.\d+)?)"', plaat)]
    xs = [float(x) for x in re.findall(r'x="(\d+(?:\.\d+)?)"', plaat)]

    assert max(ys) < hoogte
    assert max(xs) <= 760


# --- v3.22.1: bewegende stroompijlen ---------------------------------




def test_the_arrow_thickness_follows_the_power():
    """Bij veel stroom een dikkere pijl - dan zie je in één blik waar de
    energie heen gaat."""
    from overview_svg import _pijl

    import re

    dun = _pijl(0, 0, 0, 30, 100, "#fff")
    dik = _pijl(0, 0, 0, 30, 3000, "#fff")

    d1 = float(re.search(r'stroke-width="([\d.]+)"', dun).group(1))
    d2 = float(re.search(r'stroke-width="([\d.]+)"', dik).group(1))

    assert d2 > d1


# --- v3.23.0: klikken buiten de SVG ----------------------------------


def test_the_svg_has_no_links():
    """Gemeld met een schermafbeelding waarop de hele plaat als PLATTE
    TEKST verscheen, met de linkgedeelten blauw onderstreept.

    De opschoner van de markdown-kaart accepteert `<a>` binnen SVG niet
    en zet dan het hele blok om naar tekst. Gevraagd: "niet de links
    eruit, ik wil hem juist klikbaar hebben" - dus moet het klikken
    buiten de SVG gebeuren.
    """
    plaat = _plaat(
        onderwerpen={"water": {"niveau": "betrouwbaar", "zin": "test"}}
    )

    assert "<a href" not in plaat
    assert "xlink" not in plaat




def test_the_plate_has_two_columns_now():
    """De statuskolom is eruit, dus de twee die overblijven mogen
    breder."""
    plaat = _plaat()

    for titel in ("ACCU", "INSTALLATIE", "VERMOGEN", "VANDAAG"):
        assert titel in plaat
    assert "STATUS" not in plaat



def test_the_visual_page_is_a_panel_again():
    """v3.25.2: teruggezet naar de paneelweergave met alleen de plaat.

    Gemeld: "de Visueel pagina werkt niet correct, graag terugbrengen
    naar de stand van gisteren." De dashboardcontrole vond niets - 103
    verwijzingen nagelopen, geen ontbrekende entiteiten of attributen -
    dus wat er precies misging is niet vast te stellen.

    Dan is teruggaan naar een aantoonbaar werkende stand verstandiger
    dan blijven sleutelen. De sectie-indeling met de klikbare tegels uit
    v3.23.0 vervalt daarmee; die kan terugkomen zodra duidelijk is wat er
    aan de hand was.
    """
    import yaml
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    pagina = next(v for v in data["views"] if v.get("path") == "visueel")

    assert pagina.get("panel") is True

    # v3.25.3: één SVG per markdown-kaart. Twee SVG-blokken in dezelfde
    # kaart werden als PLATTE TEKST getoond - de markdown-verwerker
    # herkent het tweede blok dan niet meer als HTML.
    stapel = pagina["cards"][0]
    assert stapel["type"] == "vertical-stack"
    assert all(k["type"] == "markdown" for k in stapel["cards"])


def test_the_plate_and_the_sections_are_both_shown():
    import yaml
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    pagina = next(v for v in data["views"] if v.get("path") == "visueel")
    inhoud = [k["content"] for k in pagina["cards"][0]["cards"]]

    assert any("overzichtsplaat" in c for c in inhoud)
    assert any("overzichtsecties" in c for c in inhoud)


def test_no_card_holds_two_svgs():
    """De oorzaak van de platte tekst: twee `<svg>`-blokken in dezelfde
    markdown-kaart. Het eerste wordt als HTML herkend, het tweede niet
    meer - en dan verschijnt alles als tekst.

    Eén per kaart, en een vertical-stack eromheen zodat ze onder elkaar
    blijven staan.
    """
    import yaml
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )

    def _kaarten(o):
        if isinstance(o, dict):
            if o.get("type") == "markdown" and o.get("content"):
                yield o["content"]
            for v in o.values():
                yield from _kaarten(v)
        elif isinstance(o, list):
            for x in o:
                yield from _kaarten(x)

    for inhoud in _kaarten(data):
        aantal = sum(
            1
            for naam in ("overzichtsplaat", "overzichtsecties", "overzichtstatus")
            if naam in inhoud
        )
        assert aantal <= 1, f"kaart met {aantal} SVG-bronnen: {inhoud[:80]}"


# --- v3.25.4: geen SMIL-animatie meer --------------------------------


def test_the_plate_uses_only_plain_svg():
    """Gemeld: "Visueel is nog steeds een lap tekst."

    De tijdlijn wijst één kant op: de beweging kwam er in v3.22.1, en
    precies daarna begon dit. Daarvoor renderde de plaat.

    Home Assistant filtert SMIL-animatie uit de markdown-kaart; wat
    overblijft is geen geldige SVG meer en valt terug op tekst.
    """
    import re

    plaat = _plaat(pv_w=210.0, net_w=180.0, huis_w=820.0, accu_w=-430.0)
    elementen = set(re.findall(r"<([a-z]+)", plaat))

    verboden = {"animate", "animatetransform", "animatemotion", "set", "script"}
    assert not (elementen & verboden), elementen & verboden


def test_the_direction_is_still_visible():
    """Zonder beweging moet de richting uit een pijlPUNT blijken."""
    plaat = _plaat(pv_w=800.0)

    assert "<polygon" in plaat


def test_no_flow_no_arrowhead():
    """Een pijl die altijd staat zegt niets."""
    plaat = _plaat(pv_w=0.0, net_w=0.0, huis_w=0.0, accu_w=0.0)

    assert "<polygon" not in plaat


def test_the_arrowhead_turns_with_the_flow():
    """Bij teruglevering wijst de punt omhoog in plaats van omlaag."""
    import re

    def _punt_y(plaat):
        # De eerste coördinaat is de TIP van de driehoek; die wijst de
        # kant op waar de stroom heen gaat.
        m = re.search(r'<polygon points="[\d.]+,([\d.]+) ', plaat)
        return float(m.group(1)) if m else None

    # Alleen de NETpijl: de plaat bevat er meer, en dan pakt een zoekactie
    # op het eerste voorkomen de verkeerde.
    omlaag = _punt_y(_plaat(net_w=800.0, pv_w=0.0, huis_w=0.0, accu_w=0.0))
    omhoog = _punt_y(_plaat(net_w=-800.0, pv_w=0.0, huis_w=0.0, accu_w=0.0))

    assert omlaag is not None and omhoog is not None
    assert omlaag > omhoog


def test_the_thickness_still_follows_the_power():
    import re

    from overview_svg import _pijl

    dun = _pijl(0, 0, 0, 30, 100, "#fff")
    dik = _pijl(0, 0, 0, 30, 3000, "#fff")

    d1 = float(re.search(r'stroke-width="([\d.]+)"', dun).group(1))
    d2 = float(re.search(r'stroke-width="([\d.]+)"', dik).group(1))

    assert d2 > d1


def test_no_svg_anywhere_uses_unsafe_elements():
    """v3.25.4: derde poging op dezelfde pagina.

    Eerst dacht ik dat links het probleem waren, toen dat twee SVG's in
    één kaart het deden. Beide waren gissingen die ik niet kon toetsen.
    De werkelijke oorzaak bleek `<animate>`.

    Deze toets loopt ELKE plaat na die de integratie kan maken, met
    verschillende gegevens, zodat een element dat alleen in een bepaalde
    toestand verschijnt ook wordt gevangen.
    """
    import re

    from overview_svg import bouw_scada, bouw_secties, bouw_status

    verboden = {
        "animate",
        "animatetransform",
        "animatemotion",
        "set",
        "script",
        "foreignobject",
        "iframe",
        "a",
    }

    gevallen = [
        bouw_scada({}),
        bouw_scada(
            {
                "soc": 75.0,
                "pv_w": 2000.0,
                "net_w": -1400.0,
                "huis_w": 249.0,
                "accu_w": 1600.0,
                "koeling": {"ventilator_aan": True, "buiten_c": 17.8},
                "tekort_kwartieren": 3,
            }
        ),
        bouw_scada({"net_w": 800.0, "accu_w": -900.0}),
        bouw_secties({"secties": [("test", [("a", "b", None)])]}),
        bouw_status(
            {"onderwerpen": {"water": {"niveau": "betrouwbaar", "zin": "x"}}}
        ),
    ]

    for svg in gevallen:
        if not svg:
            continue
        elementen = {m.lower() for m in re.findall(r"<([a-zA-Z]+)", svg)}
        fout = elementen & verboden
        assert not fout, f"onveilig element in een plaat: {fout}"
