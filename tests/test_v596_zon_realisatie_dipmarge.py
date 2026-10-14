"""v5.96: zon van vandaag volgt de werkelijkheid; bijladen in een dip met marge.

Gemeld 14-10 06:03: "Wat gaat er mis? Accu nog maar 18% met zo meteen hele
dure kwartieren". 13-10: in het blok pas om 13:30 van het net geladen (zon
zou de accu om 15:03 vullen; de zon gaf 2,95 kWh), accu 78 %. Vannacht bleef
de dip van 26-28 ct liggen voor een ochtendpiek van 47-58 ct: het spaarplan
zag 0,72 kWh nodig tegen 0,75 beschikbaar, zonder marge.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.energy_management_system.const import DIP_MARGE, ZON_REALISATIE_MIN_KWH

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 13, 13, 0, tzinfo=TZ)
BRON = (Path(__file__).resolve().parents[1] / "custom_components" / "energy_management_system"
        / "coordinator.py").read_text(encoding="utf-8")


def _entries(kwh_per_halfuur):
    t = NU.replace(hour=8, minute=0)
    uit = []
    while t < NU.replace(hour=18):
        uit.append((t, t + timedelta(minutes=30), kwh_per_halfuur))
        t += timedelta(minutes=30)
    return uit


def test_constanten():
    assert ZON_REALISATIE_MIN_KWH == 0.5
    assert DIP_MARGE == 1.25


def test_factor(make_coordinator):
    c = make_coordinator({})
    assert c._realisatie_factor(4.0, 2.0) == 0.5
    assert c._realisatie_factor(4.0, 6.0) == 1.0          # nooit omhoog
    assert c._realisatie_factor(0.3, 0.0) is None         # te weinig verwacht
    assert c._realisatie_factor(2.0, -1.0) == 0.0


def test_realisatie_13_oktober(make_coordinator):
    """08:00-13:00 verwacht 10 x 0,4 = 4 kWh, gemeten 1,6 kWh -> 0,4."""
    c = make_coordinator({})
    c.pv_production_today_kwh = 1.6
    c._pv_energy_meter_last = 23426.0
    assert abs(c._zon_realisatie(NU, _entries(0.4)) - 0.4) < 1e-9


def test_vroeg_op_de_dag_geen_correctie(make_coordinator):
    c = make_coordinator({})
    c.pv_production_today_kwh = 0.0
    c._pv_energy_meter_last = 23426.0
    assert c._zon_realisatie(NU.replace(hour=8, minute=30), _entries(0.4)) is None


def test_zonder_opwekmeter_geen_correctie(make_coordinator):
    c = make_coordinator({})
    c.pv_production_today_kwh = 0.0
    c._pv_energy_meter_last = None
    assert c._zon_realisatie(NU, _entries(0.4)) is None


def test_zonschatting_gebruikt_de_voorzichtigste():
    assert '"realisatie": self._zon_realisatie(nu, pv_entries)' in BRON
    assert "remaining_correction_ratio if remaining_correction_ratio is not None else 1.0" in BRON


def test_dip_rekent_met_marge():
    assert "blok, marge=DIP_MARGE)" in BRON
    assert "(b, p, d * DIP_MARGE if d > 0 else d)" in BRON


def test_spaarplan_marge_alleen_tot_het_blok(make_coordinator):
    c = make_coordinator({})
    blok = NU + timedelta(hours=5)
    kw = [(NU + timedelta(minutes=15 * i), NU + timedelta(minutes=15 * (i + 1)), 0.4, 0.1)
          for i in range(24)]
    c.smart_charging_supported = lambda: True
    c.beschikbare_energie_kwh = lambda: 2.2
    c._spaarkwartieren = lambda now, entries, b: list(kw)
    c._spaarkwartieren_op_verkooptoets = lambda k, b: (k, {})
    zonder = c.spaarplan(NU, [], blok)
    met = c.spaarplan(NU, [], blok, marge=1.25)
    assert abs(zonder["nodig_kwh"] - 2.4) < 1e-6
    assert abs(met["nodig_kwh"] - (2.0 * 1.25 + 0.4)) < 1e-6   # 20 kwartieren voor, 4 na het blok
    assert met["marge"] == 1.25
