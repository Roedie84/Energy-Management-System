"""v5.268.0: uitval van de omvormer tellen en melden.

Ruud, 27 november: "Af en toe lijkt de accu niet correct 0 op de meter te
houden." Gevonden: sinds 26-11 15:01 meldt de SolarFlow af en toe een fout
(is_error), levert dan ongeveer anderhalve minuut niets en komt vanzelf
terug; 8 keer in 17 uur, in de 9 dagen ervoor geen enkele keer. Het EMS
telt dit nu en meldt het vanaf drie keer op een dag. Stuurt niets.
"""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import zendure_lokaal as zl

# 27-11-2026 07:37:16 lokaal, de uitval in rust van die ochtend
T0 = datetime(2026, 11, 27, 6, 37, 16, tzinfo=timezone.utc).timestamp()
GOED = {"foutmelding": False, "storingsniveau": 0}
FOUT = {"foutmelding": True, "storingsniveau": 2}
LEVERT = {"outputHomePower": 738.0, "gridInputPower": 0.0, "electricLevel": 83.0}
STIL = {"outputHomePower": 0.0, "gridInputPower": 0.0, "electricLevel": 83.0}


def _uitval(t, begin, duur=76):
    """Een uitval zoals gemeten: fout vanaf `begin`, `duur` seconden."""
    zl.verwerk_uitval(t, GOED, LEVERT, begin - 2)
    gewijzigd = zl.verwerk_uitval(t, FOUT, STIL, begin)
    for s in range(2, duur, 2):
        assert zl.verwerk_uitval(t, FOUT, STIL, begin + s) is False
    return gewijzigd, zl.verwerk_uitval(t, GOED, STIL, begin + duur)


def test_rapport_met_fout_wordt_herkend_in_beide_schrijfwijzen():
    assert zl.afgeleid({"properties": {"is_error": 1}})["foutmelding"] is True
    assert zl.afgeleid({"properties": {"isError": 1}})["foutmelding"] is True
    assert zl.afgeleid({"properties": {"is_error": 0}})["foutmelding"] is False
    assert zl.afgeleid({"properties": {}})["foutmelding"] is False


def test_een_uitval_wordt_een_keer_geteld_met_duur_en_vermogen_ervoor():
    t = zl.lege_tellingen()
    begin, eind = _uitval(t, T0)
    assert begin is True and eind is True       # beide meteen bewaren
    s = zl.uitval_samenvatting(t, T0 + 100)
    assert s["vandaag"] == 1 and s["laatste_7_dagen"] == 1 and s["nu_in_storing"] is False
    [g] = s["laatste"]
    assert g["duur_s"] == 76 and g["vermogen_voor_w"] == 738 and g["soc"] == 83 and g["storingsniveau"] == 2


def test_zonder_fout_wordt_er_niets_geteld():
    t = zl.lege_tellingen()
    for s in range(0, 600, 2):
        assert zl.verwerk_uitval(t, GOED, LEVERT, T0 + s) is False
    assert zl.uitval_samenvatting(t, T0 + 600)["vandaag"] == 0
    assert zl.uitval_te_melden(t, T0 + 600) is None


def test_lopende_uitval_is_zichtbaar():
    t = zl.lege_tellingen()
    zl.verwerk_uitval(t, GOED, LEVERT, T0 - 2)
    zl.verwerk_uitval(t, FOUT, STIL, T0)
    s = zl.uitval_samenvatting(t, T0 + 10)
    assert s["nu_in_storing"] is True and s["lopend_sinds"] and s["vandaag"] == 1 and s["laatste"] == []


def test_melding_vanaf_drie_keer_en_maar_een_keer_per_dag():
    t = zl.lege_tellingen()
    _uitval(t, T0)
    _uitval(t, T0 + 600)
    assert zl.uitval_te_melden(t, T0 + 700) is None          # twee keer: nog niet
    _uitval(t, T0 + 1200)
    m = zl.uitval_te_melden(t, T0 + 1300)
    assert m["aantal"] == 3 and m["laatste_duur_s"] == 76 and len(m["laatste_om"]) == 5
    assert zl.uitval_te_melden(t, T0 + 1400) is None          # niet nog eens
    _uitval(t, T0 + 1800)
    assert zl.uitval_te_melden(t, T0 + 1900) is None          # ook niet bij de vierde
    # de volgende dag begint de telling opnieuw
    morgen = T0 + 86400
    for i in range(3):
        _uitval(t, morgen + i * 600)
    assert zl.uitval_te_melden(t, morgen + 2000)["aantal"] == 3
    assert zl.uitval_samenvatting(t, morgen + 2000)["laatste_7_dagen"] == 7


def test_herstart_midden_in_een_storing_geeft_geen_uitval_van_uren():
    t = zl.lege_tellingen()
    zl.verwerk_uitval(t, GOED, LEVERT, T0 - 2)
    zl.verwerk_uitval(t, FOUT, STIL, T0)
    zl.verwerk_uitval(t, FOUT, STIL, T0 + 20)
    # een uur geen lezing; daarna is de fout weg
    assert zl.verwerk_uitval(t, GOED, LEVERT, T0 + 3600) is True
    [g] = zl.uitval_samenvatting(t, T0 + 3700)["laatste"]
    assert g["duur_s"] == 20


def test_telling_overleeft_een_herstart():
    t = zl.lege_tellingen()
    _uitval(t, T0)
    terug = zl.herstel(dict(t))
    assert zl.uitval_samenvatting(terug, T0 + 200)["vandaag"] == 1
    # een bewaarde stand van voor deze versie heeft het veld nog niet
    oud = {k: v for k, v in t.items() if k != "uitval"}
    assert zl.verwerk_uitval(zl.herstel(oud), GOED, LEVERT, T0) is False


def test_per_dag_houdt_veertien_dagen():
    t = zl.lege_tellingen()
    for dag in range(20):
        _uitval(t, T0 + dag * 86400)
    assert len(zl.uitval_samenvatting(t, T0 + 20 * 86400)["per_dag"]) == zl.UITVAL_DAGEN


def test_coordinator_meldt_een_keer(make_coordinator):
    c = make_coordinator({})
    t = zl.lege_tellingen()
    for i in range(3):
        _uitval(t, T0 + i * 600)
    c.zendure_lokaal = SimpleNamespace(tellingen=t, _relais_gewijzigd=False)
    gestuurd = []
    c._dispatch_notification = lambda **kw: gestuurd.append(kw)
    nu = datetime.fromtimestamp(T0 + 2000, tz=timezone.utc)
    c._update_omvormer_uitval(nu)
    c._update_omvormer_uitval(nu)
    assert len(gestuurd) == 1 and gestuurd[0]["kind"] == "omvormer_uitval"
    assert "3 keer" in gestuurd[0]["message"] and "Zendure-app" in gestuurd[0]["message"]
    assert c.zendure_lokaal._relais_gewijzigd is True         # gemeld_dag wordt bewaard


def test_zonder_meelezer_gebeurt_er_niets(make_coordinator):
    c = make_coordinator({})
    c.zendure_lokaal = None
    c._update_omvormer_uitval(datetime.fromtimestamp(T0, tz=timezone.utc))


def test_het_tellen_stuurt_niets():
    bron = (Path(pkg.__file__).parent / "zendure_lokaal.py").read_text(encoding="utf-8")
    blok = bron[bron.index("def lege_uitval"):bron.index("def rendement_samenvatting")]
    for verboden in ("async_call", "sessie.post", "properties/write", "set_value"):
        assert verboden not in blok, verboden
