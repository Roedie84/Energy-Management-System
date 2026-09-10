"""Hoeveel zon gaat er naar het net terwijl de accu ruimte heeft? (v4.7)

Gemeld op 9 september: "Dit komt waarschijnlijk door stapelwolken in
combinatie met harde wind, waardoor PV-opbrengst fluctueert en de
Zendure zelf dit niet kan bijbenen." Uit het dagverloop van 8 september:

    14:15  pv 2999   accu −2024   net −534
    14:30  pv 2232   accu  −695   net −1263

De zon zakt 767 W, het laadvermogen zakt 1329 W. Dat is geen beslissing
maar een regellus die doorschiet. In `arbitrage_solar_capture` staat de
accu in de slimme stand en bepaalt het apparaat zelf hoe hard het laadt.

Of dat structureel geld kost, is te meten: tel per kwartier hoeveel zon
er naar het NET ging terwijl de accu nog ruimte had en niet op zijn
laadgrens zat. Dat is de bovengrens van wat handmatig laden zou hebben
opgevangen. Meet; stuurt niet.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 9, 10, 14, 30, tzinfo=timezone.utc)


def _dag(c, regels):
    """regels: (tijd, pv_w, huis_w, accu_w, net_w, soc)"""
    c.dagverloop = {
        "2026-09-08": [
            {"tijd": t, "pv_w": pv, "huis_w": h, "accu_w": a, "net_w": n,
             "soc": soc, "prijs_ct": 25.0, "reden": "arbitrage_solar_capture"}
            for t, pv, h, a, n, soc in regels
        ]
    }
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.effective_min_soc_percent = lambda: 10.0


def test_zon_naar_het_net_met_ruimte_telt(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, [("14:30", 2232, 274, -695, -1263, 60.0)])

    uit = c.gemiste_zonlading("2026-09-08")

    # 1263 W een kwartier lang = 0,316 kWh
    assert uit["kwh"] == pytest.approx(0.32, abs=0.01)
    assert uit["kwartieren"] == 1


def test_zonder_ruimte_telt_niet(make_coordinator, hass):
    """Accu vol: dan is er niets op te vangen."""
    c = make_coordinator({})
    _dag(c, [("14:30", 2232, 274, -695, -1263, 100.0)])

    assert c.gemiste_zonlading("2026-09-08")["kwh"] == 0.0


def test_op_de_laadgrens_telt_niet(make_coordinator, hass):
    """Laadt al op 2000 W: dan kon het apparaat niet harder."""
    c = make_coordinator({})
    _dag(c, [("14:30", 4200, 274, -1980, -1946, 60.0)])

    assert c.gemiste_zonlading("2026-09-08")["kwh"] == 0.0


def test_meer_dan_de_laadruimte_telt_niet_mee(make_coordinator, hass):
    """Er kan hooguit worden opgevangen wat er nog aan laadvermogen
    over is."""
    c = make_coordinator({})
    _dag(c, [("14:30", 5000, 274, -500, -4226, 60.0)])

    # laadruimte 2000 - 500 = 1500 W, niet 4226
    assert c.gemiste_zonlading("2026-09-08")["kwh"] == pytest.approx(0.375, abs=0.01)


def test_de_kandidaat_rekent_over_de_dagen(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}
    c.gemiste_zonlading = lambda dag: {"kwh": 0.8, "kwartieren": 3, "eur": 0.20}
    c.nabeschouwingen = [
        {"te_becijferen": True, "kwartieren": 96, "datum": f"2026-09-0{d}"}
        for d in range(1, 5)
    ]

    k = c._kandidaat_laadsnelheid()

    assert k["waarde"] is not None
    assert k["mag_regelen"] is False
    assert k["zou_hebben_opgeleverd"]["eur_totaal"] == pytest.approx(0.80, abs=0.01)
