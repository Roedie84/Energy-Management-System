"""v5.62: de meetlog- en cockpitsensor houden de event loop niet meer vast.

Uit het logboek van 9 oktober: MeetlogSensor ~2,0 s, CockpitSensor 0,7 s.

- Meetlog: de statusregel kopieerde elke 30 seconden ALLE evaluaties van
  vandaag (deepcopy, honderden volledige records) om ze te tellen. Nu wordt
  er zonder kopie geteld, en alleen opnieuw als er iets bij is gekomen.
  Dezelfde tekst.
- Cockpit: de gegevens werden per toestand drie keer opgebouwd (waarde,
  plaat, reden), en voor de eerste ronde elke keer met de trage helft
  erbij. Nu één keer per toestand, en de trage helft één keer.

Aan de sturing verandert niets.
"""
import statistics
import time
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import kwartierenergie

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 9, 12, 0, tzinfo=TZ)


def _evaluatie(i: int) -> dict:
    """Een volledig record, van de omvang die de meetlaag elk kwartier
    wegschrijft."""
    return {
        "evaluation_timestamp": (NU + timedelta(seconds=30 * i)).isoformat(),
        "snapshot_id": "abc123def456",
        "production_action": {"stand": "smart", "vermogen_w": 0, "categorie": "huis", "reden": "x" * 40},
        "recommended_action": {"reden": "x" * 40, "stand": "smart", "vermogen_w": 0},
        "mirror_matches_production": None if i % 7 == 0 else i % 5 != 0,
        "mirror_per_slijtage": {str(ct): "huis" for ct in range(10)},
        "measurements": {f"m{k}": k * 1.1 for k in range(40)},
        "commands": [{"wat": "y" * 30} for _ in range(5)],
        "record": "volledig",
    }


def _kwartier(i: int) -> dict:
    return {"t": f"k{i}", "i": 0.1, "e": 0.0, "p": 0.0, "o": 0.0, "c": 0.0, "h": 0.1,
            "pr": 0.4, "q": "mmmmm", "cov": float(50 + i % 50), "a": [5, 5, 5, 5, 5]}


def _laag(make_coordinator, evaluaties=2000, kwartieren=48):
    from custom_components.energy_management_system.meetlaag import Meetlaag

    laag = Meetlaag(make_coordinator({}))
    laag._dag = NU.date()
    for i in range(evaluaties):
        laag.log.voeg_toe("evaluatie", NU, _evaluatie(i))
    for i in range(kwartieren):
        laag.log.voeg_toe("kwartier", NU, _kwartier(i))
    return laag


def _oude_status(laag) -> str:
    """De statusregel van voor v5.62, letterlijk (met kopieën)."""
    vandaag = laag._dag
    evaluaties = laag.log.regels("evaluatie", vandaag) if vandaag else []
    kwartieren = [kwartierenergie.uitpakken(k) for k in laag.log.regels("kwartier", vandaag)] if vandaag else []
    kwartieren = [k for k in kwartieren if "reden" not in k]
    met_spiegel = [e for e in evaluaties if e.get("mirror_matches_production") is not None]
    spiegel = (
        f"spiegel {round(100 * sum(1 for e in met_spiegel if e['mirror_matches_production']) / len(met_spiegel))}%"
        if met_spiegel else "spiegel -"
    )
    dekking = (
        f"dekking {round(statistics.mean(k.get('coverage_percent') or 0 for k in kwartieren))}%"
        if kwartieren else "dekking -"
    )
    return f"{'ok' if not laag.log.fouten else f'fouten {laag.log.fouten}'} · {len(evaluaties)} evaluaties · {spiegel} · {dekking}"


def test_dezelfde_statusregel(make_coordinator, hass):
    laag = _laag(make_coordinator)
    assert laag.status_tekst() == _oude_status(laag)


def test_lege_dag_en_geen_dag(make_coordinator, hass):
    laag = _laag(make_coordinator, evaluaties=0, kwartieren=0)
    assert laag.status_tekst() == _oude_status(laag) == "ok · 0 evaluaties · spiegel - · dekking -"
    laag._dag = None
    assert laag.status_tekst() == _oude_status(laag)


def test_geen_kopie_van_de_dag(make_coordinator, hass):
    laag = _laag(make_coordinator)

    def nooit(*_a, **_k):
        raise AssertionError("de statusregel kopieert de hele dag")

    laag.log.regels = nooit
    laag.status_tekst()


def test_volgt_nieuwe_regels_en_fouten(make_coordinator, hass):
    laag = _laag(make_coordinator, evaluaties=10, kwartieren=2)
    eerst = laag.status_tekst()

    laag.log.voeg_toe("evaluatie", NU, _evaluatie(11))
    assert laag.status_tekst() != eerst
    assert laag.status_tekst() == _oude_status(laag)

    laag.log.voeg_toe("kwartier", NU, _kwartier(3))
    assert laag.status_tekst() == _oude_status(laag)

    laag.log.fouten += 1
    assert laag.status_tekst().startswith("fouten 1")

    # Een bewaarde dag die na een herstart wordt samengevoegd.
    laag.log.laad_dag("evaluatie", NU.date().isoformat(), {"regels": [_evaluatie(500)]})
    assert laag.status_tekst() == _oude_status(laag)


def test_snel_met_een_volle_dag(make_coordinator, hass):
    laag = _laag(make_coordinator, evaluaties=3000, kwartieren=96)
    start = time.perf_counter()
    oud = _oude_status(laag)
    oude_ms = (time.perf_counter() - start) * 1000

    laag.status_tekst()  # eerste keer telt
    start = time.perf_counter()
    for _ in range(10):
        assert laag.status_tekst() == oud
    ms = (time.perf_counter() - start) * 1000 / 10

    assert ms < 5, ms
    assert ms < oude_ms / 10, (ms, oude_ms)


def test_meetlogsensor_vraagt_de_kopie_niet(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import MeetlogSensor

    c = make_coordinator({})
    laag = _laag(make_coordinator, evaluaties=50)
    c._meetlaag = laag
    laag.log.regels = lambda *a, **k: (_ for _ in ()).throw(AssertionError("kopie"))
    s = MeetlogSensor(c, "x")

    assert "50 evaluaties" in s.native_value
    assert "opslag" in s.extra_state_attributes


# --- cockpit ---------------------------------------------------------------


def test_cockpit_een_keer_per_toestand(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import CockpitSensor

    c = make_coordinator({})
    keren = []
    c.cockpit_gegevens = lambda: keren.append(1) or {"status_kort": "GOED", "status_regel": "alles goed"}
    s = CockpitSensor(c, "x")

    waarde = s.native_value
    attributen = s.extra_state_attributes

    assert waarde == "GOED"
    assert attributen["reden"] == "alles goed"
    assert attributen["plaat"]
    assert len(keren) == 1


def test_cockpit_volgt_de_metingen_wel(make_coordinator, hass, monkeypatch):
    """Eén keer per toestand, niet één keer voor altijd: de volgende
    toestand leest de metingen opnieuw."""
    from custom_components.energy_management_system import sensor as m

    c = make_coordinator({})
    stand = {"status_kort": "GOED"}
    c.cockpit_gegevens = lambda: dict(stand)
    klok = [100.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: klok[0])
    s = m.CockpitSensor(c, "x")

    assert s.native_value == "GOED"
    stand["status_kort"] = "LET OP"
    klok[0] += 5
    assert s.native_value == "LET OP"


def test_de_trage_helft_een_keer_voor_de_eerste_ronde(make_coordinator, hass):
    c = make_coordinator({})
    c._cockpit_context = None
    keren = []
    echt = c._schema_gegevens
    c._schema_gegevens = lambda: keren.append(1) or echt()

    c.cockpit_gegevens()
    c.cockpit_gegevens()
    c.get_cockpit_svg()

    assert len(keren) == 1
    # De ronde ververst hem zoals altijd.
    c.ververs_cockpit_context()
    assert len(keren) == 2


def test_de_plaat_is_dezelfde(make_coordinator, hass):
    c = make_coordinator({})
    c.ververs_cockpit_context()
    gegevens = c.cockpit_gegevens()
    gegevens["moment"] = "09-10 12:00:00"
    c.cockpit_gegevens = lambda: dict(gegevens)

    assert c.get_cockpit_svg() == c.get_cockpit_svg(dict(gegevens))
