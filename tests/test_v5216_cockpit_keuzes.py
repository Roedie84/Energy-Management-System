"""v5.216.0 (Ruud 11-11 13:25: "Alle 7 akkoord"): de keuzes uit de cockpit-audit."""
from pathlib import Path

from custom_components.energy_management_system import coordinator as C

JS = (Path(C.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def test_accu_vandaag_toont_de_gecorrigeerde_besparing():
    assert 'accu ${getal(bes) < 0 ? "kost" : "levert"} vandaag <b>${euroTeken(getal(bes))}</b>' in JS


def test_reservetegels_vervangen_door_het_plan():
    for weg in ('mini("Reserve tot blok"', 'mini("Vrij te verkopen"', 'mini("Veiligheidsmarge"', "o.naam"):
        assert weg not in JS, weg
    for erbij in ('mini("Waarde lading"', 'mini("Verkoop gepland"', 'mini("Accu leeg om"'):
        assert erbij in JS, erbij
    assert "wpNu.waarde_inhoud_eur_per_kwh" in JS


def test_koelingschip_zegt_welke_temperatuur():
    assert "omvormer ${fmt(attr(koeling, \"accu_c\"))}" in JS


def test_vooruitblik_in_cent():
    assert "`${fmt(lo * 100, 0)}\\u2013${fmt(hi * 100, 0)} ct`" in JS


def test_voetregel_kort():
    assert 'split(" \\u00b7 ").slice(0, 3)' in JS
    assert "bruikbaar(meetlog) ? esc(meetlog.state)" not in JS
