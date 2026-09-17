"""Zelfvoorziening telt netlading niet mee (v3.16.0).

Gemeld met een screenshot: "-103.2% Zelfvoorziening". Een schaal die van
0 tot 100 loopt kan niet op min honderd uitkomen.

De rekensom klopte, maar de vraag niet. Op 18 augustus was er 5,88 kWh
geïmporteerd bij 2,87 kWh verbruik - het verschil zat in de ACCU, want de
winterguard had bijgeladen. De formule nam aan dat alle import naar het
huis gaat.
"""


def _c(make_coordinator, verbruik, importeren, netlading=0.0):
    c = make_coordinator({})
    c.gross_consumption_today_kwh = verbruik
    c.grid_import_today_kwh = importeren
    c.grid_charge_today_kwh = netlading
    return c


def test_the_reported_case_is_no_longer_negative(make_coordinator, hass):
    """5,88 kWh import bij 2,87 kWh verbruik, waarvan het meeste de accu
    in ging."""
    c = _c(make_coordinator, verbruik=2.87, importeren=5.88, netlading=3.6)

    ratio = c.self_sufficiency_ratio_percent

    assert 0 <= ratio <= 100


def test_grid_charging_is_not_house_consumption(make_coordinator, hass):
    """Wat er van het net de accu in gaat is geen huisverbruik. Die kWh
    wordt later gebruikt of verkocht, en telt dan mee - niet nu."""
    zonder = _c(make_coordinator, 10.0, 4.0, 0.0).self_sufficiency_ratio_percent
    met = _c(make_coordinator, 10.0, 4.0, 3.0).self_sufficiency_ratio_percent

    assert met > zonder


def test_without_grid_charging_nothing_changes(make_coordinator, hass):
    """Op een gewone dag verandert er niets aan het cijfer."""
    c = _c(make_coordinator, verbruik=10.0, importeren=2.0)

    assert c.self_sufficiency_ratio_percent == 80.0


def test_it_never_goes_below_zero(make_coordinator, hass):
    """Meer netlading dan import kan niet, maar een meetfout wel - en
    dan mag het cijfer niet omslaan."""
    c = _c(make_coordinator, verbruik=5.0, importeren=2.0, netlading=9.0)

    assert c.self_sufficiency_ratio_percent == 100.0


def test_full_grid_supply_is_zero_percent(make_coordinator, hass):
    """Alles van het net, niets in de accu: nul procent zelfvoorziening."""
    c = _c(make_coordinator, verbruik=4.0, importeren=4.0)

    assert c.self_sufficiency_ratio_percent == 0.0


def test_the_counter_rolls_over_at_midnight():
    """Anders telt de netlading van gisteren morgen nog mee."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("self.grid_import_today_kwh = 0.0")
    blok = bron[kop : kop + 200]

    assert "self.grid_charge_today_kwh = 0.0" in blok


def test_the_counter_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "grid_charge_today_kwh" in PERSISTED_PLAIN_FIELDS


def test_the_consistency_check_uses_the_same_formula(make_coordinator, hass):
    """De zelfcontrole rekent de zelfvoorziening na. Rekent die anders,
    dan meldt hij vanaf nu elke dag een fout die er niet is."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("# --- 1. Zelfvoorziening moet volgen uit import en verbruik ---")
    blok = bron[kop : kop + 900]

    assert "grid_charge_today_kwh" in blok


# --- v3.23.1: niet meer afhankelijk van een teller -------------------


def test_it_never_goes_negative_without_the_counter(make_coordinator, hass):
    """Gemeld: "-54% zelfvoorziening", en na de reparatie van v3.16.0
    nog steeds.

    Die reparatie trok de netlading eraf, maar die teller wordt alleen
    gevuld door de kostprijsboekhouding - en die draait niet bij elke
    laadroute. Op 18 augustus stond hij op `None` terwijl er 5,93 kWh
    binnenkwam bij 3,91 kWh verbruik.
    """
    c = _c(make_coordinator, verbruik=3.91, importeren=5.93)
    c.grid_charge_today_kwh = 0.0

    ratio = c.self_sufficiency_ratio_percent

    assert ratio == 0.0


def test_a_missing_counter_does_not_crash(make_coordinator, hass):
    """De teller stond zelfs op `None` - dan mag de som niet omvallen."""
    c = _c(make_coordinator, verbruik=4.0, importeren=2.0)
    c.grid_charge_today_kwh = None

    assert c.self_sufficiency_ratio_percent == 50.0


def test_the_house_cannot_import_more_than_it_used(make_coordinator, hass):
    """Wat er méér binnenkomt dan het huis verbruikt is per definitie
    ergens anders heen gegaan - de accu."""
    c = _c(make_coordinator, verbruik=2.0, importeren=9.0)

    assert c.self_sufficiency_ratio_percent == 0.0
