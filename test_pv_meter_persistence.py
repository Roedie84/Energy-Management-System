"""Het ijkpunt van de PV-meter overleeft een herstart (v1.16.5).

Gemeld: "Vandaag: 0.0 kWh opgewekt" in het dagoverzicht van 22:00,
terwijl de omvormer die dag 15,5 kWh had geproduceerd.

De dagsleutel en `pv_production_today_kwh` werden wél bewaard, maar het
IJKPUNT van de kWh-meter niet. Na een herstart klopt de dagsleutel dus -
geen dagwissel, geen reset - maar `_pv_energy_meter_day_start` is None,
waarna `_verwerk_pv_meterstand` opnieuw ijkt op de huidige meterstand.

De opwek wordt dan meterstand min huidige stand, oftewel bijna nul, en
dat overschrijft de bewaarde waarde. Bij meerdere herstarts op een dag
blijft alleen de opwek sinds de laatste over.
"""
import custom_components.energy_management_system.const as C


def _persisted() -> set[str]:
    velden: set[str] = set()
    for naam in dir(C):
        if naam.startswith("PERSISTED_") and isinstance(getattr(C, naam), tuple):
            velden |= set(getattr(C, naam))
    return velden


# --- de kern ---------------------------------------------------------


def test_the_calibration_point_is_persisted():
    """Zonder ijkpunt is een cumulatieve meter waardeloos: je weet niet
    meer waar de dag begon."""
    assert "_pv_energy_meter_day_start" in _persisted()


def test_the_last_reading_is_persisted():
    """Nodig voor de teller-reset-bescherming uit v1.9.1; zonder vorige
    stand kan een terugsprong niet herkend worden."""
    assert "_pv_energy_meter_last" in _persisted()


def test_production_survives_a_restart(make_coordinator, hass):
    """Het gerapporteerde geval, met de werkelijke orde van grootte."""
    c = make_coordinator({})
    c._pv_energy_meter_day_start = 12345.6
    c._pv_energy_meter_last = 12361.1
    c.pv_production_today_kwh = 15.5

    c._verwerk_pv_meterstand(12362.0)

    assert c.pv_production_today_kwh == 16.4


def test_without_the_calibration_it_would_start_over(make_coordinator, hass):
    """Legt vast wat er misging, zodat de reden van deze test duidelijk
    blijft als iemand het veld ooit weer uit de lijst haalt."""
    c = make_coordinator({})
    c.pv_production_today_kwh = 15.5

    c._verwerk_pv_meterstand(12361.1)
    c._verwerk_pv_meterstand(12362.0)

    assert c.pv_production_today_kwh < 1.0


# --- samenhang -------------------------------------------------------


def test_the_day_key_is_persisted_too():
    """De sleutel bepaalt of er een dagwissel is; die stond al in
    PERSISTED_DATE_FIELDS - het ijkpunt was de ontbrekende schakel."""
    assert "_self_sufficiency_day_key" in _persisted()
    assert "pv_production_today_kwh" in _persisted()


def test_a_new_day_still_recalibrates(make_coordinator, hass):
    """Bewaren mag de dagwissel niet blokkeren, anders telt de opwek van
    gisteren gewoon door."""
    c = make_coordinator({})
    c._pv_energy_meter_day_start = 12345.6
    c._pv_energy_meter_last = 12361.1

    c._reset_pv_energy_meter_day()

    assert c._pv_energy_meter_day_start != 12345.6
