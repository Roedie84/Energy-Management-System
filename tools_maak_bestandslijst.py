"""Genereert `bestandscontrole.json`: een hash per bestand.

Wordt door de toetsen aangeroepen, zodat de lijst niet kan verouderen.
"""
import hashlib
import json
import pathlib

MAP = pathlib.Path(__file__).parent / "custom_components" / "energy_management_system"
UITGESLOTEN = {"bestandscontrole.json"}


def bereken() -> dict:
    uit = {}
    for pad in sorted(MAP.rglob("*")):
        if not pad.is_file() or "__pycache__" in pad.parts:
            continue
        naam = pad.relative_to(MAP).as_posix()
        if naam in UITGESLOTEN:
            continue
        uit[naam] = hashlib.sha256(pad.read_bytes()).hexdigest()[:16]
    return uit


if __name__ == "__main__":
    (MAP / "bestandscontrole.json").write_text(
        json.dumps(bereken(), indent=2, sort_keys=True) + "\n"
    )
    print(f"{len(bereken())} bestanden vastgelegd")
