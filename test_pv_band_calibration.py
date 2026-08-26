"""De integratie leert zelf wat de bandbreedte waard is (v2.8.0).

Gevraagd: "Is de spreiding op de verwachting niet heeeeel erg groot? Wat
zegt dit nog?" - en daarna: "Ik wil dat de integratie dit zelf leert, en
bepaalt aan de hand van beschikbare data."

Terechte scepsis. Op 17 augustus liep de voorspelling van 2,4 tot 18,3
kWh op een verwachting van 9,8 - een factor zeven. Zo'n band zegt op
zichzelf niets, en een vaste drempel van 40% met een vaste bonus van 10
procentpunt is dan een aanname en geen meting.
"""
from datetime import date

from custom_components.energy_management_system.const import (
    CONF_SOLAR_TODAY_FORECAST_SENSOR,
    PV_BAND_MIN_DAGEN,
    PV_SPREAD_MARGIN_MAX_PERCENT,
)


def _met_band(make_coordinator, hass, p10=2.4, p90=18.3, verwacht=9.8):
    c = make_coordinator(
        {CONF_SOLAR_TODAY_FORECAST_SENSOR: "sensor.solcast"}
    )
    hass.states.set(
        "sensor.solcast",
        str(verwacht),
        {"estimate": verwacht, "estimate10": p10, "estimate90": p90},
    )
    return c


def _vul(c, posities):
    c.pv_band_history = [
        {
            "datum": f"2026-08-{(i % 28) + 1:02d}",
            "p10_kwh": 2.0,
            "p90_kwh": 18.0,
            "verwacht_kwh": 10.0,
            "werkelijk_kwh": 2.0 + p * 16.0,
            "positie": p,
        }
        for i, p in enumerate(posities)
    ]


def test_the_position_in_the_band_is_recorded(make_coordinator, hass):
    """0 is p10, 1 is p90 - dat is de grootheid waaruit alles volgt."""
    c = _met_band(make_coordinator, hass, p10=2.0, p90=18.0, verwacht=10.0)
    c._energiedagstand = {"opwek_kwh": 10.0}

    c._leg_pv_bandbreedte_vast(date(2026, 8, 17))

    assert c.pv_band_history[0]["positie"] == 0.5


def test_falling_below_p10_is_recorded_as_negative(make_coordinator, hass):
    """Buiten de band mag - dat is juist het interessante geval."""
    c = _met_band(make_coordinator, hass, p10=2.0, p90=18.0, verwacht=10.0)
    c._energiedagstand = {"opwek_kwh": 1.2}

    c._leg_pv_bandbreedte_vast(date(2026, 8, 17))

    assert c.pv_band_history[0]["positie"] < 0


def test_too_few_days_changes_nothing(make_coordinator, hass):
    """Zolang er te weinig dagen zijn blijft alles bij het oude - een
    verdeling uit drie metingen zegt niets."""
    c = _met_band(make_coordinator, hass)
    _vul(c, [0.4] * (PV_BAND_MIN_DAGEN - 1))

    assert c.get_pv_band_calibration()["beschikbaar"] is False
    assert c.veilige_pv_verwachting_kwh() is None


def test_the_safe_position_is_learned(make_coordinator, hass):
    """De positie die op vier van de vijf dagen werd gehaald."""
    c = _met_band(make_coordinator, hass)
    _vul(c, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0,
             0.35, 0.45, 0.55, 0.65])

    ijking = c.get_pv_band_calibration()

    assert ijking["beschikbaar"] is True
    assert 0.0 < ijking["veilige_positie"] < 0.5


def test_a_pessimistic_solcast_shifts_the_assumption_up(
    make_coordinator, hass
):
    """Landt de opwek steevast hoog in de band, dan mag de reserve
    minder somber doen."""
    c = _met_band(make_coordinator, hass)
    _vul(c, [0.8] * PV_BAND_MIN_DAGEN)

    assert c.get_pv_band_calibration()["veilige_positie"] >= 0.8


def test_an_optimistic_solcast_shifts_it_down(make_coordinator, hass):
    """Valt de opwek structureel onder p10, dan is Solcast te
    optimistisch aan de onderkant en schuift de aanname vanzelf
    omlaag."""
    c = _met_band(make_coordinator, hass)
    _vul(c, [-0.2] * PV_BAND_MIN_DAGEN)

    ijking = c.get_pv_band_calibration()

    assert ijking["veilige_positie"] < 0
    assert ijking["aandeel_onder_p10_procent"] == 100.0


def test_the_margin_follows_the_learned_shortfall(make_coordinator, hass):
    """De marge is hoeveel de veilige aanname tekortschiet op de
    verwachting - niet een verzonnen bonus."""
    c = _met_band(make_coordinator, hass, p10=2.4, p90=18.3, verwacht=9.8)
    _vul(c, [0.25] * PV_BAND_MIN_DAGEN)

    # Veilig = 2,4 + 0,25 x 15,9 = 6,4 kWh, dus 35% onder 9,8 - maar het
    # plafond van 25 procentpunt grijpt in. Zonder plafond zou zo'n
    # brede band de hele accu blokkeren.
    marge = c._pv_onzekerheidsmarge_procent()

    assert marge == PV_SPREAD_MARGIN_MAX_PERCENT


def test_the_margin_is_capped(make_coordinator, hass):
    """Zonder plafond zou een extreem brede band de hele accu
    blokkeren."""
    c = _met_band(make_coordinator, hass, p10=0.1, p90=25.0, verwacht=12.0)
    _vul(c, [-0.5] * PV_BAND_MIN_DAGEN)

    assert c._pv_onzekerheidsmarge_procent() <= PV_SPREAD_MARGIN_MAX_PERCENT


def test_a_reliable_forecast_asks_for_no_extra_margin(
    make_coordinator, hass
):
    """Landt de opwek steevast op de verwachting, dan is er niets extra
    nodig."""
    c = _met_band(make_coordinator, hass, p10=9.0, p90=11.0, verwacht=10.0)
    _vul(c, [0.5] * PV_BAND_MIN_DAGEN)

    assert c._pv_onzekerheidsmarge_procent() == 0.0


def test_a_modest_shortfall_stays_under_the_cap(make_coordinator, hass):
    """Bij een smallere band volgt de marge het werkelijke tekort en
    grijpt het plafond niet in."""
    c = _met_band(make_coordinator, hass, p10=8.0, p90=12.0, verwacht=10.0)
    _vul(c, [0.25] * PV_BAND_MIN_DAGEN)

    # Veilig = 8,0 + 0,25 x 4,0 = 9,0 kWh, dus 10% onder 10,0.
    assert c._pv_onzekerheidsmarge_procent() == 10.0
