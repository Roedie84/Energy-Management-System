"""v5.235.0: langer dan twee uur weg -> de airco terug naar 18 °C, niet uit.

Akkoord Ruud 14-11, na v5.234.0 (niet meer uit bij afwezigheid).
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import airco_sturing as A
from custom_components.energy_management_system.klimaat import KlimaatMixin

T = datetime(2026, 11, 14, 12, 0, tzinfo=timezone(timedelta(hours=1)))


class _Stub(KlimaatMixin):
    def __init__(self):
        self.presence_state = "weg"
        self.airco_door_ems = True
        self._airco_handmatig_bij = None
        self._weg_sinds = T


def _niets(**kw):
    return dict({"actie": "niets", "tekst": "Niemand thuis: de airco blijft aan.", "redenen": ["r"],
                 "redenen_tekst": "r", "doel_c": 21.0}, **kw)


def test_binnen_twee_uur_blijft_hij_op_de_gewone_temperatuur():
    s = _Stub()
    uit = s._airco_weg_ronde(T + timedelta(minutes=119), _niets(), "heat", 21.0)
    assert uit["actie"] == "niets" and not s._airco_weg_vast


def test_na_twee_uur_terug_naar_18_en_bij_thuiskomst_weer_naar_21():
    s = _Stub()
    uit = s._airco_weg_ronde(T + timedelta(minutes=120), _niets(), "heat", 21.0)
    assert uit["actie"] == "verwarmen" and uit["doel_c"] == 18.0 and s._airco_weg_vast
    assert "terug naar 18 °C" in uit["tekst"]
    # volgende ronde: hij staat op 18, niets meer te doen
    weer = s._airco_weg_ronde(T + timedelta(minutes=121), _niets(), "heat", 18.0)
    assert weer["actie"] == "niets"
    s.presence_state = "thuis"
    terug = s._airco_weg_ronde(T + timedelta(hours=5), _niets(tekst="Warm genoeg."), "heat", 18.0)
    assert terug["actie"] == "verwarmen" and terug["doel_c"] == 21.0 and not s._airco_weg_vast


def test_alleen_een_airco_die_het_ems_aanzette_en_die_verwarmt():
    s = _Stub()
    laat = T + timedelta(hours=3)
    s.airco_door_ems = False
    assert s._airco_weg_ronde(laat, _niets(), "heat", 21.0)["actie"] == "niets"
    s.airco_door_ems = True
    assert s._airco_weg_ronde(laat, _niets(), "off", 21.0)["actie"] == "niets"
    assert s._airco_weg_ronde(laat, _niets(), "heat", 18.0)["actie"] == "niets"
    assert not s._airco_weg_vast


def test_handmatig_en_de_vaste_uit_gaan_voor():
    s = _Stub()
    laat = T + timedelta(hours=3)
    assert s._airco_weg_ronde(laat, {"actie": "uit", "altijd": True, "redenen": []}, "heat", 21.0)["actie"] == "uit"
    s._airco_handmatig_bij = "weg"
    assert s._airco_weg_ronde(laat, _niets(), "heat", 21.0)["actie"] == "niets"
    assert not s._airco_weg_vast


def test_zonder_begin_van_de_afwezigheid_niets():
    s = _Stub()
    s._weg_sinds = None
    assert s._airco_weg_ronde(T + timedelta(hours=3), _niets(), "heat", 21.0)["actie"] == "niets"


def test_met_de_oude_schakelaar_geen_terugzetten(monkeypatch):
    monkeypatch.setattr(A, "AIRCO_UIT_BIJ_WEG", True)
    s = _Stub()
    assert s._airco_weg_ronde(T + timedelta(hours=3), _niets(), "heat", 21.0)["actie"] == "niets"


def test_de_grens_is_twee_uur():
    assert A.AIRCO_WEG_TERUGZETTEN_NA_MIN == 120 and A.AIRCO_WEG_VAST_C == 18.0
