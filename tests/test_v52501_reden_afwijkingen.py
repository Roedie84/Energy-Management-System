"""v5.250.1: reden_afwijkingen kreeg sinds v4.22 nooit iets.

De nabeschouwing gaf de acties van de beste planning niet terug, dus
_leer_reden_afwijkingen stopte altijd bij `if not acties`. De
stilstandcontrole van v5.2 ving het pas op 23-11 in de cockpit.
"""
from datetime import datetime, timedelta, timezone

from tests.test_nabeschouwing import _ronde


def _dag(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}
    c.reden_afwijkingen = {}
    c.meting_laatst_gevuld = {}
    c.nabeschouwingen = []
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.effective_min_soc_percent = lambda: 10.0
    c._plan_zelfanalyse = lambda *_: None
    t0 = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    for q in range(96):
        uur = q // 4
        prijs = 0.10 if 12 <= uur < 15 else (0.40 if 18 <= uur < 21 else 0.25)
        _ronde(c, hass, t0 + timedelta(minutes=15 * q), soc=40.0, pv=0.0,
               huis=400.0, net=400.0, accu=0.0, prijs=prijs)
    for r in c.dagverloop["2026-09-08"]:
        r["reden"] = r.get("reden") or ("dure prijs" if r["tijd"] >= "18:00" else "wachten")
    return c


def test_de_dagwissel_vult_reden_afwijkingen(make_coordinator, hass):
    c = _dag(make_coordinator, hass)
    c._sluit_dag_af_met_nabeschouwing("2026-09-08")

    assert c.reden_afwijkingen, "nog steeds leeg"
    assert sum(len(v) for v in c.reden_afwijkingen.values()) == 96
    assert "reden_afwijkingen" in c.meting_laatst_gevuld
    # de beste planning ontlaadde in het dure blok, wij niet
    assert sum(sum(v) for v in c.reden_afwijkingen.values()) > 0
    # de acties worden niet bewaard (opslag)
    assert "acties" not in c.nabeschouwingen[-1]
    assert c.get_reden_afwijkingen()


def test_de_diagnose_leert_niet_mee(make_coordinator, hass):
    c = _dag(make_coordinator, hass)
    uit = c.get_nabeschouwing("2026-09-08")
    uit2 = c.get_nabeschouwing("2026-09-08")

    assert uit["te_becijferen"] and uit2["te_becijferen"]
    assert "acties" not in uit
    assert c.reden_afwijkingen == {}
    assert "reden_afwijkingen" not in c.meting_laatst_gevuld
