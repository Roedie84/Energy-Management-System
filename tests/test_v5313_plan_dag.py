"""v5.31.3 - "Komend schema" toont de dag.

Gemeld op 6 oktober 18:38: "Waarom maar tot 00:00?" Het plan liep tot
morgen 23:45 (118 kwartieren, prijzen tot 8 oktober 00:00) en stond helemaal
op smart: één blok van 18:30 tot middernacht van MORGEN. De kaart toonde
alleen het uur.
"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 6, 18, 39, tzinfo=TZ)


def _plan(van, kwartieren, modus="smart"):
    return [
        {"start": (van + timedelta(minutes=15 * i)).isoformat(), "modus": modus, "prijs_ct": 40.0}
        for i in range(kwartieren)
    ]


def test_zes_oktober_tot_morgen_middernacht(make_coordinator):
    c = make_coordinator({})
    c.get_quarter_plan = lambda now=None: _plan(datetime(2026, 10, 6, 18, 30, tzinfo=TZ), 118)
    blok = c.get_plan_blokken(NU)
    assert len(blok) == 1
    assert blok[0]["van_tekst"] == "18:30"
    assert blok[0]["tot_tekst"] == "morgen 24:00"


def test_vandaag_middernacht_is_24_00(make_coordinator):
    c = make_coordinator({})
    c.get_quarter_plan = lambda now=None: _plan(datetime(2026, 10, 6, 22, 0, tzinfo=TZ), 8)
    assert c.get_plan_blokken(NU)[0]["tot_tekst"] == "24:00"


def test_een_blok_morgen(make_coordinator):
    c = make_coordinator({})
    plan = _plan(datetime(2026, 10, 6, 23, 0, tzinfo=TZ), 4) + _plan(
        datetime(2026, 10, 7, 0, 0, tzinfo=TZ), 4, "manual (laden)"
    )
    c.get_quarter_plan = lambda now=None: plan
    blokken = c.get_plan_blokken(NU)
    assert blokken[1]["van_tekst"] == "morgen 00:00"
    assert blokken[1]["tot_tekst"] == "morgen 01:00"
    assert blokken[0]["tot_tekst"] == "24:00"


def test_het_dashboard_toont_de_tekst(make_coordinator):
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    sjabloon = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text(encoding="utf-8")
    assert "''tot_tekst''" in sjabloon and "''van_tekst''" in sjabloon
    assert "as_timestamp(t[0].get(''end''))" not in sjabloon
