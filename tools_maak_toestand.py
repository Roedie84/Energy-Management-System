"""Maakt tests/fixtures/opslag_echt.json uit een echte toestand (v5.14).

Het uitvraagmechanisme (tests/test_alles_uitgevraagd.py) draait elke
entiteit en de export op een ECHTE opgeslagen toestand. Dit script maakt
die toestand.

    python3 tools_maak_toestand.py <bestand>

Twee soorten bestand:

1. Het opslagbestand zelf, uit config/.storage/ - de BESTE bron. Dat is
   precies wat de integratie bij het opstarten inleest.

2. Een diagnostiek-export - een terugval. Let op: een export is niet de
   opslag. Van de 200 bewaarde velden staan er maar een deel in, en
   sommige staan er als RAPPORT in plaats van als toestand (zo zet de
   export onder `sensor_cadence` een samenvatting). Dat is precies waar
   het mechanisme op struikelde toen het voor het eerst draaide.

Het resultaat staat in .gitignore: het is het huishoudelijk verbruik van
deze installatie, per kwartier, en hoort niet in een openbare repository.
Ontbreekt het bestand, dan slaat het deel van de toetsen met een echte
toestand over.
"""
import importlib.util
import json
import sys
from pathlib import Path

HIER = Path(__file__).parent
DOEL = HIER / "tests" / "fixtures" / "opslag_echt.json"


def _bewaarde_velden() -> set:
    pad = HIER / "custom_components" / "energy_management_system" / "const.py"
    spec = importlib.util.spec_from_file_location("const", pad)
    const = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(const)
    return set(const.PERSISTED_FIELDS)


def main(bron: str) -> None:
    ruw = json.loads(Path(bron).read_text(encoding="utf-8"))
    velden = _bewaarde_velden()
    if "version" in ruw and isinstance(ruw.get("data"), dict) and "coordinator" not in ruw.get("data", {}):
        soort = "opslagbestand"
        toestand = ruw["data"]
    elif isinstance(ruw.get("data"), dict) and "coordinator" in ruw["data"]:
        soort = "diagnostiek-export (terugval, onvolledig)"
        toestand = ruw["data"]["coordinator"]
    else:
        sys.exit("Onbekend bestand: geen opslagbestand en geen diagnostiek-export.")
    opslag = {v: toestand[v] for v in velden if v in toestand}
    DOEL.parent.mkdir(parents=True, exist_ok=True)
    DOEL.write_text(json.dumps(opslag, ensure_ascii=False, separators=(",", ":")))
    print(
        f"{soort}: {len(opslag)} van de {len(velden)} bewaarde velden, "
        f"{DOEL.stat().st_size // 1024} kB -> {DOEL.relative_to(HIER)}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
