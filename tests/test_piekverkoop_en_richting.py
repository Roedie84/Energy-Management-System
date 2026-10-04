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

    # v5.28.4 - VERWACHTING BEWUST GEWIJZIGD: "huis dient altijd voor te
    # gaan". Onder de reserve wordt helemaal niet meer verkocht - dus ook
    # nooit door de bodem.
    op_de_bodem = c._geen_ruimte_boven_reserve(NU, reeks, BLOK, 1.30, 4.0, 1600.0, 0.25)
    assert op_de_bodem is None

    erboven = c._geen_ruimte_boven_reserve(NU, reeks, BLOK, 2.0, 4.0, 1600.0, 0.25)
    assert erboven is None
    assert "het huis gaat voor" in c.last_piekverkoop["reden"]


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


def test_de_huisgrens_gaat_voor_de_piekregel(make_coordinator, hass):
    """v5.28.4 - VERWACHTING BEWUST GEWIJZIGD. v5.26.3 liet de piekregel
    voor de huisgrens gaan (30 september: 86%, 44,7 ct, niets verkocht). Op
    3 oktober verkocht die regel de accu leeg tot 25% en haalde het huis
    vannacht 2,9 kWh van het net. "Huis dient altijd voor te gaan": de
    huisgrens beslist."""
    c = make_coordinator({})
    c.may_sell_now = lambda now, beschikbaar=None: {
        "mag_verkopen": False,
        "reden": "het huis heeft 8.64 kWh nodig tot het goedkope blok",
    }
    reeks = _reeks(NU, [0.448, 0.435, 0.433, 0.41, 0.38] + [0.30] * 40)

    ruimte = c._verkoopruimte_met_piek(NU, reeks, BLOK, 6.6)

    assert ruimte["mag_verkopen"] is False
    assert "8.64" in ruimte["reden"]


def test_zonder_piek_blijft_de_huisgrens_staan(make_coordinator, hass):
    """Komt er nog een duurder kwartier, dan houdt de huisgrens stand."""
    c = make_coordinator({})
    c.may_sell_now = lambda now, beschikbaar=None: {"mag_verkopen": False, "reden": "huis gaat voor"}
    reeks = _reeks(NU, [0.447, 0.448] + [0.30] * 40)

    ruimte = c._verkoopruimte_met_piek(NU, reeks, BLOK, 6.6)

    assert ruimte["mag_verkopen"] is False
    assert ruimte["reden"] == "huis gaat voor"


# --- v5.26.5: tot de accu weer wordt bijgevuld -----------------------------

TZ2 = timezone(timedelta(hours=2))
OCHTEND = datetime(2026, 10, 1, 8, 0, tzinfo=TZ2)
BLOK_1OKT = datetime(2026, 10, 1, 10, 45, tzinfo=TZ2)


def _dag_1_oktober(blokprijs):
    """Ochtend 44,8 / 41,9 / 40,4 ct, blok 10:45-16:30, avond tot 51,2 ct."""
    reeks = []
    t = OCHTEND
    while t < OCHTEND + timedelta(hours=16):
        h = t.hour + t.minute / 60
        if h < 9: p = 0.448 if t.minute == 0 else 0.418
        elif h < 10: p = 0.419 if t.minute == 0 else 0.397
        elif h < 10.75: p = 0.404 if t.minute == 0 else 0.377
        elif h < 16.5: p = blokprijs
        elif h < 19.5: p = 0.46
        elif h < 19.75: p = 0.512
        else: p = 0.45
        reeks.append((t, p))
        t += timedelta(minutes=15)
    return reeks


def test_de_ochtend_bewaart_als_het_blok_niet_goedkoop_bijvult(make_coordinator, hass):
    """1 oktober: het blok van 31,2 ct vult de accu niet zinvol bij -
    31,2 / 83,7% + 11,4 = 48,7 ct om te vervangen. De avond van 51,2 ct telt
    dus als 48,7, en de ochtend van 44,8 ct bewaart."""
    c = make_coordinator({})
    reeks = _dag_1_oktober(0.312)
    vervang = 0.312 / 0.837 + 0.114

    duurste = c._duurste_later(OCHTEND, reeks, BLOK_1OKT, vervang)

    assert round(duurste, 3) == round(vervang, 3)
    assert 0.448 < duurste  # dus bewaren


def test_de_ochtend_verkoopt_als_het_blok_goedkoop_bijvult(make_coordinator, hass):
    """Zonnige dag, blok van 15 ct: 15 / 83,7% + 11,4 = 29,3 ct. De ochtend
    van 44,8 ct verkoopt - het blok vult goedkoop bij."""
    c = make_coordinator({})
    reeks = _dag_1_oktober(0.15)
    vervang = 0.15 / 0.837 + 0.114

    duurste = c._duurste_later(OCHTEND, reeks, BLOK_1OKT, vervang)

    assert 0.448 > duurste  # dus verkopen


def test_zonder_vervangprijs_zoals_voorheen_tot_het_blok(make_coordinator, hass):
    c = make_coordinator({})
    reeks = _dag_1_oktober(0.312)

    duurste = c._duurste_later(OCHTEND, reeks, BLOK_1OKT, None)

    assert duurste == 0.419  # alleen de ochtend telt


def test_de_vervangprijs_uit_blok_rendement_en_slijtage(make_coordinator, hass):
    c = make_coordinator({})
    c.last_cheap_block_end = BLOK_1OKT + timedelta(hours=5, minutes=45)
    c.charge_efficiency_history = [83.7] * 7
    c.discharge_efficiency_history = [100.0] * 7
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 11.40}
    entries = [
        (b, b + timedelta(minutes=15), p * PRICE_SCALE_FACTOR)
        for b, p in _dag_1_oktober(0.312)
    ]

    assert round(c._piek_vervangprijs(entries, BLOK_1OKT), 3) == round(0.312 / 0.837 + 0.114, 3)
