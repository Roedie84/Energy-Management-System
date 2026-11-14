"""v5.234.0: de airco gaat niet meer uit als iedereen weg is.

Ruud 14-11: "Eigenlijk wil ik niet meer uitschakelen bij afwezigheid". Die dag
ging hij om 12:19 uit (even weg) en pas om 12:43 weer aan.
"""
from custom_components.energy_management_system import airco_sturing as a


def _besluit(**anders):
    basis = dict(
        woonkamer_c=19.5, aanwezigheid="weg", aanzet_c=18.5, doel_c=21.0,
        advies="airco", handmatig=False, airco_stand="heat", door_ems_aan=True,
        setpunten_gezien=6, setpunten_nodig=5,
    )
    basis.update(anders)
    return a.besluit(**basis)


def test_weg_en_het_ems_zette_hem_aan_dan_blijft_hij_aan():
    uit = _besluit()
    assert uit["actie"] == "niets"
    assert "blijft aan" in uit["tekst"] and "niemand thuis" in uit["redenen_tekst"]


def test_weg_en_de_airco_staat_uit_dan_gaat_hij_niet_aan():
    uit = _besluit(airco_stand="off", door_ems_aan=False, woonkamer_c=16.0)
    assert uit["actie"] == "niets" and uit["tekst"] == "Niemand thuis."


def test_iedereen_slaapt_zet_nog_wel_uit():
    assert _besluit(aanwezigheid="slaapt")["actie"] == "uit"


def test_onbekende_aanwezigheid_zet_nog_wel_uit():
    assert _besluit(aanwezigheid=None)["actie"] == "uit"


def test_met_de_schakelaar_terug_gaat_hij_weer_uit_bij_weg(monkeypatch):
    monkeypatch.setattr(a, "AIRCO_UIT_BIJ_WEG", True)
    assert _besluit()["actie"] == "uit"


def test_handmatig_gaat_nog_steeds_voor():
    assert _besluit(handmatig=True)["actie"] == "niets"
