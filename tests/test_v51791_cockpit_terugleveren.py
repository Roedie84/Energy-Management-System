"""v5.179.1: zon terugleveren heet in de cockpit ook zo.

Gemeld 04-11 09:30 (screenshot): de Vooruitblik toonde 'Handmatig · in rust' voor
de kwartieren waarin het waardeplan de zon terug laat leveren
(modus 'manual (terugleveren)'), en de grafiek kleurde ze als rust.
"""
import json
import subprocess
from pathlib import Path

import custom_components.energy_management_system as pkg

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _const(naam):
    regels = JS.splitlines()
    begin = next(i for i, r in enumerate(regels) if r.startswith(f"const {naam} = "))
    if regels[begin].rstrip().endswith(";"):
        return regels[begin] + "\n"
    eind = next(i for i in range(begin, len(regels)) if regels[i] in ("};", "];"))
    return "\n".join(regels[begin:eind + 1]) + "\n"


def _node(expr):
    code = "".join(_const(n) for n in ("STREEP", "hoofd", "MODI", "modus", "getal", "num", "DOEN", "doen"))
    uit = subprocess.run(["node", "-e", code + f"console.log(JSON.stringify({expr}));"],
                         capture_output=True, text=True, check=True)
    return json.loads(uit.stdout)


def test_modus_terugleveren():
    assert _node('modus("manual (terugleveren)").label') == "Zon terugleveren"
    assert _node('modus("manual (laden)").k') == "laden"
    assert _node('modus("manual").label') == "Handmatig"


def test_grafiek_kleurt_terugleveren_apart():
    assert _node('doen({modus: "manual (terugleveren)", accu_w: 0})') == "terug"
    assert _node('doen({modus: "smart", accu_w: -600})') == "zon"


def test_vooruitblik_toont_terugleververmogen():
    vb = JS.split("  _vooruitblik(rijen, tijden) {")[1].split("  /* v5.146.0")[0]
    assert 'b.k === "terug"' in vb and "levert ${" in vb
    assert "b.net.push" in JS


# --- huis gaat voor: geen zon terugleveren als het huis daarna leeg staat --

from custom_components.energy_management_system import waardeplan as wp


def _r(actie, net, inhoud):
    return {"actie": actie, "net_kwh": net, "inhoud_kwh": inhoud}


def test_export_met_later_lege_accu_is_tekort():
    rijen = [_r("zon_export", -0.2, 0.7), _r("zon", -0.1, 1.0), _r("huis", 0.0, 0.0), _r("houden", 0.3, 0.0)]
    assert wp.zon_export_laat_huis_tekort(rijen) is True


def test_export_met_genoeg_tot_laden_mag():
    rijen = [_r("zon_export", -0.2, 2.0), _r("huis", 0.0, 0.5), _r("laden_net", 0.6, 1.0), _r("houden", 0.3, 0.0)]
    assert wp.zon_export_laat_huis_tekort(rijen) is False


def test_lege_accu_voor_de_export_telt_niet():
    rijen = [_r("houden", 0.3, 0.0), _r("zon_export", -0.2, 0.0), _r("huis", 0.0, 0.4)]
    assert wp.zon_export_laat_huis_tekort(rijen) is False


def test_coordinator_plant_opnieuw_zonder_export(make_coordinator):
    """v5.186.0 (punt 14): de herberekening zonder terugleveren zit in het plan
    zelf (per kwartier, `plan` -> zon_export_geweigerd); de sturing neemt de
    uitkomst over in `waardeplan_zon_export_geweigerd` en het attribuut."""
    from pathlib import Path
    import custom_components.energy_management_system as pkg
    code = (Path(pkg.__file__).parent / "waardeplan_sturing.py").read_text(encoding="utf-8")
    assert "_waardeplan_huis_eerst" not in code
    assert 'self.waardeplan_zon_export_geweigerd = bool(getattr(res, "zon_export_geweigerd", 0))' in code
    rijen = [_r("zon_export", -0.2, 0.7), _r("houden", 0.3, 0.0)]
    assert wp._zon_export_voor_tekort(rijen) == [0]
    goed = [_r("zon_export", -0.2, 2.0), _r("huis", 0.0, 1.0)]
    assert wp._zon_export_voor_tekort(goed) == []