"""Het installatieschema op de visuele pagina (v5.16).

Gemeld: *"ik vind hem er niet professioneel uitzien"*, *"op de landingpage
staat info welke niet op het visuele gedeelte zichtbaar is"*, *"ik wil
graag een professioneel overzicht waar de stroom heen gaat"* en *"het moet
zo zijn dat wanneer bezoek, een EMS-specialist of een grafisch ontwerper
het dashboard ziet, ze denken: dit is echt wel de top"*.

Deze keer is de plaat niet blind gebouwd: met `cairosvg` omgezet naar een
afbeelding en bekeken. Dat legde fouten bloot die in de code niet opvallen
- tekst buiten zijn kader, een kop over zijn eerste regel, labels op
pijlen.
"""
from datetime import datetime, timezone

import pytest


def _gegevens(c):
    return c._schema_gegevens()


def test_het_verloop_van_vandaag_komt_uit_het_dagverloop(make_coordinator, hass):
    """Geen nieuwe meting: het dagverloop ligt er al."""
    c = make_coordinator({})
    dag = __import__("homeassistant.util.dt", fromlist=["dt"]).now().date().isoformat()
    c.dagverloop = {
        dag: [
            {"tijd": "08:00", "pv_w": 100, "huis_w": 300},
            {"tijd": "08:15", "pv_w": 300, "huis_w": 500},
            {"tijd": "09:00", "pv_w": 900, "huis_w": 400},
        ]
    }

    verloop = c._verloop_van_vandaag()

    assert verloop["pv"][8] == 200      # gemiddelde van 100 en 300
    assert verloop["pv"][9] == 900
    assert verloop["huis"][8] == 400
    assert verloop["pv"][0] is None     # voor zonsopkomst: geen meting


def test_zonder_dagverloop_geen_grafiekje(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}

    assert c._verloop_van_vandaag() == {}


def test_de_plaat_toont_de_landingspaginagegevens(make_coordinator, hass):
    """De aanleiding: die stonden er niet op."""
    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada(
        {
            "status": "goed",
            "balk": [
                ("BESLUIT", "zon opvangen", "#f4f7fa", None),
                ("GOEDKOOP BLOK", "23:00", "#5fd38d", None),
                ("RESERVE", "2,01 kWh", "#f4f7fa", None),
                ("MELDINGEN 24U", "12", "#f4f7fa", None),
                ("AANDACHTSPUNTEN", "0", "#5fd38d", None),
            ],
        }
    )

    for veld in ("BESLUIT", "GOEDKOOP BLOK", "RESERVE", "MELDINGEN 24U",
                 "AANDACHTSPUNTEN"):
        assert veld in plaat


def test_elke_knoop_heeft_een_eigen_regel_per_gegeven(make_coordinator, hass):
    """De botsingen die bij het RENDEREN zichtbaar werden: het dagtotaal
    liep over de contextregel heen. Elk gegeven staat nu op een eigen
    hoogte."""
    import re

    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada(
        {
            "status": "goed", "net_w": 620.0,
            "net_onder": "stroomprijs nu 12,4 ct/kWh",
            "net_vandaag": "+0,7 / -4,7 kWh",
        }
    )
    # de twee regels van het NET-kader staan onder elkaar, niet naast elkaar
    hoogtes = {
        int(m.group(1))
        for m in re.finditer(r'<text x="140" y="(\d+)"', plaat)
    }

    assert len(hoogtes) >= 3, hoogtes


def test_de_plaat_past_op_het_doek(make_coordinator, hass):
    """Narekenen in plaats van met het oog beoordelen."""
    import re

    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada({"status": "goed", "pv_w": 2480.0, "accu_w": -1350.0})
    breedte, hoogte = (
        int(x) for x in re.search(r'viewBox="0 0 (\d+) (\d+)"', plaat).groups()
    )
    xs = [float(x) for x in re.findall(r'x="(\d+(?:\.\d+)?)"', plaat)]
    ys = [float(y) for y in re.findall(r'y="(\d+(?:\.\d+)?)"', plaat)]

    assert max(xs) <= breedte
    assert max(ys) < hoogte


def test_de_accuregel_past_ook_met_draaiende_ventilator(make_coordinator, hass):
    """Gemeld bij het bekijken: de regel kapte af op "... reserve 2,01 kWh
    ·…". De ventilator staat nu rechts op de onderste regel."""
    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada(
        {
            "status": "goed", "accu_w": -1350.0, "accustand": "LADEN",
            "soc": 68.0, "reserve_kwh": 2.01, "vrij_kwh": 4.9,
            "accu_vandaag": "4,9 kWh vrij",
            "koeling": {"ventilator_aan": True},
        }
    )

    # v5.17: de accukaart is opnieuw ingedeeld - laadstand voorop,
    # daaronder de stand, de reserve en de vrije ruimte.
    assert "LADEN" in plaat
    assert "reserve 2,01 kWh" in plaat
    assert "ventilator draait" in plaat
    assert "…" not in plaat


def test_de_balk_onderaan_kapt_een_besluit_niet_af(make_coordinator, hass):
    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada(
        {"status": "goed", "balk": [("BESLUIT", "net dekt het huis", "#fff", None)]}
    )

    assert "net dekt het huis" in plaat


def test_het_grafiekje_beslaat_altijd_de_hele_dag(make_coordinator, hass):
    """Anders wordt een half uur zon over de volle breedte uitgerekt en
    lijkt een vlakke ochtend een vlakke dag."""
    import re

    from custom_components.energy_management_system.overview_svg import bouw_scada

    ochtend = bouw_scada(
        {"status": "goed", "verloop": {"pv": [0, 0.2, 0.6, 1.2], "huis": []}}
    )
    xs = [
        float(m)
        for m in re.findall(r"[ML](\d+),", ochtend)
    ]

    # vier uur van de dag: de curve loopt tot ongeveer een zesde van de breedte
    # v5.18.3: het grafiekje staat rechtsboven op een doek van 1600 breed.
    assert max(xs) < 1240 + 324 / 3, max(xs)


def test_de_plaat_staat_alleen_op_de_pagina_visueel():
    """v5.18.2 - gemeld: "op de landingpage moet hij weg". De cockpit heeft
    een eigen pagina; op de landingspagina stond hij dubbel."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    sjabloon = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    overzicht = sjabloon[sjabloon.index("- title: Overzicht") : sjabloon.index("- title: Visueel")]
    visueel = sjabloon[sjabloon.index("- title: Visueel") :]

    assert "overzichtsplaat" not in overzicht
    # v5.19: de cockpitsensor, niet het attribuut van de GACS-sensor.
    assert "_cockpit'', ''plaat''" in visueel


# --- v5.17: de cockpit ---------------------------------------------------


def test_de_vier_statussen(make_coordinator, hass):
    """Gevraagd: GOED, LET OP, INGRIJPEN, STORING - en representatief voor
    het hele EMS, niet cosmetisch."""
    from custom_components.energy_management_system.overview_svg import STATUSKLEUREN

    assert set(STATUSKLEUREN) == {"GOED", "LET OP", "INGRIJPEN", "STORING"}


def _gezonde_basis(c):
    """Een draaiende installatie: geslaagde ronde, niets kapot.

    v5.18 - zonder geslaagde ronde is de stand terecht STORING (regel 2 van
    de matrix). Dat is de opzet van de toets die onvolledig was, niet de
    verwachting."""
    from homeassistant.util import dt as dt_util

    c.last_successful_update = dt_util.now()
    c.internal_failures = {}
    c.get_configuratiecontrole = lambda: {"entiteiten": []}
    c.get_energiebalans_controle = lambda: {"beschikbaar": True, "alles_klopt": True}
    c.get_diagnostic_summary = lambda: {"aandachtspunten": []}
    return c


def test_een_storing_weegt_zwaarder_dan_een_aandachtspunt(make_coordinator, hass):
    c = _gezonde_basis(make_coordinator({}))
    c.get_diagnostic_summary = lambda: {"aandachtspunten": [{"ernst": "let_op"}]}

    assert c._ems_status()[0] == "LET OP"

    c.get_diagnostic_summary = lambda: {"aandachtspunten": [{"ernst": "fout"}]}
    assert c._ems_status()[0] == "INGRIJPEN"

    c.internal_failures = {"iets": "stuk"}
    assert c._ems_status()[0] == "STORING"


def test_de_statusregel_noemt_alleen_gemeten_grootheden(make_coordinator, hass):
    """Nooit een verzonnen "confidence": wel de GEMETEN spreiding van de
    zonvoorspelling, de energiebalans en de sensoruitval."""
    c = _gezonde_basis(make_coordinator({}))
    c.get_configuratiecontrole = lambda: {
        "entiteiten": [{"oordeel": "in_orde", "instelling": "price_sensor_entity"}]
    }

    stand, regel = c._ems_status()

    assert stand == "GOED"
    assert "koppelingen 1/1" in regel
    assert "balans ✓" in regel
    assert "confidence" not in regel.lower()


def test_het_net_zegt_inkoop_of_teruglevering(make_coordinator, hass):
    """Gevraagd: "ik wil nooit hoeven onthouden of een positieve of
    negatieve sensorwaarde import of export betekent"."""
    from custom_components.energy_management_system.overview_svg import bouw_scada

    assert "INKOOP" in bouw_scada({"net_w": 620.0})
    assert "TERUGLEVERING" in bouw_scada({"net_w": -620.0})


def test_de_accubalk_toont_reserve_ook_als_de_accu_eronder_zit(make_coordinator, hass):
    """Dan is dat juist het nieuws."""
    from custom_components.energy_management_system.overview_svg import (
        KLEUR_ALARM,
        bouw_scada,
    )

    plaat = bouw_scada(
        {"soc": 10.0, "soc_deel": 0.10, "reserve_deel": 0.53, "tekort_kwartieren": 6}
    )

    assert KLEUR_ALARM in plaat


def test_het_besluit_draagt_zijn_eigen_waarom(make_coordinator, hass):
    """Explainability: de verklaring komt uit `get_why_now`, de
    werkelijke beslisparameters - nooit achteraf verzonnen."""
    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada(
        {
            "besluit": "zon opvangen",
            "besluit_uitleg": "De accu houdt ruimte vrij.",
            "waarom": ["hoge zonverwachting", "reserve voldoende"],
        }
    )

    assert "ZON OPVANGEN" in plaat
    assert "WAAROM" in plaat
    assert "hoge zonverwachting · reserve voldoende" in plaat


def test_het_waarom_komt_uit_de_beslislogica(make_coordinator, hass):
    from homeassistant.util import dt as dt_util

    c = _gezonde_basis(make_coordinator({}))
    c.get_why_now = lambda now=None: {
        "beschikbaar": True, "kort": "Zon opvangen",
        "redenen": ["hoge zonverwachting", "reserve voldoende", "vierde regel", "vijfde"],
    }

    # v5.18: de cockpit leest het SNAPSHOT, niet de losse functies.
    c._besluit_snapshot_vastleggen(dt_util.now())
    gegevens = c._schema_gegevens()

    assert gegevens["besluit"] == "Zon opvangen"
    assert gegevens["waarom"] == [
        "hoge zonverwachting", "reserve voldoende", "vierde regel",
    ]


def test_de_plaat_is_breed_genoeg_voor_een_beeldscherm():
    """Gemeld: "schaling werkt niet" - bij 1000 bij 790 werd de plaat op
    een breed scherm hoger dan het scherm zelf. Breed doek, lage
    verhouding."""
    import re

    from custom_components.energy_management_system.overview_svg import bouw_scada

    breedte, hoogte = (
        int(x)
        for x in re.search(r'viewBox="0 0 (\d+) (\d+)"', bouw_scada({})).groups()
    )

    assert breedte / hoogte >= 2.2, f"{breedte}x{hoogte}"


def test_de_plaat_past_zich_aan_een_smal_scherm_aan():
    """Automatische schaling: een SVG in een `<img>` kent zijn eigen
    breedte, dus hij ziet zelf of hij op een telefoon staat. Dan vallen de
    bijzaken weg en wordt het schema groter getekend."""
    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada({"status_kort": "GOED", "verloop": {"pv": [0, 1]}})

    assert "@media (max-width: 760px)" in plaat
    assert 'class="bijzaak"' in plaat
    assert 'id="stroomschema"' in plaat


def test_de_mediaregel_verbergt_geen_primaire_waarde():
    """Wat wegvalt op een telefoon mag geen antwoord op de vijf vragen
    zijn: het schema zelf blijft staan."""
    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada(
        {"pv_w": 653.0, "net_w": -60.0, "huis_w": 132.0, "accu_w": -461.0,
         "accustand": "LADEN", "soc": 10.0}
    )
    # Het schema loopt van zijn eigen opening tot de bijzaken eronder; op
    # de eerste </g> knippen zou midden in een icoon eindigen.
    begin = plaat.index('<g id="stroomschema">')
    eind = plaat.index('<g class="bijzaak">', begin)
    schema = plaat[begin:eind]

    for stuk in ("ZONNEPANELEN", "NET", "HUIS", "THUISACCU", "653", "132"):
        assert stuk in schema, stuk


def test_geen_twee_teksten_over_elkaar():
    """Narekenen in plaats van met het oog beoordelen (v5.18.3).

    Bij elke herindeling liep er iets over iets anders heen: het dagtotaal
    over de contextregel, de tekortregel over de koeltekst, de balk over de
    reserveregel. Deze toets groepeert de teksten per kolom en eist tussen
    twee regels in dezelfde kolom minstens 13 pixels.
    """
    import re
    from collections import defaultdict

    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada(
        {
            "status_kort": "GOED", "status_regel": "koppelingen 70/70 · balans ✓",
            "pv_w": 1500.0, "accu_w": -1100.0, "net_w": -53.0, "huis_w": 301.0,
            "accustand": "LADEN", "soc": 15.0, "reserve_kwh": 2.0,
            "tekort_kwh": 1.57, "vrij_kwh": 0.0,
            "accu_balk": {"soc_deel": 0.15, "reserve_deel": 0.33,
                          "ondergrens_deel": 0.10},
            "zon_onder": "14,9 kWh verwacht", "zon_vandaag": "0,9 kWh",
            "huis_onder": "grootste nu: Koelkast schuur", "huis_vandaag": "2,3 kWh",
            "net_onder": "29,4 ct/kWh · goedkoopste blok 11:30",
            "net_vandaag": "+0,4 / -0,6 kWh",
            "besluit": "Standaard slim laden",
            "besluit_uitleg": "De accu heeft niet genoeg beschikbare energie.",
            "waarom": ["de prijs is nu 29,4 ct"],
            "balk": [("RESERVE", "2,00 kWh", "#f4f7fa", None)],
        }
    )
    kolommen = defaultdict(list)
    for m in re.finditer(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]*)', plaat):
        x, y, tekst = float(m.group(1)), float(m.group(2)), m.group(3)
        if tekst.strip():
            kolommen[round(x / 80)].append((y, tekst.strip()[:24]))

    botsingen = []
    for regels in kolommen.values():
        regels.sort()
        for (y1, t1), (y2, t2) in zip(regels, regels[1:]):
            if 0 < y2 - y1 < 13:
                botsingen.append(f"{t1!r} en {t2!r} op {y1} en {y2}")

    assert not botsingen, "\n".join(botsingen)


def test_geen_tekst_buiten_zijn_kader():
    """Gemeld met een schermafdruk: "tekst valt er buiten" - de
    waarom-regel stond onder het besluitblok.

    Deze toets rekent per kader na dat elke tekst erbinnen valt, in plaats
    van dat het met het oog moet worden gezien."""
    import re

    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada(
        {
            "besluit": "Standaard slim laden",
            "besluit_uitleg": (
                "Er is nu geen speciale reden om in te grijpen: de huidige "
                "prijs haalt de drempel voor duur niet."
            ),
            "waarom": [
                "de prijs is nu 25.3 ct, de drempel voor 'duur' ligt op 41.7 ct",
                "de accu staat op 27% (1.5 kWh bruikbaar)",
            ],
            "balk": [("RESERVE", "1,99 kWh", "#f4f7fa", None)],
            "soc": 27.0, "accustand": "STANDBY", "reserve_kwh": 1.99,
            "tekort_kwh": 0.52,
            "accu_balk": {"soc_deel": 0.27, "reserve_deel": 0.33,
                          "ondergrens_deel": 0.10},
        }
    )
    kaders = [
        (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in re.finditer(
            r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="1[24]"',
            plaat,
        )
    ]
    buiten = []
    for m in re.finditer(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]*)', plaat):
        tx, ty, tekst = float(m.group(1)), float(m.group(2)), m.group(3).strip()
        if not tekst:
            continue
        for kx, ky, kb, kh in kaders:
            # hoort de tekst bij dit kader? dan moet hij er ook in vallen
            if kx <= tx <= kx + kb and ky <= ty <= ky + kh + 40:
                assert ty <= ky + kh - 4, f"{tekst!r} valt onder zijn kader"
                break

    assert not buiten


def test_geen_enkele_tekst_wordt_afgekapt_bij_echte_zinnen():
    """Gemeld, drie keer op rij: "tekst valt weg", "tekst niet volledig
    zichtbaar", "tekst valt nog weg".

    Deze toets gebruikt de WERKELIJKE uitleg en waarom-regels van de
    beslislogica - de langste die in de praktijk voorkomen - en eist dat
    er geen beletselteken in de plaat staat."""
    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada(
        {
            "besluit": "Standaard slim laden",
            # v5.19.7: de langste die in bedrijf gezien is - drie regels.
            "besluit_uitleg": (
                "Er is nu geen speciale reden om in te grijpen: de huidige "
                "prijs (€0.191/kWh) haalt de drempel voor 'duur' vandaag "
                "(€0.417/kWh) niet, en het goedkoopste blok is al gaande of "
                "voorbij. De Zendure regelt dit zelf (smart-modus). Ook de "
                "ruimere secundaire drempel (€0.339/kWh, top 45%) wordt niet "
                "gehaald, dus er is geen reden om te ontladen."
            ),
            "waarom": [
                "de prijs is nu 19.6 ct, de drempel voor 'duur' ligt op 41.7 ct",
                "de accu staat op 43% (2.9 kWh bruikbaar)",
                "geen bijzondere reden om iets anders te doen: de accu vangt "
                "zon op en voedt het huis",
            ],
        }
    )

    assert "…" not in plaat


def test_de_grafiek_belooft_geen_verwachting_die_er_niet_is():
    """Gevraagd: "welke kleur is werkelijk/verwacht?" - en dat legde een
    fout bloot: het dagverloop levert alleen GEMETEN waarden, dus er was
    helemaal geen verwachte lijn. Het label beloofde iets wat er niet
    stond."""
    from custom_components.energy_management_system.overview_svg import bouw_scada

    alleen_gemeten = bouw_scada({"verloop": {"pv": [0, 1, 2], "huis": [1, 1, 1]}})
    met_verwachting = bouw_scada(
        {"verloop": {"pv": [0, 1, 2], "huis": [1, 1, 1], "pv_verwacht": [None, 2, 3]}}
    )

    assert "VERWACHT" not in alleen_gemeten
    assert "VERWACHT" in met_verwachting


def test_de_lijnen_worden_bij_hun_kleur_benoemd():
    """Zonder legenda kon je niet zien welke lijn wat was."""
    from custom_components.energy_management_system.overview_svg import bouw_scada

    plaat = bouw_scada({"verloop": {"pv": [0, 1, 2], "huis": [1, 1, 1]}})
    # de legenda staat als losse stukken op vaste plekken
    assert 'fill="#f0b429" font-size="10"' in plaat and "— ZON" in plaat
    assert 'fill="#8b98a5" font-size="10"' in plaat and "— VERBRUIK" in plaat
