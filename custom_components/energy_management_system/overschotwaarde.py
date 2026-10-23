"""Waarde van zonoverschot: wat is een extra kWh verbruik NU waard? (v5.121.0)

Gevraagd 23-10 ("Wat verbetert toepassen"), punt 1. Een apparaat dat nu een
kWh extra gebruikt, kost niet altijd de inkoopprijs:

* Is er zonoverschot en kan de accu niets meer opnemen (vol, of hij laadt al
  op zijn maximum), dan gaat die kWh anders het net op. Hij kost dan wat
  terugleveren had opgebracht: de TERUGLEVERWAARDE.
* Anders komt hij (direct of via de accu) uit inkoop: de INKOOPPRIJS.

Onder het salderen is de terugleverwaarde gelijk aan de inkoopprijs (plus de
vaste premie): er valt niets te kiezen en het EMS gedraagt zich als altijd.
Vanaf 2027 betaalt Zonneplan de kale prijs + € 0,02 + 10 % zonnebonus (over
een positieve kale prijs), zonder terugleverkosten. Dan is een kWh uit
overschot een stuk goedkoper dan een kWh uit het net, en loont het om
warmte (airco), fietsladers en witgoed naar het overschot te schuiven.

Sturen gebeurt alleen in het regime van 2027; tot dan rekent dit bestand in
de schaduw (sensorattributen, generale repetitie).

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

#: Vaste premie per teruggeleverde kWh (gelijk aan FEEDIN_PREMIUM_EUR_PER_KWH).
PREMIE_EUR = 0.02
#: Zonnebonus van Zonneplan: 10 % over de (positieve) kale prijs.
ZONNEBONUS_FRACTIE = 0.10
#: Onder dit overschot (W) telt het als "geen overschot" (meetruis).
OVERSCHOT_MIN_W = 50.0
#: Laadt de accu op minstens dit deel van zijn maximum, dan neemt hij niets meer op.
MAX_LADEN_FRACTIE = 0.95
#: Binnen zoveel procentpunt van de bovengrens telt de accu als vol.
VOL_MARGE_PROCENT = 2.0
#: In een kwartierplan: zoveel kWh onder het maximum telt als vol.
VOL_MARGE_KWH = 0.1


def terugleverwaarde_2027(kaal_eur: float | None, terugleverkosten_eur: float = 0.0) -> float | None:
    """Wat een teruggeleverde kWh vanaf 2027 oplevert: kaal + premie + bonus.

    De zonnebonus geldt alleen over een positieve kale prijs; bij een negatieve
    kale prijs blijft het kaal + premie (kan dan onder nul komen: terugleveren
    kost geld).
    """
    if kaal_eur is None:
        return None
    return kaal_eur + PREMIE_EUR + ZONNEBONUS_FRACTIE * max(0.0, kaal_eur) - (terugleverkosten_eur or 0.0)


def marginale_waarde(
    *,
    overschot_w: float | None,
    accu_vol: bool,
    laadt_op_max: bool,
    inkoop_eur: float | None,
    teruglever_eur: float | None,
) -> dict:
    """De waarde van één extra kWh verbruik op dit moment.

    `overschot_w` = zon min huis (zonder de accu). Geeft `eur` (None als de
    prijs ontbreekt), `bron` ("teruglevering" of "inkoop") en een korte reden.
    """
    overschot = (overschot_w or 0.0) > OVERSCHOT_MIN_W
    if overschot and (accu_vol or laadt_op_max) and teruglever_eur is not None:
        reden = "zonoverschot en de accu is vol" if accu_vol else "zonoverschot en de accu laadt al op zijn maximum"
        return {"eur": round(teruglever_eur, 5), "bron": "teruglevering", "reden": reden}
    if overschot:
        reden = "zonoverschot, maar de accu neemt het nog op"
    else:
        reden = "geen zonoverschot"
    return {
        "eur": round(inkoop_eur, 5) if inkoop_eur is not None else None,
        "bron": "inkoop",
        "reden": reden,
    }


def is_vol(soc_procent: float | None, bovengrens_procent: float | None) -> bool:
    if soc_procent is None or bovengrens_procent is None:
        return False
    return soc_procent >= bovengrens_procent - VOL_MARGE_PROCENT


def laadt_op_max(laad_w: float | None, max_laad_w: float | None) -> bool:
    """`laad_w` positief = laden."""
    if laad_w is None or not max_laad_w:
        return False
    return laad_w >= MAX_LADEN_FRACTIE * abs(max_laad_w)


def per_kwartier(
    kwartieren: list[dict],
    *,
    start_kwh: float,
    bruikbaar_kwh: float,
    laad_kwh_max: float,
) -> list[dict]:
    """De marginale waarde per kwartier van een kwartierplan.

    Elk kwartier: `zon_kwh`, `verbruik_kwh`, `soc_kwh` (stand NA het
    kwartier), `inkoop_eur` en `teruglever_eur`. Vol = de stand na het
    kwartier zit binnen VOL_MARGE_KWH van het maximum; op max = de toename is
    minstens MAX_LADEN_FRACTIE van wat er per kwartier in kan.
    """
    uit = []
    vorige = start_kwh
    for kw in kwartieren:
        stand = kw.get("soc_kwh")
        stand = vorige if stand is None else stand
        overschot_kwh = (kw.get("zon_kwh") or 0.0) - (kw.get("verbruik_kwh") or 0.0)
        toename = stand - vorige
        w = marginale_waarde(
            overschot_w=overschot_kwh * 4000,
            accu_vol=stand >= bruikbaar_kwh - VOL_MARGE_KWH,
            laadt_op_max=laad_kwh_max > 0 and toename >= MAX_LADEN_FRACTIE * laad_kwh_max,
            inkoop_eur=kw.get("inkoop_eur"),
            teruglever_eur=kw.get("teruglever_eur"),
        )
        uit.append({**w, "start": kw.get("start"), "overschot_kwh": round(max(0.0, overschot_kwh), 3)})
        vorige = stand
    return uit


def beste_venster(waarden: list[dict], kwartieren_nodig: int) -> dict | None:
    """Het aaneengesloten venster van `kwartieren_nodig` kwartieren met de
    laagste som van de marginale waarde (witgoedadvies). None als er te
    weinig kwartieren met een prijs zijn."""
    n = max(1, int(kwartieren_nodig))
    if len(waarden) < n:
        return None
    beste = None
    for i in range(len(waarden) - n + 1):
        stuk = waarden[i:i + n]
        if any(w.get("eur") is None for w in stuk):
            continue
        som = sum(w["eur"] for w in stuk) / n
        if beste is None or som < beste["gemiddeld_eur"] - 1e-9:
            beste = {
                "start": stuk[0].get("start"),
                "gemiddeld_eur": round(som, 5),
                "uit_overschot_kwartieren": sum(1 for w in stuk if w.get("bron") == "teruglevering"),
            }
    return beste


# --- punt 6: negatieve terugleverwaarde (2027) --------------------------------

#: Dode zone rond nul op de P1-meter (W): binnen deze band de grens laten staan.
NUL_DODE_ZONE_W = 75.0
#: Ruimte die de accu boven de berekende behoefte extra vrijhoudt (kWh).
RUIMTE_MARGE_KWH = 0.3
#: Zo ver vooruit kijkt de ruimtetoets (uur).
RUIMTE_HORIZON_UUR = 12


def ruimte_voor_negatief(
    kwartieren: list[dict],
    *,
    now,
    bruikbaar_kwh: float | None,
    beschikbaar_kwh: float | None,
    laad_kwh: float,
    teruglever_nu: float | None,
    overschot_w: float | None,
) -> dict:
    """Moet de accu de zon nu laten gaan om ruimte te houden voor straks?

    `kwartieren`: per kwartier `start` (datetime), `overschot_kwh`,
    `inkoop_eur` en `teruglever_2027_eur`. De uren met een negatieve
    terugleverwaarde die vandaag nog komen (binnen RUIMTE_HORIZON_UUR, het
    eerste aaneengesloten stuk): zoveel overschot kan de accu daar opvangen
    (hooguit `laad_kwh` per kwartier; bij een negatieve ALL-IN prijs laadt het
    EMS op vol vermogen uit het net, dus dan het hele `laad_kwh`). Is de
    vrije ruimte nu kleiner dan dat plus een marge, en levert terugleveren NU
    nog iets op, dan het overschot van nu niet opslaan.
    """
    leeg = {"ruimte_houden": False, "nodig_kwh": 0.0, "vrij_kwh": None, "negatief_vanaf": None}
    if bruikbaar_kwh is None or beschikbaar_kwh is None:
        return leeg
    vrij = max(0.0, bruikbaar_kwh - beschikbaar_kwh)
    leeg["vrij_kwh"] = round(vrij, 2)
    eerste = None
    nodig = 0.0
    from datetime import timedelta

    grens = now + timedelta(hours=RUIMTE_HORIZON_UUR)
    for k in sorted(kwartieren, key=lambda x: x["start"]):
        if k["start"] < now - timedelta(minutes=15) or k["start"] >= grens:
            continue
        t = k.get("teruglever_2027_eur")
        negatief = t is not None and t < 0
        if eerste is None:
            if not negatief:
                continue
            eerste = k["start"]
        elif not negatief:
            break   # alleen het eerste aaneengesloten stuk
        if (k.get("inkoop_eur") or 0.0) < 0:
            nodig += laad_kwh
        else:
            nodig += min(k.get("overschot_kwh") or 0.0, laad_kwh)
    if eerste is None:
        return leeg
    nodig = min(nodig, bruikbaar_kwh)
    voor_het_blok = now < eerste
    houden = (
        voor_het_blok
        and teruglever_nu is not None and teruglever_nu > 0
        and (overschot_w or 0.0) > OVERSCHOT_MIN_W
        and vrij < nodig + RUIMTE_MARGE_KWH
    )
    return {
        "ruimte_houden": bool(houden),
        "nodig_kwh": round(nodig, 2),
        "vrij_kwh": round(vrij, 2),
        "negatief_vanaf": eerste.isoformat() if hasattr(eerste, "isoformat") else eerste,
    }


def grens_voor_nul_teruglevering(
    *, huidig_procent: float | None, pv_w: float | None, net_w: float | None
) -> float | None:
    """De nieuwe omvormergrens (%) voor ~0 W op de P1-meter.

    `net_w` negatief = teruglevering. Evenredig: de zon die nu het net op gaat
    eraf (of bij import erbij), naar rato van de huidige grens. None binnen de
    dode zone of zonder meting.
    """
    if huidig_procent is None or pv_w is None or net_w is None:
        return None
    if abs(net_w) <= NUL_DODE_ZONE_W:
        return None
    if net_w > 0 and huidig_procent >= 100:
        return None
    if pv_w <= 50:
        # bijna niets opgewekt: bij teruglevering dicht, bij import open
        return 0.0 if net_w < 0 else 100.0
    doel_pv = max(0.0, pv_w + net_w)
    nieuw = huidig_procent * doel_pv / pv_w
    if net_w > 0 and huidig_procent < 5:
        nieuw = max(nieuw, huidig_procent + 10)
    nieuw = max(0.0, min(100.0, nieuw))
    return round(nieuw, 1) if abs(nieuw - huidig_procent) >= 1.0 else None
