"""Meetlat voor de verbruiksvoorspelling van het plan (v5.214.0).

Ruud 11-11 11:55 (akkoord, punt 3): van de zonvoorspelling weet het EMS hoe
ver die ernaast zit; van het verbruik niet per kwartier vooruit. Hier: wat
het plan voor een kwartier verwachtte toen dat kwartier 0, 1 en 3 uur weg
was, tegen het gemeten gemiddelde van dat kwartier.

Alleen meten; stuurt niets. Zuivere functies en een kleine toestand, zonder
Home Assistant. Niet bewaard over een herstart (de telling begint dan opnieuw).
"""
from __future__ import annotations

#: kwartieren vooruit -> naam
HORIZONNEN = {0: "dit_kwartier", 4: "1_uur", 12: "3_uur"}
#: zoveel openstaande kwartieren bewaren (3 uur vooruit plus speling)
MAX_OPEN = 40


class Verbruiksmeetlat:
    def __init__(self) -> None:
        self._open: dict[str, dict[int, float]] = {}
        self._genoteerd: str | None = None
        self._som: dict[int, list] = {h: [0, 0.0, 0.0] for h in HORIZONNEN}
        self.laatste: dict | None = None

    def noteer_plan(self, kwartier: str, rijen: list[dict]) -> bool:
        """Het eerste plan van een kwartier: de verwachting per horizon.

        `rijen` = de planrijen vanaf nu (begin, verbruik_kwh, uren). True als
        er genoteerd is (één keer per kwartier).
        """
        if not kwartier or kwartier == self._genoteerd or not rijen:
            return False
        self._genoteerd = kwartier
        for h in HORIZONNEN:
            if h >= len(rijen):
                continue
            r = rijen[h] or {}
            uren = float(r.get("uren") or 0.25)
            kwh = r.get("verbruik_kwh")
            begin = r.get("begin")
            if kwh is None or begin is None or uren <= 0:
                continue
            sleutel = begin.isoformat() if hasattr(begin, "isoformat") else str(begin)
            self._open.setdefault(sleutel[:16], {})[h] = float(kwh) / uren * 1000
        for oud in sorted(self._open)[:-MAX_OPEN]:
            self._open.pop(oud, None)
        return True

    def sluit_kwartier(self, begin: str, gemeten_w: float | None) -> dict | None:
        """Een afgelopen kwartier: de fout per horizon erbij."""
        verwacht = self._open.pop(str(begin)[:16], None)
        if not verwacht or gemeten_w is None:
            return None
        uit = {"kwartier": str(begin)[:16], "gemeten_w": round(float(gemeten_w))}
        for h, w in verwacht.items():
            fout = w - float(gemeten_w)
            s = self._som[h]
            s[0] += 1
            s[1] += abs(fout)
            s[2] += fout
            uit[HORIZONNEN[h]] = round(w)
        self.laatste = uit
        return uit

    def overzicht(self) -> dict:
        """Per horizon: aantal kwartieren, gemiddelde fout en afwijking (W)."""
        uit: dict = {"toelichting": (
            "Wat het plan voor een kwartier aan verbruik verwachtte (0, 1 en 3 uur "
            "vooraf) tegen het gemeten gemiddelde. Fout = gemiddeld ernaast; afwijking "
            "= te hoog (+) of te laag (-). Sinds de laatste herstart. Alleen meten."
        )}
        for h, naam in HORIZONNEN.items():
            n, absoluut, som = self._som[h]
            uit[naam] = {
                "kwartieren": n,
                "fout_w": round(absoluut / n) if n else None,
                "afwijking_w": round(som / n) if n else None,
            }
        if self.laatste:
            uit["laatste"] = self.laatste
        return uit
