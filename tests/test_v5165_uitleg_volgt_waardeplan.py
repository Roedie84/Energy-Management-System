"""v5.165.0 punt 3 - de uitleg volgt het waardeplan (akkoord Ruud 02-11).

De uitleg kwam uit de oude regels terwijl het waardeplan stuurde: "laadblok
23:30" terwijl het plan om 23:45 laadde, "bijladen uit het net loont niet"
naast een geplande netlading, en "wordt in het laadblok bijgeladen 5,58 kWh"
terwijl het plan ~1,2 kWh laadt.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C
from homeassistant.util import dt as dt_util

TZ = timezone.utc
NU = datetime(2026, 11, 2, 18, 5, tzinfo=TZ)


def _rij(begin, actie, kwh=0.0):
    return {"begin": begin, "actie": actie, "kwh": kwh, "accu_kwh": kwh, "net_kwh": 0.1,
            "inhoud_kwh": 1.0, "inhoud_delta_kwh": 0.0, "prijs_eur": 0.3}


def _c(make_coordinator, acties):
    c = make_coordinator({})
    begin = NU.replace(minute=0)
    c._waardeplan_rijen = [
        _rij(begin + timedelta(minutes=15 * i), a, k) for i, (a, k) in enumerate(acties)
    ]
    c.last_waardeplan = {"beschikbaar": True, "vooruit": [], "nu": {}}
    c.last_reason = "waardeplan_huis"
    return c


# 18:00 huis ... 23:45-00:15 laden (0,6 + 0,6), daarna huis
ACTIES = [("huis", 0.0)] * 23 + [("laden_net", 0.6), ("laden_net", 0.6)] + [("huis", 0.0)] * 8


def test_volgende_lading_uit_het_plan(make_coordinator, hass):
    c = _c(make_coordinator, ACTIES)
    lading = c._waardeplan_volgende_lading(NU)
    assert lading["van"] == NU.replace(minute=0) + timedelta(minutes=15 * 23)
    assert lading["tot"] == lading["van"] + timedelta(minutes=30)
    assert lading["kwh"] == 1.2
    zin = c._waardeplan_lading_zin(NU)
    assert f"{dt_util.as_local(lading['van']):%H:%M}" in zin and "1,2 kWh" in zin


def test_geen_netlading_in_het_plan(make_coordinator, hass):
    c = _c(make_coordinator, [("huis", 0.0)] * 16)
    assert c._waardeplan_volgende_lading(NU)["geen"]
    assert "niet uit het net" in c._waardeplan_lading_zin(NU)


def test_alleen_als_het_waardeplan_stuurt(make_coordinator, hass):
    c = _c(make_coordinator, ACTIES)
    c.last_reason = "celbescherming_houden"
    assert c._waardeplan_volgende_lading(NU) is None
    assert c._waardeplan_lading_zin(NU) is None
    assert c._waardeplan_laadbesluit_stand() is None


def test_uitleg_noemt_de_lading_van_het_plan(make_coordinator, hass, monkeypatch):
    c = _c(make_coordinator, ACTIES)
    monkeypatch.setattr(dt_util, "now", lambda *a, **k: NU)
    tekst = c._reden_uitleg("waardeplan_huis")
    assert "1,2 kWh uit het net" in tekst
    assert "waardeplan laadt" in "".join(c._waarom_waardeplan())


def test_tabel_zegt_niet_meer_dat_het_laadblok_bijlaadt():
    b = {"diepste_tekort_tot_blok_kwh": 1.0, "diepste_tekort_na_blok_kwh": 5.58, "diepste_tekort_kwh": 6.58}
    oud = C._tabelregels_tot_en_na_blok(b)
    assert any("laadblok" in label for label, _ in oud)
    nieuw = C._tabelregels_tot_en_na_blok(b, "het waardeplan laadt 23:45-00:15 1,2 kWh uit het net")
    assert not any("laadblok" in label for label, _ in nieuw)
    assert ("Laden uit het net (waardeplan)", "Het waardeplan laadt 23:45-00:15 1,2 kWh uit het net") in nieuw


def test_laadbesluit_loont_bij_geplande_netlading(make_coordinator, hass):
    c = _c(make_coordinator, ACTIES)
    c.last_laadbesluit = {"waarde_eur": 0.2, "prijs_nu_eur": 0.3}   # oud: loont niet
    c._laadbesluit_stand = "loont_niet"
    c._volg_laadbesluit_en_zon(None)
    assert c._laadbesluit_stand == "loont"
    assert not c._netladen_economisch_afgewezen()


def test_laadbesluit_loont_niet_zonder_netlading_in_het_plan(make_coordinator, hass):
    c = _c(make_coordinator, [("huis", 0.0)] * 16)
    c.last_laadbesluit = {"waarde_eur": 0.4, "prijs_nu_eur": 0.3}   # oud: loont
    c._laadbesluit_stand = None
    c._volg_laadbesluit_en_zon(None)
    assert c._laadbesluit_stand == "loont_niet"
