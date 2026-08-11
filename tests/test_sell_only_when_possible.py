"""Verkopen alleen als de woning het aankan (v1.23.0).

Gevraagd: "Hij moet actief kijken of verkoop van energie mogelijk is
(dus is er nog genoeg voor mijn woning)." En over de winter: "dan alleen
laden en indien nodig bijladen, en de eigen woning voeden, punt."

Doorgerekend op een winterdag met 5 kWh zon tegen 7,4 kWh verbruik: de
accu verkocht 's ochtends tot nul en stond daarna drie uur leeg terwijl
het huis 25 tot 33 ct per kWh uit het net betaalde.

De bestaande reserve deed wél zijn werk - die bewaarde 1,20 kWh voor de
vier uur tot het goedkope blok. Maar verkopen gaat op 1600 W terwijl het
huis 300 W trekt: ruim vijf keer zo snel. Binnen een uur stond de accu op
de bodem, en daar bleef hij.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_SOLAR_TODAY_FORECAST_SENSOR,
    SELL_RESERVE_SAFETY_FACTOR,
    SOLAR_POOR_DAY_KWH,
)

NU = datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, zon=22.0, met_voorspelling=True):
    config = (
        {CONF_SOLAR_TODAY_FORECAST_SENSOR: "sensor.solcast_vandaag"}
        if met_voorspelling
        else {}
    )
    c = make_coordinator(config)
    c.last_cheap_block_start = NU + timedelta(hours=4)
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: 0.3 * (b - a).total_seconds() / 3600
    )
    # v1.24.2: de dagopbrengst telt nu als "al opgewekt + nog te komen".
    # Gemeld: 's avonds las de oude berekening 0,1 kWh en dus "zonarme
    # dag", terwijl er die dag ruim 20 kWh was geproduceerd.
    #
    # Om 07:00 is er nog niets opgewekt; de rest van de dag draagt het
    # geheel. Het korte venster tot het goedkope blok (vier uur) krijgt
    # een klein deel, zodat de reservetoets iets te toetsen heeft.
    c.pv_production_today_kwh = 0.0
    c._estimate_pv_kwh_for_period = lambda a, b: (
        zon if (b - a).total_seconds() > 10 * 3600 else 0.0
    )
    return c


# --- de winterregel --------------------------------------------------


def test_a_poor_solar_day_never_sells(make_coordinator, hass):
    """"dan alleen laden en indien nodig bijladen, en de eigen woning
    voeden, punt." """
    c = _coordinator(make_coordinator, hass, zon=3.5)

    resultaat = c.may_sell_now(NU, 3.0)

    assert resultaat["mag_verkopen"] is False
    assert "Zonarme dag" in resultaat["reden"]


def test_a_full_battery_on_a_poor_day_still_does_not_sell(
    make_coordinator, hass
):
    """Ook met een volle accu niet: die energie is voor de nacht, en er
    komt die dag te weinig zon om hem opnieuw te vullen."""
    c = _coordinator(make_coordinator, hass, zon=3.5)

    assert c.may_sell_now(NU, 7.0)["mag_verkopen"] is False


def test_the_threshold_is_where_it_was_agreed():
    assert SOLAR_POOR_DAY_KWH == 5.0


# --- de woning gaat voor --------------------------------------------


def test_a_sunny_day_with_enough_charge_may_sell(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    resultaat = c.may_sell_now(NU, 3.0)

    assert resultaat["mag_verkopen"] is True
    assert resultaat["vrij_te_verkopen_kwh"] > 0


def test_a_sunny_day_with_too_little_charge_does_not_sell(
    make_coordinator, hass
):
    """De kern van de melding: verkopen mag niet als het huis daarna aan
    het net komt te hangen."""
    c = _coordinator(make_coordinator, hass)

    resultaat = c.may_sell_now(NU, 1.0)

    assert resultaat["mag_verkopen"] is False
    assert "aan het net" in resultaat["reden"]


def test_the_margin_is_more_than_bare_minimum():
    """Precies genoeg is te krap: een koude avond of een onverwachte
    wasmachine hoort erin te passen."""
    assert SELL_RESERVE_SAFETY_FACTOR >= 1.25


def test_solar_before_the_cheap_block_counts(make_coordinator, hass):
    """Komt er nog zon vóór het goedkope blok, dan hoeft de accu dat
    deel niet te dekken."""
    c = _coordinator(make_coordinator, hass)
    c._estimate_pv_kwh_for_period = lambda a, b: (
        22.0 if (b - a).total_seconds() > 20 * 3600 else 5.0
    )

    resultaat = c.may_sell_now(NU, 1.0)

    assert resultaat["mag_verkopen"] is True


# --- niet blokkeren bij ontbrekende gegevens -------------------------


def test_without_a_forecast_sensor_it_does_not_block(
    make_coordinator, hass
):
    """Zonder Solcast geeft de schatting 0,0 terug, en dat zou elke dag
    als zonarm bestempelen - dan zou er nooit meer verkocht worden voor
    wie die sensor niet heeft."""
    c = _coordinator(make_coordinator, hass, met_voorspelling=False)

    assert c.may_sell_now(NU, 3.0)["mag_verkopen"] is True


def test_without_a_battery_reading_it_does_not_block(
    make_coordinator, hass
):
    """Blokkeren zou een installatie zonder accusensor stilzetten; de
    bestaande reserve blijft dan gelden."""
    c = _coordinator(make_coordinator, hass)
    c.last_available_kwh = None

    resultaat = c.may_sell_now(NU, None)

    assert resultaat["mag_verkopen"] is True
    assert "bestaande reserve" in resultaat["reden"]


# --- inbedding -------------------------------------------------------


def test_it_is_wired_into_the_expensive_quarter_decision():
    """Toetsen zonder toepassen zou niets veranderen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "verkoopruimte = self.may_sell_now(" in bron
    assert 'if is_expensive and not verkoopruimte.get("mag_verkopen")' in bron


# --- v1.24.2: de hele dag telt, niet alleen wat er nog komt ---------


def test_a_good_day_is_not_poor_in_the_evening(make_coordinator, hass):
    """Gemeld: "Zonarme dag is natuurlijk raar om 20:23, de zon is zo
    goed als weg en de dagopbrengst was goed."

    `_estimate_pv_kwh_for_period` kijkt alleen VOORUIT, dus 's avonds
    bleef er 0,1 kWh over en dat las als een zonarme dag - terwijl er
    die dag ruim 20 kWh was opgewekt.
    """
    from datetime import datetime, timezone

    c = _coordinator(make_coordinator, hass, zon=0.1)
    c.pv_production_today_kwh = 20.4
    c._estimate_pv_kwh_for_period = lambda a, b: 0.1
    avond = datetime(2026, 8, 12, 20, 23, tzinfo=timezone.utc)
    c.last_cheap_block_start = avond.replace(hour=23)

    resultaat = c.may_sell_now(avond, 6.5)

    assert resultaat["mag_verkopen"] is True


def test_a_genuinely_poor_day_still_blocks(make_coordinator, hass):
    """De winterregel mag niet verdwijnen: weinig opgewekt én weinig te
    verwachten blijft zonarm."""
    from datetime import datetime, timezone

    c = _coordinator(make_coordinator, hass, zon=0.1)
    c.pv_production_today_kwh = 3.2
    c._estimate_pv_kwh_for_period = lambda a, b: 0.1
    avond = datetime(2026, 8, 12, 20, 23, tzinfo=timezone.utc)

    resultaat = c.may_sell_now(avond, 6.5)

    assert resultaat["mag_verkopen"] is False
    assert "hele dag" in resultaat["reden"]


def test_without_a_day_meter_it_uses_the_forecast(make_coordinator, hass):
    """Zonder dagmeter is de voorspelling van vanochtend de beste
    schatting die er is."""
    from custom_components.energy_management_system.const import (
        CONF_SOLAR_TODAY_FORECAST_SENSOR,
    )

    c = _coordinator(make_coordinator, hass)
    c.pv_production_today_kwh = None
    hass.states.set("sensor.solcast_vandaag", "18.0")
    c.config = {
        **c.config,
        CONF_SOLAR_TODAY_FORECAST_SENSOR: "sensor.solcast_vandaag",
    }

    assert c.may_sell_now(NU, 3.0)["mag_verkopen"] is True


# --- v1.27.0: het diepste moment, niet de nettosom -------------------


def _nacht(make_coordinator, hass):
    """Een avond zoals 10 augustus 20:54: het goedkope blok ligt de
    volgende ochtend, dus er zit een hele nacht tussen.

    De nettosom over die periode trok de zon van MORGENOCHTEND af van
    het verbruik van VANNACHT. Nodig kwam op 1,77 kWh terwijl het
    diepste moment onderweg 5,23 kWh vroeg.
    """
    avond = datetime(2026, 8, 10, 18, 54, tzinfo=timezone.utc)
    c = make_coordinator({CONF_SOLAR_TODAY_FORECAST_SENSOR: "sensor.solcast"})
    c.last_cheap_block_start = avond + timedelta(hours=14)
    c.pv_production_today_kwh = 21.0
    c.learned_hourly_avg_kw = lambda uur: 0.35
    # Zon komt overdag; 's nachts niets.
    c._estimate_pv_kwh_for_period = lambda a, b: (
        0.0
        if a.hour >= 20 or a.hour < 7
        else 1.0 * (b - a).total_seconds() / 3600
    )
    c._estimate_consumption_kwh_for_period = (
        lambda a, b: 0.35 * (b - a).total_seconds() / 3600
    )
    return c, avond


def test_the_night_counts_not_the_net_sum(make_coordinator, hass):
    """De zon van morgenochtend helpt vannacht niet."""
    c, avond = _nacht(make_coordinator, hass)

    nettosom = c._estimate_consumption_kwh_for_period(
        avond, c.last_cheap_block_start
    ) - c._estimate_pv_kwh_for_period(avond, c.last_cheap_block_start)
    diepste = c._estimate_worst_case_deficit_kwh(avond, c.last_cheap_block_start)

    assert diepste > nettosom
    resultaat = c.may_sell_now(avond, 6.91)
    assert resultaat["methode"] == "diepste tekort onderweg"
    assert resultaat["nodig_voor_woning_kwh"] > nettosom


def test_selling_stops_before_the_house_hangs_on_the_grid(
    make_coordinator, hass
):
    """De planning verkocht 10 kwartieren en voorspelde daarna twee
    kwartieren waarin het huis aan het net hing."""
    c, avond = _nacht(make_coordinator, hass)

    krap = c.may_sell_now(avond, 4.0)

    assert krap["mag_verkopen"] is False
    assert "aan het net" in krap["reden"]


def test_a_real_surplus_may_still_be_sold(make_coordinator, hass):
    """De toets mag verkopen niet helemaal stilzetten: wat boven de
    nachtbehoefte uitkomt, is vrij."""
    c, avond = _nacht(make_coordinator, hass)

    ruim = c.may_sell_now(avond, 7.7)

    assert ruim["mag_verkopen"] is True
    assert ruim["vrij_te_verkopen_kwh"] > 0


def test_without_an_hourly_profile_it_falls_back(make_coordinator, hass):
    """Zonder uurprofiel valt die wandeling niet te maken. Dan de oude
    nettosom met de oude, ruimere marge - die was op dát getal
    gekalibreerd."""
    c, avond = _nacht(make_coordinator, hass)
    c.learned_hourly_avg_kw = lambda uur: None

    resultaat = c.may_sell_now(avond, 6.91)

    assert resultaat["methode"].startswith("nettosom")


def test_the_deepest_margin_matches_the_energy_bridge():
    """De 1,5 compenseerde een basis die structureel te laag was. Het
    diepste tekort is zelf al voorzichtig, dus dezelfde marge als de
    energiebrug volstaat."""
    from custom_components.energy_management_system.const import (
        SELL_RESERVE_DEEPEST_SAFETY_FACTOR,
    )

    assert SELL_RESERVE_DEEPEST_SAFETY_FACTOR == 1.15
