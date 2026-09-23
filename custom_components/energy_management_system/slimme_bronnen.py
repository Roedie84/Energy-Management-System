"""Rekenlogica voor bronnen die de integratie eerder niet gebruikte (v5.14).

Gevonden door live in Home Assistant mee te kijken: entiteiten die er al
stonden, maar waar niets mee gebeurde.

- een tweede zonvoorspelling (Forecast.Solar) naast Solcast
- gemeten instraling van het KNMI-station Groenlo-Hupsel
- de gasprijs, naast de stroomprijs en de airco
- het werkelijke vermogen van de accuventilatoren

Alles hier is puur: getallen erin, een oordeel eruit. De coördinator leest
de sensoren en bewaart de reeksen; deze module rekent. Zo is het te toetsen
zonder Home Assistant, en groeit de coördinator niet verder.

Niets hiervan STUURT. De bewijsstandaard van dit project is: eerst een
bevinding, dan een meting, dan een schaduwanalyse, dan pas sturen. Dit is
de meting.
"""
from __future__ import annotations

from statistics import median

# --- verwarmen: airco tegen gas -------------------------------------------

# Nuttige warmte per kubieke meter aardgas in een HR-ketel. De onderwaarde
# van Nederlands aardgas is ongeveer 8,8 kWh/m3, en een condenserende ketel
# haalt daar bij lage retourtemperatuur ongeveer 100% van. Een ruwe maat,
# bewust afgerond: de onzekerheid in de COP van de airco is veel groter.
GAS_KWH_WARMTE_PER_M3 = 8.8

# De COP van een lucht-lucht warmtepomp daalt als het buiten kouder wordt.
# Een eenvoudige lineaire benadering tussen gangbare fabriekswaarden - geen
# meting van DEZE airco. Begrensd, want buiten dit bereik is een lijn
# onzin.
COP_BIJ_0_GRADEN = 3.0
COP_PER_GRAAD = 0.08
COP_MIN = 2.0
COP_MAX = 4.5


def cop_bij(buiten_c: float | None) -> float:
    """Geschatte COP van de airco bij deze buitentemperatuur."""
    if buiten_c is None:
        return COP_BIJ_0_GRADEN
    return max(COP_MIN, min(COP_MAX, COP_BIJ_0_GRADEN + COP_PER_GRAAD * buiten_c))


def verwarmingsadvies(
    gasprijs_m3: float | None,
    stroomprijs_kwh: float | None,
    buiten_c: float | None,
) -> dict:
    """Kost een kWh warmte minder met de airco of met de cv?

    Bij de prijzen van september 2026 - gas 1,74 euro per m3, stroom rond
    de 0,24 - kost warmte uit gas ongeveer 0,20 euro per kWh en uit de
    airco ongeveer 0,08. De airco wint dan ruim, en blijft winnen tot de
    stroomprijs boven het omslagpunt komt.
    """
    if gasprijs_m3 is None or stroomprijs_kwh is None or gasprijs_m3 <= 0:
        return {
            "advies": None,
            "reden": "Geen gasprijs of stroomprijs beschikbaar.",
        }
    cop = cop_bij(buiten_c)
    gas_per_kwh = gasprijs_m3 / GAS_KWH_WARMTE_PER_M3
    airco_per_kwh = stroomprijs_kwh / cop
    omslag = gas_per_kwh * cop
    advies = "airco" if airco_per_kwh < gas_per_kwh else "cv"
    besparing = gas_per_kwh - airco_per_kwh
    return {
        "advies": advies,
        "cop_geschat": round(cop, 2),
        "gas_eur_per_kwh_warmte": round(gas_per_kwh, 4),
        "airco_eur_per_kwh_warmte": round(airco_per_kwh, 4),
        "omslag_stroomprijs_eur": round(omslag, 4),
        "besparing_eur_per_kwh_warmte": round(besparing, 4),
        "reden": (
            f"Warmte kost nu {airco_per_kwh:.3f} euro per kWh met de airco "
            f"(COP {cop:.1f} bij {buiten_c if buiten_c is not None else '?'} "
            f"graden) tegen {gas_per_kwh:.3f} met de cv. Pas boven een "
            f"stroomprijs van {omslag:.2f} euro wint de cv."
            if advies == "airco"
            else f"De stroom is nu zo duur dat de cv goedkoper verwarmt: "
            f"{gas_per_kwh:.3f} tegen {airco_per_kwh:.3f} euro per kWh."
        ),
    }


# --- twee zonvoorspellingen -----------------------------------------------

# Vanaf welk verschil tussen de twee voorspellingen een dag als onzeker
# telt. Een kwart: kleiner is binnen wat twee modellen normaal uiteenlopen.
PV_ENSEMBLE_ONEENS_PROCENT = 25.0

# Hoeveel volledige dagen er nodig zijn voordat de vergelijking iets zegt.
PV_ENSEMBLE_MIN_DAGEN = 7


def oneens_procent(a: float | None, b: float | None) -> float | None:
    """Hoeveel procent twee voorspellingen uiteenlopen, t.o.v. hun midden."""
    if a is None or b is None:
        return None
    midden = (a + b) / 2
    if midden <= 0:
        return None
    return round(100 * abs(a - b) / midden, 1)


def pv_ensemble_analyse(dagen: list[dict]) -> dict:
    """Welke voorspelling zat dichter bij, en voorspelt onenigheid een fout?

    `dagen`: per voltooide dag `solcast_kwh`, `tweede_kwh` en `werkelijk_kwh`
    - de twee voorspellingen zoals ze 's ochtends stonden, en de opbrengst.
    """
    bruikbaar = [
        d
        for d in dagen
        if d.get("solcast_kwh") is not None
        and d.get("tweede_kwh") is not None
        and d.get("werkelijk_kwh") is not None
        and d["werkelijk_kwh"] > 0
    ]
    if len(bruikbaar) < PV_ENSEMBLE_MIN_DAGEN:
        return {
            "dagen": len(bruikbaar),
            "oordeel": (
                f"{len(bruikbaar)} van de {PV_ENSEMBLE_MIN_DAGEN} dagen met "
                "beide voorspellingen en een opbrengst. Nog te weinig om te "
                "zeggen welke beter is."
            ),
        }

    def fout(voorspeld: float, werkelijk: float) -> float:
        return 100 * abs(voorspeld - werkelijk) / werkelijk

    solcast = [fout(d["solcast_kwh"], d["werkelijk_kwh"]) for d in bruikbaar]
    tweede = [fout(d["tweede_kwh"], d["werkelijk_kwh"]) for d in bruikbaar]
    gemiddeld = [
        fout((d["solcast_kwh"] + d["tweede_kwh"]) / 2, d["werkelijk_kwh"])
        for d in bruikbaar
    ]
    onzeker, zeker = [], []
    for d, f in zip(bruikbaar, solcast):
        o = oneens_procent(d["solcast_kwh"], d["tweede_kwh"])
        (onzeker if o is not None and o >= PV_ENSEMBLE_ONEENS_PROCENT else zeker).append(f)
    beste = min(
        ("solcast", median(solcast)),
        ("tweede", median(tweede)),
        ("gemiddelde", median(gemiddeld)),
        key=lambda x: x[1],
    )[0]
    voorspelt_fout = (
        bool(onzeker) and bool(zeker) and median(onzeker) > median(zeker) * 1.5
    )
    return {
        "dagen": len(bruikbaar),
        "mediaan_fout_solcast_procent": round(median(solcast), 1),
        "mediaan_fout_tweede_procent": round(median(tweede), 1),
        "mediaan_fout_gemiddelde_procent": round(median(gemiddeld), 1),
        "beste": beste,
        "dagen_oneens": len(onzeker),
        "fout_solcast_als_oneens_procent": round(median(onzeker), 1) if onzeker else None,
        "fout_solcast_als_eens_procent": round(median(zeker), 1) if zeker else None,
        "onenigheid_voorspelt_fout": voorspelt_fout,
        "oordeel": (
            f"Over {len(bruikbaar)} dagen zat '{beste}' het dichtst bij. "
            + (
                "Op dagen dat de twee het oneens waren, zat Solcast er "
                "duidelijk verder naast - onenigheid is dus een bruikbaar "
                "teken van een onzekere dag."
                if voorspelt_fout
                else "Onenigheid tussen de twee zegt (nog) niet dat Solcast "
                "er verder naast zit."
            )
        ),
    }


# --- gemeten instraling ---------------------------------------------------

INSTRALING_MIN_WM2 = 150.0
INSTRALING_MIN_ZONHOOGTE = 10.0
INSTRALING_AZIMUT_VAK = 20
INSTRALING_MONSTERS_PER_VAK = 200
INSTRALING_MIN_MONSTERS = 20


def azimut_vak(azimut: float) -> int:
    """Het vak (in hele graden, veelvoud van INSTRALING_AZIMUT_VAK)."""
    return int(azimut // INSTRALING_AZIMUT_VAK) * INSTRALING_AZIMUT_VAK


def instraling_telt(
    instraling_wm2: float | None,
    zonhoogte: float | None,
    pv_w: float | None,
) -> bool:
    """Is dit moment bruikbaar om de panelen tegen het licht te leggen?"""
    return (
        instraling_wm2 is not None
        and zonhoogte is not None
        and pv_w is not None
        and instraling_wm2 >= INSTRALING_MIN_WM2
        and zonhoogte >= INSTRALING_MIN_ZONHOOGTE
        and pv_w >= 0
    )


def instraling_analyse(verhoudingen: dict) -> dict:
    """Levert het dak per zonrichting wat het licht belooft?

    `verhoudingen`: per azimutvak een lijst van PV-vermogen gedeeld door de
    gemeten instraling. Normaal op het beste vak: dat is wat het dak kan
    als niets in de weg staat.

    Het verschil met de bestaande beschaduwingsanalyse: die legt de
    opbrengst naast een VOORSPELLING, en een voorspelfout lijkt daar op
    schaduw. Dit legt hem naast gemeten licht.
    """
    # Na het bewaren komen de sleutels als tekst terug; hier gelijktrekken.
    reeksen = {int(vak): reeks for vak, reeks in (verhoudingen or {}).items()}
    medianen = {
        vak: median(reeks)
        for vak, reeks in reeksen.items()
        if len(reeks) >= INSTRALING_MIN_MONSTERS
    }
    if not medianen:
        totaal = sum(len(r) for r in reeksen.values())
        return {
            "vakken": {},
            "oordeel": (
                f"{totaal} metingen, nog geen richting met "
                f"{INSTRALING_MIN_MONSTERS}. Alleen momenten met instraling "
                f"boven {INSTRALING_MIN_WM2:.0f} W/m2 en de zon boven "
                f"{INSTRALING_MIN_ZONHOOGTE:.0f} graden tellen."
            ),
        }
    beste = max(medianen.values()) or 1.0
    vakken = {
        vak: {
            "procent_van_beste": round(100 * m / beste, 1),
            "metingen": len(reeksen[vak]),
        }
        for vak, m in sorted(medianen.items())
    }
    zwak = [vak for vak, v in vakken.items() if v["procent_van_beste"] < 60]
    return {
        "vakken": vakken,
        "zwakke_richtingen": zwak,
        "oordeel": (
            (
                "Bij gemeten licht blijven deze richtingen ver achter: "
                + ", ".join(f"{v} graden" for v in zwak)
                + ". Dat is geen voorspelfout maar iets wat het licht "
                "tegenhoudt."
            )
            if zwak
            else "Geen richting blijft ver achter bij het gemeten licht."
        ),
    }


# --- de accuventilatoren --------------------------------------------------

VENTILATOR_AAN_W = 5.0
VENTILATOR_HISTORIE_DAGEN = 40


def ventilator_overzicht(
    per_dag: dict,
    vermogens_aan: list[float],
    stroomprijs_kwh: float | None,
) -> dict:
    """Wat de accukoeling werkelijk verbruikt.

    Aanleiding: de stekker van de ventilatoren stond op 325 kWh, terwijl de
    koellogica rekende met "een paar watt ventilator". Alleen de
    ventilatoren hangen aan die stekker, dus dat verbruik is echt.
    """
    dagen = sorted(per_dag or {})
    if not dagen:
        return {"oordeel": "Nog geen ventilatorverbruik gemeten."}
    kwh = [per_dag[d] for d in dagen]
    gem = sum(kwh) / len(kwh)
    vermogen = round(median(vermogens_aan), 1) if vermogens_aan else None
    prijs = stroomprijs_kwh or 0.0
    return {
        "dagen": len(dagen),
        "gemiddeld_kwh_per_dag": round(gem, 3),
        "vermogen_aan_w": vermogen,
        "kosten_eur_per_jaar": round(gem * 365 * prijs, 2) if prijs else None,
        "oordeel": (
            f"De ventilatoren verbruiken gemiddeld {gem:.2f} kWh per dag"
            + (f", {vermogen:.0f} W als ze draaien" if vermogen else "")
            + (f" - ongeveer {gem * 365 * prijs:.0f} euro per jaar." if prijs else ".")
        ),
    }


# --- gemiddelde prijzen per periode ---------------------------------------


def _deel(teller: float | None, noemer: float | None) -> float | None:
    """Gemiddelde prijs, of None als een van beide ontbreekt."""
    if teller is None or not noemer:
        return None
    return round(teller / noemer, 4)


def prijzen_per_periode(perioden: dict) -> dict:
    """Gemiddelde in- en verkoopprijzen per periode, incl en excl btw.

    `perioden`: de optelling per vandaag/week/maand/jaar/contractjaar, met
    per periode de bedragen (inkoop_eur, teruglever_eur, gas_eur) en de
    hoeveelheden (import_kwh, export_kwh, gas_m3).

    Het verschil tussen incl en excl is bij dynamische tarieven geen vast
    percentage maar een vast BEDRAG per kWh - energiebelasting plus btw.
    Gemeten op 23 september: 0,3494 tegen 0,2386 euro per kWh. Bij een lage
    prijs valt er dus verhoudingsgewijs veel meer weg, en daarom staan
    beide er los bij in plaats van één met een omrekening.
    """
    uit = {}
    for naam, p in (perioden or {}).items():
        if not isinstance(p, dict):
            continue
        uit[naam] = {
            "dagen": p.get("dagen"),
            "van": p.get("van"),
            "inkoop_eur_per_kwh": _deel(p.get("inkoop_eur"), p.get("import_kwh")),
            "inkoop_eur_per_kwh_excl": _deel(
                p.get("inkoop_eur_excl"), p.get("import_kwh")
            ),
            "teruglever_eur_per_kwh": _deel(
                p.get("teruglever_eur"), p.get("export_kwh")
            ),
            "teruglever_eur_per_kwh_excl": _deel(
                p.get("teruglever_eur_excl"), p.get("export_kwh")
            ),
            "gas_eur_per_m3": _deel(p.get("gas_eur"), p.get("gas_m3")),
            "gas_eur_per_m3_excl": _deel(p.get("gas_eur_excl"), p.get("gas_m3")),
            "inkoop_eur": p.get("inkoop_eur"),
            "teruglever_eur": p.get("teruglever_eur"),
            "gas_eur": p.get("gas_eur"),
            "gas_m3": p.get("gas_m3"),
        }
    return uit


def prijzen_per_uur(kwartierprijzen: list, belastingdeel_eur: float | None) -> dict:
    """De gemiddelde prijs per uur van vandaag, incl en excl btw.

    `kwartierprijzen`: paren (moment, prijs incl. belasting en btw) - de
    prijs waarmee de integratie ook stuurt.

    Het bedrag dat er voor excl btw af gaat is per kWh gelijk, en wordt
    gemeten uit de dagbedragen van de leverancier: het verschil tussen de
    gemiddelde prijs incl en excl van vandaag. Is dat er niet, dan blijft
    de excl-kolom leeg in plaats van dat er een percentage wordt geraden.
    """
    per_uur: dict[int, list] = {}
    for moment, prijs in kwartierprijzen or []:
        if prijs is None:
            continue
        per_uur.setdefault(getattr(moment, "hour", None), []).append(prijs)
    uit = {}
    for uur in sorted(u for u in per_uur if u is not None):
        gemiddeld = sum(per_uur[uur]) / len(per_uur[uur])
        uit[uur] = {
            "eur_per_kwh": round(gemiddeld, 4),
            "eur_per_kwh_excl": (
                round(gemiddeld - belastingdeel_eur, 4)
                if belastingdeel_eur is not None
                else None
            ),
            "kwartieren": len(per_uur[uur]),
        }
    return uit
