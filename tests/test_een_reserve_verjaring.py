"""De zelfcontrole "één reserve" vergeleek twee rondes (v5.6).

Gemeld met een schermafdruk:

    Er is een tweede reservedefinitie ingeslopen: brug wijkt af van de
    sturing. Dat was de fout van v3.92 tot v4.1.

De cijfers:

    sturing         3,240 kWh   reserve_kwh_after_margin
    brug            2,501 kWh
    verkooptoets    3,240 kWh   leest de sturing

Eerst leek dit een vergelijking van appels met peren - de sturing is na
de marge, de brug ervoor. Maar de brug gebruikt DEZELFDE functie
`_get_dynamic_discharge_reserve_kwh`, dus beide zijn na de marge. Ze
zouden gelijk moeten zijn.

De oorzaak zit in `_update_needed_kwh_breakdown_for_display`:

    u = self.last_reserve_margin_breakdown or {} if blok_in_zicht else {}
    if blok_in_zicht and not u:
        self._get_dynamic_discharge_reserve_kwh(now, cheap_block_start)

De sturing HERGEBRUIKT de bewaarde uitsplitsing en rekent alleen
opnieuw als die leeg is. De brug rekent elke ronde vers. Dus de sturing
kan uit een eerdere ronde komen, met een andere zonverwachting en een
ander aantal tekortdagen erin.

Dat is precies de `last_*`-verjaring die in de architectuuraudit als
punt 4 op de lijst stond: snapshots zonder levensduurbeheer. Hier is
het geen theorie meer.

Twee reparaties:
- de uitsplitsing wordt elke ronde verse berekend als er een blok in
  zicht is;
- de zelfcontrole weigert te vergelijken over rondes heen, want twee
  getallen uit verschillende rondes zeggen niets over één definitie.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 18, 11, 15, tzinfo=timezone.utc)


def test_de_uitsplitsing_wordt_elke_ronde_verse_berekend():
    """De voorwaarde `and not u` hoort weg: die maakte de sturing een
    momentopname uit een willekeurige eerdere ronde."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("def _update_needed_kwh_breakdown_for_display")
    j = bron.index("\n    def ", i + 10)
    blok = bron[i:j]

    assert "if blok_in_zicht and not u:" not in blok
    assert "_get_dynamic_discharge_reserve_kwh" in blok


def _klok(monkeypatch):
    """De zelfcontrole vergelijkt `last_cheap_block_start` met de klok;
    zonder vaste klok valt de toets op de echte tijd."""
    import custom_components.energy_management_system.coordinator as mod

    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)


def test_de_zelfcontrole_vergelijkt_niet_over_rondes(
    make_coordinator, hass, monkeypatch
):
    _klok(monkeypatch)
    """Twee getallen uit verschillende rondes zeggen niets over één
    definitie - dan hoort de controle te zwijgen in plaats van alarm te
    slaan."""
    c = make_coordinator({})
    c.last_cheap_block_start = NU + timedelta(hours=2)
    c.last_reserve_margin_breakdown = {
        "reserve_kwh_after_margin": 3.24,
        "ronde": (NU - timedelta(minutes=3)).isoformat(),
    }
    c.last_needed_kwh_to_bridge = 2.501
    c.last_sell_check = {"nodig_voor_woning_kwh": 3.24}
    c._forecast_cache_ronde = NU

    uit = c.zelfcontrole_een_reserve()

    assert uit["in_orde"] is True
    assert "ronde" in uit["uitleg"].lower()


def test_binnen_een_ronde_wordt_er_wel_vergeleken(
    make_coordinator, hass, monkeypatch
):
    _klok(monkeypatch)
    """Anders is de controle uitgezet in plaats van gerepareerd."""
    c = make_coordinator({})
    c.last_cheap_block_start = NU + timedelta(hours=2)
    c.last_reserve_margin_breakdown = {
        "reserve_kwh_after_margin": 3.24,
        "ronde": NU.isoformat(),
    }
    c.last_needed_kwh_to_bridge = 2.501
    c.last_sell_check = {"nodig_voor_woning_kwh": 3.24}
    c._forecast_cache_ronde = NU

    uit = c.zelfcontrole_een_reserve()

    assert uit["in_orde"] is False
    assert "brug" in uit["afwijkend"]


def test_gelijke_getallen_binnen_een_ronde_zijn_in_orde(
    make_coordinator, hass, monkeypatch
):
    _klok(monkeypatch)
    c = make_coordinator({})
    c.last_cheap_block_start = NU + timedelta(hours=2)
    c.last_reserve_margin_breakdown = {
        "reserve_kwh_after_margin": 3.24,
        "ronde": NU.isoformat(),
    }
    c.last_needed_kwh_to_bridge = 3.24
    c.last_sell_check = {"nodig_voor_woning_kwh": 3.24}
    c._forecast_cache_ronde = NU

    assert c.zelfcontrole_een_reserve()["in_orde"] is True


def test_de_uitsplitsing_draagt_het_rondenummer(make_coordinator, hass):
    """Zonder rondenummer is niet te zien of twee getallen bij elkaar
    horen. Dat was de hele oorzaak."""
    from custom_components.energy_management_system.const import (
        DYNAMIC_DISCHARGE_RESERVE_MARGIN,
    )

    c = make_coordinator({})
    c._forecast_cache_ronde = NU
    c.last_reserve_margin_breakdown = {}
    c._estimate_worst_case_deficit_kwh = lambda a, b: 2.0
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.reserve_daily_records = []

    c._get_dynamic_discharge_reserve_kwh(NU, NU + timedelta(hours=2))

    assert c.last_reserve_margin_breakdown.get("ronde") == NU.isoformat()
    assert DYNAMIC_DISCHARGE_RESERVE_MARGIN >= 1.0
