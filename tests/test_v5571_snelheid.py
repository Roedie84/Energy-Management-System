"""De zelfbeoordeling niet meer traag (v5.57.1).

Gemeld uit het logboek van 9 oktober, 10:42:

    Updating state for sensor...gacs_zelfbeoordeling took 2.315 seconds

Gemeten in plaats van vermoed: de proefstand-slijtage was het niet (60
boekingen, microseconden). Het was de heldere-hemel-ijking. Die werd per
toestand van de sensor vijf keer opgebouwd, en elke keer telde de rangorde
alle paren tegen elkaar (n², 480 paren per bron) en sorteerde hij de
ijklijn opnieuw voor elk paar. Met volle reeksen: 1,2 s voor de
zelfbeoordeling plus 0,75 s voor de betrouwbaarheidssensor.

Nu: tellen in n log n, de ijklijn één keer per bakje, en het resultaat
bewaard tot de metingen veranderen. Dezelfde getallen - dat toetst dit
bestand naast de snelheid.
"""
import random
import time

import pytest

from tests.test_alles_uitgevraagd import _echte_toestand, _maximaal, _alle_entiteiten

BRONNEN = ("weather.knmi", "weather.buienradar", "weather.openmeteo", "weather.met")


def _vul(c, zaad=1):
    """Volle reeksen: 12 bakjes x 400 metingen, 4 bronnen x 480 paren over
    40 dagen - het maximum dat de opslag bewaart."""
    rnd = random.Random(zaad)
    c.helderheid_ijklijn = {
        str(float(b)): [round(rnd.uniform(0, 5000), 1) for _ in range(400)]
        for b in range(10, 70, 5)
    }
    c.helderheid_dagen = {
        k: [f"2026-09-{d:02d}" for d in range(1, 30)] for k in c.helderheid_ijklijn
    }
    c.weerbron_helderheid_paren = {}
    for bron in BRONNEN:
        paren = []
        for i in range(480):
            dag = f"2026-{8 + i // 360:02d}-{1 + (i // 12) % 30:02d}"
            paren.append([
                float(rnd.randint(0, 20) * 5),  # veel gelijke bewolking
                round(rnd.choice([0.0, 1200.0, rnd.uniform(0, 5000)]), 1),  # en gelijke opbrengst
                str(float(10 + 5 * rnd.randint(0, 11))),
                dag,
                f"{dag}T{7 + i % 12:02d}",
            ])
        c.weerbron_helderheid_paren[bron] = paren


def _oude_rangorde(paren):
    """De dubbele lus van vóór v5.57.1, letterlijk."""
    eens = 0
    totaal = 0
    for i in range(len(paren)):
        bewolking_i, helder_i = paren[i]
        for j in range(i + 1, len(paren)):
            bewolking_j, helder_j = paren[j]
            if bewolking_i == bewolking_j or helder_i == helder_j:
                continue
            totaal += 1
            if (bewolking_i > bewolking_j) == (helder_i < helder_j):
                eens += 1
    return eens, totaal


def _oude_paren(c, bron):
    """`_helderheidsparen` van vóór v5.57.1: per paar opnieuw sorteren."""
    from custom_components.energy_management_system.const import (
        HELDERHEID_IJKLIJN_PERCENTIEL,
        HELDERHEID_MIN_METINGEN_PER_BAKJE,
    )

    uit = []
    for paar in c.weerbron_helderheid_paren.get(bron) or []:
        if len(paar) < 5:
            continue
        bewolking, pv_w, bakje = paar[0], paar[1], paar[2]
        metingen = c.helderheid_ijklijn.get(str(bakje))
        if not metingen or len(metingen) < HELDERHEID_MIN_METINGEN_PER_BAKJE:
            continue
        gesorteerd = sorted(metingen)
        index = min(len(gesorteerd) - 1, int(len(gesorteerd) * HELDERHEID_IJKLIJN_PERCENTIEL))
        ijklijn = gesorteerd[index]
        if not ijklijn:
            continue
        uit.append((float(bewolking), max(0.0, float(pv_w)) / ijklijn))
    return uit


@pytest.mark.parametrize("zaad", range(25))
def test_snelle_telling_is_gelijk_aan_de_dubbele_lus(zaad):
    from custom_components.energy_management_system.coordinator import _tel_rangorde

    rnd = random.Random(zaad)
    n = rnd.randint(0, 300)
    paren = [
        (float(rnd.randint(0, 10)), rnd.choice([0.0, 0.5, 1.0, rnd.random()]))
        for _ in range(n)
    ]
    assert _tel_rangorde(paren) == _oude_rangorde(paren)


def test_telling_randgevallen():
    from custom_components.energy_management_system.coordinator import _tel_rangorde

    for paren in ([], [(1.0, 1.0)], [(1.0, 1.0)] * 5, [(0.0, 1.0), (-0.0, 2.0)],
                  [(1.0, 2.0), (2.0, 1.0)], [(1.0, 1.0), (2.0, 2.0)],
                  [(float("nan"), 1.0), (1.0, 2.0), (2.0, 0.5)]):
        assert _tel_rangorde(paren) == _oude_rangorde(paren)


def test_paren_en_scores_gelijk_aan_vroeger(make_coordinator):
    c = make_coordinator(_maximaal())
    _vul(c)
    for bron in BRONNEN:
        oud = _oude_paren(c, bron)
        assert c._helderheidsparen(bron) == oud
        eens, totaal = _oude_rangorde(oud)
        assert c.weerbron_rangorde_score(bron) == round(100 * eens / totaal, 1)


def test_cache_geeft_hetzelfde_als_vers_rekenen(make_coordinator):
    c = make_coordinator(_maximaal())
    _vul(c)
    vers = c._bereken_helderheid_ijking()
    eerste = c.get_helderheid_ijking()
    tweede = c.get_helderheid_ijking()
    assert eerste == vers == tweede
    assert list(eerste) == list(vers)  # ook de volgorde van de velden


@pytest.mark.parametrize("wijziging", ["meting", "paar", "dag", "nieuwe_bron", "zelfde_lengte"])
def test_cache_vervalt_als_de_metingen_veranderen(make_coordinator, wijziging):
    c = make_coordinator(_maximaal())
    _vul(c)
    voor = c.get_helderheid_ijking()
    if wijziging == "meting":
        c.helderheid_ijklijn["10.0"].append(99999.0)
    elif wijziging == "paar":
        c.weerbron_helderheid_paren["weather.knmi"][0][0] = 100.0 - c.weerbron_helderheid_paren["weather.knmi"][0][0]
    elif wijziging == "dag":
        c.helderheid_dagen["10.0"].append("2026-10-09")
    elif wijziging == "nieuwe_bron":
        c.weerbron_helderheid_paren["weather.nieuw"] = list(c.weerbron_helderheid_paren["weather.met"])
    else:
        # In place, zelfde lengte en zelfde laatste waarde: een teller of
        # een lengte zou dit missen.
        c.weerbron_helderheid_paren["weather.met"][5][1] += 777.0
    na = c.get_helderheid_ijking()
    assert na == c._bereken_helderheid_ijking() | {
        "helderheid_nu": na["helderheid_nu"],
        "ijklijn_nu_w": na["ijklijn_nu_w"],
    }
    if wijziging in ("nieuwe_bron", "dag"):
        assert na != voor


def test_het_moment_blijft_vers(make_coordinator):
    """helderheid_nu en ijklijn_nu_w volgen het moment, ook uit de cache."""
    c = make_coordinator(_maximaal())
    _vul(c)
    c.get_helderheid_ijking()
    c.gemeten_helderheid = lambda: 0.42
    c.ijklijn_vermogen_w = lambda elevatie: 4321.0
    uit = c.get_helderheid_ijking()
    assert uit["helderheid_nu"] == 0.42
    assert uit["ijklijn_nu_w"] == 4321.0


@pytest.mark.asyncio
async def test_geen_entiteit_rekent_traag(make_coordinator, hass):
    """Elke toestand ruim binnen de grens - ook met volle reeksen.

    Voor v5.57.1 met deze reeksen: zelfbeoordeling ~1.400 ms,
    betrouwbaarheid ~750 ms. Nu enkele ms. De grens is ruim voor CI.
    """
    c = make_coordinator(_maximaal())
    c._apply_persisted_state(_echte_toestand())
    _vul(c)
    entiteiten = await _alle_entiteiten(hass, c)
    for e in entiteiten:  # eerste keer: caches vullen
        try:
            e.extra_state_attributes
        except Exception:  # noqa: BLE001
            pass
    traag = {}
    for e in entiteiten:
        start = time.perf_counter()
        try:
            getattr(e, "native_value", None)
            e.extra_state_attributes
        except Exception:  # noqa: BLE001
            pass
        ms = (time.perf_counter() - start) * 1000
        if ms > 100:
            traag[type(e).__name__] = round(ms)
    assert not traag, traag


def test_zelfbeoordeling_snel_ook_na_nieuwe_meting(make_coordinator):
    """Ook als de cache net vervallen is (overdag elke ronde een meting)."""
    from custom_components.energy_management_system.sensor import GacsAssessmentSensor

    c = make_coordinator(_maximaal())
    _vul(c)
    s = GacsAssessmentSensor(c, "toets")
    s.extra_state_attributes
    c.helderheid_ijklijn["30.0"].append(2500.0)
    start = time.perf_counter()
    s.extra_state_attributes
    assert (time.perf_counter() - start) * 1000 < 250
    start = time.perf_counter()
    s.extra_state_attributes
    assert (time.perf_counter() - start) * 1000 < 100
