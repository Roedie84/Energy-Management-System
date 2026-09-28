"""Alles wat pas na de saldering draait, met gegevens in hun ECHTE vorm (v5.22).

Aanleiding (v5.21): `_verkoop_loont_na_saldering` las de prijsreeks als
woordenboeken terwijl hij uit tupels bestaat. Hij viel nooit om, omdat hij
zolang de saldering loopt meteen stopt - en de toetsen bouwden hun
prijsreeks in diezelfde verkeerde vorm. In 2027 gaan al deze paden
tegelijk aan. Deze module doorloopt ze allemaal met de saldering UIT.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    FEEDIN_PREMIUM_EUR_PER_KWH,
    POST_SALDEREN_DISCHARGE_OVERSHOOT_W,
    POST_SALDEREN_MIN_USEFUL_DISCHARGE_W,
    PRICE_SCALE_FACTOR,
)

NA = datetime(2027, 3, 10, 18, 0, tzinfo=timezone.utc)


def _reeks(start, prijzen):
    """De vorm die `_get_forecast_entries` werkelijk levert."""
    return [
        (start + timedelta(hours=i), start + timedelta(hours=i + 1), p * PRICE_SCALE_FACTOR)
        for i, p in enumerate(prijzen)
    ]


def _na_de_saldering(c):
    c._is_salderen_active = lambda now: False
    return c


def test_de_terugleverwaarde_na_de_saldering(make_coordinator, hass):
    c = _na_de_saldering(make_coordinator({}))
    c._get_forecast_entries = lambda price_key_override=None: _reeks(
        NA - timedelta(minutes=30), [0.08, 0.09]
    )

    waarde = c._get_feedin_value_per_kwh([], NA)

    assert waarde is not None
    assert round(waarde, 4) == round(0.08 + FEEDIN_PREMIUM_EUR_PER_KWH - (
        float(c.instelling("feedin_cost_eur_per_kwh", 0.0) or 0.0)
    ), 4)


def test_ontladen_wordt_begrensd_tot_eigen_verbruik(make_coordinator, hass):
    c = _na_de_saldering(make_coordinator({}))
    c._read_corrected_consumption_power = lambda: 400.0

    assert c.cap_discharge_to_own_consumption(NA, 1600.0) == (
        400.0 + POST_SALDEREN_DISCHARGE_OVERSHOOT_W
    )


def test_te_weinig_verbruik_om_te_ontladen(make_coordinator, hass):
    c = _na_de_saldering(make_coordinator({}))
    c._read_corrected_consumption_power = lambda: POST_SALDEREN_MIN_USEFUL_DISCHARGE_W - 1

    assert c.cap_discharge_to_own_consumption(NA, 1600.0) is None


def test_zonoverschot_opvangen_na_de_saldering(make_coordinator, hass):
    c = _na_de_saldering(make_coordinator({}))
    c._get_expected_pv_power_w = lambda now: 2000.0
    c._read_corrected_consumption_power = lambda: 400.0

    assert c.should_capture_surplus_over_selling(NA) is True


def test_de_verkooptoets_na_de_saldering(make_coordinator, hass):
    c = _na_de_saldering(make_coordinator({}))
    c._get_forecast_entries = lambda **kw: _reeks(NA + timedelta(hours=1), [0.40, 0.45])
    c._get_feedin_value_per_kwh = lambda entries, now: 0.10
    c.charge_efficiency_history = [90.0] * 7
    c.discharge_efficiency_history = [100.0] * 7
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 10.0}

    uitkomst = c._verkoop_loont_na_saldering(NA)

    assert uitkomst is not None
    # 45 ct later vermijden is meer waard dan 10 ct nu verkopen
    assert uitkomst["mag_verkopen"] is False


def test_het_laadbesluit_na_de_saldering(make_coordinator, hass):
    """Na de saldering met de gewone zonverwachting, en zonder fout."""
    c = _na_de_saldering(make_coordinator({}))
    blok = (NA - timedelta(minutes=15), NA + timedelta(hours=2))
    c.huidige_prijs_eur_per_kwh = lambda: 0.10
    c._resterende_laadruimte_kwh = lambda: 3.0
    c.beschikbare_energie_kwh = lambda: 0.4
    c.charge_efficiency_history = [84.0] * 7
    c.discharge_efficiency_history = [100.0] * 7
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 11.4}
    c._verwacht_zonoverschot_kwh = lambda a, b, veilig=True: 0.0
    c._get_forecast_entries = lambda **kw: _reeks(blok[1], [0.40] * 6)

    besluit = c.laadbesluit_uit_het_net(NA, *blok)

    assert besluit["voorzichtige_zon"] is False
    assert besluit["laden"] is True
