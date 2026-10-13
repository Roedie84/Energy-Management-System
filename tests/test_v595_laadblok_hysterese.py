"""v5.95: hysterese bij laden in het goedkope blok.

Gemeld 13-10 (planning): 02:15-02:45 "Laden van net" tussen kwartieren
"slim" - de accu zakte 's nachts naar 99% en werd weer bijgetopt. Ruud:
"Dat rare kwartier kan hij dan toch beter op slim blijven staan" - "Ja bouw
maar". Vanaf 97% (bruikbaar deel) start een nieuwe netlading in het blok
niet meer; een lading die al loopt laadt gewoon door.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.energy_management_system.const import LAADBLOK_HERLAAD_DREMPEL

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 14, 2, 15, tzinfo=TZ)
BLOK = (NU - timedelta(hours=2), NU + timedelta(hours=3))


def test_drempel_is_97_procent():
    assert LAADBLOK_HERLAAD_DREMPEL == 0.97


def test_hysterese_regel(make_coordinator):
    c = make_coordinator({})
    h = c._laadblok_hysterese
    assert h(7.43, 7.5, False) is True          # 99%: niet opnieuw beginnen
    assert h(7.275, 7.5, False) is True         # precies 97%
    assert h(7.2, 7.5, False) is False          # 96%: gewoon laden mag
    assert h(7.43, 7.5, True) is False          # loopt al: doorladen tot vol
    assert h(1.0, 0.0, False) is False          # geen capaciteit bekend


def test_laadt_uit_het_net_volgt_de_vorige_ronde(make_coordinator):
    c = make_coordinator({})
    c.last_reason = "grid_charging_profitable"
    assert c._laadt_uit_het_net() is True
    c.last_reason = "grid_charging_low_solar"
    assert c._laadt_uit_het_net() is True
    c.last_reason = "smart"
    assert c._laadt_uit_het_net() is False


def _live(make_coordinator, beschikbaar, ruimte, vorige):
    c = make_coordinator({})
    c.huidige_prijs_eur_per_kwh = lambda: 0.20
    c._resterende_laadruimte_kwh = lambda: ruimte
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.2}
    c.last_reason = vorige
    return c


def test_beslissing_start_niet_opnieuw_vanaf_97(make_coordinator):
    c = _live(make_coordinator, beschikbaar=7.43, ruimte=0.07, vorige="smart")
    uit = c.laadbesluit_uit_het_net(NU, *BLOK)
    assert uit["laden"] is False
    assert uit.get("hysterese") is True
    assert "niet opnieuw bijladen" in uit["reden"]


def test_beslissing_onder_97_gaat_door_de_gewone_regel(make_coordinator):
    c = _live(make_coordinator, beschikbaar=6.0, ruimte=1.5, vorige="smart")
    uit = c.laadbesluit_uit_het_net(NU, *BLOK)
    assert not uit.get("hysterese")


def test_lopende_lading_wordt_niet_afgebroken(make_coordinator):
    c = _live(make_coordinator, beschikbaar=7.43, ruimte=0.07, vorige="grid_charging_profitable")
    uit = c.laadbesluit_uit_het_net(NU, *BLOK)
    assert not uit.get("hysterese")


def test_plan_gebruikt_dezelfde_toets():
    bron = (Path(__file__).resolve().parents[1] / "custom_components"
            / "energy_management_system" / "coordinator.py").read_text(encoding="utf-8")
    assert 'netregels["laadde_vorig"] = modus == "manual (laden)"' in bron
    assert '"laadde_vorig": self._laadt_uit_het_net()' in bron


def test_plan_laadt_niet_opnieuw_vanaf_97(make_coordinator):
    c = make_coordinator({})
    regels = {"slijtage_ct": 4.2, "rendement": 85.0, "salderen": True, "reeks": [],
              "laadde_vorig": False}
    assert c._plan_laadt(regels, NU, 0.2, soc=7.43, bruikbaar=7.5,
                         laad_kwh=0.6, per_kwartier=0.4) == 0.0
