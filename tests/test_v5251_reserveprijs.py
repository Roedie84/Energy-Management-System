"""v5.251.0: tweede prijsbron (EnergyZero) als Zonneplan uitvalt."""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import reserveprijs as rp

T0 = datetime(2026, 11, 23, 0, 0, tzinfo=timezone.utc)


def _ez(uren=48, prijs=0.20):
    return rp.lees_energyzero({"prices": [
        {"price": prijs + 0.001 * (h % 5), "start": str(T0 + timedelta(hours=h)),
         "end": str(T0 + timedelta(hours=h + 1))} for h in range(uren)]})


def _zonneplan(kwartieren, opslag_incl=0.12, opslag_excl=0.03, prijs=0.20):
    uit = []
    for q in range(kwartieren):
        t = T0 + timedelta(minutes=15 * q)
        ez = prijs + 0.001 * ((q // 4) % 5)
        uit.append({"start_date": t.isoformat(), "end_date": (t + timedelta(minutes=15)).isoformat(),
                    "price_tax_included": {"amount": round((ez + opslag_incl) * 1e7)},
                    "price_tax_excluded": {"amount": round((ez + opslag_excl) * 1e7)}})
    return uit


def test_het_antwoord_van_energyzero_wordt_gelezen():
    r = _ez(3)
    assert len(r) == 3 and r[0]["prijs"] == 0.2
    assert r[0]["start"].startswith("2026-11-23T00:00")


def test_de_opslag_wordt_geleerd_en_pas_met_genoeg_kwartieren_gebruikt():
    v = rp.leer_verschillen({}, _zonneplan(40), _ez())
    assert rp.opslag(v) is None              # te weinig
    v = rp.leer_verschillen(v, _zonneplan(96), _ez())
    o = rp.opslag(v)
    assert abs(o["incl_eur"] - 0.12) < 1e-4 and abs(o["excl_eur"] - 0.03) < 1e-4
    assert o["kwartieren"] == 96


def test_reserve_in_zonneplanformaat_en_aanvullen_na_de_bewaarde_reeks():
    geleerd = {"incl_eur": 0.12, "excl_eur": 0.03}
    items = rp.als_zonneplan(_ez(48), geleerd)
    assert len(items) == 192
    assert items[0]["price_tax_included"]["amount"] == round(0.32 * 1e7)
    bewaard = _zonneplan(96)                  # tot middernacht
    uit = rp.vul_aan(bewaard, items)
    assert len(uit) == 192                    # morgen komt uit de reserve
    assert uit[96]["bron"] == "energyzero"
    assert uit[96]["start_date"] == (T0 + timedelta(days=1)).isoformat()


def test_het_ingekorte_geheugen():
    v = {}
    for d in range(10):
        dag = [dict(i, start_date=(datetime.fromisoformat(i["start_date"]) + timedelta(days=d)).isoformat())
               for i in _zonneplan(96)]
        ez = [dict(r, start=(datetime.fromisoformat(r["start"]) + timedelta(days=d)).isoformat(),
                   eind=(datetime.fromisoformat(r["eind"]) + timedelta(days=d)).isoformat()) for r in _ez(24)]
        v = rp.leer_verschillen(v, dag, ez)
    assert len(v) == rp.OPSLAG_BEWAARD


def test_de_coordinator_vult_een_storing_aan(make_coordinator, hass, monkeypatch):
    from homeassistant.util import dt as dt_util

    c = make_coordinator({"price_sensor_entity": "sensor.zonneplan"})
    monkeypatch.setattr(dt_util, "now", lambda *a: T0 + timedelta(hours=10))
    c.prijs_forecast_cache = {"sensor": "sensor.zonneplan", "om": T0.isoformat(), "forecast": _zonneplan(96)}
    c.reserveprijs = {"om": T0.isoformat(), "reeks": _ez(48)}
    c.reserveprijs_verschillen = rp.leer_verschillen({}, _zonneplan(96), _ez(48))

    uit = c._forecast_met_cache("sensor.zonneplan", None)

    assert len(uit) == 192 - 40               # vanaf 10:00, tot en met morgen
    assert c._prijsbron_terugval == "bewaarde reeks + energyzero"
    assert c.get_reserveprijs()["in_gebruik"] is True


def test_zonder_geleerde_opslag_blijft_het_bij_de_bewaarde_reeks(make_coordinator, hass, monkeypatch):
    from homeassistant.util import dt as dt_util

    c = make_coordinator({"price_sensor_entity": "sensor.zonneplan"})
    monkeypatch.setattr(dt_util, "now", lambda *a: T0 + timedelta(hours=10))
    c.prijs_forecast_cache = {"sensor": "sensor.zonneplan", "om": T0.isoformat(), "forecast": _zonneplan(96)}
    c.reserveprijs = {"om": T0.isoformat(), "reeks": _ez(48)}
    c.reserveprijs_verschillen = {}

    uit = c._forecast_met_cache("sensor.zonneplan", None)

    assert len(uit) == 96 - 40
    assert c._prijsbron_terugval == "bewaarde reeks"


import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_ophalen_vraagt_kwartieren_en_leert_van_de_levende_reeks(make_coordinator, hass):
    from types import SimpleNamespace

    c = make_coordinator({"price_sensor_entity": "sensor.zonneplan"})
    gevraagd = {}

    vragen = []

    async def _roep(domein, dienst, data, blocking, return_response):
        vragen.append(data)
        if len(vragen) == 2:
            raise RuntimeError("No price data available for morgen")   # v5.251.1
        gevraagd.update(data)
        gevraagd["domein"], gevraagd["dienst"] = domein, dienst
        return {"prices": [{"price": r["prijs"], "start": r["start"], "end": r["eind"]} for r in _ez(24)]}

    c.hass.services = SimpleNamespace(async_call=_roep)
    c.hass.states.get = lambda e: SimpleNamespace(attributes={"forecast": _zonneplan(192)}) \
        if e == "sensor.zonneplan" else None
    c.schedule_persisted_state_save = lambda: None

    await c._async_reserveprijs_halen("abc", T0 + timedelta(hours=10))

    assert c._reserveprijs_fout is None, c._reserveprijs_fout
    assert gevraagd["domein"] == "energyzero" and gevraagd["interval"] == "quarter"
    assert gevraagd["config_entry"] == "abc" and gevraagd["incl_vat"] is True
    assert c.get_reserveprijs()["opslag"]["kwartieren"] == 96
    # v5.251.1: per dag gevraagd, tot 23:59; morgen mag mislukken
    assert len(vragen) == 2 and gevraagd["end"].endswith("23:59:00")
    assert gevraagd["start"][:10] == gevraagd["end"][:10]
    assert c._reserveprijs_bezig is False
