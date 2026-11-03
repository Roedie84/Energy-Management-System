"""Rondrit-rendement verankerd op de kWh-meter van de accu (v5.169.0).

Aanleiding (audit 03-11): het waardeplan rekende met laden 81,9 % x
ontladen 95,8 % = 78,5 % heen en terug, het geleerde rendement met
83,3 % x 96,0 % = 80,0 %. De kWh-meter van de accu (een HomeWizard,
`sensor.zendure_batterij_energy_import` / `_energie_export`) gaf over
oktober 226,5 kWh erin en 194,1 eruit bij een kleine daling van de
laadstand: AC -> AC ~85 %, rustverbruik inbegrepen.

Waarom de halve metingen te laag uitkwamen: ze rekenen in inhoud-eenheden
(laadstand x 11,52 kWh), en die schaal is niet precies de AC-schaal (de
ijking van de Zendure, niet-lineair). Ontladen in inhoud-eenheden komt
daardoor vaak BOVEN 1,0 uit (AC eruit ~3-8 % meer dan de daling van de
laadstand). De code gooide rondes boven 1,15 weg en kapte de uitkomst op
1,0 af; het product (de rondrit) kwam zo stelselmatig 5-7 pt te laag uit.

Oplossing:
1. De RONDRIT uit de tellerstanden over een lang venster (>= 14 dagen,
   standaard 30): rondrit = AC eruit / (AC erin - verandering inhoud /
   laadrendement). De inhoudsverandering wordt zo teruggerekend naar de
   AC die ervoor nodig was (of die hij uitspaarde).
2. Het gemeten LAADRENDEMENT (stijging inhoud / AC erin, per ronde) blijft
   het splitspunt; het ontlaadrendement (inhoud -> AC) = rondrit /
   laadrendement, en dat mag boven 1,0 (het is een schaalfactor tussen
   SoC-eenheden en AC). Binnen ONTLADEN_MIN..ONTLADEN_MAX.
3. De ontlaadbanden houden hun onderlinge verhouding; ze worden zo
   geschaald dat hun gewogen gemiddelde (naar de inhoud die eruit ging)
   gelijk is aan rondrit / laadrendement. Zo is laden x ontladen bij elke
   gebruiker de gemeten rondrit.

v5.170.0 - de rondrit voor BESLISSINGEN zonder sluimerverbruik:
De tellerstanden tellen ook mee wat de accu gebruikt als hij stilstaat
(sluimer: sparen ~5-11 W uit de cellen, leeg/vol uit het net). Dat gebeurt
of je nu een extra ronde maakt of niet, en het EMS rekent het extra
sluimeren van VASTGEHOUDEN energie al apart (`_sluimer_bij_sparen`,
v5.155.0). In het rendement zou het dus dubbel tellen en een rustige week
het rendement omlaag drukken. Daarom:

    rondrit_conversie = AC eruit / (AC erin - Δinhoud/laden - sluimer_ac)

met sluimer_ac = wat er in de stilstandkwartieren van het venster uit het
net ging (stand vol/leeg) plus de afname van de inhoud (sparen/overig,
teruggerekend naar AC met / laden). Gemeten als het gemiddelde vermogen
per stand (`accukosten.sluimerverbruik`: de lange blokken als die
betrouwbaar zijn, anders per kwartier) x de stilstanduren per stand uit de
kwartierreeks; dekt de reeks het venster niet helemaal, dan opgeschaald.
`rendement` (wat alle gebruikers lezen) wordt de conversie;
`rendement_totaal` blijft staan voor de weergave. Zonder sluimermeting of
buiten 60-95 % blijft het de totale rondrit (v5.169.0).

Losse functies zonder Home Assistant.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .accukosten import STIL_KWH, _moment, _stilstand_soort

#: Het venster voor de tellerstanden (dagen).
VENSTER_DAGEN = 30
#: Korter dan dit venster: geen anker (dan de oude rekenwijze).
MIN_DAGEN = 14.0
#: Minstens zoveel kWh moet er in het venster de accu in zijn gegaan.
MIN_AC_KWH = 20.0
#: Een rondrit buiten deze grenzen is een meetfout (meterwissel, gat).
RONDRIT_MIN = 0.60
RONDRIT_MAX = 0.95
#: Het ontlaadrendement in inhoud-eenheden (inhoud -> AC): een schaalfactor,
#: dus boven 1,0 toegestaan. Buiten deze grenzen afgekapt.
ONTLADEN_MIN = 0.85
ONTLADEN_MAX = 1.20
#: Zonder gemeten laadrendement rekent de inhoudsverandering hiermee terug.
LAADRENDEMENT_TERUGVAL = 0.85
#: Hooguit zoveel minuten mag een inhoudsregel naast het tellermoment liggen.
INHOUD_SPELING_MIN = 20


def inhoud_op(inhoud: dict, moment: datetime) -> float | None:
    """De inhoud (kWh) het dichtst bij `moment`, binnen INHOUD_SPELING_MIN."""
    beste = None
    for t, kwh in inhoud.items():
        afstand = abs((t - moment).total_seconds())
        if afstand <= INHOUD_SPELING_MIN * 60 and (beste is None or afstand < beste[0]):
            beste = (afstand, kwh)
    return None if beste is None else beste[1]


def _randen(erin: dict, eruit: dict, inhoud: dict) -> tuple | None:
    """Het vroegste en laatste moment met beide tellers en een inhoud."""
    momenten = sorted(set(erin) & set(eruit))
    begin = next((t for t in momenten if inhoud_op(inhoud, t) is not None), None)
    eind = next((t for t in reversed(momenten) if inhoud_op(inhoud, t) is not None), None)
    if begin is None or eind is None or eind <= begin:
        return None
    return begin, eind


def rondrit_uit_meter(erin: dict, eruit: dict, inhoud: dict, laadrendement: float | None,
                      min_dagen: float = MIN_DAGEN) -> dict:
    """De rondrit uit de tellerstanden van de kWh-meter van de accu.

    `erin`/`eruit`: {moment: cumulatieve tellerstand in kWh} (bijv. de
    `sum` van de uurstatistiek, op het eind van het uur). `inhoud`:
    {moment: inhoud in kWh} (de beschikbare energie van het dagverloop).
    Geeft altijd een dict met `rendement` (fractie of None) en de reden.
    """
    uit: dict = {"rendement": None}
    randen = _randen(erin or {}, eruit or {}, inhoud or {})
    if randen is None:
        uit["reden"] = "geen tellerstanden met een bekende inhoud aan begin en eind"
        return uit
    begin, eind = randen
    dagen = (eind - begin).total_seconds() / 86400
    ac_in = erin[eind] - erin[begin]
    ac_uit = eruit[eind] - eruit[begin]
    delta = inhoud_op(inhoud, eind) - inhoud_op(inhoud, begin)
    eta_l = laadrendement if laadrendement and 0.5 <= laadrendement <= 1.0 else LAADRENDEMENT_TERUGVAL
    noemer = ac_in - delta / eta_l
    uit.update({
        "van": begin.isoformat(), "tot": eind.isoformat(), "dagen": round(dagen, 1),
        "ac_erin_kwh": round(ac_in, 2), "ac_eruit_kwh": round(ac_uit, 2),
        "inhoud_verandering_kwh": round(delta, 2),
        "laadrendement_voor_inhoud": round(eta_l, 3),
    })
    if dagen < min_dagen:
        uit["reden"] = f"venster {dagen:.1f} dagen, minstens {min_dagen:.0f} nodig"
        return uit
    if ac_in < MIN_AC_KWH or noemer <= 0:
        uit["reden"] = f"te weinig door de accu ({ac_in:.1f} kWh erin)"
        return uit
    rt = ac_uit / noemer
    uit["rendement_gemeten"] = round(rt, 4)
    if not RONDRIT_MIN <= rt <= RONDRIT_MAX:
        uit["reden"] = f"rondrit {rt * 100:.1f} % buiten {RONDRIT_MIN * 100:.0f}-{RONDRIT_MAX * 100:.0f} %"
        return uit
    uit["rendement"] = rt
    uit["reden"] = "ok"
    return uit


def ontlaadrendement(rondrit: float, laadrendement: float) -> float:
    """Ontladen (inhoud -> AC) = rondrit / laden, binnen ONTLADEN_MIN..MAX."""
    return max(ONTLADEN_MIN, min(ONTLADEN_MAX, rondrit / laadrendement))


def schaal_ontlaadbanden(banden: dict | None, doel: float) -> dict | None:
    """De ontlaadbanden zo geschaald dat hun gewogen gemiddelde `doel` is.

    Gewogen naar `kwh` (de inhoud die in die band eruit ging), over elke band
    met een rendement: dat gemiddelde is precies AC eruit / inhoud eruit over
    alle meegetelde rondes. De onderlinge verhouding blijft; elke band binnen
    ONTLADEN_MIN..ONTLADEN_MAX. Het gemeten getal blijft staan als
    `rendement_gemeten_procent`. Zonder bruikbare band ongewijzigd.
    """
    if not banden:
        return banden
    ontladen = banden.get("ontladen") or {}
    teller = noemer = 0.0
    for b in ontladen.values():
        if b.get("rendement_procent") and b.get("kwh"):
            teller += b["kwh"] * b["rendement_procent"] / 100
            noemer += b["kwh"]
    if noemer <= 0 or teller <= 0:
        return banden
    factor = doel / (teller / noemer)
    nieuw = {}
    for naam, b in ontladen.items():
        b = dict(b)
        if b.get("rendement_procent"):
            b["rendement_gemeten_procent"] = b["rendement_procent"]
            eta = max(ONTLADEN_MIN, min(ONTLADEN_MAX, b["rendement_procent"] / 100 * factor))
            b["rendement_procent"] = round(eta * 100, 1)
        nieuw[naam] = b
    return {**banden, "ontladen": nieuw, "ontladen_geschaald_met": round(factor, 4)}


def tellerstanden(rijen: list | None, factor: float = 1.0) -> dict:
    """{moment: stand} uit statistiekrijen (`end` en `sum`), stand x factor."""
    uit = {}
    for r in rijen or []:
        eind, som = r.get("end"), r.get("sum")
        if eind is None or som is None:
            continue
        if isinstance(eind, (int, float)):
            eind = datetime.fromtimestamp(eind if eind < 1e11 else eind / 1000)
        uit[eind] = float(som) * factor
    return uit


def venster(nu: datetime, dagen: int = VENSTER_DAGEN) -> tuple[datetime, datetime]:
    """(begin, eind) van het tellervenster: hele uren tot het begin van dit uur."""
    eind = nu.replace(minute=0, second=0, microsecond=0)
    return eind - timedelta(days=dagen) - timedelta(hours=1), eind


#: v5.170.0: de standen waarin de sluimer uit het net komt (AC, 1:1); de
#: andere standen halen hem uit de cellen (inhoud, / laadrendement naar AC).
SLUIMER_UIT_NET = ("vol", "leeg")
#: Dekt de kwartierreeks minder dan dit deel van het venster: geen correctie.
SLUIMER_MIN_DEKKING = 0.25


def sluimer_vermogen(sluimer: dict | None) -> dict:
    """{stand: W} uit `accukosten.sluimerverbruik` (v5.170.0).

    Per stand de lange stilstandblokken als die betrouwbaar zijn (die zien
    ook de SoC-stap die het kwartierfilter weggooit), anders de kwartier-
    meting als die betrouwbaar is, anders het algemene gemiddelde. Nooit
    negatief."""
    sluimer = sluimer or {}
    blokken = sluimer.get("zelfontlading_blokken") or {}
    per = sluimer.get("per_stand") or {}
    algemeen = sluimer.get("gemiddeld_w")
    uit = {}
    for stand in ("sparen", "vol", "leeg", "overig"):
        for bron in (blokken.get(stand), per.get(stand)):
            if bron and bron.get("betrouwbaar") and bron.get("gemiddeld_w") is not None:
                uit[stand] = max(0.0, float(bron["gemiddeld_w"]))
                break
        else:
            if algemeen is not None:
                uit[stand] = max(0.0, float(algemeen))
    return uit


def sluimer_in_venster(reeks: list | None, van: datetime, tot: datetime, sluimer: dict | None,
                       laadrendement: float, min_soc: float, bovengrens: float) -> dict:
    """De sluimer (kWh aan de AC-kant) in het tellervenster (v5.170.0).

    Telt de stilstandkwartieren (< 50 W) per stand in [van, tot) en
    vermenigvuldigt met het gemeten vermogen per stand. Uit de cellen (sparen,
    overig) / laadrendement: die inhoud had zoveel AC gekost. Dekt de reeks
    het venster niet helemaal, dan opgeschaald naar het hele venster.
    `kwh` None = niet te bepalen (dan geen correctie)."""
    uit: dict = {"kwh": None}
    vermogen = sluimer_vermogen(sluimer)
    kwartieren = stil = 0
    uren: dict = {}
    for q in reeks or []:
        moment = _moment(str(q.get("dag")), str(q.get("tijd")))
        if moment is None or moment < van or moment + timedelta(minutes=15) > tot:
            continue
        kwartieren += 1
        if abs(q.get("accu_kwh") or 0.0) > STIL_KWH:
            continue
        stil += 1
        soort = _stilstand_soort(q, min_soc, bovengrens)
        uren[soort] = uren.get(soort, 0.0) + 0.25
    venster_kwartieren = max(1.0, (tot - van).total_seconds() / 900)
    dekking = kwartieren / venster_kwartieren
    uit.update({"dekking": round(min(1.0, dekking), 3), "stilstand_uren": round(stil / 4, 1),
                "vermogen_w": vermogen})
    if dekking < SLUIMER_MIN_DEKKING:
        uit["reden"] = f"kwartierreeks dekt {dekking * 100:.0f} % van het venster"
        return uit
    if stil and not vermogen:
        uit["reden"] = "sluimerverbruik nog niet gemeten"
        return uit
    schaal = 1.0 / min(1.0, dekking)
    per = {}
    totaal = 0.0
    for soort, u in uren.items():
        w = vermogen.get(soort, 0.0)
        kwh = u * w / 1000 * (1.0 if soort in SLUIMER_UIT_NET else 1.0 / laadrendement) * schaal
        per[soort] = {"uren": round(u * schaal, 1), "w": w, "kwh_ac": round(kwh, 3)}
        totaal += kwh
    uit.update({"kwh": totaal, "per_stand": per, "opgeschaald_met": round(schaal, 3), "reden": "ok"})
    return uit


def met_sluimer(meting: dict, reeks: list | None, sluimer: dict | None,
                min_soc: float, bovengrens: float) -> dict:
    """De meting van `rondrit_uit_meter` aangevuld met de conversie (v5.170.0).

    `rendement_totaal` = de rondrit met sluimer (weergave). `rendement` =
    `rendement_conversie` = zonder sluimer (alle beslissingen), als die
    te bepalen en plausibel (RONDRIT_MIN..MAX) is; anders blijft `rendement`
    de totale rondrit. Een meting zonder `rendement` blijft ongemoeid."""
    rt = meting.get("rendement")
    if not rt:
        return meting
    uit = dict(meting)
    uit["rendement_totaal"] = rt
    uit["rendement_voor_beslissingen"] = "totaal (met sluimer)"
    try:
        van, tot = datetime.fromisoformat(meting["van"]), datetime.fromisoformat(meting["tot"])
    except (KeyError, TypeError, ValueError):
        uit["sluimer_reden"] = "geen venster"
        return uit
    eta_l = meting.get("laadrendement_voor_inhoud") or LAADRENDEMENT_TERUGVAL
    s = sluimer_in_venster(reeks, van, tot, sluimer, eta_l, min_soc, bovengrens)
    uit["sluimer"] = s
    if s.get("kwh") is None:
        uit["sluimer_reden"] = s.get("reden")
        return uit
    noemer = meting["ac_erin_kwh"] - meting["inhoud_verandering_kwh"] / eta_l - s["kwh"]
    uit["sluimer_kwh"] = round(s["kwh"], 3)
    if noemer <= 0:
        uit["sluimer_reden"] = "sluimer groter dan wat erin ging"
        return uit
    conversie = meting["ac_eruit_kwh"] / noemer
    uit["rendement_conversie_gemeten"] = round(conversie, 4)
    if not RONDRIT_MIN <= conversie <= RONDRIT_MAX:
        uit["sluimer_reden"] = (f"conversie {conversie * 100:.1f} % buiten "
                                f"{RONDRIT_MIN * 100:.0f}-{RONDRIT_MAX * 100:.0f} %")
        return uit
    uit.update({"rendement": conversie, "rendement_conversie": conversie,
                "rendement_voor_beslissingen": "conversie (zonder sluimer)", "sluimer_reden": "ok"})
    return uit
