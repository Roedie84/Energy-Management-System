"""Het berekende airco-vermogen nameten op de P1-meter (v5.265.0).

Ruud 26-11: "Hoe nauwkeurig is nu het airco-verbruik?" Het EMS rekent het
vermogen uit de compressorfrequentie, geleerd van de teller van Daikin zelf.
Er hangt geen eigen meter aan. Wel zit de airco op een eigen fase achter de
P1-meter. Met de hand nagemeten op 26-11 06:30-08:16: 1,54 kWh op de meter
tegen 1,63 kWh berekend (+6 %).

Deze module doet dat elke dag: per blok van tien minuten het gemiddelde
vermogen per fase en de gemiddelde frequentie. Blokken met de compressor uit
geven de rustwaarde van elke fase; blokken met de compressor aan geven wat de
fase boven die rustwaarde trok (rust binnen twee uur ervoor of erna). De fase die het meeste meebeweegt is de fase
van de airco.

Alleen een METING: de omrekening van het EMS verandert hier niet door. Het
besluit om te ijken op de P1-meter staat in het meetregister.

Alleen pure functies; de toestand staat in het dagritme (`ritme["ijking"]`),
het lopende blok in een dict die de coordinator vasthoudt.
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta

BLOK_MIN = 10
#: Zoveel metingen nodig in een blok (één per ronde van een minuut).
BLOK_MIN_METINGEN = 6
#: Een rustwaarde telt zo lang mee voor een blok met de compressor aan.
RUST_GELDIG_MIN = 120
RUST_MIN_BLOKKEN = 2
RUST_BEWAREN = 36
#: Een blok zonder rustwaarde wacht hooguit zo lang op een rustblok erna.
WACHT_MAX_MIN = 360
WACHT_BEWAREN = 40
BLOKKEN_BEWAREN = 700
#: Een oordeel pas vanaf zoveel blokken met de compressor aan.
OORDEEL_MIN_BLOKKEN = 30
#: Stabiel: de frequentie bewoog binnen het blok hooguit zoveel.
STABIEL_HZ = 10.0
#: v5.267.0: boven dit vermogen van de accu of de zonnepanelen telt een
#: meting als storing (ze zitten op een fase en overstemmen de airco).
ACCU_ZON_MAX_W = 50.0


def leeg() -> dict:
    return {"rust": [], "blokken": [], "wacht": []}


def geldig(model) -> dict:
    if not isinstance(model, dict):
        return leeg()
    model.setdefault("rust", [])
    model.setdefault("blokken", [])
    model.setdefault("wacht", [])
    return model


def nieuw_blok(now: datetime) -> dict:
    return {"begin": now.isoformat(), "hz": [], "fasen": [], "storing": False}


def ronde(model: dict, blok: dict, now: datetime, *, hz, fasen_w, storing: bool) -> dict:
    """Een meting erbij; geeft het (eventueel nieuwe) lopende blok terug."""
    model = geldig(model)
    begin = datetime.fromisoformat(blok["begin"])
    if now - begin >= timedelta(minutes=BLOK_MIN):
        _sluit(model, blok, begin)
        blok = nieuw_blok(now)
    if hz is None or not fasen_w or any(w is None for w in fasen_w):
        blok["storing"] = True
        return blok
    blok["hz"].append(float(hz))
    blok["fasen"].append([float(w) for w in fasen_w])
    if storing:
        blok["storing"] = True
    return blok


def _rust_rond(model: dict, begin: datetime, aantal: int) -> list | None:
    """De rustwaarde per fase uit de blokken met de compressor uit binnen
    `RUST_GELDIG_MIN` voor of na dit blok; None bij te weinig."""
    venster = timedelta(minutes=RUST_GELDIG_MIN)
    recent = [
        r["w"] for r in model["rust"]
        if abs(datetime.fromisoformat(r["t"]) - begin) <= venster and len(r["w"]) == aantal
    ]
    if len(recent) < RUST_MIN_BLOKKEN:
        return None
    return [statistics.median(r[i] for r in recent) for i in range(aantal)]


def _boek(model: dict, regel: dict, rust: list) -> None:
    model["blokken"].append({
        "t": regel["t"], "hz": regel["hz"], "stabiel": regel["stabiel"],
        "extra_w": [round(regel["w"][i] - rust[i], 1) for i in range(len(rust))],
    })
    model["blokken"].sort(key=lambda b: b["t"])
    del model["blokken"][:-BLOKKEN_BEWAREN]


def _sluit(model: dict, blok: dict, begin: datetime) -> None:
    if blok.get("storing") or len(blok["hz"]) < BLOK_MIN_METINGEN:
        return
    aantal = len(blok["fasen"][0])
    if any(len(f) != aantal for f in blok["fasen"]):
        return
    gem = [round(statistics.mean(f[i] for f in blok["fasen"]), 1) for i in range(aantal)]
    hz = blok["hz"]
    if max(hz) <= 0:
        model["rust"].append({"t": begin.isoformat(), "w": gem})
        del model["rust"][:-RUST_BEWAREN]
        # blokken die op een rustwaarde wachtten: de compressor liep langer
        # dan `RUST_GELDIG_MIN` aan een stuk
        nog = []
        for regel in model["wacht"]:
            tijd = datetime.fromisoformat(regel["t"])
            rust = _rust_rond(model, tijd, len(regel["w"]))
            if rust is not None:
                _boek(model, regel, rust)
            elif begin - tijd <= timedelta(minutes=WACHT_MAX_MIN):
                nog.append(regel)
        model["wacht"] = nog
        return
    regel = {
        "t": begin.isoformat(),
        "hz": round(statistics.mean(hz), 2),
        "stabiel": (max(hz) - min(hz)) <= STABIEL_HZ and min(hz) > 0,
        "w": gem,
    }
    rust = _rust_rond(model, begin, aantal)
    if rust is not None:
        _boek(model, regel, rust)
    else:
        model["wacht"].append(regel)
        del model["wacht"][:-WACHT_BEWAREN]


def _fase(blokken: list) -> int | None:
    """De fase van de airco: die het meeste meebeweegt, en duidelijk."""
    if not blokken:
        return None
    aantal = len(blokken[0]["extra_w"])
    som = [sum(b["extra_w"][i] for b in blokken if len(b["extra_w"]) == aantal) for i in range(aantal)]
    beste = max(range(aantal), key=lambda i: som[i])
    rest = max([abs(som[i]) for i in range(aantal) if i != beste] or [0.0])
    if som[beste] <= 0 or som[beste] < 3 * rest:
        return None
    return beste


def overzicht(model, w_per_hz: float | None, basis_w: float | None) -> dict:
    """Wat de meter zegt tegen wat het EMS rekent."""
    model = geldig(model)
    blokken = model["blokken"]
    uit = {
        "blokken": len(blokken),
        "blokken_nodig": OORDEEL_MIN_BLOKKEN,
        "toelichting": (
            "Het berekende airco-vermogen naast de P1-meter gelegd, per blok van "
            f"{BLOK_MIN} minuten. Alleen een meting; de omrekening van het EMS verandert hier niet door."
        ),
    }
    fase = _fase(blokken)
    if fase is None or w_per_hz is None or basis_w is None:
        uit["oordeel"] = "nog geen fase herkend" if blokken else "nog geen metingen"
        return uit
    paren = [(b["hz"], b["extra_w"][fase], bool(b.get("stabiel"))) for b in blokken]
    gemeten = sum(w for _hz, w, _s in paren)
    berekend = sum(max(w_per_hz * hz + basis_w, 0.0) for hz, _w, _s in paren)
    uit.update({
        "fase": fase + 1,
        "dagen": len({b["t"][:10] for b in blokken}),
        "gemeten_kwh": round(gemeten * BLOK_MIN / 60 / 1000, 2),
        "berekend_kwh": round(berekend * BLOK_MIN / 60 / 1000, 2),
    })
    if gemeten > 0:
        uit["afwijking_procent"] = round((berekend / gemeten - 1) * 100, 1)
    stabiel = [(hz, w) for hz, w, s in paren if s]
    if stabiel and sum(w for _hz, w in stabiel) > 0:
        uit["afwijking_stabiel_procent"] = round(
            (sum(max(w_per_hz * hz + basis_w, 0.0) for hz, _w in stabiel) / sum(w for _hz, w in stabiel) - 1) * 100, 1
        )
    n = len(paren)
    gx = sum(hz for hz, _w, _s in paren) / n
    gy = gemeten / n
    noemer = sum((hz - gx) ** 2 for hz, _w, _s in paren)
    if noemer > 0:
        a = sum((hz - gx) * (w - gy) for hz, w, _s in paren) / noemer
        uit["meter_w_per_hz"] = round(a, 1)
        uit["meter_basis_w"] = round(gy - a * gx, 0)
    uit["rekent_w_per_hz"] = round(w_per_hz, 1)
    uit["rekent_basis_w"] = round(basis_w, 0)
    uit["spreiding_w"] = round(math.sqrt(sum((max(w_per_hz * hz + basis_w, 0.0) - w) ** 2 for hz, w, _s in paren) / n), 0)
    uit["oordeel"] = "genoeg metingen" if n >= OORDEEL_MIN_BLOKKEN else "nog te weinig metingen"
    return uit
