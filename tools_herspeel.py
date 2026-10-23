"""Echte dagen opnieuw afspelen - regressietest in euro's (v5.123.0, punt 5).

    python3 tools_herspeel.py <bron.json> [--storage <map>] [--dagen 40]
                              [--uit resultaat.json] [--vergelijk oud.json]

<bron.json> is het opslagbestand van de integratie (config/.storage/...) of
een diagnostiek-export: alles met een `dagverloop` erin. Met --storage (de
map config/.storage) leest hij ook de kwartierenergie uit de meetlaag
(energy_management_system_meetlog_kwartier_JJJJMMDD); zonder rekent hij met
het vermogen uit het dagverloop.

Werkwijze voor-en-na: draai dit op dezelfde bron met de code van vóór een
wijziging (--uit oud.json) en daarna met de nieuwe code (--vergelijk
oud.json). Het verschil staat per strategie en per dag; negatief = goedkoper.

De modelwaarden (capaciteit, rendement, slijtage, vermogens) komen uit de
export (`herspeel.model`) als die er is, anders uit de opties hieronder.
Draait zonder Home Assistant. Zie `herspeel.py` voor wat wel en niet
opnieuw wordt afgespeeld.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import types
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).parent
PAKKET = HIER / "custom_components" / "energy_management_system"


def _laad_pure_modules():
    """De zuivere modules laden zonder het pakket (dat Home Assistant importeert)."""
    pkg = types.ModuleType("ems_puur")
    pkg.__path__ = [str(PAKKET)]
    sys.modules["ems_puur"] = pkg
    return importlib.import_module("ems_puur.herspeel"), importlib.import_module("ems_puur.kwartierenergie")


def zoek(boom, sleutel):
    """De eerste waarde onder `sleutel`, waar ook in de boom."""
    if isinstance(boom, dict):
        if sleutel in boom and isinstance(boom[sleutel], dict):
            return boom[sleutel]
        for v in boom.values():
            gevonden = zoek(v, sleutel)
            if gevonden is not None:
                return gevonden
    elif isinstance(boom, list):
        for v in boom:
            gevonden = zoek(v, sleutel)
            if gevonden is not None:
                return gevonden
    return None


def meetlaag_uit_opslag(map_: Path, dagen: list[str], kwartierenergie) -> dict:
    """Per dag per 'HH:MM': huis, zon en accu uit de bewaarde meetlaag."""
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Amsterdam")
    except Exception:  # noqa: BLE001
        tz = None
    uit: dict = {}
    for dag in dagen:
        pad = map_ / f"energy_management_system_meetlog_kwartier_{dag.replace('-', '')}"
        if not pad.exists():
            continue
        inhoud = json.loads(pad.read_text(encoding="utf-8"))
        regels = (inhoud.get("data") or inhoud).get("regels") or []
        per = {}
        for kort in regels:
            try:
                r = kwartierenergie.uitpakken(kort)
            except Exception:  # noqa: BLE001
                continue
            if r.get("quality") not in ("measured", "partially_estimated"):
                continue
            if None in (r.get("house_kwh"), r.get("pv_kwh"), r.get("battery_out_kwh"), r.get("battery_in_kwh")):
                continue
            moment = datetime.fromisoformat(r["kwartier"])
            if tz is not None and moment.tzinfo is not None:
                moment = moment.astimezone(tz)
            per[moment.strftime("%H:%M")] = {"huis_kwh": r["house_kwh"], "pv_kwh": r["pv_kwh"],
                                             "accu_kwh": r["battery_out_kwh"] - r["battery_in_kwh"]}
        uit[dag] = per
    return uit


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("bron")
    p.add_argument("--storage", help="de map config/.storage, voor de meetlaag")
    p.add_argument("--dagen", type=int, default=40)
    p.add_argument("--uit", help="resultaat als JSON wegschrijven")
    p.add_argument("--vergelijk", help="een eerder resultaat (JSON) om mee te vergelijken")
    p.add_argument("--capaciteit-kwh", type=float, default=9.8)
    p.add_argument("--min-soc", type=float, default=15.0)
    p.add_argument("--laad-kw", type=float, default=2.4)
    p.add_argument("--ontlaad-kw", type=float, default=2.4)
    p.add_argument("--rendement", type=float, default=0.84)
    p.add_argument("--slijtage-eur", type=float, default=0.04)
    a = p.parse_args(argv)

    H, kwartierenergie = _laad_pure_modules()
    bron = json.loads(Path(a.bron).read_text(encoding="utf-8"))
    verloop = zoek(bron, "dagverloop")
    if not verloop:
        print("Geen dagverloop gevonden in de bron.", file=sys.stderr)
        return 2
    vandaag = datetime.now().date().isoformat()
    dagen = [d for d in sorted(verloop) if d < vandaag][-a.dagen:]
    model = dict(capaciteit_kwh=a.capaciteit_kwh, min_soc_procent=a.min_soc, laad_kw=a.laad_kw,
                 ontlaad_kw=a.ontlaad_kw, rendement=a.rendement, slijtage_eur=a.slijtage_eur)
    uit_export = (zoek(bron, "herspeel") or {}).get("model")
    if isinstance(uit_export, dict):
        model.update({k: v for k, v in uit_export.items() if k in model and v is not None})
    gemeten = meetlaag_uit_opslag(Path(a.storage), dagen, kwartierenergie) if a.storage else {}
    resultaat = H.herspeel({d: verloop[d] for d in dagen}, gemeten, dagen=a.dagen, **model)
    resultaat["bron"] = str(a.bron)
    print(json.dumps(resultaat["samenvatting"], indent=2, ensure_ascii=False))
    if a.uit:
        Path(a.uit).write_text(json.dumps(resultaat, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.vergelijk:
        oud = json.loads(Path(a.vergelijk).read_text(encoding="utf-8"))
        print(json.dumps(H.vergelijk(oud, resultaat), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
