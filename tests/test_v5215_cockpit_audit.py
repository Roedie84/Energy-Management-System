"""v5.215.0 (Ruud 11-11 13:05: "volledige audit"): schoonheidsfouten in de cockpit.

De cockpit is met de live gegevens van 11-11 13:06 gerenderd (1400 en 420 px)
en nagelopen; dit zijn de herstelde punten.
"""
from pathlib import Path

from custom_components.energy_management_system import coordinator as C

JS = (Path(C.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
Coord = C.EnergyManagementSystemCoordinator


def test_geld_twee_kolommen_alleen_bij_genoeg_breedte():
    assert "repeat(auto-fit, minmax(min(100%, 300px), 1fr))" in JS
    assert ".geld-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }" not in JS


def test_paneelkop_kapt_chips_niet_af():
    blok = JS[JS.index(".ph-r {"):JS.index(".ph-r {") + 200]
    assert "flex-wrap: wrap" in blok and "overflow: hidden" not in blok


def test_grafiek_zon_als_vermogen_en_ronde_as():
    assert "num(r.zon_w) != null" in JS
    assert "`${x(0).toFixed(2)},100 `" in JS
    assert "Math.ceil(pMax / 20) * 20" in JS


def test_kleine_verschillen_heten_vrijwel_gelijk():
    assert JS.count('"vrijwel gelijk"') >= 2


def test_bedragen_en_labels():
    assert "net ${euroTeken(net.marge_eur)}" in JS
    assert '["repetitie", "Na de saldering"]' in JS
    assert '"Cockpit: versie onbekend"' in JS
    assert 'n: "Vakantie", s:' in JS
    assert "dagLabel(lstD) + klok(lstD)" in JS


def test_vooruitblik_schuift_op_een_smal_scherm():
    assert ".tabel.vb { display: block; overflow-x: auto;" in JS


def test_moduledrift_in_gewone_woorden():
    assert Coord.MODULE_DRIFT_NAMEN["temperatuur_afwijking_c"] == "temperatuur"
    assert Coord.MODULE_DRIFT_NAMEN["cel_delta_afwijking_v"] == "celverschil"


def _zin(samenvatting):
    c = Coord.__new__(Coord)
    for naam in dir(Coord):
        attr = getattr(Coord, naam, None)
        if callable(attr) and "kwartier(en) aan het net" in (getattr(attr, "__doc__", "") or "") + "":
            pass
    import inspect
    for naam, f in inspect.getmembers(Coord, inspect.isfunction):
        if "bijladen: {tekorten} kwartier(en) aan het net" in inspect.getsource(f):
            return f(c, samenvatting)
    raise AssertionError("zin niet gevonden")


def test_planzin_zegt_de_ondergrens_een_keer_en_in_euro():
    zin = _zin({"beschikbaar": True, "kwartieren": 44, "verwachte_opbrengst_eur": -1.03, "eind_soc_procent": 10,
                "min_soc_procent_hard": 10, "laagste_soc_tot_bijladen_procent": 10, "tekort_kwartieren": 13,
                "tekort_perioden": ["20:45-00:00"]})
    assert zin.count("ondergrens zelf") == 1
    assert "allebei de ondergrens zelf, dus zonder marge" in zin
    assert zin.endswith("-€ 1,03 over 11 uur.")
    assert "EUR" not in zin


def test_planzin_met_marge_blijft_zoals_hij_was():
    zin = _zin({"beschikbaar": True, "kwartieren": 104, "verwachte_opbrengst_eur": 0.8, "eind_soc_procent": 51,
                "min_soc_procent_hard": 10, "laagste_soc_tot_bijladen_procent": 19, "tekort_kwartieren": 0})
    assert zin == "Ja, de accu haalt het bijladen: geen kwartier aan het net. Laagste 19% tot het bijladen, 51% na 26 uur. € 0,80 over 26 uur."
