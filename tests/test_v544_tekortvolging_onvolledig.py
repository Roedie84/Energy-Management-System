"""Een onvolledige live tekortvolging deelt niet in als planning (v5.44).

Gemeld op 7 oktober, 22:52: verwacht_tekort stond op 0,63 kWh "planning",
met `laadbesluit_sinds_9u` leeg. De accu kwam die dag tot 93% en werd niet
verder uit het net bijgeladen, omdat dat niet loonde (rendement en slijtage).
Maar v5.41 was pas om 21:00 geïnstalleerd: het laadbesluit, de zon en de
verkoop sinds 09:00 waren alleen vanaf dat moment gevolgd. Om 09:00 zou de
nacht als planning worden ingedeeld en de cockpit op LET OP gaan.

Nu: liep de volging niet vanaf 09:00 (of zat er een gat in, of ontbreekt het
laadbesluit bij een accu die niet vol werd), dan wordt de nacht - en het
verwachte tekort - uit het dagverloop ingedeeld, met dezelfde regels als de
herleiding van oude nachten. Is ook dat te dun: onbekend, nooit planning.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import coordinator as mod
from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

BEGIN = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
INSTALLATIE = BEGIN.replace(hour=21, minute=3)


def _c(make_coordinator):
    c = make_coordinator({})
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 11.22}
    c.bruikbaar_tussen_grenzen_kwh = lambda: 7.78
    return c


def _zeven_oktober(k, tijd):
    """Het patroon van 7 oktober: de hele dag `smart`, de zon de accu in tot
    93%, goedkoopst 29,7 ct, geen verkoop (alleen de vaste -50 W), 's avonds
    het huis uit de accu, tegen de ochtend leeg en import tegen 30 ct."""
    if k < 36:  # 09:00-17:45
        return {"soc": min(93.0, 30 + k * 1.8), "net_w": -50.0, "accu_w": -1200.0,
                "prijs_ct": 29.7 if k == 17 else 33.0}
    if k < 80:  # 18:00-04:45
        return {"soc": max(10.0, 93 - (k - 36) * 1.9), "net_w": -50.0, "accu_w": 380.0,
                "prijs_ct": 42.0 if k < 52 else 33.0}
    return {"soc": 9.0, "net_w": 300.0, "accu_w": 0.0, "prijs_ct": 30.0}


def _dagverloop(rij=_zeven_oktober, tot=96):
    dagen = {}
    for k in range(tot):
        moment = BEGIN + timedelta(minutes=15 * k)
        dagen.setdefault(moment.date().isoformat(), []).append(
            {"tijd": moment.strftime("%H:%M"), "stand": "smart", "reden": "default_smart",
             **rij(k, moment.strftime("%H:%M"))}
        )
    return dagen


def _onvolledig_gevolgd(c, sinds=INSTALLATIE):
    """Zoals de avond van 7 oktober: gevolgd sinds de installatie, zonder gat
    tot de ochtend, laadbesluit leeg, niet vol geweest."""
    c._tekort_volg_sinds = sinds.isoformat()
    c._vol_voor_nacht = False
    c._verkocht_na_vol_kwh = 0.02
    c._laadbesluit_stand = None


# --- de volging zelf ----------------------------------------------------


def test_de_eerste_ronde_begint_de_volging(make_coordinator):
    c = _c(make_coordinator)
    moment = BEGIN.replace(hour=21, minute=3)
    c._volg_vol_en_verkoop(moment)

    assert c._tekort_volg_sinds == moment.isoformat()
    assert c._tekort_volg_laatst == moment.isoformat()


def test_doorlopende_rondes_en_een_korte_herstart_houden_de_volging(make_coordinator):
    c = _c(make_coordinator)
    c._volg_vol_en_verkoop(BEGIN.replace(minute=1))
    sinds = c._tekort_volg_sinds
    moment = BEGIN.replace(minute=1)
    for _ in range(30):
        moment += timedelta(minutes=1)
        c._volg_vol_en_verkoop(moment)
    # een herstart van een halve minuut, zoals 7 oktober een stuk of tien keer
    c._volg_vol_en_verkoop(moment + timedelta(minutes=1, seconds=30))

    assert c._tekort_volg_sinds == sinds


def test_een_gat_van_meer_dan_een_half_uur_begint_de_volging_opnieuw(make_coordinator):
    c = _c(make_coordinator)
    c._volg_vol_en_verkoop(BEGIN.replace(minute=1))
    later = BEGIN.replace(hour=14)
    c._volg_vol_en_verkoop(later)

    assert c._tekort_volg_sinds == later.isoformat()
    assert c._live_tekortvolging_onvolledig(BEGIN).startswith("live gevolgd sinds")


def test_een_volledig_venster_is_volledig(make_coordinator):
    c = _c(make_coordinator)
    c._tekort_volg_sinds = BEGIN.replace(minute=1).isoformat()
    c._laadbesluit_stand = "loont_niet"

    assert c._live_tekortvolging_onvolledig(BEGIN) is None


def test_geen_laadbesluit_bij_een_accu_die_niet_vol_werd_is_onvolledig(make_coordinator):
    c = _c(make_coordinator)
    c._tekort_volg_sinds = BEGIN.replace(minute=1).isoformat()
    c._laadbesluit_stand = None

    assert c._live_tekortvolging_onvolledig(BEGIN) == "geen laadbesluit vastgelegd sinds 09:00"
    c._vol_voor_nacht = True
    assert c._live_tekortvolging_onvolledig(BEGIN) is None


def test_de_velden_overleven_een_herstart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    for veld in ("_tekort_volg_sinds", "_tekort_volg_laatst", "_tekort_herleid_vandaag"):
        assert veld in PERSISTED_PLAIN_FIELDS


# --- de nacht om 09:00 --------------------------------------------------


def _ochtend(c, tekort_kwh=1.2):
    c._tekortnacht_vandaag_kwh = tekort_kwh
    ochtend = BEGIN + timedelta(days=1, minutes=1)
    c._tekort_volg_laatst = (ochtend - timedelta(minutes=1)).isoformat()
    c._volg_vol_en_verkoop(ochtend)
    return ochtend


def test_de_nacht_van_7_oktober_wordt_economisch_en_niet_planning(make_coordinator):
    c = _c(make_coordinator)
    c.dagverloop = _dagverloop()
    _onvolledig_gevolgd(c)

    ochtend = _ochtend(c)

    assert c._tekort_soort_vandaag == "economisch", c._tekort_reden_vandaag
    assert "laden loonde nergens" in c._tekort_reden_vandaag
    assert "uit het dagverloop; live gevolgd sinds 07-10 21:03" in c._tekort_reden_vandaag
    assert c._tekort_herleid_vandaag == "v5.44"
    assert c._tekort_volg_sinds == ochtend.isoformat(), "het nieuwe venster loopt vanaf nu"

    # en zo komt hij in het dagrecord, en de herleiding laat hem staan
    c._shortfall_check_date = ochtend.date()
    c._update_shortfall_detection(ochtend + timedelta(days=1), "default_smart")
    record = c.reserve_daily_records[-1]
    assert record["tekort_soort"] == "economisch"
    assert record["tekort_soort_herleid"] == "v5.44"
    assert c._herleid_onbekende_tekortnachten() == 0
    assert record["tekort_soort"] == "economisch"
    assert c.get_tekortsoorten()["tekortnachten_planning"] == 0
    assert c._tekort_herleid_vandaag is None


def test_zonder_dagverloop_is_het_onbekend_en_geen_planning(make_coordinator):
    c = _c(make_coordinator)
    c.dagverloop = {}
    _onvolledig_gevolgd(c)

    ochtend = _ochtend(c)

    assert c._tekort_soort_vandaag is None
    assert c._tekort_reden_vandaag.startswith("onbekend: live gevolgd sinds")
    assert c._tekort_herleid_vandaag is None

    c._shortfall_check_date = ochtend.date()
    c._update_shortfall_detection(ochtend + timedelta(days=1), "default_smart")
    soorten = c.get_tekortsoorten()
    assert soorten["tekort_soort_per_nacht"][-1] == "onbekend"
    assert soorten["tekortnachten_planning"] == 0
    assert not any("tekort-dag" in p for p in c._tekortnachten_meldingen()[0])
    # later opnieuw geprobeerd, zodra het dagverloop er wel is
    assert "tekort_soort_herleid" not in c.reserve_daily_records[-1]


def test_verkocht_terwijl_niet_vol_blijft_planning_ook_uit_het_dagverloop(make_coordinator):
    # v5.55: verkocht tegen 28,0 ct, onder de 30 ct van het tekort - geen
    # winst, dus planning. Tegen 51,5 ct (zoals hier tot v5.54 stond) is het
    # sinds v5.55 "verkocht met winst" (test_v555_doorlichting.py).
    def rij(k, tijd):
        if 40 <= k < 44:
            return {"soc": 70 - (k - 40) * 4, "net_w": -1450.0, "accu_w": 1636.0,
                    "prijs_ct": 28.0}
        return _zeven_oktober(k, tijd)

    c = _c(make_coordinator)
    c.dagverloop = _dagverloop(rij)
    _onvolledig_gevolgd(c)

    _ochtend(c)

    assert c._tekort_soort_vandaag == "planning"
    assert "verkocht terwijl de accu niet vol was" in c._tekort_reden_vandaag


def test_een_volledig_gevolgde_nacht_blijft_live(make_coordinator):
    c = _c(make_coordinator)
    c.dagverloop = {}
    _onvolledig_gevolgd(c, sinds=BEGIN.replace(minute=1))
    c._laadbesluit_stand = "loont"

    _ochtend(c)

    assert c._tekort_soort_vandaag == "planning"
    assert c._tekort_reden_vandaag == "bijladen loonde, maar de accu werd niet vol"
    assert c._tekort_herleid_vandaag is None


def test_geen_tekort_geen_soort_ook_bij_onvolledige_volging(make_coordinator):
    c = _c(make_coordinator)
    c.dagverloop = _dagverloop()
    _onvolledig_gevolgd(c)

    _ochtend(c, tekort_kwh=0.2)

    assert c._tekort_soort_vandaag is None
    assert c._tekort_reden_vandaag is None


# --- het verwachte tekort -----------------------------------------------


def _avond(c, monkeypatch, prijs_ct=30.0):
    nu = BEGIN.replace(hour=22, minute=52)
    monkeypatch.setattr(mod.dt_util, "now", lambda: nu)
    c.dagverloop = _dagverloop(tot=56)  # tot en met 22:45
    c.last_reserve_margin_breakdown = {"needed_kwh_before_margin": 5.21}
    c.beschikbare_energie_kwh = lambda: 4.58
    begin = nu.replace(minute=45) + timedelta(minutes=15)
    c._get_forecast_entries = lambda **kw: [
        (begin + timedelta(minutes=15 * i), begin + timedelta(minutes=15 * (i + 1)),
         prijs_ct / 100 * PRICE_SCALE_FACTOR)
        for i in range(40)
    ]
    _onvolledig_gevolgd(c)
    return nu


def test_het_verwachte_tekort_van_7_oktober_is_economisch(make_coordinator, monkeypatch):
    c = _c(make_coordinator)
    _avond(c, monkeypatch)

    verwacht = c.verwacht_tekort()

    assert verwacht["tekort_kwh"] == 0.63
    assert verwacht["tekort_soort"] == "economisch", verwacht
    assert verwacht["soort_bron"] == "dagverloop"
    assert verwacht["live_onvolledig"] == "live gevolgd sinds 07-10 21:03"
    assert verwacht["tracking_since"] == INSTALLATIE.isoformat()
    assert "laden loonde nergens" in verwacht["tekort_reden"]
    assert c._tekort_soort_zin().startswith(" Dit tekort is economisch")


def test_verwacht_tekort_tegen_een_dure_nacht_is_planning(make_coordinator, monkeypatch):
    """Had laden tegen 29,7 ct geloond tegen een nacht van 60 ct
    (60 x 0,843 - 11,22 = 39,4 ct), dan is het wel planning."""
    c = _c(make_coordinator)
    _avond(c, monkeypatch, prijs_ct=60.0)

    verwacht = c.verwacht_tekort()

    assert verwacht["tekort_soort"] == "planning"
    assert verwacht["soort_bron"] == "dagverloop"


def test_verwacht_tekort_zonder_dagverloop_is_onbekend(make_coordinator, monkeypatch):
    c = _c(make_coordinator)
    _avond(c, monkeypatch)
    c.dagverloop = {}

    verwacht = c.verwacht_tekort()

    assert verwacht["tekort_soort"] == "onbekend"
    assert "niet uit het dagverloop te herleiden" in verwacht["tekort_reden"]
    assert c._tekort_soort_zin() == ""
    assert not any("tekort-dag" in p for p in c._tekortnachten_meldingen()[0])


def test_verwacht_tekort_groter_dan_de_accu_blijft_capaciteit(make_coordinator, monkeypatch):
    c = _c(make_coordinator)
    _avond(c, monkeypatch)
    c.last_reserve_margin_breakdown = {"needed_kwh_before_margin": 9.0}
    c.dagverloop = {}

    verwacht = c.verwacht_tekort()

    assert verwacht["tekort_soort"] == "capaciteit"
    assert verwacht["soort_bron"] == "live"


def test_verwacht_tekort_met_volledige_volging_blijft_live(make_coordinator, monkeypatch):
    c = _c(make_coordinator)
    _avond(c, monkeypatch)
    c._tekort_volg_sinds = BEGIN.replace(minute=1).isoformat()
    c._laadbesluit_stand = "loont_niet"

    verwacht = c.verwacht_tekort()

    assert verwacht["tekort_soort"] == "economisch"
    assert verwacht["soort_bron"] == "live"
    assert verwacht["live_onvolledig"] is None

