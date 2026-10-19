"""v5.100: de koppeling in de coordinator - schaduwregime, invoer en rekenwerk."""
import threading
from datetime import datetime, timezone

from custom_components.energy_management_system import keuzeoordeel, regime2027
from custom_components.energy_management_system.coordinator import _reken_zelfanalyse

NU = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def test_schaduwregime_geldt_alleen_in_de_eigen_draad(make_coordinator, hass):
    c = make_coordinator({})
    assert c._is_salderen_active(NU) is True
    c._regime_2027_draad = threading.get_ident()
    assert c._is_salderen_active(NU) is False
    c._regime_2027_draad = threading.get_ident() + 1
    assert c._is_salderen_active(NU) is True
    c._regime_2027_draad = None


def test_r27_velden_vragen_de_regels_in_het_regime_van_2027(make_coordinator, hass):
    c = make_coordinator({})
    gezien = []

    def opvangen(now):
        gezien.append(c._is_salderen_active(now))
        return True

    c.should_capture_surplus_over_selling = opvangen
    c._verkoop_loont_na_saldering = lambda now: {"mag_verkopen": False}
    c._get_feedin_value_per_kwh = lambda entries, now: 0.0712345
    uit = c._r27_velden(NU)
    assert gezien == [False]
    assert uit == {"r27_opvangen": True, "r27_verkoop": False, "r27_export": 0.07123}
    assert c._regime_2027_draad is None and c._is_salderen_active(NU) is True


def test_r27_velden_zet_het_regime_ook_na_een_fout_terug(make_coordinator, hass):
    c = make_coordinator({})

    def kapot(now):
        raise RuntimeError("stuk")

    c.should_capture_surplus_over_selling = kapot
    try:
        c._r27_velden(NU)
    except RuntimeError:
        pass
    assert c._regime_2027_draad is None


def _dagverloop():
    rijen = []
    for i in range(96):
        uur = i // 4
        rijen.append({
            "tijd": f"{uur:02d}:{i % 4 * 15:02d}", "reden": "discharging_window" if uur < 17 else "default_smart",
            "stand": "smart_discharging" if uur < 17 else "smart", "soc": 60 - i * 0.3,
            "pv_w": 1200.0 if 10 <= uur < 15 else 0.0, "huis_w": 400.0, "accu_w": 400.0 if uur >= 17 else 0.0,
            "prijs_ct": 45.0 if 17 <= uur < 21 else 30.0,
            "r27_opvangen": 10 <= uur < 15, "r27_verkoop": True, "r27_export": 0.08,
        })
    return rijen


def test_invoer_en_rekenwerk_van_een_hele_dag(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {"2026-10-18": _dagverloop()}
    c.bruikbare_capaciteit_kwh = lambda: 8.0
    invoer = c._zelfanalyse_invoer("2026-10-18")
    assert invoer["te_becijferen"] and len(invoer["kwartieren"]) == 96
    oordeel, repetitie = _reken_zelfanalyse(invoer, keuzeoordeel, regime2027)
    assert oordeel["te_becijferen"] and oordeel["keuzes"] == 2
    # het zonoverschot ging de accu niet in (smart_discharging): dat kostte iets
    assert any(k["richting"] == "te weinig zon opgevangen" for k in oordeel["niet_de_beste"])
    assert repetitie["te_becijferen"] and repetitie["datum"] == "2026-10-18"
    assert repetitie["accu_levert_op_2027_eur"] > repetitie["accu_levert_op_nu_eur"]


def test_te_korte_dag_geeft_een_reden(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {"2026-10-18": _dagverloop()[:20]}
    invoer = c._zelfanalyse_invoer("2026-10-18")
    assert invoer["te_becijferen"] is False and "van de" in invoer["reden"]


def test_getters_zonder_gegevens(make_coordinator, hass):
    c = make_coordinator({})
    z = c.get_zelfanalyse()
    assert z["gisteren"] is None and z["kaart_primair"].startswith("€ 0,00")
    r = c.get_repetitie_2027()
    assert r["kaart_primair"] == "Generale repetitie 2027" and r["salderen_tot"] == "2026-12-31"
    p = c.get_prijsverwachting()
    assert p["beschikbaar"] is False and p["kaart_secundair"] == "nog geen verwachting"
    namen = [i["naam"] for i in c.get_meet_stuurt_niet()["items"]]
    assert "Prijsverwachting overmorgen" in namen and "Regels van 2027 (na de saldering)" in namen


def test_achterstand_en_wachtrij(make_coordinator, hass):
    import asyncio

    c = make_coordinator({})
    c.dagverloop = {"2026-10-16": _dagverloop(), "2026-10-17": _dagverloop(), "2026-10-18": _dagverloop()[:10]}
    c.bruikbare_capaciteit_kwh = lambda: 8.0
    taken = []
    c._start_achtergrondtaak = lambda coro, naam: taken.append(coro) or True

    async def executor(fn, *args):
        return fn(*args)

    c.hass.async_add_executor_job = executor
    gemeld = []
    c._meld_keuzes_achteraf = lambda oordeel: gemeld.append(oordeel["datum"])
    c._plan_zelfanalyse_achterstand(NU)
    c._plan_zelfanalyse("2026-10-18")          # dagwissel terwijl de achterstand loopt
    assert len(taken) == 1 and c._zelfanalyse_wachtrij == ["2026-10-18"]
    asyncio.run(taken[0])
    assert [d["datum"] for d in c.keuzeoordelen] == ["2026-10-16", "2026-10-17", "2026-10-18"]
    assert c.keuzeoordelen[-1]["te_becijferen"] is False   # te kort
    assert gemeld == ["2026-10-18"] and c._zelfanalyse_bezig is False


def test_prijsverwachting_loopt_door_zonder_fout(make_coordinator, hass, monkeypatch):
    import asyncio
    import math
    from datetime import timedelta

    from custom_components.energy_management_system import prijsverwachting as P

    c = make_coordinator({})
    begin = datetime(2026, 9, 1, tzinfo=timezone.utc)
    weer_uren, tijden = {"wind_speed_100m": [], "shortwave_radiation": [], "temperature_2m": []}, []
    for h in range(55 * 24):
        t = begin + timedelta(hours=h)
        lok = t.astimezone(P.TZ)
        if t < datetime(2026, 10, 20, tzinfo=timezone.utc):
            c.prijsgeschiedenis[P.uur_sleutel(t)] = 0.30 + (0.1 if 17 <= lok.hour < 21 else 0.0) - 0.002 * (15 + 10 * math.sin(h / 30))
        tijden.append(t.strftime("%Y-%m-%dT%H:00"))
        weer_uren["wind_speed_100m"].append(15 + 10 * math.sin(h / 30))
        weer_uren["shortwave_radiation"].append(0.0)
        weer_uren["temperature_2m"].append(10.0)
    antwoord = [{"hourly": {"time": tijden, **weer_uren}}]

    class Antwoord:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        async def json(self):
            return antwoord

    class Sessie:
        def get(self, url):
            assert "open-meteo" in url
            return Antwoord()

    import sys
    import types

    ac = types.ModuleType("homeassistant.helpers.aiohttp_client")
    ac.async_get_clientsession = lambda hass: Sessie()
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.aiohttp_client", ac)

    async def executor(fn, *args):
        return fn(*args)

    c.hass.async_add_executor_job = executor
    c._prijsgeschiedenis_gezaaid = True
    c._get_forecast_entries = lambda: []
    nu = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)
    asyncio.run(c._async_prijsverwachting(nu))
    pv = c.get_prijsverwachting()
    assert pv["fout"] is None, pv["fout"]
    assert pv["beschikbaar"] and pv["dagen"]
    assert pv["backtest_21_dagen"]["dagen"] > 10
    assert c.prijsverwachting_archief and c._prijsverwachting_bezig is False
