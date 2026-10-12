"""v5.93.2: plan en sturing gelijk in het lopende goedkope blok.

Gemeld 12-10 13:16-13:19 met schermafdrukken: het kwartierplan zette
13:15-13:30 op "Laden van net" (2,4 kW), "Wat doet het EMS nu" zei "Netladen
volgt in dit blok (13:15)", maar de sturing laadde niet van het net
(laadbesluit: "de zon vult de accu vanzelf; laden verdringt alleen zon") en
stond op sparen. De planvolging noemde 1,8 kW laden tegen 2,4 kW gepland
"604 W meer ontladen" en "de accu wijkt zelf af".
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import planvolging as pv

TZ = timezone(timedelta(hours=2))
BLOK = datetime(2026, 10, 12, 11, 30, tzinfo=TZ)
BLOK_EIND = datetime(2026, 10, 12, 16, 15, tzinfo=TZ)
KWARTIER = datetime(2026, 10, 12, 13, 15, tzinfo=TZ)
EINDE = KWARTIER + timedelta(minutes=15)
VOL_OM = datetime(2026, 10, 12, 15, 3, tzinfo=TZ)


def _reeks():
    """Blok 30,2-30,3 ct tot 16:15, daarna 34-48 ct."""
    uit, t = [], EINDE
    while t < EINDE + timedelta(hours=24):
        if t < BLOK_EIND:
            p = 0.303
        elif datetime(2026, 10, 12, 18, 45, tzinfo=TZ) <= t < datetime(2026, 10, 12, 19, 15, tzinfo=TZ):
            p = 0.48
        else:
            p = 0.34
        uit.append((t, p))
        t += timedelta(minutes=15)
    return uit


def _coordinator(make_coordinator):
    c = make_coordinator({})
    c._verwacht_zonoverschot_kwh = lambda a, b, veilig=True: 3.0
    c._zon_vol_om = lambda start, beschikbaar, ruimte, eind: VOL_OM
    return c


def _netregels(blok=True):
    regels = {"slijtage_ct": 4.2, "rendement": 83.9, "salderen": True, "reeks": _reeks()}
    if blok:
        regels["blok"] = (BLOK, BLOK_EIND)
    return regels


def test_plan_laadt_niet_als_de_zon_de_accu_vult(make_coordinator):
    c = _coordinator(make_coordinator)
    geladen = c._plan_laadt(_netregels(), EINDE, 0.302, soc=6.4, bruikbaar=7.5,
                            laad_kwh=0.6, per_kwartier=0.6)
    assert geladen == 0.0


def test_zonder_blok_rekent_het_plan_zoals_voorheen(make_coordinator):
    """De oude rekenwijze nam de blokkwartieren mee als 'later' en laadde dan
    wel: precies het verschil met de beslissing."""
    c = _coordinator(make_coordinator)
    geladen = c._plan_laadt(_netregels(blok=False), EINDE, 0.302, soc=6.4, bruikbaar=7.5,
                            laad_kwh=0.6, per_kwartier=0.6)
    assert geladen > 0.0


def test_buiten_het_blok_verandert_er_niets(make_coordinator):
    c = _coordinator(make_coordinator)
    regels = _netregels()
    regels["blok"] = (BLOK + timedelta(days=1), BLOK_EIND + timedelta(days=1))
    met = c._plan_laadt(regels, EINDE, 0.302, soc=6.4, bruikbaar=7.5, laad_kwh=0.6, per_kwartier=0.6)
    zonder = c._plan_laadt(_netregels(blok=False), EINDE, 0.302, soc=6.4, bruikbaar=7.5,
                           laad_kwh=0.6, per_kwartier=0.6)
    assert met == zonder


def test_netregels_geven_het_blok_mee():
    from pathlib import Path

    bron = (Path(__file__).resolve().parents[1] / "custom_components" / "energy_management_system"
            / "coordinator.py").read_text(encoding="utf-8")
    assert '"blok": (self.last_cheap_block_start, self.last_cheap_block_end),' in bron
    assert "if begin is None or begin <= kwartier or begin >= blok_eind:" in bron


# --- planvolging: "andere keuze" en de juiste woorden ---------------------


def _gepland(accu_w=-2386, modus="manual (laden)"):
    return {"kwartier": KWARTIER.isoformat(), "van": "13:15", "modus": modus,
            "accu_w": accu_w, "zon_w": 2250, "huis_w": 990}


def test_andere_stand_is_de_sturing_niet_de_accu():
    o = pv.beoordeel(_gepland(), -1808, 1972, 175, stand="smart_charging")
    assert o["oorzaak"] == "sturing" and o["status"] == "afwijking sturing"
    assert "de sturing koos sparen (alleen zon laden) in plaats van laden van het net" in o["tekst"]
    assert o["verschil_tekst"] == "minder laden"


def test_zelfde_soort_stand_blijft_zoals_het_was():
    o = pv.beoordeel(_gepland(), -1808, 2250, 990, stand="manual")
    assert o["oorzaak"] == "accu" and o["status"] == "afwijking accu"


def test_zonder_stand_zoals_voorheen():
    o = pv.beoordeel(_gepland(), -1808, 2250, 990)
    assert o["oorzaak"] == "accu"


def test_verschil_in_woorden():
    assert pv.verschil_tekst(-2386, -1808) == "minder laden"
    assert pv.verschil_tekst(-1000, -1800) == "meer laden"
    assert pv.verschil_tekst(1000, 1600) == "meer ontladen"
    assert pv.verschil_tekst(1600, 1000) == "minder ontladen"
    assert pv.verschil_tekst(-500, 400) == "meer ontladen"
    assert pv.verschil_tekst(-500, -480) == "geen"


def test_kwartieroordeel_neemt_de_meest_voorkomende_stand():
    monsters = [{"accu_w": -1800, "zon_w": 2000, "huis_w": 200, "stand": "smart_charging"}] * 3
    o = pv.sluit_kwartier(_gepland(), monsters)
    assert o["oorzaak"] == "sturing"


def test_cockpit_gebruikt_de_woorden():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "custom_components" / "energy_management_system"
          / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert "nu.verschil_tekst ? esc(nu.verschil_tekst)" in js
    assert '"andere keuze"' in js
