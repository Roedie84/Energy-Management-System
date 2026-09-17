"""De nieuwe metingen worden bewaakt (v5.2).

Gevraagd: "Worden alle recente wijzigingen ook weer bewaakt?"

Nee. De stilstandcontrole (`get_stalled_series_report`, v1.11.1) loopt
automatisch over alle lijstvelden - goed ontworpen, nieuwe velden komen
er gratis in - maar hij kijkt alleen naar LIJSTEN VAN GETALLEN:

    getallen = [x for x in waarde if isinstance(x, (int, float))]

De metingen van v4.14 tot v5.1 zijn lijsten van DICTS
(`safe_sell_shadow`, `eigen_ingrepen`, `cycluskosten_geschiedenis`) of
DICTS VAN LIJSTEN (`reden_afwijkingen`, `nachtlast_per_apparaat`). Die
vallen er allemaal buiten. En `meet_stuurt_niet` bewaakt alleen
proefstandkandidaten; deze vijf zijn geen kandidaten.

Gevolg: stopt `safe_sell_shadow` met vullen - bijvoorbeeld omdat het
terugvalpad na een wijziging nooit meer wordt bereikt - dan merkt
niemand het. Precies de klasse fout van deze weken: de ijklijn die nooit
klaar kon komen, de uursleutels van v4.6 die drie maanden sluimerden,
en `meet_stuurt_niet` zelf, dat bestaat omdat metingen stil bleven
staan.

En het is waarschijnlijker dan bij de oude reeksen: `safe_sell_shadow`
vult alleen bij verkoop in het terugvalpad, en bij `expensive_quarter`
gaat het om zeventien momenten per acht zomerdagen. "Leeg" is dan
maanden lang niet te onderscheiden van "kapot".

Daarom niet "verandert de reeks nog" maar "wanneer kwam er voor het
laatst iets bij", met een VERWACHTE frequentie per meting - anders is
elke drempel willekeurig.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def test_elke_nieuwe_meting_heeft_een_verwachte_frequentie():
    """De ratel: een meting zonder verwachting is niet te beoordelen."""
    from custom_components.energy_management_system.const import (
        METING_VERWACHTE_STILTE_DAGEN,
    )

    for naam in (
        "safe_sell_shadow",
        "eigen_ingrepen",
        "cycluskosten_geschiedenis",
        "reden_afwijkingen",
        "nachtlast_per_apparaat",
        "dagverloop",
        "nabeschouwingen",
    ):
        assert naam in METING_VERWACHTE_STILTE_DAGEN, naam
        assert METING_VERWACHTE_STILTE_DAGEN[naam] > 0


def test_een_meting_die_net_gevuld_is_meldt_niets(make_coordinator, hass):
    c = make_coordinator({})
    c.meting_laatst_gevuld = {"safe_sell_shadow": NU.isoformat()}

    rapport = c.get_metingen_stilstand(NU + timedelta(days=1))

    assert not [r for r in rapport if r["meting"] == "safe_sell_shadow"]


def test_een_meting_die_te_lang_stil_staat_wordt_gemeld(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        METING_VERWACHTE_STILTE_DAGEN,
    )

    c = make_coordinator({})
    dagen = METING_VERWACHTE_STILTE_DAGEN["cycluskosten_geschiedenis"]
    c.meting_laatst_gevuld = {"cycluskosten_geschiedenis": NU.isoformat()}

    rapport = c.get_metingen_stilstand(NU + timedelta(days=dagen + 1))
    regel = next(r for r in rapport if r["meting"] == "cycluskosten_geschiedenis")

    assert regel["dagen_stil"] == dagen + 1
    assert regel["verwacht_binnen_dagen"] == dagen
    assert "vaatwas" in regel["wat_vult_hem"] or "beurt" in regel["wat_vult_hem"]


def test_een_meting_die_nooit_gevuld_is_rekent_vanaf_de_start(make_coordinator, hass):
    """Anders lijkt een meting die vanaf het begin stuk is nooit stil."""
    c = make_coordinator({})
    c.meting_laatst_gevuld = {}
    c._started_at = NU

    rapport = c.get_metingen_stilstand(NU + timedelta(days=90))
    regel = next(r for r in rapport if r["meting"] == "reden_afwijkingen")

    assert regel["nooit_gevuld"] is True


def test_binnen_de_aanlooptijd_wordt_er_niets_gemeld(make_coordinator, hass):
    """Een verse installatie heeft nog niets gevuld en dat is normaal."""
    c = make_coordinator({})
    c.meting_laatst_gevuld = {}
    c._started_at = NU

    assert c.get_metingen_stilstand(NU + timedelta(hours=6)) == []


def test_het_vullen_wordt_vastgelegd(make_coordinator, hass):
    c = make_coordinator({})
    c.meting_laatst_gevuld = {}
    c.eigen_ingrepen = []
    c.last_available_kwh = 2.0
    c.accustand_procent = lambda: 40.0
    c.last_reserve_margin_breakdown = {}

    c.noteer_eigen_ingreep("laden", NU)

    assert "eigen_ingrepen" in c.meting_laatst_gevuld


def test_de_zeldzame_metingen_krijgen_een_ruime_drempel():
    """safe_sell_shadow vult alleen bij avondverkoop in het terugvalpad -
    zeventien momenten per acht zomerdagen. Een drempel van zeven dagen
    zou daar elke week vals alarm geven."""
    from custom_components.energy_management_system.const import (
        METING_VERWACHTE_STILTE_DAGEN,
    )

    assert METING_VERWACHTE_STILTE_DAGEN["safe_sell_shadow"] >= 45
    assert METING_VERWACHTE_STILTE_DAGEN["reden_afwijkingen"] <= 3
    assert METING_VERWACHTE_STILTE_DAGEN["dagverloop"] <= 2


def test_het_rapport_staat_in_de_aandachtspunten(make_coordinator, hass):
    """Een stille meting hoort op de landingspagina, niet alleen in de
    export - anders moet iemand ernaar zoeken."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("def _aandachtspunten_over_de_integratie")
    j = bron.index("\n    def ", i + 10)

    assert "get_metingen_stilstand" in bron[i:j]
