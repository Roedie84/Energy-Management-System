"""Structuurscan 11: geen twee herstelpaden voor dezelfde gegevens
(v3.42.1).

Uit een echte fout voortgekomen, en niet voor het eerst. De opruiming
van de klimaatcellen in v3.41.0 werkte wél, maar had geen effect: de
klimaatsensor zette dezelfde cellen daarna terug uit zijn eigen
entiteit-attributen.

Dat is dezelfde vorm als v0.63.115, toen de NILM-apparaten bij elke
herstart op twintig bleven steken omdat de entiteit-attributen (die op
twintig zijn afgekapt) de volledige Store overschreven.

Een veld dat zowel in de Store staat als uit een entiteit wordt
teruggezet, heeft twee bronnen van waarheid. Dat mag - soms is het de
enige migratieweg - maar dan moet het bewust zijn en hier staan.
"""
import ast
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import (
    PERSISTED_DATE_FIELDS,
    PERSISTED_DATETIME_FIELDS,
    PERSISTED_INT_FIELDS,
    PERSISTED_PLAIN_FIELDS,
)

MAP = Path(pkg.__file__).parent
BEWAARD = set(
    PERSISTED_PLAIN_FIELDS
    + PERSISTED_INT_FIELDS
    + PERSISTED_DATE_FIELDS
    + PERSISTED_DATETIME_FIELDS
)

# Velden waarvan bewust twee paden bestaan, met de reden erbij.
BEWUST = {
    # De Store is leidend; de entiteit is er alleen voor gebruikers die
    # van vóór de Store komen. Zie v0.63.115.
    "nilm_confirmed_devices": "migratiepad van vóór de Store",
    "nilm_rejected_entities": "migratiepad van vóór de Store",
    # v3.42.1: hersteld pad, maar nu met een filter op het sleutelformaat
    # zodat een opruiming niet ongedaan wordt gemaakt.
    "climate_rate_history": "entiteit herstelt alleen het nieuwe formaat",
    "climate_forecast_bias_history": "staat los van de sleutelwijziging",
    # v3.99.1: de dagrecords gaan naar de Store, want de sensoren bewaren
    # alleen shortfall/excess en de velden uit v3.99.0 (vermogensgrens,
    # max_ontlaad_w) gingen bij elke herstart verloren. De sensorroute
    # blijft één keer als vangnet: bij de eerste herstart na deze versie
    # is de Store nog leeg en zou de historie van zeven dagen anders weg
    # zijn. De samenvoeging overschrijft niets uit de Store.
    # Weghalen zodra de Store de records een keer heeft weggeschreven.
    "reserve_daily_records": "vangnet voor de eerste herstart na v3.99.1",
}


def _hersteld_uit_entiteit() -> set[str]:
    """Velden die een entiteit terugzet in `async_added_to_hass`."""
    gevonden = set()
    for pad in (MAP / "sensor.py", MAP / "switch.py", MAP / "button.py"):
        boom = ast.parse(pad.read_text())
        for knoop in ast.walk(boom):
            if not (
                isinstance(knoop, ast.AsyncFunctionDef)
                and knoop.name == "async_added_to_hass"
            ):
                continue
            for binnen in ast.walk(knoop):
                if (
                    isinstance(binnen, ast.Attribute)
                    and isinstance(binnen.ctx, ast.Store)
                    and isinstance(binnen.value, ast.Attribute)
                    and binnen.value.attr == "_coordinator"
                ):
                    gevonden.add(binnen.attr)
    return gevonden


def test_no_field_has_two_unacknowledged_restore_paths():
    """Een veld met twee bronnen van waarheid loopt uiteen zodra er aan

    één van de twee wordt gerepareerd - precies wat er met de
    klimaatcellen gebeurde.
    """
    dubbel = (_hersteld_uit_entiteit() & BEWAARD) - set(BEWUST)

    assert not dubbel, (
        "deze velden worden zowel uit de Store als uit een entiteit "
        f"teruggezet: {sorted(dubbel)}. Zet ze in BEWUST met de reden, of "
        "haal één van de twee paden weg."
    )


def test_the_acknowledged_list_stays_honest():
    """Staat er iets in de lijst dat allang niet meer uit een entiteit

    komt, dan beschrijft de lijst iets dat niet meer waar is.
    """
    uit_entiteit = _hersteld_uit_entiteit()

    verouderd = sorted(v for v in BEWUST if v not in uit_entiteit)

    assert not verouderd, (
        f"deze staan als bewust dubbel genoteerd maar worden nergens uit "
        f"een entiteit teruggezet: {verouderd}"
    )


def test_the_climate_cells_filter_on_the_key_format():
    """De reparatie zelf: het herstelpad mag alleen het nieuwe formaat

    terugzetten, anders is de opruiming zinloos.
    """
    bron = (MAP / "sensor.py").read_text()
    begin = bron.index('raw_cells = last_state.attributes')
    blok = bron[begin:][:1600]

    assert 'startswith("d")' in blok


# --- structuurscan 14: sleutels in toetsen volgen het echte formaat ---


def test_no_test_uses_a_stale_climate_key_format():
    """De vorm die zes dagen onopgemerkt bleef (v3.47.0).

    Elf toetsen op de klimaatterugval gebruikten nog sleutels op
    buitentemperatuur, van de vorm "18-punt-0 pipe beide_dicht pipe uit",
    waar het sinds v3.41.0 met een `d` hoort te beginnen. Ze slaagden, omdat ze consequent hun eigen
    oude vorm gebruikten aan beide kanten: zelf de cel aanmaken, zelf
    bevragen, alles klopt.

    Een gesloten wereldje dat prima klopt en niets meer met de
    werkelijkheid te maken heeft. Daardoor bewaakten ze zes dagen lang
    een terugval die in de praktijk niet meer liep.

    De uitzondering is de toets die juist bewijst dat oude sleutels
    worden opgeruimd; die MOET de oude vorm gebruiken.
    """
    import re
    from pathlib import Path

    map_tests = Path(__file__).parent
    toegestaan = {
        # Bewijst dat de opruiming van v3.42.1 werkt.
        "test_klimaatcellen_twee_herstelpaden.py",
        "test_climate_tab.py",
    }

    fout = []
    for pad in sorted(map_tests.glob("*.py")):
        if pad.name in toegestaan or pad.name == Path(__file__).name:
            continue
        for nummer, regel in enumerate(pad.read_text().split("\n"), 1):
            for sleutel in re.findall(r'"([-\d.]+)\|[a-z_]+\|[a-z]+"', regel):
                fout.append(f"{pad.name}:{nummer} - '{sleutel}|...'")

    assert not fout, (
        "klimaatsleutels zonder het `d`-merkteken van v3.41.0: "
        + ", ".join(fout)
    )


# --- structuurscan 16: gedeelde lijsten houden één soort -------------


def test_shared_lists_hold_one_kind_of_element():
    """De fout van 24 augustus én van 28 augustus (v3.70.0).

    Gemeld met een schermafdruk: "1 onderdeel(en) vallen om -
    diagnostiek:get_live_narrative", en de export kwam als tekstbestand
    terug in plaats van JSON.

    De oorzaak: `aandachtspunten` is een lijst TEKSTEN. Elke plek voegt
    er een zin aan toe, en `_narrate_attention` doet daar
    `" ".join(...)` overheen voor het Live-verhaal. In v3.67.0 kwamen
    daar dicts bij met `titel`, `tekst` en `actie` - en `join` op een
    dict werpt een TypeError.

    Vier dagen eerder ging het om de kwartierplanning, met dezelfde
    vorm: een bestaande lijst vullen met een ander soort element dan de
    lezers verwachten.

    Deze scan kijkt per lijst of alle `append`-aanroepen hetzelfde soort
    element toevoegen.
    """
    import ast
    import collections
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    boom = ast.parse((Path(pkg.__file__).parent / "coordinator.py").read_text())

    # Per FUNCTIE, niet per naam: `regels` heet in tien functies zo en
    # betekent overal iets anders. Alleen binnen dezelfde functie - of
    # op een `self.`-veld, dat wél gedeeld is - zegt een mengeling iets.
    soorten = collections.defaultdict(set)
    regels = collections.defaultdict(list)
    omhullend = {}
    for fn in ast.walk(boom):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for k in ast.walk(fn):
                omhullend.setdefault(id(k), fn.name)

    for n in ast.walk(boom):
        if not (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "append"
            and len(n.args) == 1
        ):
            continue
        doel = n.func.value
        naam = (
            doel.attr
            if isinstance(doel, ast.Attribute)
            else (doel.id if isinstance(doel, ast.Name) else None)
        )
        if not naam:
            continue
        if isinstance(doel, ast.Name):
            # Een lokale lijst: alleen binnen dezelfde functie
            # vergelijken.
            naam = f"{omhullend.get(id(n), '?')}::{naam}"
        arg = n.args[0]
        if isinstance(arg, ast.Dict):
            soort = "dict"
        elif isinstance(arg, (ast.JoinedStr, ast.Constant)) and not isinstance(
            getattr(arg, "value", None), (int, float, bool)
        ):
            soort = "tekst"
        else:
            continue  # variabelen zeggen niets zonder typeanalyse
        soorten[naam].add(soort)
        regels[naam].append(f"regel {n.lineno}: {soort}")

    gemengd = {
        naam: regels[naam] for naam, s in soorten.items() if len(s) > 1
    }

    assert not gemengd, (
        "deze lijsten krijgen zowel teksten als dicts, en de lezers "
        f"verwachten er maar een van: {gemengd}"
    )


# --- structuurscan 17: vluchtige markering bij bewaarde reeks --------


def test_no_volatile_marker_guards_a_persisted_series():
    """Twee keer dezelfde fout in twee dagen (v3.73.0).

    Gemeten in de export van 29 augustus:

        mpc_vergelijking              2 dubbele dagen
        digital_twin_accuracy_history 2 dubbele momenten

    Allebei dezelfde vorm: een VLUCHTIGE markering die bewaakt of er al
    is gemeten, terwijl de reeks zelf WEL wordt bewaard. Na een herstart
    is de markering weg, de reeks niet - en dan wordt dezelfde dag
    opnieuw gemeten.

    Bij de MPC leverde dat +1,45 en -0,75 op dezelfde dag; bij de
    tweeling twee voorspellingen die op hetzelfde moment aankwamen. In
    beide gevallen vertekent dat de mediaan waar de kandidaat op rust.

    Deze scan zoekt naar markeringen die als vluchtig zijn verklaard en
    toch in een `if`-vergelijking staan die iets afdwingt.
    """
    import ast
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    toetsen = Path(__file__).parent / "test_state_persistence.py"
    tekst = toetsen.read_text()
    vluchtig = set(
        re.findall(
            r'"(\w+)":\s*"', tekst[tekst.index("VLUCHTIG_MET_REDEN") :]
        )
    )

    boom = ast.parse(bron)
    verdacht = []
    for n in ast.walk(boom):
        if not isinstance(n, ast.Compare) or not isinstance(n.left, ast.Attribute):
            continue
        if not (
            isinstance(n.left.value, ast.Name) and n.left.value.id == "self"
        ):
            continue
        naam = n.left.attr
        if naam not in vluchtig:
            continue
        # Alleen markeringen die een MOMENT vasthouden. Een lusteller
        # (`_idx`) of een tijdvenster (`_window_duration_hours`) staat
        # ook in een vergelijking, maar bewaakt niets dat een herstart
        # moet overleven - die twee gaven vals alarm bij het invoeren.
        if not any(
            w in naam for w in ("gemeten", "queued", "laatst", "_op", "datum", "dag")
        ):
            continue
        verdacht.append(f"regel {n.lineno}: self.{naam}")

    # De MPC- en tweelingmarkering mogen blijven staan: ze zijn nu een
    # TWEEDE slot naast de geschiedenis, niet het enige.
    toegestaan = {"_mpc_gemeten_op", "_digital_twin_last_queued"}
    echt = [
        v for v in verdacht
        if not any(t in v for t in toegestaan)
    ]

    assert not echt, (
        "vluchtige markeringen die als enige bewaken of iets al is "
        f"gebeurd: {echt}"
    )
