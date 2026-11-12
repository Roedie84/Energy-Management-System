"""v5.228.0 - meetvelden uit de dagcontrole van 12-11 (alleen meten).

11-11 verkocht de accu niets terwijl de avondpiek 61-68 ct was. Achteraf
bleek de knop "Verkopen uit" van 11:08 tot middernacht aan te staan; dat
stond nergens in het dagverloop. En de telling van de live wissels van
gisteren was om 00:00 weg.
"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 11, 16, 20, tzinfo=TZ)


def _c(make_coordinator):
    c = make_coordinator({"salderen_end_date": "2026-12-31", "update_interval_seconds": 60})
    c._read_corrected_consumption_power = lambda: 600.0
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    return c


def test_dagverloop_bewaart_de_knop_verkopen_uit(make_coordinator):
    c = _c(make_coordinator)
    c._leg_dagverloop_vast(NU)
    assert c.dagverloop[NU.date().isoformat()][-1]["verkoop_pauze"] is False
    c.zet_verkoop_pauze(True, now=NU)
    c._leg_dagverloop_vast(NU + timedelta(minutes=15))
    assert c.dagverloop[NU.date().isoformat()][-1]["verkoop_pauze"] is True


def test_dagverloop_knop_fout_breekt_niets(make_coordinator):
    c = _c(make_coordinator)

    def stuk(now=None):
        raise RuntimeError("stuk")

    c.verkoop_pauze_actief = stuk
    c._leg_dagverloop_vast(NU)
    assert c.dagverloop[NU.date().isoformat()][-1]["verkoop_pauze"] is None


def test_herplanningen_van_gisteren_blijven_bewaard(make_coordinator):
    c = _c(make_coordinator)
    c._tel_herplanning(NU, "live_wissel")
    c._tel_herplanning(NU, "live_wissel")
    c.waardeplan_herplanningen["live_wissel_eur"] = 0.031
    morgen = NU + timedelta(days=1)
    c._tel_herplanning(morgen, "midkwartier")
    gisteren = c.waardeplan_herplanningen_gisteren
    assert gisteren["dag"] == "2026-11-11"
    assert gisteren["live_wissel"] == 2 and gisteren["live_wissel_eur"] == 0.031
    assert not any(k.startswith("_") for k in gisteren)
    assert c.waardeplan_herplanningen["dag"] == "2026-11-12"
    assert c.waardeplan_herplanningen["midkwartier"] == 1


def test_eerste_telling_zonder_gisteren(make_coordinator):
    c = _c(make_coordinator)
    c._tel_herplanning(NU, "midkwartier")
    assert c.waardeplan_herplanningen_gisteren is None
