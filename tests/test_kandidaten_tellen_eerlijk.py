"""Drie proefstandkandidaten die verkeerd telden (v1.0.1).

Uit de export van 15 september, zes tot zeven nabeschouwde dagen:

1. "Sneller laden bij zonoverschot": 14,7 kWh naar het net terwijl de
   accu ruimte had, 505 kwartieren in 7 dagen. Dat is 72 kwartieren per
   DAG - achttien uur. Het dagverloop laat zien wat er meetelde: de
   -40 W die 's nachts naar het net gaat omdat de accu iets meer levert
   dan het huis vraagt. Geen zon, geen overschot, wel geteld.

2. "Reserve uit de nabeschouwing": "gemist door de reserve 2,16 euro
   over 6 dagen". Vier van die zes dagen zijn nabeschouwd VOOR v4.12,
   met de reserve als bodem - het model dat twintig keer te hoge
   bedragen gaf. De kandidaat mengt oude en nieuwe cijfers.

3. "Vooruitplannen over 24 uur": +2,39 euro per dag, 873 per jaar.
   De nabeschouwing - de beste planning met volledige kennis vooraf -
   zegt dat er 0,54 per dag te winnen was. Een kandidaat die MEER
   belooft dan het theoretisch maximum, rekent iets fout of rekent iets
   mee dat het EMS bewust niet doet. In beide gevallen mag dat bedrag
   niet als "betrouwbaar" op de proefstand staan.
"""
import pytest


def _regel(tijd, pv, huis, accu, net, soc, prijs=25.0):
    return {"tijd": tijd, "pv_w": pv, "huis_w": huis, "accu_w": accu, "net_w": net,
            "soc": soc, "prijs_ct": prijs, "reden": "default_smart"}


def test_nachtelijke_export_telt_niet_als_gemiste_zon(make_coordinator, hass):
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.effective_min_soc_percent = lambda: 10.0
    c.dagverloop = {"2026-09-14": [
        _regel("02:00", 0, 180, 220, -40, 50.0),     # nacht: -40 W, geen zon
        _regel("02:15", 0, 180, 220, -40, 50.0),
        _regel("13:00", 3000, 300, -500, -1200, 50.0),   # dag: echt overschot, 1500 W laadruimte
    ]}

    uit = c.gemiste_zonlading("2026-09-14")

    assert uit["kwartieren"] == 1
    assert uit["kwh"] == pytest.approx(0.30, abs=0.01)


def test_een_klein_overschot_overdag_telt_ook_niet(make_coordinator, hass):
    """Onder de 200 W is het regelruis, geen gemiste lading."""
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.effective_min_soc_percent = lambda: 10.0
    c.dagverloop = {"2026-09-14": [_regel("13:00", 1000, 300, -600, -100, 50.0)]}

    assert c.gemiste_zonlading("2026-09-14")["kwartieren"] == 0


def test_de_reservekandidaat_gebruikt_alleen_het_poortmodel(make_coordinator, hass):
    c = make_coordinator({})
    c.nabeschouwingen = [
        {"datum": "2026-09-09", "te_becijferen": True, "kwartieren": 96,
         "gemist_door_reserve_eur": 0.40, "te_veel_vastgehouden_kwh": 0.6, "te_veel_ontladen_kwh": 4.5},
        {"datum": "2026-09-14", "te_becijferen": True, "kwartieren": 96, "reserve_als": "verkooppoort",
         "gemist_door_reserve_eur": 0.02, "te_veel_vastgehouden_kwh": 0.1, "te_veel_ontladen_kwh": 0.3},
    ]

    k = c._kandidaat_reserve_uit_nabeschouwing()

    assert k["status"] == "onvoldoende_data"
    assert "1 volledige dag" in k["onderbouwing"]
    assert "oude model" in k["onderbouwing"]


def test_een_kandidaat_boven_het_theoretisch_maximum_is_niet_betrouwbaar(make_coordinator, hass):
    """De nabeschouwing is de bovengrens. Wie daarboven zit, rekent
    fout of rekent iets mee dat het EMS bewust niet doet."""
    c = make_coordinator({})
    c.nabeschouwingen = [
        {"datum": f"2026-09-{d:02d}", "te_becijferen": True, "kwartieren": 96, "gemist_eur": 0.5}
        for d in range(8, 15)
    ]
    kandidaat = {
        "naam": "Vooruitplannen over 24 uur", "status": "betrouwbaar",
        "zou_hebben_opgeleverd": {"te_becijferen": True, "bedrag_per_dag_eur": 2.39},
    }

    uit = c._toets_tegen_de_nabeschouwing(kandidaat)

    assert uit["status"] != "betrouwbaar"
    assert "nabeschouwing" in uit["betrouwbaarheid"].lower()
    assert uit["boven_theoretisch_maximum"] is True


def test_een_kandidaat_binnen_het_maximum_blijft_ongemoeid(make_coordinator, hass):
    c = make_coordinator({})
    c.nabeschouwingen = [
        {"datum": f"2026-09-{d:02d}", "te_becijferen": True, "kwartieren": 96, "gemist_eur": 0.5}
        for d in range(8, 15)
    ]
    kandidaat = {"naam": "X", "status": "betrouwbaar",
                 "zou_hebben_opgeleverd": {"te_becijferen": True, "bedrag_per_dag_eur": 0.10}}

    uit = c._toets_tegen_de_nabeschouwing(kandidaat)

    assert uit["status"] == "betrouwbaar"
    assert uit.get("boven_theoretisch_maximum") is False
