"""Verkopen in de piek, laden in het plan en de richtingscontrole (v5.22)."""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    HANDMATIGE_INGREEP_MIN_DUUR_MINUTEN,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 9, 28, 19, 0, tzinfo=timezone.utc)
BLOK = NU + timedelta(hours=16)


def _reeks(start, prijzen):
    return [
        (start + timedelta(minutes=15 * i), start + timedelta(minutes=15 * (i + 1)),
         p * PRICE_SCALE_FACTOR)
        for i, p in enumerate(prijzen)
    ]


# --- de piekverkoop -------------------------------------------------------


def test_het_duurste_kwartier_tot_het_blok_mag_onder_de_reserve(make_coordinator, hass):
    """48 ct nu, daarna nooit meer dan 38 ct tot het blok: verkopen en later
    inkopen levert minstens 10 ct per kWh op."""
    c = make_coordinator({})
    reeks = _reeks(NU, [0.48] + [0.38] * 8 + [0.30] * 50)

    piek = c._piekverkoop(NU, reeks, BLOK, beschikbaar_kwh=3.0)

    assert piek["verkopen"] is True
    assert piek["winst_ct_per_kwh"] == 10.0


def test_komt_er_nog_een_duurder_kwartier_dan_niet(make_coordinator, hass):
    c = make_coordinator({})
    reeks = _reeks(NU, [0.44, 0.48] + [0.30] * 50)

    assert c._piekverkoop(NU, reeks, BLOK, beschikbaar_kwh=3.0)["verkopen"] is False


def test_nooit_door_de_bodem(make_coordinator, hass):
    """De bodem kwam er na de nacht van 30 op 31 augustus (voorspeld 52%
    over, werkelijk 17%). De piekverkoop mag er nooit doorheen."""
    c = make_coordinator({})
    c.last_reserve_margin_breakdown = {"bodem_kwh": 1.30}
    reeks = _reeks(NU, [0.48] + [0.30] * 50)

    op_de_bodem = c._geen_ruimte_boven_reserve(NU, reeks, BLOK, 1.30, 4.0, 1600.0, 0.25)
    assert op_de_bodem is None
    assert c.last_piekverkoop["reden"] == "de bodem is bereikt"

    erboven = c._geen_ruimte_boven_reserve(NU, reeks, BLOK, 2.0, 4.0, 1600.0, 0.25)
    assert erboven == 1600.0


def test_zonder_bekende_bodem_geen_piekverkoop(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reserve_margin_breakdown = {}
    reeks = _reeks(NU, [0.48] + [0.30] * 50)

    assert c._geen_ruimte_boven_reserve(NU, reeks, BLOK, 3.0, 4.0, 1600.0, 0.25) is None


def test_de_import_na_een_piekverkoop_is_verklaard(make_coordinator, hass):
    """Anders telt hij als onverwachte tekortdag en drijft hij de marge op -
    het EMS zou zijn eigen goede besluit afstraffen."""
    from homeassistant.util import dt as dt_util

    c = make_coordinator({})
    c.piekverkoop_tot = (dt_util.now() + timedelta(hours=8)).isoformat()
    assert c._import_verklaard_door_ontlaadgrens("expensive_quarter_soc_protected") is True

    c.piekverkoop_tot = (dt_util.now() - timedelta(minutes=5)).isoformat()
    c._read_corrected_battery_power = lambda: 0.0
    assert c._import_verklaard_door_ontlaadgrens("expensive_quarter_soc_protected") is False


def test_de_piekverkoop_heeft_een_eigen_reden():
    from custom_components.energy_management_system.const import REASON_REGISTRY

    assert REASON_REGISTRY["expensive_quarter_peak"]["titel"] == "Verkopen in de duurste piek"


def test_de_waarom_regels_van_de_piekverkoop(make_coordinator, hass):
    c = make_coordinator({})
    c.last_piekverkoop = c._piekverkoop(
        NU, _reeks(NU, [0.48] + [0.38] * 8), BLOK, beschikbaar_kwh=3.0
    )

    regels = " · ".join(c._waarom_bij_laden("expensive_quarter_peak", [], None))

    assert "48.0 ct" in regels and "38.0 ct" in regels and "10.0 ct per kWh" in regels


# --- laden in het plan ----------------------------------------------------


def test_het_plan_laadt_met_dezelfde_regel_als_de_beslissing(make_coordinator, hass):
    """Zelfde getallen als 27 september: 13,1 ct nu, straks 38,4 ct."""
    c = make_coordinator({})
    c._verwacht_zonoverschot_kwh = lambda a, b, veilig=True: 0.0
    einde = NU + timedelta(minutes=15)
    netregels = {
        "rendement": 83.7,
        "slijtage_ct": 11.40,
        "salderen": True,
        "reeks": [(einde + timedelta(hours=4, minutes=15 * i), p)
                  for i, p in enumerate([0.384] * 8 + [0.22] * 40)],
    }

    geladen = c._plan_laadt(netregels, einde, 0.131, soc=0.4, bruikbaar=7.78,
                            laad_kwh=0.5, per_kwartier=0.4)

    assert geladen == 0.5


def test_het_plan_laadt_niet_als_het_niet_loont(make_coordinator, hass):
    c = make_coordinator({})
    c._verwacht_zonoverschot_kwh = lambda a, b, veilig=True: 0.0
    einde = NU + timedelta(minutes=15)
    netregels = {
        "rendement": 83.7, "slijtage_ct": 11.40, "salderen": True,
        "reeks": [(einde + timedelta(hours=4, minutes=15 * i), 0.22) for i in range(40)],
    }

    assert c._plan_laadt(netregels, einde, 0.131, 0.4, 7.78, 0.5, 0.4) == 0.0


def test_het_duurste_kwartier_tot_het_blok_per_kwartier(make_coordinator, hass):
    """De grens voor de piekverkoop in het plan: het duurste van wat ERNA
    komt, tot het goedkope blok VAN DE BESLISSING (v5.26.4).

    Gemeld via de export van 30 september 20:16: het plan zag de
    nachtkwartieren al als "blok" en voorspelde verkopen om 20:15 tegen
    43,3 ct; de beslissing kende het blok van 10:45 en zag daarvoor nog
    08:00 tegen 44,8 ct."""
    c = make_coordinator({})
    reeks = _reeks(NU, [0.433, 0.318, 0.318, 0.448, 0.30])
    c.last_cheap_block_start = NU + timedelta(minutes=60)

    netregels = c._plan_netregels(NU, reeks, lambda begin: 0.32)

    assert netregels["duurste_tot_blok"][NU] == 0.448
    assert 0.433 < netregels["duurste_tot_blok"][NU]  # dus niet verkopen om 20:15


# --- besluit tegenover actie ---------------------------------------------


def _richting(c, reden, vermogen):
    c.last_reason = reden
    c._read_corrected_battery_power = lambda: vermogen
    c.learning_only = False
    c.force_manual = False
    return c


def test_laden_opgedragen_maar_de_accu_ontlaadt(make_coordinator, hass):
    c = _richting(make_coordinator({}), "grid_charging_profitable", 800.0)

    c._volg_richting(NU)
    assert c.richting_afwijking is None  # nog te kort

    c._volg_richting(NU + timedelta(minutes=HANDMATIGE_INGREEP_MIN_DUUR_MINUTEN))
    assert c.richting_afwijking["verwacht"] == "LADEN"
    assert c.richting_afwijking["gemeten"] == "ONTLADEN"
    punten = " ".join(str(p) for p in c._aandachtspunten_over_de_integratie())
    assert "Besluit en actie wijken af" in punten


def test_stilstand_is_geen_afwijking(make_coordinator, hass):
    """Een volle accu kan niet laden, een lege niet ontladen."""
    c = _richting(make_coordinator({}), "grid_charging_profitable", 0.0)

    c._volg_richting(NU)
    c._volg_richting(NU + timedelta(minutes=10))

    assert c.richting_afwijking is None


def test_in_de_slimme_stand_geen_controle(make_coordinator, hass):
    """Daar volgt de Zendure zelf de P1-meter."""
    c = _richting(make_coordinator({}), "default_smart", -800.0)

    c._volg_richting(NU)
    c._volg_richting(NU + timedelta(minutes=10))

    assert c.richting_afwijking is None


def test_de_afwijking_verdwijnt_als_de_accu_weer_volgt(make_coordinator, hass):
    c = _richting(make_coordinator({}), "expensive_quarter", -800.0)
    c._volg_richting(NU)
    c._volg_richting(NU + timedelta(minutes=5))
    assert c.richting_afwijking is not None

    c._read_corrected_battery_power = lambda: 1600.0
    c._volg_richting(NU + timedelta(minutes=6))

    assert c.richting_afwijking is None


# --- v5.26.3: de piekregel voor de huisgrens ------------------------------


def test_de_piekregel_gaat_voor_de_huisgrens(make_coordinator, hass):
    """30 september 19:30: accu 86%, 44,7 ct, niets verkocht - de huisgrens
    ("8,64 kWh nodig, 7,78 kWh beschikbaar") zette het dure kwartier uit
    voordat de piekregel aan bod kwam."""
    c = make_coordinator({})
    c.may_sell_now = lambda now, beschikbaar=None: {
        "mag_verkopen": False,
        "reden": "het huis heeft 8.64 kWh nodig tot het goedkope blok",
    }
    reeks = _reeks(NU, [0.448, 0.435, 0.433, 0.41, 0.38] + [0.30] * 40)

    ruimte = c._verkoopruimte_met_piek(NU, reeks, BLOK, 6.6)

    assert ruimte["mag_verkopen"] is True
    assert ruimte["methode"] == "piekverkoop"
    assert "8.64" in ruimte["geblokkeerd_door"]


def test_zonder_piek_blijft_de_huisgrens_staan(make_coordinator, hass):
    """Komt er nog een duurder kwartier, dan houdt de huisgrens stand."""
    c = make_coordinator({})
    c.may_sell_now = lambda now, beschikbaar=None: {"mag_verkopen": False, "reden": "huis gaat voor"}
    reeks = _reeks(NU, [0.447, 0.448] + [0.30] * 40)

    ruimte = c._verkoopruimte_met_piek(NU, reeks, BLOK, 6.6)

    assert ruimte["mag_verkopen"] is False
    assert ruimte["reden"] == "huis gaat voor"
