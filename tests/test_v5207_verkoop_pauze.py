"""v5.207.0 - knop "Verkopen uit (vandaag)".

Ruud 10-11: "Ik weet dat de oven nog een paar keer aan moet, kunnen we een
knop bouwen waarmee ik zeg dat verkopen niet toegestaan is? Deze moet
dagelijks resetten en het plan moet er rekening mee houden."
"""
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.verkoop_pauze import (
    VERKOOP_PAUZE_REDEN,
    einde_van_de_dag,
)


def _nu():
    return dt_util.as_local(datetime(2026, 11, 10, 15, 17, tzinfo=dt_util.UTC))


def test_einde_is_middernacht():
    e = einde_van_de_dag(_nu())
    assert (e.hour, e.minute) == (0, 0)
    assert e.date() == _nu().date() + timedelta(days=1)


def test_aan_tot_middernacht_en_daarna_vanzelf_uit(make_coordinator):
    c = make_coordinator({})
    c._waardeplan_cache = ("x", {})
    c.zet_verkoop_pauze(True, now=_nu())
    assert c._waardeplan_cache is None            # plan meteen opnieuw
    assert c.verkoop_pauze_actief(_nu())
    assert c.verkoop_pauze_actief(_nu() + timedelta(hours=8)) is True   # 23:17
    assert c.verkoop_pauze_actief(_nu() + timedelta(hours=9)) is False  # na middernacht
    assert c.verkoop_pauze_tot is None


def test_uitzetten(make_coordinator):
    c = make_coordinator({})
    c.zet_verkoop_pauze(True, now=_nu())
    c.zet_verkoop_pauze(False, now=_nu())
    assert not c.verkoop_pauze_actief(_nu())
    assert c.get_verkoop_pauze_status(_nu()) == {"actief": False}


def test_kwartieren_vandaag_wel_morgen_niet(make_coordinator):
    c = make_coordinator({})
    c.zet_verkoop_pauze(True, now=dt_util.now())
    vandaag = dt_util.now() + timedelta(minutes=5)
    morgen = einde_van_de_dag(dt_util.now()) + timedelta(minutes=15)
    assert c.verkoop_verboden_om(vandaag) is True
    assert c.verkoop_verboden_om(morgen) is False


def test_verkooptoets_zegt_nee(make_coordinator):
    c = make_coordinator({})
    assert c.verkoop_pauze_toets({"mag_verkopen": True})["mag_verkopen"] is True
    c.zet_verkoop_pauze(True)
    t = c.verkoop_pauze_toets({"mag_verkopen": True, "vrij_kwh": 2.0})
    assert t["mag_verkopen"] is False and t["reden"] == VERKOOP_PAUZE_REDEN
    assert t["vrij_kwh"] == 2.0


def test_plan_verkoopt_niet_met_verbod_maar_dekt_huis():
    """Avondpiek 90 ct, accu vol: zonder verbod verkoopt het plan, met verbod
    gaat alles naar het huis."""
    begin = datetime(2026, 11, 10, 17, 0)
    def kws(verboden):
        return [
            W.Kwartier(begin + timedelta(minutes=15 * i), 0.2, 0.0, 0.30, 0.90 if i < 4 else 0.05,
                       verkoop_verboden=verboden)
            for i in range(8)
        ]
    accu = W.Accu(inhoud_kwh=5.0, bruikbaar_kwh=5.0, laden_kw=2.4, ontladen_kw=2.4, verkoop_kw=2.4,
                  rendement=0.85, slijtage_eur=0.04, netladen=False, verkopen=True)
    met = W.plan(kws(False), accu)
    zonder = W.plan(kws(True), accu)
    assert any(r.get("actie") == "verkopen" for r in met.kwartieren)
    assert not any(r.get("actie") == "verkopen" for r in zonder.kwartieren)
    assert any(r.get("actie") == "huis" for r in zonder.kwartieren)


def test_schakelaar(make_coordinator, hass):
    from custom_components.energy_management_system.switch import VerkoopPauzeSwitch

    c = make_coordinator({})
    knop = VerkoopPauzeSwitch(c, entry_id="x")
    assert knop._attr_unique_id == "x_verkoop_pauze"
    assert knop.is_on is False
    c.zet_verkoop_pauze(True)
    assert knop.is_on is True
    assert knop.extra_state_attributes["actief"] is True
