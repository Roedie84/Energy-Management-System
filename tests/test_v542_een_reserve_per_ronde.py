"""Eén reserve per ronde (v5.42).

Gemeld na de herstart op v5.41 (21:43):

    Eén reserve: Er is een tweede reservedefinitie ingeslopen: brug wijkt
    af van de sturing. Dat was de fout van v3.92 tot v4.1.

Geen tweede formule. De brug rekent vóór het staartstuk, de schemaprojectie
erna - en daartussen zet `_meet_lange_reserve` het deel na het goedkope blok.
Dat staat na een herstart op nul (niet bewaard): de brug rekende zonder de
1,87 kWh lange horizon, de projectie mét, en de projectie schreef de
uitsplitsing waar de zelfcontrole mee vergelijkt. Monte Carlo (v5.40) las
het getal nog eens los.

Nu is de eerste berekening in een ronde DE reserve van die ronde.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 10, 7, 19, 43, tzinfo=timezone.utc)
BLOK = NU + timedelta(hours=16)


def _opzet(c, hass, ronde=NU):
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.beschikbare_energie_kwh = lambda: 5.0
    c._estimate_worst_case_deficit_kwh = lambda now, tot: 3.0
    c.lange_horizon_actief = True
    c._lange_reserve_extra_kwh = 0.0  # net herstart: nog niet gemeten
    c.last_cheap_block_start = BLOK
    c.last_cheap_block_end = BLOK + timedelta(hours=2)
    c.config = dict(c.config or {})
    c.config["available_energy_sensor_entity"] = "sensor.avail"
    hass.states.set("sensor.avail", "5.0")
    c._verkoop_geblokkeerd_door_reserve = False
    c._verkoop_dicht_sinds = None
    c._begin_ronde_cache(ronde)


def _klok(monkeypatch):
    import custom_components.energy_management_system.coordinator as mod

    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)


def test_de_herstart_van_21_43(make_coordinator, hass, monkeypatch):
    """De volgorde van een ronde na een herstart: brug, dan de meting van de
    lange horizon in het staartstuk, dan de projectie. Eén getal."""
    _klok(monkeypatch)
    c = make_coordinator({})
    _opzet(c, hass)

    c._should_postpone_charging([(BLOK, BLOK + timedelta(hours=2), 500)], NU, BLOK)
    brug = c.last_needed_kwh_to_bridge
    c._lange_reserve_extra_kwh = 1.871  # het staartstuk meet
    projectie = c._get_dynamic_discharge_reserve_kwh(NU, BLOK)

    assert projectie == pytest.approx(brug)
    assert c.last_reserve_margin_breakdown["lange_horizon_extra_kwh"] == 0.0
    controle = c.zelfcontrole_een_reserve()
    assert controle["in_orde"], controle


def test_de_volgende_ronde_telt_de_meting_voor_iedereen(make_coordinator, hass, monkeypatch):
    _klok(monkeypatch)
    c = make_coordinator({})
    _opzet(c, hass)
    eerste = c._get_dynamic_discharge_reserve_kwh(NU, BLOK, bewaar=False)
    c._lange_reserve_extra_kwh = 1.871

    c._begin_ronde_cache(NU + timedelta(seconds=1))
    sturing = c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    brug = c._get_dynamic_discharge_reserve_kwh(NU, BLOK, bewaar=False)

    assert sturing > eerste
    assert brug == sturing
    assert c.last_reserve_margin_breakdown["lange_horizon_extra_kwh"] == pytest.approx(1.871)


def test_een_lezer_zonder_bewaren_schrijft_de_uitsplitsing_niet(make_coordinator, hass):
    """Ook niet via de rondecache: de brug rekent als eerste, de sturing
    leest daarna hetzelfde getal en schrijft dan pas."""
    c = make_coordinator({})
    _opzet(c, hass)
    c.last_reserve_margin_breakdown = {"oud": True}

    c._get_dynamic_discharge_reserve_kwh(NU, BLOK, bewaar=False)
    assert c.last_reserve_margin_breakdown == {"oud": True}

    c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    assert c.last_reserve_margin_breakdown["ronde"] == NU.isoformat()


def test_een_ander_moment_of_blok_rekent_apart(make_coordinator, hass):
    """De planning rekent per kwartier van morgen; dat zijn andere vragen."""
    c = make_coordinator({})
    _opzet(c, hass)
    aanroepen = []
    echt = c._bereken_dynamische_reserve_kwh

    def tel(*args, **kwargs):
        aanroepen.append(args[0])
        return echt(*args, **kwargs)

    c._bereken_dynamische_reserve_kwh = tel
    c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    c._get_dynamic_discharge_reserve_kwh(NU, BLOK, bewaar=False)
    c._get_dynamic_discharge_reserve_kwh(NU + timedelta(hours=3), BLOK, bewaar=False)

    assert aanroepen == [NU, NU + timedelta(hours=3)]


def test_zonder_ronde_wordt_gewoon_gerekend(make_coordinator, hass):
    """Tests en de allereerste aanroep hebben geen rondestempel."""
    c = make_coordinator({})
    _opzet(c, hass)
    c._forecast_cache_ronde = None
    voor = c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    c._lange_reserve_extra_kwh = 1.0

    assert c._get_dynamic_discharge_reserve_kwh(NU, BLOK) > voor


def test_monte_carlo_telt_het_deel_na_het_blok_uit_de_reserve(make_coordinator, hass):
    """Monte Carlo blijft adviserend en rekent met hetzelfde getal als de
    sturing, ook als het staartstuk het intussen heeft bijgewerkt."""
    c = make_coordinator({})
    _opzet(c, hass)
    c._lange_reserve_extra_kwh = 0.9
    c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    c._lange_reserve_extra_kwh = 1.871
    c.monte_carlo_horizon_basis = "goedkoopste blok"
    c.monte_carlo_horizon = BLOK

    assert c._monte_carlo_lange_extra() == pytest.approx(0.9)
