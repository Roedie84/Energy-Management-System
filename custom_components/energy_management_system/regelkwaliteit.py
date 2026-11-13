"""Hoe goed houdt de accu de netmeter op nul? (v5.232.0)

Gevraagd door Ruud 13-11 ("Hoe goed is de 0 op de meter regeling?", punt 2
akkoord): per dag bijhouden wat er over de meter gaat terwijl de accu het
huis volgt, zodat de dagcontrole ziet als de regeling slechter wordt
(bijvoorbeeld na een update van de Zendure). Alleen meten.

Meting 10 t/m 13-11 (11 regeluren): zonder Quooker gemiddeld +7 W op de
meter; met de Quooker actief +102 W, omdat de regelsensor de Quooker-piek
bewust wegfiltert en de pulsen (10 s op 2,1 kW) korter zijn dan de reactie
van de Zendure. Daarom twee bakken: `rustig` en `quooker`.

Een monster telt voor de tijd tot het volgende monster (hooguit MAX_GAT_S),
in de bak die bij het monster hoorde. "Regelend" bepaalt de aanroeper: de
stand is smart en de accu ontlaadt tussen ACCU_MIN_W en ACCU_MAX_W (dus niet
leeg, niet vol en niet op zijn maximum).

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

#: Een gat tussen twee metingen telt hooguit zo lang mee.
MAX_GAT_S = 30.0
#: Vanaf dit vermogen telt de Quooker als actief ...
QUOOKER_AAN_W = 100.0
#: ... en zo lang erna nog (de accu herstelt dan van de puls).
QUOOKER_NASLEEP_S = 30.0
#: De accu volgt het huis als hij tussen deze grenzen ontlaadt.
ACCU_MIN_W = 30.0
ACCU_MAX_W = 2300.0
#: Zoveel afgesloten dagen blijven bewaard.
DAGEN_BEWAARD = 14
BAKKEN = ("rustig", "quooker")


def _lege_bak() -> dict:
    return {"s": 0.0, "afname_wh": 0.0, "teruglevering_wh": 0.0}


def lege_dag(dag: str) -> dict:
    return {"dag": dag, **{bak: _lege_bak() for bak in BAKKEN}}


def is_regelend(stand, accu_ontlaad_w) -> bool:
    """Volgt de accu nu het huis? `accu_ontlaad_w`: + is ontladen."""
    if stand != "smart" or not isinstance(accu_ontlaad_w, (int, float)):
        return False
    return ACCU_MIN_W <= accu_ontlaad_w <= ACCU_MAX_W


def verwerk(staat: dict | None, vorige: dict | None, *, nu_ts: float, dag: str,
            p1_w, regelend: bool, quooker_w) -> tuple[dict, dict]:
    """Verwerkt een meting. Geeft (bewaarde staat, het monster voor de volgende keer).

    `staat` = {"vandaag": dagregel, "dagen": [afgesloten dagregels]} (wordt
    bewaard); `vorige` = het vorige monster (niet bewaard: na een herstart
    begint de eerste meting zonder voorganger).
    """
    staat = staat if isinstance(staat, dict) else {}
    vandaag = staat.get("vandaag") if isinstance(staat.get("vandaag"), dict) else None
    dagen = [d for d in (staat.get("dagen") or []) if isinstance(d, dict)]
    if vandaag is None:
        vandaag = lege_dag(dag)
    for bak in BAKKEN:
        if not isinstance(vandaag.get(bak), dict):
            vandaag[bak] = _lege_bak()
    # Het vorige monster gold tot nu; het telt bij de dag waarin het viel.
    if isinstance(vorige, dict) and vorige.get("regelend") and isinstance(vorige.get("w"), (int, float)):
        t_vorige = vorige.get("t")
        dt_s = min(max(nu_ts - float(t_vorige), 0.0), MAX_GAT_S) if isinstance(t_vorige, (int, float)) else 0.0
        if dt_s > 0 and vorige.get("dag") == vandaag.get("dag"):
            bak = vandaag[vorige.get("bak") if vorige.get("bak") in BAKKEN else "rustig"]
            wh = float(vorige["w"]) * dt_s / 3600
            bak["s"] += dt_s
            if wh >= 0:
                bak["afname_wh"] += wh
            else:
                bak["teruglevering_wh"] -= wh
    if vandaag.get("dag") != dag:
        if any(vandaag[bak]["s"] > 0 for bak in BAKKEN):
            dagen = [d for d in dagen if d.get("dag") != vandaag.get("dag")] + [vandaag]
        dagen = sorted(dagen, key=lambda d: str(d.get("dag")))[-DAGEN_BEWAARD:]
        vandaag = lege_dag(dag)
    quooker_aan = isinstance(quooker_w, (int, float)) and quooker_w >= QUOOKER_AAN_W
    laatst = nu_ts if quooker_aan else (vorige or {}).get("quooker_t")
    in_nasleep = isinstance(laatst, (int, float)) and 0 <= nu_ts - laatst <= QUOOKER_NASLEEP_S
    monster = {
        "t": nu_ts, "dag": dag,
        "w": float(p1_w) if isinstance(p1_w, (int, float)) else None,
        "regelend": bool(regelend),
        "bak": "quooker" if (quooker_aan or in_nasleep) else "rustig",
        "quooker_t": laatst,
    }
    return {"vandaag": vandaag, "dagen": dagen}, monster


def _bak_samenvatting(bak: dict) -> dict:
    s = float(bak.get("s") or 0.0)
    afname, terug = float(bak.get("afname_wh") or 0.0), float(bak.get("teruglevering_wh") or 0.0)
    return {
        "uren": round(s / 3600, 2),
        "afname_wh": round(afname, 1),
        "teruglevering_wh": round(terug, 1),
        "gemiddeld_w": round((afname - terug) / (s / 3600), 1) if s >= 60 else None,
    }


def dag_samenvatting(dagregel: dict | None) -> dict | None:
    """Een dagregel in leesbare vorm, met het totaal erbij."""
    if not isinstance(dagregel, dict):
        return None
    uit = {"dag": dagregel.get("dag")}
    totaal = _lege_bak()
    for bak in BAKKEN:
        regel = dagregel.get(bak) if isinstance(dagregel.get(bak), dict) else _lege_bak()
        uit[bak] = _bak_samenvatting(regel)
        for veld in totaal:
            totaal[veld] += float(regel.get(veld) or 0.0)
    uit["totaal"] = _bak_samenvatting(totaal)
    return uit


def overzicht(staat: dict | None) -> dict:
    """Vandaag, gisteren en de bewaarde dagen (voor sensor en diagnose)."""
    staat = staat if isinstance(staat, dict) else {}
    dagen = [dag_samenvatting(d) for d in (staat.get("dagen") or []) if isinstance(d, dict)]
    return {
        "vandaag": dag_samenvatting(staat.get("vandaag")),
        "gisteren": dagen[-1] if dagen else None,
        "dagen": dagen,
        "toelichting": (
            "Wat er over de netmeter gaat terwijl de accu het huis volgt (stand smart, "
            f"ontlading {ACCU_MIN_W:.0f}-{ACCU_MAX_W:.0f} W). 'quooker' = de Quooker was aan of "
            f"korter dan {QUOOKER_NASLEEP_S:.0f} s uit: die piek volgt de accu bewust niet. "
            "Referentie 10 t/m 13-11: rustig +7 W, quooker +102 W."
        ),
    }
