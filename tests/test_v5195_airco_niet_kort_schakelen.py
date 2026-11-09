"""v5.195.0: de airco niet kort schakelen.

08-11: het EMS zette de airco om 15:22 uit ('niemand thuis', Ruud > 3 km weg,
Majorie wel thuis) en om 15:43 weer aan. Ruud 09-11: "niet goed voor de airco,
niet meer voor laten komen". Nu: wat het EMS schakelde blijft minstens 30 min
zo, en ook ver weg pas uit na 30 min afwezigheid.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import airco_ritme as R
from custom_components.energy_management_system import airco_sturing as A

T = datetime(2026, 11, 8, 15, 22, tzinfo=timezone(timedelta(hours=1)))


def _b(actie):
    return {"actie": actie, "tekst": "x", "redenen": ["r"], "redenen_tekst": "r"}


def test_niet_binnen_30_min_weer_aan():
    uit = A.niet_kort_schakelen(_b("verwarmen"), ("uit", T), T + timedelta(minutes=21))
    assert uit["actie"] == "niets" and uit["kort_schakelen"]
    assert "9 min" in uit["tekst"]


def test_na_30_min_wel():
    assert A.niet_kort_schakelen(_b("verwarmen"), ("uit", T), T + timedelta(minutes=30))["actie"] == "verwarmen"


def test_niet_kort_na_aanzetten_uit():
    assert A.niet_kort_schakelen(_b("uit"), ("verwarmen", T), T + timedelta(minutes=10))["actie"] == "niets"


def test_zonder_vorige_schakeling_gewoon():
    assert A.niet_kort_schakelen(_b("uit"), None, T)["actie"] == "uit"
    assert A.niet_kort_schakelen(_b("niets"), ("uit", T), T)["actie"] == "niets"


def test_raam_open_gaat_voor():
    """De raamregel komt na deze en zet de airco toch uit."""
    geblokt = A.niet_kort_schakelen(_b("uit"), ("verwarmen", T), T + timedelta(minutes=5))
    uit = A.raam_open(geblokt, {"open": ["woonkamer voor"]}, airco_stand="heat",
                      door_ems_aan=True, open_sinds_s=600, uitstel_s=300)
    assert uit["actie"] == "uit"


def test_ver_weg_pas_na_30_min_uit():
    ritme = R.leeg()
    assert R.kort_weg(ritme, 5, 12.0) is not None
    assert R.kort_weg(ritme, R.KORT_WEG_MIN_MIN, 12.0) is None
