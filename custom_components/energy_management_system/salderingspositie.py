"""Waar staat de saldering aan het eind van het salderingsjaar? (v5.168.0)

Ruud 02-11 22:40: Zonneplan saldeert per CONTRACTJAAR. In het lopende
contractjaar (vanaf 1 april) leverde hij ~1470 kWh terug tegen ~500 kWh
afname. November en december voegen naar verwachting een paar honderd kWh
afname toe, dus op 31-12 (het einde van de saldering) staat hij nog steeds
honderden kWh "in de plus".

Wat dat betekent voor één kWh extra:

* een kWh extra AFNAME wordt weggestreept tegen het overschot: de
  energiebelasting (plus btw daarover) wordt er effectief niet over betaald;
* een kWh extra TERUGLEVERING vergroot alleen het overschot, en over een
  overschot krijg je geen energiebelasting terug.

De MARGINALE waarde van een kWh is dan in beide richtingen de prijs zonder
het belastingdeel. Het plan rekende met de volle prijs incl. belasting, en
dat overschat elk verlies (rondrit ~81 %) en dus de drempel om goedkoop te
laden voor een duur kwartier.

Deze module rekent alleen de positie uit; welke prijs het plan gebruikt,
beslist de coordinator. Zuiver Python, zonder Home Assistant.

Drie standen:

* ``overschot`` - de verwachte eindstand ligt verder onder nul dan de marge:
  rekenen met de prijs zonder belastingdeel.
* ``tekort`` - de verwachte eindstand ligt verder boven nul dan de marge:
  elke kWh kost/levert de volle prijs; het bestaande gedrag.
* ``onzeker`` - rond nul, of te weinig gegevens. Ook dan het bestaande
  gedrag. Bewust: de kant op "overschot" mis hebben kost meer dan de andere
  kant. Wie onterecht zonder belasting rekent, laadt en verliest kWh die
  uiteindelijk wél belast worden afgerekend (dan is het rondritverlies tegen
  de volle prijs echt geld). Wie onterecht mét belasting rekent, laat alleen
  een paar marginale ladingen liggen - het oude, bekende gedrag.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

OVERSCHOT = "overschot"
TEKORT = "tekort"
ONZEKER = "onzeker"
NA_SALDERING = "na_saldering"

#: Nooit een kleinere marge dan dit (kWh) rond nul.
MARGE_MIN_KWH = 100.0
#: Zoveel standaardafwijkingen van het dagsaldo, over de resterende dagen.
MARGE_SIGMA = 3.0
#: Plus dit deel van de verwachte resterende afname: de verwachting zelf kan
#: ernaast zitten (koudere winter, meer netladen onder de nieuwe prijs). Klein,
#: omdat de verwachting al de HOOGSTE van de twee bronnen is. Live 02-11: vorig
#: jaar 3-11..31-12 gemiddeld 12,2 kWh per dag (sigma 4,6), de laatste weken
#: ~6,5; eindstand -962 + 722 = -240 kWh, marge 106 + 72 = 178 kWh. Pas als
#: november en december 33 % boven vorig jaar uitkomen, eindigt het jaar
#: netto in de min.
MARGE_MODELFOUT = 0.10
#: Recente dagen voor de verwachting.
RECENT_DAGEN = 28
#: Zoveel recente dagen zijn minimaal nodig.
RECENT_MIN_DAGEN = 14
#: Zoveel van de dagen vorig jaar moeten er zijn om die reeks te gebruiken.
VORIG_JAAR_DEKKING = 0.7
#: Mag er van de dagen sinds het begin van het contractjaar zoveel ontbreken.
MAX_ONTBREKEND_DEEL = 0.1


def _verschuif_jaar(d: date, jaren: int) -> date:
    try:
        return d.replace(year=d.year + jaren)
    except ValueError:  # 29 februari
        return d.replace(year=d.year + jaren, day=28)


def contractjaar(start: date | None, vandaag: date) -> tuple[date, date] | None:
    """(begin, laatste dag) van het lopende contractjaar, of None."""
    if start is None:
        return None
    begin = _verschuif_jaar(start, vandaag.year - start.year)
    if begin > vandaag:
        begin = _verschuif_jaar(begin, -1)
    return begin, _verschuif_jaar(begin, 1) - timedelta(days=1)


def _saldo(rij: dict) -> float | None:
    imp, exp = rij.get("import_kwh"), rij.get("export_kwh")
    if imp is None or exp is None:
        return None
    try:
        return float(imp) - float(exp)
    except (TypeError, ValueError):
        return None


def _per_dag(dagen: list[dict]) -> dict[date, float]:
    uit: dict[date, float] = {}
    for r in dagen or []:
        try:
            d = date.fromisoformat(str(r.get("datum")))
        except (TypeError, ValueError):
            continue
        s = _saldo(r)
        if s is not None:
            uit[d] = s
    return uit


def _reeks(saldi: dict[date, float], van: date, tot: date) -> list[float]:
    """Dagsaldi van `van` tot en met `tot`."""
    return [v for d, v in saldi.items() if van <= d <= tot]


def _schatting(waarden: list[float]) -> tuple[float, float]:
    gem = sum(waarden) / len(waarden)
    sigma = statistics.pstdev(waarden) if len(waarden) > 1 else abs(gem)
    return gem, sigma


def bepaal(
    dagen: list[dict],
    vandaag: date,
    contract_start: date | None,
    salderen_tot: date | None,
    vandaag_import_kwh: float = 0.0,
    vandaag_export_kwh: float = 0.0,
    dagdeel_verstreken: float = 0.0,
) -> dict:
    """De salderingspositie.

    `dagen`: dagregels met ``datum``, ``import_kwh`` en ``export_kwh`` (de
    netmeter; afgesloten dagen). Vandaag komt apart, tot nu toe.
    `dagdeel_verstreken`: welk deel van vandaag al voorbij is (0-1).
    """
    uit: dict = {"modus": ONZEKER}
    if salderen_tot is not None and vandaag > salderen_tot:
        uit.update(modus=NA_SALDERING, reden="de saldering is voorbij")
        return uit
    jaar = contractjaar(contract_start, vandaag)
    if jaar is None:
        uit["reden"] = "geen contractstart ingesteld; het salderingsjaar is onbekend"
        return uit
    begin, jaar_eind = jaar
    eind = min(jaar_eind, salderen_tot) if salderen_tot else jaar_eind
    uit.update(
        contractjaar_begin=begin.isoformat(),
        contractjaar_eind=jaar_eind.isoformat(),
        eind=eind.isoformat(),
    )
    saldi = _per_dag(dagen)
    verstreken = (vandaag - begin).days
    tot_nu = _reeks(saldi, begin, vandaag - timedelta(days=1))
    ontbreekt = verstreken - len(tot_nu)
    vandaag_saldo = float(vandaag_import_kwh or 0.0) - float(vandaag_export_kwh or 0.0)
    balans = sum(tot_nu) + vandaag_saldo
    uit.update(
        balans_kwh=round(balans, 1),
        dagen_gemeten=len(tot_nu),
        dagen_ontbrekend=max(0, ontbreekt),
    )
    if verstreken > 0 and ontbreekt > MAX_ONTBREKEND_DEEL * verstreken:
        uit["reden"] = f"{ontbreekt} van {verstreken} dagen ontbreken in de meterreeks"
        return uit
    rest_dagen = max(0.0, (eind - vandaag).days + 1 - min(1.0, max(0.0, dagdeel_verstreken)))
    uit["resterende_dagen"] = round(rest_dagen, 2)

    bronnen = {}
    morgen = vandaag + timedelta(days=1)
    if eind >= morgen:
        vj = _reeks(saldi, _verschuif_jaar(morgen, -1), _verschuif_jaar(eind, -1))
        nodig = (eind - morgen).days + 1
        if len(vj) >= VORIG_JAAR_DEKKING * nodig and vj:
            bronnen["vorig_jaar"] = _schatting(vj)
    recent = _reeks(saldi, vandaag - timedelta(days=RECENT_DAGEN), vandaag - timedelta(days=1))
    if len(recent) >= RECENT_MIN_DAGEN:
        bronnen["recent"] = _schatting(recent)
    if not bronnen and rest_dagen > 1:
        uit["reden"] = "te weinig dagen om de rest van het salderingsjaar te schatten"
        return uit
    # De hoogste verwachte afname per dag: de voorzichtige kant (een hogere
    # afname maakt een overschot kleiner). In november ligt het verbruik van
    # vorig jaar meestal boven dat van de laatste weken (minder zon, kouder).
    bron, (per_dag, sigma) = max(bronnen.items(), key=lambda kv: kv[1][0]) if bronnen else ("geen", (0.0, 0.0))
    verwacht = per_dag * rest_dagen
    sigma_max = max((s for _g, s in bronnen.values()), default=0.0)
    marge = max(
        MARGE_MIN_KWH,
        MARGE_SIGMA * sigma_max * math.sqrt(rest_dagen) + MARGE_MODELFOUT * abs(verwacht),
    )
    eindstand = balans + verwacht
    uit.update(
        verwachting_bron=bron,
        verwacht_per_dag_kwh=round(per_dag, 2),
        verwacht_rest_kwh=round(verwacht, 1),
        eindstand_kwh=round(eindstand, 1),
        marge_kwh=round(marge, 1),
        schattingen={k: {"per_dag_kwh": round(g, 2), "sigma_kwh": round(s, 2)} for k, (g, s) in bronnen.items()},
    )
    if eindstand < -marge:
        uit["modus"] = OVERSCHOT
        uit["overschot_kwh"] = round(-eindstand, 0)
        uit["reden"] = (
            f"naar verwachting {-eindstand:.0f} kWh overschot op {eind:%d-%m-%Y} "
            f"(marge {marge:.0f} kWh)"
        )
    elif eindstand > marge:
        uit["modus"] = TEKORT
        uit["reden"] = (
            f"naar verwachting {eindstand:.0f} kWh netto afname op {eind:%d-%m-%Y}; "
            "elke kWh telt tegen de volle prijs"
        )
    else:
        uit["reden"] = (
            f"verwachte eindstand {eindstand:+.0f} kWh ligt binnen de marge van "
            f"{marge:.0f} kWh; voorzichtig met de volle prijs gerekend"
        )
    return uit


def marginale_prijzen(prijs_incl: float, belastingdeel: float, premie: float, overschot: bool) -> tuple[float, float]:
    """(inkoop, teruglever) per kWh voor het plan zolang er gesaldeerd wordt.

    Bij een overschot beide zonder het belastingdeel; de premie blijft (die
    betaalt Zonneplan over elke teruggeleverde kWh, los van de saldering).
    Het belastingdeel wordt nooit negatief afgetrokken, dus de marginale
    prijs ligt nooit boven de prijs incl. belasting.
    """
    korting = max(0.0, belastingdeel) if overschot else 0.0
    inkoop = prijs_incl - korting
    return inkoop, inkoop + premie
