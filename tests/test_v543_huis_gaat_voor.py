"""v5.43: het huis gaat voor - energie onder de reserve wordt nooit verkocht.

Nagerekend naar aanleiding van de twee planningsnachten van v5.42:

- nacht naar 3 oktober: 2 oktober 19:00-20:00 `expensive_quarter_peak`;
- nacht naar 4 oktober: 3 oktober 19:55-22:26 `expensive_quarter_peak`.

Beide door de piekregel (v5.22, sinds v5.26.3 vóór de huisgrens), verholpen
in v5.28.4. Deze toetsen leggen dat vast, plus de twee gaten die er daarna
nog waren: de lange horizon die een ronde achterliep (na een herstart nul),
en de secundaire prijslaag die een NEE van de verkooptoets om een andere
reden dan de reserve negeerde.
"""
import asyncio

from gouden_scenarios import DAG, _config, _prijs_dag, draai


def _verkoopt(uitkomst) -> bool:
    return any(
        d == "number" and (data.get("value") or 0) > 0
        for d, _srv, data in uitkomst["opdrachten"]
    )


# --- regressie v5.28.4: de piekregel verkoopt niet onder de reserve ------


def test_avondpiek_met_lading_onder_de_reserve_verkoopt_niet(make_coordinator, hass):
    """Duurste kwartier tot het blok (51 ct om 19:30), accu onder de
    reserve: vóór v5.28.4 was dit `expensive_quarter_peak` tot de bodem."""
    uitkomst = draai(make_coordinator, hass, "avondpiek_laag")
    c = draai.laatste

    assert uitkomst["reden"] != "expensive_quarter_peak"
    assert not _verkoopt(uitkomst)
    assert c.last_sell_check["mag_verkopen"] is False


def test_de_piekregel_passeert_de_huisgrens_niet(make_coordinator, hass):
    c = make_coordinator({})
    c.may_sell_now = lambda now, beschikbaar=None: {
        "mag_verkopen": False,
        "reden": "huis gaat voor",
    }
    # Ook als de prijs nu de duurste is tot het blok.
    c._piekverkoop = lambda *a, **k: {"verkopen": True}

    ruimte = c._verkoopruimte_met_piek(DAG.replace(hour=19), [], None, 2.0)

    assert ruimte["mag_verkopen"] is False


def test_geen_ruimte_boven_de_reserve_geeft_geen_vermogen(make_coordinator, hass):
    c = make_coordinator({})

    assert (
        c._geen_ruimte_boven_reserve(DAG.replace(hour=19), [], None, 3.0, 5.0, 2400, 0.25)
        is None
    )
    assert c.last_piekverkoop["verkopen"] is False


# --- v5.43: de lange horizon telt in dezelfde ronde ---------------------


def _ronde_met_lange_horizon(make_coordinator, hass, monkeypatch, extra_kwh):
    from conftest import make_price_forecast
    from custom_components.energy_management_system import coordinator as coord_mod

    vandaag = make_price_forecast(DAG, _prijs_dag)
    morgen = make_price_forecast(DAG + coord_mod.timedelta(days=1), _prijs_dag)
    hass.states.set("sensor.price", "0", {"forecast": vandaag + morgen})
    hass.states.set("sensor.p1", "350")
    hass.states.set("sensor.available_energy", "7.5")
    hass.states.set("sensor.capaciteit", "8.64")
    hass.states.set("sensor.pv", "0")
    hass.states.set("select.op", "smart")
    hass.states.set("number.pow", "0")
    c = make_coordinator(_config())
    c.learned_efficiency_history = [83.8] * 7
    # Net herstart: de lange horizon is nog niet gemeten.
    c._lange_reserve_extra_kwh = 0.0
    volgorde = []

    def meet(self, now, entries):
        volgorde.append("meet")
        self._lange_reserve_extra_kwh = extra_kwh

    echte_reserve = coord_mod.EnergyManagementSystemCoordinator._bereken_dynamische_reserve_kwh

    def reserve(self, *a, **k):
        volgorde.append("reserve")
        return echte_reserve(self, *a, **k)

    monkeypatch.setattr(coord_mod.EnergyManagementSystemCoordinator, "_meet_lange_reserve", meet)
    # Het diepste tekort zoals in bedrijf (met uurprofiel): de lange horizon
    # komt daar bovenop. 5,425 kWh x 1,25 = 6,78 kWh korte reserve.
    monkeypatch.setattr(
        coord_mod.EnergyManagementSystemCoordinator,
        "_estimate_worst_case_deficit_kwh",
        lambda self, now, tot: 5.425,
    )
    monkeypatch.setattr(
        coord_mod.EnergyManagementSystemCoordinator, "_bereken_dynamische_reserve_kwh", reserve
    )
    moment = DAG.replace(hour=19, minute=30)
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: moment)
    hass.services.calls.clear()
    # Zoals in bedrijf: een rondestempel, dus één reserve per ronde (v5.42).
    # Zonder stempel rekent elke lezer opnieuw en is het gat niet te zien.
    c._begin_ronde_cache(moment)
    asyncio.run(c._async_update_locked())
    opdrachten = [
        [d, srv, data] for d, srv, data in hass.services.calls if d in ("select", "number")
    ]
    return c, {"reden": c.last_reason, "opdrachten": opdrachten}, volgorde


def test_de_lange_horizon_wordt_gemeten_voor_de_eerste_reserve(
    make_coordinator, hass, monkeypatch
):
    _c, _uitkomst, volgorde = _ronde_met_lange_horizon(
        make_coordinator, hass, monkeypatch, 0.0
    )

    assert "meet" in volgorde and "reserve" in volgorde
    assert volgorde.index("meet") < volgorde.index("reserve")


def test_eerste_ronde_na_herstart_verkoopt_niet_onder_de_lange_reserve(
    make_coordinator, hass, monkeypatch
):
    """7,5 kWh tegen een korte reserve van 6,78: zonder lange horizon wordt
    er verkocht (gouden scenario `avondpiek_vol`). Met 1,9 kWh lange
    horizon is de reserve 8,6 kWh, en dan niet - ook in de eerste ronde na
    een herstart, toen het deel na het blok nog op nul stond."""
    c, uitkomst, _ = _ronde_met_lange_horizon(make_coordinator, hass, monkeypatch, 1.9)

    assert not _verkoopt(uitkomst)
    assert c.last_reason not in ("expensive_quarter", "expensive_quarter_peak")
    assert c.last_sell_check["mag_verkopen"] is False
    assert c.last_reserve_margin_breakdown["lange_horizon_extra_kwh"] == 1.9


def test_zonder_lange_horizon_blijft_de_verkoop_boven_de_reserve(
    make_coordinator, hass, monkeypatch
):
    """Tegenproef: de verplaatsing zelf verandert niets aan verkopen BOVEN
    de reserve."""
    _c, uitkomst, _ = _ronde_met_lange_horizon(make_coordinator, hass, monkeypatch, 0.0)

    assert uitkomst["reden"] == "expensive_quarter"
    assert _verkoopt(uitkomst)


# --- v5.43: de secundaire laag luistert naar elk NEE van de verkooptoets --


def test_secundaire_laag_dicht_als_de_verkooptoets_nee_zegt(make_coordinator, hass):
    c = make_coordinator({})
    c._verkoop_geblokkeerd_door_reserve = False
    c.last_sell_check = {
        "mag_verkopen": False,
        "methode": "planning voorziet een tekort",
    }

    assert c._secundaire_laag_toegestaan() is False


def test_secundaire_laag_open_als_de_verkooptoets_ja_zegt(make_coordinator, hass):
    c = make_coordinator({})
    c._verkoop_geblokkeerd_door_reserve = False
    c.last_sell_check = {"mag_verkopen": True}

    assert c._secundaire_laag_toegestaan() is True


def test_een_voorzien_tekort_blokkeert_ook_de_secundaire_laag(
    make_coordinator, hass, monkeypatch
):
    """Volledige ronde: de planning voorziet een tekort (de echte
    nachtbehoefte ligt boven de reserve), de secundaire laag ziet ruimte
    boven de reserve. Vóór v5.43 verkocht hij dan alsnog."""
    from custom_components.energy_management_system import coordinator as coord_mod

    klasse = coord_mod.EnergyManagementSystemCoordinator
    monkeypatch.setattr(
        klasse,
        "may_sell_now",
        lambda self, now, beschikbaar=None: {
            "mag_verkopen": False,
            "methode": "planning voorziet een tekort",
            "reden": "Niet verkopen: de planning voorziet een tekort.",
        },
    )
    monkeypatch.setattr(klasse, "_is_expensive_now", lambda self, entries, now: False)
    monkeypatch.setattr(
        klasse, "_is_worth_discharging_at_secondary_tier", lambda self, *a, **k: True
    )

    uitkomst = draai(make_coordinator, hass, "avondpiek_vol")
    c = draai.laatste

    assert c.last_expensive_tier is None
    assert not _verkoopt(uitkomst)
    assert uitkomst["reden"] not in ("expensive_quarter", "expensive_quarter_peak")


# --- v5.43: "Wat doet de integratie nu" ---------------------------------


def test_de_toestand_eindigt_op_een_zinsgrens(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import LiveNarrativeSensor

    c = make_coordinator({})
    zin = "De accu dekt het huis en er wordt niet verkocht. "
    tekst = zin * 4 + "Diepste-tekort-berekening (het tekort onderweg) " + "x" * 200
    c.get_live_narrative = lambda now: tekst
    sensor = LiveNarrativeSensor(c, "entry1")

    staat = sensor.native_value
    assert len(staat) <= 255
    assert staat.endswith("verkocht. …")
    assert "Diepste" not in staat
    assert sensor.extra_state_attributes["volledige_tekst"] == tekst
    assert sensor.extra_state_attributes["ingekort"] is True


def test_een_korte_tekst_blijft_heel(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import LiveNarrativeSensor

    c = make_coordinator({})
    c.get_live_narrative = lambda now: "Alles rustig."
    sensor = LiveNarrativeSensor(c, "entry1")

    assert sensor.native_value == "Alles rustig."
    assert sensor.extra_state_attributes["ingekort"] is False


def test_een_decimaalpunt_is_geen_zinsgrens():
    from custom_components.energy_management_system.sensor import kort_op_zinsgrens

    tekst = "Beschikbaar 4.84 kWh " + "en nog meer woorden " * 20

    uitkomst = kort_op_zinsgrens(tekst, 60)
    assert len(uitkomst) <= 60
    assert uitkomst.endswith("…")
    assert not uitkomst.startswith("Beschikbaar 4.…")


def test_de_smart_modus_heet_niet_meer_bijladen(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reason = "default_smart"
    c.last_has_enough_energy = False
    c.last_available_kwh = 4.84
    c.last_needed_kwh_to_bridge = 7.19

    tekst = c._build_explanation()

    assert "zelf bijladen" not in tekst
    assert "laden bij zonoverschot, ontladen voor het huis" in tekst
