"""v5.175.0 punt 3 - "Den accu kump tekort" en "Verkopen geet neet" volgen het
waardeplan.

03-11 14:59 (eerste ronde na de herstart): "Den accu kump tekort" voor
20:15-06:00 (39 kwartieren, laagste 10 %) terwijl het waardeplan 20 % vasthield
(~1,1 kWh, accu 0 W, geen tekortvlag); de echte tekortkwartieren zijn morgen
19:30-23:45. `verwacht_tekort` zei 3,3 kWh. Tegelijk "Verkopen geet neet"
zonder één verkoopkwartier in het plan.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import coordinator as C

TZ = timezone.utc
T0 = datetime(2026, 11, 3, 14, 0, tzinfo=TZ)   # 15:00 lokaal


def _rij(i, actie, inhoud, net, kwh=0.0):
    return {"begin": T0 + timedelta(minutes=15 * i), "actie": actie, "kwh": kwh, "accu_kwh": 0.0,
            "net_kwh": net, "inhoud_kwh": inhoud, "inhoud_delta_kwh": 0.0, "prijs_eur": 0.45}


def _plan_03_11():
    """15:00-20:00 huis tot 1,1 kWh, 20:15-06:00 houden (1,1 kWh), 06:00
    laden, overdag zon, morgen 19:30-23:45 leeg (tekort)."""
    rijen = [_rij(i, "huis", 3.0 - i * 0.1, 0.0) for i in range(20)]           # 15:00-19:45
    rijen += [_rij(20 + i, "houden", 1.1, 0.15) for i in range(41)]           # 20:00-06:00
    rijen += [_rij(61, "laden_net", 1.7, 0.7, 0.6)]                           # 06:15
    rijen += [_rij(62 + i, "huis", max(0.0, 1.7 - i * 0.05), 0.0) for i in range(56)]  # tot 20:00 morgen
    rijen += [_rij(118 + i, "houden", 0.0, 0.15) for i in range(18)]          # 19:30-23:45 morgen
    return rijen


def _c(make_coordinator, rijen=None, waardeplan=None):
    c = make_coordinator({})
    c._waardeplan_rijen = _plan_03_11() if rijen is None else rijen
    c.last_waardeplan = {"beschikbaar": True} if waardeplan is None else waardeplan
    return c


def test_tekort_uit_het_waardeplan(make_coordinator, hass):
    t = _c(make_coordinator).waardeplan_tekort()
    assert t["tot_bijladen_kwh"] == 0.0                      # vasthouden is geen tekort
    assert t["na_bijladen_kwh"] == round(18 * 0.15, 2)
    assert len(t["perioden"]) == 1 and t["perioden"][0].endswith("00:00")
    assert t["vastgehouden_kwh"] == 1.1


def test_geen_waardeplan_geen_plantekort(make_coordinator, hass):
    c = _c(make_coordinator, waardeplan={"beschikbaar": False})
    assert c.waardeplan_tekort() is None


def test_verwacht_tekort_telt_de_vastgehouden_lading(make_coordinator, hass):
    c = _c(make_coordinator)
    c._nodig_tot_en_na_blok_kwh = lambda: (4.4, 0.0)
    c.beschikbare_energie_kwh = lambda: 1.1
    v = c.verwacht_tekort()
    assert v["tekort_kwh"] == 0.0                            # was 3,3 (reserve - inhoud)
    assert v["verwacht_tekort_na_blok_kwh"] == 2.7
    assert v["tekort_bron"] == "waardeplan"
    assert v["plan_vastgehouden_kwh"] == 1.1


def test_verwacht_tekort_zonder_waardeplan_ongewijzigd(make_coordinator, hass):
    c = _c(make_coordinator, waardeplan={"beschikbaar": False})
    c._nodig_tot_en_na_blok_kwh = lambda: (4.4, 0.0)
    c.beschikbare_energie_kwh = lambda: 1.1
    v = c.verwacht_tekort()
    assert v["tekort_kwh"] == 3.3 and v["tekort_bron"] == "reserve"


def test_verkoopmelding_alleen_als_het_plan_wilde_verkopen(make_coordinator, hass):
    c = _c(make_coordinator)
    c.last_sell_check = {"mag_verkopen": False, "reden": "oude verkooptoets"}
    assert c._verkoopblokkade_voor_melding() == {}
    c.last_waardeplan = {"beschikbaar": True, "verkoop_tegengehouden": "onder de verkoopreserve"}
    blok = c._verkoopblokkade_voor_melding()
    assert blok["mag_verkopen"] is False and "verkoopreserve" in blok["reden"]


def test_verkoopmelding_zonder_waardeplan_de_oude_toets(make_coordinator, hass):
    c = _c(make_coordinator, waardeplan={"beschikbaar": False})
    c.last_sell_check = {"mag_verkopen": False, "reden": "oude verkooptoets"}
    assert c._verkoopblokkade_voor_melding()["reden"] == "oude verkooptoets"


def _regel(i, voor_bijladen=True):
    begin = T0 + timedelta(minutes=15 * i)
    return {"start": begin.isoformat(), "van": f"{begin:%H:%M}", "tot": "", "dag": "",
            "modus": "smart", "soc_kwh": 0.0, "net_kwh": 0.2, "uren": 0.25,
            "voor_bijladen": voor_bijladen, "tekort": True}


def test_tabel_telt_tekort_tot_de_netlading_van_het_plan(make_coordinator, hass):
    c = _c(make_coordinator)
    c.bruikbare_capaciteit_kwh = lambda: 11.52
    c.effective_min_soc_percent = lambda: 10.0
    # de oude planning: tekort 20:15-06:00, 'voor bijladen' tot 06:00
    plan = [_regel(i, voor_bijladen=i < 61) for i in range(136)]
    nieuw = c._met_waardeplan(plan)
    assert c._tel_tekorten_tot_bijladen(nieuw) == 0
    assert c._tekort_perioden(nieuw) == []
    assert c._tel_tekorten_tot_bijladen(plan) > 30            # zo kwam de melding


def test_waardeplan_ververst_het_kwartierplan(make_coordinator, hass):
    c = _c(make_coordinator)
    c._kwartierplan_cache = ("oud", [{"start": "x"}])
    c.beschikbare_energie_kwh = lambda: 1.0
    c.bereken_waardeplan = lambda now, entries: {"beschikbaar": False, "reden": "test"}
    c._waardeplan_cache = None
    c._waardeplan_nu(T0, [])
    assert c._kwartierplan_cache is None
    assert c._waardeplan_rijen is None


def test_eerste_ronde_na_herstart_telt_het_waardeplan(make_coordinator, hass):
    """Het kwartierplan werd eerder in de ronde gecachet zonder waardeplan;
    na het rekenen van het waardeplan telt de tabel diens rijen."""
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 11.52
    c.effective_min_soc_percent = lambda: 10.0
    oud = [_regel(i, voor_bijladen=i < 61) for i in range(136)]
    c._waardeplan_rijen = None
    assert c._tel_tekorten_tot_bijladen(c._met_waardeplan(oud)) > 30
    c._kwartierplan_cache = ("ronde", c._met_waardeplan(oud))
    c.beschikbare_energie_kwh = lambda: 1.1
    rijen = _plan_03_11()

    def _bereken(now, entries):
        c._waardeplan_rijen = rijen
        return {"beschikbaar": True, "inhoud_kwh": 1.1, "nu": {}}

    c.bereken_waardeplan = _bereken
    c._waardeplan_cache = None
    c._waardeplan_nu(T0, [])
    assert c._kwartierplan_cache is None
    assert c._tel_tekorten_tot_bijladen(c._met_waardeplan(oud)) == 0
