"""Een derde waarde die gemeten is (v3.94.0).

Gevraagd: "Kunnen we nog een derde waarde ergens vandaan halen om te
kijken welke echt goed zou zijn?" en "zelf middels diagnostiek aangeven
of het werkt of niet en of het kan gaan regelen".

De aanleiding: twee weerbronnen die 38 tot 72 procentpunt uiteenlopen
over dezelfde lucht, en een scheidsrechter die niet neutraal is. De
overeenstemming per bron wordt nu gemeten met

    ratio = live_pv_w / solcast_kw

en Solcast heeft zijn eigen bewolkingsinschatting al ingebakken. Op 30
augustus zat Solcast er 44% naast; die dag telt elke bron die "helder"
zei als fout, ook als hij gelijk had.

De ijklijn is wél neutraal: het hoge percentiel van de eigen
paneelopbrengst per bakje zonnestand benadert een wolkeloze hemel.
Helderheid = nu / ijklijn. Nul is dicht, één is wolkeloos.

Deze toetsen leggen drie dingen vast: dat de ijklijn zwijgt tot hij
genoeg heeft, dat de bronnen op RANGORDE worden gescoord en niet op
procentpunten, en dat de zelfbeoordeling eerlijk zegt of er al iets mee
te sturen valt.
"""
from datetime import datetime, timezone

import pytest

from custom_components.energy_management_system.const import (
    HELDERHEID_MIN_GEVULDE_BAKJES,
    HELDERHEID_MIN_METINGEN_PER_BAKJE,
    HELDERHEID_MIN_PAREN,
    RELIABILITY_INSUFFICIENT,
)

NU = datetime(2026, 8, 31, 13, 0, tzinfo=timezone.utc)


def _vul_ijklijn(c, bakjes=(20.0, 30.0, 40.0), piek_per_bakje=None):
    """Een ijklijn zoals hij na weken meten zou staan."""
    piek_per_bakje = piek_per_bakje or {20.0: 1500.0, 30.0: 3000.0, 40.0: 4500.0}
    c.helderheid_ijklijn = {
        str(b): [
            piek_per_bakje[b] * (0.3 + 0.7 * (i / HELDERHEID_MIN_METINGEN_PER_BAKJE))
            for i in range(HELDERHEID_MIN_METINGEN_PER_BAKJE)
        ]
        for b in bakjes
    }


# --- 1. de ijklijn zelf ----------------------------------------------


def test_zonder_metingen_geen_ijklijn(make_coordinator, hass):
    """Een verhouding tegen een verzonnen noemer is erger dan geen

    verhouding.
    """
    c = make_coordinator({})

    assert c.ijklijn_vermogen_w(30.0) is None
    assert c.gemeten_helderheid() is None


def test_een_half_gevuld_bakje_telt_nog_niet(make_coordinator, hass):
    c = make_coordinator({})
    c.helderheid_ijklijn = {"30.0": [3000.0] * 5}

    assert c.ijklijn_vermogen_w(30.0) is None


def test_de_ijklijn_geeft_het_hoge_percentiel(make_coordinator, hass):
    """Niet het maximum: randverstrooiing kan de opbrengst kort boven de

    heldere waarde tillen, en dan zou één meting de hele lijn optillen.
    """
    c = make_coordinator({})
    c.helderheid_ijklijn = {
        "30.0": [3000.0] * HELDERHEID_MIN_METINGEN_PER_BAKJE + [9999.0]
    }

    assert c.ijklijn_vermogen_w(30.0) == pytest.approx(3000.0, abs=1.0)


def test_de_helderheid_is_de_verhouding(make_coordinator, hass):
    c = make_coordinator({})
    c.helderheid_ijklijn = {
        "30.0": [4000.0] * HELDERHEID_MIN_METINGEN_PER_BAKJE
    }
    c.get_sun_elevation_degrees = lambda: 32.0
    c.is_daylight_now = lambda: True
    c._lees_pv_vermogen_w = lambda: 2000.0

    assert c.gemeten_helderheid() == pytest.approx(0.5, abs=0.02)


def test_laag_aan_de_hemel_wordt_niet_gemeten(make_coordinator, hass):
    """Onder tien graden is een paar tientallen watt al een factor

    twee - dat is ruis, geen bewolking.
    """
    c = make_coordinator({})
    _vul_ijklijn(c)
    c.get_sun_elevation_degrees = lambda: 4.0
    c.is_daylight_now = lambda: True
    c._lees_pv_vermogen_w = lambda: 100.0

    assert c.gemeten_helderheid() is None


# --- 2. de bronnen op rangorde ---------------------------------------


def _paren(c, bron, paren):
    c.weerbron_helderheid_paren = {bron: list(paren)}


def test_een_bron_die_perfect_ordent_scoort_hoog(make_coordinator, hass):
    """Meer bewolking hoort samen te gaan met minder zon. Meer is niet

    nodig: de schaal van de bron hoeft niet te kloppen, alleen de
    richting.
    """
    c = make_coordinator({})
    _paren(
        c,
        "weather.goed",
        [(i, 1.0 - i / 150) for i in range(HELDERHEID_MIN_PAREN + 20)],
    )

    score = c.weerbron_rangorde_score("weather.goed")

    assert score is not None
    assert score > 95


def test_een_omgekeerde_bron_scoort_laag(make_coordinator, hass):
    """Zou een bron onbewolkt in plaats van bewolkt melden, dan valt hij

    hier meteen door de mand - dat was de vraag van 31 augustus.
    """
    c = make_coordinator({})
    _paren(
        c,
        "weather.omgekeerd",
        [(i, i / 150) for i in range(HELDERHEID_MIN_PAREN + 20)],
    )

    assert c.weerbron_rangorde_score("weather.omgekeerd") < 5


def test_te_weinig_paren_geeft_geen_score(make_coordinator, hass):
    c = make_coordinator({})
    _paren(c, "weather.nieuw", [(10, 0.9), (80, 0.2)])

    assert c.weerbron_rangorde_score("weather.nieuw") is None


# --- 3. de zelfbeoordeling -------------------------------------------


def test_de_diagnostiek_zegt_dat_hij_nog_niets_weet(make_coordinator, hass):
    """"Of het werkt of niet" - en zolang dat niet vaststaat, hoort dat

    er te staan in plaats van een leeg veld.
    """
    c = make_coordinator({})

    ijking = c.get_helderheid_ijking()

    assert ijking["status"] == RELIABILITY_INSUFFICIENT
    assert ijking["mag_regelen"] is False
    assert ijking["wat_ontbreekt"]


def test_de_diagnostiek_telt_de_gevulde_bakjes(make_coordinator, hass):
    c = make_coordinator({})
    _vul_ijklijn(c)

    ijking = c.get_helderheid_ijking()

    assert ijking["gevulde_bakjes"] == HELDERHEID_MIN_GEVULDE_BAKJES


def test_zonder_winnaar_mag_er_niets_geregeld_worden(make_coordinator, hass):
    """Twee bronnen die even goed ordenen, leveren geen keuze op. Dan

    hoort de zelfbeoordeling dat te zeggen en niet alsnog te kiezen.
    """
    c = make_coordinator({})
    _vul_ijklijn(c)
    reeks = [(i, 1.0 - i / 150) for i in range(HELDERHEID_MIN_PAREN + 20)]
    c.weerbron_helderheid_paren = {"weather.a": reeks, "weather.b": list(reeks)}

    ijking = c.get_helderheid_ijking()

    assert ijking["beste_bron"] is None
    assert ijking["mag_regelen"] is False
    assert "voorsprong" in ijking["wat_ontbreekt"].lower()


def test_met_een_duidelijke_winnaar_mag_het_wel(make_coordinator, hass):
    c = make_coordinator({})
    _vul_ijklijn(c)
    goed = [(i, 1.0 - i / 150) for i in range(HELDERHEID_MIN_PAREN + 20)]
    # Ordent nog net beter dan toeval, maar met veel ruis.
    slecht = [
        (i, 1.0 - i / 150 + (0.35 if i % 3 else -0.35))
        for i in range(HELDERHEID_MIN_PAREN + 20)
    ]
    c.weerbron_helderheid_paren = {"weather.goed": goed, "weather.slecht": slecht}

    ijking = c.get_helderheid_ijking()

    assert ijking["beste_bron"] == "weather.goed"
    assert ijking["mag_regelen"] is True


def test_de_ijking_stuurt_uit_zichzelf_niets(make_coordinator, hass):
    """Vaste afspraak: proefstandkandidaten sturen pas na bewijs, en dan

    met de hand aangezet. `mag_regelen` is een OORDEEL, geen schakelaar.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_helderheid_ijking")
    blok = bron[kop : kop + 4000]

    assert "async_set" not in blok
    assert "_async_set_switch" not in blok


# --- 4. waar het te zien is ------------------------------------------


def test_de_regel_staat_bij_de_adviesmodules(make_coordinator, hass):
    """De kaart zet een kop bij elke groepswissel en toont de regels in

    invoegvolgorde. Stond deze tussen de metingen, dan verscheen er
    halverwege een tweede kop "Adviesmodules" met één regel eronder.
    """
    c = make_coordinator({})

    rijen = c.get_reliability_overview()
    namen = [r["naam"] for r in rijen]
    plek = namen.index("Heldere-hemel-ijklijn")

    assert rijen[plek]["groep"] == "Adviesmodules"

    # En elke groep staat aaneengesloten, anders zet de kaart dezelfde
    # kop twee keer neer met de helft van de regels eronder.
    groepen = [r["groep"] for r in rijen]
    koppen = [g for i, g in enumerate(groepen) if i == 0 or groepen[i - 1] != g]
    assert len(koppen) == len(set(groepen))


def test_de_kaart_leest_de_juiste_sleutel():
    """Zonder deze toets kan de kaart stil op een hernoemde sleutel

    blijven staan - dat is scan 19 in een andere vorm.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    kaart = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()

    assert "helderheid_ijking" in kaart
    assert "mag_regelen" in kaart
