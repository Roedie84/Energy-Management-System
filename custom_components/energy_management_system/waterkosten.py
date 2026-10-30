"""Wat kost een tapmoment? (v5.150.0)

Gevraagd 30-10: "Hoelang duurt een gemiddelde douchebeurt bij ons en wat
kost dit" en "Neem je de waterprijzen ook al in het EMS mee?" - nee: EMS
herkende de douche wel, maar zette er geen bedrag bij.

Een douche kost water én gas. Het water is liters maal de waterprijs. Het
gas wordt GEMETEN: de gasmeterstand bij het begin van het tappen tegen de
eerste stand ná het einde. Een combiketel stopt met verwarmen zolang hij
warm water maakt, dus wat de meter in die tijd optelt is het warme water.
De meterstand loopt een paar minuten achter (een slimme meter geeft elke
vijf minuten een gasstand), vandaar het wachten op een stand na het
einde.

Geen gasmeter, of geen stand binnen de wachttijd? Dan een schatting:
douchewater van 38 °C uit leidingwater van 10 °C, met een ketelrendement
van 90 %. Voor 140 liter geeft dat 0,58 m³; gemeten was het op 29-10
0,51 m³ - in de buurt, maar de meting gaat voor.

Losse functies zonder Home Assistant, zodat ze los te toetsen zijn.
"""
from __future__ import annotations

from datetime import datetime, timedelta

# Vitens 2026, inclusief btw: € 1,34 drinkwater + € 0,48 belasting op
# leidingwater per m³. Instelbaar, want elk waterbedrijf rekent anders.
WATERPRIJS_STANDAARD_EUR_PER_M3 = 1.82

# Bronnen waarbij de ketel warm water maakte.
WARM_WATER_BRONNEN = ("douche", "warm water kort")

# Schatting zonder gasmeter.
DOUCHE_TEMPERATUUR_C = 38.0
LEIDINGWATER_TEMPERATUUR_C = 10.0
GAS_ENERGIE_MJ_PER_M3 = 31.65
KETELRENDEMENT = 0.90
WATER_MJ_PER_LITER_PER_GRAAD = 0.004186

# Zo lang na het einde van het tappen wachten op een nieuwe gasstand.
# Ruim, want een dagteller van de leverancier werkt soms per uur bij.
GAS_WACHTTIJD_MINUTEN = 75

# Een meting die hier boven komt, is geen tapmoment maar iets anders
# (verwarming, een herstart van de meter).
GAS_MAX_M3_PER_LITER = 0.012

# Hoeveel douchebeurten bewaard blijven voor het overzicht.
DOUCHE_HISTORIE_LENGTE = 150


def schat_gas_m3(liter: float | None) -> float | None:
    """Gas voor warm water, geschat uit het volume."""
    if liter is None or liter <= 0:
        return None
    energie_mj = (
        liter
        * (DOUCHE_TEMPERATUUR_C - LEIDINGWATER_TEMPERATUUR_C)
        * WATER_MJ_PER_LITER_PER_GRAAD
    )
    return energie_mj / (GAS_ENERGIE_MJ_PER_M3 * KETELRENDEMENT)


def gemeten_gas_m3(
    start_m3: float | None, eind_m3: float | None, liter: float | None
) -> float | None:
    """Het gemeten gas, of None als de meting niet te vertrouwen is."""
    if start_m3 is None or eind_m3 is None:
        return None
    verschil = eind_m3 - start_m3
    if verschil < 0:
        # Een dagteller die om middernacht naar nul ging.
        return None
    if liter and verschil > liter * GAS_MAX_M3_PER_LITER:
        return None
    return verschil


def kosten(
    liter: float | None,
    waterprijs_eur_per_m3: float | None,
    gas_m3: float | None = None,
    gasprijs_eur_per_m3: float | None = None,
) -> dict:
    """Bedragen bij een tapmoment, afgerond voor het tonen."""
    water_eur = (
        liter / 1000 * waterprijs_eur_per_m3
        if liter is not None and waterprijs_eur_per_m3 is not None
        else None
    )
    gas_eur = (
        gas_m3 * gasprijs_eur_per_m3
        if gas_m3 is not None and gasprijs_eur_per_m3 is not None
        else None
    )
    delen = [w for w in (water_eur, gas_eur) if w is not None]
    return {
        "water_eur": round(water_eur, 3) if water_eur is not None else None,
        "gas_m3": round(gas_m3, 3) if gas_m3 is not None else None,
        "gas_eur": round(gas_eur, 3) if gas_eur is not None else None,
        "kosten_eur": round(sum(delen), 2) if delen else None,
    }


def _moment(waarde) -> datetime | None:
    if isinstance(waarde, datetime):
        return waarde
    try:
        return datetime.fromisoformat(str(waarde))
    except (TypeError, ValueError):
        return None


def douche_overzicht(douches: list[dict], nu: datetime, dagen: int = 30) -> dict:
    """Gemiddelde duur en kosten per douchebeurt, en het verloop per week."""
    grens = nu - timedelta(days=dagen)
    binnen = []
    for d in douches or []:
        moment = _moment(d.get("gestart"))
        if moment is None:
            continue
        if moment.tzinfo is None and nu.tzinfo is not None:
            moment = moment.replace(tzinfo=nu.tzinfo)
        if moment >= grens:
            binnen.append((moment, d))
    if not binnen:
        return {"beschikbaar": False, "dagen": dagen, "aantal": 0}

    def gem(sleutel, rij):
        waarden = [d.get(sleutel) for _, d in rij if d.get(sleutel) is not None]
        return sum(waarden) / len(waarden) if waarden else None

    weken: dict[str, list] = {}
    for moment, d in binnen:
        maandag = (moment - timedelta(days=moment.weekday())).date().isoformat()
        weken.setdefault(maandag, []).append((moment, d))
    per_week = []
    for maandag in sorted(weken):
        rij = weken[maandag]
        duur = gem("duur_minuten", rij)
        geld = gem("kosten_eur", rij)
        per_week.append(
            {
                "week_van": maandag,
                "aantal": len(rij),
                "gem_minuten": round(duur, 1) if duur is not None else None,
                "gem_eur": round(geld, 2) if geld is not None else None,
            }
        )

    duur = gem("duur_minuten", binnen)
    liter = gem("liter", binnen)
    geld = gem("kosten_eur", binnen)
    gas = gem("gas_m3", binnen)
    totaal = sum(d.get("kosten_eur") or 0 for _, d in binnen)
    laatste_moment, laatste = max(binnen, key=lambda x: x[0])
    gemeten = sum(1 for _, d in binnen if d.get("gas_bron") == "gasmeter")
    return {
        "beschikbaar": True,
        "dagen": dagen,
        "aantal": len(binnen),
        "per_dag": round(len(binnen) / dagen, 2),
        "gem_minuten": round(duur, 1) if duur is not None else None,
        "gem_liter": round(liter, 1) if liter is not None else None,
        "gem_gas_m3": round(gas, 3) if gas is not None else None,
        "gem_eur": round(geld, 2) if geld is not None else None,
        "totaal_eur": round(totaal, 2),
        "gas_gemeten": gemeten,
        "laatste": {
            "gestart": laatste_moment.isoformat(),
            "duur_minuten": laatste.get("duur_minuten"),
            "liter": laatste.get("liter"),
            "kosten_eur": laatste.get("kosten_eur"),
        },
        "per_week": per_week,
    }
