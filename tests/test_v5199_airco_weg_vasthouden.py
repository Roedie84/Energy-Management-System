"""v5.199.0: bij langere afwezigheid uit of vasthouden op 18 °C.

Ruud 09-11: "bij langere afwezigheid de temperatuur wat lager zetten tot
terugkomst?" - akkoord op: het EMS rekent wat goedkoper is, uit of 18 °C
vasthouden, op de prijzen en het moment waarop jullie meestal thuiskomen.
Bij thuiskomst weer naar de gewone temperatuur.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import airco_sturing as A
from custom_components.energy_management_system.klimaat import KlimaatMixin

T = datetime(2026, 11, 9, 9, 0, tzinfo=timezone(timedelta(hours=1)))


def _keuze(**kw):
    basis = dict(binnen_c=21.0, buiten_c=5.0, doel_c=21.0, tempo_c_per_uur=2.0,
                 uren_weg=8.0, kost_vast=0.25, kost_terug=0.25)
    basis.update(kw)
    return A.weg_keuze(**basis)


def test_gelijke_prijzen_uit_is_goedkoper():
    k = _keuze()
    assert k["keuze"] == "uit"
    assert k["kosten_uit_eur"] < k["kosten_vast_eur"] + A.AIRCO_WEG_MIN_VOORDEEL_EUR


def test_duur_bij_thuiskomst_vasthouden():
    k = _keuze(kost_vast=0.10, kost_terug=0.60, uren_weg=10.0)
    assert k["keuze"] == "vast", k
    assert "goedkoper" in k["reden"]


def test_kort_weg_koelt_niet_tot_18():
    k = _keuze(uren_weg=1.0, kost_vast=0.01, kost_terug=1.0)
    assert k["keuze"] == "uit" and "koelt niet af" in k["reden"]


def test_zonder_prijs_of_thuiskomst_gewoon_uit():
    assert _keuze(kost_terug=None)["keuze"] == "uit"
    assert _keuze(uren_weg=None)["keuze"] == "uit"


def test_doel_niet_boven_18_geen_vasthouden():
    assert _keuze(doel_c=18.0, kost_vast=0.0, kost_terug=1.0)["keuze"] == "uit"


class _Stub(KlimaatMixin):
    def __init__(self, keuze):
        self.presence_state = "weg"
        self.airco_door_ems = True
        self._airco_handmatig_bij = None
        self._keuze = keuze

    def _airco_weg_bereken(self, now, uit):
        return dict(self._keuze)


def _uit():
    return {"actie": "uit", "tekst": "Uitzetten: niemand thuis", "redenen": ["r"],
            "redenen_tekst": "r", "doel_c": 21.0}


def test_ronde_vasthouden_en_terug():
    s = _Stub({"keuze": "vast", "reden": "vasthouden op 18 °C is goedkoper"})
    eerste = s._airco_weg_ronde(T, _uit(), "heat", 21.0)
    assert eerste["actie"] == "verwarmen" and eerste["doel_c"] == 18.0
    # volgende rondes: niet uitzetten
    tweede = s._airco_weg_ronde(T + timedelta(minutes=1), _uit(), "heat", 18.0)
    assert tweede["actie"] == "niets"
    # thuis: weer naar 21
    s.presence_state = "thuis"
    terug = s._airco_weg_ronde(T + timedelta(hours=8), dict(_uit(), actie="niets"), "heat", 18.0)
    assert terug["actie"] == "verwarmen" and terug["doel_c"] == 21.0
    assert not s._airco_weg_vast and s._airco_weg_keuze is None


def test_ronde_uit_blijft_uit():
    s = _Stub({"keuze": "uit", "reden": "uit is goedkoper"})
    uit = s._airco_weg_ronde(T, _uit(), "heat", 21.0)
    assert uit["actie"] == "uit" and "uit is goedkoper" in uit["redenen"]


def test_vaste_uittijd_en_handmatig_gaan_voor():
    s = _Stub({"keuze": "vast", "reden": "x"})
    assert s._airco_weg_ronde(T, dict(_uit(), altijd=True), "heat", 21.0)["actie"] == "uit"
    s._airco_handmatig_bij = "weg"
    assert s._airco_weg_ronde(T, _uit(), "heat", 21.0)["actie"] == "uit"


def test_handmatig_uitgezet_stopt_vasthouden():
    s = _Stub({"keuze": "vast", "reden": "x"})
    s._airco_weg_ronde(T, _uit(), "heat", 21.0)
    s._airco_weg_ronde(T + timedelta(minutes=5), {"actie": "niets", "redenen": []}, "off", 18.0)
    assert not s._airco_weg_vast


def test_verwachte_thuiskomst_uit_weekprofiel():
    s = _Stub({})
    terug = T.replace(hour=17, minute=30)
    s.presence_week_profile = {f"{terug.weekday()}-1730": [4, 5]}
    assert s._verwachte_thuiskomst(T) == terug
    s.presence_week_profile = {}
    assert s._verwachte_thuiskomst(T) is None
