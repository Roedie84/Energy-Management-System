"""Een klein regressiewoud in gewoon Python (v2.9.0).

Gevraagd: "Is verder optimaliseren middels een Random Forest Regressor
nog een idee?" - en na mijn bezwaren: "Proberen kan altijd toch?"

Terecht. De bezwaren gingen over scikit-learn (numpy en scipy erbij,
zo'n 100 MB op een Raspberry Pi), niet over de techniek. Een woud voor
tweehonderd waarnemingen en acht kenmerken is in een paar honderd regels
te schrijven, zonder enige afhankelijkheid.

Wat de bezwaren NIET wegneemt:

- met ongeveer tweehonderd waarnemingen leert een woud de gegevens uit
  zijn hoofd. Daarom wordt hier getoetst op dagen die het model NIET
  heeft gezien, en vergeleken met de huidige methode op diezelfde dagen;
- de winst zit in de paar dagen met 41% fout, en of de informatie
  daarvoor in de kenmerken zit weten we niet. Dat is precies wat deze
  meting uitwijst;
- een woud is niet uit te leggen. Daarom stuurt het niets, en staat het
  op de proefstand tot de cijfers iets anders zeggen.
"""
from __future__ import annotations

import math
import random


class _Blad:
    __slots__ = ("waarde",)

    def __init__(self, waarde: float) -> None:
        self.waarde = waarde


class _Knoop:
    __slots__ = ("kenmerk", "grens", "links", "rechts")

    def __init__(self, kenmerk: int, grens: float, links, rechts) -> None:
        self.kenmerk = kenmerk
        self.grens = grens
        self.links = links
        self.rechts = rechts


def _gemiddelde(waarden: list[float]) -> float:
    return sum(waarden) / len(waarden) if waarden else 0.0


def _spreiding(waarden: list[float]) -> float:
    """Som van kwadratische afwijkingen - de maat die een splitsing
    probeert te verkleinen."""
    if len(waarden) < 2:
        return 0.0
    gem = _gemiddelde(waarden)
    return sum((w - gem) ** 2 for w in waarden)


def _bouw_boom(
    rijen: list[list[float]],
    doelen: list[float],
    kenmerken_per_splitsing: int,
    min_blad: int,
    diepte: int,
    max_diepte: int,
    rng: random.Random,
):
    """Eén regressieboom, recursief."""
    if (
        diepte >= max_diepte
        or len(rijen) < 2 * min_blad
        or _spreiding(doelen) < 1e-9
    ):
        return _Blad(_gemiddelde(doelen))

    aantal_kenmerken = len(rijen[0])
    kandidaten = rng.sample(
        range(aantal_kenmerken),
        min(kenmerken_per_splitsing, aantal_kenmerken),
    )

    beste = None
    beste_score = _spreiding(doelen)
    for kenmerk in kandidaten:
        waarden = sorted({rij[kenmerk] for rij in rijen})
        if len(waarden) < 2:
            continue
        # Grenzen tussen opeenvolgende unieke waarden.
        for a, b in zip(waarden, waarden[1:]):
            grens = (a + b) / 2
            links_d = [d for rij, d in zip(rijen, doelen) if rij[kenmerk] <= grens]
            rechts_d = [d for rij, d in zip(rijen, doelen) if rij[kenmerk] > grens]
            if len(links_d) < min_blad or len(rechts_d) < min_blad:
                continue
            score = _spreiding(links_d) + _spreiding(rechts_d)
            if score < beste_score:
                beste_score = score
                beste = (kenmerk, grens)

    if beste is None:
        return _Blad(_gemiddelde(doelen))

    kenmerk, grens = beste
    links_r, links_d, rechts_r, rechts_d = [], [], [], []
    for rij, doel in zip(rijen, doelen):
        if rij[kenmerk] <= grens:
            links_r.append(rij)
            links_d.append(doel)
        else:
            rechts_r.append(rij)
            rechts_d.append(doel)

    return _Knoop(
        kenmerk,
        grens,
        _bouw_boom(
            links_r, links_d, kenmerken_per_splitsing, min_blad,
            diepte + 1, max_diepte, rng,
        ),
        _bouw_boom(
            rechts_r, rechts_d, kenmerken_per_splitsing, min_blad,
            diepte + 1, max_diepte, rng,
        ),
    )


def _voorspel_boom(knoop, rij: list[float]) -> float:
    while isinstance(knoop, _Knoop):
        knoop = knoop.links if rij[knoop.kenmerk] <= knoop.grens else knoop.rechts
    return knoop.waarde


class RegressieWoud:
    """Een bos van regressiebomen op bootstrapmonsters."""

    def __init__(
        self,
        bomen: int = 30,
        max_diepte: int = 6,
        min_blad: int = 3,
        zaad: int = 20260817,
    ) -> None:
        self.bomen_aantal = bomen
        self.max_diepte = max_diepte
        self.min_blad = min_blad
        self._rng = random.Random(zaad)
        self._bomen: list = []

    def leer(self, rijen: list[list[float]], doelen: list[float]) -> None:
        self._bomen = []
        if not rijen or len(rijen) != len(doelen):
            return
        aantal_kenmerken = len(rijen[0])
        # De gebruikelijke keuze voor regressie: een derde van de
        # kenmerken per splitsing, met minimaal één.
        per_splitsing = max(1, aantal_kenmerken // 3)

        for _ in range(self.bomen_aantal):
            monster = [
                self._rng.randrange(len(rijen)) for _ in range(len(rijen))
            ]
            self._bomen.append(
                _bouw_boom(
                    [rijen[i] for i in monster],
                    [doelen[i] for i in monster],
                    per_splitsing,
                    self.min_blad,
                    0,
                    self.max_diepte,
                    self._rng,
                )
            )

    def voorspel(self, rij: list[float]) -> float | None:
        if not self._bomen:
            return None
        return sum(_voorspel_boom(b, rij) for b in self._bomen) / len(self._bomen)


def gemiddelde_absolute_fout(
    werkelijk: list[float], voorspeld: list[float]
) -> float | None:
    """De maat waarop het woud en de huidige methode worden vergeleken."""
    paren = [
        (w, v)
        for w, v in zip(werkelijk, voorspeld)
        if w is not None and v is not None and not math.isnan(w)
    ]
    if not paren:
        return None
    return sum(abs(w - v) for w, v in paren) / len(paren)
