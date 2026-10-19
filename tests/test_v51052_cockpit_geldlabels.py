"""v5.105.2 - duidelijker wat de bedragen in Geld wel en niet tellen.

Gevraagd 19-10: "Wordt in deze kosten ook meegenomen de besparing omdat de
accu het huis voedt....." en "Ja graag duidelijker". De besparing vergelijkt
met een huis zonder accu (alles, ook het huis voeden in de stand slim); de
drie regels eronder alleen wat het EMS actief doet.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def test_de_besparing_zegt_zonder_accu():
    assert '"t.o.v. zonder accu"' in JS
    assert "t.o.v. zonder sturing\"" not in JS and ", zonder sturing ${" not in JS


def test_de_regels_heten_actieve_sturing():
    geld = JS.split("  _geld() {")[1].split("\n  }\n")[0]
    for tekst in ("Ontladen in dure kwartieren", "Laden uit het net", "Actieve sturing netto",
                  "alleen wat het EMS zelf ingrijpt"):
        assert tekst in geld
    assert "Accu netto" not in geld
